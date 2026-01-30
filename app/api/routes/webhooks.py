from datetime import datetime
from typing import Any, Dict, List, Optional
import logging

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.core.database import get_db
from app.models.property import PropertyContract, PropertyPhoneCall, PropertySMS, PropertyContact, ContractStatus, CallStatus, SMSStatus, SMSDirection
from app.services.docuseal import map_docuseal_status_to_contract_status
from app.services.agent_gateway import get_agent_gateway


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ============ DocuSeal Webhook Event Models ============

class DocuSealWebhookEvent(BaseModel):
    """Model for storing webhook events."""
    event_type: str
    timestamp: datetime
    submission_id: Optional[int] = None
    contract_id: Optional[int] = None
    data: Dict[str, Any]


# In-memory event log (in production, store in database)
_webhook_events: List[DocuSealWebhookEvent] = []


def log_webhook_event(event: DocuSealWebhookEvent):
    """Log webhook event for debugging/auditing."""
    _webhook_events.append(event)
    # Keep only last 100 events in memory
    if len(_webhook_events) > 100:
        _webhook_events.pop(0)
    logger.info(f"DocuSeal webhook: {event.event_type} - submission_id={event.submission_id}")


@router.get("/docuseal/events", response_model=List[DocuSealWebhookEvent])
async def list_docuseal_events(limit: int = 50):
    """
    List recent DocuSeal webhook events for debugging.
    Returns the most recent events first.
    """
    return list(reversed(_webhook_events[-limit:]))


@router.post("/docuseal")
async def docuseal_webhook(
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Receive all DocuSeal webhook events.

    DocuSeal sends the following event types:
    - submission.created: New submission created
    - submission.send: Submission sent to signers
    - submission.completed: All signers have completed
    - submission.expired: Submission expired
    - submission.archived: Submission archived
    - form.viewed: Signer viewed the form
    - form.started: Signer started filling the form
    - form.completed: Individual signer completed their part
    - form.declined: Signer declined to sign
    - template.created: New template created
    - template.updated: Template updated

    Payload structure:
    {
        "event_type": "submission.completed",
        "timestamp": "2024-01-15T10:30:00Z",
        "data": {
            "id": 123,
            "status": "completed",
            "submitters": [...],
            "documents": [...],
            ...
        }
    }
    """
    event_type = payload.get("event_type", "unknown")
    data = payload.get("data", {})
    timestamp_str = payload.get("timestamp")

    # Parse timestamp
    try:
        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00")) if timestamp_str else datetime.utcnow()
    except (ValueError, AttributeError):
        timestamp = datetime.utcnow()

    # Get submission ID from various possible locations
    submission_id = data.get("id") or data.get("submission_id") or data.get("submission", {}).get("id")

    # Create event record
    event = DocuSealWebhookEvent(
        event_type=event_type,
        timestamp=timestamp,
        submission_id=submission_id,
        data=data
    )

    # Log event in background
    background_tasks.add_task(log_webhook_event, event)

    # Handle template events (no contract association)
    if event_type.startswith("template."):
        return {
            "status": "received",
            "event_type": event_type,
            "message": "Template event logged"
        }

    # For submission/form events, try to find and update contract
    if not submission_id:
        return {
            "status": "received",
            "event_type": event_type,
            "message": "No submission_id found, event logged only"
        }

    # Find contract by docuseal_submission_id
    result = await db.execute(
        select(PropertyContract).where(
            PropertyContract.docuseal_submission_id == submission_id
        )
    )
    contract = result.scalar_one_or_none()

    if not contract:
        return {
            "status": "received",
            "event_type": event_type,
            "submission_id": submission_id,
            "message": "Contract not found for submission, event logged only"
        }

    # Update event with contract_id
    event.contract_id = contract.id

    # Process based on event type
    response_message = "Event processed"

    if event_type == "submission.created":
        # Submission was just created
        contract.docuseal_status = "created"
        response_message = "Submission created, contract updated"

    elif event_type == "submission.send":
        # Submission sent to signers
        contract.docuseal_status = "sent"
        contract.status = ContractStatus.PENDING
        response_message = "Submission sent to signers"

    elif event_type == "form.viewed":
        # Signer viewed the document
        contract.docuseal_status = "viewed"
        response_message = "Document viewed by signer"

    elif event_type == "form.started":
        # Signer started filling
        contract.docuseal_status = "in_progress"
        response_message = "Signer started filling document"

    elif event_type == "form.completed":
        # Individual signer completed (may have multiple signers)
        submitters = data.get("submitters", [])
        all_completed = all(s.get("status") == "completed" for s in submitters) if submitters else False

        if all_completed:
            contract.docuseal_status = "completed"
            contract.status = ContractStatus.ACTIVE
            contract.signed_at = timestamp
        else:
            contract.docuseal_status = "partially_signed"

        response_message = f"Signer completed - all done: {all_completed}"

    elif event_type == "form.declined":
        # Signer declined
        contract.docuseal_status = "declined"
        contract.status = ContractStatus.CANCELLED
        response_message = "Signer declined to sign"

    elif event_type == "submission.completed":
        # All signers completed
        contract.docuseal_status = "completed"
        contract.status = ContractStatus.ACTIVE
        contract.signed_at = timestamp

        # Get signed document URL
        documents = data.get("documents", [])
        if documents:
            contract.docuseal_document_url = documents[0].get("url")

        response_message = "All signers completed, contract is now active"

    elif event_type == "submission.expired":
        # Submission expired
        contract.docuseal_status = "expired"
        contract.status = ContractStatus.EXPIRED
        response_message = "Submission expired"

    elif event_type == "submission.archived":
        # Submission archived
        contract.docuseal_status = "archived"
        response_message = "Submission archived"

    else:
        # Handle status from data if event type not specifically handled
        new_status = data.get("status", "")
        if new_status:
            contract.docuseal_status = new_status
            mapped_status = map_docuseal_status_to_contract_status(new_status)
            contract.status = ContractStatus(mapped_status)
            response_message = f"Status updated to {new_status}"

    await db.commit()

    return {
        "status": "processed",
        "event_type": event_type,
        "contract_id": contract.id,
        "contract_status": contract.status.value,
        "docuseal_status": contract.docuseal_status,
        "message": response_message
    }


# ============ Vapi Webhook Events ============

class VapiWebhookEvent(BaseModel):
    """Model for storing Vapi webhook events."""
    event_type: str
    timestamp: datetime
    call_id: Optional[str] = None
    phone_call_id: Optional[int] = None
    data: Dict[str, Any]


# In-memory event log for Vapi events
_vapi_webhook_events: List[VapiWebhookEvent] = []


def log_vapi_webhook_event(event: VapiWebhookEvent):
    """Log Vapi webhook event for debugging/auditing."""
    _vapi_webhook_events.append(event)
    if len(_vapi_webhook_events) > 100:
        _vapi_webhook_events.pop(0)
    logger.info(f"Vapi webhook: {event.event_type} - call_id={event.call_id}")


async def process_call_completion_background(
    call_id: int,
    transcript: str,
    summary: Optional[str] = None
):
    """Background task to extract memories from completed call."""
    from app.core.database import async_session_maker
    try:
        async with async_session_maker() as db:
            gateway = get_agent_gateway(db)
            await gateway.process_call_completion(call_id, transcript, summary)
            logger.info(f"Memory extraction completed for call {call_id}")
    except Exception as e:
        logger.error(f"Failed to extract memories from call {call_id}: {e}")


@router.get("/vapi/events", response_model=List[VapiWebhookEvent])
async def list_vapi_events(limit: int = 50):
    """
    List recent Vapi webhook events for debugging.
    Returns the most recent events first.
    """
    return list(reversed(_vapi_webhook_events[-limit:]))


@router.post("/vapi")
async def vapi_webhook(
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Receive all Vapi webhook events for phone calls.

    Vapi sends the following event types:
    - call.started: Call has started
    - call.ringing: Phone is ringing
    - call.answered: Call was answered
    - call.ended: Call has ended
    - call.failed: Call failed to connect
    - transcript: Real-time transcript update
    - speech.update: Speech detection update
    - function.call: AI requested a function call
    - hang: Call was hung up
    - tool.calls: Tool calls from the AI

    Payload structure varies by event type, but typically includes:
    {
        "message": {
            "type": "end-of-call-report",
            "call": {...},
            "transcript": "...",
            "summary": "...",
            "recordingUrl": "...",
            ...
        }
    }
    """
    message = payload.get("message", {})
    event_type = message.get("type", payload.get("type", "unknown"))
    call_data = message.get("call", {})

    # Get call ID
    vapi_call_id = call_data.get("id") or payload.get("call", {}).get("id")

    # Parse timestamp
    timestamp_str = message.get("timestamp") or payload.get("timestamp")
    try:
        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00")) if timestamp_str else datetime.utcnow()
    except (ValueError, AttributeError, TypeError):
        timestamp = datetime.utcnow()

    # Create event record
    event = VapiWebhookEvent(
        event_type=event_type,
        timestamp=timestamp,
        call_id=vapi_call_id,
        data=payload
    )

    # Log event in background
    background_tasks.add_task(log_vapi_webhook_event, event)

    # If no call ID, just log the event
    if not vapi_call_id:
        return {
            "status": "received",
            "event_type": event_type,
            "message": "No call_id found, event logged only"
        }

    # Find our phone call record
    result = await db.execute(
        select(PropertyPhoneCall).where(
            PropertyPhoneCall.vapi_call_id == vapi_call_id
        )
    )
    phone_call = result.scalar_one_or_none()

    if not phone_call:
        return {
            "status": "received",
            "event_type": event_type,
            "call_id": vapi_call_id,
            "message": "Phone call record not found, event logged only"
        }

    # Update event with our phone call ID
    event.phone_call_id = phone_call.id

    # Process based on event type
    response_message = "Event processed"

    if event_type in ("call-started", "call.started"):
        phone_call.status = CallStatus.IN_PROGRESS
        phone_call.started_at = timestamp
        response_message = "Call started"

    elif event_type in ("call-ringing", "call.ringing"):
        phone_call.status = CallStatus.RINGING
        response_message = "Call ringing"

    elif event_type in ("call-ended", "call.ended", "end-of-call-report"):
        phone_call.status = CallStatus.ENDED
        phone_call.ended_at = timestamp

        # Calculate duration
        if phone_call.started_at:
            phone_call.duration_seconds = int((timestamp - phone_call.started_at).total_seconds())

        # Get transcript from various possible locations
        transcript = message.get("transcript") or call_data.get("transcript")
        if transcript:
            phone_call.transcript = transcript

        # Get summary
        summary = message.get("summary") or call_data.get("summary")
        if summary:
            phone_call.summary = summary

        # Get recording URL
        recording_url = message.get("recordingUrl") or call_data.get("recordingUrl")
        if recording_url:
            phone_call.recording_url = recording_url

        # Get end reason
        end_reason = message.get("endedReason") or call_data.get("endedReason")
        if end_reason:
            # Map certain end reasons to outcomes
            if end_reason == "assistant-ended-call":
                pass  # Normal end
            elif end_reason == "customer-ended-call":
                pass  # Normal end
            elif end_reason == "voicemail":
                phone_call.outcome = "left_voicemail"
            elif end_reason in ("no-answer", "busy"):
                phone_call.status = CallStatus.NO_ANSWER
                phone_call.outcome = end_reason

        response_message = f"Call ended - duration: {phone_call.duration_seconds}s"

        # Trigger memory extraction in background if we have a transcript
        if transcript:
            background_tasks.add_task(
                process_call_completion_background,
                phone_call.id,
                transcript,
                summary
            )

    elif event_type in ("call-failed", "call.failed"):
        phone_call.status = CallStatus.FAILED
        phone_call.ended_at = timestamp

        error_message = message.get("error") or call_data.get("error", {}).get("message", "Unknown error")
        phone_call.outcome = f"failed: {error_message}"
        response_message = f"Call failed: {error_message}"

    elif event_type == "transcript":
        # Real-time transcript update
        transcript = message.get("transcript") or payload.get("transcript")
        if transcript:
            phone_call.transcript = transcript
        response_message = "Transcript updated"

    elif event_type == "status-update":
        # Generic status update
        status = message.get("status") or call_data.get("status")
        if status:
            status_map = {
                "queued": CallStatus.QUEUED,
                "ringing": CallStatus.RINGING,
                "in-progress": CallStatus.IN_PROGRESS,
                "ended": CallStatus.ENDED,
                "failed": CallStatus.FAILED,
            }
            new_status = status_map.get(status.lower())
            if new_status:
                phone_call.status = new_status
        response_message = f"Status updated to {status}"

    await db.commit()

    return {
        "status": "processed",
        "event_type": event_type,
        "phone_call_id": phone_call.id,
        "call_status": phone_call.status.value,
        "message": response_message
    }


# ============ Twilio SMS Webhook Events ============

class TwilioSMSWebhookEvent(BaseModel):
    """Model for storing Twilio SMS webhook events."""
    event_type: str
    timestamp: datetime
    message_sid: Optional[str] = None
    sms_id: Optional[int] = None
    data: Dict[str, Any]


# In-memory event log for Twilio SMS events
_twilio_sms_webhook_events: List[TwilioSMSWebhookEvent] = []


def log_twilio_sms_event(event: TwilioSMSWebhookEvent):
    """Log Twilio SMS webhook event for debugging/auditing."""
    _twilio_sms_webhook_events.append(event)
    if len(_twilio_sms_webhook_events) > 100:
        _twilio_sms_webhook_events.pop(0)
    logger.info(f"Twilio SMS webhook: {event.event_type} - message_sid={event.message_sid}")


async def process_sms_received_background(sms_id: int):
    """Background task to extract memories from received SMS."""
    from app.core.database import async_session_maker
    try:
        async with async_session_maker() as db:
            gateway = get_agent_gateway(db)
            await gateway.process_sms_received(sms_id)
            logger.info(f"Memory extraction completed for SMS {sms_id}")
    except Exception as e:
        logger.error(f"Failed to extract memories from SMS {sms_id}: {e}")


@router.get("/twilio/sms/events", response_model=List[TwilioSMSWebhookEvent])
async def list_twilio_sms_events(limit: int = 50):
    """
    List recent Twilio SMS webhook events for debugging.
    Returns the most recent events first.
    """
    return list(reversed(_twilio_sms_webhook_events[-limit:]))


@router.post("/twilio/sms")
async def twilio_sms_webhook(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    # Twilio sends form data, not JSON
    From: str = "",
    To: str = "",
    Body: str = "",
    MessageSid: str = "",
    AccountSid: str = "",
    NumMedia: str = "0",
    SmsStatus: str = "",
    FromCity: Optional[str] = None,
    FromState: Optional[str] = None,
    FromZip: Optional[str] = None,
    FromCountry: Optional[str] = None,
    ToCity: Optional[str] = None,
    ToState: Optional[str] = None,
    ToZip: Optional[str] = None,
    ToCountry: Optional[str] = None,
    **kwargs  # Capture any additional form fields
):
    """
    Receive Twilio SMS webhooks for incoming messages and status updates.

    Twilio sends webhooks for:
    - Incoming SMS messages (when someone texts your Twilio number)
    - Message status updates (sent, delivered, failed, etc.)

    Webhook payload (form data):
    - MessageSid: Unique message identifier
    - AccountSid: Your Twilio account SID
    - From: Sender phone number (E.164)
    - To: Recipient phone number (E.164)
    - Body: Message text
    - NumMedia: Number of media items
    - SmsStatus: Message status (received, sent, delivered, failed, etc.)
    - From/To City, State, Zip, Country: Location info

    For MMS, additional MediaUrl{N} fields contain media URLs.
    """
    timestamp = datetime.utcnow()

    # Determine event type
    if SmsStatus:
        event_type = f"sms.{SmsStatus.lower()}"
    else:
        event_type = "sms.inbound" if From else "sms.unknown"

    # Collect all data
    payload_data = {
        "from": From,
        "to": To,
        "body": Body,
        "message_sid": MessageSid,
        "account_sid": AccountSid,
        "num_media": int(NumMedia) if NumMedia else 0,
        "sms_status": SmsStatus,
        "from_city": FromCity,
        "from_state": FromState,
        "from_zip": FromZip,
        "from_country": FromCountry,
        "to_city": ToCity,
        "to_state": ToState,
        "to_zip": ToZip,
        "to_country": ToCountry,
        **kwargs  # Include any extra fields like MediaUrl0, MediaUrl1, etc.
    }

    # Collect media URLs
    media_urls = []
    for i in range(int(NumMedia) if NumMedia else 0):
        media_key = f"MediaUrl{i}"
        if media_key in kwargs:
            media_urls.append(kwargs[media_key])
    payload_data["media_urls"] = media_urls

    # Create event record
    event = TwilioSMSWebhookEvent(
        event_type=event_type,
        timestamp=timestamp,
        message_sid=MessageSid,
        data=payload_data
    )

    # Log event in background
    background_tasks.add_task(log_twilio_sms_event, event)

    if not MessageSid:
        return {
            "status": "received",
            "event_type": event_type,
            "message": "No message_sid found, event logged only"
        }

    # Check if this is a status update for an existing outbound message
    result = await db.execute(
        select(PropertySMS).where(PropertySMS.twilio_message_sid == MessageSid)
    )
    existing_sms = result.scalar_one_or_none()

    if existing_sms:
        # This is a status update for an outbound message
        event.sms_id = existing_sms.id

        # Map Twilio status to our status
        status_map = {
            "queued": SMSStatus.QUEUED,
            "sending": SMSStatus.SENDING,
            "sent": SMSStatus.SENT,
            "delivered": SMSStatus.DELIVERED,
            "failed": SMSStatus.FAILED,
            "undelivered": SMSStatus.FAILED,
        }
        if SmsStatus.lower() in status_map:
            existing_sms.status = status_map[SmsStatus.lower()]

        if SmsStatus.lower() == "delivered":
            existing_sms.delivered_at = timestamp

        # Check for error codes
        if "ErrorCode" in kwargs:
            existing_sms.error_code = str(kwargs["ErrorCode"])
        if "ErrorMessage" in kwargs:
            existing_sms.error_message = kwargs["ErrorMessage"]

        await db.commit()

        return {
            "status": "processed",
            "event_type": event_type,
            "sms_id": existing_sms.id,
            "sms_status": existing_sms.status.value,
            "message": f"Status updated to {SmsStatus}"
        }

    # This might be an inbound message - try to match to a property/contact
    if event_type == "sms.inbound" or SmsStatus.lower() == "received":
        # Try to find a contact with this phone number
        result = await db.execute(
            select(PropertyContact).where(PropertyContact.phone == From)
        )
        contact = result.scalar_one_or_none()

        # If we found a matching contact, create an inbound SMS record
        if contact:
            import json
            media_urls_json = json.dumps(media_urls) if media_urls else None

            inbound_sms = PropertySMS(
                property_id=contact.property_id,
                contact_id=contact.id,
                sent_by_id=None,  # Inbound message, no user sent it
                twilio_message_sid=MessageSid,
                phone_number=From,
                from_number=From,
                to_number=To,
                body=Body,
                media_urls=media_urls_json,
                direction=SMSDirection.INBOUND,
                status=SMSStatus.RECEIVED,
                sent_at=timestamp,
            )
            db.add(inbound_sms)
            await db.commit()
            await db.refresh(inbound_sms)

            event.sms_id = inbound_sms.id

            # Trigger memory extraction in background
            background_tasks.add_task(
                process_sms_received_background,
                inbound_sms.id
            )

            return {
                "status": "processed",
                "event_type": event_type,
                "sms_id": inbound_sms.id,
                "property_id": contact.property_id,
                "contact_id": contact.id,
                "message": f"Inbound SMS from {From} linked to contact {contact.name}",
                "memory_extraction": "triggered"
            }

        # No matching contact, just log it
        return {
            "status": "received",
            "event_type": event_type,
            "message_sid": MessageSid,
            "from": From,
            "message": "Inbound SMS logged but no matching contact found"
        }

    return {
        "status": "received",
        "event_type": event_type,
        "message_sid": MessageSid,
        "message": "Event logged"
    }


@router.post("/twilio/sms/status")
async def twilio_sms_status_webhook(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    MessageSid: str = "",
    MessageStatus: str = "",
    ErrorCode: Optional[str] = None,
    ErrorMessage: Optional[str] = None,
    **kwargs
):
    """
    Receive Twilio SMS status callback webhooks.

    This is a separate endpoint for status updates only.
    Configure this URL in your Twilio message status callback settings.

    Status values: queued, sending, sent, delivered, undelivered, failed
    """
    timestamp = datetime.utcnow()
    event_type = f"sms.status.{MessageStatus.lower()}" if MessageStatus else "sms.status.unknown"

    # Create event record
    event = TwilioSMSWebhookEvent(
        event_type=event_type,
        timestamp=timestamp,
        message_sid=MessageSid,
        data={
            "message_sid": MessageSid,
            "status": MessageStatus,
            "error_code": ErrorCode,
            "error_message": ErrorMessage,
            **kwargs
        }
    )

    background_tasks.add_task(log_twilio_sms_event, event)

    if not MessageSid:
        return {"status": "received", "message": "No message_sid"}

    # Find and update the SMS record
    result = await db.execute(
        select(PropertySMS).where(PropertySMS.twilio_message_sid == MessageSid)
    )
    sms = result.scalar_one_or_none()

    if not sms:
        return {
            "status": "received",
            "event_type": event_type,
            "message_sid": MessageSid,
            "message": "SMS record not found"
        }

    event.sms_id = sms.id

    # Map status
    status_map = {
        "queued": SMSStatus.QUEUED,
        "sending": SMSStatus.SENDING,
        "sent": SMSStatus.SENT,
        "delivered": SMSStatus.DELIVERED,
        "failed": SMSStatus.FAILED,
        "undelivered": SMSStatus.FAILED,
    }
    if MessageStatus.lower() in status_map:
        sms.status = status_map[MessageStatus.lower()]

    if MessageStatus.lower() == "delivered":
        sms.delivered_at = timestamp

    if ErrorCode:
        sms.error_code = ErrorCode
    if ErrorMessage:
        sms.error_message = ErrorMessage

    await db.commit()

    return {
        "status": "processed",
        "event_type": event_type,
        "sms_id": sms.id,
        "sms_status": sms.status.value,
        "message": f"Status updated to {MessageStatus}"
    }

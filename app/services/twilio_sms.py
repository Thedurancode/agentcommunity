"""
Twilio SMS Service for sending and receiving text messages.
"""
from typing import Any, Dict, List, Optional
import logging

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from app.core.config import settings


logger = logging.getLogger(__name__)


class TwilioService:
    """Service for interacting with Twilio SMS API."""

    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.from_number = settings.TWILIO_PHONE_NUMBER
        self._client: Optional[Client] = None

    @property
    def client(self) -> Client:
        """Lazy initialization of Twilio client."""
        if self._client is None:
            if not self.account_sid or not self.auth_token:
                raise ValueError("Twilio credentials not configured")
            self._client = Client(self.account_sid, self.auth_token)
        return self._client

    async def send_sms(
        self,
        to_number: str,
        message: str,
        from_number: Optional[str] = None,
        media_urls: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Send an SMS message.

        Args:
            to_number: Recipient phone number in E.164 format (+1234567890)
            message: Message body (max 1600 chars for SMS, 5000 for MMS)
            from_number: Optional sender number (defaults to configured number)
            media_urls: Optional list of media URLs for MMS

        Returns:
            Dict with message SID, status, and other details
        """
        if not from_number:
            from_number = self.from_number

        if not from_number:
            raise ValueError("No from_number configured")

        try:
            params = {
                "body": message,
                "from_": from_number,
                "to": to_number,
            }

            if media_urls:
                params["media_url"] = media_urls

            # Twilio client is synchronous, but we wrap it for consistency
            msg = self.client.messages.create(**params)

            logger.info(f"SMS sent: {msg.sid} to {to_number}")

            return {
                "message_sid": msg.sid,
                "status": msg.status,
                "to": msg.to,
                "from": msg.from_,
                "body": msg.body,
                "date_sent": msg.date_sent,
                "direction": "outbound",
                "error_code": msg.error_code,
                "error_message": msg.error_message,
            }

        except TwilioRestException as e:
            logger.error(f"Twilio error sending SMS to {to_number}: {e.msg}")
            raise

    async def get_message(self, message_sid: str) -> Dict[str, Any]:
        """
        Get details of a specific message.

        Args:
            message_sid: The Twilio message SID

        Returns:
            Dict with message details
        """
        try:
            msg = self.client.messages(message_sid).fetch()

            return {
                "message_sid": msg.sid,
                "status": msg.status,
                "to": msg.to,
                "from": msg.from_,
                "body": msg.body,
                "date_sent": msg.date_sent,
                "date_created": msg.date_created,
                "direction": msg.direction,
                "error_code": msg.error_code,
                "error_message": msg.error_message,
                "num_segments": msg.num_segments,
                "price": msg.price,
                "price_unit": msg.price_unit,
            }

        except TwilioRestException as e:
            logger.error(f"Twilio error fetching message {message_sid}: {e.msg}")
            raise

    async def list_messages(
        self,
        to_number: Optional[str] = None,
        from_number: Optional[str] = None,
        limit: int = 50,
        date_sent_after: Optional[str] = None,
        date_sent_before: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List messages with optional filters.

        Args:
            to_number: Filter by recipient number
            from_number: Filter by sender number
            limit: Maximum number of messages to return
            date_sent_after: Filter messages sent after this date (ISO format)
            date_sent_before: Filter messages sent before this date (ISO format)

        Returns:
            List of message dictionaries
        """
        try:
            params = {"limit": limit}

            if to_number:
                params["to"] = to_number
            if from_number:
                params["from_"] = from_number
            if date_sent_after:
                params["date_sent_after"] = date_sent_after
            if date_sent_before:
                params["date_sent_before"] = date_sent_before

            messages = self.client.messages.list(**params)

            return [
                {
                    "message_sid": msg.sid,
                    "status": msg.status,
                    "to": msg.to,
                    "from": msg.from_,
                    "body": msg.body,
                    "date_sent": msg.date_sent,
                    "direction": msg.direction,
                }
                for msg in messages
            ]

        except TwilioRestException as e:
            logger.error(f"Twilio error listing messages: {e.msg}")
            raise


# Singleton instance
_twilio_service: Optional[TwilioService] = None


def get_twilio_service() -> TwilioService:
    """Get or create Twilio service singleton."""
    global _twilio_service
    if _twilio_service is None:
        _twilio_service = TwilioService()
    return _twilio_service

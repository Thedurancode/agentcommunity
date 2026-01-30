"""
Agent Gateway Service - The orchestration layer for AI agents.

This service:
1. Accepts natural language instructions
2. Parses intent and required actions
3. Automatically gathers context (memories, preferences, history)
4. Executes actions (calls, SMS, etc.) with context injected
5. Extracts and stores memories from results
6. Tracks task execution

This is the single entry point for AI agents to interact with the system.
"""
import json
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.agent_task import AgentTask, AgentTaskStep, TaskStatus, TaskType
from app.models.property import Property, PropertyContact, PropertyPhoneCall, PropertySMS, CallStatus, SMSStatus, SMSDirection
from app.models.agent_memory import MemoryType, MemorySourceType
from app.schemas.memory import AgentContextRequest, MemoryCreate, MemoryExtractionRequest
from app.services.memory import get_memory_service
from app.services.memory_extraction import get_extraction_service
from app.services.vapi import VapiService
from app.services.twilio_sms import get_twilio_service


# Intent parsing prompt
INTENT_PARSING_PROMPT = """You are an AI assistant that parses user instructions into structured actions.

Given an instruction, identify:
1. task_type: One of "call", "sms", "follow_up", "research", "schedule", "custom"
2. action: The specific action to take
3. target: Who/what is the target (contact name, phone number, etc.)
4. purpose: The purpose or goal of the action
5. additional_context: Any additional context or requirements

Respond in JSON format only:
{
    "task_type": "call|sms|follow_up|research|schedule|custom",
    "action": "make_call|send_sms|lookup_info|schedule_meeting|other",
    "target": "contact name or identifier",
    "purpose": "brief description of purpose",
    "additional_context": "any other relevant details",
    "requires_contact": true/false,
    "requires_property": true/false
}"""


class AgentGatewayService:
    """
    Main orchestration service for AI agents.

    Handles the complete lifecycle of agent tasks:
    - Intent parsing
    - Context gathering
    - Action execution
    - Memory extraction
    - Task tracking
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._anthropic_client = None
        self._memory_service = None
        self._extraction_service = None

    @property
    def anthropic_client(self):
        """Lazy-load Anthropic client."""
        if self._anthropic_client is None:
            if not settings.ANTHROPIC_API_KEY:
                raise ValueError("ANTHROPIC_API_KEY not configured")
            import anthropic
            self._anthropic_client = anthropic.AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY
            )
        return self._anthropic_client

    @property
    def memory_service(self):
        if self._memory_service is None:
            self._memory_service = get_memory_service(self.db)
        return self._memory_service

    @property
    def extraction_service(self):
        if self._extraction_service is None:
            self._extraction_service = get_extraction_service(self.db)
        return self._extraction_service

    def is_available(self) -> bool:
        """Check if gateway is available."""
        return bool(settings.ANTHROPIC_API_KEY)

    # ============ Intent Parsing ============

    async def parse_intent(self, instruction: str) -> Dict[str, Any]:
        """Parse natural language instruction into structured intent."""
        response = await self.anthropic_client.messages.create(
            model=settings.AI_MODEL,
            max_tokens=500,
            system=INTENT_PARSING_PROMPT,
            messages=[{"role": "user", "content": instruction}]
        )

        response_text = response.content[0].text

        # Parse JSON
        try:
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            return json.loads(response_text.strip())
        except json.JSONDecodeError:
            return {
                "task_type": "custom",
                "action": "unknown",
                "target": None,
                "purpose": instruction,
                "additional_context": None,
                "requires_contact": False,
                "requires_property": False
            }

    # ============ Context Building ============

    async def build_context(
        self,
        property_id: Optional[int] = None,
        contact_id: Optional[int] = None,
        purpose: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build comprehensive context for an AI action.

        Gathers:
        - Property details
        - Contact details and preferences
        - Relevant memories (semantic search if purpose provided)
        - Recent conversation history
        - Open commitments
        """
        context = {
            "property": None,
            "contact": None,
            "preferences": None,
            "memories": [],
            "recent_conversations": [],
            "open_commitments": [],
            "system_instructions": []
        }

        # Get property details
        if property_id:
            result = await self.db.execute(
                select(Property).where(Property.id == property_id)
            )
            property = result.scalar_one_or_none()
            if property:
                context["property"] = {
                    "id": property.id,
                    "name": property.name,
                    "address": ", ".join(filter(None, [
                        property.address, property.city, property.state, property.zip_code
                    ])) or None,
                    "type": property.property_type,
                    "status": property.status.value if property.status else None,
                    "description": property.description
                }

        # Get contact details
        if contact_id:
            result = await self.db.execute(
                select(PropertyContact).where(PropertyContact.id == contact_id)
            )
            contact = result.scalar_one_or_none()
            if contact:
                context["contact"] = {
                    "id": contact.id,
                    "name": contact.name,
                    "phone": contact.phone,
                    "email": contact.email,
                    "company": contact.company,
                    "type": contact.contact_type.value if contact.contact_type else None,
                    "notes": contact.notes
                }

                # Get preferences
                pref = await self.memory_service.get_or_create_preferences(contact_id)
                if pref:
                    context["preferences"] = {
                        "preferred_channel": pref.preferred_channel,
                        "preferred_time": pref.preferred_time,
                        "do_not_call": pref.do_not_call,
                        "do_not_text": pref.do_not_text,
                        "formality_level": pref.formality_level,
                        "language": pref.language
                    }

                    # Add system instructions based on preferences
                    if pref.do_not_call:
                        context["system_instructions"].append(
                            "WARNING: Contact has requested NO PHONE CALLS. Use SMS or email instead."
                        )
                    if pref.do_not_text:
                        context["system_instructions"].append(
                            "WARNING: Contact has requested NO TEXT MESSAGES. Use phone or email instead."
                        )
                    if pref.preferred_time:
                        context["system_instructions"].append(
                            f"Contact prefers to be contacted: {pref.preferred_time}"
                        )
                    if pref.formality_level:
                        context["system_instructions"].append(
                            f"Communication style: {pref.formality_level}"
                        )

        # Get memories using semantic search if purpose provided
        if self.memory_service.is_available() and purpose:
            from app.schemas.memory import VectorSearchRequest
            try:
                search_request = VectorSearchRequest(
                    query=purpose,
                    property_id=property_id,
                    contact_id=contact_id,
                    limit=10,
                    min_similarity=0.5
                )
                memories = await self.memory_service.semantic_search(search_request)
                context["memories"] = [
                    {"content": m.content, "type": m.memory_type.value, "importance": m.importance}
                    for m in memories
                ]
            except Exception:
                # Fall back to regular memory retrieval
                memories = await self.memory_service.list_memories(
                    property_id=property_id,
                    contact_id=contact_id,
                    limit=10
                )
                context["memories"] = [
                    {"content": m.content, "type": m.memory_type.value, "importance": m.importance}
                    for m in memories
                ]
        else:
            # Regular memory retrieval
            memories = await self.memory_service.list_memories(
                property_id=property_id,
                contact_id=contact_id,
                limit=10
            )
            context["memories"] = [
                {"content": m.content, "type": m.memory_type.value, "importance": m.importance}
                for m in memories
            ]

        # Get open commitments
        commitment_memories = await self.memory_service.list_memories(
            property_id=property_id,
            contact_id=contact_id,
            memory_types=[MemoryType.COMMITMENT],
            limit=5
        )
        context["open_commitments"] = [
            {"content": m.content, "created_at": m.created_at.isoformat()}
            for m in commitment_memories
        ]

        # Get recent conversations
        conversations = await self.memory_service.get_recent_conversations(
            property_id=property_id,
            contact_id=contact_id,
            limit=3
        )
        context["recent_conversations"] = [
            {
                "summary": c.summary,
                "date": c.conversation_at.isoformat(),
                "sentiment": c.sentiment,
                "action_items": json.loads(c.action_items) if c.action_items else None
            }
            for c in conversations
        ]

        return context

    def format_context_for_prompt(self, context: Dict[str, Any]) -> str:
        """Format context into a string for injection into AI prompts."""
        parts = []

        # System instructions (warnings)
        if context.get("system_instructions"):
            parts.append("=== IMPORTANT ===")
            for instruction in context["system_instructions"]:
                parts.append(f"- {instruction}")
            parts.append("")

        # Property info
        if context.get("property"):
            p = context["property"]
            parts.append("=== Property Information ===")
            parts.append(f"Name: {p['name']}")
            if p.get("address"):
                parts.append(f"Address: {p['address']}")
            if p.get("type"):
                parts.append(f"Type: {p['type']}")
            if p.get("status"):
                parts.append(f"Status: {p['status']}")
            if p.get("description"):
                parts.append(f"Description: {p['description']}")
            parts.append("")

        # Contact info
        if context.get("contact"):
            c = context["contact"]
            parts.append("=== Contact Information ===")
            parts.append(f"Name: {c['name']}")
            if c.get("company"):
                parts.append(f"Company: {c['company']}")
            if c.get("type"):
                parts.append(f"Role: {c['type']}")
            if c.get("notes"):
                parts.append(f"Notes: {c['notes']}")
            parts.append("")

        # Memories (facts learned)
        if context.get("memories"):
            parts.append("=== What We Know ===")
            for m in context["memories"]:
                parts.append(f"- [{m['type']}] {m['content']}")
            parts.append("")

        # Open commitments
        if context.get("open_commitments"):
            parts.append("=== Open Commitments ===")
            for c in context["open_commitments"]:
                parts.append(f"- {c['content']} (from {c['created_at'][:10]})")
            parts.append("")

        # Recent conversations
        if context.get("recent_conversations"):
            parts.append("=== Recent Conversations ===")
            for conv in context["recent_conversations"]:
                parts.append(f"[{conv['date'][:10]}] {conv['summary']}")
                if conv.get("action_items"):
                    parts.append(f"  Action items: {', '.join(conv['action_items'])}")
            parts.append("")

        return "\n".join(parts)

    # ============ Task Execution ============

    async def execute(
        self,
        instruction: str,
        property_id: Optional[int] = None,
        contact_id: Optional[int] = None,
        user_id: int = None,
        auto_execute: bool = True
    ) -> AgentTask:
        """
        Main entry point for agent execution.

        1. Creates a task record
        2. Parses the instruction
        3. Builds context
        4. Executes the appropriate action
        5. Stores results and extracts memories
        """
        start_time = datetime.utcnow()

        # Parse intent
        intent = await self.parse_intent(instruction)

        # Map task type
        task_type_map = {
            "call": TaskType.CALL,
            "sms": TaskType.SMS,
            "follow_up": TaskType.FOLLOW_UP,
            "research": TaskType.RESEARCH,
            "schedule": TaskType.SCHEDULE,
        }
        task_type = task_type_map.get(intent.get("task_type"), TaskType.CUSTOM)

        # Create task record
        task = AgentTask(
            initiated_by_id=user_id,
            property_id=property_id,
            contact_id=contact_id,
            task_type=task_type,
            instruction=instruction,
            parsed_intent=json.dumps(intent),
            status=TaskStatus.IN_PROGRESS,
            started_at=start_time
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)

        try:
            # Build context
            context = await self.build_context(
                property_id=property_id,
                contact_id=contact_id,
                purpose=intent.get("purpose") or instruction
            )
            task.context_snapshot = json.dumps(context)

            # Check for blocking preferences
            if task_type == TaskType.CALL and context.get("preferences", {}).get("do_not_call"):
                task.status = TaskStatus.FAILED
                task.status_message = "Contact has requested no phone calls"
                task.last_error = "do_not_call preference is set"
                await self.db.commit()
                return task

            if task_type == TaskType.SMS and context.get("preferences", {}).get("do_not_text"):
                task.status = TaskStatus.FAILED
                task.status_message = "Contact has requested no text messages"
                task.last_error = "do_not_text preference is set"
                await self.db.commit()
                return task

            if not auto_execute:
                # Return task without executing (for preview/confirmation)
                task.status = TaskStatus.PENDING
                task.status_message = "Ready for execution"
                await self.db.commit()
                return task

            # Execute based on task type
            if task_type == TaskType.CALL:
                result = await self._execute_call(task, context, intent)
            elif task_type == TaskType.SMS:
                result = await self._execute_sms(task, context, intent)
            else:
                result = await self._execute_custom(task, context, intent)

            # Update task with results
            task.result_data = json.dumps(result)
            task.status = TaskStatus.COMPLETED if result.get("success") else TaskStatus.FAILED
            task.status_message = result.get("message")
            task.result_summary = result.get("summary")

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.last_error = str(e)
            task.status_message = f"Execution failed: {str(e)}"

        # Record completion
        task.completed_at = datetime.utcnow()
        task.execution_time_ms = int((task.completed_at - start_time).total_seconds() * 1000)
        await self.db.commit()
        await self.db.refresh(task)

        return task

    async def _execute_call(
        self,
        task: AgentTask,
        context: Dict[str, Any],
        intent: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a phone call with auto-context injection."""
        # Get phone number
        phone_number = None
        if context.get("contact", {}).get("phone"):
            phone_number = context["contact"]["phone"]
        elif intent.get("target"):
            # Assume target is a phone number
            phone_number = intent["target"]

        if not phone_number:
            return {"success": False, "message": "No phone number available"}

        # Build context prompt for the AI caller
        context_prompt = self.format_context_for_prompt(context)
        purpose = intent.get("purpose") or task.instruction

        # Build Vapi call
        try:
            vapi_service = VapiService()
            vapi_context = {
                "property_id": task.property_id,
                "property_name": context.get("property", {}).get("name"),
                "property_address": context.get("property", {}).get("address"),
                "contact_name": context.get("contact", {}).get("name"),
                "contact_type": context.get("contact", {}).get("type"),
                "memory_context": context_prompt,
                "additional_context": intent.get("additional_context"),
            }

            result = await vapi_service.create_call(
                phone_number=phone_number,
                purpose=purpose,
                context=vapi_context
            )

            vapi_call_id = result.get("id")
            if not vapi_call_id:
                return {"success": False, "message": "Failed to initiate call"}

            # Create call record
            call = PropertyPhoneCall(
                property_id=task.property_id,
                contact_id=task.contact_id,
                initiated_by_id=task.initiated_by_id,
                vapi_call_id=vapi_call_id,
                phone_number=phone_number,
                purpose=purpose,
                status=CallStatus.QUEUED,
                call_context=context_prompt
            )
            self.db.add(call)
            await self.db.commit()
            await self.db.refresh(call)

            # Update task with call reference
            task.call_id = call.id

            return {
                "success": True,
                "message": f"Call initiated to {phone_number}",
                "call_id": call.id,
                "vapi_call_id": vapi_call_id,
                "summary": f"Initiated call to {context.get('contact', {}).get('name', phone_number)} regarding: {purpose}"
            }

        except Exception as e:
            return {"success": False, "message": f"Call failed: {str(e)}"}

    async def _execute_sms(
        self,
        task: AgentTask,
        context: Dict[str, Any],
        intent: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute SMS with auto-context (for AI-generated messages)."""
        # Get phone number
        phone_number = None
        if context.get("contact", {}).get("phone"):
            phone_number = context["contact"]["phone"]
        elif intent.get("target"):
            phone_number = intent["target"]

        if not phone_number:
            return {"success": False, "message": "No phone number available"}

        # Generate message if not provided
        message = intent.get("additional_context")
        if not message:
            # Use AI to generate an appropriate message
            message = await self._generate_sms_message(context, intent)

        try:
            twilio_service = get_twilio_service()
            result = await twilio_service.send_sms(
                to_number=phone_number,
                message=message
            )

            # Create SMS record
            sms = PropertySMS(
                property_id=task.property_id,
                contact_id=task.contact_id,
                sent_by_id=task.initiated_by_id,
                twilio_message_sid=result["message_sid"],
                phone_number=phone_number,
                from_number=result["from"],
                to_number=result["to"],
                body=message,
                direction=SMSDirection.OUTBOUND,
                status=SMSStatus.SENT,
                sent_at=datetime.utcnow()
            )
            self.db.add(sms)
            await self.db.commit()
            await self.db.refresh(sms)

            # Update task
            task.sms_id = sms.id

            return {
                "success": True,
                "message": f"SMS sent to {phone_number}",
                "sms_id": sms.id,
                "summary": f"Sent SMS to {context.get('contact', {}).get('name', phone_number)}: {message[:100]}..."
            }

        except Exception as e:
            return {"success": False, "message": f"SMS failed: {str(e)}"}

    async def _generate_sms_message(
        self,
        context: Dict[str, Any],
        intent: Dict[str, Any]
    ) -> str:
        """Generate an SMS message using AI based on context."""
        context_prompt = self.format_context_for_prompt(context)
        purpose = intent.get("purpose", "general communication")

        prompt = f"""Generate a brief, professional SMS message.

Context:
{context_prompt}

Purpose: {purpose}

Requirements:
- Keep it under 160 characters if possible
- Be friendly but professional
- Reference relevant context if appropriate
- Include a clear call-to-action if needed

Generate only the message text, no quotes or explanation."""

        response = await self.anthropic_client.messages.create(
            model=settings.AI_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )

        return response.content[0].text.strip()

    async def _execute_custom(
        self,
        task: AgentTask,
        context: Dict[str, Any],
        intent: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a custom/research task."""
        # For custom tasks, we just return the context and let the user decide
        return {
            "success": True,
            "message": "Task analyzed",
            "context": context,
            "intent": intent,
            "summary": f"Analyzed request: {intent.get('purpose', task.instruction)}"
        }

    # ============ Post-Execution Processing ============

    async def process_call_completion(
        self,
        call_id: int,
        transcript: str,
        summary: Optional[str] = None
    ) -> None:
        """
        Process a completed call - extract memories and update records.

        Called by webhook when Vapi call ends.
        """
        # Get the call
        result = await self.db.execute(
            select(PropertyPhoneCall).where(PropertyPhoneCall.id == call_id)
        )
        call = result.scalar_one_or_none()
        if not call:
            return

        # Extract memories from transcript
        if self.extraction_service.is_available() and transcript:
            extraction_request = MemoryExtractionRequest(
                source_type=MemorySourceType.PHONE_CALL,
                source_id=call_id,
                text=transcript,
                property_id=call.property_id,
                contact_id=call.contact_id
            )

            # Build context strings
            property_context = None
            if call.property_id:
                prop_result = await self.db.execute(
                    select(Property).where(Property.id == call.property_id)
                )
                prop = prop_result.scalar_one_or_none()
                if prop:
                    property_context = f"{prop.name} - {prop.address or 'No address'}"

            contact_context = None
            if call.contact_id:
                contact_result = await self.db.execute(
                    select(PropertyContact).where(PropertyContact.id == call.contact_id)
                )
                contact = contact_result.scalar_one_or_none()
                if contact:
                    contact_context = f"{contact.name} ({contact.contact_type.value if contact.contact_type else 'contact'})"

            await self.extraction_service.process_and_store(
                extraction_request,
                user_id=call.initiated_by_id,
                property_context=property_context,
                contact_context=contact_context,
                conversation_at=call.started_at or call.created_at
            )

    async def process_sms_received(
        self,
        sms_id: int
    ) -> None:
        """
        Process an inbound SMS - extract memories and update records.

        Called by webhook when a new SMS is received.
        """
        # Get the SMS
        result = await self.db.execute(
            select(PropertySMS).where(PropertySMS.id == sms_id)
        )
        sms = result.scalar_one_or_none()
        if not sms or not sms.body:
            return

        # Extract memories from SMS content
        if self.extraction_service.is_available():
            extraction_request = MemoryExtractionRequest(
                source_type=MemorySourceType.SMS,
                source_id=sms_id,
                text=sms.body,
                property_id=sms.property_id,
                contact_id=sms.contact_id
            )

            # Build context strings
            property_context = None
            if sms.property_id:
                prop_result = await self.db.execute(
                    select(Property).where(Property.id == sms.property_id)
                )
                prop = prop_result.scalar_one_or_none()
                if prop:
                    property_context = f"{prop.name} - {prop.address or 'No address'}"

            contact_context = None
            if sms.contact_id:
                contact_result = await self.db.execute(
                    select(PropertyContact).where(PropertyContact.id == sms.contact_id)
                )
                contact = contact_result.scalar_one_or_none()
                if contact:
                    contact_context = f"{contact.name} ({contact.contact_type.value if contact.contact_type else 'contact'})"

            await self.extraction_service.process_and_store(
                extraction_request,
                user_id=sms.sent_by_id,
                property_context=property_context,
                contact_context=contact_context,
                conversation_at=sms.sent_at or sms.created_at
            )


def get_agent_gateway(db: AsyncSession) -> AgentGatewayService:
    """Get agent gateway service instance."""
    return AgentGatewayService(db)

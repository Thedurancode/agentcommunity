"""
Memory extraction service using Claude.

Extracts structured memories, facts, commitments, and preferences
from conversation transcripts.
"""
import json
from typing import Optional, List
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.agent_memory import MemoryType, MemorySourceType
from app.schemas.memory import (
    MemoryCreate, MemoryExtractionRequest, MemoryExtractionResult, ExtractedMemory,
    ConversationSummaryCreate
)
from app.services.memory import MemoryService, get_memory_service


EXTRACTION_SYSTEM_PROMPT = """You are an AI assistant that extracts structured information from conversation transcripts.

Your task is to analyze the conversation and extract:
1. FACTS: Concrete facts learned about the contact or property
   Examples: "John prefers morning calls", "Property has 3 bedrooms", "Wife's name is Sarah"

2. PREFERENCES: Communication or scheduling preferences
   Examples: "Prefers text over calls", "Available only on weekdays", "Speaks Spanish"

3. COMMITMENTS: Things someone committed to doing
   Examples: "Will send inspection report by Friday", "Promised to call back next week"

4. CONTEXT: Important context for future interactions
   Examples: "Currently dealing with tenant issues", "Planning to sell in 6 months"

For each extracted memory, provide:
- content: The memory in a clear, concise sentence
- memory_type: One of "fact", "preference", "commitment", "context"
- confidence: 0.0-1.0 how confident you are this is accurate
- importance: 0.0-1.0 how important this is for future interactions

Also provide:
- summary: A brief summary of the conversation (2-3 sentences)
- key_points: List of main topics discussed
- action_items: List of action items or follow-ups needed
- sentiment: "positive", "negative", or "neutral"
- sentiment_score: -1.0 to 1.0 (negative to positive)

Respond in JSON format only."""


EXTRACTION_USER_TEMPLATE = """Analyze this {source_type} transcript and extract all relevant memories.

Context:
- Property: {property_context}
- Contact: {contact_context}

Transcript:
{transcript}

Respond with a JSON object containing:
{{
    "memories": [
        {{
            "content": "string",
            "memory_type": "fact|preference|commitment|context",
            "confidence": 0.0-1.0,
            "importance": 0.0-1.0
        }}
    ],
    "summary": "string",
    "key_points": ["string"],
    "action_items": ["string"],
    "sentiment": "positive|negative|neutral",
    "sentiment_score": -1.0 to 1.0
}}"""


class MemoryExtractionService:
    """Service for extracting memories from conversations using Claude."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._anthropic_client = None
        self._memory_service = None

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
    def memory_service(self) -> MemoryService:
        """Get memory service."""
        if self._memory_service is None:
            self._memory_service = get_memory_service(self.db)
        return self._memory_service

    def is_available(self) -> bool:
        """Check if extraction service is available."""
        return bool(settings.ANTHROPIC_API_KEY)

    async def extract_memories(
        self,
        request: MemoryExtractionRequest,
        property_context: Optional[str] = None,
        contact_context: Optional[str] = None
    ) -> MemoryExtractionResult:
        """
        Extract memories from a conversation transcript.

        Uses Claude to analyze the text and extract structured memories.
        """
        if not self.is_available():
            raise ValueError("Memory extraction service not available (Anthropic not configured)")

        # Format source type for prompt
        source_type_map = {
            MemorySourceType.PHONE_CALL: "phone call",
            MemorySourceType.SMS: "SMS conversation",
            MemorySourceType.NOTE: "note",
            MemorySourceType.USER_INPUT: "user input",
            MemorySourceType.SYSTEM: "system event",
        }
        source_type_str = source_type_map.get(request.source_type, "conversation")

        # Build the prompt
        user_message = EXTRACTION_USER_TEMPLATE.format(
            source_type=source_type_str,
            property_context=property_context or "Not specified",
            contact_context=contact_context or "Not specified",
            transcript=request.text
        )

        # Call Claude
        response = await self.anthropic_client.messages.create(
            model=settings.AI_MODEL,
            max_tokens=2000,
            system=EXTRACTION_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        # Parse response
        response_text = response.content[0].text

        # Try to extract JSON from response
        try:
            # Handle markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            data = json.loads(response_text.strip())
        except json.JSONDecodeError:
            # Return empty result if parsing fails
            return MemoryExtractionResult(
                memories=[],
                summary=None,
                key_points=None,
                action_items=None,
                sentiment=None,
                sentiment_score=None
            )

        # Map memory types
        memory_type_map = {
            "fact": MemoryType.FACT,
            "preference": MemoryType.PREFERENCE,
            "commitment": MemoryType.COMMITMENT,
            "context": MemoryType.CONTEXT,
            "summary": MemoryType.SUMMARY,
            "relationship": MemoryType.RELATIONSHIP,
        }

        # Build result
        memories = []
        for mem_data in data.get("memories", []):
            mem_type_str = mem_data.get("memory_type", "fact").lower()
            mem_type = memory_type_map.get(mem_type_str, MemoryType.FACT)

            memories.append(ExtractedMemory(
                content=mem_data.get("content", ""),
                memory_type=mem_type,
                confidence=float(mem_data.get("confidence", 0.8)),
                importance=float(mem_data.get("importance", 0.5))
            ))

        return MemoryExtractionResult(
            memories=memories,
            summary=data.get("summary"),
            key_points=data.get("key_points"),
            action_items=data.get("action_items"),
            sentiment=data.get("sentiment"),
            sentiment_score=data.get("sentiment_score")
        )

    async def process_and_store(
        self,
        request: MemoryExtractionRequest,
        user_id: Optional[int] = None,
        property_context: Optional[str] = None,
        contact_context: Optional[str] = None,
        conversation_at: Optional[datetime] = None
    ) -> MemoryExtractionResult:
        """
        Extract memories and store them in the database.

        Also creates a conversation summary.
        """
        # Extract memories
        result = await self.extract_memories(
            request,
            property_context=property_context,
            contact_context=contact_context
        )

        # Store each memory
        for extracted in result.memories:
            memory_create = MemoryCreate(
                content=extracted.content,
                memory_type=extracted.memory_type,
                confidence=extracted.confidence,
                importance=extracted.importance,
                property_id=request.property_id,
                contact_id=request.contact_id,
                source_type=request.source_type,
                source_id=request.source_id,
            )
            await self.memory_service.create_memory(memory_create, user_id=user_id)

        # Create conversation summary if we have a property
        if request.property_id and result.summary:
            summary_create = ConversationSummaryCreate(
                property_id=request.property_id,
                contact_id=request.contact_id,
                conversation_type=request.source_type.value,
                source_id=request.source_id,
                summary=result.summary,
                key_points=result.key_points,
                action_items=result.action_items,
                sentiment=result.sentiment,
                sentiment_score=result.sentiment_score,
                conversation_at=conversation_at or datetime.utcnow(),
                follow_up_required=bool(result.action_items),
            )
            await self.memory_service.create_conversation_summary(summary_create)

        return result


def get_extraction_service(db: AsyncSession) -> MemoryExtractionService:
    """Get memory extraction service instance."""
    return MemoryExtractionService(db)

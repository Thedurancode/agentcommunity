from typing import Optional, List, Dict, Any

import httpx

from app.core.config import settings


class VapiService:
    """Service for interacting with Vapi API for AI-powered phone calls."""

    def __init__(self):
        self.api_key = settings.VAPI_API_KEY
        self.base_url = settings.VAPI_API_URL
        self.phone_number_id = settings.VAPI_PHONE_NUMBER_ID
        self.default_assistant_id = settings.VAPI_ASSISTANT_ID
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make an async request to Vapi API."""
        if not self.api_key:
            raise ValueError("VAPI_API_KEY is not configured")

        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                f"{self.base_url}{endpoint}",
                headers=self.headers,
                params=params,
                json=json,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def create_call(
        self,
        phone_number: str,
        purpose: str,
        context: Dict[str, Any],
        assistant_id: Optional[str] = None,
        first_message: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create an outbound phone call with context.

        Args:
            phone_number: The phone number to call (E.164 format, e.g., +1234567890)
            purpose: Brief description of why we're calling
            context: Property and contact information to provide to the AI
            assistant_id: Vapi assistant ID (uses default if not provided)
            first_message: Custom first message for the AI to say
            system_prompt: Custom system prompt to override assistant's default

        Returns:
            Call data including call_id and status
        """
        if not self.phone_number_id:
            raise ValueError("VAPI_PHONE_NUMBER_ID is not configured")

        # Build the payload
        payload: Dict[str, Any] = {
            "phoneNumberId": self.phone_number_id,
            "customer": {
                "number": phone_number,
            },
        }

        # Use provided assistant_id or default
        aid = assistant_id or self.default_assistant_id

        if aid:
            # Use existing assistant with optional overrides
            payload["assistantId"] = aid
            if system_prompt or first_message:
                payload["assistantOverrides"] = {}
                if first_message:
                    payload["assistantOverrides"]["firstMessage"] = first_message
                if system_prompt:
                    payload["assistantOverrides"]["model"] = {
                        "messages": [{"role": "system", "content": system_prompt}]
                    }
        else:
            # Create a transient assistant for this call
            payload["assistant"] = self._build_transient_assistant(
                purpose=purpose,
                context=context,
                first_message=first_message,
                system_prompt=system_prompt,
            )

        # Add metadata for tracking
        payload["metadata"] = {
            "purpose": purpose,
            "property_id": context.get("property_id"),
            "contact_id": context.get("contact_id"),
        }

        return await self._request("POST", "/call/phone", json=payload)

    def _build_transient_assistant(
        self,
        purpose: str,
        context: Dict[str, Any],
        first_message: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a transient assistant configuration for a call."""
        # Build context string from property info
        context_parts = []

        if context.get("property_name"):
            context_parts.append(f"Property: {context['property_name']}")
        if context.get("property_address"):
            context_parts.append(f"Address: {context['property_address']}")
        if context.get("property_type"):
            context_parts.append(f"Type: {context['property_type']}")
        if context.get("property_status"):
            context_parts.append(f"Status: {context['property_status']}")
        if context.get("contact_name"):
            context_parts.append(f"Speaking with: {context['contact_name']}")
        if context.get("contact_type"):
            context_parts.append(f"Contact role: {context['contact_type']}")
        if context.get("additional_context"):
            context_parts.append(f"Notes: {context['additional_context']}")

        context_string = "\n".join(context_parts)

        # Default system prompt if not provided
        default_system_prompt = f"""You are a professional assistant making a phone call regarding a property.

PURPOSE OF THIS CALL: {purpose}

PROPERTY CONTEXT:
{context_string}

GUIDELINES:
- Be professional, friendly, and concise
- Introduce yourself and state the purpose of the call clearly
- Reference the property details when relevant
- Listen carefully and respond appropriately
- Take note of any important information shared
- If asked questions you cannot answer, offer to have someone follow up
- End the call politely and summarize any action items
"""

        return {
            "model": {
                "provider": "openai",
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": system_prompt or default_system_prompt}
                ],
            },
            "voice": {
                "provider": "11labs",
                "voiceId": "21m00Tcm4TlvDq8ikWAM",  # Rachel - professional female voice
            },
            "firstMessage": first_message or f"Hello, this is calling regarding {context.get('property_name', 'your property')}. {purpose}. Is this a good time to talk?",
            "endCallMessage": "Thank you for your time. Have a great day!",
            "transcriber": {
                "provider": "deepgram",
                "model": "nova-2",
                "language": "en",
            },
        }

    async def get_call(self, call_id: str) -> Dict[str, Any]:
        """Get call details and status."""
        return await self._request("GET", f"/call/{call_id}")

    async def list_calls(
        self,
        limit: int = 100,
        created_at_gt: Optional[str] = None,
        created_at_lt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List calls with optional filters."""
        params = {"limit": limit}
        if created_at_gt:
            params["createdAtGt"] = created_at_gt
        if created_at_lt:
            params["createdAtLt"] = created_at_lt

        result = await self._request("GET", "/call", params=params)
        return result if isinstance(result, list) else result.get("data", [])

    async def end_call(self, call_id: str) -> Dict[str, Any]:
        """End an active call."""
        return await self._request("DELETE", f"/call/{call_id}")

    async def list_phone_numbers(self) -> List[Dict[str, Any]]:
        """List available phone numbers."""
        result = await self._request("GET", "/phone-number")
        return result if isinstance(result, list) else result.get("data", [])

    async def list_assistants(self) -> List[Dict[str, Any]]:
        """List available assistants."""
        result = await self._request("GET", "/assistant")
        return result if isinstance(result, list) else result.get("data", [])


# Call status mapping
VAPI_CALL_STATUS_MAP = {
    "queued": "queued",
    "ringing": "ringing",
    "in-progress": "in_progress",
    "forwarding": "forwarding",
    "ended": "ended",
    "busy": "failed",
    "failed": "failed",
    "no-answer": "no_answer",
}


def map_vapi_call_status(vapi_status: str) -> str:
    """Map Vapi call status to our status."""
    return VAPI_CALL_STATUS_MAP.get(vapi_status.lower(), vapi_status.lower())

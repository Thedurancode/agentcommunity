from typing import Optional, List, Dict, Any

import httpx

from app.core.config import settings


class DocuSealService:
    """Service for interacting with DocuSeal API for e-signatures."""

    def __init__(self):
        self.api_key = settings.DOCUSEAL_API_KEY
        self.base_url = settings.DOCUSEAL_API_URL
        self.headers = {
            "X-Auth-Token": self.api_key,
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make an async request to DocuSeal API."""
        if not self.api_key:
            raise ValueError("DOCUSEAL_API_KEY is not configured")

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

    async def list_templates(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List available DocuSeal templates."""
        result = await self._request("GET", "/templates", params={"limit": limit})
        return result.get("data", result) if isinstance(result, dict) else result

    async def get_template(self, template_id: int) -> Dict[str, Any]:
        """Get a specific template by ID."""
        return await self._request("GET", f"/templates/{template_id}")

    async def create_submission(
        self,
        template_id: int,
        signers: List[Dict[str, Any]],
        send_email: bool = True,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new submission for signing.

        Args:
            template_id: The DocuSeal template ID
            signers: List of signer dicts with 'email' and optionally 'name', 'role'
            send_email: Whether to send email to signers
            message: Optional custom message for signers

        Returns:
            Submission data including submission_id and signing URLs
        """
        payload = {
            "template_id": template_id,
            "send_email": send_email,
            "submitters": signers,
        }
        if message:
            payload["message"] = message

        return await self._request("POST", "/submissions", json=payload)

    async def get_submission(self, submission_id: int) -> Dict[str, Any]:
        """Get submission status and details."""
        return await self._request("GET", f"/submissions/{submission_id}")

    async def get_submission_documents(self, submission_id: int) -> List[Dict[str, Any]]:
        """Get documents for a completed submission."""
        result = await self._request("GET", f"/submissions/{submission_id}/documents")
        return result.get("data", result) if isinstance(result, dict) else result

    async def void_submission(self, submission_id: int) -> Dict[str, Any]:
        """Void/cancel a pending submission."""
        return await self._request("DELETE", f"/submissions/{submission_id}")


# Status mapping from DocuSeal to our contract status
DOCUSEAL_STATUS_MAP = {
    "pending": "pending",
    "awaiting": "pending",
    "sent": "pending",
    "opened": "pending",
    "completed": "active",
    "signed": "active",
    "expired": "expired",
    "declined": "cancelled",
    "voided": "cancelled",
}


def map_docuseal_status_to_contract_status(docuseal_status: str) -> str:
    """Map DocuSeal submission status to our contract status."""
    return DOCUSEAL_STATUS_MAP.get(docuseal_status.lower(), "pending")

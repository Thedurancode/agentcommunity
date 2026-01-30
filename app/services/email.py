"""
Email Service using Resend.

Provides email functionality for sending reports, notifications, and communications.
"""
import base64
from typing import Optional, List, Dict, Any
import httpx

from app.core.config import settings


class EmailService:
    """Service for sending emails via Resend."""

    def __init__(self):
        self.api_key = settings.RESEND_API_KEY
        self.api_url = "https://api.resend.com"
        self.from_email = settings.RESEND_FROM_EMAIL or "reports@resend.dev"

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for Resend API requests."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def send_email(
        self,
        to: str | List[str],
        subject: str,
        html: Optional[str] = None,
        text: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        reply_to: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Send an email via Resend.

        Args:
            to: Recipient email(s)
            subject: Email subject
            html: HTML content
            text: Plain text content
            attachments: List of attachments with 'filename', 'content' (base64), and 'content_type'
            reply_to: Reply-to email address
            cc: CC recipients
            bcc: BCC recipients

        Returns:
            Resend API response with email ID
        """
        if not self.api_key:
            raise ValueError("RESEND_API_KEY not configured")

        # Ensure to is a list
        if isinstance(to, str):
            to = [to]

        payload = {
            "from": self.from_email,
            "to": to,
            "subject": subject
        }

        if html:
            payload["html"] = html
        if text:
            payload["text"] = text
        if attachments:
            payload["attachments"] = attachments
        if reply_to:
            payload["reply_to"] = reply_to
        if cc:
            payload["cc"] = cc
        if bcc:
            payload["bcc"] = bcc

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/emails",
                headers=self._get_headers(),
                json=payload,
                timeout=30.0
            )

            if response.status_code >= 400:
                return {
                    "success": False,
                    "error": response.text,
                    "status_code": response.status_code
                }

            result = response.json()
            return {
                "success": True,
                "email_id": result.get("id"),
                "data": result
            }

    async def send_pdf_report(
        self,
        to: str | List[str],
        subject: str,
        pdf_bytes: bytes,
        filename: str,
        body_html: Optional[str] = None,
        body_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a PDF report via email.

        Args:
            to: Recipient email(s)
            subject: Email subject
            pdf_bytes: PDF file content as bytes
            filename: Filename for the attachment
            body_html: Optional HTML body
            body_text: Optional plain text body

        Returns:
            Resend API response
        """
        # Encode PDF as base64
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

        # Create attachment
        attachments = [
            {
                "filename": filename,
                "content": pdf_base64,
                "content_type": "application/pdf"
            }
        ]

        # Default body if not provided
        if not body_html and not body_text:
            body_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2>Your Property Report is Ready</h2>
                <p>Please find your property intelligence report attached to this email.</p>
                <p>The report includes:</p>
                <ul>
                    <li>Property Overview & Valuation</li>
                    <li>Ownership History</li>
                    <li>Tax Information</li>
                    <li>Risk Assessment</li>
                    <li>Comparable Sales</li>
                    <li>Neighborhood Intelligence</li>
                </ul>
                <p>If you have any questions, please don't hesitate to reach out.</p>
                <br>
                <p style="color: #666;">This report was generated automatically by Property Intelligence.</p>
            </body>
            </html>
            """

        return await self.send_email(
            to=to,
            subject=subject,
            html=body_html,
            text=body_text,
            attachments=attachments
        )

    async def send_property_report_email(
        self,
        to: str | List[str],
        property_address: str,
        pdf_bytes: bytes,
        brand_name: str = "Property Intelligence",
        custom_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a property report email with custom branding.

        Args:
            to: Recipient email(s)
            property_address: Property address for subject line
            pdf_bytes: PDF report bytes
            brand_name: Brand name for email
            custom_message: Optional custom message to include

        Returns:
            Resend API response
        """
        subject = f"Property Report: {property_address}"

        custom_section = ""
        if custom_message:
            custom_section = f"""
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 8px; margin: 20px 0;">
                <p style="margin: 0;"><strong>Note:</strong> {custom_message}</p>
            </div>
            """

        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="border-bottom: 3px solid #1a365d; padding-bottom: 15px; margin-bottom: 20px;">
                <h1 style="color: #1a365d; margin: 0; font-size: 24px;">{brand_name}</h1>
            </div>

            <h2 style="color: #333;">Your Property Report is Ready</h2>

            <p style="color: #555; font-size: 16px;">
                We've completed the due diligence research for:
            </p>

            <div style="background-color: #f0f7ff; padding: 15px; border-radius: 8px; border-left: 4px solid #1a365d; margin: 20px 0;">
                <p style="margin: 0; font-size: 18px; font-weight: bold; color: #1a365d;">
                    {property_address}
                </p>
            </div>

            {custom_section}

            <p style="color: #555;">Your comprehensive property intelligence report is attached. It includes:</p>

            <ul style="color: #555;">
                <li><strong>Executive Summary</strong> - Quick overview and value estimate</li>
                <li><strong>Risk Scorecard</strong> - Title, tax, permit, and market risks</li>
                <li><strong>Ownership Timeline</strong> - 30-year transfer history</li>
                <li><strong>Tax History</strong> - Assessment and payment records</li>
                <li><strong>Zoning & Permits</strong> - Land use and permit history</li>
                <li><strong>Comparable Sales</strong> - Recent sales in the area</li>
                <li><strong>Neighborhood Intelligence</strong> - Schools, transit, environment</li>
                <li><strong>Next Steps</strong> - Questions to ask and documents to request</li>
            </ul>

            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd;">
                <p style="color: #888; font-size: 12px;">
                    This report was generated by {brand_name}. The information provided is for
                    informational purposes only and should be verified independently.
                </p>
            </div>
        </body>
        </html>
        """

        # Create filename
        safe_address = "".join(c if c.isalnum() or c in " -_" else "" for c in property_address)
        filename = f"Property_Report_{safe_address[:50]}.pdf"

        return await self.send_pdf_report(
            to=to,
            subject=subject,
            pdf_bytes=pdf_bytes,
            filename=filename,
            body_html=body_html
        )


def get_email_service() -> EmailService:
    """Get email service instance."""
    return EmailService()

"""
Sentiment Analysis Service

Uses Claude API to analyze sentiment and emotions in text.
"""
from typing import Optional
from pydantic import BaseModel

from anthropic import AsyncAnthropic

from app.core.config import settings


class SentimentResult(BaseModel):
    """Result of sentiment analysis."""
    sentiment: str  # positive, negative, neutral, mixed
    confidence: float  # 0.0 to 1.0
    emotions: list[str]  # joy, sadness, anger, fear, surprise, disgust, etc.
    tone: str  # formal, casual, urgent, calm, etc.
    summary: str  # Brief summary of the emotional content


class SentimentService:
    def __init__(self):
        if not settings.ANTHROPIC_API_KEY:
            self.client = None
        else:
            self.client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    def is_available(self) -> bool:
        return self.client is not None

    async def analyze_sentiment(
        self,
        text: str,
        context: Optional[str] = None,
    ) -> SentimentResult:
        """
        Analyze sentiment and emotions in text.

        Args:
            text: Text to analyze
            context: Optional context about the text (e.g., "customer support call")

        Returns:
            SentimentResult with sentiment, emotions, tone, and summary
        """
        if not self.client:
            raise ValueError("Sentiment service not configured. Set ANTHROPIC_API_KEY.")

        context_str = f"\nContext: {context}" if context else ""

        prompt = f"""Analyze the sentiment and emotions in the following text.{context_str}

Text to analyze:
\"\"\"
{text}
\"\"\"

Respond with a JSON object containing:
- "sentiment": one of "positive", "negative", "neutral", or "mixed"
- "confidence": a float between 0.0 and 1.0 indicating confidence in the sentiment classification
- "emotions": an array of detected emotions (e.g., "joy", "sadness", "anger", "fear", "surprise", "frustration", "excitement", "calm")
- "tone": the overall tone (e.g., "formal", "casual", "urgent", "calm", "professional", "friendly")
- "summary": a one-sentence summary of the emotional content

Respond with only the JSON object, no other text."""

        response = await self.client.messages.create(
            model="claude-3-haiku-20240307",  # Fast and cost-effective for sentiment
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        import json
        result_text = response.content[0].text.strip()

        # Handle potential markdown code blocks
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            result_text = "\n".join(lines[1:-1])

        result = json.loads(result_text)

        return SentimentResult(
            sentiment=result.get("sentiment", "neutral"),
            confidence=result.get("confidence", 0.5),
            emotions=result.get("emotions", []),
            tone=result.get("tone", "neutral"),
            summary=result.get("summary", ""),
        )


# Singleton instance
sentiment_service = SentimentService()


def get_sentiment_service() -> SentimentService:
    return sentiment_service

"""
Sentiment Analysis Routes

Standalone sentiment analysis endpoints for AI voice agents.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.models.user import User
from app.services.sentiment import get_sentiment_service
from app.schemas.voice_note import SentimentResponse


router = APIRouter(prefix="/sentiment", tags=["sentiment"])


class SentimentAnalysisRequest(BaseModel):
    """Request to analyze sentiment."""
    text: str
    context: Optional[str] = None  # e.g., "customer support call", "sales conversation"


class BatchSentimentRequest(BaseModel):
    """Request to analyze sentiment for multiple texts."""
    texts: list[str]
    context: Optional[str] = None


class BatchSentimentResponse(BaseModel):
    """Response for batch sentiment analysis."""
    results: list[SentimentResponse]


@router.post("/analyze", response_model=SentimentResponse)
async def analyze_sentiment(
    request: SentimentAnalysisRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Analyze sentiment for a piece of text.

    This endpoint is optimized for AI voice agent use cases:
    - Fast response time using Claude Haiku
    - Provides sentiment, emotions, tone, and summary
    - Optional context parameter for better analysis

    Example:
        POST /api/v1/sentiment/analyze
        {
            "text": "I'm really frustrated with this issue. It's been going on for days!",
            "context": "customer support call"
        }

    Response:
        {
            "sentiment": "negative",
            "confidence": 0.92,
            "emotions": ["frustration", "anger"],
            "tone": "urgent",
            "summary": "Customer expressing frustration about an ongoing issue"
        }
    """
    if not request.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text cannot be empty",
        )

    sentiment_service = get_sentiment_service()
    if not sentiment_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sentiment analysis service not configured. Set ANTHROPIC_API_KEY.",
        )

    result = await sentiment_service.analyze_sentiment(
        request.text,
        context=request.context,
    )

    return SentimentResponse(
        sentiment=result.sentiment,
        confidence=result.confidence,
        emotions=result.emotions,
        tone=result.tone,
        summary=result.summary,
    )


@router.post("/analyze-batch", response_model=BatchSentimentResponse)
async def analyze_sentiment_batch(
    request: BatchSentimentRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Analyze sentiment for multiple texts in a single request.

    Useful for analyzing conversation history or multiple utterances.
    Maximum 10 texts per request.
    """
    if not request.texts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Texts list cannot be empty",
        )

    if len(request.texts) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 10 texts per batch request",
        )

    sentiment_service = get_sentiment_service()
    if not sentiment_service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sentiment analysis service not configured. Set ANTHROPIC_API_KEY.",
        )

    results = []
    for text in request.texts:
        if text.strip():
            result = await sentiment_service.analyze_sentiment(
                text,
                context=request.context,
            )
            results.append(SentimentResponse(
                sentiment=result.sentiment,
                confidence=result.confidence,
                emotions=result.emotions,
                tone=result.tone,
                summary=result.summary,
            ))
        else:
            results.append(SentimentResponse(
                sentiment="neutral",
                confidence=0.0,
                emotions=[],
                tone="neutral",
                summary="Empty text",
            ))

    return BatchSentimentResponse(results=results)


@router.get("/info")
async def sentiment_info():
    """Get information about the sentiment analysis service."""
    sentiment_service = get_sentiment_service()

    return {
        "available": sentiment_service.is_available(),
        "model": "claude-3-haiku-20240307",
        "supported_sentiments": ["positive", "negative", "neutral", "mixed"],
        "supported_emotions": [
            "joy", "sadness", "anger", "fear", "surprise",
            "frustration", "excitement", "calm", "confusion", "satisfaction"
        ],
        "supported_tones": [
            "formal", "casual", "urgent", "calm",
            "professional", "friendly", "neutral"
        ],
        "endpoints": {
            "analyze": "POST /api/v1/sentiment/analyze - Analyze single text",
            "analyze_batch": "POST /api/v1/sentiment/analyze-batch - Analyze multiple texts",
        },
    }

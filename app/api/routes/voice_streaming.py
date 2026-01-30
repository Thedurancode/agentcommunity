"""
WebSocket Voice Streaming Routes

Real-time voice streaming for AI voice agents.
Supports:
- Audio streaming from client to server
- Real-time transcription
- Sentiment analysis on transcripts
- Streaming responses back to client
"""
import json
import base64
import asyncio
from datetime import datetime
from typing import Optional
from enum import Enum

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.api_key import APIKey
from app.core.security import verify_api_key
from app.services.transcription import get_transcription_service
from app.services.sentiment import get_sentiment_service


router = APIRouter(prefix="/voice-stream", tags=["voice-streaming"])


class StreamEventType(str, Enum):
    """Types of events in the voice stream."""
    # Client -> Server
    AUDIO_CHUNK = "audio_chunk"
    END_OF_SPEECH = "end_of_speech"
    CONFIG = "config"

    # Server -> Client
    TRANSCRIPTION = "transcription"
    TRANSCRIPTION_PARTIAL = "transcription_partial"
    SENTIMENT = "sentiment"
    ERROR = "error"
    READY = "ready"
    PROCESSING = "processing"


class ConnectionManager:
    """Manages WebSocket connections for voice streaming."""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self.connection_configs: dict[str, dict] = {}

    async def connect(self, websocket: WebSocket, connection_id: str):
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        self.connection_configs[connection_id] = {
            "language": None,
            "enable_sentiment": True,
            "audio_format": "wav",
        }

    def disconnect(self, connection_id: str):
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        if connection_id in self.connection_configs:
            del self.connection_configs[connection_id]

    def get_config(self, connection_id: str) -> dict:
        return self.connection_configs.get(connection_id, {})

    def update_config(self, connection_id: str, config: dict):
        if connection_id in self.connection_configs:
            self.connection_configs[connection_id].update(config)

    async def send_event(self, connection_id: str, event_type: StreamEventType, data: dict):
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            await websocket.send_json({
                "type": event_type.value,
                "data": data,
                "timestamp": datetime.utcnow().isoformat(),
            })


manager = ConnectionManager()


async def authenticate_websocket(
    websocket: WebSocket,
    api_key: Optional[str] = Query(None, alias="api_key"),
    token: Optional[str] = Query(None),
) -> Optional[User]:
    """Authenticate WebSocket connection using API key or JWT token."""
    from app.core.database import async_session_maker

    async with async_session_maker() as db:
        # Try API key first
        if api_key:
            result = await db.execute(
                select(APIKey).where(APIKey.key_prefix == api_key[:12])
            )
            api_key_record = result.scalar_one_or_none()

            if api_key_record and api_key_record.is_active:
                if verify_api_key(api_key, api_key_record.key_hash):
                    # Update last used
                    api_key_record.last_used_at = datetime.utcnow()
                    await db.commit()

                    # Get user
                    result = await db.execute(
                        select(User).where(User.id == api_key_record.user_id)
                    )
                    return result.scalar_one_or_none()

        # Try JWT token
        if token:
            from jose import jwt, JWTError
            from app.core.config import settings

            try:
                payload = jwt.decode(
                    token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
                )
                user_id: str = payload.get("sub")
                if user_id:
                    result = await db.execute(
                        select(User).where(User.id == int(user_id))
                    )
                    return result.scalar_one_or_none()
            except (JWTError, ValueError):
                pass

    return None


@router.websocket("/connect")
async def voice_stream_connect(
    websocket: WebSocket,
    api_key: Optional[str] = Query(None, alias="api_key"),
    token: Optional[str] = Query(None),
):
    """
    WebSocket endpoint for real-time voice streaming.

    Authentication:
        - api_key: API key as query parameter
        - token: JWT token as query parameter

    Client -> Server Events:
        - audio_chunk: Base64 encoded audio data
        - end_of_speech: Signal end of speech segment
        - config: Update stream configuration

    Server -> Client Events:
        - ready: Connection established and ready
        - transcription: Final transcription result
        - transcription_partial: Partial/interim transcription
        - sentiment: Sentiment analysis result
        - processing: Status update
        - error: Error message

    Example client message:
    {
        "type": "audio_chunk",
        "data": {
            "audio": "<base64_encoded_audio>",
            "format": "wav"
        }
    }

    Example config message:
    {
        "type": "config",
        "data": {
            "language": "en",
            "enable_sentiment": true,
            "audio_format": "wav"
        }
    }
    """
    # Authenticate
    user = await authenticate_websocket(websocket, api_key, token)
    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Generate connection ID
    connection_id = f"{user.id}_{datetime.utcnow().timestamp()}"

    # Accept connection
    await manager.connect(websocket, connection_id)

    # Send ready event
    await manager.send_event(connection_id, StreamEventType.READY, {
        "connection_id": connection_id,
        "user_id": user.id,
        "message": "Voice stream connected and ready",
    })

    # Audio buffer for accumulating chunks
    audio_buffer = bytearray()

    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            event_type = data.get("type")
            event_data = data.get("data", {})

            if event_type == StreamEventType.CONFIG.value:
                # Update configuration
                manager.update_config(connection_id, event_data)
                await manager.send_event(connection_id, StreamEventType.READY, {
                    "message": "Configuration updated",
                    "config": manager.get_config(connection_id),
                })

            elif event_type == StreamEventType.AUDIO_CHUNK.value:
                # Accumulate audio data
                audio_b64 = event_data.get("audio", "")
                if audio_b64:
                    try:
                        audio_bytes = base64.b64decode(audio_b64)
                        audio_buffer.extend(audio_bytes)
                    except Exception as e:
                        await manager.send_event(connection_id, StreamEventType.ERROR, {
                            "message": f"Invalid audio data: {str(e)}",
                        })

            elif event_type == StreamEventType.END_OF_SPEECH.value:
                # Process accumulated audio
                if len(audio_buffer) > 0:
                    await manager.send_event(connection_id, StreamEventType.PROCESSING, {
                        "message": "Processing audio...",
                        "audio_size_bytes": len(audio_buffer),
                    })

                    config = manager.get_config(connection_id)

                    try:
                        # Get transcription service
                        transcription_service = get_transcription_service()
                        if not transcription_service.is_available():
                            raise ValueError("Transcription service not available")

                        # Transcribe audio
                        audio_format = config.get("audio_format", "wav")
                        transcript = await transcription_service.transcribe_bytes(
                            bytes(audio_buffer),
                            f"audio.{audio_format}",
                            language=config.get("language"),
                        )

                        # Send transcription result
                        await manager.send_event(connection_id, StreamEventType.TRANSCRIPTION, {
                            "text": transcript,
                            "is_final": True,
                        })

                        # Perform sentiment analysis if enabled
                        if config.get("enable_sentiment", True) and transcript.strip():
                            sentiment_service = get_sentiment_service()
                            if sentiment_service.is_available():
                                sentiment_result = await sentiment_service.analyze_sentiment(
                                    transcript,
                                    context="voice conversation",
                                )

                                await manager.send_event(connection_id, StreamEventType.SENTIMENT, {
                                    "sentiment": sentiment_result.sentiment,
                                    "confidence": sentiment_result.confidence,
                                    "emotions": sentiment_result.emotions,
                                    "tone": sentiment_result.tone,
                                    "summary": sentiment_result.summary,
                                })

                    except Exception as e:
                        await manager.send_event(connection_id, StreamEventType.ERROR, {
                            "message": f"Processing error: {str(e)}",
                        })

                    # Clear buffer
                    audio_buffer.clear()
                else:
                    await manager.send_event(connection_id, StreamEventType.ERROR, {
                        "message": "No audio data to process",
                    })

    except WebSocketDisconnect:
        manager.disconnect(connection_id)
    except Exception as e:
        await manager.send_event(connection_id, StreamEventType.ERROR, {
            "message": f"Connection error: {str(e)}",
        })
        manager.disconnect(connection_id)


@router.get("/info")
async def voice_stream_info():
    """Get information about the voice streaming endpoint."""
    return {
        "endpoint": "/api/v1/voice-stream/connect",
        "protocol": "WebSocket",
        "authentication": {
            "api_key": "Pass as query parameter: ?api_key=YOUR_API_KEY",
            "token": "Pass as query parameter: ?token=YOUR_JWT_TOKEN",
        },
        "supported_formats": ["wav", "mp3", "webm", "ogg", "m4a"],
        "events": {
            "client_to_server": {
                "audio_chunk": "Send base64 encoded audio chunks",
                "end_of_speech": "Signal end of speech segment for processing",
                "config": "Update stream configuration",
            },
            "server_to_client": {
                "ready": "Connection ready",
                "transcription": "Final transcription result",
                "transcription_partial": "Partial transcription (if supported)",
                "sentiment": "Sentiment analysis result",
                "processing": "Processing status",
                "error": "Error message",
            },
        },
        "config_options": {
            "language": "Language code (e.g., 'en', 'es')",
            "enable_sentiment": "Enable sentiment analysis (default: true)",
            "audio_format": "Audio format (default: 'wav')",
        },
        "example_client_message": {
            "type": "audio_chunk",
            "data": {
                "audio": "<base64_encoded_audio>",
                "format": "wav",
            },
        },
    }

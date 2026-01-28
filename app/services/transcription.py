"""
Transcription Service

Uses OpenAI Whisper API to transcribe audio files.
Supports files up to 25MB per OpenAI limits.
For larger files, we split them into chunks.
"""
import os
import tempfile
from typing import Optional
from pathlib import Path

from openai import AsyncOpenAI

from app.core.config import settings


class TranscriptionService:
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            self.client = None
        else:
            self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    def is_available(self) -> bool:
        return self.client is not None

    async def transcribe_file(
        self,
        file_path: str,
        language: Optional[str] = None,
    ) -> str:
        """
        Transcribe an audio file using OpenAI Whisper.

        Args:
            file_path: Path to the audio file
            language: Optional language code (e.g., 'en', 'es')

        Returns:
            Transcribed text
        """
        if not self.client:
            raise ValueError("Transcription service not configured. Set OPENAI_API_KEY.")

        # Check file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        # Check file size (Whisper has 25MB limit)
        file_size = os.path.getsize(file_path)
        max_size = 25 * 1024 * 1024  # 25MB

        if file_size > max_size:
            # For large files, we'd need to split - for now raise error
            raise ValueError(
                f"File too large ({file_size / 1024 / 1024:.1f}MB). "
                f"Max size is 25MB. Consider splitting the audio."
            )

        # Transcribe using Whisper
        with open(file_path, "rb") as audio_file:
            kwargs = {"file": audio_file, "model": "whisper-1"}
            if language:
                kwargs["language"] = language

            transcript = await self.client.audio.transcriptions.create(**kwargs)

        return transcript.text

    async def transcribe_bytes(
        self,
        audio_bytes: bytes,
        filename: str,
        language: Optional[str] = None,
    ) -> str:
        """
        Transcribe audio from bytes.

        Args:
            audio_bytes: Audio file content as bytes
            filename: Original filename (needed for format detection)
            language: Optional language code

        Returns:
            Transcribed text
        """
        if not self.client:
            raise ValueError("Transcription service not configured. Set OPENAI_API_KEY.")

        # Write to temp file (Whisper API needs a file)
        suffix = Path(filename).suffix or ".mp3"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            return await self.transcribe_file(tmp_path, language)
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


# Singleton instance
transcription_service = TranscriptionService()


def get_transcription_service() -> TranscriptionService:
    return transcription_service

import os
import uuid
import aiofiles
from pathlib import Path
from typing import Optional
from fastapi import UploadFile, HTTPException, status


ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/x-icon": ".ico",
}

ALLOWED_VIDEO_TYPES = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/ogg": ".ogv",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    "video/x-matroska": ".mkv",
}

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_VIDEO_SIZE = 500 * 1024 * 1024  # 500MB


class StorageService:
    def __init__(self, upload_dir: str = "uploads"):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def _get_project_dir(self, project_id: int) -> Path:
        """Get or create project-specific upload directory."""
        project_dir = self.upload_dir / f"project_{project_id}"
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir

    def _get_brand_dir(self, project_id: int) -> Path:
        """Get or create brand assets directory for a project."""
        brand_dir = self._get_project_dir(project_id) / "brand"
        brand_dir.mkdir(parents=True, exist_ok=True)
        return brand_dir

    def _get_videos_dir(self, project_id: int) -> Path:
        """Get or create videos directory for a project."""
        videos_dir = self._get_project_dir(project_id) / "videos"
        videos_dir.mkdir(parents=True, exist_ok=True)
        return videos_dir

    async def validate_image(self, file: UploadFile) -> str:
        """Validate uploaded file is an allowed image type and size."""
        if not file.content_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not determine file type",
            )

        if file.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_IMAGE_TYPES.keys())}",
            )

        # Check file size by reading content
        content = await file.read()
        await file.seek(0)  # Reset file pointer

        if len(content) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File too large. Maximum size is {MAX_IMAGE_SIZE // (1024 * 1024)}MB",
            )

        return ALLOWED_IMAGE_TYPES[file.content_type]

    async def validate_video(self, file: UploadFile) -> tuple[str, int]:
        """Validate uploaded file is an allowed video type and size. Returns extension and file size."""
        if not file.content_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not determine file type",
            )

        if file.content_type not in ALLOWED_VIDEO_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_VIDEO_TYPES.keys())}",
            )

        # Check file size by reading content
        content = await file.read()
        await file.seek(0)  # Reset file pointer
        file_size = len(content)

        if file_size > MAX_VIDEO_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File too large. Maximum size is {MAX_VIDEO_SIZE // (1024 * 1024)}MB",
            )

        return ALLOWED_VIDEO_TYPES[file.content_type], file_size

    async def save_brand_logo(
        self,
        project_id: int,
        file: UploadFile,
        logo_type: str  # "main", "dark", or "favicon"
    ) -> str:
        """Save a brand logo file and return the file path."""
        extension = await self.validate_image(file)

        # Generate unique filename
        filename = f"{logo_type}_{uuid.uuid4().hex[:8]}{extension}"
        brand_dir = self._get_brand_dir(project_id)
        file_path = brand_dir / filename

        # Save file
        content = await file.read()
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        # Return relative path for storage in database
        return str(file_path)

    async def save_video(
        self,
        project_id: int,
        file: UploadFile,
    ) -> tuple[str, str, int, str]:
        """
        Save a video file and return (file_path, file_name, file_size, mime_type).
        """
        extension, file_size = await self.validate_video(file)

        # Generate unique filename
        original_name = file.filename or "video"
        base_name = Path(original_name).stem
        filename = f"{base_name}_{uuid.uuid4().hex[:8]}{extension}"
        videos_dir = self._get_videos_dir(project_id)
        file_path = videos_dir / filename

        # Save file
        content = await file.read()
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        return str(file_path), filename, file_size, file.content_type

    async def save_video_thumbnail(
        self,
        project_id: int,
        file: UploadFile,
        video_id: int,
    ) -> str:
        """Save a thumbnail image for a video."""
        extension = await self.validate_image(file)

        filename = f"thumb_{video_id}_{uuid.uuid4().hex[:8]}{extension}"
        videos_dir = self._get_videos_dir(project_id)
        file_path = videos_dir / filename

        content = await file.read()
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        return str(file_path)

    async def delete_file(self, file_path: str) -> bool:
        """Delete a file if it exists."""
        try:
            path = Path(file_path)
            if path.exists():
                os.remove(path)
                return True
            return False
        except Exception:
            return False

    async def delete_brand_assets(self, project_id: int) -> bool:
        """Delete all brand assets for a project."""
        try:
            brand_dir = self._get_brand_dir(project_id)
            if brand_dir.exists():
                for file in brand_dir.iterdir():
                    if file.is_file():
                        os.remove(file)
                return True
            return False
        except Exception:
            return False

    def get_file_url(self, file_path: str, base_url: str = "") -> str:
        """Convert file path to URL for serving."""
        if not file_path:
            return ""
        # In production, this would return a CDN URL or signed URL
        return f"{base_url}/uploads/{file_path.replace('uploads/', '')}"


# Singleton instance
storage_service = StorageService()


def get_storage_service() -> StorageService:
    return storage_service

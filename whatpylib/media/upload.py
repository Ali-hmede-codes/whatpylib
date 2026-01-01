"""
Media upload functionality for WhatsApp.

Handles encrypting and uploading media files to WhatsApp's servers.
"""

import os
import hashlib
import mimetypes
from dataclasses import dataclass
from typing import Optional, Tuple, Union
from pathlib import Path
import io

import aiohttp

from whatpylib.crypto.media import MediaCrypto, MediaType, get_media_type_for_mimetype
from whatpylib.utils.logger import get_logger

logger = get_logger("media.upload")


# WhatsApp media upload endpoints
MEDIA_UPLOAD_URL = "https://mmg.whatsapp.net/v/media/upload"


@dataclass
class UploadResult:
    """
    Result of a media upload.
    
    Attributes:
        url: Direct download URL
        direct_path: Path for media download
        media_key: 32-byte encryption key
        file_sha256: Hash of original file
        file_enc_sha256: Hash of encrypted file
        file_length: Original file size
        mimetype: MIME type of the file
        width: Width for images/videos
        height: Height for images/videos
        duration: Duration for audio/video (seconds)
    """
    url: str
    direct_path: str
    media_key: bytes
    file_sha256: bytes
    file_enc_sha256: bytes
    file_length: int
    mimetype: str
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None
    thumbnail: Optional[bytes] = None


def detect_mimetype(
    file_path: Optional[str] = None,
    data: Optional[bytes] = None,
    filename: Optional[str] = None,
) -> str:
    """
    Detect MIME type from file path, data, or filename.
    
    Args:
        file_path: Path to the file
        data: File data
        filename: Filename hint
        
    Returns:
        MIME type string
    """
    # Try from file path or filename
    path = file_path or filename
    if path:
        mime, _ = mimetypes.guess_type(path)
        if mime:
            return mime
    
    # Try magic bytes detection
    if data and len(data) >= 12:
        # JPEG
        if data[:2] == b'\xff\xd8':
            return "image/jpeg"
        # PNG
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        # GIF
        if data[:6] in (b'GIF87a', b'GIF89a'):
            return "image/gif"
        # WebP
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return "image/webp"
        # MP4
        if data[4:8] == b'ftyp':
            return "video/mp4"
        # PDF
        if data[:4] == b'%PDF':
            return "application/pdf"
        # Ogg (audio)
        if data[:4] == b'OggS':
            return "audio/ogg"
        # MP3
        if data[:2] == b'\xff\xfb' or data[:3] == b'ID3':
            return "audio/mpeg"
    
    # Default
    return "application/octet-stream"


def get_image_dimensions(data: bytes) -> Tuple[int, int]:
    """
    Get width and height from image data.
    
    Args:
        data: Image bytes
        
    Returns:
        Tuple of (width, height)
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        return img.size
    except Exception:
        return (0, 0)


def get_video_duration(data: bytes) -> int:
    """
    Get video duration in seconds.
    
    Note: Requires moviepy or ffprobe for accurate results.
    Returns 0 if unable to determine.
    """
    # Simplified - would need moviepy/ffprobe for real implementation
    return 0


def get_audio_duration(data: bytes) -> int:
    """
    Get audio duration in seconds.
    
    Note: Requires pydub/ffprobe for accurate results.
    Returns 0 if unable to determine.
    """
    # Simplified - would need pydub/ffprobe for real implementation
    return 0


class MediaUploader:
    """
    Handles uploading media to WhatsApp servers.
    """
    
    def __init__(
        self,
        auth_token: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        """
        Initialize the uploader.
        
        Args:
            auth_token: Authentication token for uploads
            session: Optional aiohttp session to reuse
        """
        self.auth_token = auth_token
        self._session = session
        self._owns_session = session is None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self) -> None:
        """Close the uploader and release resources."""
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None
    
    async def upload(
        self,
        data: Optional[bytes] = None,
        file_path: Optional[str] = None,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> UploadResult:
        """
        Upload a media file.
        
        Args:
            data: File data bytes
            file_path: Path to file (if data not provided)
            mimetype: MIME type (auto-detected if not provided)
            filename: Filename hint
            
        Returns:
            UploadResult with upload details
        """
        # Read file if path provided
        if data is None:
            if file_path is None:
                raise ValueError("Either data or file_path must be provided")
            
            with open(file_path, "rb") as f:
                data = f.read()
            
            if filename is None:
                filename = os.path.basename(file_path)
        
        # Detect MIME type
        if mimetype is None:
            mimetype = detect_mimetype(file_path, data, filename)
        
        # Determine media type for encryption
        media_type = get_media_type_for_mimetype(mimetype)
        
        # Encrypt the file
        result = MediaCrypto.encrypt(data, media_type)
        
        # Get dimensions for images/videos
        width, height = None, None
        duration = None
        
        if mimetype.startswith("image/"):
            width, height = get_image_dimensions(data)
        elif mimetype.startswith("video/"):
            width, height = get_image_dimensions(data)  # thumbnail
            duration = get_video_duration(data)
        elif mimetype.startswith("audio/"):
            duration = get_audio_duration(data)
        
        # Generate thumbnail for images/videos
        thumbnail = None
        if mimetype.startswith("image/") or mimetype.startswith("video/"):
            from whatpylib.crypto.media import generate_thumbnail
            thumbnail = generate_thumbnail(data)
        
        # Upload to server
        # Note: This is a placeholder - actual upload logic depends on
        # WhatsApp's current API endpoints and authentication
        upload_url, direct_path = await self._upload_to_server(
            result.ciphertext,
            mimetype,
        )
        
        return UploadResult(
            url=upload_url,
            direct_path=direct_path,
            media_key=result.media_key,
            file_sha256=result.file_sha256,
            file_enc_sha256=result.file_enc_sha256,
            file_length=result.file_length,
            mimetype=mimetype,
            width=width,
            height=height,
            duration=duration,
            thumbnail=thumbnail,
        )
    
    async def _upload_to_server(
        self,
        encrypted_data: bytes,
        mimetype: str,
    ) -> Tuple[str, str]:
        """
        Upload encrypted data to WhatsApp's media servers.
        
        Args:
            encrypted_data: Encrypted file data
            mimetype: MIME type
            
        Returns:
            Tuple of (download_url, direct_path)
        """
        session = await self._get_session()
        
        # Prepare upload request
        # Note: This is placeholder logic - actual implementation
        # requires proper authentication and endpoint discovery
        
        headers = {
            "Content-Type": "application/octet-stream",
            "Origin": "https://web.whatsapp.com",
        }
        
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        
        # For now, return placeholder values
        # Real implementation would POST to WhatsApp's upload endpoint
        file_hash = hashlib.sha256(encrypted_data).hexdigest()[:16]
        
        # Simulate upload (in real implementation, this would be an actual HTTP request)
        logger.info(f"Would upload {len(encrypted_data)} bytes ({mimetype})")
        
        # Return placeholder URLs
        direct_path = f"/v/t62.xxxxx-xx/{file_hash}"
        url = f"https://mmg.whatsapp.net{direct_path}"
        
        return url, direct_path
    
    async def upload_from_url(
        self,
        url: str,
        mimetype: Optional[str] = None,
    ) -> UploadResult:
        """
        Download a file from URL and upload to WhatsApp.
        
        Args:
            url: URL to download from
            mimetype: Optional MIME type override
            
        Returns:
            UploadResult
        """
        session = await self._get_session()
        
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.read()
            
            # Use Content-Type from response if not provided
            if mimetype is None:
                mimetype = response.headers.get("Content-Type", "application/octet-stream")
        
        return await self.upload(data=data, mimetype=mimetype)
    
    async def __aenter__(self) -> "MediaUploader":
        await self._get_session()
        return self
    
    async def __aexit__(self, *args) -> None:
        await self.close()

"""
Media download functionality for WhatsApp.

Handles downloading and decrypting media files from WhatsApp's servers.
"""

import os
from dataclasses import dataclass
from typing import Optional, AsyncIterator
from pathlib import Path
import io

import aiohttp

from whatpylib.crypto.media import MediaCrypto, MediaType, get_media_type_for_mimetype
from whatpylib.utils.logger import get_logger
from whatpylib.utils.retry import retry

logger = get_logger("media.download")


@dataclass
class DownloadResult:
    """
    Result of a media download.
    
    Attributes:
        data: Decrypted file data
        mimetype: MIME type
        file_length: File size
    """
    data: bytes
    mimetype: str
    file_length: int


class MediaDownloader:
    """
    Handles downloading and decrypting media from WhatsApp servers.
    """
    
    def __init__(
        self,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        """
        Initialize the downloader.
        
        Args:
            session: Optional aiohttp session to reuse
        """
        self._session = session
        self._owns_session = session is None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self) -> None:
        """Close the downloader and release resources."""
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None
    
    @retry(max_attempts=3, base_delay=1.0)
    async def download(
        self,
        url: str,
        media_key: bytes,
        mimetype: str,
        file_sha256: Optional[bytes] = None,
    ) -> DownloadResult:
        """
        Download and decrypt a media file.
        
        Args:
            url: Download URL
            media_key: 32-byte decryption key
            mimetype: MIME type for key derivation
            file_sha256: Expected file hash for verification
            
        Returns:
            DownloadResult with decrypted data
        """
        session = await self._get_session()
        
        logger.debug(f"Downloading media from {url[:50]}...")
        
        # Download encrypted file
        async with session.get(url) as response:
            response.raise_for_status()
            encrypted_data = await response.read()
        
        logger.debug(f"Downloaded {len(encrypted_data)} bytes, decrypting...")
        
        # Determine media type
        media_type = get_media_type_for_mimetype(mimetype)
        
        # Decrypt
        decrypted = MediaCrypto.decrypt(
            encrypted_data,
            media_key,
            media_type,
            file_sha256,
        )
        
        logger.debug(f"Decrypted to {len(decrypted)} bytes")
        
        return DownloadResult(
            data=decrypted,
            mimetype=mimetype,
            file_length=len(decrypted),
        )
    
    async def download_to_file(
        self,
        url: str,
        media_key: bytes,
        mimetype: str,
        output_path: str,
        file_sha256: Optional[bytes] = None,
    ) -> str:
        """
        Download, decrypt, and save a media file.
        
        Args:
            url: Download URL
            media_key: Decryption key
            mimetype: MIME type
            output_path: Path to save the file
            file_sha256: Expected file hash
            
        Returns:
            Path to saved file
        """
        result = await self.download(url, media_key, mimetype, file_sha256)
        
        # Ensure directory exists
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file
        with open(path, "wb") as f:
            f.write(result.data)
        
        logger.info(f"Saved media to {output_path}")
        return str(path)
    
    async def stream_download(
        self,
        url: str,
        chunk_size: int = 64 * 1024,
    ) -> AsyncIterator[bytes]:
        """
        Stream download a file (without decryption).
        
        Useful for large files where you want to handle
        decryption separately.
        
        Args:
            url: Download URL
            chunk_size: Chunk size for streaming
            
        Yields:
            Chunks of encrypted data
        """
        session = await self._get_session()
        
        async with session.get(url) as response:
            response.raise_for_status()
            async for chunk in response.content.iter_chunked(chunk_size):
                yield chunk
    
    async def download_thumbnail(
        self,
        url: str,
    ) -> bytes:
        """
        Download a thumbnail (unencrypted preview).
        
        Args:
            url: Thumbnail URL
            
        Returns:
            Thumbnail image data
        """
        session = await self._get_session()
        
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.read()
    
    async def __aenter__(self) -> "MediaDownloader":
        await self._get_session()
        return self
    
    async def __aexit__(self, *args) -> None:
        await self.close()


async def download_media_message(
    message_info: dict,
    output_dir: Optional[str] = None,
) -> DownloadResult:
    """
    Convenience function to download media from a message.
    
    Args:
        message_info: Message info dict with url, mediaKey, mimetype, etc.
        output_dir: Optional directory to save the file
        
    Returns:
        DownloadResult
    """
    import base64
    
    url = message_info.get("url") or message_info.get("directPath")
    if not url:
        raise ValueError("No download URL in message")
    
    media_key = message_info.get("mediaKey")
    if isinstance(media_key, str):
        media_key = base64.b64decode(media_key)
    
    mimetype = message_info.get("mimetype", "application/octet-stream")
    
    file_sha256 = message_info.get("fileSha256")
    if isinstance(file_sha256, str):
        file_sha256 = base64.b64decode(file_sha256)
    
    async with MediaDownloader() as downloader:
        result = await downloader.download(url, media_key, mimetype, file_sha256)
        
        if output_dir:
            # Generate filename
            from whatpylib.messages.types import generate_message_id
            import mimetypes as mt
            
            ext = mt.guess_extension(mimetype) or ".bin"
            filename = f"{generate_message_id()}{ext}"
            output_path = os.path.join(output_dir, filename)
            
            with open(output_path, "wb") as f:
                f.write(result.data)
        
        return result

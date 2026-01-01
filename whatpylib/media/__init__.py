"""
Media package for upload, download, and processing.
"""

from whatpylib.media.upload import MediaUploader, UploadResult
from whatpylib.media.download import MediaDownloader
from whatpylib.media.thumbnail import ThumbnailGenerator

__all__ = [
    "MediaUploader",
    "UploadResult",
    "MediaDownloader",
    "ThumbnailGenerator",
]

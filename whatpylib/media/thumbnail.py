"""
Thumbnail generation for media files.
"""

import io
from dataclasses import dataclass
from typing import Optional, Tuple

from whatpylib.utils.logger import get_logger

logger = get_logger("media.thumbnail")


@dataclass
class Thumbnail:
    """
    Generated thumbnail.
    
    Attributes:
        data: JPEG thumbnail data
        width: Thumbnail width
        height: Thumbnail height
    """
    data: bytes
    width: int
    height: int


class ThumbnailGenerator:
    """
    Generates thumbnails for various media types.
    """
    
    # Default thumbnail sizes
    DEFAULT_SIZE = (320, 320)
    STICKER_SIZE = (96, 96)
    PROFILE_SIZE = (640, 640)
    
    @staticmethod
    def generate_image_thumbnail(
        image_data: bytes,
        max_size: Tuple[int, int] = DEFAULT_SIZE,
        quality: int = 60,
    ) -> Optional[Thumbnail]:
        """
        Generate a thumbnail from image data.
        
        Args:
            image_data: Original image bytes
            max_size: Maximum thumbnail dimensions
            quality: JPEG quality (1-100)
            
        Returns:
            Thumbnail or None if generation fails
        """
        try:
            from PIL import Image
            
            # Load image
            img = Image.open(io.BytesIO(image_data))
            original_size = img.size
            
            # Convert to RGB if needed (for JPEG output)
            if img.mode in ("RGBA", "P", "LA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")
            
            # Resize maintaining aspect ratio
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Save as JPEG
            output = io.BytesIO()
            img.save(output, format="JPEG", quality=quality, optimize=True)
            
            return Thumbnail(
                data=output.getvalue(),
                width=img.size[0],
                height=img.size[1],
            )
            
        except ImportError:
            logger.warning("Pillow not installed, cannot generate thumbnail")
            return None
        except Exception as e:
            logger.error(f"Failed to generate image thumbnail: {e}")
            return None
    
    @staticmethod
    def generate_video_thumbnail(
        video_data: bytes,
        max_size: Tuple[int, int] = DEFAULT_SIZE,
        frame_time: float = 1.0,
    ) -> Optional[Thumbnail]:
        """
        Generate a thumbnail from video data.
        
        Args:
            video_data: Video file bytes
            max_size: Maximum thumbnail dimensions
            frame_time: Time in seconds to extract frame from
            
        Returns:
            Thumbnail or None if generation fails
        """
        try:
            # Try using moviepy
            from moviepy.editor import VideoFileClip
            import tempfile
            
            # Write to temp file (moviepy needs file access)
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                f.write(video_data)
                temp_path = f.name
            
            try:
                clip = VideoFileClip(temp_path)
                
                # Get frame at specified time (or first frame if video is shorter)
                t = min(frame_time, clip.duration - 0.1)
                frame = clip.get_frame(max(0, t))
                
                clip.close()
                
                # Convert numpy array to PIL Image
                from PIL import Image
                img = Image.fromarray(frame)
                
                # Resize
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                # Convert to JPEG
                if img.mode != "RGB":
                    img = img.convert("RGB")
                
                output = io.BytesIO()
                img.save(output, format="JPEG", quality=60)
                
                return Thumbnail(
                    data=output.getvalue(),
                    width=img.size[0],
                    height=img.size[1],
                )
            finally:
                import os
                os.unlink(temp_path)
                
        except ImportError:
            logger.warning("moviepy not installed, cannot generate video thumbnail")
            return None
        except Exception as e:
            logger.error(f"Failed to generate video thumbnail: {e}")
            return None
    
    @staticmethod
    def generate_audio_waveform(
        audio_data: bytes,
        width: int = 64,
        height: int = 32,
    ) -> Optional[bytes]:
        """
        Generate a waveform visualization for audio.
        
        Args:
            audio_data: Audio file bytes
            width: Number of waveform samples
            height: Maximum height value
            
        Returns:
            Waveform data as bytes (each byte is 0-height) or None
        """
        try:
            from pydub import AudioSegment
            import numpy as np
            
            # Load audio
            audio = AudioSegment.from_file(io.BytesIO(audio_data))
            
            # Convert to mono and get samples
            samples = np.array(audio.set_channels(1).get_array_of_samples())
            
            # Normalize
            samples = np.abs(samples).astype(float)
            samples = samples / (samples.max() + 1e-6)
            
            # Downsample to width
            chunk_size = len(samples) // width
            if chunk_size == 0:
                chunk_size = 1
            
            waveform = []
            for i in range(width):
                start = i * chunk_size
                end = start + chunk_size
                chunk = samples[start:end] if end <= len(samples) else samples[start:]
                if len(chunk) > 0:
                    waveform.append(int(chunk.mean() * height))
                else:
                    waveform.append(0)
            
            return bytes(waveform)
            
        except ImportError:
            logger.warning("pydub/numpy not installed, cannot generate waveform")
            return None
        except Exception as e:
            logger.error(f"Failed to generate audio waveform: {e}")
            return None
    
    @classmethod
    def generate_sticker_thumbnail(
        cls,
        sticker_data: bytes,
    ) -> Optional[Thumbnail]:
        """
        Generate a thumbnail for a sticker.
        
        Args:
            sticker_data: Sticker image bytes (usually WebP)
            
        Returns:
            Thumbnail
        """
        return cls.generate_image_thumbnail(sticker_data, cls.STICKER_SIZE, quality=80)
    
    @classmethod
    def auto_generate(
        cls,
        data: bytes,
        mimetype: str,
    ) -> Optional[Thumbnail]:
        """
        Automatically generate a thumbnail based on MIME type.
        
        Args:
            data: Media file bytes
            mimetype: MIME type string
            
        Returns:
            Thumbnail or None
        """
        mimetype = mimetype.lower()
        
        if mimetype.startswith("image/"):
            if "webp" in mimetype:
                return cls.generate_sticker_thumbnail(data)
            return cls.generate_image_thumbnail(data)
        
        if mimetype.startswith("video/"):
            return cls.generate_video_thumbnail(data)
        
        # No thumbnail for audio/documents
        return None

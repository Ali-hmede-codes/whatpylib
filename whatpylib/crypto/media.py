"""
Media encryption and decryption for WhatsApp.

WhatsApp encrypts media files with a derived key before uploading.
The encrypted file is uploaded to WhatsApp's media servers, and the
decryption key is sent in the message body.
"""

import os
import hashlib
import hmac
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple
import io

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from whatpylib.utils.logger import get_logger

logger = get_logger("media_crypto")


class MediaType(Enum):
    """Media type identifiers for HKDF info."""
    IMAGE = b"WhatsApp Image Keys"
    VIDEO = b"WhatsApp Video Keys"
    AUDIO = b"WhatsApp Audio Keys"
    DOCUMENT = b"WhatsApp Document Keys"
    STICKER = b"WhatsApp Image Keys"  # Stickers use same as images
    HISTORY = b"WhatsApp History Keys"
    APP_STATE = b"WhatsApp App State Keys"


@dataclass
class MediaEncryptResult:
    """
    Result of media encryption.
    
    Attributes:
        ciphertext: Encrypted file data
        media_key: 32-byte media key
        file_sha256: SHA256 of original file
        file_enc_sha256: SHA256 of encrypted file
        file_length: Original file length
        iv: Initialization vector used
    """
    ciphertext: bytes
    media_key: bytes
    file_sha256: bytes
    file_enc_sha256: bytes
    file_length: int
    iv: bytes


class MediaCrypto:
    """
    Media encryption and decryption for WhatsApp.
    
    WhatsApp uses CBC mode with PKCS7 padding for media, with a
    10-byte MAC appended at the end.
    """
    
    # Key derivation sizes
    IV_SIZE = 16
    KEY_SIZE = 32
    MAC_KEY_SIZE = 32
    MAC_SIZE = 10
    
    @staticmethod
    def derive_keys(
        media_key: bytes,
        media_type: MediaType,
    ) -> Tuple[bytes, bytes, bytes]:
        """
        Derive encryption keys from media key.
        
        Args:
            media_key: 32-byte random media key
            media_type: Type of media for HKDF info
            
        Returns:
            Tuple of (iv, cipher_key, mac_key)
        """
        # HKDF expansion
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=112,  # 16 IV + 32 cipher key + 32 mac key + 32 unused
            salt=b"",
            info=media_type.value,
        )
        
        expanded = hkdf.derive(media_key)
        
        iv = expanded[:16]
        cipher_key = expanded[16:48]
        mac_key = expanded[48:80]
        
        return iv, cipher_key, mac_key
    
    @staticmethod
    def encrypt(
        plaintext: bytes,
        media_type: MediaType,
        media_key: Optional[bytes] = None,
    ) -> MediaEncryptResult:
        """
        Encrypt media data.
        
        Args:
            plaintext: File data to encrypt
            media_type: Type of media
            media_key: Optional media key (generated if not provided)
            
        Returns:
            MediaEncryptResult with encrypted data and keys
        """
        # Generate or use provided media key
        if media_key is None:
            media_key = os.urandom(32)
        
        # Calculate original file hash
        file_sha256 = hashlib.sha256(plaintext).digest()
        file_length = len(plaintext)
        
        # Derive keys
        iv, cipher_key, mac_key = MediaCrypto.derive_keys(media_key, media_type)
        
        # Pad plaintext (PKCS7)
        pad_length = 16 - (len(plaintext) % 16)
        padded = plaintext + bytes([pad_length] * pad_length)
        
        # Encrypt with AES-CBC
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        cipher = Cipher(algorithms.AES(cipher_key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded) + encryptor.finalize()
        
        # Calculate MAC
        mac_input = iv + ciphertext
        mac = hmac.new(mac_key, mac_input, hashlib.sha256).digest()[:10]
        
        # Combine: ciphertext + mac
        encrypted = ciphertext + mac
        
        # Hash encrypted file
        file_enc_sha256 = hashlib.sha256(encrypted).digest()
        
        return MediaEncryptResult(
            ciphertext=encrypted,
            media_key=media_key,
            file_sha256=file_sha256,
            file_enc_sha256=file_enc_sha256,
            file_length=file_length,
            iv=iv,
        )
    
    @staticmethod
    def decrypt(
        ciphertext: bytes,
        media_key: bytes,
        media_type: MediaType,
        file_sha256: Optional[bytes] = None,
    ) -> bytes:
        """
        Decrypt media data.
        
        Args:
            ciphertext: Encrypted file data (with MAC)
            media_key: 32-byte media key
            media_type: Type of media
            file_sha256: Expected SHA256 of decrypted file (for verification)
            
        Returns:
            Decrypted file data
            
        Raises:
            ValueError: If MAC verification fails or file hash doesn't match
        """
        if len(ciphertext) < MediaCrypto.MAC_SIZE:
            raise ValueError("Ciphertext too short")
        
        # Split ciphertext and MAC
        encrypted = ciphertext[:-10]
        mac = ciphertext[-10:]
        
        # Derive keys
        iv, cipher_key, mac_key = MediaCrypto.derive_keys(media_key, media_type)
        
        # Verify MAC
        expected_mac = hmac.new(
            mac_key,
            iv + encrypted,
            hashlib.sha256,
        ).digest()[:10]
        
        if not hmac.compare_digest(mac, expected_mac):
            raise ValueError("MAC verification failed")
        
        # Decrypt with AES-CBC
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        cipher = Cipher(algorithms.AES(cipher_key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded = decryptor.update(encrypted) + decryptor.finalize()
        
        # Remove PKCS7 padding
        pad_length = padded[-1]
        if pad_length > 16 or pad_length == 0:
            raise ValueError("Invalid padding")
        
        for i in range(1, pad_length + 1):
            if padded[-i] != pad_length:
                raise ValueError("Invalid padding")
        
        plaintext = padded[:-pad_length]
        
        # Verify file hash if provided
        if file_sha256 is not None:
            actual_hash = hashlib.sha256(plaintext).digest()
            if not hmac.compare_digest(file_sha256, actual_hash):
                raise ValueError("File hash verification failed")
        
        return plaintext
    
    @staticmethod
    def encrypt_stream(
        input_stream: io.IOBase,
        media_type: MediaType,
        chunk_size: int = 64 * 1024,
        media_key: Optional[bytes] = None,
    ) -> Tuple[io.BytesIO, MediaEncryptResult]:
        """
        Encrypt media from a stream.
        
        Args:
            input_stream: Input file stream
            media_type: Type of media
            chunk_size: Read chunk size
            media_key: Optional media key
            
        Returns:
            Tuple of (output stream, encryption result)
        """
        # Read all data (for simplicity - could be improved for large files)
        plaintext = input_stream.read()
        
        result = MediaCrypto.encrypt(plaintext, media_type, media_key)
        
        output = io.BytesIO(result.ciphertext)
        return output, result
    
    @staticmethod
    def decrypt_stream(
        input_stream: io.IOBase,
        media_key: bytes,
        media_type: MediaType,
        file_sha256: Optional[bytes] = None,
    ) -> io.BytesIO:
        """
        Decrypt media from a stream.
        
        Args:
            input_stream: Input encrypted stream
            media_key: Media key
            media_type: Type of media
            file_sha256: Expected file hash
            
        Returns:
            Output stream with decrypted data
        """
        ciphertext = input_stream.read()
        plaintext = MediaCrypto.decrypt(ciphertext, media_key, media_type, file_sha256)
        return io.BytesIO(plaintext)


def get_media_type_for_mimetype(mimetype: str) -> MediaType:
    """
    Get the appropriate MediaType for a MIME type.
    
    Args:
        mimetype: MIME type string
        
    Returns:
        Corresponding MediaType
    """
    mimetype = mimetype.lower()
    
    if mimetype.startswith("image/"):
        if "webp" in mimetype:
            return MediaType.STICKER
        return MediaType.IMAGE
    
    if mimetype.startswith("video/"):
        return MediaType.VIDEO
    
    if mimetype.startswith("audio/"):
        return MediaType.AUDIO
    
    # Default to document for unknown types
    return MediaType.DOCUMENT


def generate_thumbnail(
    image_data: bytes,
    max_size: Tuple[int, int] = (320, 320),
    quality: int = 60,
) -> bytes:
    """
    Generate a thumbnail for an image.
    
    Args:
        image_data: Original image bytes
        max_size: Maximum thumbnail dimensions
        quality: JPEG quality
        
    Returns:
        Thumbnail as JPEG bytes
    """
    try:
        from PIL import Image
        
        # Load image
        img = Image.open(io.BytesIO(image_data))
        
        # Convert to RGB if needed
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        # Resize maintaining aspect ratio
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Save as JPEG
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=quality)
        return output.getvalue()
        
    except ImportError:
        logger.warning("Pillow not installed, cannot generate thumbnail")
        return b""
    except Exception as e:
        logger.error(f"Failed to generate thumbnail: {e}")
        return b""

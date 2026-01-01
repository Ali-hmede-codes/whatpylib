"""
QR code generation and handling for WhatsApp Web authentication.
"""

import base64
import io
from dataclasses import dataclass
from typing import Callable, Optional, Any
import asyncio

try:
    import qrcode
    from qrcode.main import QRCode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from whatpylib.utils.logger import get_logger

logger = get_logger("qr")


@dataclass
class QRData:
    """
    QR code data for WhatsApp authentication.
    
    Attributes:
        ref: Reference string from server
        public_key: Client's public key
        client_id: Client identifier
        timestamp: Generation timestamp
    """
    ref: str
    public_key: bytes
    client_id: str
    timestamp: int
    
    def to_string(self) -> str:
        """
        Generate the QR code string.
        
        The format is: ref,publicKey,clientId
        """
        public_key_b64 = base64.b64encode(self.public_key).decode("ascii")
        return f"{self.ref},{public_key_b64},{self.client_id}"


def generate_qr_data(
    ref: str,
    public_key: bytes,
    client_id: str,
    timestamp: Optional[int] = None,
) -> QRData:
    """
    Generate QR data for authentication.
    
    Args:
        ref: Reference string from server
        public_key: Client's Curve25519 public key
        client_id: Client identifier
        timestamp: Optional timestamp (defaults to current time)
        
    Returns:
        QRData object
    """
    import time
    return QRData(
        ref=ref,
        public_key=public_key,
        client_id=client_id,
        timestamp=timestamp or int(time.time()),
    )


class QRCodeHandler:
    """
    Handler for QR code generation and display.
    
    Supports terminal output, image generation, and custom callbacks.
    """
    
    def __init__(
        self,
        print_terminal: bool = True,
        save_path: Optional[str] = None,
        on_qr: Optional[Callable[[str], Any]] = None,
    ) -> None:
        """
        Initialize QR code handler.
        
        Args:
            print_terminal: Whether to print QR to terminal
            save_path: Optional path to save QR image
            on_qr: Optional callback with QR string
        """
        self.print_terminal = print_terminal
        self.save_path = save_path
        self.on_qr = on_qr
        self._current_ref: Optional[str] = None
    
    async def handle_qr(self, qr_data: QRData) -> None:
        """
        Handle a new QR code.
        
        Args:
            qr_data: QR data to display
        """
        qr_string = qr_data.to_string()
        self._current_ref = qr_data.ref
        
        logger.info(f"New QR code generated (ref: {qr_data.ref[:8]}...)")
        
        # Print to terminal
        if self.print_terminal:
            self.print_qr_terminal(qr_string)
        
        # Save to file
        if self.save_path:
            self.save_qr_image(qr_string, self.save_path)
        
        # Call custom callback
        if self.on_qr:
            result = self.on_qr(qr_string)
            if asyncio.iscoroutine(result):
                await result
    
    def print_qr_terminal(self, data: str) -> None:
        """
        Print QR code to terminal using Unicode characters.
        
        Args:
            data: QR code data string
        """
        if not HAS_QRCODE:
            logger.warning("qrcode library not installed, cannot display QR")
            print(f"\nQR Data: {data}\n")
            return
        
        qr = QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        # Print using Unicode blocks
        print("\n" + "=" * 50)
        print("Scan this QR code with WhatsApp:")
        print("=" * 50)
        
        # Generate ASCII art
        matrix = qr.get_matrix()
        for r in range(0, len(matrix), 2):
            line = ""
            for c in range(len(matrix[0])):
                top = matrix[r][c] if r < len(matrix) else False
                bottom = matrix[r + 1][c] if r + 1 < len(matrix) else False
                
                if top and bottom:
                    line += "█"
                elif top:
                    line += "▀"
                elif bottom:
                    line += "▄"
                else:
                    line += " "
            print(line)
        
        print("=" * 50 + "\n")
    
    def save_qr_image(self, data: str, path: str) -> None:
        """
        Save QR code as image file.
        
        Args:
            data: QR code data string
            path: File path to save to
        """
        if not HAS_QRCODE:
            logger.warning("qrcode library not installed, cannot save QR image")
            return
        
        qr = QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(path)
        logger.info(f"QR code saved to {path}")
    
    def get_qr_bytes(self, data: str, format: str = "PNG") -> bytes:
        """
        Get QR code as bytes.
        
        Args:
            data: QR code data string
            format: Image format (PNG, JPEG, etc.)
            
        Returns:
            Image bytes
        """
        if not HAS_QRCODE or not HAS_PIL:
            raise RuntimeError("qrcode and Pillow required for QR image generation")
        
        qr = QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format=format)
        return buffer.getvalue()
    
    def get_qr_base64(self, data: str, format: str = "PNG") -> str:
        """
        Get QR code as base64 string.
        
        Args:
            data: QR code data string
            format: Image format
            
        Returns:
            Base64 encoded image string
        """
        img_bytes = self.get_qr_bytes(data, format)
        return base64.b64encode(img_bytes).decode("ascii")

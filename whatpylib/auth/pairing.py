"""
Pairing code authentication for WhatsApp.

This allows linking without scanning a QR code by entering a pairing
code on the phone.
"""

import asyncio
import os
import base64
from dataclasses import dataclass
from typing import Callable, Optional, Any

from whatpylib.utils.logger import get_logger

logger = get_logger("pairing")


@dataclass
class PairingRequest:
    """
    Pairing code request data.
    
    Attributes:
        phone_number: Phone number to pair with (with country code)
        pairing_code: The generated pairing code
        ref: Server reference for the pairing
        expires_at: Expiration timestamp
    """
    phone_number: str
    pairing_code: str
    ref: str
    expires_at: int


def generate_pairing_code() -> str:
    """
    Generate a random 8-digit pairing code.
    
    The format matches WhatsApp's: XXXX-XXXX
    
    Returns:
        Pairing code string
    """
    # Generate 8 random digits
    digits = "".join(str(b % 10) for b in os.urandom(8))
    # Format as XXXX-XXXX
    return f"{digits[:4]}-{digits[4:]}"


class PairingCodeHandler:
    """
    Handler for phone number pairing authentication.
    
    This allows users to link their WhatsApp by entering a pairing code
    on their phone instead of scanning a QR code.
    """
    
    def __init__(
        self,
        on_code: Optional[Callable[[str], Any]] = None,
        print_code: bool = True,
    ) -> None:
        """
        Initialize pairing code handler.
        
        Args:
            on_code: Callback when pairing code is generated
            print_code: Whether to print code to console
        """
        self.on_code = on_code
        self.print_code = print_code
        self._current_request: Optional[PairingRequest] = None
    
    async def request_pairing_code(
        self,
        phone_number: str,
        noise_keypair: dict[str, bytes],
        send_message: Callable,
    ) -> PairingRequest:
        """
        Request a pairing code for the given phone number.
        
        Args:
            phone_number: Phone number with country code (e.g., "1234567890")
            noise_keypair: The noise protocol keypair
            send_message: Function to send messages to WhatsApp
            
        Returns:
            PairingRequest with the generated code
        """
        import time
        
        # Normalize phone number
        phone = "".join(c for c in phone_number if c.isdigit())
        
        # Generate pairing code locally
        code = generate_pairing_code()
        
        logger.info(f"Requesting pairing code for {phone[:3]}***{phone[-2:]}")
        
        # Create pairing request
        # The actual registration happens through the WebSocket
        request = PairingRequest(
            phone_number=phone,
            pairing_code=code,
            ref="",  # Will be set by server response
            expires_at=int(time.time()) + 60,  # 60 second expiry
        )
        
        self._current_request = request
        
        # Display code
        if self.print_code:
            self._print_code(code)
        
        # Call callback
        if self.on_code:
            result = self.on_code(code)
            if asyncio.iscoroutine(result):
                await result
        
        return request
    
    def _print_code(self, code: str) -> None:
        """Print the pairing code to console."""
        print("\n" + "=" * 50)
        print("Enter this code in WhatsApp on your phone:")
        print("Settings > Linked Devices > Link a Device")
        print("=" * 50)
        print(f"\n    {code}\n")
        print("=" * 50 + "\n")
    
    async def wait_for_confirmation(
        self,
        timeout: float = 60.0,
    ) -> bool:
        """
        Wait for the pairing to be confirmed.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if pairing was successful
        """
        # This will be implemented to listen for the pairing confirmation
        # message from the WebSocket
        logger.info("Waiting for pairing confirmation...")
        
        # Placeholder - actual implementation will use WebSocket events
        await asyncio.sleep(timeout)
        return False


def encode_pairing_payload(
    phone_number: str,
    pairing_code: str,
    noise_public_key: bytes,
    identity_public_key: bytes,
) -> bytes:
    """
    Encode the pairing registration payload.
    
    Args:
        phone_number: Phone number to pair
        pairing_code: The pairing code
        noise_public_key: Noise protocol public key
        identity_public_key: Signal identity public key
        
    Returns:
        Encoded payload bytes
    """
    # Encode phone number
    phone_bytes = phone_number.encode("utf-8")
    
    # Encode pairing code (remove dash)
    code_bytes = pairing_code.replace("-", "").encode("utf-8")
    
    # Build payload
    # Format: phone_length(1) + phone + code_length(1) + code + keys
    payload = bytearray()
    payload.append(len(phone_bytes))
    payload.extend(phone_bytes)
    payload.append(len(code_bytes))
    payload.extend(code_bytes)
    payload.extend(noise_public_key)
    payload.extend(identity_public_key)
    
    return bytes(payload)

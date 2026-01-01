"""
Authentication package for WhatsApp login.
"""

from whatpylib.auth.state import AuthState, FileAuthState, MemoryAuthState
from whatpylib.auth.qr import QRCodeHandler, generate_qr_data
from whatpylib.auth.pairing import PairingCodeHandler

__all__ = [
    "AuthState",
    "FileAuthState",
    "MemoryAuthState",
    "QRCodeHandler",
    "generate_qr_data",
    "PairingCodeHandler",
]

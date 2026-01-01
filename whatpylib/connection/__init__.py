"""
Connection package for WebSocket and protocol handling.
"""

from whatpylib.connection.socket import WhatsAppSocket
from whatpylib.connection.noise import NoiseHandler, NoiseState
from whatpylib.connection.binary import BinaryEncoder, BinaryDecoder

__all__ = [
    "WhatsAppSocket",
    "NoiseHandler",
    "NoiseState",
    "BinaryEncoder",
    "BinaryDecoder",
]

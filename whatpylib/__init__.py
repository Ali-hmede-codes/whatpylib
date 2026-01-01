"""
WhatPyLib - A Python library for WhatsApp Web communication.

This library implements the WhatsApp Multi-Device protocol, allowing you to
interact with WhatsApp without requiring a phone after initial QR code linking.

Example usage:
    >>> from whatpylib import WhatsAppClient
    >>> async with WhatsAppClient() as client:
    ...     await client.connect()
    ...     await client.send_message("1234567890@s.whatsapp.net", "Hello!")
"""

__version__ = "0.1.0"
__author__ = "WhatPyLib Contributors"

from whatpylib.client import WhatsAppClient
from whatpylib.config import Config
from whatpylib.events.emitter import EventEmitter

# Message types
from whatpylib.messages.types import (
    TextMessage,
    ImageMessage,
    VideoMessage,
    AudioMessage,
    DocumentMessage,
    LocationMessage,
    ContactMessage,
    ReactionMessage,
    PollMessage,
)

# Auth state
from whatpylib.auth.state import AuthState, FileAuthState, MemoryAuthState

# Utilities
from whatpylib.utils.jid import JID, parse_jid, encode_jid

__all__ = [
    # Main client
    "WhatsAppClient",
    "Config",
    "EventEmitter",
    # Messages
    "TextMessage",
    "ImageMessage",
    "VideoMessage",
    "AudioMessage",
    "DocumentMessage",
    "LocationMessage",
    "ContactMessage",
    "ReactionMessage",
    "PollMessage",
    # Auth
    "AuthState",
    "FileAuthState",
    "MemoryAuthState",
    # Utils
    "JID",
    "parse_jid",
    "encode_jid",
]

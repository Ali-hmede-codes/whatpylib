"""
Configuration and constants for WhatsApp Web protocol.
"""

from dataclasses import dataclass, field
from typing import Optional
import platform


# WhatsApp Web endpoints
WA_WEB_SOCKET_URL = "wss://web.whatsapp.com/ws/chat"
WA_WEB_ORIGIN = "https://web.whatsapp.com"
WA_UPLOAD_URL = "https://mmg.whatsapp.net"

# Protocol versions
WA_WEB_VERSION = [2, 3000, 1012734542]  # WhatsApp Web version
WA_WEB_VERSION_HASH = "2.3000.1012734542"

# Binary protocol constants
NOISE_PROTOCOL_NAME = b"Noise_XX_25519_AESGCM_SHA256\x00\x00\x00\x00"
WA_HEADER = b"WA\x06\x00"  # WhatsApp header for binary protocol

# Default timeouts (in seconds)
DEFAULT_CONNECT_TIMEOUT = 30
DEFAULT_QR_TIMEOUT = 60
DEFAULT_REQUEST_TIMEOUT = 30
DEFAULT_KEEPALIVE_INTERVAL = 25

# Message constants
MAX_MESSAGE_LENGTH = 65536
MAX_MEDIA_SIZE = 64 * 1024 * 1024  # 64MB
MAX_DOCUMENT_SIZE = 100 * 1024 * 1024  # 100MB

# Rate limiting
MIN_MESSAGE_INTERVAL = 0.5  # Minimum seconds between messages
MAX_MESSAGES_PER_MINUTE = 60

# JID suffixes
JID_SERVER = "s.whatsapp.net"
JID_BROADCAST = "broadcast"
JID_GROUP = "g.us"
JID_STATUS = "status@broadcast"

# Protobuf message types
class MessageType:
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    STICKER = "sticker"
    LOCATION = "location"
    CONTACT = "contact"
    CONTACT_ARRAY = "contactArray"
    POLL = "poll"
    REACTION = "reaction"
    EXTENDED_TEXT = "extendedText"
    BUTTONS = "buttons"
    LIST = "list"
    TEMPLATE = "template"


class ConnectionState:
    """Connection state constants."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATING = "authenticating"
    AUTHENTICATED = "authenticated"
    RECONNECTING = "reconnecting"


class PresenceState:
    """Presence state constants."""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    COMPOSING = "composing"
    RECORDING = "recording"
    PAUSED = "paused"


@dataclass
class Config:
    """
    Configuration for WhatsApp client.
    
    Attributes:
        auth_state_path: Path to store authentication state
        connect_timeout: Connection timeout in seconds
        qr_timeout: QR code scan timeout in seconds
        request_timeout: Request timeout in seconds
        keepalive_interval: Keepalive ping interval in seconds
        auto_reconnect: Whether to automatically reconnect on disconnect
        max_reconnect_attempts: Maximum reconnection attempts
        reconnect_delay: Delay between reconnection attempts
        log_level: Logging level
        browser_name: Browser name for device registration
        browser_version: Browser version for device registration
        os_name: OS name for device registration
        os_version: OS version for device registration
    """
    auth_state_path: Optional[str] = None
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT
    qr_timeout: float = DEFAULT_QR_TIMEOUT
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT
    keepalive_interval: float = DEFAULT_KEEPALIVE_INTERVAL
    auto_reconnect: bool = True
    max_reconnect_attempts: int = 5
    reconnect_delay: float = 3.0
    log_level: str = "INFO"
    
    # Device info
    browser_name: str = "WhatPyLib"
    browser_version: str = "1.0.0"
    os_name: str = field(default_factory=lambda: platform.system())
    os_version: str = field(default_factory=lambda: platform.release())
    
    # Advanced options
    print_qr_terminal: bool = True
    emit_self_messages: bool = False
    sync_full_history: bool = False
    
    def get_user_agent(self) -> str:
        """Get user agent string for HTTP requests."""
        return (
            f"Mozilla/5.0 ({self.os_name} {self.os_version}) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/138.0.0.0 Safari/537.36"
        )
    
    def get_device_props(self) -> dict:
        """Get device properties for registration."""
        return {
            "os": self.os_name,
            "version": {
                "primary": int(WA_WEB_VERSION[0]),
                "secondary": int(WA_WEB_VERSION[1]),
                "tertiary": int(WA_WEB_VERSION[2]),
            },
            "platformType": "DESKTOP",
            "requireFullSync": self.sync_full_history,
        }

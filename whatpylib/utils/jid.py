"""
JID (Jabber ID) utilities for WhatsApp addressing.

WhatsApp uses JIDs to identify users, groups, and broadcasts:
- User: 1234567890@s.whatsapp.net
- Group: 1234567890-1234567890@g.us
- Broadcast: status@broadcast
"""

from dataclasses import dataclass
from typing import Optional
import re

from whatpylib.config import JID_SERVER, JID_GROUP, JID_BROADCAST


@dataclass(frozen=True)
class JID:
    """
    Represents a WhatsApp JID (Jabber ID).
    
    Attributes:
        user: The user part (phone number or group ID)
        server: The server part (s.whatsapp.net, g.us, or broadcast)
        agent: Optional agent identifier for multi-device
        device: Optional device identifier for multi-device
    """
    user: str
    server: str
    agent: int = 0
    device: int = 0
    
    def __str__(self) -> str:
        """Return the full JID string."""
        return encode_jid(self)
    
    def __repr__(self) -> str:
        return f"JID({self})"
    
    @property
    def is_user(self) -> bool:
        """Check if this is a user JID."""
        return self.server == JID_SERVER
    
    @property
    def is_group(self) -> bool:
        """Check if this is a group JID."""
        return self.server == JID_GROUP
    
    @property
    def is_broadcast(self) -> bool:
        """Check if this is a broadcast JID."""
        return self.server == JID_BROADCAST or self.user == "status"
    
    @property
    def phone_number(self) -> Optional[str]:
        """Extract phone number if this is a user JID."""
        if self.is_user:
            return self.user
        return None
    
    def to_user_jid(self) -> "JID":
        """Convert to a user JID (strip device info)."""
        return JID(user=self.user, server=self.server)


# Regex patterns for JID parsing
JID_PATTERN = re.compile(
    r"^(?P<user>[^@:]+)"
    r"(?::(?P<agent>\d+):(?P<device>\d+))?"
    r"@(?P<server>[^@]+)$"
)

PHONE_PATTERN = re.compile(r"^\+?[1-9]\d{6,14}$")


def parse_jid(jid_str: str) -> JID:
    """
    Parse a JID string into a JID object.
    
    Args:
        jid_str: The JID string to parse (e.g., "1234567890@s.whatsapp.net")
        
    Returns:
        JID object
        
    Raises:
        ValueError: If the JID string is invalid
    """
    if not jid_str:
        raise ValueError("Empty JID string")
    
    # Handle phone number without server
    if "@" not in jid_str:
        # Assume it's a phone number
        phone = normalize_phone(jid_str)
        return JID(user=phone, server=JID_SERVER)
    
    match = JID_PATTERN.match(jid_str)
    if not match:
        raise ValueError(f"Invalid JID format: {jid_str}")
    
    groups = match.groupdict()
    return JID(
        user=groups["user"],
        server=groups["server"],
        agent=int(groups["agent"]) if groups["agent"] else 0,
        device=int(groups["device"]) if groups["device"] else 0,
    )


def encode_jid(jid: JID) -> str:
    """
    Encode a JID object to a JID string.
    
    Args:
        jid: The JID object to encode
        
    Returns:
        JID string
    """
    if jid.agent or jid.device:
        return f"{jid.user}:{jid.agent}:{jid.device}@{jid.server}"
    return f"{jid.user}@{jid.server}"


def normalize_phone(phone: str) -> str:
    """
    Normalize a phone number for use in a JID.
    
    Args:
        phone: Phone number (with or without + prefix)
        
    Returns:
        Normalized phone number (digits only)
        
    Raises:
        ValueError: If the phone number is invalid
    """
    # Remove all non-digit characters except leading +
    cleaned = "".join(c for c in phone if c.isdigit())
    
    if not cleaned:
        raise ValueError(f"Invalid phone number: {phone}")
    
    # Basic validation
    if len(cleaned) < 7 or len(cleaned) > 15:
        raise ValueError(f"Phone number has invalid length: {phone}")
    
    return cleaned


def is_group_jid(jid: JID | str) -> bool:
    """
    Check if a JID represents a group.
    
    Args:
        jid: JID object or string
        
    Returns:
        True if the JID is a group JID
    """
    if isinstance(jid, str):
        jid = parse_jid(jid)
    return jid.is_group


def is_user_jid(jid: JID | str) -> bool:
    """
    Check if a JID represents a user.
    
    Args:
        jid: JID object or string
        
    Returns:
        True if the JID is a user JID
    """
    if isinstance(jid, str):
        jid = parse_jid(jid)
    return jid.is_user


def jid_from_phone(phone: str) -> JID:
    """
    Create a user JID from a phone number.
    
    Args:
        phone: Phone number
        
    Returns:
        User JID
    """
    return JID(user=normalize_phone(phone), server=JID_SERVER)


def get_group_id(jid: JID | str) -> Optional[str]:
    """
    Extract the group ID from a group JID.
    
    Args:
        jid: JID object or string
        
    Returns:
        Group ID or None if not a group JID
    """
    if isinstance(jid, str):
        jid = parse_jid(jid)
    if jid.is_group:
        return jid.user
    return None

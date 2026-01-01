"""
Message type definitions for WhatsApp messages.

This module defines dataclasses for all supported message types.
"""

import time
import base64
from dataclasses import dataclass, field
from typing import Any, Optional, List
from abc import ABC

from whatpylib.utils.jid import JID, parse_jid


def generate_message_id() -> str:
    """
    Generate a unique message ID.
    
    Format: WA_XXXX_XXXXXXXX_XXXX where X is base64 chars
    """
    import os
    random_bytes = os.urandom(16)
    b64 = base64.urlsafe_b64encode(random_bytes).decode("ascii")[:16]
    return f"3EB0{b64.upper()}"


@dataclass
class MessageKey:
    """
    Unique identifier for a message.
    
    Attributes:
        remote_jid: JID of the chat
        from_me: Whether the message is from us
        id: Message ID
        participant: Participant JID (for groups)
    """
    remote_jid: str
    from_me: bool
    id: str
    participant: Optional[str] = None
    
    def __str__(self) -> str:
        return f"{self.remote_jid}:{self.id}"


@dataclass
class MessageContext:
    """
    Context for quoted/replied messages.
    
    Attributes:
        quoted_message_id: ID of the quoted message
        quoted_participant: JID of the quoted message sender
        mentioned_jids: List of mentioned JIDs
    """
    quoted_message_id: Optional[str] = None
    quoted_participant: Optional[str] = None
    mentioned_jids: List[str] = field(default_factory=list)


@dataclass
class Message(ABC):
    """
    Base class for all message types.
    
    Attributes:
        key: Message key (unique identifier)
        timestamp: Message timestamp (unix epoch)
        push_name: Sender's push name
        broadcast: Whether this is a broadcast message
        context: Optional message context (for replies)
    """
    key: MessageKey
    timestamp: int = field(default_factory=lambda: int(time.time()))
    push_name: Optional[str] = None
    broadcast: bool = False
    context: Optional[MessageContext] = None
    
    @property
    def chat_jid(self) -> str:
        """Get the chat JID."""
        return self.key.remote_jid
    
    @property
    def sender_jid(self) -> str:
        """Get the sender JID."""
        if self.key.participant:
            return self.key.participant
        return self.key.remote_jid
    
    @property
    def from_me(self) -> bool:
        """Check if message is from us."""
        return self.key.from_me
    
    @property
    def message_id(self) -> str:
        """Get the message ID."""
        return self.key.id
    
    def is_group(self) -> bool:
        """Check if message is from a group."""
        jid = parse_jid(self.key.remote_jid)
        return jid.is_group
    
    def is_reply(self) -> bool:
        """Check if this message is a reply."""
        return self.context is not None and self.context.quoted_message_id is not None


@dataclass
class TextMessage(Message):
    """
    Text message.
    
    Attributes:
        text: Message text content
    """
    text: str = ""
    
    def __str__(self) -> str:
        return f"TextMessage({self.text[:50]}...)" if len(self.text) > 50 else f"TextMessage({self.text})"


@dataclass
class ExtendedTextMessage(Message):
    """
    Extended text message with rich content.
    
    Attributes:
        text: Message text
        title: Link preview title
        description: Link preview description
        canonical_url: URL for link preview
        matched_text: Text that matched for preview
        thumbnail: Thumbnail image bytes
    """
    text: str = ""
    title: Optional[str] = None
    description: Optional[str] = None
    canonical_url: Optional[str] = None
    matched_text: Optional[str] = None
    thumbnail: Optional[bytes] = None


@dataclass
class MediaMessage(Message):
    """
    Base class for media messages.
    
    Attributes:
        url: Media download URL
        mimetype: Media MIME type
        file_sha256: SHA256 of the file
        file_length: File size in bytes
        media_key: Encryption key for media
        file_enc_sha256: SHA256 of encrypted file
        caption: Optional caption
    """
    url: Optional[str] = None
    mimetype: Optional[str] = None
    file_sha256: Optional[bytes] = None
    file_length: int = 0
    media_key: Optional[bytes] = None
    file_enc_sha256: Optional[bytes] = None
    caption: Optional[str] = None
    
    # Local file handling
    _local_data: Optional[bytes] = field(default=None, repr=False)
    _local_path: Optional[str] = field(default=None, repr=False)


@dataclass
class ImageMessage(MediaMessage):
    """
    Image message.
    
    Attributes:
        width: Image width
        height: Image height
        thumbnail: JPEG thumbnail
    """
    width: int = 0
    height: int = 0
    thumbnail: Optional[bytes] = None
    
    def __str__(self) -> str:
        return f"ImageMessage({self.width}x{self.height})"


@dataclass
class VideoMessage(MediaMessage):
    """
    Video message.
    
    Attributes:
        width: Video width
        height: Video height
        duration: Duration in seconds
        gif_playback: Whether to play as GIF
        thumbnail: JPEG thumbnail
    """
    width: int = 0
    height: int = 0
    duration: int = 0
    gif_playback: bool = False
    thumbnail: Optional[bytes] = None


@dataclass
class AudioMessage(MediaMessage):
    """
    Audio message.
    
    Attributes:
        duration: Duration in seconds
        ptt: Whether this is a voice note (push-to-talk)
        waveform: Audio waveform data
    """
    duration: int = 0
    ptt: bool = False  # Voice note
    waveform: Optional[bytes] = None


@dataclass
class DocumentMessage(MediaMessage):
    """
    Document message.
    
    Attributes:
        filename: Original filename
        page_count: Number of pages (for PDFs)
    """
    filename: Optional[str] = None
    page_count: int = 0
    
    def __str__(self) -> str:
        return f"DocumentMessage({self.filename})"


@dataclass
class StickerMessage(MediaMessage):
    """
    Sticker message.
    
    Attributes:
        width: Sticker width
        height: Sticker height
        is_animated: Whether sticker is animated
        is_avatar: Whether sticker is an avatar
    """
    width: int = 0
    height: int = 0
    is_animated: bool = False
    is_avatar: bool = False


@dataclass
class LocationMessage(Message):
    """
    Location message.
    
    Attributes:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        name: Location name
        address: Location address
        url: Google Maps URL
        thumbnail: Map thumbnail
    """
    latitude: float = 0.0
    longitude: float = 0.0
    name: Optional[str] = None
    address: Optional[str] = None
    url: Optional[str] = None
    thumbnail: Optional[bytes] = None
    
    def __str__(self) -> str:
        return f"LocationMessage({self.latitude}, {self.longitude})"


@dataclass
class LiveLocationMessage(LocationMessage):
    """
    Live location sharing message.
    
    Attributes:
        accuracy: Location accuracy in meters
        speed: Speed in m/s
        degrees_clockwise: Heading
        caption: Optional caption
        sequence_number: Update sequence
        time_offset: Time offset
    """
    accuracy: int = 0
    speed: float = 0.0
    degrees_clockwise: int = 0
    sequence_number: int = 0
    time_offset: int = 0


@dataclass
class ContactInfo:
    """
    Contact card information.
    
    Attributes:
        display_name: Display name
        vcard: vCard data
    """
    display_name: str = ""
    vcard: str = ""


@dataclass
class ContactMessage(Message):
    """
    Contact card message.
    
    Attributes:
        display_name: Contact display name
        vcard: vCard string
    """
    display_name: str = ""
    vcard: str = ""
    
    def __str__(self) -> str:
        return f"ContactMessage({self.display_name})"


@dataclass
class ContactArrayMessage(Message):
    """
    Multiple contacts message.
    
    Attributes:
        contacts: List of contact info
    """
    contacts: List[ContactInfo] = field(default_factory=list)


@dataclass
class ReactionMessage(Message):
    """
    Reaction to a message.
    
    Attributes:
        react_key: Key of the message being reacted to
        emoji: Reaction emoji (empty string to remove)
    """
    react_key: Optional[MessageKey] = None
    emoji: str = ""
    
    def __str__(self) -> str:
        return f"ReactionMessage({self.emoji})"


@dataclass
class PollOption:
    """
    Poll option.
    
    Attributes:
        name: Option text
        sha256: Option hash (for selection)
    """
    name: str = ""
    sha256: Optional[bytes] = None


@dataclass
class PollMessage(Message):
    """
    Poll message.
    
    Attributes:
        name: Poll question
        options: List of poll options
        selectable_count: Max selectable options (0 = unlimited)
    """
    name: str = ""
    options: List[PollOption] = field(default_factory=list)
    selectable_count: int = 0


@dataclass
class PollUpdateMessage(Message):
    """
    Poll vote update.
    
    Attributes:
        poll_key: Key of the poll message
        selected_options: Hashes of selected options
        voter_jid: JID of the voter
    """
    poll_key: Optional[MessageKey] = None
    selected_options: List[bytes] = field(default_factory=list)
    voter_jid: Optional[str] = None


@dataclass
class ButtonsMessage(Message):
    """
    Message with buttons (deprecated by WhatsApp).
    
    Attributes:
        content_text: Message text
        footer_text: Footer text
        buttons: List of button definitions
    """
    content_text: str = ""
    footer_text: Optional[str] = None
    buttons: List[dict[str, Any]] = field(default_factory=list)


@dataclass 
class ListMessage(Message):
    """
    List/menu message (deprecated by WhatsApp).
    
    Attributes:
        title: List title
        description: Description text
        button_text: Button text
        list_type: Type of list
        sections: List sections
    """
    title: str = ""
    description: str = ""
    button_text: str = ""
    list_type: int = 0
    sections: List[dict[str, Any]] = field(default_factory=list)


def create_text_message(
    to: str,
    text: str,
    quoted: Optional[Message] = None,
    mentions: Optional[List[str]] = None,
) -> TextMessage:
    """
    Create a text message.
    
    Args:
        to: Recipient JID
        text: Message text
        quoted: Optional message to reply to
        mentions: Optional list of JIDs to mention
        
    Returns:
        TextMessage ready to send
    """
    key = MessageKey(
        remote_jid=to,
        from_me=True,
        id=generate_message_id(),
    )
    
    context = None
    if quoted or mentions:
        context = MessageContext(
            quoted_message_id=quoted.key.id if quoted else None,
            quoted_participant=quoted.sender_jid if quoted else None,
            mentioned_jids=mentions or [],
        )
    
    return TextMessage(
        key=key,
        text=text,
        context=context,
    )


def create_reaction(
    to_message: Message,
    emoji: str,
) -> ReactionMessage:
    """
    Create a reaction to a message.
    
    Args:
        to_message: Message to react to
        emoji: Reaction emoji (empty string to remove)
        
    Returns:
        ReactionMessage ready to send
    """
    key = MessageKey(
        remote_jid=to_message.key.remote_jid,
        from_me=True,
        id=generate_message_id(),
    )
    
    return ReactionMessage(
        key=key,
        react_key=to_message.key,
        emoji=emoji,
    )

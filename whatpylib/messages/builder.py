"""
Fluent message builder for constructing messages.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional, Union
import os

from whatpylib.messages.types import (
    Message,
    MessageKey,
    MessageContext,
    TextMessage,
    ImageMessage,
    VideoMessage,
    AudioMessage,
    DocumentMessage,
    LocationMessage,
    ContactMessage,
    ReactionMessage,
    PollMessage,
    PollOption,
    StickerMessage,
    generate_message_id,
)
from whatpylib.utils.jid import parse_jid


class MessageBuilder:
    """
    Fluent builder for creating messages.
    
    Example:
        message = (
            MessageBuilder()
            .to("1234567890@s.whatsapp.net")
            .text("Hello!")
            .mention(["user1@s.whatsapp.net"])
            .build()
        )
    """
    
    def __init__(self) -> None:
        self._to: Optional[str] = None
        self._text: Optional[str] = None
        self._media_path: Optional[str] = None
        self._media_data: Optional[bytes] = None
        self._media_type: Optional[str] = None
        self._mimetype: Optional[str] = None
        self._caption: Optional[str] = None
        self._filename: Optional[str] = None
        self._quoted_message: Optional[Message] = None
        self._mentions: List[str] = []
        self._location: Optional[tuple[float, float]] = None
        self._location_name: Optional[str] = None
        self._contact_name: Optional[str] = None
        self._contact_vcard: Optional[str] = None
        self._reaction_emoji: Optional[str] = None
        self._reaction_key: Optional[MessageKey] = None
        self._poll_name: Optional[str] = None
        self._poll_options: List[str] = []
        self._poll_selectable: int = 0
        self._ptt: bool = False  # Voice note
        self._gif_playback: bool = False
    
    def to(self, jid: str) -> "MessageBuilder":
        """
        Set the recipient.
        
        Args:
            jid: Recipient JID (phone number or group ID)
            
        Returns:
            Self for chaining
        """
        # Normalize JID
        if "@" not in jid:
            jid = f"{jid}@s.whatsapp.net"
        self._to = jid
        return self
    
    def text(self, content: str) -> "MessageBuilder":
        """
        Set text content.
        
        Args:
            content: Text message content
            
        Returns:
            Self for chaining
        """
        self._text = content
        self._media_type = None
        return self
    
    def image(
        self,
        path: Optional[str] = None,
        data: Optional[bytes] = None,
        caption: Optional[str] = None,
    ) -> "MessageBuilder":
        """
        Set image content.
        
        Args:
            path: Path to image file
            data: Image bytes
            caption: Optional caption
            
        Returns:
            Self for chaining
        """
        if path:
            self._media_path = path
        if data:
            self._media_data = data
        self._media_type = "image"
        self._caption = caption
        return self
    
    def video(
        self,
        path: Optional[str] = None,
        data: Optional[bytes] = None,
        caption: Optional[str] = None,
        gif_playback: bool = False,
    ) -> "MessageBuilder":
        """
        Set video content.
        
        Args:
            path: Path to video file
            data: Video bytes
            caption: Optional caption
            gif_playback: Play as GIF
            
        Returns:
            Self for chaining
        """
        if path:
            self._media_path = path
        if data:
            self._media_data = data
        self._media_type = "video"
        self._caption = caption
        self._gif_playback = gif_playback
        return self
    
    def audio(
        self,
        path: Optional[str] = None,
        data: Optional[bytes] = None,
        ptt: bool = False,
    ) -> "MessageBuilder":
        """
        Set audio content.
        
        Args:
            path: Path to audio file
            data: Audio bytes
            ptt: Voice note (push-to-talk) mode
            
        Returns:
            Self for chaining
        """
        if path:
            self._media_path = path
        if data:
            self._media_data = data
        self._media_type = "audio"
        self._ptt = ptt
        return self
    
    def voice_note(
        self,
        path: Optional[str] = None,
        data: Optional[bytes] = None,
    ) -> "MessageBuilder":
        """
        Set voice note content (shortcut for audio with ptt=True).
        
        Args:
            path: Path to audio file
            data: Audio bytes
            
        Returns:
            Self for chaining
        """
        return self.audio(path=path, data=data, ptt=True)
    
    def document(
        self,
        path: Optional[str] = None,
        data: Optional[bytes] = None,
        filename: Optional[str] = None,
        mimetype: Optional[str] = None,
        caption: Optional[str] = None,
    ) -> "MessageBuilder":
        """
        Set document content.
        
        Args:
            path: Path to document file
            data: Document bytes
            filename: Filename to display
            mimetype: MIME type
            caption: Optional caption
            
        Returns:
            Self for chaining
        """
        if path:
            self._media_path = path
            if not filename:
                filename = os.path.basename(path)
        if data:
            self._media_data = data
        self._media_type = "document"
        self._filename = filename
        self._mimetype = mimetype
        self._caption = caption
        return self
    
    def sticker(
        self,
        path: Optional[str] = None,
        data: Optional[bytes] = None,
    ) -> "MessageBuilder":
        """
        Set sticker content.
        
        Args:
            path: Path to sticker file (WebP)
            data: Sticker bytes
            
        Returns:
            Self for chaining
        """
        if path:
            self._media_path = path
        if data:
            self._media_data = data
        self._media_type = "sticker"
        return self
    
    def location(
        self,
        latitude: float,
        longitude: float,
        name: Optional[str] = None,
        address: Optional[str] = None,
    ) -> "MessageBuilder":
        """
        Set location content.
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            name: Location name
            address: Location address
            
        Returns:
            Self for chaining
        """
        self._location = (latitude, longitude)
        self._location_name = name
        self._media_type = "location"
        return self
    
    def contact(
        self,
        display_name: str,
        vcard: str,
    ) -> "MessageBuilder":
        """
        Set contact card content.
        
        Args:
            display_name: Contact name
            vcard: vCard string
            
        Returns:
            Self for chaining
        """
        self._contact_name = display_name
        self._contact_vcard = vcard
        self._media_type = "contact"
        return self
    
    def reaction(
        self,
        to_message: Union[Message, MessageKey],
        emoji: str,
    ) -> "MessageBuilder":
        """
        Create a reaction.
        
        Args:
            to_message: Message or key to react to
            emoji: Reaction emoji (empty to remove)
            
        Returns:
            Self for chaining
        """
        if isinstance(to_message, Message):
            self._reaction_key = to_message.key
        else:
            self._reaction_key = to_message
        self._reaction_emoji = emoji
        self._media_type = "reaction"
        return self
    
    def poll(
        self,
        question: str,
        options: List[str],
        selectable_count: int = 0,
    ) -> "MessageBuilder":
        """
        Create a poll.
        
        Args:
            question: Poll question
            options: List of options
            selectable_count: Max selections (0 = unlimited)
            
        Returns:
            Self for chaining
        """
        self._poll_name = question
        self._poll_options = options
        self._poll_selectable = selectable_count
        self._media_type = "poll"
        return self
    
    def reply_to(self, message: Message) -> "MessageBuilder":
        """
        Reply to a message.
        
        Args:
            message: Message to reply to
            
        Returns:
            Self for chaining
        """
        self._quoted_message = message
        return self
    
    def mention(self, jids: List[str]) -> "MessageBuilder":
        """
        Add mentions.
        
        Args:
            jids: List of JIDs to mention
            
        Returns:
            Self for chaining
        """
        self._mentions.extend(jids)
        return self
    
    def build(self) -> Message:
        """
        Build the message.
        
        Returns:
            Constructed message
            
        Raises:
            ValueError: If required fields are missing
        """
        if not self._to:
            raise ValueError("Recipient (to) is required")
        
        # Create message key
        key = MessageKey(
            remote_jid=self._to,
            from_me=True,
            id=generate_message_id(),
        )
        
        # Create context if needed
        context = None
        if self._quoted_message or self._mentions:
            context = MessageContext(
                quoted_message_id=self._quoted_message.key.id if self._quoted_message else None,
                quoted_participant=self._quoted_message.sender_jid if self._quoted_message else None,
                mentioned_jids=self._mentions,
            )
        
        # Build appropriate message type
        if self._media_type == "image":
            return ImageMessage(
                key=key,
                context=context,
                caption=self._caption,
                _local_path=self._media_path,
                _local_data=self._media_data,
            )
        
        elif self._media_type == "video":
            return VideoMessage(
                key=key,
                context=context,
                caption=self._caption,
                gif_playback=self._gif_playback,
                _local_path=self._media_path,
                _local_data=self._media_data,
            )
        
        elif self._media_type == "audio":
            return AudioMessage(
                key=key,
                context=context,
                ptt=self._ptt,
                _local_path=self._media_path,
                _local_data=self._media_data,
            )
        
        elif self._media_type == "document":
            return DocumentMessage(
                key=key,
                context=context,
                caption=self._caption,
                filename=self._filename,
                mimetype=self._mimetype,
                _local_path=self._media_path,
                _local_data=self._media_data,
            )
        
        elif self._media_type == "sticker":
            return StickerMessage(
                key=key,
                context=context,
                _local_path=self._media_path,
                _local_data=self._media_data,
            )
        
        elif self._media_type == "location":
            lat, lon = self._location or (0.0, 0.0)
            return LocationMessage(
                key=key,
                context=context,
                latitude=lat,
                longitude=lon,
                name=self._location_name,
            )
        
        elif self._media_type == "contact":
            return ContactMessage(
                key=key,
                context=context,
                display_name=self._contact_name or "",
                vcard=self._contact_vcard or "",
            )
        
        elif self._media_type == "reaction":
            if not self._reaction_key:
                raise ValueError("Reaction target is required")
            return ReactionMessage(
                key=key,
                react_key=self._reaction_key,
                emoji=self._reaction_emoji or "",
            )
        
        elif self._media_type == "poll":
            options = [PollOption(name=opt) for opt in self._poll_options]
            return PollMessage(
                key=key,
                context=context,
                name=self._poll_name or "",
                options=options,
                selectable_count=self._poll_selectable,
            )
        
        else:
            # Default to text message
            if not self._text:
                raise ValueError("Text content is required for text messages")
            return TextMessage(
                key=key,
                context=context,
                text=self._text,
            )

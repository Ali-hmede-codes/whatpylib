"""
Main WhatsApp client class.

The WhatsAppClient provides a high-level API for interacting with WhatsApp.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional, Union, List

from whatpylib.config import Config, ConnectionState
from whatpylib.connection.socket import WhatsAppSocket
from whatpylib.connection.binary import BinaryNode
from whatpylib.auth.state import AuthState, FileAuthState, MemoryAuthState
from whatpylib.auth.qr import QRCodeHandler, QRData
from whatpylib.events.emitter import EventEmitter
from whatpylib.messages.types import (
    Message,
    TextMessage,
    MessageKey,
    create_text_message,
    create_reaction,
    generate_message_id,
)
from whatpylib.messages.builder import MessageBuilder
from whatpylib.utils.jid import parse_jid, JID
from whatpylib.utils.logger import get_logger, setup_logging
from whatpylib.utils.rate_limit import RateLimiter

logger = get_logger("client")


EventHandler = Callable[..., Coroutine[Any, Any, None]]


class WhatsAppClient:
    """
    Main WhatsApp client for sending and receiving messages.
    
    This is the primary interface for interacting with WhatsApp. It handles:
    - Connection management
    - Authentication (QR code or pairing code)
    - Sending/receiving messages
    - Event handling
    
    Example:
        >>> from whatpylib import WhatsAppClient
        >>> 
        >>> async def main():
        ...     client = WhatsAppClient(auth_state_path="./auth")
        ...     
        ...     @client.on("message")
        ...     async def on_message(msg):
        ...         print(f"Received: {msg}")
        ...         if msg.text == "ping":
        ...             await client.send_message(msg.chat_jid, "pong!")
        ...     
        ...     await client.connect()
        ...     await client.wait_until_disconnect()
    """
    
    def __init__(
        self,
        auth_state: Optional[AuthState] = None,
        auth_state_path: Optional[str] = None,
        config: Optional[Config] = None,
        print_qr: bool = True,
        log_level: str = "INFO",
    ) -> None:
        """
        Initialize the WhatsApp client.
        
        Args:
            auth_state: Custom auth state implementation
            auth_state_path: Path for file-based auth state (creates FileAuthState)
            config: Client configuration
            print_qr: Whether to print QR code to terminal
            log_level: Logging level
        """
        # Setup logging
        setup_logging(level=log_level)
        
        # Configuration
        self.config = config or Config()
        self.config.print_qr_terminal = print_qr
        
        # Auth state
        if auth_state:
            self.auth_state = auth_state
        elif auth_state_path:
            self.auth_state = FileAuthState(auth_state_path)
        else:
            self.auth_state = MemoryAuthState()
        
        # Event emitter
        self.events = EventEmitter()
        
        # Internal state
        self._socket: Optional[WhatsAppSocket] = None
        self._qr_handler = QRCodeHandler(print_terminal=print_qr)
        self._rate_limiter = RateLimiter(rate=60, period=60)
        self._message_handlers: List[Callable] = []
        self._disconnect_event = asyncio.Event()
        self._me: Optional[dict] = None
    
    # ==================== Connection ====================
    
    async def connect(self) -> None:
        """
        Connect to WhatsApp.
        
        This will:
        1. Load existing auth state if available
        2. Connect to WebSocket
        3. Perform authentication (QR code if needed)
        4. Start message handling
        """
        logger.info("Connecting to WhatsApp...")
        
        # Load auth state
        has_auth = await self.auth_state.load()
        if has_auth:
            logger.info("Loaded existing auth state")
        
        # Create socket
        self._socket = WhatsAppSocket(
            config=self.config,
            events=self.events,
        )
        
        # Setup event handlers
        self._setup_internal_handlers()
        
        # Connect
        await self._socket.connect()
        
        # Authenticate if needed
        if not self.auth_state.is_authenticated:
            await self._authenticate()
        else:
            # Restore session
            await self._restore_session()
    
    async def disconnect(self) -> None:
        """Disconnect from WhatsApp."""
        if self._socket:
            await self._socket.close()
            self._socket = None
        
        self._disconnect_event.set()
        logger.info("Disconnected from WhatsApp")
    
    async def wait_until_disconnect(self) -> None:
        """Wait until the client disconnects."""
        await self._disconnect_event.wait()
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to WhatsApp."""
        return self._socket is not None and self._socket.is_connected
    
    @property
    def me(self) -> Optional[dict]:
        """Get current user info."""
        return self._me or self.auth_state.session.me
    
    # ==================== Authentication ====================
    
    async def _authenticate(self) -> None:
        """Perform authentication (QR code flow)."""
        logger.info("Starting authentication...")
        
        # Request QR code
        # This is a placeholder - actual implementation depends on
        # the exact server response format
        
        # Wait for QR scan or pairing
        await self.events.wait_for(
            "auth.success",
            timeout=self.config.qr_timeout,
        )
        
        # Save auth state
        await self.auth_state.save()
        logger.info("Authentication successful")
    
    async def _restore_session(self) -> None:
        """Restore existing session."""
        logger.info("Restoring session...")
        
        # Send session restore message
        # This is a placeholder for the actual protocol
        
        self._me = self.auth_state.session.me
        await self.events.emit("connection.update", {"connection": "open"})
    
    async def logout(self) -> None:
        """Logout and clear auth state."""
        # Send logout message
        if self._socket and self._socket.is_connected:
            await self._socket.send_node(BinaryNode(
                tag="iq",
                attrs={"type": "set", "xmlns": "w:sync"},
                content=None,
            ))
        
        # Clear auth state
        await self.auth_state.clear()
        
        # Disconnect
        await self.disconnect()
        
        logger.info("Logged out")
    
    # ==================== Event Handling ====================
    
    def _setup_internal_handlers(self) -> None:
        """Setup internal event handlers."""
        self.events.on("connection.update", self._on_connection_update)
        self.events.on("message", self._on_message_node)
        self.events.on("notification", self._on_notification)
    
    async def _on_connection_update(self, update: dict) -> None:
        """Handle connection state updates."""
        connection = update.get("connection")
        if connection == ConnectionState.DISCONNECTED:
            self._disconnect_event.set()
    
    async def _on_message_node(self, node: BinaryNode) -> None:
        """Handle incoming message nodes."""
        # Parse message from node
        # This is a placeholder - actual parsing depends on
        # the protobuf message format
        pass
    
    async def _on_notification(self, node: BinaryNode) -> None:
        """Handle notification nodes."""
        pass
    
    def on(
        self,
        event: str,
        handler: Optional[EventHandler] = None,
    ) -> Union[EventHandler, Callable[[EventHandler], EventHandler]]:
        """
        Register an event handler.
        
        Can be used as a decorator or called directly:
        
            @client.on("message")
            async def handler(msg):
                ...
        
        Supported events:
        - "message": New message received
        - "message.update": Message updated
        - "message.delete": Message deleted
        - "message.reaction": Reaction added/removed
        - "group.update": Group info updated
        - "group.participants.update": Group members changed
        - "presence.update": User presence changed
        - "connection.update": Connection state changed
        - "call": Incoming call
        
        Args:
            event: Event name
            handler: Optional handler function
            
        Returns:
            Handler (for decorator use)
        """
        return self.events.on(event, handler)
    
    def once(
        self,
        event: str,
        handler: Optional[EventHandler] = None,
    ) -> Union[EventHandler, Callable[[EventHandler], EventHandler]]:
        """Register a one-time event handler."""
        return self.events.once(event, handler)
    
    def off(self, event: str, handler: EventHandler) -> bool:
        """Remove an event handler."""
        return self.events.off(event, handler)
    
    # ==================== Messaging ====================
    
    async def send_message(
        self,
        to: str,
        content: Union[str, Message],
        **kwargs: Any,
    ) -> MessageKey:
        """
        Send a message.
        
        Args:
            to: Recipient JID or phone number
            content: Message text or Message object
            **kwargs: Additional message options
            
        Returns:
            Message key of sent message
        """
        # Normalize JID
        if "@" not in to:
            to = f"{to}@s.whatsapp.net"
        
        # Create message
        if isinstance(content, str):
            message = create_text_message(to, content)
        else:
            message = content
        
        # Rate limit
        await self._rate_limiter.acquire()
        
        # Send message
        await self._send_message_internal(message)
        
        logger.info(f"Sent message to {to}")
        return message.key
    
    async def _send_message_internal(self, message: Message) -> None:
        """Internal message sending."""
        if not self._socket:
            raise RuntimeError("Not connected")
        
        # Build message node
        node = self._build_message_node(message)
        
        # Send
        await self._socket.send_node(node)
    
    def _build_message_node(self, message: Message) -> BinaryNode:
        """Build a binary node from a message."""
        # This is a simplified version - actual implementation
        # would use protobuf encoding
        
        attrs = {
            "to": message.key.remote_jid,
            "id": message.key.id,
            "type": "text",
        }
        
        content = None
        if isinstance(message, TextMessage):
            content = message.text.encode("utf-8")
        
        return BinaryNode(
            tag="message",
            attrs=attrs,
            content=content,
        )
    
    async def reply(
        self,
        message: Message,
        content: str,
    ) -> MessageKey:
        """
        Reply to a message.
        
        Args:
            message: Message to reply to
            content: Reply text
            
        Returns:
            Message key of sent reply
        """
        reply_msg = (
            MessageBuilder()
            .to(message.chat_jid)
            .text(content)
            .reply_to(message)
            .build()
        )
        return await self.send_message(message.chat_jid, reply_msg)
    
    async def react(
        self,
        message: Message,
        emoji: str,
    ) -> MessageKey:
        """
        React to a message.
        
        Args:
            message: Message to react to
            emoji: Reaction emoji (empty string to remove)
            
        Returns:
            Message key of reaction
        """
        reaction = create_reaction(message, emoji)
        return await self.send_message(message.chat_jid, reaction)
    
    async def forward_message(
        self,
        message: Message,
        to: str,
    ) -> MessageKey:
        """
        Forward a message.
        
        Args:
            message: Message to forward
            to: Recipient JID
            
        Returns:
            Message key of forwarded message
        """
        # Create forwarded message
        # Implementation depends on message type
        raise NotImplementedError("Message forwarding not yet implemented")
    
    async def delete_message(
        self,
        message: Message,
        for_everyone: bool = False,
    ) -> None:
        """
        Delete a message.
        
        Args:
            message: Message to delete
            for_everyone: Delete for all participants
        """
        raise NotImplementedError("Message deletion not yet implemented")
    
    async def edit_message(
        self,
        message: Message,
        new_text: str,
    ) -> MessageKey:
        """
        Edit a sent message.
        
        Args:
            message: Message to edit
            new_text: New message text
            
        Returns:
            Message key
        """
        raise NotImplementedError("Message editing not yet implemented")
    
    # ==================== Media ====================
    
    async def send_image(
        self,
        to: str,
        image: Union[str, bytes],
        caption: Optional[str] = None,
    ) -> MessageKey:
        """
        Send an image.
        
        Args:
            to: Recipient JID
            image: Image path or bytes
            caption: Optional caption
            
        Returns:
            Message key
        """
        builder = MessageBuilder().to(to)
        if isinstance(image, str):
            builder.image(path=image, caption=caption)
        else:
            builder.image(data=image, caption=caption)
        return await self.send_message(to, builder.build())
    
    async def send_video(
        self,
        to: str,
        video: Union[str, bytes],
        caption: Optional[str] = None,
    ) -> MessageKey:
        """
        Send a video.
        
        Args:
            to: Recipient JID
            video: Video path or bytes
            caption: Optional caption
            
        Returns:
            Message key
        """
        builder = MessageBuilder().to(to)
        if isinstance(video, str):
            builder.video(path=video, caption=caption)
        else:
            builder.video(data=video, caption=caption)
        return await self.send_message(to, builder.build())
    
    async def send_audio(
        self,
        to: str,
        audio: Union[str, bytes],
        ptt: bool = False,
    ) -> MessageKey:
        """
        Send audio.
        
        Args:
            to: Recipient JID
            audio: Audio path or bytes
            ptt: Send as voice note
            
        Returns:
            Message key
        """
        builder = MessageBuilder().to(to)
        if isinstance(audio, str):
            builder.audio(path=audio, ptt=ptt)
        else:
            builder.audio(data=audio, ptt=ptt)
        return await self.send_message(to, builder.build())
    
    async def send_document(
        self,
        to: str,
        document: Union[str, bytes],
        filename: Optional[str] = None,
        caption: Optional[str] = None,
    ) -> MessageKey:
        """
        Send a document.
        
        Args:
            to: Recipient JID
            document: Document path or bytes
            filename: Filename to display
            caption: Optional caption
            
        Returns:
            Message key
        """
        builder = MessageBuilder().to(to)
        if isinstance(document, str):
            builder.document(path=document, filename=filename, caption=caption)
        else:
            builder.document(data=document, filename=filename, caption=caption)
        return await self.send_message(to, builder.build())
    
    async def send_location(
        self,
        to: str,
        latitude: float,
        longitude: float,
        name: Optional[str] = None,
    ) -> MessageKey:
        """
        Send a location.
        
        Args:
            to: Recipient JID
            latitude: Latitude
            longitude: Longitude
            name: Location name
            
        Returns:
            Message key
        """
        msg = (
            MessageBuilder()
            .to(to)
            .location(latitude, longitude, name=name)
            .build()
        )
        return await self.send_message(to, msg)
    
    async def send_poll(
        self,
        to: str,
        question: str,
        options: List[str],
        selectable_count: int = 0,
    ) -> MessageKey:
        """
        Send a poll.
        
        Args:
            to: Recipient JID
            question: Poll question
            options: List of options
            selectable_count: Max selections (0 = unlimited)
            
        Returns:
            Message key
        """
        msg = (
            MessageBuilder()
            .to(to)
            .poll(question, options, selectable_count)
            .build()
        )
        return await self.send_message(to, msg)
    
    # ==================== Presence ====================
    
    async def update_presence(self, presence: str) -> None:
        """
        Update presence state.
        
        Args:
            presence: "available", "unavailable", "composing", "recording"
        """
        if not self._socket:
            raise RuntimeError("Not connected")
        
        await self._socket.send_node(BinaryNode(
            tag="presence",
            attrs={"type": presence},
        ))
    
    async def send_typing(self, to: str) -> None:
        """
        Send typing indicator.
        
        Args:
            to: Chat JID
        """
        if not self._socket:
            raise RuntimeError("Not connected")
        
        await self._socket.send_node(BinaryNode(
            tag="chatstate",
            attrs={"to": to},
            content=[BinaryNode(tag="composing", attrs={})],
        ))
    
    async def send_recording(self, to: str) -> None:
        """
        Send recording indicator.
        
        Args:
            to: Chat JID
        """
        if not self._socket:
            raise RuntimeError("Not connected")
        
        await self._socket.send_node(BinaryNode(
            tag="chatstate",
            attrs={"to": to},
            content=[BinaryNode(tag="recording", attrs={})],
        ))
    
    # ==================== Contacts & Profile ====================
    
    async def get_profile_picture(
        self,
        jid: str,
        high_res: bool = False,
    ) -> Optional[str]:
        """
        Get profile picture URL.
        
        Args:
            jid: User or group JID
            high_res: Get high resolution image
            
        Returns:
            Picture URL or None
        """
        raise NotImplementedError("Profile picture fetch not yet implemented")
    
    async def get_status(self, jid: str) -> Optional[str]:
        """
        Get user's status/about text.
        
        Args:
            jid: User JID
            
        Returns:
            Status text or None
        """
        raise NotImplementedError("Status fetch not yet implemented")
    
    # ==================== Groups ====================
    
    async def get_group_metadata(self, group_jid: str) -> dict:
        """
        Get group metadata.
        
        Args:
            group_jid: Group JID
            
        Returns:
            Group metadata
        """
        raise NotImplementedError("Group metadata not yet implemented")
    
    async def create_group(
        self,
        name: str,
        participants: List[str],
    ) -> str:
        """
        Create a new group.
        
        Args:
            name: Group name
            participants: List of participant JIDs
            
        Returns:
            Group JID
        """
        raise NotImplementedError("Group creation not yet implemented")
    
    async def update_group_subject(
        self,
        group_jid: str,
        subject: str,
    ) -> None:
        """
        Update group subject/name.
        
        Args:
            group_jid: Group JID
            subject: New subject
        """
        raise NotImplementedError("Group subject update not yet implemented")
    
    async def update_group_description(
        self,
        group_jid: str,
        description: str,
    ) -> None:
        """
        Update group description.
        
        Args:
            group_jid: Group JID
            description: New description
        """
        raise NotImplementedError("Group description update not yet implemented")
    
    async def add_group_participants(
        self,
        group_jid: str,
        participants: List[str],
    ) -> None:
        """
        Add participants to group.
        
        Args:
            group_jid: Group JID
            participants: JIDs to add
        """
        raise NotImplementedError("Add participants not yet implemented")
    
    async def remove_group_participants(
        self,
        group_jid: str,
        participants: List[str],
    ) -> None:
        """
        Remove participants from group.
        
        Args:
            group_jid: Group JID
            participants: JIDs to remove
        """
        raise NotImplementedError("Remove participants not yet implemented")
    
    async def promote_group_participants(
        self,
        group_jid: str,
        participants: List[str],
    ) -> None:
        """
        Promote participants to admin.
        
        Args:
            group_jid: Group JID
            participants: JIDs to promote
        """
        raise NotImplementedError("Promote participants not yet implemented")
    
    async def demote_group_participants(
        self,
        group_jid: str,
        participants: List[str],
    ) -> None:
        """
        Demote participants from admin.
        
        Args:
            group_jid: Group JID
            participants: JIDs to demote
        """
        raise NotImplementedError("Demote participants not yet implemented")
    
    async def leave_group(self, group_jid: str) -> None:
        """
        Leave a group.
        
        Args:
            group_jid: Group JID
        """
        raise NotImplementedError("Leave group not yet implemented")
    
    async def get_group_invite_link(self, group_jid: str) -> str:
        """
        Get group invite link.
        
        Args:
            group_jid: Group JID
            
        Returns:
            Invite link URL
        """
        raise NotImplementedError("Group invite link not yet implemented")
    
    async def revoke_group_invite_link(self, group_jid: str) -> str:
        """
        Revoke and get new group invite link.
        
        Args:
            group_jid: Group JID
            
        Returns:
            New invite link URL
        """
        raise NotImplementedError("Revoke invite link not yet implemented")
    
    # ==================== Context Manager ====================
    
    async def __aenter__(self) -> "WhatsAppClient":
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()


# Convenience function
async def create_client(
    auth_state_path: Optional[str] = None,
    **kwargs: Any,
) -> WhatsAppClient:
    """
    Create and connect a WhatsApp client.
    
    Args:
        auth_state_path: Path for auth state storage
        **kwargs: Additional client options
        
    Returns:
        Connected WhatsAppClient
    """
    client = WhatsAppClient(auth_state_path=auth_state_path, **kwargs)
    await client.connect()
    return client

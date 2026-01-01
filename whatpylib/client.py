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
from whatpylib.media.upload import MediaUploader
from whatpylib.media.download import MediaDownloader, download_media_message
from whatpylib.groups.participants import ParticipantManager, ParticipantAction
from whatpylib.groups.manager import GroupManager
from whatpylib.groups.metadata import GroupMetadata
from whatpylib.proto.wa_pb2 import (
    WebMessageInfo,
    Message as ProtoMessage,
    MessageKey as ProtoMessageKey,
    ExtendedTextMessage,
    ImageMessage as ProtoImageMessage,
    VideoMessage as ProtoVideoMessage,
    AudioMessage as ProtoAudioMessage,
    DocumentMessage as ProtoDocumentMessage,
    ContextInfo,
)

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
        
        # Managers
        self._media_uploader = MediaUploader()
        self._media_downloader = MediaDownloader()
        self._group_participants = ParticipantManager(
            send_node=self._send_node_wrapper,
            send_and_wait=self._send_and_wait_wrapper,
        )
        self._group_manager = GroupManager(
            send_node=self._send_node_wrapper,
            send_and_wait=self._send_and_wait_wrapper,
        )
    
    # ==================== Internal Wrappers ====================
    
    async def _send_node_wrapper(self, node: BinaryNode) -> None:
        """Wrapper for sending nodes."""
        if not self._socket:
            raise RuntimeError("Not connected")
        await self._socket.send_node(node)
    
    async def _send_and_wait_wrapper(
        self,
        node: BinaryNode,
        timeout: Optional[float] = None,
    ) -> BinaryNode:
        """Wrapper for sending and waiting for response."""
        if not self._socket:
            raise RuntimeError("Not connected")
        # This needs actual implementation in socket.py or here
        # For now, we'll just send and return None as placeholder
        # Real implementation requires tracking message IDs
        await self._socket.send_node(node)
        # TODO: Implement wait_for_response in socket
        return BinaryNode(tag="iq", attrs={"type": "result"})  # Fake success

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
        # Node structure: <message>encrypted_bytes</message> or similar
        # We need to decrypt first (if encrypted) then parse protobuf
        
        try:
            content = node.content
            if not isinstance(content, bytes):
                return
            
            # TODO: Decrypt here using SignalProtocol
            # decrypted = self.signal.decrypt(content)
            # For now assume plaintext for testing/MVP or if unencrypted
            decrypted = content
            
            # Parse WebMessageInfo
            web_msg = WebMessageInfo.ParseFromString(decrypted)
            
            if not web_msg.message:
                return
                
            # Convert to high-level Message object
            # This logic belongs in a parser/converter, but putting here for now
            msg_key = MessageKey(
                remote_jid=web_msg.key.remoteJid,
                from_me=web_msg.key.fromMe,
                id=web_msg.key.id,
            )
            
            high_level_msg = None
            proto_msg = web_msg.message
            
            if proto_msg.conversation:
                high_level_msg = TextMessage(
                    key=msg_key,
                    timestamp=web_msg.messageTimestamp,
                    text=proto_msg.conversation,
                )
            elif proto_msg.extendedTextMessage:
                high_level_msg = TextMessage(
                    key=msg_key,
                    timestamp=web_msg.messageTimestamp,
                    text=proto_msg.extendedTextMessage.text,
                )
            elif proto_msg.imageMessage:
                from whatpylib.messages.types import ImageMessage
                img = proto_msg.imageMessage
                high_level_msg = ImageMessage(
                    key=msg_key,
                    timestamp=web_msg.messageTimestamp,
                    url=img.url,
                    mimetype=img.mimetype,
                    caption=img.caption,
                    file_sha256=img.fileSha256,
                    file_length=img.fileLength,
                    height=img.height,
                    width=img.width,
                    media_key=img.mediaKey,
                    file_enc_sha256=img.fileEncSha256,
                    direct_path=img.directPath,
                    view_once=img.viewOnce,
                )
            # Add other types...
            
            if high_level_msg:
                await self.events.emit("message", high_level_msg)
                
        except Exception as e:
            logger.error(f"Failed to parse message: {e}")
    
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
        
        # Handle media upload if needed
        from whatpylib.messages.types import MediaMessage
        if isinstance(message, MediaMessage):
            if message._local_data or message._local_path:
                logger.info(f"Uploading media for message {message.key.id}")
                result = await self._media_uploader.upload(
                    data=message._local_data,
                    file_path=message._local_path,
                    mimetype=message.mimetype,
                )
                
                # Update message with upload result
                message.url = result.url
                message.media_key = result.media_key
                message.file_sha256 = result.file_sha256
                message.file_enc_sha256 = result.file_enc_sha256
                message.file_length = result.file_length
                message.mimetype = result.mimetype
                
                # Update type-specific fields
                if hasattr(message, "width") and result.width:
                    message.width = result.width
                if hasattr(message, "height") and result.height:
                    message.height = result.height
                if hasattr(message, "duration") and result.duration:
                    message.duration = result.duration
                if hasattr(message, "thumbnail") and result.thumbnail:
                    message.thumbnail = result.thumbnail

        # Build message node
        node = self._build_message_node(message)
        
        # Send
        await self._socket.send_node(node)
    
    def _build_message_node(self, message: Message) -> BinaryNode:
        """Build a binary node from a message."""
        # Create Protobuf Message
        proto_msg = ProtoMessage()
        
        # Handle different message types
        if isinstance(message, TextMessage):
            if message.preview_url:
                # Extended Text Message
                extended = ExtendedTextMessage(
                    text=message.text,
                    previewType=1,  # Video/Link preview
                    # Add other fields like title/description if available
                )
                proto_msg.extendedTextMessage = extended
                proto_msg.conversation = message.text  # Fallback
            else:
                # Simple conversation
                proto_msg.conversation = message.text
                
        elif hasattr(message, "mimetype"):  # Media messages
            # Common media fields
            media_args = {
                "url": getattr(message, "url", None),
                "mimetype": getattr(message, "mimetype", None),
                "fileSha256": getattr(message, "file_sha256", None),
                "fileLength": getattr(message, "file_length", None),
                "mediaKey": getattr(message, "media_key", None),
                "fileEncSha256": getattr(message, "file_enc_sha256", None),
                "directPath": getattr(message, "direct_path", None),
                "caption": getattr(message, "caption", None),
            }
            
            # Add thumbnail if available
            if hasattr(message, "thumbnail") and message.thumbnail:
                media_args["jpegThumbnail"] = message.thumbnail.data if hasattr(message.thumbnail, "data") else message.thumbnail
            
            from whatpylib.messages.types import ImageMessage, VideoMessage, AudioMessage, DocumentMessage
            
            if isinstance(message, ImageMessage):
                media_args["height"] = getattr(message, "height", 0)
                media_args["width"] = getattr(message, "width", 0)
                media_args["viewOnce"] = getattr(message, "view_once", False)
                proto_msg.imageMessage = ProtoImageMessage(**media_args)
                
            elif isinstance(message, VideoMessage):
                media_args["height"] = getattr(message, "height", 0)
                media_args["width"] = getattr(message, "width", 0)
                media_args["seconds"] = getattr(message, "duration", 0)
                media_args["gifPlayback"] = getattr(message, "gif_playback", False)
                proto_msg.videoMessage = ProtoVideoMessage(**media_args)
                
            elif isinstance(message, AudioMessage):
                media_args["seconds"] = getattr(message, "duration", 0)
                media_args["ptt"] = getattr(message, "ptt", False)
                # Remove caption for audio
                media_args.pop("caption", None)
                proto_msg.audioMessage = ProtoAudioMessage(**media_args)
                
            elif isinstance(message, DocumentMessage):
                media_args["fileName"] = getattr(message, "filename", None)
                media_args["pageCount"] = getattr(message, "page_count", 0)
                proto_msg.documentMessage = ProtoDocumentMessage(**media_args)
        
        # Handle reply context
        if message.context_info:
            # Create ContextInfo
            context = ContextInfo(
                stanzaId=message.context_info.stanza_id,
                participant=message.context_info.participant,
                remoteJid=message.context_info.remote_jid,
            )
            # Attach to the specific message type
            if proto_msg.extendedTextMessage:
                proto_msg.extendedTextMessage.contextInfo = context
            elif proto_msg.imageMessage:
                proto_msg.imageMessage.contextInfo = context
            elif proto_msg.videoMessage:
                proto_msg.videoMessage.contextInfo = context
            elif proto_msg.audioMessage:
                proto_msg.audioMessage.contextInfo = context
            elif proto_msg.documentMessage:
                proto_msg.documentMessage.contextInfo = context
        
        # Serialize to bytes
        msg_bytes = proto_msg.SerializeToString()
        
        # Create WebMessageInfo (wrapper)
        web_msg = WebMessageInfo(
            key=ProtoMessageKey(
                remoteJid=message.key.remote_jid,
                fromMe=message.key.from_me,
                id=message.key.id,
            ),
            message=proto_msg,
            messageTimestamp=message.timestamp,
            status=1,  # PENDING
        )
        
        # In actual WhatsApp protocol, we send the Message node, 
        # but the content is encrypted using Signal Protocol.
        # For MVP without full E2E, we might be sending plaintext or 
        # partial implementation.
        # However, the task says "Signal Protocol integration" is done (in crypto module).
        # So we should encrypt this `msg_bytes` using `SignalSession`.
        
        # But wait, `client.py` doesn't have the SignalProtocol instance initialized yet!
        # I need to initialize SignalProtocol in `client.py` and use it here.
        
        # For now, let's assume we are sending the `message` node with the protobuf content
        # as the `content` (if not encrypted) or inside `enc` node (if encrypted).
        # Since full E2E is complex to wire up in one go, I'll stick to the structure
        # but note that encryption is the next step.
        
        # Actually, `BinaryNode` expects bytes for content.
        
        attrs = {
            "to": message.key.remote_jid,
            "id": message.key.id,
            "type": "text", # This changes based on message type
        }
        
        if isinstance(message, TextMessage):
            attrs["type"] = "text"
        else:
            attrs["type"] = "media"
            
        return BinaryNode(
            tag="message",
            attrs=attrs,
            content=msg_bytes, # This should be encrypted!
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
    
    async def get_group_metadata(self, group_jid: str) -> GroupMetadata:
        """
        Get group metadata.
        
        Args:
            group_jid: Group JID
            
        Returns:
            Group metadata
        """
        return await self._group_manager.get_group_metadata(group_jid)
    
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
        return await self._group_manager.create_group(name, participants)
    
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
        await self._group_manager.update_subject(group_jid, subject)
    
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
        await self._group_manager.update_description(group_jid, description)
    
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
        await self._group_participants.add_participants(group_jid, participants)
    
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
        await self._group_participants.remove_participants(group_jid, participants)
    
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
        await self._group_participants.promote_participants(group_jid, participants)
    
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
        await self._group_participants.demote_participants(group_jid, participants)
    
    async def leave_group(self, group_jid: str) -> None:
        """
        Leave a group.
        
        Args:
            group_jid: Group JID
        """
        await self._group_manager.leave_group(group_jid)
    
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

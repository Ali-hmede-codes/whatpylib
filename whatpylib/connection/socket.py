"""
WebSocket client for WhatsApp connection.

Handles WebSocket connection, reconnection, keepalive, and message framing.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional
import random

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
    from websockets.exceptions import ConnectionClosed
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False
    WebSocketClientProtocol = Any  # type: ignore

from whatpylib.config import (
    WA_WEB_SOCKET_URL,
    WA_WEB_ORIGIN,
    Config,
    ConnectionState,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_KEEPALIVE_INTERVAL,
)
from whatpylib.connection.noise import NoiseHandler, NoiseState
from whatpylib.connection.binary import (
    BinaryNode,
    BinaryEncoder,
    BinaryDecoder,
    encode_frame,
    decode_frame,
    FrameType,
)
from whatpylib.events.emitter import EventEmitter
from whatpylib.utils.logger import get_logger
from whatpylib.utils.retry import retry

logger = get_logger("socket")


MessageCallback = Callable[[BinaryNode], Coroutine[Any, Any, None]]


@dataclass
class WhatsAppSocket:
    """
    WebSocket client for WhatsApp communication.
    
    Handles:
    - WebSocket connection management
    - Noise protocol handshake
    - Binary message encoding/decoding
    - Automatic reconnection
    - Keepalive heartbeats
    
    Attributes:
        config: Client configuration
        events: Event emitter for connection events
    """
    config: Config = field(default_factory=Config)
    events: EventEmitter = field(default_factory=EventEmitter)
    
    _ws: Optional[WebSocketClientProtocol] = field(default=None, init=False)
    _noise: NoiseHandler = field(default_factory=NoiseHandler, init=False)
    _state: str = field(default=ConnectionState.DISCONNECTED, init=False)
    _reconnect_count: int = field(default=0, init=False)
    _keepalive_task: Optional[asyncio.Task] = field(default=None, init=False)
    _receive_task: Optional[asyncio.Task] = field(default=None, init=False)
    _message_queue: asyncio.Queue = field(default_factory=asyncio.Queue, init=False)
    _pending_requests: dict[str, asyncio.Future] = field(default_factory=dict, init=False)
    _closed: bool = field(default=False, init=False)
    
    def __post_init__(self) -> None:
        if not HAS_WEBSOCKETS:
            raise ImportError(
                "websockets package required. Install with: pip install websockets"
            )
    
    @property
    def state(self) -> str:
        """Get current connection state."""
        return self._state
    
    @property
    def is_connected(self) -> bool:
        """Check if connected and handshake complete."""
        return (
            self._state == ConnectionState.CONNECTED and
            self._ws is not None and
            self._noise.is_established
        )
    
    async def _set_state(self, new_state: str) -> None:
        """Update connection state and emit event."""
        old_state = self._state
        self._state = new_state
        logger.info(f"Connection state: {old_state} -> {new_state}")
        await self.events.emit("connection.update", {
            "connection": new_state,
            "lastDisconnect": old_state if new_state == ConnectionState.DISCONNECTED else None,
        })
    
    async def connect(self) -> None:
        """
        Connect to WhatsApp WebSocket server.
        
        Performs:
        1. WebSocket connection
        2. Noise XX handshake
        3. Starts keepalive and receive loops
        """
        if self._state not in (ConnectionState.DISCONNECTED, ConnectionState.RECONNECTING):
            logger.warning(f"Cannot connect in state: {self._state}")
            return
        
        await self._set_state(ConnectionState.CONNECTING)
        
        try:
            # Connect to WebSocket
            logger.info(f"Connecting to {WA_WEB_SOCKET_URL}")
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    WA_WEB_SOCKET_URL,
                    origin=WA_WEB_ORIGIN,
                    subprotocols=["chat"],
                    max_size=16 * 1024 * 1024,  # 16MB max message
                    ping_interval=None,  # We handle keepalive ourselves
                    close_timeout=5,
                ),
                timeout=self.config.connect_timeout,
            )
            
            # Perform Noise handshake
            try:
                await self._perform_handshake()
            except ValueError as e:
                if "Handshake 2 message too short" in str(e):
                    logger.error("Handshake failed: Message too short. This usually means the WhatsApp Web version is outdated or the protocol has changed.")
                raise e
            
            # Reset reconnect count on success
            self._reconnect_count = 0
            
            # Start background tasks
            self._start_background_tasks()
            
            await self._set_state(ConnectionState.CONNECTED)
            
        except asyncio.TimeoutError:
            logger.error("Connection timeout")
            await self._set_state(ConnectionState.DISCONNECTED)
            raise ConnectionError("Connection timeout")
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            await self._set_state(ConnectionState.DISCONNECTED)
            raise
    
    async def _perform_handshake(self) -> None:
        """Perform Noise XX handshake."""
        if not self._ws:
            raise RuntimeError("Not connected")
        
        logger.debug("Starting Noise handshake")
        
        # Initialize new Noise handler
        self._noise = NoiseHandler()
        
        # Send handshake message 1 (-> e)
        msg1 = self._noise.create_handshake_message_1()
        await self._ws.send(msg1)
        logger.debug("Sent handshake message 1")
        
        # Receive handshake message 2 (<- e, ee, s, es)
        response = await self._ws.recv()
        if isinstance(response, str):
            response = response.encode("utf-8")
        
        payload = self._noise.process_handshake_message_2(response)
        logger.debug(f"Received handshake message 2, payload: {len(payload)} bytes")
        
        # Send handshake message 3 (-> s, se, payload)
        # Include client hello in the payload
        client_payload = self._create_client_payload()
        msg3 = self._noise.create_handshake_message_3(client_payload)
        await self._ws.send(msg3)
        logger.debug("Sent handshake message 3")
        
        logger.info("Noise handshake complete")
    
    def _create_client_payload(self) -> bytes:
        """Create client hello payload for handshake."""
        # Build client hello node
        node = BinaryNode(
            tag="client_hello",
            attrs={"type": "init"},
            content=None,
        )
        encoder = BinaryEncoder()
        return encoder.encode_node(node)
    
    def _start_background_tasks(self) -> None:
        """Start keepalive and receive tasks."""
        # Start keepalive
        if self._keepalive_task:
            self._keepalive_task.cancel()
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        
        # Start receive loop
        if self._receive_task:
            self._receive_task.cancel()
        self._receive_task = asyncio.create_task(self._receive_loop())
    
    async def _keepalive_loop(self) -> None:
        """Send periodic keepalive pings."""
        interval = self.config.keepalive_interval
        logger.debug(f"Starting keepalive loop (interval: {interval}s)")
        
        while not self._closed and self._ws:
            try:
                await asyncio.sleep(interval)
                
                if self._ws and self.is_connected:
                    # Send ping
                    ping_node = BinaryNode(
                        tag="iq",
                        attrs={"type": "get", "xmlns": "w:ping"},
                        content=None,
                    )
                    await self.send_node(ping_node)
                    logger.debug("Sent keepalive ping")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Keepalive error: {e}")
    
    async def _receive_loop(self) -> None:
        """Receive and process incoming messages."""
        logger.debug("Starting receive loop")
        
        while not self._closed and self._ws:
            try:
                message = await self._ws.recv()
                
                if isinstance(message, str):
                    message = message.encode("utf-8")
                
                # Decrypt with Noise
                decrypted = self._noise.decrypt(message)
                
                # Decode frame
                frame_type, payload = decode_frame(decrypted)
                
                if frame_type == FrameType.BINARY:
                    # Decode binary node
                    decoder = BinaryDecoder(payload)
                    node = decoder.decode_node()
                    
                    # Handle pending request
                    msg_id = node.get_attr("id")
                    if msg_id and msg_id in self._pending_requests:
                        future = self._pending_requests.pop(msg_id)
                        if not future.done():
                            future.set_result(node)
                    
                    # Emit message event
                    await self.events.emit("message.received", node)
                    await self._process_node(node)
                    
            except asyncio.CancelledError:
                break
            except ConnectionClosed as e:
                logger.warning(f"Connection closed: {e}")
                await self._handle_disconnect(e)
                break
            except Exception as e:
                logger.error(f"Receive error: {e}")
    
    async def _process_node(self, node: BinaryNode) -> None:
        """Process a received node."""
        tag = node.tag
        
        # Handle different node types
        if tag == "iq":
            await self.events.emit("iq", node)
        elif tag == "message":
            await self.events.emit("message", node)
        elif tag == "call":
            await self.events.emit("call", node)
        elif tag == "ack":
            await self.events.emit("ack", node)
        elif tag == "notification":
            await self.events.emit("notification", node)
        elif tag == "presence":
            await self.events.emit("presence", node)
        elif tag == "chatstate":
            await self.events.emit("chatstate", node)
    
    async def _handle_disconnect(self, error: Optional[Exception] = None) -> None:
        """Handle disconnection and potential reconnection."""
        await self._set_state(ConnectionState.DISCONNECTED)
        
        if self._closed:
            return
        
        if not self.config.auto_reconnect:
            return
        
        if self._reconnect_count >= self.config.max_reconnect_attempts:
            logger.error("Max reconnection attempts reached")
            return
        
        self._reconnect_count += 1
        delay = self.config.reconnect_delay * (2 ** (self._reconnect_count - 1))
        delay = min(delay, 60)  # Cap at 60 seconds
        delay *= (0.5 + random.random())  # Add jitter
        
        logger.info(f"Reconnecting in {delay:.1f}s (attempt {self._reconnect_count})")
        
        await self._set_state(ConnectionState.RECONNECTING)
        await asyncio.sleep(delay)
        
        try:
            await self.connect()
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            await self._handle_disconnect(e)
    
    async def send_node(self, node: BinaryNode) -> None:
        """
        Send a binary node.
        
        Args:
            node: Node to send
        """
        if not self.is_connected:
            raise RuntimeError("Not connected")
        
        # Encode node
        encoder = BinaryEncoder()
        data = encoder.encode_node(node)
        
        # Frame it
        framed = encode_frame(data, FrameType.BINARY)
        
        # Encrypt with Noise
        encrypted = self._noise.encrypt(framed)
        
        # Send
        await self._ws.send(encrypted)  # type: ignore
        
        logger.debug(f"Sent node: {node.tag}")
    
    async def send_and_wait(
        self,
        node: BinaryNode,
        timeout: Optional[float] = None,
    ) -> BinaryNode:
        """
        Send a node and wait for response.
        
        Args:
            node: Node to send (must have id attribute)
            timeout: Optional timeout in seconds
            
        Returns:
            Response node
        """
        msg_id = node.get_attr("id")
        if not msg_id:
            raise ValueError("Node must have id attribute for send_and_wait")
        
        # Create future for response
        future: asyncio.Future[BinaryNode] = asyncio.get_event_loop().create_future()
        self._pending_requests[msg_id] = future
        
        try:
            await self.send_node(node)
            return await asyncio.wait_for(
                future,
                timeout=timeout or self.config.request_timeout,
            )
        except asyncio.TimeoutError:
            self._pending_requests.pop(msg_id, None)
            raise
    
    async def close(self) -> None:
        """Close the connection."""
        self._closed = True
        
        # Cancel background tasks
        if self._keepalive_task:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        # Close WebSocket
        if self._ws:
            await self._ws.close()
            self._ws = None
        
        # Cancel pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()
        
        await self._set_state(ConnectionState.DISCONNECTED)
        logger.info("Connection closed")
    
    async def __aenter__(self) -> "WhatsAppSocket":
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

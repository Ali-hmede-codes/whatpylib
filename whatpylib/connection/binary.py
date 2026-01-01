"""
Binary protocol encoder/decoder for WhatsApp's custom framing.

WhatsApp uses a custom binary protocol on top of WebSocket for efficient
message serialization. This module handles encoding and decoding of that format.
"""

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Optional
import io

from whatpylib.utils.logger import get_logger

logger = get_logger("binary")


class FrameType(IntEnum):
    """Frame type identifiers."""
    BINARY = 0
    JSON = 1
    PROTOBUF = 2


class BinaryTag(IntEnum):
    """Binary protocol tag types."""
    LIST_EMPTY = 0
    STREAM_END = 1
    DICTIONARY_0 = 2
    DICTIONARY_1 = 3
    DICTIONARY_2 = 4
    DICTIONARY_3 = 5
    LIST_8 = 248
    LIST_16 = 249
    JID_PAIR = 250
    HEX_8 = 251
    BINARY_8 = 252
    BINARY_20 = 253
    BINARY_32 = 254
    NIBBLE_8 = 255


# Single-byte token dictionary (common strings)
SINGLE_BYTE_TOKENS = [
    "", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "-", ".", "true", "false", "null",
    "s.whatsapp.net", "g.us", "broadcast", "call",
    "action", "add", "after", "archive", "available",
    "battery", "before", "body", "broadcast", "chat",
    "clear", "code", "composing", "contacts", "count",
    "create", "debug", "delete", "demote", "duplicate",
    "encoding", "error", "false", "filehash", "from",
    "g.us", "group", "groups_v2", "height", "id",
    "image", "in", "index", "invis", "item",
    "jid", "kind", "last", "leave", "live",
    "log", "media", "message", "modify", "mute",
    "name", "net", "none", "not", "notify",
    "out", "owner", "participant", "paused",
    "picture", "ping", "platform", "presence", "preview",
    "promote", "query", "read", "receipt", "received",
    "recipient", "recording", "relay", "remove", "response",
    "resume", "retry", "s.whatsapp.net", "seconds", "set",
    "size", "status", "subject", "subscribe", "t",
    "text", "timestamp", "to", "true", "type",
    "unarchive", "unavailable", "url", "user", "value",
    "web", "width", "xml", "participants",
]


@dataclass
class BinaryNode:
    """
    Represents a node in the binary protocol tree.
    
    Attributes:
        tag: Node tag name
        attrs: Node attributes
        content: Node content (bytes, string, or list of child nodes)
    """
    tag: str
    attrs: dict[str, Any]
    content: Optional[Any] = None
    
    def __repr__(self) -> str:
        content_repr = ""
        if isinstance(self.content, bytes):
            content_repr = f"bytes({len(self.content)})"
        elif isinstance(self.content, list):
            content_repr = f"[{len(self.content)} nodes]"
        elif self.content is not None:
            content_repr = str(self.content)[:50]
        
        return f"BinaryNode({self.tag}, {self.attrs}, {content_repr})"
    
    def get_attr(self, key: str, default: Any = None) -> Any:
        """Get an attribute value."""
        return self.attrs.get(key, default)
    
    def find(self, tag: str) -> Optional["BinaryNode"]:
        """Find a child node by tag."""
        if isinstance(self.content, list):
            for child in self.content:
                if isinstance(child, BinaryNode) and child.tag == tag:
                    return child
        return None
    
    def find_all(self, tag: str) -> list["BinaryNode"]:
        """Find all child nodes with the given tag."""
        result = []
        if isinstance(self.content, list):
            for child in self.content:
                if isinstance(child, BinaryNode) and child.tag == tag:
                    result.append(child)
        return result


class BinaryEncoder:
    """
    Encoder for WhatsApp's binary protocol.
    """
    
    def __init__(self) -> None:
        self._buffer = io.BytesIO()
    
    def reset(self) -> None:
        """Reset the encoder buffer."""
        self._buffer = io.BytesIO()
    
    def get_bytes(self) -> bytes:
        """Get the encoded bytes."""
        return self._buffer.getvalue()
    
    def encode_node(self, node: BinaryNode) -> bytes:
        """
        Encode a binary node to bytes.
        
        Args:
            node: The node to encode
            
        Returns:
            Encoded bytes
        """
        self.reset()
        self._write_node(node)
        return self.get_bytes()
    
    def _write_byte(self, value: int) -> None:
        """Write a single byte."""
        self._buffer.write(bytes([value & 0xFF]))
    
    def _write_int16(self, value: int) -> None:
        """Write a 16-bit big-endian integer."""
        self._buffer.write(struct.pack(">H", value))
    
    def _write_int32(self, value: int) -> None:
        """Write a 32-bit big-endian integer."""
        self._buffer.write(struct.pack(">I", value))
    
    def _write_bytes(self, data: bytes) -> None:
        """Write raw bytes."""
        self._buffer.write(data)
    
    def _write_string(self, s: str) -> None:
        """Write a string with length prefix."""
        data = s.encode("utf-8")
        self._write_packed_bytes(data)
    
    def _write_packed_bytes(self, data: bytes) -> None:
        """Write bytes with appropriate length tag."""
        length = len(data)
        
        if length == 0:
            self._write_byte(BinaryTag.BINARY_8)
            self._write_byte(0)
        elif length < 256:
            self._write_byte(BinaryTag.BINARY_8)
            self._write_byte(length)
        elif length < 1 << 20:
            self._write_byte(BinaryTag.BINARY_20)
            # 20-bit length encoding
            self._write_byte((length >> 16) & 0xFF)
            self._write_byte((length >> 8) & 0xFF)
            self._write_byte(length & 0xFF)
        else:
            self._write_byte(BinaryTag.BINARY_32)
            self._write_int32(length)
        
        self._write_bytes(data)
    
    def _write_token(self, token: str) -> None:
        """Write a string as token or raw."""
        if not token:
            self._write_byte(BinaryTag.LIST_EMPTY)
            return
        
        # Check if it's in the token dictionary
        try:
            index = SINGLE_BYTE_TOKENS.index(token)
            self._write_byte(index)
            return
        except ValueError:
            pass
        
        # Write as raw string
        self._write_string(token)
    
    def _write_jid(self, user: str, server: str) -> None:
        """Write a JID (user@server)."""
        if not user and not server:
            self._write_byte(BinaryTag.LIST_EMPTY)
            return
        
        self._write_byte(BinaryTag.JID_PAIR)
        if user:
            self._write_token(user)
        else:
            self._write_byte(BinaryTag.LIST_EMPTY)
        self._write_token(server)
    
    def _write_list_start(self, length: int) -> None:
        """Write list start tag with length."""
        if length == 0:
            self._write_byte(BinaryTag.LIST_EMPTY)
        elif length < 256:
            self._write_byte(BinaryTag.LIST_8)
            self._write_byte(length)
        else:
            self._write_byte(BinaryTag.LIST_16)
            self._write_int16(length)
    
    def _write_node(self, node: BinaryNode) -> None:
        """Write a node to the buffer."""
        # Calculate list size: 1 for tag, 1 for each attr pair, 0 or 1 for content
        attr_count = len(node.attrs) * 2
        has_content = node.content is not None
        list_size = 1 + attr_count + (1 if has_content else 0)
        
        self._write_list_start(list_size)
        
        # Write tag
        self._write_token(node.tag)
        
        # Write attributes
        for key, value in node.attrs.items():
            self._write_token(key)
            if isinstance(value, str) and "@" in value:
                # Handle JID
                parts = value.split("@")
                self._write_jid(parts[0], parts[1])
            else:
                self._write_token(str(value))
        
        # Write content
        if has_content:
            if isinstance(node.content, bytes):
                self._write_packed_bytes(node.content)
            elif isinstance(node.content, str):
                self._write_string(node.content)
            elif isinstance(node.content, list):
                self._write_list_start(len(node.content))
                for child in node.content:
                    if isinstance(child, BinaryNode):
                        self._write_node(child)
                    else:
                        self._write_token(str(child))


class BinaryDecoder:
    """
    Decoder for WhatsApp's binary protocol.
    """
    
    def __init__(self, data: bytes) -> None:
        self._buffer = io.BytesIO(data)
        self._data = data
    
    def decode_node(self) -> BinaryNode:
        """
        Decode a binary node from the buffer.
        
        Returns:
            Decoded BinaryNode
        """
        return self._read_node()
    
    def _read_byte(self) -> int:
        """Read a single byte."""
        data = self._buffer.read(1)
        if not data:
            raise ValueError("Unexpected end of data")
        return data[0]
    
    def _read_int16(self) -> int:
        """Read a 16-bit big-endian integer."""
        data = self._buffer.read(2)
        if len(data) < 2:
            raise ValueError("Unexpected end of data")
        return struct.unpack(">H", data)[0]
    
    def _read_int32(self) -> int:
        """Read a 32-bit big-endian integer."""
        data = self._buffer.read(4)
        if len(data) < 4:
            raise ValueError("Unexpected end of data")
        return struct.unpack(">I", data)[0]
    
    def _read_bytes(self, length: int) -> bytes:
        """Read raw bytes."""
        data = self._buffer.read(length)
        if len(data) < length:
            raise ValueError("Unexpected end of data")
        return data
    
    def _read_string(self, tag: int) -> str:
        """Read a string based on tag."""
        if tag == BinaryTag.LIST_EMPTY:
            return ""
        
        if tag < len(SINGLE_BYTE_TOKENS):
            return SINGLE_BYTE_TOKENS[tag]
        
        if tag == BinaryTag.BINARY_8:
            length = self._read_byte()
            return self._read_bytes(length).decode("utf-8")
        
        if tag == BinaryTag.BINARY_20:
            b1 = self._read_byte()
            b2 = self._read_byte()
            b3 = self._read_byte()
            length = (b1 << 16) | (b2 << 8) | b3
            return self._read_bytes(length).decode("utf-8")
        
        if tag == BinaryTag.BINARY_32:
            length = self._read_int32()
            return self._read_bytes(length).decode("utf-8")
        
        if tag == BinaryTag.JID_PAIR:
            user_tag = self._read_byte()
            user = self._read_string(user_tag) if user_tag != BinaryTag.LIST_EMPTY else ""
            server_tag = self._read_byte()
            server = self._read_string(server_tag)
            return f"{user}@{server}" if user else server
        
        raise ValueError(f"Unknown string tag: {tag}")
    
    def _read_packed_bytes(self, tag: int) -> bytes:
        """Read packed bytes based on tag."""
        if tag == BinaryTag.BINARY_8:
            length = self._read_byte()
            return self._read_bytes(length)
        
        if tag == BinaryTag.BINARY_20:
            b1 = self._read_byte()
            b2 = self._read_byte()
            b3 = self._read_byte()
            length = (b1 << 16) | (b2 << 8) | b3
            return self._read_bytes(length)
        
        if tag == BinaryTag.BINARY_32:
            length = self._read_int32()
            return self._read_bytes(length)
        
        raise ValueError(f"Unknown binary tag: {tag}")
    
    def _read_list_size(self, tag: int) -> int:
        """Read list size based on tag."""
        if tag == BinaryTag.LIST_EMPTY:
            return 0
        if tag == BinaryTag.LIST_8:
            return self._read_byte()
        if tag == BinaryTag.LIST_16:
            return self._read_int16()
        raise ValueError(f"Unknown list tag: {tag}")
    
    def _read_node(self) -> BinaryNode:
        """Read a node from the buffer."""
        list_tag = self._read_byte()
        list_size = self._read_list_size(list_tag)
        
        if list_size == 0:
            raise ValueError("Empty node")
        
        # Read tag
        tag_byte = self._read_byte()
        tag = self._read_string(tag_byte)
        
        # Read attributes
        attrs: dict[str, Any] = {}
        attr_count = (list_size - 1) // 2
        
        for _ in range(attr_count):
            key_tag = self._read_byte()
            key = self._read_string(key_tag)
            value_tag = self._read_byte()
            value = self._read_string(value_tag)
            attrs[key] = value
        
        # Check for content
        content: Optional[Any] = None
        if list_size % 2 == 0:
            # Has content
            content_tag = self._read_byte()
            
            if content_tag in (BinaryTag.LIST_8, BinaryTag.LIST_16, BinaryTag.LIST_EMPTY):
                # List of child nodes
                child_count = self._read_list_size(content_tag)
                content = []
                for _ in range(child_count):
                    content.append(self._read_node())
            elif content_tag in (BinaryTag.BINARY_8, BinaryTag.BINARY_20, BinaryTag.BINARY_32):
                # Binary content
                content = self._read_packed_bytes(content_tag)
            else:
                # String content
                content = self._read_string(content_tag)
        
        return BinaryNode(tag=tag, attrs=attrs, content=content)


def encode_frame(data: bytes, frame_type: FrameType = FrameType.BINARY) -> bytes:
    """
    Encode a binary frame with header.
    
    Args:
        data: Frame payload
        frame_type: Type of frame
        
    Returns:
        Framed data with header
    """
    # Frame format: [flags:1][length:3][payload]
    length = len(data)
    header = bytes([
        frame_type & 0xFF,
        (length >> 16) & 0xFF,
        (length >> 8) & 0xFF,
        length & 0xFF,
    ])
    return header + data


def decode_frame(data: bytes) -> tuple[FrameType, bytes]:
    """
    Decode a binary frame.
    
    Args:
        data: Raw frame data
        
    Returns:
        Tuple of (frame_type, payload)
    """
    if len(data) < 4:
        raise ValueError("Frame too short")
    
    frame_type = FrameType(data[0])
    length = (data[1] << 16) | (data[2] << 8) | data[3]
    payload = data[4:4 + length]
    
    return frame_type, payload

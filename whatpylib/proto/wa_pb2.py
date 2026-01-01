"""
Pure Python implementation of WhatsApp Protobuf definitions.
This avoids the need for 'protoc' compiler installation.
"""

from dataclasses import dataclass, field, fields
from typing import List, Optional, Any, Dict, Type, Union
from enum import Enum
import struct

# ==================== Protobuf Primitives ====================

def _encode_varint(value: int) -> bytes:
    """Encode an integer as a varint."""
    buffer = []
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            buffer.append(byte | 0x80)
        else:
            buffer.append(byte)
            break
    return bytes(buffer)

def _decode_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Decode a varint from data at offset."""
    value = 0
    shift = 0
    while True:
        if offset >= len(data):
            raise ValueError("Varint truncated")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7
    return value, offset

class WireType(Enum):
    VARINT = 0
    FIXED64 = 1
    LENGTH_DELIMITED = 2
    START_GROUP = 3
    END_GROUP = 4
    FIXED32 = 5

class ProtoField:
    def __init__(self, tag: int, type_name: str, repeated: bool = False):
        self.tag = tag
        self.type_name = type_name
        self.repeated = repeated

def proto_field(tag: int, type_name: str, repeated: bool = False):
    if repeated:
        return field(metadata={"proto_tag": tag, "proto_type": type_name, "proto_repeated": repeated}, default_factory=list)
    else:
        return field(metadata={"proto_tag": tag, "proto_type": type_name, "proto_repeated": repeated}, default=None)

class ProtobufMixin:
    """Mixin to provide protobuf serialization/deserialization."""
    
    def SerializeToString(self) -> bytes:
        """Serialize message to bytes."""
        buffer = bytearray()
        
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None:
                continue
            
            tag = f.metadata.get("proto_tag")
            type_name = f.metadata.get("proto_type")
            repeated = f.metadata.get("proto_repeated")
            
            if tag is None:
                continue
            
            if repeated:
                if not value:
                    continue
                for item in value:
                    self._encode_field(buffer, tag, type_name, item)
            else:
                self._encode_field(buffer, tag, type_name, value)
                
        return bytes(buffer)
    
    def _encode_field(self, buffer: bytearray, tag: int, type_name: str, value: Any):
        if type_name == "int" or type_name == "uint64" or type_name == "uint32" or type_name == "int64" or type_name == "enum":
            # Varint
            key = (tag << 3) | WireType.VARINT.value
            buffer.extend(_encode_varint(key))
            buffer.extend(_encode_varint(int(value)))
        elif type_name == "bool":
            # Varint
            key = (tag << 3) | WireType.VARINT.value
            buffer.extend(_encode_varint(key))
            buffer.extend(_encode_varint(1 if value else 0))
        elif type_name == "string":
            # Length delimited
            key = (tag << 3) | WireType.LENGTH_DELIMITED.value
            buffer.extend(_encode_varint(key))
            encoded = value.encode("utf-8")
            buffer.extend(_encode_varint(len(encoded)))
            buffer.extend(encoded)
        elif type_name == "bytes":
            # Length delimited
            key = (tag << 3) | WireType.LENGTH_DELIMITED.value
            buffer.extend(_encode_varint(key))
            buffer.extend(_encode_varint(len(value)))
            buffer.extend(value)
        elif type_name == "float":
            # Fixed32
            key = (tag << 3) | WireType.FIXED32.value
            buffer.extend(_encode_varint(key))
            buffer.extend(struct.pack("<f", value))
        elif type_name == "double":
            # Fixed64
            key = (tag << 3) | WireType.FIXED64.value
            buffer.extend(_encode_varint(key))
            buffer.extend(struct.pack("<d", value))
        elif type_name == "message":
            # Length delimited (embedded message)
            key = (tag << 3) | WireType.LENGTH_DELIMITED.value
            buffer.extend(_encode_varint(key))
            encoded = value.SerializeToString()
            buffer.extend(_encode_varint(len(encoded)))
            buffer.extend(encoded)
    
    @classmethod
    def ParseFromString(cls, data: bytes) -> "ProtobufMixin":
        """Parse message from bytes."""
        obj = cls()
        offset = 0
        length = len(data)
        
        # Map tags to fields
        tag_map = {}
        for f in fields(cls):
            tag = f.metadata.get("proto_tag")
            if tag:
                tag_map[tag] = f
        
        while offset < length:
            # Read key
            key, offset = _decode_varint(data, offset)
            tag = key >> 3
            wire_type = WireType(key & 0x07)
            
            f = tag_map.get(tag)
            if not f:
                # Skip unknown field
                offset = cls._skip_field(data, offset, wire_type)
                continue
            
            type_name = f.metadata.get("proto_type")
            repeated = f.metadata.get("proto_repeated")
            
            value = None
            
            if wire_type == WireType.VARINT:
                val, offset = _decode_varint(data, offset)
                if type_name == "bool":
                    value = bool(val)
                else:
                    value = val
            elif wire_type == WireType.FIXED64:
                value = struct.unpack("<d", data[offset:offset+8])[0] if type_name == "double" else struct.unpack("<Q", data[offset:offset+8])[0]
                offset += 8
            elif wire_type == WireType.LENGTH_DELIMITED:
                l, offset = _decode_varint(data, offset)
                content = data[offset:offset+l]
                offset += l
                
                if type_name == "string":
                    value = content.decode("utf-8", errors="ignore")
                elif type_name == "bytes":
                    value = content
                elif type_name == "message":
                    # Find the class for this field
                    # This requires type hints to be resolved or passed in metadata
                    # For simplicity, we'll assume the type hint is the class
                    # But type hints are strings in some contexts.
                    # We'll use a registry or assume it's in globals
                    field_type = f.type
                    if isinstance(field_type, str):
                        # Forward reference
                        if field_type in globals():
                            field_type = globals()[field_type]
                        else:
                            # Try to find in current module
                            pass
                    
                    # Handle Optional[Type]
                    if hasattr(field_type, "__args__"): # Union/Optional
                        field_type = field_type.__args__[0]
                    
                    if issubclass(field_type, ProtobufMixin):
                        value = field_type.ParseFromString(content)
            elif wire_type == WireType.FIXED32:
                value = struct.unpack("<f", data[offset:offset+4])[0] if type_name == "float" else struct.unpack("<I", data[offset:offset+4])[0]
                offset += 4
            
            if value is not None:
                if repeated:
                    getattr(obj, f.name).append(value)
                else:
                    setattr(obj, f.name, value)
                    
        return obj

    @staticmethod
    def _skip_field(data: bytes, offset: int, wire_type: WireType) -> int:
        if wire_type == WireType.VARINT:
            _, offset = _decode_varint(data, offset)
        elif wire_type == WireType.FIXED64:
            offset += 8
        elif wire_type == WireType.LENGTH_DELIMITED:
            l, offset = _decode_varint(data, offset)
            offset += l
        elif wire_type == WireType.START_GROUP:
            while True:
                key, offset = _decode_varint(data, offset)
                wt = WireType(key & 0x07)
                if wt == WireType.END_GROUP:
                    break
                offset = ProtobufMixin._skip_field(data, offset, wt)
        elif wire_type == WireType.END_GROUP:
            pass
        elif wire_type == WireType.FIXED32:
            offset += 4
        return offset

# ==================== WhatsApp Messages ====================

@dataclass
class MessageKey(ProtobufMixin):
    remoteJid: Optional[str] = proto_field(1, "string")
    fromMe: Optional[bool] = proto_field(2, "bool")
    id: Optional[str] = proto_field(3, "string")
    participant: Optional[str] = proto_field(4, "string")

@dataclass
class ContextInfo(ProtobufMixin):
    stanzaId: Optional[str] = proto_field(1, "string")
    participant: Optional[str] = proto_field(2, "string")
    quotedMessage: Optional["Message"] = proto_field(3, "message")
    remoteJid: Optional[str] = proto_field(4, "string")
    mentionedJid: List[str] = proto_field(15, "string", repeated=True)
    conversionSource: Optional[str] = proto_field(18, "string")
    conversionData: Optional[bytes] = proto_field(19, "bytes")
    conversionDelaySeconds: Optional[int] = proto_field(20, "uint32")
    forwardingScore: Optional[int] = proto_field(21, "uint32")
    isForwarded: Optional[bool] = proto_field(22, "bool")

@dataclass
class ImageMessage(ProtobufMixin):
    url: Optional[str] = proto_field(1, "string")
    mimetype: Optional[str] = proto_field(2, "string")
    caption: Optional[str] = proto_field(3, "string")
    fileSha256: Optional[bytes] = proto_field(4, "bytes")
    fileLength: Optional[int] = proto_field(5, "uint64")
    height: Optional[int] = proto_field(6, "uint32")
    width: Optional[int] = proto_field(7, "uint32")
    mediaKey: Optional[bytes] = proto_field(8, "bytes")
    fileEncSha256: Optional[bytes] = proto_field(9, "bytes")
    directPath: Optional[str] = proto_field(11, "string")
    mediaKeyTimestamp: Optional[int] = proto_field(12, "int64")
    jpegThumbnail: Optional[bytes] = proto_field(16, "bytes")
    contextInfo: Optional[ContextInfo] = proto_field(17, "message")
    viewOnce: Optional[bool] = proto_field(25, "bool")

@dataclass
class VideoMessage(ProtobufMixin):
    url: Optional[str] = proto_field(1, "string")
    mimetype: Optional[str] = proto_field(2, "string")
    fileSha256: Optional[bytes] = proto_field(3, "bytes")
    fileLength: Optional[int] = proto_field(4, "uint64")
    seconds: Optional[int] = proto_field(5, "uint32")
    mediaKey: Optional[bytes] = proto_field(6, "bytes")
    caption: Optional[str] = proto_field(7, "string")
    gifPlayback: Optional[bool] = proto_field(8, "bool")
    height: Optional[int] = proto_field(9, "uint32")
    width: Optional[int] = proto_field(10, "uint32")
    fileEncSha256: Optional[bytes] = proto_field(11, "bytes")
    directPath: Optional[str] = proto_field(13, "string")
    mediaKeyTimestamp: Optional[int] = proto_field(14, "int64")
    jpegThumbnail: Optional[bytes] = proto_field(16, "bytes")
    contextInfo: Optional[ContextInfo] = proto_field(17, "message")
    viewOnce: Optional[bool] = proto_field(19, "bool")

@dataclass
class AudioMessage(ProtobufMixin):
    url: Optional[str] = proto_field(1, "string")
    mimetype: Optional[str] = proto_field(2, "string")
    fileSha256: Optional[bytes] = proto_field(3, "bytes")
    fileLength: Optional[int] = proto_field(4, "uint64")
    seconds: Optional[int] = proto_field(5, "uint32")
    ptt: Optional[bool] = proto_field(6, "bool")
    mediaKey: Optional[bytes] = proto_field(7, "bytes")
    fileEncSha256: Optional[bytes] = proto_field(8, "bytes")
    directPath: Optional[str] = proto_field(9, "string")
    mediaKeyTimestamp: Optional[int] = proto_field(10, "int64")
    contextInfo: Optional[ContextInfo] = proto_field(17, "message")
    waveform: Optional[bytes] = proto_field(19, "bytes")

@dataclass
class DocumentMessage(ProtobufMixin):
    url: Optional[str] = proto_field(1, "string")
    mimetype: Optional[str] = proto_field(2, "string")
    title: Optional[str] = proto_field(3, "string")
    fileSha256: Optional[bytes] = proto_field(4, "bytes")
    fileLength: Optional[int] = proto_field(5, "uint64")
    pageCount: Optional[int] = proto_field(6, "uint32")
    mediaKey: Optional[bytes] = proto_field(7, "bytes")
    fileName: Optional[str] = proto_field(8, "string")
    fileEncSha256: Optional[bytes] = proto_field(9, "bytes")
    directPath: Optional[str] = proto_field(10, "string")
    mediaKeyTimestamp: Optional[int] = proto_field(11, "int64")
    jpegThumbnail: Optional[bytes] = proto_field(16, "bytes")
    contextInfo: Optional[ContextInfo] = proto_field(17, "message")
    caption: Optional[str] = proto_field(18, "string")

@dataclass
class ExtendedTextMessage(ProtobufMixin):
    text: Optional[str] = proto_field(1, "string")
    matchedText: Optional[str] = proto_field(2, "string")
    canonicalUrl: Optional[str] = proto_field(4, "string")
    description: Optional[str] = proto_field(5, "string")
    title: Optional[str] = proto_field(6, "string")
    jpegThumbnail: Optional[bytes] = proto_field(16, "bytes")
    contextInfo: Optional[ContextInfo] = proto_field(17, "message")

@dataclass
class LocationMessage(ProtobufMixin):
    degreesLatitude: Optional[float] = proto_field(1, "double")
    degreesLongitude: Optional[float] = proto_field(2, "double")
    name: Optional[str] = proto_field(3, "string")
    address: Optional[str] = proto_field(4, "string")
    jpegThumbnail: Optional[bytes] = proto_field(16, "bytes")
    contextInfo: Optional[ContextInfo] = proto_field(17, "message")

@dataclass
class ContactMessage(ProtobufMixin):
    displayName: Optional[str] = proto_field(1, "string")
    vcard: Optional[str] = proto_field(16, "string")
    contextInfo: Optional[ContextInfo] = proto_field(17, "message")

@dataclass
class ReactionMessage(ProtobufMixin):
    key: Optional[MessageKey] = proto_field(1, "message")
    text: Optional[str] = proto_field(2, "string")
    groupingKey: Optional[str] = proto_field(3, "string")
    senderTimestampMs: Optional[int] = proto_field(4, "int64")

@dataclass
class ProtocolMessage(ProtobufMixin):
    key: Optional[MessageKey] = proto_field(1, "message")
    type: Optional[int] = proto_field(2, "enum")
    ephemeralExpiration: Optional[int] = proto_field(4, "uint32")

@dataclass
class Message(ProtobufMixin):
    conversation: Optional[str] = proto_field(1, "string")
    imageMessage: Optional[ImageMessage] = proto_field(3, "message")
    contactMessage: Optional[ContactMessage] = proto_field(4, "message")
    locationMessage: Optional[LocationMessage] = proto_field(5, "message")
    extendedTextMessage: Optional[ExtendedTextMessage] = proto_field(6, "message")
    documentMessage: Optional[DocumentMessage] = proto_field(7, "message")
    audioMessage: Optional[AudioMessage] = proto_field(8, "message")
    videoMessage: Optional[VideoMessage] = proto_field(9, "message")
    protocolMessage: Optional[ProtocolMessage] = proto_field(12, "message")
    reactionMessage: Optional[ReactionMessage] = proto_field(46, "message")

@dataclass
class WebMessageInfo(ProtobufMixin):
    key: Optional[MessageKey] = proto_field(1, "message")
    message: Optional[Message] = proto_field(2, "message")
    messageTimestamp: Optional[int] = proto_field(3, "uint64")
    status: Optional[int] = proto_field(4, "enum")
    participant: Optional[str] = proto_field(5, "string")
    pushName: Optional[str] = proto_field(19, "string")
    broadcast: Optional[bool] = proto_field(18, "bool")
    multicast: Optional[bool] = proto_field(21, "bool")

# Fix forward references
ContextInfo.__annotations__["quotedMessage"] = Optional[Message]

"""
Tests for pure-python protobuf implementation.
"""

import pytest
from whatpylib.proto.wa_pb2 import (
    WebMessageInfo,
    Message,
    MessageKey,
    ExtendedTextMessage,
    ImageMessage,
)

def test_basic_serialization():
    """Test basic serialization of simple types."""
    key = MessageKey(
        remoteJid="1234567890@s.whatsapp.net",
        fromMe=True,
        id="ABCDEF123456",
    )
    
    data = key.SerializeToString()
    assert isinstance(data, bytes)
    assert len(data) > 0
    
    # Deserialize
    decoded = MessageKey.ParseFromString(data)
    assert decoded.remoteJid == key.remoteJid
    assert decoded.fromMe == key.fromMe
    assert decoded.id == key.id

def test_nested_message():
    """Test serialization of nested messages."""
    text_msg = ExtendedTextMessage(
        text="Hello World",
        title="Greeting",
    )
    
    msg = Message(
        extendedTextMessage=text_msg,
        conversation="Fallback",
    )
    
    data = msg.SerializeToString()
    
    # Deserialize
    decoded = Message.ParseFromString(data)
    assert decoded.extendedTextMessage is not None
    assert decoded.extendedTextMessage.text == "Hello World"
    assert decoded.extendedTextMessage.title == "Greeting"
    assert decoded.conversation == "Fallback"

def test_repeated_fields():
    """Test repeated fields."""
    # ContextInfo has repeated mentionedJid
    from whatpylib.proto.wa_pb2 import ContextInfo
    
    ctx = ContextInfo(
        mentionedJid=["user1@s.whatsapp.net", "user2@s.whatsapp.net"]
    )
    
    data = ctx.SerializeToString()
    
    decoded = ContextInfo.ParseFromString(data)
    assert len(decoded.mentionedJid) == 2
    assert decoded.mentionedJid[0] == "user1@s.whatsapp.net"
    assert decoded.mentionedJid[1] == "user2@s.whatsapp.net"

def test_web_message_info():
    """Test full WebMessageInfo structure."""
    key = MessageKey(
        remoteJid="123@s.whatsapp.net",
        fromMe=True,
        id="MSG123",
    )
    
    msg = Message(conversation="Test Message")
    
    web_msg = WebMessageInfo(
        key=key,
        message=msg,
        messageTimestamp=1600000000,
        status=1,
    )
    
    data = web_msg.SerializeToString()
    
    decoded = WebMessageInfo.ParseFromString(data)
    assert decoded.key.remoteJid == "123@s.whatsapp.net"
    assert decoded.message.conversation == "Test Message"
    assert decoded.messageTimestamp == 1600000000
    assert decoded.status == 1

def test_image_message():
    """Test ImageMessage with bytes."""
    img = ImageMessage(
        url="https://example.com/image.jpg",
        fileSha256=b"1234",
        fileLength=1000,
        height=100,
        width=100,
    )
    
    msg = Message(imageMessage=img)
    data = msg.SerializeToString()
    
    decoded = Message.ParseFromString(data)
    assert decoded.imageMessage is not None
    assert decoded.imageMessage.url == "https://example.com/image.jpg"
    assert decoded.imageMessage.fileSha256 == b"1234"
    assert decoded.imageMessage.fileLength == 1000

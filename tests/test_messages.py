import pytest
from whatpylib.messages.builder import MessageBuilder
from whatpylib.messages.types import TextMessage

def test_build_text_message():
    """Test building a simple text message."""
    builder = MessageBuilder()
    msg = (
        builder
        .to("12345678@s.whatsapp.net")
        .text("Hello World")
        .build()
    )
    
    assert isinstance(msg, TextMessage)
    assert msg.text == "Hello World"
    assert msg.chat_jid == "12345678@s.whatsapp.net"

def test_reply_context():
    """Test adding reply context."""
    original = TextMessage(
        key=None, # Mock key needed
        timestamp=123456,
        text="Original"
    )
    # Mock key properties
    original_key = MagicMock()
    original_key.remote_jid = "remote@s.whatsapp.net"
    original_key.id = "ABC123ID"
    original_key.from_me = False
    
    # Needs to be attached to original message
    original.key = original_key
    
    # Also need to mock sender_jid property which uses participant or remote_jid
    # Since TextMessage is specific, sender_jid property logic is in base Message class.
    # We should ensure the original message yields the correct sender_jid.
    # The error "assert <MagicMock ...> == 'remote@...'" suggests one value is a Mock object.
    # It seems `quoted_participant` is getting assigned the mock PROPERTY instead of value?
    # No, it's likely `original.sender_jid` which returns the property logic.
    # If `original.key` is a mock, referencing attribute works.
    # But `Message.sender_jid` accesses `self.key.participant`.
    # `original_key.participant` is a Mock by default if not set.
    original_key.participant = None # Explicitly set to None so it falls back to remote_jid
    
    builder = MessageBuilder()
    msg = (
        builder
        .to("remote@s.whatsapp.net")
        .text("Reply")
        .reply_to(original)
        .build()
    )
    
    assert msg.context is not None
    assert msg.context.quoted_message_id == "ABC123ID"
    assert msg.context.quoted_participant == "remote@s.whatsapp.net"

from unittest.mock import MagicMock

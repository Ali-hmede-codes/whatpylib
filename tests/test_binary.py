"""
Tests for binary protocol encoder/decoder.
"""

import pytest
from whatpylib.connection.binary import (
    BinaryNode,
    BinaryEncoder,
    BinaryDecoder,
    encode_frame,
    decode_frame,
    FrameType,
)


class TestBinaryNode:
    """Tests for BinaryNode class."""
    
    def test_create_node(self):
        node = BinaryNode(
            tag="message",
            attrs={"to": "123@s.whatsapp.net", "type": "text"},
            content=b"Hello",
        )
        assert node.tag == "message"
        assert node.attrs["to"] == "123@s.whatsapp.net"
        assert node.content == b"Hello"
    
    def test_get_attr(self):
        node = BinaryNode(tag="test", attrs={"key": "value"})
        assert node.get_attr("key") == "value"
        assert node.get_attr("missing") is None
        assert node.get_attr("missing", "default") == "default"
    
    def test_find_child(self):
        child1 = BinaryNode(tag="child1", attrs={})
        child2 = BinaryNode(tag="child2", attrs={})
        parent = BinaryNode(tag="parent", attrs={}, content=[child1, child2])
        
        found = parent.find("child1")
        assert found is child1
        
        not_found = parent.find("nonexistent")
        assert not_found is None
    
    def test_find_all_children(self):
        child1 = BinaryNode(tag="item", attrs={"id": "1"})
        child2 = BinaryNode(tag="item", attrs={"id": "2"})
        child3 = BinaryNode(tag="other", attrs={})
        parent = BinaryNode(tag="parent", attrs={}, content=[child1, child2, child3])
        
        items = parent.find_all("item")
        assert len(items) == 2
        assert items[0] is child1
        assert items[1] is child2


class TestBinaryEncoder:
    """Tests for binary encoding."""
    
    def test_encode_simple_node(self):
        node = BinaryNode(tag="ping", attrs={})
        encoder = BinaryEncoder()
        data = encoder.encode_node(node)
        assert isinstance(data, bytes)
        assert len(data) > 0
    
    def test_encode_node_with_attrs(self):
        node = BinaryNode(
            tag="iq",
            attrs={"type": "get", "id": "123"},
        )
        encoder = BinaryEncoder()
        data = encoder.encode_node(node)
        assert isinstance(data, bytes)
    
    def test_encode_node_with_content(self):
        node = BinaryNode(
            tag="message",
            attrs={"type": "text"},
            content=b"Hello World",
        )
        encoder = BinaryEncoder()
        data = encoder.encode_node(node)
        assert b"Hello World" in data


class TestBinaryDecoder:
    """Tests for binary decoding."""
    
    def test_roundtrip_simple(self):
        original = BinaryNode(tag="ping", attrs={})
        
        encoder = BinaryEncoder()
        encoded = encoder.encode_node(original)
        
        decoder = BinaryDecoder(encoded)
        decoded = decoder.decode_node()
        
        assert decoded.tag == original.tag
    
    def test_roundtrip_with_attrs(self):
        original = BinaryNode(
            tag="iq",
            attrs={"type": "get"},
        )
        
        encoder = BinaryEncoder()
        encoded = encoder.encode_node(original)
        
        decoder = BinaryDecoder(encoded)
        decoded = decoder.decode_node()
        
        assert decoded.tag == original.tag
        assert decoded.attrs["type"] == "get"


class TestFrameEncoding:
    """Tests for frame encoding/decoding."""
    
    def test_encode_frame(self):
        data = b"test payload"
        framed = encode_frame(data, FrameType.BINARY)
        
        assert len(framed) == len(data) + 4
        assert framed[0] == FrameType.BINARY
    
    def test_decode_frame(self):
        data = b"test payload"
        framed = encode_frame(data, FrameType.BINARY)
        
        frame_type, payload = decode_frame(framed)
        
        assert frame_type == FrameType.BINARY
        assert payload == data
    
    def test_frame_roundtrip(self):
        original = b"Hello, WhatsApp!"
        
        framed = encode_frame(original, FrameType.BINARY)
        frame_type, decoded = decode_frame(framed)
        
        assert decoded == original
        assert frame_type == FrameType.BINARY

"""
Tests for utility functions.
"""

import pytest
from whatpylib.utils.jid import (
    JID,
    parse_jid,
    encode_jid,
    normalize_phone,
    is_group_jid,
    is_user_jid,
    jid_from_phone,
)


class TestJID:
    """Tests for JID class."""
    
    def test_user_jid(self):
        jid = JID(user="1234567890", server="s.whatsapp.net")
        assert jid.is_user
        assert not jid.is_group
        assert jid.phone_number == "1234567890"
        assert str(jid) == "1234567890@s.whatsapp.net"
    
    def test_group_jid(self):
        jid = JID(user="1234567890-1234567890", server="g.us")
        assert jid.is_group
        assert not jid.is_user
        assert jid.phone_number is None
    
    def test_jid_with_device(self):
        jid = JID(user="1234567890", server="s.whatsapp.net", agent=0, device=1)
        assert str(jid) == "1234567890:0:1@s.whatsapp.net"


class TestParseJID:
    """Tests for parse_jid function."""
    
    def test_parse_user_jid(self):
        jid = parse_jid("1234567890@s.whatsapp.net")
        assert jid.user == "1234567890"
        assert jid.server == "s.whatsapp.net"
        assert jid.is_user
    
    def test_parse_group_jid(self):
        jid = parse_jid("1234567890-1234567890@g.us")
        assert jid.is_group
    
    def test_parse_phone_only(self):
        jid = parse_jid("1234567890")
        assert jid.user == "1234567890"
        assert jid.server == "s.whatsapp.net"
    
    def test_parse_jid_with_device(self):
        jid = parse_jid("1234567890:0:1@s.whatsapp.net")
        assert jid.user == "1234567890"
        assert jid.agent == 0
        assert jid.device == 1
    
    def test_parse_empty_raises(self):
        with pytest.raises(ValueError):
            parse_jid("")


class TestNormalizePhone:
    """Tests for normalize_phone function."""
    
    def test_normalize_with_plus(self):
        assert normalize_phone("+1234567890") == "1234567890"
    
    def test_normalize_with_spaces(self):
        assert normalize_phone("123 456 7890") == "1234567890"
    
    def test_normalize_with_dashes(self):
        assert normalize_phone("123-456-7890") == "1234567890"
    
    def test_invalid_phone_raises(self):
        with pytest.raises(ValueError):
            normalize_phone("abc")
    
    def test_too_short_raises(self):
        with pytest.raises(ValueError):
            normalize_phone("123")


class TestJIDHelpers:
    """Tests for JID helper functions."""
    
    def test_is_group_jid_string(self):
        assert is_group_jid("123@g.us")
        assert not is_group_jid("123@s.whatsapp.net")
    
    def test_is_user_jid_string(self):
        assert is_user_jid("123@s.whatsapp.net")
        assert not is_user_jid("123@g.us")
    
    def test_jid_from_phone(self):
        jid = jid_from_phone("1234567890")
        assert jid.user == "1234567890"
        assert jid.server == "s.whatsapp.net"

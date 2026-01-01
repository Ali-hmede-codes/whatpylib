"""
Sender Keys for group message encryption.

WhatsApp uses Sender Keys for efficient group message encryption.
Each group member distributes a sender key, and messages are encrypted
once and sent to all participants.
"""

import os
import hashlib
import hmac
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, List
import base64

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives import serialization

from whatpylib.utils.logger import get_logger

logger = get_logger("sender_keys")


@dataclass
class SenderKey:
    """
    A sender key for group encryption.
    
    Attributes:
        key_id: Unique identifier for this sender key
        chain_key: Current chain key (32 bytes)
        signing_key: Signing key for verification
        iteration: Current iteration count
    """
    key_id: int
    chain_key: bytes
    signing_key: X25519PrivateKey
    iteration: int = 0
    
    @classmethod
    def generate(cls) -> "SenderKey":
        """Generate a new sender key."""
        return cls(
            key_id=int.from_bytes(os.urandom(4), "big"),
            chain_key=os.urandom(32),
            signing_key=X25519PrivateKey.generate(),
            iteration=0,
        )
    
    def get_message_key(self) -> bytes:
        """Derive a message key from the chain key."""
        return hmac.new(
            self.chain_key,
            b"\x01",
            hashlib.sha256,
        ).digest()
    
    def advance(self) -> None:
        """Advance the chain key."""
        self.chain_key = hmac.new(
            self.chain_key,
            b"\x02",
            hashlib.sha256,
        ).digest()
        self.iteration += 1
    
    def get_public_signing_key(self) -> bytes:
        """Get the public signing key."""
        return self.signing_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        private_bytes = self.signing_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return {
            "keyId": self.key_id,
            "chainKey": base64.b64encode(self.chain_key).decode("ascii"),
            "signingKey": base64.b64encode(private_bytes).decode("ascii"),
            "iteration": self.iteration,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SenderKey":
        """Deserialize from dictionary."""
        signing_key = X25519PrivateKey.from_private_bytes(
            base64.b64decode(data["signingKey"])
        )
        return cls(
            key_id=data["keyId"],
            chain_key=base64.b64decode(data["chainKey"]),
            signing_key=signing_key,
            iteration=data.get("iteration", 0),
        )


@dataclass
class SenderKeyRecord:
    """
    Record of a sender key from another participant.
    
    Attributes:
        sender_jid: JID of the sender
        key_id: Sender key ID
        chain_key: Current chain key
        public_signing_key: Public signing key
        iteration: Current iteration
    """
    sender_jid: str
    key_id: int
    chain_key: bytes
    public_signing_key: bytes
    iteration: int = 0
    
    def get_message_key(self) -> bytes:
        """Derive a message key from the chain key."""
        return hmac.new(
            self.chain_key,
            b"\x01",
            hashlib.sha256,
        ).digest()
    
    def advance(self) -> None:
        """Advance the chain key."""
        self.chain_key = hmac.new(
            self.chain_key,
            b"\x02",
            hashlib.sha256,
        ).digest()
        self.iteration += 1
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "senderJid": self.sender_jid,
            "keyId": self.key_id,
            "chainKey": base64.b64encode(self.chain_key).decode("ascii"),
            "publicSigningKey": base64.b64encode(self.public_signing_key).decode("ascii"),
            "iteration": self.iteration,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SenderKeyRecord":
        """Deserialize from dictionary."""
        return cls(
            sender_jid=data["senderJid"],
            key_id=data["keyId"],
            chain_key=base64.b64decode(data["chainKey"]),
            public_signing_key=base64.b64decode(data["publicSigningKey"]),
            iteration=data.get("iteration", 0),
        )


@dataclass
class SenderKeyDistribution:
    """
    Sender key distribution message.
    
    This is sent to group members to distribute our sender key.
    """
    group_id: str
    key_id: int
    chain_key: bytes
    public_signing_key: bytes
    iteration: int
    
    def to_bytes(self) -> bytes:
        """Serialize to bytes for sending."""
        result = bytearray()
        
        # Key ID (4 bytes)
        result.extend(self.key_id.to_bytes(4, "big"))
        
        # Iteration (4 bytes)
        result.extend(self.iteration.to_bytes(4, "big"))
        
        # Chain key (32 bytes)
        result.extend(self.chain_key)
        
        # Public signing key (32 bytes)
        result.extend(self.public_signing_key)
        
        return bytes(result)
    
    @classmethod
    def from_bytes(cls, group_id: str, data: bytes) -> "SenderKeyDistribution":
        """Deserialize from bytes."""
        if len(data) < 72:
            raise ValueError("Distribution message too short")
        
        key_id = int.from_bytes(data[:4], "big")
        iteration = int.from_bytes(data[4:8], "big")
        chain_key = data[8:40]
        public_signing_key = data[40:72]
        
        return cls(
            group_id=group_id,
            key_id=key_id,
            chain_key=chain_key,
            public_signing_key=public_signing_key,
            iteration=iteration,
        )


class SenderKeyStore:
    """
    Storage for sender keys (our keys and received keys from others).
    """
    
    def __init__(self) -> None:
        # Our sender keys per group
        self._our_keys: Dict[str, SenderKey] = {}
        
        # Received sender keys: group_id -> sender_jid -> record
        self._their_keys: Dict[str, Dict[str, SenderKeyRecord]] = {}
    
    def create_sender_key(self, group_id: str) -> SenderKey:
        """
        Create a new sender key for a group.
        
        Args:
            group_id: Group JID
            
        Returns:
            New SenderKey
        """
        key = SenderKey.generate()
        self._our_keys[group_id] = key
        return key
    
    def get_sender_key(self, group_id: str) -> Optional[SenderKey]:
        """Get our sender key for a group."""
        return self._our_keys.get(group_id)
    
    def store_sender_key(
        self,
        group_id: str,
        sender_jid: str,
        distribution: SenderKeyDistribution,
    ) -> None:
        """
        Store a received sender key.
        
        Args:
            group_id: Group JID
            sender_jid: Sender's JID
            distribution: Sender key distribution message
        """
        if group_id not in self._their_keys:
            self._their_keys[group_id] = {}
        
        record = SenderKeyRecord(
            sender_jid=sender_jid,
            key_id=distribution.key_id,
            chain_key=distribution.chain_key,
            public_signing_key=distribution.public_signing_key,
            iteration=distribution.iteration,
        )
        
        self._their_keys[group_id][sender_jid] = record
    
    def get_sender_key_record(
        self,
        group_id: str,
        sender_jid: str,
    ) -> Optional[SenderKeyRecord]:
        """Get a stored sender key record."""
        group_keys = self._their_keys.get(group_id)
        if group_keys:
            return group_keys.get(sender_jid)
        return None
    
    def create_distribution_message(
        self,
        group_id: str,
    ) -> SenderKeyDistribution:
        """
        Create a sender key distribution message.
        
        Args:
            group_id: Group JID
            
        Returns:
            SenderKeyDistribution for sending to group members
        """
        key = self._our_keys.get(group_id)
        if not key:
            key = self.create_sender_key(group_id)
        
        return SenderKeyDistribution(
            group_id=group_id,
            key_id=key.key_id,
            chain_key=key.chain_key,
            public_signing_key=key.get_public_signing_key(),
            iteration=key.iteration,
        )
    
    def encrypt_for_group(
        self,
        group_id: str,
        plaintext: bytes,
    ) -> bytes:
        """
        Encrypt a message for a group using sender keys.
        
        Args:
            group_id: Group JID
            plaintext: Message to encrypt
            
        Returns:
            Encrypted message
        """
        key = self._our_keys.get(group_id)
        if not key:
            raise RuntimeError(f"No sender key for group {group_id}")
        
        # Get message key
        message_key = key.get_message_key()
        
        # Encrypt with AES-GCM
        iv = os.urandom(12)
        aesgcm = AESGCM(message_key)
        ciphertext = aesgcm.encrypt(iv, plaintext, None)
        
        # Build message: [key_id:4][iteration:4][iv:12][ciphertext]
        result = bytearray()
        result.extend(key.key_id.to_bytes(4, "big"))
        result.extend(key.iteration.to_bytes(4, "big"))
        result.extend(iv)
        result.extend(ciphertext)
        
        # Advance the key
        key.advance()
        
        return bytes(result)
    
    def decrypt_from_group(
        self,
        group_id: str,
        sender_jid: str,
        ciphertext: bytes,
    ) -> bytes:
        """
        Decrypt a group message.
        
        Args:
            group_id: Group JID
            sender_jid: Sender's JID
            ciphertext: Encrypted message
            
        Returns:
            Decrypted plaintext
        """
        if len(ciphertext) < 20:
            raise ValueError("Ciphertext too short")
        
        key_id = int.from_bytes(ciphertext[:4], "big")
        iteration = int.from_bytes(ciphertext[4:8], "big")
        iv = ciphertext[8:20]
        encrypted = ciphertext[20:]
        
        # Get sender key record
        record = self.get_sender_key_record(group_id, sender_jid)
        if not record:
            raise RuntimeError(f"No sender key from {sender_jid} for group {group_id}")
        
        # Advance to the correct iteration if needed
        while record.iteration < iteration:
            record.advance()
        
        if record.iteration != iteration:
            raise RuntimeError("Message iteration mismatch")
        
        # Get message key and decrypt
        message_key = record.get_message_key()
        aesgcm = AESGCM(message_key)
        plaintext = aesgcm.decrypt(iv, encrypted, None)
        
        # Advance the record
        record.advance()
        
        return plaintext
    
    def to_dict(self) -> dict:
        """Serialize store for persistence."""
        return {
            "ourKeys": {
                gid: key.to_dict()
                for gid, key in self._our_keys.items()
            },
            "theirKeys": {
                gid: {
                    sid: record.to_dict()
                    for sid, record in sender_keys.items()
                }
                for gid, sender_keys in self._their_keys.items()
            },
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SenderKeyStore":
        """Deserialize store from persistence."""
        store = cls()
        
        for gid, key_data in data.get("ourKeys", {}).items():
            store._our_keys[gid] = SenderKey.from_dict(key_data)
        
        for gid, sender_keys in data.get("theirKeys", {}).items():
            store._their_keys[gid] = {}
            for sid, record_data in sender_keys.items():
                store._their_keys[gid][sid] = SenderKeyRecord.from_dict(record_data)
        
        return store

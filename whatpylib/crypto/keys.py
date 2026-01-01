"""
Key generation and management utilities for Signal Protocol.
"""

import os
import base64
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
import time

from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization

from whatpylib.utils.logger import get_logger

logger = get_logger("keys")


@dataclass
class IdentityKeyPair:
    """
    Identity key pair for Signal Protocol.
    
    The identity key is a long-term Curve25519 keypair that identifies
    a user/device. It's used to sign pre-keys and establish trust.
    
    Attributes:
        private_key: Ed25519 private key for signing
        public_key: Ed25519 public key (identity)
    """
    private_key: Ed25519PrivateKey
    public_key: Ed25519PublicKey
    
    @classmethod
    def generate(cls) -> "IdentityKeyPair":
        """Generate a new identity key pair."""
        private = Ed25519PrivateKey.generate()
        public = private.public_key()
        return cls(private_key=private, public_key=public)
    
    @classmethod
    def from_bytes(cls, private_bytes: bytes) -> "IdentityKeyPair":
        """Create from private key bytes."""
        private = Ed25519PrivateKey.from_private_bytes(private_bytes)
        public = private.public_key()
        return cls(private_key=private, public_key=public)
    
    def get_private_bytes(self) -> bytes:
        """Get private key as raw bytes."""
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
    
    def get_public_bytes(self) -> bytes:
        """Get public key as raw bytes."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    
    def sign(self, data: bytes) -> bytes:
        """Sign data with the identity key."""
        return self.private_key.sign(data)
    
    def verify(self, signature: bytes, data: bytes) -> bool:
        """Verify a signature."""
        try:
            self.public_key.verify(signature, data)
            return True
        except Exception:
            return False
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for storage."""
        return {
            "private": base64.b64encode(self.get_private_bytes()).decode("ascii"),
            "public": base64.b64encode(self.get_public_bytes()).decode("ascii"),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "IdentityKeyPair":
        """Deserialize from dictionary."""
        private_bytes = base64.b64decode(data["private"])
        return cls.from_bytes(private_bytes)


@dataclass
class PreKey:
    """
    Pre-key for Signal Protocol.
    
    Pre-keys are one-time use Curve25519 keypairs that allow
    asynchronous session establishment.
    
    Attributes:
        key_id: Unique identifier for this pre-key
        private_key: X25519 private key
        public_key: X25519 public key
    """
    key_id: int
    private_key: X25519PrivateKey
    public_key: X25519PublicKey
    
    @classmethod
    def generate(cls, key_id: int) -> "PreKey":
        """Generate a new pre-key with the given ID."""
        private = X25519PrivateKey.generate()
        public = private.public_key()
        return cls(key_id=key_id, private_key=private, public_key=public)
    
    def get_private_bytes(self) -> bytes:
        """Get private key as raw bytes."""
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
    
    def get_public_bytes(self) -> bytes:
        """Get public key as raw bytes."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "keyId": self.key_id,
            "private": base64.b64encode(self.get_private_bytes()).decode("ascii"),
            "public": base64.b64encode(self.get_public_bytes()).decode("ascii"),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "PreKey":
        """Deserialize from dictionary."""
        private_bytes = base64.b64decode(data["private"])
        private = X25519PrivateKey.from_private_bytes(private_bytes)
        public = private.public_key()
        return cls(key_id=data["keyId"], private_key=private, public_key=public)


@dataclass
class SignedPreKey:
    """
    Signed pre-key for Signal Protocol.
    
    A signed pre-key is a medium-term pre-key that is signed by the
    identity key to prove authenticity.
    
    Attributes:
        key_id: Unique identifier
        private_key: X25519 private key
        public_key: X25519 public key
        signature: Identity key signature of the public key
        timestamp: Creation timestamp
    """
    key_id: int
    private_key: X25519PrivateKey
    public_key: X25519PublicKey
    signature: bytes
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))
    
    @classmethod
    def generate(
        cls,
        key_id: int,
        identity_key: IdentityKeyPair,
    ) -> "SignedPreKey":
        """Generate a new signed pre-key."""
        private = X25519PrivateKey.generate()
        public = private.public_key()
        
        # Get public key bytes for signing
        public_bytes = public.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        
        # Sign with identity key
        signature = identity_key.sign(public_bytes)
        
        return cls(
            key_id=key_id,
            private_key=private,
            public_key=public,
            signature=signature,
        )
    
    def get_public_bytes(self) -> bytes:
        """Get public key as raw bytes."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    
    def get_private_bytes(self) -> bytes:
        """Get private key as raw bytes."""
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "keyId": self.key_id,
            "private": base64.b64encode(self.get_private_bytes()).decode("ascii"),
            "public": base64.b64encode(self.get_public_bytes()).decode("ascii"),
            "signature": base64.b64encode(self.signature).decode("ascii"),
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SignedPreKey":
        """Deserialize from dictionary."""
        private_bytes = base64.b64decode(data["private"])
        private = X25519PrivateKey.from_private_bytes(private_bytes)
        public = private.public_key()
        signature = base64.b64decode(data["signature"])
        return cls(
            key_id=data["keyId"],
            private_key=private,
            public_key=public,
            signature=signature,
            timestamp=data.get("timestamp", 0),
        )


class KeyHelper:
    """
    Helper class for generating Signal Protocol keys.
    """
    
    # Pre-key ID range
    PRE_KEY_ID_START = 1
    PRE_KEY_ID_MAX = 0xFFFFFF
    
    @staticmethod
    def generate_identity_key_pair() -> IdentityKeyPair:
        """Generate a new identity key pair."""
        return IdentityKeyPair.generate()
    
    @staticmethod
    def generate_registration_id() -> int:
        """
        Generate a random registration ID.
        
        The registration ID is a random 14-bit number that identifies
        a Signal Protocol installation.
        """
        return int.from_bytes(os.urandom(2), "big") & 0x3FFF
    
    @staticmethod
    def generate_pre_keys(
        start_id: int,
        count: int,
    ) -> List[PreKey]:
        """
        Generate a batch of pre-keys.
        
        Args:
            start_id: Starting key ID
            count: Number of pre-keys to generate
            
        Returns:
            List of PreKey objects
        """
        pre_keys = []
        for i in range(count):
            key_id = (start_id + i) % KeyHelper.PRE_KEY_ID_MAX
            pre_keys.append(PreKey.generate(key_id))
        return pre_keys
    
    @staticmethod
    def generate_signed_pre_key(
        key_id: int,
        identity_key: IdentityKeyPair,
    ) -> SignedPreKey:
        """
        Generate a new signed pre-key.
        
        Args:
            key_id: Key ID for the signed pre-key
            identity_key: Identity key pair for signing
            
        Returns:
            SignedPreKey object
        """
        return SignedPreKey.generate(key_id, identity_key)
    
    @staticmethod
    def generate_sender_key() -> bytes:
        """Generate a random sender key for group messaging."""
        return os.urandom(32)
    
    @staticmethod
    def generate_sender_key_id() -> int:
        """Generate a random sender key ID."""
        return int.from_bytes(os.urandom(4), "big")


@dataclass
class KeyBundle:
    """
    A bundle of keys for establishing a session.
    
    Contains all the public keys needed to initiate a Signal session
    with another user.
    """
    registration_id: int
    identity_key: bytes  # Public key bytes
    signed_pre_key_id: int
    signed_pre_key: bytes  # Public key bytes
    signed_pre_key_signature: bytes
    pre_key_id: Optional[int] = None
    pre_key: Optional[bytes] = None  # Public key bytes (optional one-time)
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        result = {
            "registrationId": self.registration_id,
            "identityKey": base64.b64encode(self.identity_key).decode("ascii"),
            "signedPreKeyId": self.signed_pre_key_id,
            "signedPreKey": base64.b64encode(self.signed_pre_key).decode("ascii"),
            "signedPreKeySignature": base64.b64encode(self.signed_pre_key_signature).decode("ascii"),
        }
        if self.pre_key_id is not None and self.pre_key is not None:
            result["preKeyId"] = self.pre_key_id
            result["preKey"] = base64.b64encode(self.pre_key).decode("ascii")
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> "KeyBundle":
        """Deserialize from dictionary."""
        pre_key_id = data.get("preKeyId")
        pre_key = data.get("preKey")
        return cls(
            registration_id=data["registrationId"],
            identity_key=base64.b64decode(data["identityKey"]),
            signed_pre_key_id=data["signedPreKeyId"],
            signed_pre_key=base64.b64decode(data["signedPreKey"]),
            signed_pre_key_signature=base64.b64decode(data["signedPreKeySignature"]),
            pre_key_id=pre_key_id,
            pre_key=base64.b64decode(pre_key) if pre_key else None,
        )

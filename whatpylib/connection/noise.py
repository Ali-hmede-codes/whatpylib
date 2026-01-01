"""
Noise Protocol XX handshake implementation for WhatsApp.

WhatsApp uses Noise_XX_25519_AESGCM_SHA256 for initial connection security.
This establishes a secure channel before any authentication takes place.
"""

import hashlib
import hmac
import os
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives import serialization

from whatpylib.config import NOISE_PROTOCOL_NAME, WA_HEADER
from whatpylib.utils.logger import get_logger

logger = get_logger("noise")


class NoiseState(Enum):
    """Noise handshake state machine."""
    INITIAL = auto()
    HANDSHAKE_1_SENT = auto()
    HANDSHAKE_2_RECEIVED = auto()
    HANDSHAKE_3_SENT = auto()
    ESTABLISHED = auto()


@dataclass
class NoiseKeys:
    """
    Cryptographic keys for Noise protocol.
    """
    private_key: X25519PrivateKey
    public_key: X25519PublicKey
    
    @classmethod
    def generate(cls) -> "NoiseKeys":
        """Generate a new keypair."""
        private = X25519PrivateKey.generate()
        public = private.public_key()
        return cls(private_key=private, public_key=public)
    
    @classmethod
    def from_private_bytes(cls, data: bytes) -> "NoiseKeys":
        """Load from private key bytes."""
        private = X25519PrivateKey.from_private_bytes(data)
        public = private.public_key()
        return cls(private_key=private, public_key=public)
    
    def get_private_bytes(self) -> bytes:
        """Get private key as bytes."""
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
    
    def get_public_bytes(self) -> bytes:
        """Get public key as bytes."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )


@dataclass
class NoiseHandler:
    """
    Handler for Noise XX handshake and encryption.
    
    Implements the Noise_XX_25519_AESGCM_SHA256 protocol pattern:
    - -> e
    - <- e, ee, s, es
    - -> s, se
    
    Attributes:
        local_keys: Our ephemeral keypair
        remote_public: Server's public key
        state: Current handshake state
    """
    local_keys: NoiseKeys = field(default_factory=NoiseKeys.generate)
    local_static: Optional[NoiseKeys] = None
    remote_public: Optional[bytes] = None
    remote_static: Optional[bytes] = None
    state: NoiseState = NoiseState.INITIAL
    
    # Noise protocol state
    _hash: bytes = field(default=b"", init=False)
    _chaining_key: bytes = field(default=b"", init=False)
    _cipher_key: bytes = field(default=b"", init=False)
    _counter: int = field(default=0, init=False)
    
    # Split keys after handshake
    _send_key: Optional[bytes] = field(default=None, init=False)
    _recv_key: Optional[bytes] = field(default=None, init=False)
    _send_counter: int = field(default=0, init=False)
    _recv_counter: int = field(default=0, init=False)
    
    def __post_init__(self) -> None:
        """Initialize noise protocol state."""
        self._initialize_symmetric()
    
    def _initialize_symmetric(self) -> None:
        """Initialize symmetric state for handshake."""
        # Protocol name padded to 32 bytes
        self._hash = NOISE_PROTOCOL_NAME[:32].ljust(32, b"\x00")
        self._chaining_key = self._hash
        
        # Mix in WhatsApp header
        self._mix_hash(WA_HEADER)
    
    def _mix_hash(self, data: bytes) -> None:
        """Mix data into the hash."""
        self._hash = hashlib.sha256(self._hash + data).digest()
    
    def _mix_key(self, input_key_material: bytes) -> None:
        """Mix key into chaining key and derive cipher key."""
        # HKDF with chaining key
        self._chaining_key, self._cipher_key = self._hkdf(
            self._chaining_key,
            input_key_material,
        )
        self._counter = 0
    
    def _hkdf(
        self,
        salt: bytes,
        input_key_material: bytes,
        num_outputs: int = 2,
    ) -> Tuple[bytes, ...]:
        """
        HKDF extract and expand.
        
        Args:
            salt: HKDF salt
            input_key_material: Input key material
            num_outputs: Number of 32-byte outputs
            
        Returns:
            Tuple of derived keys
        """
        # Extract
        prk = hmac.new(salt, input_key_material, hashlib.sha256).digest()
        
        # Expand
        outputs = []
        prev = b""
        for i in range(num_outputs):
            prev = hmac.new(
                prk,
                prev + bytes([i + 1]),
                hashlib.sha256,
            ).digest()
            outputs.append(prev)
        
        return tuple(outputs)
    
    def _encrypt(self, plaintext: bytes, associated_data: bytes = b"") -> bytes:
        """
        Encrypt with current cipher key.
        
        Args:
            plaintext: Data to encrypt
            associated_data: Additional authenticated data
            
        Returns:
            Ciphertext with authentication tag
        """
        if not self._cipher_key:
            raise RuntimeError("No cipher key established")
        
        # Create nonce from counter
        nonce = self._counter.to_bytes(12, "little")
        self._counter += 1
        
        # Encrypt with AES-GCM
        aesgcm = AESGCM(self._cipher_key)
        return aesgcm.encrypt(nonce, plaintext, associated_data)
    
    def _decrypt(self, ciphertext: bytes, associated_data: bytes = b"") -> bytes:
        """
        Decrypt with current cipher key.
        
        Args:
            ciphertext: Data to decrypt
            associated_data: Additional authenticated data
            
        Returns:
            Decrypted plaintext
        """
        if not self._cipher_key:
            raise RuntimeError("No cipher key established")
        
        # Create nonce from counter
        nonce = self._counter.to_bytes(12, "little")
        self._counter += 1
        
        # Decrypt with AES-GCM
        aesgcm = AESGCM(self._cipher_key)
        return aesgcm.decrypt(nonce, ciphertext, associated_data)
    
    def _dh(self, private: X25519PrivateKey, public_bytes: bytes) -> bytes:
        """
        Perform Diffie-Hellman key exchange.
        
        Args:
            private: Our private key
            public_bytes: Their public key bytes
            
        Returns:
            Shared secret
        """
        public = X25519PublicKey.from_public_bytes(public_bytes)
        return private.exchange(public)
    
    def create_handshake_message_1(self) -> bytes:
        """
        Create the first handshake message (-> e).
        
        Returns:
            First handshake message bytes
        """
        if self.state != NoiseState.INITIAL:
            raise RuntimeError(f"Invalid state for handshake 1: {self.state}")
        
        # Generate ephemeral keypair if needed
        if self.local_keys is None:
            self.local_keys = NoiseKeys.generate()
        
        # Get our ephemeral public key
        e_public = self.local_keys.get_public_bytes()
        
        # Mix public key into hash
        self._mix_hash(e_public)
        
        self.state = NoiseState.HANDSHAKE_1_SENT
        logger.debug("Created handshake message 1")
        
        return e_public
    
    def process_handshake_message_2(self, message: bytes) -> bytes:
        """
        Process the second handshake message (<- e, ee, s, es).
        
        Args:
            message: Server's handshake response
            
        Returns:
            Decrypted payload
        """
        if self.state != NoiseState.HANDSHAKE_1_SENT:
            raise RuntimeError(f"Invalid state for handshake 2: {self.state}")
        
        # Extract server's ephemeral public key (first 32 bytes)
        if len(message) < 32:
            raise ValueError("Handshake 2 message too short")
        
        server_public = message[:32]
        self.remote_public = server_public
        self._mix_hash(server_public)
        
        # Perform ee DH
        shared_ee = self._dh(self.local_keys.private_key, server_public)
        self._mix_key(shared_ee)
        
        # Decrypt server's static public key
        encrypted_static = message[32:32 + 48]  # 32 bytes key + 16 bytes tag
        self.remote_static = self._decrypt(encrypted_static, self._hash)
        self._mix_hash(encrypted_static)
        
        # Perform es DH
        shared_es = self._dh(self.local_keys.private_key, self.remote_static)
        self._mix_key(shared_es)
        
        # Decrypt payload
        encrypted_payload = message[80:]
        payload = self._decrypt(encrypted_payload, self._hash)
        self._mix_hash(encrypted_payload)
        
        self.state = NoiseState.HANDSHAKE_2_RECEIVED
        logger.debug("Processed handshake message 2")
        
        return payload
    
    def create_handshake_message_3(self, payload: bytes = b"") -> bytes:
        """
        Create the third handshake message (-> s, se).
        
        Args:
            payload: Optional payload to include
            
        Returns:
            Third handshake message bytes
        """
        if self.state != NoiseState.HANDSHAKE_2_RECEIVED:
            raise RuntimeError(f"Invalid state for handshake 3: {self.state}")
        
        if self.local_static is None:
            self.local_static = NoiseKeys.generate()
        
        result = bytearray()
        
        # Encrypt our static public key
        static_encrypted = self._encrypt(
            self.local_static.get_public_bytes(),
            self._hash,
        )
        result.extend(static_encrypted)
        self._mix_hash(static_encrypted)
        
        # Perform se DH
        shared_se = self._dh(self.local_static.private_key, self.remote_public)  # type: ignore
        self._mix_key(shared_se)
        
        # Encrypt payload
        if payload:
            payload_encrypted = self._encrypt(payload, self._hash)
            result.extend(payload_encrypted)
            self._mix_hash(payload_encrypted)
        
        # Split keys for transport
        self._split_keys()
        
        self.state = NoiseState.HANDSHAKE_3_SENT
        logger.debug("Created handshake message 3")
        
        return bytes(result)
    
    def _split_keys(self) -> None:
        """Split handshake keys into transport keys."""
        # Derive two keys from chaining key
        self._send_key, self._recv_key = self._hkdf(
            self._chaining_key,
            b"",
            2,
        )
        self._send_counter = 0
        self._recv_counter = 0
        self.state = NoiseState.ESTABLISHED
        logger.info("Noise handshake complete, transport keys established")
    
    def encrypt(self, plaintext: bytes) -> bytes:
        """
        Encrypt data for sending using transport key.
        
        Args:
            plaintext: Data to encrypt
            
        Returns:
            Encrypted data with header
        """
        if self.state != NoiseState.ESTABLISHED:
            raise RuntimeError("Handshake not complete")
        
        if not self._send_key:
            raise RuntimeError("No send key")
        
        # Create nonce
        nonce = self._send_counter.to_bytes(12, "little")
        self._send_counter += 1
        
        # Encrypt
        aesgcm = AESGCM(self._send_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, b"")
        
        return ciphertext
    
    def decrypt(self, ciphertext: bytes) -> bytes:
        """
        Decrypt received data using transport key.
        
        Args:
            ciphertext: Encrypted data
            
        Returns:
            Decrypted plaintext
        """
        if self.state != NoiseState.ESTABLISHED:
            raise RuntimeError("Handshake not complete")
        
        if not self._recv_key:
            raise RuntimeError("No receive key")
        
        # Create nonce
        nonce = self._recv_counter.to_bytes(12, "little")
        self._recv_counter += 1
        
        # Decrypt
        aesgcm = AESGCM(self._recv_key)
        return aesgcm.decrypt(nonce, ciphertext, b"")
    
    @property
    def is_established(self) -> bool:
        """Check if handshake is complete."""
        return self.state == NoiseState.ESTABLISHED
    
    def get_static_keypair(self) -> Optional[NoiseKeys]:
        """Get our static keypair (for saving)."""
        return self.local_static
    
    def set_static_keypair(self, keys: NoiseKeys) -> None:
        """Set our static keypair (for restoring)."""
        self.local_static = keys

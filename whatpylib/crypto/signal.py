"""
Signal Protocol implementation for WhatsApp E2E encryption.

This module wraps python-axolotl to provide Signal Protocol encryption
for WhatsApp messages.
"""

import os
import hashlib
import hmac
from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List, Tuple
import base64

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from whatpylib.crypto.keys import (
    IdentityKeyPair,
    PreKey,
    SignedPreKey,
    KeyHelper,
    KeyBundle,
)
from whatpylib.utils.logger import get_logger

logger = get_logger("signal")


# Signal Protocol constants
HKDF_INFO_MESSAGE_KEYS = b"WhisperMessageKeys"
HKDF_INFO_RATCHET = b"WhisperRatchet"
MAX_MESSAGE_KEYS = 2000


@dataclass
class MessageKeys:
    """
    Derived message keys for encryption/decryption.
    
    Attributes:
        cipher_key: AES encryption key (32 bytes)
        mac_key: HMAC key (32 bytes)
        iv: Initialization vector (16 bytes)
        index: Message index
    """
    cipher_key: bytes
    mac_key: bytes
    iv: bytes
    index: int


@dataclass
class ChainKey:
    """
    Chain key for the double ratchet algorithm.
    
    Attributes:
        key: The chain key (32 bytes)
        index: Current index in the chain
    """
    key: bytes
    index: int = 0
    
    def get_message_keys(self) -> MessageKeys:
        """Derive message keys from the chain key."""
        # Derive message key using HMAC
        message_key = hmac.new(
            self.key,
            b"\x01",
            hashlib.sha256,
        ).digest()
        
        # Derive cipher key, mac key, and IV using HKDF
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=80,  # 32 + 32 + 16
            salt=b"\x00" * 32,
            info=HKDF_INFO_MESSAGE_KEYS,
        )
        derived = hkdf.derive(message_key)
        
        return MessageKeys(
            cipher_key=derived[:32],
            mac_key=derived[32:64],
            iv=derived[64:80],
            index=self.index,
        )
    
    def next(self) -> "ChainKey":
        """Advance to the next chain key."""
        next_key = hmac.new(
            self.key,
            b"\x02",
            hashlib.sha256,
        ).digest()
        return ChainKey(key=next_key, index=self.index + 1)


@dataclass
class RootKey:
    """
    Root key for the double ratchet algorithm.
    
    Attributes:
        key: The root key (32 bytes)
    """
    key: bytes
    
    def create_chain(
        self,
        their_ratchet_key: bytes,
        our_ratchet_key: X25519PrivateKey,
    ) -> Tuple["RootKey", ChainKey]:
        """
        Perform a DH ratchet step and derive new keys.
        
        Args:
            their_ratchet_key: Their public ratchet key
            our_ratchet_key: Our private ratchet key
            
        Returns:
            Tuple of (new_root_key, new_chain_key)
        """
        # Perform DH
        their_public = X25519PublicKey.from_public_bytes(their_ratchet_key)
        shared_secret = our_ratchet_key.exchange(their_public)
        
        # Derive new keys using HKDF
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,  # 32 + 32
            salt=self.key,
            info=HKDF_INFO_RATCHET,
        )
        derived = hkdf.derive(shared_secret)
        
        new_root_key = RootKey(key=derived[:32])
        new_chain_key = ChainKey(key=derived[32:64], index=0)
        
        return new_root_key, new_chain_key


@dataclass
class SessionState:
    """
    State of a Signal Protocol session.
    
    Contains all the cryptographic state needed for the double ratchet.
    """
    # Identity keys
    local_identity_public: bytes
    remote_identity_public: bytes
    
    # Root key
    root_key: RootKey
    
    # Sending chain
    sending_chain: Optional[ChainKey] = None
    sending_ratchet_key: Optional[X25519PrivateKey] = None
    
    # Receiving chains (mapped by their ratchet key)
    receiving_chains: Dict[bytes, ChainKey] = field(default_factory=dict)
    
    # Their current ratchet key
    their_ratchet_key: Optional[bytes] = None
    
    # Previous counter (for out-of-order messages)
    previous_counter: int = 0
    
    # Skipped message keys (for out-of-order decryption)
    skipped_keys: Dict[Tuple[bytes, int], MessageKeys] = field(default_factory=dict)


@dataclass
class SignalSession:
    """
    A Signal Protocol session with another user.
    
    Manages encryption/decryption state for communication with a specific
    recipient.
    """
    remote_jid: str
    state: SessionState
    
    def encrypt(self, plaintext: bytes) -> Tuple[bytes, int]:
        """
        Encrypt a message.
        
        Args:
            plaintext: Message to encrypt
            
        Returns:
            Tuple of (ciphertext, message_type)
        """
        if self.state.sending_chain is None:
            raise RuntimeError("Session not initialized for sending")
        
        # Get message keys
        message_keys = self.state.sending_chain.get_message_keys()
        
        # Advance the chain
        self.state.sending_chain = self.state.sending_chain.next()
        
        # Encrypt with AES-GCM
        aesgcm = AESGCM(message_keys.cipher_key)
        ciphertext = aesgcm.encrypt(message_keys.iv, plaintext, None)
        
        # Build the message
        # Format: [ratchet_key:32][counter:4][previous_counter:4][ciphertext]
        message = bytearray()
        
        if self.state.sending_ratchet_key:
            from cryptography.hazmat.primitives import serialization
            ratchet_public = self.state.sending_ratchet_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            message.extend(ratchet_public)
        else:
            message.extend(b"\x00" * 32)
        
        message.extend(message_keys.index.to_bytes(4, "big"))
        message.extend(self.state.previous_counter.to_bytes(4, "big"))
        message.extend(ciphertext)
        
        # Calculate MAC
        mac = hmac.new(
            message_keys.mac_key,
            bytes(message),
            hashlib.sha256,
        ).digest()[:8]
        
        message.extend(mac)
        
        return bytes(message), 1  # 1 = Signal message
    
    def decrypt(self, ciphertext: bytes) -> bytes:
        """
        Decrypt a message.
        
        Args:
            ciphertext: Encrypted message
            
        Returns:
            Decrypted plaintext
        """
        if len(ciphertext) < 48:  # 32 + 4 + 4 + min_ciphertext + 8
            raise ValueError("Message too short")
        
        # Parse message
        their_ratchet_key = ciphertext[:32]
        counter = int.from_bytes(ciphertext[32:36], "big")
        previous_counter = int.from_bytes(ciphertext[36:40], "big")
        encrypted = ciphertext[40:-8]
        mac = ciphertext[-8:]
        
        # Check for ratchet key change
        if their_ratchet_key != self.state.their_ratchet_key:
            # Perform receiving ratchet
            self._ratchet_for_receiving(their_ratchet_key)
        
        # Get the receiving chain
        receiving_chain = self.state.receiving_chains.get(their_ratchet_key)
        if not receiving_chain:
            raise RuntimeError("No receiving chain for this ratchet key")
        
        # Skip ahead if needed
        while receiving_chain.index < counter:
            # Store skipped message keys
            skipped = receiving_chain.get_message_keys()
            self.state.skipped_keys[(their_ratchet_key, skipped.index)] = skipped
            receiving_chain = receiving_chain.next()
            
            # Limit stored keys
            if len(self.state.skipped_keys) > MAX_MESSAGE_KEYS:
                # Remove oldest
                oldest_key = next(iter(self.state.skipped_keys))
                del self.state.skipped_keys[oldest_key]
        
        # Get message keys
        message_keys = receiving_chain.get_message_keys()
        
        # Verify MAC
        expected_mac = hmac.new(
            message_keys.mac_key,
            ciphertext[:-8],
            hashlib.sha256,
        ).digest()[:8]
        
        if not hmac.compare_digest(mac, expected_mac):
            raise ValueError("MAC verification failed")
        
        # Advance the chain
        self.state.receiving_chains[their_ratchet_key] = receiving_chain.next()
        
        # Decrypt
        aesgcm = AESGCM(message_keys.cipher_key)
        return aesgcm.decrypt(message_keys.iv, encrypted, None)
    
    def _ratchet_for_receiving(self, their_ratchet_key: bytes) -> None:
        """Perform a DH ratchet step for receiving."""
        # Store previous counter
        if self.state.sending_chain:
            self.state.previous_counter = self.state.sending_chain.index
        
        # Generate new sending ratchet key
        new_ratchet = X25519PrivateKey.generate()
        
        # Derive new receiving chain
        new_root, new_receiving_chain = self.state.root_key.create_chain(
            their_ratchet_key,
            new_ratchet,
        )
        
        # Derive new sending chain
        from cryptography.hazmat.primitives import serialization
        our_public = new_ratchet.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        
        new_root2, new_sending_chain = new_root.create_chain(
            their_ratchet_key,
            new_ratchet,
        )
        
        # Update state
        self.state.root_key = new_root2
        self.state.their_ratchet_key = their_ratchet_key
        self.state.receiving_chains[their_ratchet_key] = new_receiving_chain
        self.state.sending_chain = new_sending_chain
        self.state.sending_ratchet_key = new_ratchet
    
    def to_dict(self) -> dict:
        """Serialize session state for storage."""
        return {
            "remoteJid": self.remote_jid,
            "localIdentity": base64.b64encode(self.state.local_identity_public).decode("ascii"),
            "remoteIdentity": base64.b64encode(self.state.remote_identity_public).decode("ascii"),
            "rootKey": base64.b64encode(self.state.root_key.key).decode("ascii"),
            # More fields would be serialized in full implementation
        }


class SignalProtocol:
    """
    Signal Protocol manager for WhatsApp E2E encryption.
    
    Handles session creation, message encryption/decryption, and key management.
    """
    
    def __init__(
        self,
        identity_key: IdentityKeyPair,
        registration_id: int,
    ) -> None:
        """
        Initialize Signal Protocol.
        
        Args:
            identity_key: Our identity key pair
            registration_id: Our registration ID
        """
        self.identity_key = identity_key
        self.registration_id = registration_id
        self.sessions: Dict[str, SignalSession] = {}
        self.pre_keys: Dict[int, PreKey] = {}
        self.signed_pre_key: Optional[SignedPreKey] = None
    
    def generate_pre_keys(self, start_id: int = 1, count: int = 100) -> List[PreKey]:
        """
        Generate and store pre-keys.
        
        Args:
            start_id: Starting key ID
            count: Number of pre-keys
            
        Returns:
            List of generated pre-keys
        """
        pre_keys = KeyHelper.generate_pre_keys(start_id, count)
        for pk in pre_keys:
            self.pre_keys[pk.key_id] = pk
        return pre_keys
    
    def generate_signed_pre_key(self, key_id: int) -> SignedPreKey:
        """
        Generate and store a signed pre-key.
        
        Args:
            key_id: Key ID
            
        Returns:
            Generated signed pre-key
        """
        self.signed_pre_key = KeyHelper.generate_signed_pre_key(
            key_id,
            self.identity_key,
        )
        return self.signed_pre_key
    
    def create_session(
        self,
        remote_jid: str,
        their_bundle: KeyBundle,
    ) -> SignalSession:
        """
        Create a new session with a remote user.
        
        Args:
            remote_jid: Their JID
            their_bundle: Their key bundle
            
        Returns:
            New SignalSession
        """
        # Generate ephemeral key
        ephemeral = X25519PrivateKey.generate()
        
        # Load their keys
        their_identity = X25519PublicKey.from_public_bytes(their_bundle.identity_key)
        their_signed_pre_key = X25519PublicKey.from_public_bytes(their_bundle.signed_pre_key)
        
        # Calculate shared secrets
        # DH1 = DH(IKa, SPKb)
        # DH2 = DH(EKa, IKb)  
        # DH3 = DH(EKa, SPKb)
        # DH4 = DH(EKa, OPKb) if available
        
        # For simplicity, we'll use a basic X3DH here
        # Full implementation would follow X3DH spec exactly
        
        from cryptography.hazmat.primitives import serialization
        our_identity_private = X25519PrivateKey.from_private_bytes(
            self.identity_key.get_private_bytes()[:32]  # Use first 32 bytes
        )
        
        dh1 = ephemeral.exchange(their_signed_pre_key)
        dh2 = ephemeral.exchange(their_identity)
        
        # Combine secrets
        master_secret = dh1 + dh2
        if their_bundle.pre_key:
            their_pre_key = X25519PublicKey.from_public_bytes(their_bundle.pre_key)
            dh3 = ephemeral.exchange(their_pre_key)
            master_secret += dh3
        
        # Derive root key
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"\x00" * 32,
            info=b"WhisperX3DH",
        )
        root_key_bytes = hkdf.derive(master_secret)
        root_key = RootKey(key=root_key_bytes)
        
        # Create initial chains
        _, sending_chain = root_key.create_chain(
            their_bundle.signed_pre_key,
            ephemeral,
        )
        
        # Create session state
        state = SessionState(
            local_identity_public=self.identity_key.get_public_bytes(),
            remote_identity_public=their_bundle.identity_key,
            root_key=root_key,
            sending_chain=sending_chain,
            sending_ratchet_key=ephemeral,
        )
        
        session = SignalSession(remote_jid=remote_jid, state=state)
        self.sessions[remote_jid] = session
        
        return session
    
    def get_session(self, remote_jid: str) -> Optional[SignalSession]:
        """Get an existing session."""
        return self.sessions.get(remote_jid)
    
    def has_session(self, remote_jid: str) -> bool:
        """Check if a session exists."""
        return remote_jid in self.sessions
    
    def encrypt_message(
        self,
        remote_jid: str,
        plaintext: bytes,
    ) -> Tuple[bytes, int]:
        """
        Encrypt a message for a recipient.
        
        Args:
            remote_jid: Recipient JID
            plaintext: Message to encrypt
            
        Returns:
            Tuple of (ciphertext, message_type)
        """
        session = self.sessions.get(remote_jid)
        if not session:
            raise RuntimeError(f"No session for {remote_jid}")
        
        return session.encrypt(plaintext)
    
    def decrypt_message(
        self,
        remote_jid: str,
        ciphertext: bytes,
    ) -> bytes:
        """
        Decrypt a message from a sender.
        
        Args:
            remote_jid: Sender JID
            ciphertext: Encrypted message
            
        Returns:
            Decrypted plaintext
        """
        session = self.sessions.get(remote_jid)
        if not session:
            raise RuntimeError(f"No session for {remote_jid}")
        
        return session.decrypt(ciphertext)
    
    def get_key_bundle(self) -> KeyBundle:
        """
        Get our public key bundle for sharing.
        
        Returns:
            Our KeyBundle
        """
        if not self.signed_pre_key:
            raise RuntimeError("No signed pre-key generated")
        
        # Get a random pre-key
        pre_key = None
        pre_key_id = None
        if self.pre_keys:
            pre_key_id = next(iter(self.pre_keys))
            pk = self.pre_keys[pre_key_id]
            pre_key = pk.get_public_bytes()
        
        return KeyBundle(
            registration_id=self.registration_id,
            identity_key=self.identity_key.get_public_bytes(),
            signed_pre_key_id=self.signed_pre_key.key_id,
            signed_pre_key=self.signed_pre_key.get_public_bytes(),
            signed_pre_key_signature=self.signed_pre_key.signature,
            pre_key_id=pre_key_id,
            pre_key=pre_key,
        )

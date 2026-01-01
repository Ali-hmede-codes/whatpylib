"""
Authentication state management for WhatsApp sessions.

The auth state stores all cryptographic keys and session information
needed to maintain a persistent connection without re-scanning QR codes.
"""

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional
import base64

from whatpylib.utils.logger import get_logger

logger = get_logger("auth")


@dataclass
class DeviceKeys:
    """
    Device cryptographic keys.
    
    Attributes:
        noise_key: Noise protocol static keypair
        identity_key: Signal identity keypair
        signed_pre_key: Current signed pre-key
        registration_id: Signal registration ID
    """
    noise_key: Optional[dict[str, str]] = None  # {"private": base64, "public": base64}
    identity_key: Optional[dict[str, str]] = None
    signed_pre_key: Optional[dict[str, Any]] = None
    registration_id: Optional[int] = None
    
    def is_complete(self) -> bool:
        """Check if all required keys are present."""
        return all([
            self.noise_key,
            self.identity_key,
            self.signed_pre_key,
            self.registration_id,
        ])


@dataclass
class SessionData:
    """
    WhatsApp session data.
    
    Attributes:
        server_token: Server authentication token
        client_token: Client authentication token
        enc_key: Encryption key for the session
        mac_key: MAC key for the session
        me: Current user's JID and info
    """
    server_token: Optional[str] = None
    client_token: Optional[str] = None
    enc_key: Optional[str] = None  # base64 encoded
    mac_key: Optional[str] = None  # base64 encoded
    me: Optional[dict[str, Any]] = None  # {"id": JID, "name": name}


@dataclass
class AuthStateData:
    """
    Complete authentication state.
    
    Attributes:
        creds: Device credentials and keys
        session: Session tokens and keys
        pre_keys: Pre-key store (id -> key data)
        sender_keys: Sender keys for group encryption
    """
    creds: DeviceKeys = field(default_factory=DeviceKeys)
    session: SessionData = field(default_factory=SessionData)
    pre_keys: dict[int, dict[str, Any]] = field(default_factory=dict)
    sender_keys: dict[str, dict[str, Any]] = field(default_factory=dict)
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)  # Signal sessions
    
    def is_authenticated(self) -> bool:
        """Check if we have valid session data."""
        return (
            self.creds.is_complete() and
            self.session.server_token is not None and
            self.session.me is not None
        )


class AuthState(ABC):
    """
    Abstract base class for authentication state storage.
    
    Implementations can store state in memory, files, databases, etc.
    """
    
    def __init__(self) -> None:
        self._data = AuthStateData()
    
    @property
    def creds(self) -> DeviceKeys:
        """Get device credentials."""
        return self._data.creds
    
    @property
    def session(self) -> SessionData:
        """Get session data."""
        return self._data.session
    
    @property
    def is_authenticated(self) -> bool:
        """Check if authenticated."""
        return self._data.is_authenticated()
    
    @abstractmethod
    async def load(self) -> bool:
        """
        Load auth state from storage.
        
        Returns:
            True if state was loaded successfully
        """
        pass
    
    @abstractmethod
    async def save(self) -> None:
        """Save auth state to storage."""
        pass
    
    @abstractmethod
    async def clear(self) -> None:
        """Clear all auth state."""
        pass
    
    # Pre-key management
    def get_pre_key(self, key_id: int) -> Optional[dict[str, Any]]:
        """Get a pre-key by ID."""
        return self._data.pre_keys.get(key_id)
    
    def set_pre_key(self, key_id: int, key_data: dict[str, Any]) -> None:
        """Store a pre-key."""
        self._data.pre_keys[key_id] = key_data
    
    def remove_pre_key(self, key_id: int) -> None:
        """Remove a pre-key."""
        self._data.pre_keys.pop(key_id, None)
    
    # Sender key management
    def get_sender_key(self, group_id: str, sender_id: str) -> Optional[dict[str, Any]]:
        """Get a sender key for group encryption."""
        key = f"{group_id}:{sender_id}"
        return self._data.sender_keys.get(key)
    
    def set_sender_key(self, group_id: str, sender_id: str, key_data: dict[str, Any]) -> None:
        """Store a sender key."""
        key = f"{group_id}:{sender_id}"
        self._data.sender_keys[key] = key_data
    
    # Signal session management
    def get_session(self, jid: str) -> Optional[dict[str, Any]]:
        """Get a Signal session for a JID."""
        return self._data.sessions.get(jid)
    
    def set_session(self, jid: str, session_data: dict[str, Any]) -> None:
        """Store a Signal session."""
        self._data.sessions[jid] = session_data
    
    def remove_session(self, jid: str) -> None:
        """Remove a Signal session."""
        self._data.sessions.pop(jid, None)


class MemoryAuthState(AuthState):
    """
    In-memory authentication state.
    
    Useful for testing or temporary sessions. State is lost when
    the program exits.
    """
    
    async def load(self) -> bool:
        """Memory state doesn't persist, always returns False."""
        return False
    
    async def save(self) -> None:
        """No-op for memory state."""
        pass
    
    async def clear(self) -> None:
        """Clear all state."""
        self._data = AuthStateData()


class FileAuthState(AuthState):
    """
    File-based authentication state.
    
    Stores auth state in a JSON file. Suitable for single-account use cases.
    
    Args:
        path: Path to the auth state file or directory
        filename: Filename if path is a directory (default: "auth_state.json")
    """
    
    def __init__(self, path: str | Path, filename: str = "auth_state.json") -> None:
        super().__init__()
        path = Path(path)
        
        if path.is_dir() or not path.suffix:
            self._path = path / filename
        else:
            self._path = path
        
        # Ensure parent directory exists
        self._path.parent.mkdir(parents=True, exist_ok=True)
    
    def _serialize_data(self) -> dict[str, Any]:
        """Serialize auth data to a JSON-compatible dict."""
        return {
            "creds": asdict(self._data.creds),
            "session": asdict(self._data.session),
            "pre_keys": self._data.pre_keys,
            "sender_keys": self._data.sender_keys,
            "sessions": self._data.sessions,
        }
    
    def _deserialize_data(self, data: dict[str, Any]) -> None:
        """Deserialize auth data from a dict."""
        self._data = AuthStateData(
            creds=DeviceKeys(**data.get("creds", {})),
            session=SessionData(**data.get("session", {})),
            pre_keys=data.get("pre_keys", {}),
            sender_keys=data.get("sender_keys", {}),
            sessions=data.get("sessions", {}),
        )
    
    async def load(self) -> bool:
        """Load auth state from file."""
        if not self._path.exists():
            logger.debug(f"Auth state file not found: {self._path}")
            return False
        
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._deserialize_data(data)
            logger.info(f"Loaded auth state from {self._path}")
            return True
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse auth state file: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to load auth state: {e}")
            return False
    
    async def save(self) -> None:
        """Save auth state to file."""
        try:
            data = self._serialize_data()
            
            # Write to temp file first, then rename (atomic on most systems)
            temp_path = self._path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            
            temp_path.replace(self._path)
            logger.debug(f"Saved auth state to {self._path}")
        except Exception as e:
            logger.error(f"Failed to save auth state: {e}")
            raise
    
    async def clear(self) -> None:
        """Clear auth state and delete file."""
        self._data = AuthStateData()
        if self._path.exists():
            self._path.unlink()
            logger.info(f"Deleted auth state file: {self._path}")


class MultiFileAuthState(AuthState):
    """
    Multi-file authentication state.
    
    Stores different components in separate files for better performance
    with large state (many sessions/keys).
    
    Directory structure:
        auth_dir/
            creds.json
            session.json
            keys/
                pre_key_1.json
                ...
            sessions/
                1234567890.json
                ...
    """
    
    def __init__(self, directory: str | Path) -> None:
        super().__init__()
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        
        # Subdirectories
        (self._dir / "keys").mkdir(exist_ok=True)
        (self._dir / "sessions").mkdir(exist_ok=True)
        (self._dir / "sender_keys").mkdir(exist_ok=True)
    
    async def load(self) -> bool:
        """Load auth state from files."""
        creds_file = self._dir / "creds.json"
        session_file = self._dir / "session.json"
        
        if not creds_file.exists():
            return False
        
        try:
            # Load credentials
            with open(creds_file, "r", encoding="utf-8") as f:
                self._data.creds = DeviceKeys(**json.load(f))
            
            # Load session
            if session_file.exists():
                with open(session_file, "r", encoding="utf-8") as f:
                    self._data.session = SessionData(**json.load(f))
            
            # Load pre-keys
            for key_file in (self._dir / "keys").glob("pre_key_*.json"):
                key_id = int(key_file.stem.split("_")[-1])
                with open(key_file, "r", encoding="utf-8") as f:
                    self._data.pre_keys[key_id] = json.load(f)
            
            # Load sessions
            for session_file in (self._dir / "sessions").glob("*.json"):
                jid = session_file.stem
                with open(session_file, "r", encoding="utf-8") as f:
                    self._data.sessions[jid] = json.load(f)
            
            logger.info(f"Loaded auth state from {self._dir}")
            return True
        except Exception as e:
            logger.error(f"Failed to load auth state: {e}")
            return False
    
    async def save(self) -> None:
        """Save auth state to files."""
        try:
            # Save credentials
            with open(self._dir / "creds.json", "w", encoding="utf-8") as f:
                json.dump(asdict(self._data.creds), f, indent=2)
            
            # Save session
            with open(self._dir / "session.json", "w", encoding="utf-8") as f:
                json.dump(asdict(self._data.session), f, indent=2)
            
            # Pre-keys and sessions are saved incrementally in their set methods
            logger.debug(f"Saved auth state to {self._dir}")
        except Exception as e:
            logger.error(f"Failed to save auth state: {e}")
            raise
    
    async def clear(self) -> None:
        """Clear all auth state."""
        import shutil
        self._data = AuthStateData()
        if self._dir.exists():
            shutil.rmtree(self._dir)
            self._dir.mkdir(parents=True, exist_ok=True)
            (self._dir / "keys").mkdir(exist_ok=True)
            (self._dir / "sessions").mkdir(exist_ok=True)
            (self._dir / "sender_keys").mkdir(exist_ok=True)
    
    def set_pre_key(self, key_id: int, key_data: dict[str, Any]) -> None:
        """Store a pre-key (also writes to file)."""
        super().set_pre_key(key_id, key_data)
        key_file = self._dir / "keys" / f"pre_key_{key_id}.json"
        with open(key_file, "w", encoding="utf-8") as f:
            json.dump(key_data, f)
    
    def set_session(self, jid: str, session_data: dict[str, Any]) -> None:
        """Store a session (also writes to file)."""
        super().set_session(jid, session_data)
        # Sanitize JID for filename
        safe_jid = jid.replace("@", "_").replace(":", "_")
        session_file = self._dir / "sessions" / f"{safe_jid}.json"
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f)

"""
Group metadata structures and parsing.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class ParticipantRole(Enum):
    """Role of a group participant."""
    MEMBER = "member"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


class GroupRestriction(Enum):
    """Group restriction settings."""
    ALL = "all"  # All members can do action
    ADMINS = "admins"  # Only admins can do action


@dataclass
class GroupParticipant:
    """
    A participant in a WhatsApp group.
    
    Attributes:
        jid: Participant's JID
        role: Participant's role (member, admin, superadmin)
        is_super_admin: Whether they are the group creator
    """
    jid: str
    role: ParticipantRole = ParticipantRole.MEMBER
    is_super_admin: bool = False
    
    @property
    def is_admin(self) -> bool:
        """Check if participant is an admin (or superadmin)."""
        return self.role in (ParticipantRole.ADMIN, ParticipantRole.SUPERADMIN)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroupParticipant":
        """Create from dictionary."""
        role_str = data.get("admin") or data.get("role", "member")
        
        if role_str == "superadmin":
            role = ParticipantRole.SUPERADMIN
            is_super = True
        elif role_str == "admin":
            role = ParticipantRole.ADMIN
            is_super = False
        else:
            role = ParticipantRole.MEMBER
            is_super = False
        
        return cls(
            jid=data.get("id") or data.get("jid", ""),
            role=role,
            is_super_admin=is_super,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "jid": self.jid,
            "role": self.role.value,
            "isSuperAdmin": self.is_super_admin,
        }


@dataclass
class GroupMetadata:
    """
    Metadata for a WhatsApp group.
    
    Attributes:
        id: Group JID
        subject: Group name/subject
        subject_owner: JID of user who set the subject
        subject_time: When subject was set (unix timestamp)
        description: Group description
        description_id: Description update ID
        description_owner: JID of user who set description
        creation_time: When group was created (unix timestamp)
        owner: JID of group creator
        participants: List of participants
        restrict: Who can send messages
        announce: Who can edit group info
        ephemeral: Disappearing messages duration (seconds, 0 = disabled)
        invite_link: Current invite link (if known)
        linked_parent: Parent group JID (for communities)
        size: Number of participants
    """
    id: str
    subject: str = ""
    subject_owner: Optional[str] = None
    subject_time: int = 0
    description: Optional[str] = None
    description_id: Optional[str] = None
    description_owner: Optional[str] = None
    creation_time: int = 0
    owner: Optional[str] = None
    participants: List[GroupParticipant] = field(default_factory=list)
    restrict: GroupRestriction = GroupRestriction.ALL
    announce: GroupRestriction = GroupRestriction.ALL
    ephemeral: int = 0
    invite_link: Optional[str] = None
    linked_parent: Optional[str] = None
    
    @property
    def size(self) -> int:
        """Get number of participants."""
        return len(self.participants)
    
    def get_admins(self) -> List[GroupParticipant]:
        """Get list of admin participants."""
        return [p for p in self.participants if p.is_admin]
    
    def get_members(self) -> List[GroupParticipant]:
        """Get list of non-admin participants."""
        return [p for p in self.participants if not p.is_admin]
    
    def get_participant(self, jid: str) -> Optional[GroupParticipant]:
        """Get a specific participant by JID."""
        for p in self.participants:
            if p.jid == jid:
                return p
        return None
    
    def is_participant(self, jid: str) -> bool:
        """Check if JID is a participant."""
        return self.get_participant(jid) is not None
    
    def is_admin(self, jid: str) -> bool:
        """Check if JID is an admin."""
        p = self.get_participant(jid)
        return p is not None and p.is_admin
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroupMetadata":
        """Create from dictionary (server response format)."""
        participants = [
            GroupParticipant.from_dict(p)
            for p in data.get("participants", [])
        ]
        
        # Parse restrictions
        restrict = GroupRestriction.ALL
        if data.get("restrict"):
            restrict = GroupRestriction.ADMINS
        
        announce = GroupRestriction.ALL
        if data.get("announce"):
            announce = GroupRestriction.ADMINS
        
        return cls(
            id=data.get("id", ""),
            subject=data.get("subject", ""),
            subject_owner=data.get("subjectOwner"),
            subject_time=data.get("subjectTime", 0),
            description=data.get("desc"),
            description_id=data.get("descId"),
            description_owner=data.get("descOwner"),
            creation_time=data.get("creation", 0),
            owner=data.get("owner"),
            participants=participants,
            restrict=restrict,
            announce=announce,
            ephemeral=data.get("ephemeralDuration", 0),
            linked_parent=data.get("linkedParent"),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "subject": self.subject,
            "subjectOwner": self.subject_owner,
            "subjectTime": self.subject_time,
            "desc": self.description,
            "descId": self.description_id,
            "descOwner": self.description_owner,
            "creation": self.creation_time,
            "owner": self.owner,
            "participants": [p.to_dict() for p in self.participants],
            "restrict": self.restrict == GroupRestriction.ADMINS,
            "announce": self.announce == GroupRestriction.ADMINS,
            "ephemeralDuration": self.ephemeral,
            "linkedParent": self.linked_parent,
            "size": self.size,
        }


@dataclass
class GroupInvite:
    """
    Group invite information.
    
    Attributes:
        code: Invite code
        expiration: Expiration timestamp (0 = never)
        group_jid: Group JID
    """
    code: str
    expiration: int = 0
    group_jid: Optional[str] = None
    
    @property
    def link(self) -> str:
        """Get the full invite link."""
        return f"https://chat.whatsapp.com/{self.code}"
    
    @classmethod
    def from_link(cls, link: str) -> "GroupInvite":
        """Parse an invite from a link."""
        # Handle various link formats
        if "chat.whatsapp.com/" in link:
            code = link.split("chat.whatsapp.com/")[-1].split("?")[0].strip("/")
        else:
            code = link.strip("/")
        
        return cls(code=code)

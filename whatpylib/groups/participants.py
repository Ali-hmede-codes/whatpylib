"""
Participant management for WhatsApp groups.
"""

from dataclasses import dataclass
from typing import List, Optional, Callable, Awaitable
from enum import Enum

from whatpylib.connection.binary import BinaryNode
from whatpylib.groups.metadata import GroupParticipant, ParticipantRole
from whatpylib.utils.jid import parse_jid, JID
from whatpylib.utils.logger import get_logger

logger = get_logger("groups.participants")


class ParticipantAction(Enum):
    """Actions that can be performed on participants."""
    ADD = "add"
    REMOVE = "remove"
    PROMOTE = "promote"
    DEMOTE = "demote"


@dataclass
class ParticipantUpdate:
    """
    Update about a participant change.
    
    Attributes:
        group_jid: Group JID
        participant_jid: Participant JID
        action: What happened
        actor_jid: Who performed the action (if known)
    """
    group_jid: str
    participant_jid: str
    action: ParticipantAction
    actor_jid: Optional[str] = None


class ParticipantManager:
    """
    Manager for group participant operations.
    """
    
    def __init__(
        self,
        send_node: Callable[[BinaryNode], Awaitable[None]],
        send_and_wait: Callable[[BinaryNode, Optional[float]], Awaitable[BinaryNode]],
    ) -> None:
        """
        Initialize the participant manager.
        
        Args:
            send_node: Function to send a binary node
            send_and_wait: Function to send a node and wait for response
        """
        self._send_node = send_node
        self._send_and_wait = send_and_wait
    
    async def add_participants(
        self,
        group_jid: str,
        participant_jids: List[str],
    ) -> List[str]:
        """
        Add participants to a group.
        
        Args:
            group_jid: Group JID
            participant_jids: List of JIDs to add
            
        Returns:
            List of JIDs that were successfully added
        """
        return await self._modify_participants(
            group_jid,
            participant_jids,
            ParticipantAction.ADD,
        )
    
    async def remove_participants(
        self,
        group_jid: str,
        participant_jids: List[str],
    ) -> List[str]:
        """
        Remove participants from a group.
        
        Args:
            group_jid: Group JID
            participant_jids: List of JIDs to remove
            
        Returns:
            List of JIDs that were successfully removed
        """
        return await self._modify_participants(
            group_jid,
            participant_jids,
            ParticipantAction.REMOVE,
        )
    
    async def promote_participants(
        self,
        group_jid: str,
        participant_jids: List[str],
    ) -> List[str]:
        """
        Promote participants to admin.
        
        Args:
            group_jid: Group JID
            participant_jids: List of JIDs to promote
            
        Returns:
            List of JIDs that were successfully promoted
        """
        return await self._modify_participants(
            group_jid,
            participant_jids,
            ParticipantAction.PROMOTE,
        )
    
    async def demote_participants(
        self,
        group_jid: str,
        participant_jids: List[str],
    ) -> List[str]:
        """
        Demote participants from admin.
        
        Args:
            group_jid: Group JID
            participant_jids: List of JIDs to demote
            
        Returns:
            List of JIDs that were successfully demoted
        """
        return await self._modify_participants(
            group_jid,
            participant_jids,
            ParticipantAction.DEMOTE,
        )
    
    async def _modify_participants(
        self,
        group_jid: str,
        participant_jids: List[str],
        action: ParticipantAction,
    ) -> List[str]:
        """
        Internal method to modify participants.
        
        Args:
            group_jid: Group JID
            participant_jids: List of participant JIDs
            action: Action to perform
            
        Returns:
            List of JIDs that were successfully modified
        """
        if not participant_jids:
            return []
        
        # Normalize JIDs
        normalized_jids = []
        for jid in participant_jids:
            if "@" not in jid:
                jid = f"{jid}@s.whatsapp.net"
            normalized_jids.append(jid)
        
        # Build participant nodes
        participant_nodes = [
            BinaryNode(
                tag="participant",
                attrs={"jid": jid},
            )
            for jid in normalized_jids
        ]
        
        # Build request
        from whatpylib.messages.types import generate_message_id
        
        node = BinaryNode(
            tag="iq",
            attrs={
                "id": generate_message_id(),
                "type": "set",
                "xmlns": "w:g2",
                "to": group_jid,
            },
            content=[
                BinaryNode(
                    tag=action.value,
                    attrs={},
                    content=participant_nodes,
                )
            ],
        )
        
        # Send and wait for response
        try:
            response = await self._send_and_wait(node, 30.0)
            
            # Parse response to get successful JIDs
            successful = []
            if response and response.content:
                for child in response.content:
                    if isinstance(child, BinaryNode) and child.tag == action.value:
                        for participant in (child.content or []):
                            if isinstance(participant, BinaryNode):
                                if participant.get_attr("type") != "error":
                                    successful.append(participant.get_attr("jid"))
            
            return successful if successful else normalized_jids
            
        except Exception as e:
            logger.error(f"Failed to {action.value} participants: {e}")
            raise
    
    def parse_participant_update(
        self,
        node: BinaryNode,
    ) -> Optional[ParticipantUpdate]:
        """
        Parse a participant update notification.
        
        Args:
            node: Notification node
            
        Returns:
            ParticipantUpdate or None
        """
        if node.tag != "notification":
            return None
        
        notification_type = node.get_attr("type")
        if notification_type not in ("w:gp2", "participant"):
            return None
        
        group_jid = node.get_attr("from")
        actor_jid = node.get_attr("participant")
        
        # Find the action node
        action = None
        participant_jid = None
        
        for child in (node.content or []):
            if isinstance(child, BinaryNode):
                if child.tag == "add":
                    action = ParticipantAction.ADD
                elif child.tag == "remove":
                    action = ParticipantAction.REMOVE
                elif child.tag == "promote":
                    action = ParticipantAction.PROMOTE
                elif child.tag == "demote":
                    action = ParticipantAction.DEMOTE
                
                if action and child.content:
                    for p in child.content:
                        if isinstance(p, BinaryNode) and p.tag == "participant":
                            participant_jid = p.get_attr("jid")
                            break
                break
        
        if action and participant_jid:
            return ParticipantUpdate(
                group_jid=group_jid,
                participant_jid=participant_jid,
                action=action,
                actor_jid=actor_jid,
            )
        
        return None

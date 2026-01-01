"""
Group manager for general group operations.
"""

from typing import List, Optional, Callable, Awaitable, Dict, Any

from whatpylib.connection.binary import BinaryNode
from whatpylib.groups.metadata import GroupMetadata
from whatpylib.utils.logger import get_logger
from whatpylib.messages.types import generate_message_id

logger = get_logger("groups.manager")


class GroupManager:
    """
    Manager for general group operations (metadata, creation, settings).
    """
    
    def __init__(
        self,
        send_node: Callable[[BinaryNode], Awaitable[None]],
        send_and_wait: Callable[[BinaryNode, Optional[float]], Awaitable[BinaryNode]],
    ) -> None:
        """
        Initialize the group manager.
        
        Args:
            send_node: Function to send a binary node
            send_and_wait: Function to send a node and wait for response
        """
        self._send_node = send_node
        self._send_and_wait = send_and_wait
    
    async def get_group_metadata(self, group_jid: str) -> GroupMetadata:
        """
        Get metadata for a group.
        
        Args:
            group_jid: Group JID
            
        Returns:
            GroupMetadata object
        """
        node = BinaryNode(
            tag="iq",
            attrs={
                "id": generate_message_id(),
                "type": "get",
                "xmlns": "w:g2",
                "to": group_jid,
            },
            content=[BinaryNode(tag="query", attrs={"request": "interactive"})],
        )
        
        response = await self._send_and_wait(node, 30.0)
        
        # Parse response
        # Note: This assumes the response structure matches what we expect
        # Real implementation would need robust error handling
        if response and response.content:
            for child in response.content:
                if isinstance(child, BinaryNode) and child.tag == "group":
                    # Convert attributes to dict and parse
                    data = child.attrs.copy()
                    
                    # Parse participants
                    participants = []
                    if child.content:
                        for p in child.content:
                            if isinstance(p, BinaryNode) and p.tag == "participant":
                                participants.append(p.attrs)
                    
                    data["participants"] = participants
                    data["id"] = group_jid
                    
                    return GroupMetadata.from_dict(data)
        
        raise RuntimeError(f"Failed to get metadata for {group_jid}")
    
    async def create_group(
        self,
        subject: str,
        participants: List[str],
    ) -> str:
        """
        Create a new group.
        
        Args:
            subject: Group subject (name)
            participants: Initial participant JIDs
            
        Returns:
            New group JID
        """
        # Normalize participants
        normalized_jids = []
        for jid in participants:
            if "@" not in jid:
                jid = f"{jid}@s.whatsapp.net"
            normalized_jids.append(BinaryNode(tag="participant", attrs={"jid": jid}))
        
        node = BinaryNode(
            tag="iq",
            attrs={
                "id": generate_message_id(),
                "type": "set",
                "xmlns": "w:g2",
                "to": "g.us",
            },
            content=[
                BinaryNode(
                    tag="create",
                    attrs={"subject": subject},
                    content=normalized_jids,
                )
            ],
        )
        
        response = await self._send_and_wait(node, 30.0)
        
        # Parse response to get group JID
        if response and response.content:
            for child in response.content:
                if isinstance(child, BinaryNode) and child.tag == "group":
                    return child.get_attr("id")
        
        raise RuntimeError("Failed to create group")
    
    async def update_subject(
        self,
        group_jid: str,
        subject: str,
    ) -> None:
        """
        Update group subject.
        
        Args:
            group_jid: Group JID
            subject: New subject
        """
        node = BinaryNode(
            tag="iq",
            attrs={
                "id": generate_message_id(),
                "type": "set",
                "xmlns": "w:g2",
                "to": group_jid,
            },
            content=[BinaryNode(tag="subject", attrs={}, content=subject.encode("utf-8"))],
        )
        
        await self._send_and_wait(node, 30.0)
    
    async def update_description(
        self,
        group_jid: str,
        description: str,
    ) -> None:
        """
        Update group description.
        
        Args:
            group_jid: Group JID
            description: New description
        """
        # Description update is slightly different, uses distinct ID
        desc_id = generate_message_id()[:12]
        
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
                    tag="description",
                    attrs={"id": desc_id},
                    content=[BinaryNode(tag="body", attrs={}, content=description.encode("utf-8"))],
                )
            ],
        )
        
        await self._send_and_wait(node, 30.0)
    
    async def leave_group(self, group_jid: str) -> None:
        """
        Leave a group.
        
        Args:
            group_jid: Group JID
        """
        node = BinaryNode(
            tag="iq",
            attrs={
                "id": generate_message_id(),
                "type": "set",
                "xmlns": "w:g2",
                "to": "g.us",
            },
            content=[
                BinaryNode(
                    tag="leave",
                    attrs={},
                    content=[BinaryNode(tag="group", attrs={"id": group_jid})],
                )
            ],
        )
        
        await self._send_and_wait(node, 30.0)

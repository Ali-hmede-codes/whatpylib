import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from whatpylib.groups.manager import GroupManager
from whatpylib.connection.binary import BinaryNode

@pytest.fixture
def mock_send_node():
    return AsyncMock()

@pytest.fixture
def mock_send_and_wait():
    return AsyncMock()

@pytest.fixture
def group_manager(mock_send_node, mock_send_and_wait):
    return GroupManager(
        send_node=mock_send_node,
        send_and_wait=mock_send_and_wait
    )

@pytest.mark.asyncio
async def test_create_group(group_manager, mock_send_and_wait):
    """Test group creation."""
    # Setup response
    mock_response = BinaryNode(
        tag="iq",
        attrs={"type": "result"},
        content=[
            BinaryNode(tag="group", attrs={"id": "123456@g.us"}, content=[])
        ]
    )
    mock_send_and_wait.return_value = mock_response
    
    # Call
    group_id = await group_manager.create_group("Test Group", ["12345678@s.whatsapp.net"])
    
    # Verify
    assert group_id == "123456@g.us"
    mock_send_and_wait.assert_called_once()
    call_args = mock_send_and_wait.call_args
    node = call_args[0][0]
    assert node.tag == "iq"
    assert node.attrs["type"] == "set"
    assert node.attrs["xmlns"] == "w:g2"
    
    # Check content structure for create
    # <create subject="Test Group"><participant jid="..."/></create>
    create_node = node.content[0]
    assert create_node.tag == "create"
    assert create_node.attrs["subject"] == "Test Group"
    assert create_node.content[0].tag == "participant"
    assert create_node.content[0].attrs["jid"] == "12345678@s.whatsapp.net"

@pytest.mark.asyncio
async def test_participant_manager_add(mock_send_node, mock_send_and_wait):
    """Test adding participants via ParticipantManager."""
    from whatpylib.groups.participants import ParticipantManager
    manager = ParticipantManager(send_node=mock_send_node, send_and_wait=mock_send_and_wait)
    
    # Setup response
    mock_send_and_wait.return_value = BinaryNode(
        tag="iq",
        attrs={"type": "result"},
        content=[
             BinaryNode(tag="add", attrs={}, content=[
                 BinaryNode(tag="participant", attrs={"jid": "98765432@s.whatsapp.net"}, content=None)
             ])
        ]
    )
    
    # Call
    result = await manager.add_participants("123456@g.us", ["98765432@s.whatsapp.net"])
    
    # Verify
    assert "98765432@s.whatsapp.net" in result
    mock_send_and_wait.assert_called_once()
    node = mock_send_and_wait.call_args[0][0]
    assert node.tag == "iq"
    assert node.attrs["to"] == "123456@g.us"
    
    add_node = node.content[0]
    assert add_node.tag == "add"
    assert add_node.content[0].attrs["jid"] == "98765432@s.whatsapp.net"

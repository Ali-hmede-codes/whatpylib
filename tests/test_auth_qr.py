
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from whatpylib.client import WhatsAppClient
from whatpylib.connection.binary import BinaryNode
from whatpylib.auth.state import MemoryAuthState
from whatpylib.config import Config
import base64

@pytest.mark.asyncio
async def test_authenticate_qr_flow():
    # Setup mocks
    mock_qr_handler = MagicMock()
    mock_qr_handler.handle_qr = AsyncMock()
    
    # Initialize client with mocks
    client = WhatsAppClient(
        auth_state=MemoryAuthState(),
        config=Config(qr_timeout=1.0) # Short timeout for test
    )
    client._socket = MagicMock() # Mock connected socket logic if needed
    client._qr_handler = mock_qr_handler
    
    # We need to run _authenticate in a background task so we can emit events
    auth_task = asyncio.create_task(client._authenticate())
    
    # Wait for the handler to be registered
    # We poll until "message.received" has at least one listener
    for _ in range(10):
        if client.events.listener_count("message.received") > 0:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail("Timeout waiting for message handler registration")
    
    # Simulate receiving the "failure" node with 401 and ref
    # <failure reason="401"><ref>THE_REF_STRING</ref></failure>
    ref_content = b"TEST_QR_REF_STRING"
    ref_node = BinaryNode(tag="ref", attrs={}, content=ref_content)
    failure_node = BinaryNode(
        tag="failure", 
        attrs={"reason": "401"}, 
        content=[ref_node] 
    )
    
    # Emit the event
    await client.events.emit("message.received", failure_node)
    
    # Now simulate auth.success to finish the task
    # (In real life, the user scans, and we get a success node which triggers this event)
    # We delay slightly to ensure QR handler is called first
    await asyncio.sleep(0.1)
    
    # Verify QR handler was called
    mock_qr_handler.handle_qr.assert_called_once()
    qr_data = mock_qr_handler.handle_qr.call_args[0][0]
    
    assert qr_data.ref == "TEST_QR_REF_STRING"
    assert qr_data.client_id is not None
    assert qr_data.public_key is not None
    
    # Emit success to unblock wait_for("auth.success")
    await client.events.emit("auth.success", None)
    
    # Wait for auth task to complete
    await auth_task
    
    # Verify auth state saved
    assert client.auth_state.creds.noise_key is not None
    assert client.auth_state.creds.identity_key is not None

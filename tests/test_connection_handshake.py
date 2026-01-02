import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from whatpylib.connection.socket import WhatsAppSocket
from whatpylib.config import Config

@pytest.fixture
def mock_ws_connect():
    with patch("websockets.connect") as mock:
        yield mock

@pytest.mark.asyncio
async def test_connect_success(mock_ws_connect):
    """Test successful connection flow."""
    # Mock WebSocket
    mock_ws = AsyncMock()
    
    # Correctly mock websockets.connect as an awaitable that returns the socket
    async def connect_mock(*args, **kwargs):
        return mock_ws
    mock_ws_connect.side_effect = connect_mock
    
    # Mock Noise Handler
    with patch("whatpylib.connection.socket.NoiseHandler") as MockNoiseHandler, \
         patch.object(WhatsAppSocket, "_start_background_tasks") as mock_start_tasks:
        mock_noise = MockNoiseHandler.return_value
        mock_noise.create_handshake_message_1.return_value = b"handshake_1"
        # Mock successful handshake 2 processing
        mock_noise.process_handshake_message_2.return_value = b"server_hello"
        mock_noise.create_handshake_message_3.return_value = b"handshake_3"
        
        # Setup socket
        socket = WhatsAppSocket(config=Config())
        
        # Mock receiving handshake 2
        mock_ws.recv.return_value = b"handshake_2_response"
        
        # Connect
        await socket.connect()
        
        # Verification
        assert socket.is_connected
        mock_ws.send.assert_any_call(b"handshake_1")
        mock_noise.process_handshake_message_2.assert_called_once_with(b"handshake_2_response")
        mock_ws.send.assert_any_call(b"handshake_3")
        mock_start_tasks.assert_called_once()

@pytest.mark.asyncio
async def test_handshake_too_short_reproduction(mock_ws_connect):
    """Reproduction case for 'Handshake 2 message too short'."""
    # Mock WebSocket
    mock_ws = AsyncMock()
    
    async def connect_mock(*args, **kwargs):
        return mock_ws
    mock_ws_connect.side_effect = connect_mock
    
    socket = WhatsAppSocket(config=Config())
    
    # Mock receiving short handshake 2 (fake server response)
    mock_ws.recv.return_value = b"\x88\x02\x03\xf3" # The 4 bytes from user report
    
    # We rely on the REAL NoiseHandler (not mocked) to raise ValueError
    # because we want to test that socket.connect bubbles/handles it.
    
    with pytest.raises(ValueError, match="Handshake 2 message too short"):
         await socket.connect()

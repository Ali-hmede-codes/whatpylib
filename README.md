# WhatPyLib

A Python library for WhatsApp Web communication using the Multi-Device protocol.

> ⚠️ **Disclaimer**: This is an unofficial library. WhatsApp may change their protocol at any time, potentially breaking functionality. Using this library may violate WhatsApp's Terms of Service.

## Features

- 🔌 **WebSocket-based** - Direct connection to WhatsApp servers
- 🔐 **End-to-end encrypted** - Uses Signal Protocol
- 📱 **Multi-device support** - No phone required after linking
- 🔄 **Auto-reconnect** - Automatic session restoration
- 📨 **Full messaging** - Text, media, location, contacts, polls
- 👥 **Group support** - Manage participants, settings
- ⚡ **Async-first** - Built for Python 3.10+

## Installation

```bash
pip install whatpylib
```

Or from source:

```bash
git clone https://github.com/whatpylib/whatpylib.git
cd whatpylib
pip install -e .
```

## Quick Start

```python
import asyncio
from whatpylib import WhatsAppClient

async def main():
    # Create client with persistent auth
    client = WhatsAppClient(auth_state_path="./auth")
    
    # Register message handler
    @client.on("message")
    async def on_message(msg):
        print(f"Received from {msg.sender_jid}: {msg.text}")
        
        # Echo back
        if msg.text.lower() == "ping":
            await client.send_message(msg.chat_jid, "pong!")
    
    # Connect (will show QR code on first run)
    await client.connect()
    
    # Keep running
    await client.wait_until_disconnect()

asyncio.run(main())
```

## Sending Messages

### Text Messages

```python
# Simple text
await client.send_message("1234567890", "Hello!")

# With mentions
from whatpylib import MessageBuilder

msg = (
    MessageBuilder()
    .to("group_id@g.us")
    .text("Hello @user!")
    .mention(["user@s.whatsapp.net"])
    .build()
)
await client.send_message("group_id@g.us", msg)
```

### Media Messages

```python
# Send image
await client.send_image("1234567890", "photo.jpg", caption="Check this out!")

# Send voice note
await client.send_audio("1234567890", "voice.ogg", ptt=True)

# Send document
await client.send_document("1234567890", "file.pdf", filename="Report.pdf")

# Send location
await client.send_location("1234567890", 40.7128, -74.0060, name="New York")
```

### Interactive Messages

```python
# React to a message
await client.react(message, "👍")

# Reply to a message
await client.reply(message, "I agree!")

# Send poll
await client.send_poll(
    "group@g.us",
    "What's for lunch?",
    ["Pizza", "Burger", "Sushi"],
)
```

## Events

Subscribe to various events:

```python
@client.on("message")
async def on_message(msg):
    """New message received"""
    pass

@client.on("message.reaction")
async def on_reaction(reaction):
    """Reaction added/removed"""
    pass

@client.on("group.participants.update")
async def on_group_update(update):
    """Group members changed"""
    pass

@client.on("presence.update")
async def on_presence(presence):
    """User online/offline/typing"""
    pass

@client.on("connection.update")
async def on_connection(update):
    """Connection state changed"""
    pass
```

## Groups

```python
# Get group info
metadata = await client.get_group_metadata("group@g.us")

# Create group
group_jid = await client.create_group("My Group", ["user1", "user2"])

# Manage participants
await client.add_group_participants("group@g.us", ["user3"])
await client.remove_group_participants("group@g.us", ["user2"])
await client.promote_group_participants("group@g.us", ["user1"])

# Update group settings
await client.update_group_subject("group@g.us", "New Name")
await client.update_group_description("group@g.us", "New Description")

# Get invite link
link = await client.get_group_invite_link("group@g.us")
```

## Presence

```python
# Update your presence
await client.update_presence("available")  # or "unavailable"

# Send typing indicator
await client.send_typing("user@s.whatsapp.net")

# Send recording indicator
await client.send_recording("user@s.whatsapp.net")
```

## Configuration

```python
from whatpylib import WhatsAppClient, Config

config = Config(
    connect_timeout=30,
    qr_timeout=60,
    auto_reconnect=True,
    max_reconnect_attempts=5,
    log_level="DEBUG",
)

client = WhatsAppClient(
    auth_state_path="./auth",
    config=config,
    print_qr=True,
)
```

## Authentication

### QR Code (Default)

On first run, a QR code will be displayed. Scan it with WhatsApp:
1. Open WhatsApp on your phone
2. Go to Settings > Linked Devices
3. Tap "Link a Device"
4. Scan the QR code

### Pairing Code

```python
from whatpylib.auth import PairingCodeHandler

handler = PairingCodeHandler()
code = await handler.request_pairing_code("1234567890")
# Enter the code in WhatsApp on your phone
```

## Storage

```python
# File-based (default)
from whatpylib import FileAuthState
auth = FileAuthState("./auth")

# Multi-file (better for many sessions)
from whatpylib.auth import MultiFileAuthState
auth = MultiFileAuthState("./auth_dir")

# Memory (no persistence)
from whatpylib import MemoryAuthState
auth = MemoryAuthState()

# Custom database
from whatpylib.auth import AuthState

class DatabaseAuthState(AuthState):
    async def load(self) -> bool:
        # Load from database
        pass
    
    async def save(self) -> None:
        # Save to database
        pass
    
    async def clear(self) -> None:
        # Clear from database
        pass
```

## Requirements

- Python 3.10+
- websockets
- cryptography
- protobuf
- qrcode
- Pillow
- aiohttp
- pydantic

## License

MIT License

## Disclaimer

This project is not affiliated with, endorsed by, or connected to WhatsApp or Meta Platforms, Inc. Use responsibly and in accordance with WhatsApp's Terms of Service.

"""
Simple Echo Bot Example

This example shows how to create a basic echo bot that responds to messages.
"""

import asyncio
from whatpylib import WhatsAppClient


async def main():
    # Create client with file-based auth storage
    client = WhatsAppClient(
        auth_state_path="./auth_state",
        print_qr=True,
        log_level="INFO",
    )
    
    # Register message handler
    @client.on("message")
    async def on_message(msg):
        # Skip our own messages
        if msg.from_me:
            return
        
        print(f"[{msg.sender_jid}] {msg.text}")
        
        # Echo the message back
        if msg.text:
            await client.send_message(msg.chat_jid, f"Echo: {msg.text}")
    
    # Register connection handler
    @client.on("connection.update")
    async def on_connection(update):
        print(f"Connection: {update}")
    
    try:
        # Connect and run
        print("Connecting to WhatsApp...")
        await client.connect()
        print("Connected! Waiting for messages...")
        
        # Keep running until disconnected
        await client.wait_until_disconnect()
        
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

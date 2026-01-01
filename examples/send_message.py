"""
Send Message Example

This example shows how to send various types of messages.
"""

import asyncio
from whatpylib import WhatsAppClient, MessageBuilder


async def main():
    # Create client
    client = WhatsAppClient(auth_state_path="./auth_state")
    
    try:
        await client.connect()
        
        # Target phone number (replace with actual number)
        to = "1234567890"  # Without @s.whatsapp.net suffix
        
        # ==== Text Messages ====
        
        # Simple text
        await client.send_message(to, "Hello from WhatPyLib! 👋")
        
        # Message with builder
        msg = (
            MessageBuilder()
            .to(to)
            .text("This message was built with MessageBuilder")
            .build()
        )
        await client.send_message(to, msg)
        
        # ==== Media Messages ====
        
        # Image with caption
        # await client.send_image(to, "photo.jpg", caption="Check this out!")
        
        # Document
        # await client.send_document(to, "file.pdf", filename="Important.pdf")
        
        # Voice note
        # await client.send_audio(to, "voice.ogg", ptt=True)
        
        # ==== Location ====
        
        await client.send_location(
            to,
            latitude=40.7128,
            longitude=-74.0060,
            name="New York City"
        )
        
        # ==== Poll ====
        
        await client.send_poll(
            to,
            question="What's your favorite programming language?",
            options=["Python", "JavaScript", "Go", "Rust"],
        )
        
        print("Messages sent successfully!")
        
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

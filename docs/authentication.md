# Authentication Guide

This guide explains how authentication works in `WhatPyLib` and how to manage sessions securely.

## Overview

Authentication in WhatsApp Web involves:
1.  **WebSocket Connection**: Establishing a persistent connection to WhatsApp servers.
2.  **Noise Handshake**: A secure cryptographic handshake (Noise_XX) to encrypt the connection.
3.  **QR Code / Pairing**: Proving identity by scanning a QR code or entering a pairing code.
4.  **Session Persistence**: Saving keys and tokens to avoid re-authenticating.

`WhatPyLib` handles most of this automatically via the `WhatsAppClient` class.

## The "Socket"

You asked about "creating a socket". In `WhatPyLib`, you **do not** need to manually create a socket. The `WhatsAppClient` manages the WebSocket connection for you.

When you call `await client.connect()`, the library:
1.  Connects to `wss://web.whatsapp.com/ws/chat`.
2.  Performs the Noise handshake using keys from your `AuthState`.
3.  Sends a login node to the server.

## Step-by-Step Authentication

### 1. Basic Setup (First Run)

On the first run, you need to scan a QR code.

```python
import asyncio
from whatpylib import WhatsAppClient

async def main():
    # Initialize client with a path to save session data
    # This will create a 'auth_info.json' file in the current directory
    client = WhatsAppClient(auth_state_path="./auth_info.json")
    
    # Connect to WhatsApp
    # This will print a QR code to the terminal if not authenticated
    print("Connecting... Please scan the QR code if prompted.")
    await client.connect()
    
    # Wait for the connection to close (or keep running)
    await client.wait_until_disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. Session Persistence

The key to "authenticating in the right way" is **saving your session**.

*   **FileAuthState**: Saves everything to a single JSON file. Good for simple bots.
    ```python
    client = WhatsAppClient(auth_state_path="./my_session.json")
    ```

*   **MultiFileAuthState**: Saves data to a directory with separate files for keys and sessions. Better for production or heavy usage.
    ```python
    from whatpylib.auth import MultiFileAuthState
    
    auth = MultiFileAuthState("./session_data_dir")
    client = WhatsAppClient(auth_state=auth)
    ```

**How it works:**
*   **First Run**: The client sees no session data. It generates new keys, connects, and shows a QR code. After you scan, it saves the session tokens.
*   **Next Run**: The client loads the saved data. It uses the stored keys to reconnect immediately without a QR code.

### 3. Pairing Code (Alternative to QR)

If you can't scan a QR code (e.g., server has no display), use a pairing code.

```python
import asyncio
from whatpylib import WhatsAppClient
from whatpylib.auth import PairingCodeHandler

async def main():
    client = WhatsAppClient(auth_state_path="./auth.json", print_qr=False)
    
    # Start connection in background
    asyncio.create_task(client.connect())
    
    # Wait a moment for connection to initialize
    await asyncio.sleep(2)
    
    # Request pairing code
    if not client.is_authenticated():
        handler = PairingCodeHandler(client)
        # Phone number must include country code, e.g., "1234567890"
        code = await handler.request_pairing_code("YOUR_PHONE_NUMBER")
        print(f"Pairing Code: {code}")
        print("Enter this code on your phone: Linked Devices > Link a Device > Link with phone number instead")
    
    await client.wait_until_disconnect()
```

## Troubleshooting

*   **"Socket Closed"**: If the connection drops immediately, check your internet connection.
*   **"401 Unauthorized"**: Your session might be invalid (e.g., logged out from phone). Delete your auth file (e.g., `auth.json`) and re-scan.
*   **QR Code not scanning**: Ensure your terminal supports UTF-8 or use a library to save the QR as an image.

## Advanced: Custom Storage

If you need to save sessions to a database (Redis, SQL, etc.), implement the `AuthState` interface:

```python
from whatpylib.auth import AuthState

class MyDatabaseAuth(AuthState):
    async def load(self) -> bool:
        # Load JSON from DB and call self._deserialize_data(data)
        return True
        
    async def save(self) -> None:
        # Get data via self._serialize_data() and save to DB
        pass
        
    async def clear(self) -> None:
        # Delete from DB
        pass
```

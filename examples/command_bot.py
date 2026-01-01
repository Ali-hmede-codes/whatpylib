"""
Command Bot Example

A more advanced bot that responds to commands.
"""

import asyncio
from whatpylib import WhatsAppClient


# Command handlers
COMMANDS = {}


def command(name):
    """Decorator to register a command handler."""
    def decorator(func):
        COMMANDS[name] = func
        return func
    return decorator


@command("ping")
async def cmd_ping(client, msg, args):
    """Responds with pong."""
    await client.reply(msg, "🏓 Pong!")


@command("echo")
async def cmd_echo(client, msg, args):
    """Echoes the message back."""
    text = " ".join(args) if args else "Nothing to echo!"
    await client.reply(msg, text)


@command("help")
async def cmd_help(client, msg, args):
    """Shows available commands."""
    help_text = "📋 *Available Commands:*\n\n"
    for name, func in COMMANDS.items():
        doc = func.__doc__ or "No description"
        help_text += f"• *!{name}* - {doc}\n"
    await client.reply(msg, help_text)


@command("poll")
async def cmd_poll(client, msg, args):
    """Creates a poll. Usage: !poll question | option1 | option2 | ..."""
    if not args:
        await client.reply(msg, "Usage: !poll question | option1 | option2 | ...")
        return
    
    parts = " ".join(args).split("|")
    if len(parts) < 3:
        await client.reply(msg, "Need at least a question and 2 options!")
        return
    
    question = parts[0].strip()
    options = [p.strip() for p in parts[1:]]
    
    await client.send_poll(msg.chat_jid, question, options)


@command("react")
async def cmd_react(client, msg, args):
    """Reacts to your message with an emoji."""
    emoji = args[0] if args else "👍"
    await client.react(msg, emoji)


async def handle_message(client, msg):
    """Process incoming messages."""
    # Skip our own messages and non-text
    if msg.from_me or not msg.text:
        return
    
    text = msg.text.strip()
    
    # Check for command prefix
    if not text.startswith("!"):
        return
    
    # Parse command and args
    parts = text[1:].split()
    if not parts:
        return
    
    cmd_name = parts[0].lower()
    args = parts[1:]
    
    # Execute command
    if cmd_name in COMMANDS:
        try:
            await COMMANDS[cmd_name](client, msg, args)
        except Exception as e:
            await client.reply(msg, f"❌ Error: {e}")
    else:
        await client.reply(msg, f"Unknown command: !{cmd_name}\nType !help for available commands.")


async def main():
    client = WhatsAppClient(
        auth_state_path="./auth_state",
        print_qr=True,
    )
    
    @client.on("message")
    async def on_message(msg):
        await handle_message(client, msg)
    
    @client.on("connection.update")
    async def on_connection(update):
        conn = update.get("connection")
        if conn:
            print(f"Connection: {conn}")
    
    try:
        print("Starting Command Bot...")
        print("Commands: !ping, !echo, !help, !poll, !react")
        await client.connect()
        await client.wait_until_disconnect()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

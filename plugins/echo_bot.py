"""
Echo Bot Plugin for LXMF-CLI
Automatically replies to messages with "Echo: <message>"
Can be toggled on/off with the 'echo' command
"""
import time
import sys
import os

class Plugin:
    def __init__(self, client):
        """Initialize the echo bot plugin"""
        self.client = client
        self.commands = ['echo']  # Commands this plugin handles
        self.description = "Auto-reply bot - echoes received messages"
        self.enabled = False  # Start disabled by default
        
        print(f"Echo Bot loaded! Use 'echo on' to activate")
    
    def on_message(self, message, msg_data):
        """
        Handle incoming messages
        Returns True to suppress normal notification, False to allow it
        """
        # Only process if echo bot is enabled
        if not self.enabled:
            return False  # Let normal message handling occur
        
        # Don't echo our own messages
        if msg_data['direction'] == 'outbound':
            return False
        
        # Get the message content
        content = msg_data.get('content', '')
        source_hash = msg_data['source_hash']
        
        # Don't echo empty messages
        if not content or not content.strip():
            return False
        
        # Check if sender is blacklisted (don't echo to blocked users)
        if self.client.is_blacklisted(source_hash):
            return False
        
        # Create echo reply
        reply_text = f"🔄 Echo: {content}"
        
        # Send the echo back
        try:
            # Small delay to seem more natural
            time.sleep(0.5)
            
            # Suppress ALL output from send_message
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            
            try:
                # Redirect to devnull
                devnull = open(os.devnull, 'w', encoding='utf-8', errors='ignore')
                sys.stdout = devnull
                sys.stderr = devnull
                
                # Send the reply
                self.client.send_message(source_hash, reply_text)
                
            finally:
                # Restore output streams
                devnull.close()
                sys.stdout = old_stdout
                sys.stderr = old_stderr
            
            # Show in console that we echoed
            sender_display = self.client.format_contact_display_short(source_hash)
            print(f"\n[ECHO BOT] Auto-replied to {sender_display}")
            print("> ", end="", flush=True)
            
        except Exception as e:
            # Safe error printing
            error_msg = str(e).encode('ascii', errors='ignore').decode('ascii')
            print(f"\n[ECHO BOT ERROR] Failed to send echo: {error_msg}")
            print("> ", end="", flush=True)
        
        # Return False to allow normal notification to occur
        # Change to True if you want silent echo (no notification)
        return False
    
    def handle_command(self, cmd, parts):
        """Handle the 'echo' command"""
        if cmd == 'echo':
            if len(parts) < 2:
                # Show status
                status = "ENABLED ✓" if self.enabled else "DISABLED ✗"
                print(f"\n{'='*60}")
                print(f"Echo Bot Status: {status}")
                print(f"{'='*60}")
                print("\nThe echo bot automatically replies to all messages")
                print("with 'Echo: <message content>'")
                print("\nCommands:")
                print("  echo on      - Enable auto-reply")
                print("  echo off     - Disable auto-reply")
                print("  echo status  - Show current status")
                print(f"{'='*60}\n")
            
            else:
                subcmd = parts[1].lower()
                
                if subcmd in ['on', 'enable', 'start']:
                    self.enabled = True
                    print("✓ Echo Bot ENABLED - will auto-reply to all messages")
                    print("💡 Tip: Use 'echo off' to disable")
                elif subcmd in ['off', 'disable', 'stop']:
                    self.enabled = False
                    print("✓ Echo Bot DISABLED - normal operation")
                
                elif subcmd in ['status', 'info']:
                    status = "ENABLED ✓" if self.enabled else "DISABLED ✗"
                    print(f"\nEcho Bot: {status}\n")
                
                else:
                    print(f"Unknown subcommand: {subcmd}")
                    print("Use: echo [on|off|status]")

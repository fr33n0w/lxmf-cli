"""
Away Bot Plugin for LXMF-CLI
Automatically reply when you're away from keyboard
"""
import time
import sys
import os

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['away', 'back']
        self.description = "Auto-reply when away from keyboard"
        self.is_away = False
        self.away_message = "I'm currently away. I'll reply when I'm back!"
        self.away_since = None
        self.replied_to = set()  # Track who we've replied to
        print("Away Bot loaded! Use 'away' to enable")
    
    def on_message(self, message, msg_data):
        if not self.is_away or msg_data['direction'] == 'outbound':
            return False
        
        source_hash = msg_data['source_hash']
        
        # Only reply once per person while away
        if source_hash in self.replied_to:
            return False
        
        # Don't reply to blacklisted users
        if self.client.is_blacklisted(source_hash):
            return False
        
        # Send away message silently
        try:
            time.sleep(0.5)
            away_duration = ""
            if self.away_since:
                minutes = int((time.time() - self.away_since) / 60)
                if minutes > 0:
                    away_duration = f" (away for {minutes} min)"
            
            # Keep emoji in the actual LXMF message
            reply = f"🚫 {self.away_message}{away_duration}"
            
            # Suppress ALL output from send_message
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            
            try:
                # Redirect to devnull
                devnull = open(os.devnull, 'w', encoding='utf-8', errors='ignore')
                sys.stdout = devnull
                sys.stderr = devnull
                
                self.client.send_message(source_hash, reply)
                
            finally:
                # Restore output streams
                devnull.close()
                sys.stdout = old_stdout
                sys.stderr = old_stderr
            
            self.replied_to.add(source_hash)
            
            sender = self.client.format_contact_display_short(source_hash)
            # Use safe print for console output (no emoji here)
            print(f"\n[AWAY BOT] Auto-replied to {sender}")
            print("> ", end="", flush=True)
            
        except Exception as e:
            # Safe error printing
            error_msg = str(e).encode('ascii', errors='ignore').decode('ascii')
            print(f"\n[AWAY BOT ERROR] {error_msg}")
            print("> ", end="", flush=True)
        
        return False
    
    def handle_command(self, cmd, parts):
        if cmd == 'away':
            if len(parts) >= 2:
                # Custom away message
                self.away_message = ' '.join(parts[1:])
            
            self.is_away = True
            self.away_since = time.time()
            self.replied_to.clear()
            print("✓ Away mode ENABLED")
            print(f"Away message: {self.away_message}")
            print("💡 Use 'back' to disable")
        elif cmd == 'back':
            if self.is_away:
                away_time = int((time.time() - self.away_since) / 60) if self.away_since else 0
                self.is_away = False
                self.away_since = None
                self.replied_to.clear()
                print(f"✓ Welcome back! (was away for {away_time} min)")
            else:
                print("ℹ️  You weren't away")

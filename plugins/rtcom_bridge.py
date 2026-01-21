# rtcom_bridge.py - LXMF-CLI Plugin
"""
rtcom Bridge Plugin - Monitors rtcom command file and executes commands

This plugin allows the rtcom web UI to control LXMF-CLI by:
- Monitoring rtcom_command.txt for new commands
- Executing range test start/stop commands directly
- No external processes needed!

Installation:
1. Place this file in: ~/lxmf-cli/lxmf_client_storage/plugins/rtcom_bridge.py
2. Restart LXMF-CLI or run: plugin reload
3. The plugin will auto-start and monitor for commands

The plugin runs in the background and checks the command file every 0.5 seconds.
"""

import os
import time
import threading

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['rtcom']
        self.description = "rtcom Bridge - Execute web UI commands"
        
        # Command file path
        self.command_file = os.path.join(self.client.storage_path, 'rtcom_command.txt')
        
        # Last modification time
        self.last_mtime = 0
        
        # Start monitoring thread
        self.running = True
        self.monitor_thread = threading.Thread(target=self.monitor_commands, daemon=True)
        self.monitor_thread.start()
        
        print("[rtcom-bridge] ✅ Started - monitoring for web UI commands")
    
    def monitor_commands(self):
        """Background thread to monitor command file"""
        last_content = ""  # Track last command to avoid duplicates
        
        while self.running:
            try:
                if os.path.exists(self.command_file):
                    current_mtime = os.path.getmtime(self.command_file)
                    
                    # Only process if file was modified AND has different content
                    if current_mtime > self.last_mtime:
                        # File has been modified - read it
                        with open(self.command_file, 'r') as f:
                            command = f.read().strip()
                        
                        # Only execute if:
                        # 1. File has content
                        # 2. Content is different from last command
                        if command and command != last_content:
                            # Execute the command
                            self.execute_command(command)
                            last_content = command
                            
                            # IMMEDIATELY clear the file to prevent re-execution
                            with open(self.command_file, 'w') as f:
                                f.write('')
                            
                            # Update mtime to prevent re-reading
                            self.last_mtime = time.time()
                        elif not command:
                            # File is empty - update mtime
                            self.last_mtime = current_mtime
                
                time.sleep(0.5)  # Check every 0.5 seconds
            
            except Exception as e:
                # Log errors but continue running
                pass
    
    def execute_command(self, command):
        """Execute a command from rtcom web UI"""
        try:
            parts = command.split()
            
            if len(parts) < 2:
                return
            
            # Command format: s <contact_index> <rt|rs> [N] [D]
            if parts[0] == 's':
                contact_target = parts[1]
                
                if len(parts) >= 3:
                    cmd_type = parts[2]
                    
                    if cmd_type == 'rt' and len(parts) >= 5:
                        # Start range test: s <#> rt <N> <D>
                        ping_count = parts[3]
                        ping_delay = parts[4]
                        message = f"rt {ping_count} {ping_delay}"
                        
                        print(f"\n[rtcom→LXMF] Starting range test")
                        print(f"   Target: {contact_target}")
                        print(f"   Pings: {ping_count}, Delay: {ping_delay}s")
                        
                        # Send the command to LXMF-CLI
                        self.client.send_message(contact_target, message)
                    
                    elif cmd_type == 'rs':
                        # Stop range test: s <#> rs
                        message = "[RangeTest] Stop"
                        
                        print(f"\n[rtcom→LXMF] Stopping range test")
                        print(f"   Target: {contact_target}")
                        
                        # Send the command to LXMF-CLI
                        self.client.send_message(contact_target, message)
        
        except Exception as e:
            print(f"[rtcom-bridge] ⚠️ Error executing command: {e}")
    
    def handle_command(self, cmd, parts):
        """Handle rtcom status command"""
        if cmd == 'rtcom':
            if len(parts) > 1 and parts[1] == 'test':
                # Test command execution
                print("\n🧪 Testing rtcom bridge...")
                print("Writing test command to file...")
                
                test_command = "s 0 rt 5 3"
                with open(self.command_file, 'w') as f:
                    f.write(test_command)
                
                print(f"✅ Wrote: {test_command}")
                print("⏳ Wait ~0.5s for plugin to detect and execute...")
                print("   (Check above for execution message)\n")
                return
            
            # Show status
            print("\n📡 rtcom Bridge Status")
            print("─" * 60)
            print(f"Status: {'🟢 Running' if self.running else '🔴 Stopped'}")
            print(f"Command file: {self.command_file}")
            
            if os.path.exists(self.command_file):
                size = os.path.getsize(self.command_file)
                mtime = os.path.getmtime(self.command_file)
                print(f"File exists: ✅ ({size} bytes)")
                print(f"Last modified: {time.ctime(mtime)}")
                
                # Show current content
                try:
                    with open(self.command_file, 'r') as f:
                        content = f.read().strip()
                    if content:
                        print(f"Current content: '{content}'")
                    else:
                        print(f"Current content: (empty)")
                except:
                    pass
            else:
                print(f"File exists: ⚠️ Not created yet")
            
            print("\n💡 This plugin enables rtcom web UI commands")
            print("   Start/Stop range tests from your browser!")
            print("\n📝 Commands:")
            print("   rtcom      - Show this status")
            print("   rtcom test - Send test command (for debugging)")
            print("─" * 60 + "\n")
    
    def __del__(self):
        """Cleanup when plugin is unloaded"""
        self.running = False

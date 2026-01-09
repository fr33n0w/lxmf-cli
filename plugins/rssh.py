# remote_shell.py
import subprocess
import threading
import os
import json
import time
from datetime import datetime
import hashlib

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['ssh']
        self.description = "Remote shell access via LXMF (SSH-like functionality)"
        
        # Security settings
        self.enabled = False
        self.password_hash = None
        self.active_sessions = {}  # {source_hash: session_data}
        self.pending_auth = {}  # {source_hash: timestamp}
        self.max_auth_attempts = 3
        self.auth_timeout = 60  # seconds
        
        # Message deduplication - use timestamp-based tracking
        self.last_processed = {}  # {source_hash: (timestamp, content_hash)}
        self.message_lock = threading.Lock()
        
        # Logging
        self.plugin_dir = os.path.join(client.storage_path, "plugins")
        self.log_file = os.path.join(self.plugin_dir, "remote_shell.log")
        self.config_file = os.path.join(self.plugin_dir, "remote_shell_config.json")
        
        # Load config
        self.load_config()
    
    def load_config(self):
        """Load plugin configuration"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.password_hash = config.get('password_hash')
                    self.enabled = config.get('enabled', False)
            except Exception as e:
                print(f"Error loading remote shell config: {e}")
    
    def save_config(self):
        """Save plugin configuration"""
        try:
            config = {
                'password_hash': self.password_hash,
                'enabled': self.enabled
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error saving remote shell config: {e}")
    
    def hash_password(self, password):
        """Create secure password hash"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def log_activity(self, source_hash, action, command=None):
        """Log remote shell activity"""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            contact_name = self.client.format_contact_display_short(source_hash)
            
            log_entry = f"[{timestamp}] {contact_name} ({source_hash[:16]}): {action}"
            if command:
                log_entry += f" | Command: {command}"
            
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry + "\n")
        except Exception as e:
            print(f"Error logging activity: {e}")
    
    def is_duplicate_message(self, msg_data):
        """Check if this is a duplicate message"""
        with self.message_lock:
            source_hash = msg_data['source_hash']
            timestamp = msg_data['timestamp']
            content = msg_data['content']
            
            # Create content hash
            content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
            
            # Check if we've seen this exact message from this source recently
            if source_hash in self.last_processed:
                last_time, last_hash = self.last_processed[source_hash]
                
                # Same message within 2 seconds = duplicate
                if abs(timestamp - last_time) < 2 and content_hash == last_hash:
                    return True
            
            # Update tracking
            self.last_processed[source_hash] = (timestamp, content_hash)
            
            # Clean old entries (older than 10 seconds)
            current_time = time.time()
            to_remove = []
            for key, (ts, _) in self.last_processed.items():
                if current_time - ts > 10:
                    to_remove.append(key)
            for key in to_remove:
                del self.last_processed[key]
            
            return False
    
    def execute_command(self, command, source_hash):
        """Execute shell command and return output"""
        try:
            # Log the command
            self.log_activity(source_hash, "EXEC", command)
            
            # Execute command
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=os.path.expanduser('~')
            )
            
            # Combine stdout and stderr
            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR]\n{result.stderr}"
            
            if result.returncode != 0:
                output += f"\n[Exit code: {result.returncode}]"
            
            return output if output.strip() else "[No output]"
        
        except subprocess.TimeoutExpired:
            return "[Error: Command timeout (30s limit)]"
        except Exception as e:
            return f"[Error executing command: {e}]"
    
    def on_message(self, message, msg_data):
        """Handle incoming messages"""
        # Check if plugin is enabled
        if not self.enabled:
            return False
        
        # Check for duplicate message
        if self.is_duplicate_message(msg_data):
            return True  # Silently ignore duplicates
        
        content = msg_data['content'].strip()
        source_hash = msg_data['source_hash']
        
        # Handle authentication requests
        if content.lower() == 'ssh':
            if not self.password_hash:
                self.client.send_message(
                    source_hash,
                    "Remote shell not configured. Contact administrator."
                )
                self.log_activity(source_hash, "AUTH_REQUEST_DENIED")
                return True
            
            # Start authentication
            self.pending_auth[source_hash] = {
                'timestamp': time.time(),
                'attempts': 0
            }
            
            self.client.send_message(
                source_hash,
                "🔐 Remote Shell Authentication\nEnter password:"
            )
            self.log_activity(source_hash, "AUTH_REQUEST")
            return True
        
        # Handle password submission
        if source_hash in self.pending_auth:
            auth_data = self.pending_auth[source_hash]
            
            # Check timeout
            if time.time() - auth_data['timestamp'] > self.auth_timeout:
                del self.pending_auth[source_hash]
                self.client.send_message(
                    source_hash,
                    "Authentication timeout. Send 'ssh' to retry."
                )
                self.log_activity(source_hash, "AUTH_TIMEOUT")
                return True
            
            # Check password
            if self.hash_password(content) == self.password_hash:
                # Authentication successful
                del self.pending_auth[source_hash]
                self.active_sessions[source_hash] = {
                    'start_time': time.time(),
                    'last_activity': time.time(),
                    'cwd': os.path.expanduser('~')
                }
                
                # Get system info
                try:
                    hostname = os.uname().nodename
                    username = os.getenv('USER', 'unknown')
                    current_dir = os.getcwd()
                except:
                    hostname = "unknown"
                    username = "unknown"
                    current_dir = "~"
                
                welcome = (
                    "✅ Connected to Remote Shell\n"
                    f"{username}@{hostname}:{current_dir}\n\n"
                    "Type commands to execute.\n"
                    "Type 'ssh exit' to disconnect.\n"
                    "⚠️  All activity is logged."
                )
                
                self.client.send_message(source_hash, welcome)
                self.log_activity(source_hash, "AUTH_SUCCESS")
                return True
            else:
                # Authentication failed
                auth_data['attempts'] += 1
                
                if auth_data['attempts'] >= self.max_auth_attempts:
                    del self.pending_auth[source_hash]
                    self.client.send_message(
                        source_hash,
                        "❌ Authentication failed. Access denied."
                    )
                    self.log_activity(source_hash, "AUTH_FAILED_MAX")
                else:
                    remaining = self.max_auth_attempts - auth_data['attempts']
                    self.client.send_message(
                        source_hash,
                        f"❌ Wrong password. {remaining} attempts left."
                    )
                    self.log_activity(source_hash, f"AUTH_FAILED_{auth_data['attempts']}")
                
                return True
        
        # Handle active session commands
        if source_hash in self.active_sessions:
            session = self.active_sessions[source_hash]
            session['last_activity'] = time.time()
            
            # Check for exit
            if content.lower() == 'ssh exit':
                duration = int(time.time() - session['start_time'])
                del self.active_sessions[source_hash]
                
                self.client.send_message(
                    source_hash,
                    f"👋 Session closed ({duration}s)"
                )
                self.log_activity(source_hash, f"SESSION_END {duration}s")
                return True
            
            # Execute command
            output = self.execute_command(content, source_hash)
            
            # Send with prompt
            try:
                username = os.getenv('USER', 'user')
                hostname = os.uname().nodename
                prompt = f"\n{username}@{hostname}:~$ "
            except:
                prompt = "\n$ "
            
            self.client.send_message(source_hash, output + prompt)
            return True
        
        return False
    
    def handle_command(self, cmd, parts):
        """Handle local commands"""
        if cmd == 'ssh':
            if len(parts) < 2:
                self.show_status()
                return
            
            subcmd = parts[1].lower()
            
            if subcmd == 'on':
                if self.password_hash:
                    self.enabled = True
                    self.save_config()
                    print("✅ Remote shell enabled")
                else:
                    print("\n🔐 Remote Shell Setup")
                    password = input("Set password (min 8 chars): ").strip()
                    
                    if len(password) < 8:
                        print("❌ Password too short")
                        return
                    
                    confirm = input("Confirm password: ").strip()
                    if password != confirm:
                        print("❌ Passwords don't match")
                        return
                    
                    self.password_hash = self.hash_password(password)
                    self.enabled = True
                    self.save_config()
                    print("✅ Remote shell enabled")
            
            elif subcmd == 'off':
                self.enabled = False
                for source_hash in list(self.active_sessions.keys()):
                    self.client.send_message(
                        source_hash,
                        "Admin closed all sessions."
                    )
                self.active_sessions.clear()
                self.save_config()
                print("✅ Remote shell disabled")
            
            elif subcmd == 'password':
                print("\n🔐 Change Password")
                password = input("New password (min 8 chars): ").strip()
                
                if len(password) < 8:
                    print("❌ Password too short")
                    return
                
                confirm = input("Confirm: ").strip()
                if password != confirm:
                    print("❌ Passwords don't match")
                    return
                
                self.password_hash = self.hash_password(password)
                self.save_config()
                print("✅ Password updated")
            
            elif subcmd == 'sessions':
                self.show_sessions()
            
            elif subcmd == 'log':
                self.show_log()
            
            elif subcmd == 'kick' and len(parts) >= 3:
                self.kick_session(parts[2])
            
            else:
                print("💡 ssh on/off/password/sessions/kick/log")
    
    def show_status(self):
        """Show status"""
        print("\n" + "─" * 50)
        print("REMOTE SHELL STATUS")
        print("─" * 50)
        print(f"Enabled: {'Yes' if self.enabled else 'No'}")
        print(f"Password: {'Set' if self.password_hash else 'Not set'}")
        print(f"Active sessions: {len(self.active_sessions)}")
        print("─" * 50 + "\n")
    
    def show_sessions(self):
        """Show active sessions"""
        if not self.active_sessions:
            print("\nNo active sessions\n")
            return
        
        print("\n" + "─" * 60)
        print("ACTIVE SESSIONS")
        print("─" * 60)
        
        for idx, (source_hash, session) in enumerate(self.active_sessions.items(), 1):
            contact = self.client.format_contact_display_short(source_hash)
            duration = int(time.time() - session['start_time'])
            print(f"[{idx}] {contact} - {duration}s")
        
        print("─" * 60 + "\n")
    
    def kick_session(self, identifier):
        """Close a session"""
        try:
            idx = int(identifier)
            sessions = list(self.active_sessions.items())
            
            if 1 <= idx <= len(sessions):
                source_hash, _ = sessions[idx - 1]
                self.client.send_message(source_hash, "Session closed by admin.")
                del self.active_sessions[source_hash]
                print("✅ Session closed")
            else:
                print("❌ Invalid session number")
        except ValueError:
            print("❌ Use: ssh kick <number>")
    
    def show_log(self):
        """Show log"""
        if not os.path.exists(self.log_file):
            print("\nNo log yet\n")
            return
        
        try:
            with open(self.log_file, 'r') as f:
                lines = f.readlines()
            
            print("\n" + "─" * 70)
            print("ACTIVITY LOG (last 20)")
            print("─" * 70)
            for line in lines[-20:]:
                print(line.rstrip())
            print("─" * 70 + "\n")
        except Exception as e:
            print(f"Error: {e}")
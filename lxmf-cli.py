#!/usr/bin/env python3
"""
Interactive LXMF Client - Final Version
Properly extracts display names using LXMF's helper functions
"""

import RNS
import LXMF
import time
import sys
import os
import json
import threading
from datetime import datetime
import types

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    COLOR_ENABLED = True
except ImportError:
    COLOR_ENABLED = False
    class Fore:
        RED = GREEN = YELLOW = CYAN = MAGENTA = BLUE = WHITE = ""
    class Style:
        BRIGHT = RESET_ALL = ""


class LXMFClient:
    def __init__(self, identity_path="./lxmf_client_identity", storage_path="./lxmf_client_storage"):
        self.identity_path = identity_path
        self.storage_path = storage_path
        self.messages_path = os.path.join(storage_path, "messages")
        self.contacts = {}
        self.contacts_file = os.path.join(storage_path, "contacts.json")
        self.config_file = os.path.join(storage_path, "config.json")
        self.messages = []
        self.messages_lock = threading.Lock()
        self.running = False
        self.last_sender_hash = None
        self.last_sender_name = None
        self.display_name = None
        self.announce_interval = 300
        self.stop_event = threading.Event()
        self.show_announces = True
        self.start_time = time.time()
        
        # Track pending messages
        self.pending_messages = {}
        
        # Cache for display names from announces
        self.display_name_cache = {}
        self.cache_file = os.path.join(storage_path, "display_names.json")
        self.cache_dirty = False
        self.last_cache_save = time.time()
        
        # Debug: Track suppressed errors
        self.suppressed_errors = 0
        
        # Track announced LXMF peers with fixed index numbers
        self.announced_peers = {}
        self.peers_lock = threading.Lock()
        self.next_peer_index = 1
        
        # Track contacts with fixed index numbers
        self.next_contact_index = 1
        
        # Track conversations with fixed index numbers
        self.conversation_indices = {}
        self.next_conversation_index = 1
        self.conversations_file = os.path.join(storage_path, "conversations.json")
        
        # Command aliases
        self.command_aliases = {
            'h': 'help', 's': 'send', 'c': 'contacts', 'a': 'add',
            'rm': 'remove', 're': 'reply', 'm': 'messages', 'addr': 'address',
            'n': 'name', 'i': 'interval', 'ann': 'announce', 'q': 'quit', 'e': 'exit',
            'p': 'peers', 'sp': 'sendpeer', 'ap': 'addpeer', 'da': 'discoverannounce',
            'cls': 'clear', 'r': 'restart', 'st': 'stats', 'set': 'settings'
        }
        
        os.makedirs(storage_path, exist_ok=True)
        os.makedirs(self.messages_path, exist_ok=True)
        
        # === LOAD CONFIGURATION FIRST (before Reticulum) ===
        self.load_config()
        
        # === NOW INITIALIZE RETICULUM ===
        self._print_color("Initializing Reticulum...", Fore.CYAN)
        self.reticulum = RNS.Reticulum()
        
        # Load or create identity
        if os.path.exists(identity_path):
            self.identity = RNS.Identity.from_file(identity_path)
            self._print_success("Loaded identity")
        else:
            self.identity = RNS.Identity()
            self.identity.to_file(identity_path)
            self._print_success("Created new identity")
        
        # Load display name cache
        self.load_display_name_cache()
        
        # Create LXMF router
        lxmf_storage = os.path.join(storage_path, "lxmf_router")
        os.makedirs(lxmf_storage, exist_ok=True)
        
        self.router = LXMF.LXMRouter(
            identity=self.identity,
            storagepath=lxmf_storage
        )
        
        self._print_success(f"LXMF storage: {lxmf_storage}")
        
        # Register destination with display name
        self.destination = self.router.register_delivery_identity(
            self.identity, 
            display_name=self.display_name
        )
        
        # Register callbacks
        self.router.register_delivery_callback(self.on_message_received)
        
        # Register announce handler to capture display names
        self.register_announce_handler()
        
        # Load contacts and messages
        self.load_contacts()
        self.load_messages()
        self.load_conversation_indices()
        
        # Setup thread exception handler
        threading.excepthook = self.thread_exception_handler
        
        # Show info
        print(f"\n{'='*60}")
        self._print_color(f"Display Name: {self.display_name}", Fore.GREEN + Style.BRIGHT)
        self._print_color(f"LXMF Address: {RNS.prettyhexrep(self.destination.hash)}", Fore.CYAN)
        self._print_color(f"Auto-announce: Every {self.announce_interval} seconds", Fore.YELLOW)
        print(f"{'='*60}\n")
        
        # Initial announce
        self._print_color("Announcing to network...", Fore.CYAN)
        self.destination.announce()
        self._print_success("Initial announce complete")
        
        # Start background threads
        self.announce_thread = threading.Thread(target=self.announce_loop, daemon=True)
        self.announce_thread.start()
        
        self.router_thread = threading.Thread(target=self.router_job_loop, daemon=True)
        self.router_thread.start()

    def load_conversation_indices(self):
        """Load conversation indices from file"""
        if os.path.exists(self.conversations_file):
            try:
                with open(self.conversations_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.conversation_indices = data.get('indices', {})
                    self.next_conversation_index = data.get('next_index', 1)
                if self.conversation_indices:
                    self._print_success(f"Loaded {len(self.conversation_indices)} conversation indices")
            except Exception as e:
                self._print_warning(f"Error loading conversation indices: {e}")

    def save_conversation_indices(self):
        """Save conversation indices to file"""
        try:
            data = {
                'indices': self.conversation_indices,
                'next_index': self.next_conversation_index
            }
            with open(self.conversations_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self._print_warning(f"Error saving conversation indices: {e}")

    def assign_conversation_index(self, hash_str):
        """Assign a fixed index to a conversation if it doesn't have one"""
        clean_hash = hash_str.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
        
        if clean_hash not in self.conversation_indices:
            self.conversation_indices[clean_hash] = self.next_conversation_index
            self.next_conversation_index += 1
            self.save_conversation_indices()
        
        return self.conversation_indices[clean_hash]

    def register_announce_handler(self):
        """Register handler to capture display names from announces"""
        
        class LXMFPeerAnnounceHandler:
            def __init__(self, client):
                self.client = client
                self.aspect_filter = "lxmf.delivery"
            
            def received_announce(self, destination_hash, announced_identity, app_data):
                """Called when an LXMF delivery announce is received"""
                try:
                    if app_data:
                        display_name = LXMF.display_name_from_app_data(app_data)
                        
                        if display_name and isinstance(display_name, str):
                            hash_str = RNS.prettyhexrep(destination_hash)
                            clean_hash = hash_str.replace(":", "").replace(" ", "").lower()
                            
                            with self.client.peers_lock:
                                # Check if this is a new peer
                                is_new_peer = clean_hash not in self.client.announced_peers
                                
                                if is_new_peer:
                                    # Assign a fixed index number for this peer
                                    peer_index = self.client.next_peer_index
                                    self.client.next_peer_index += 1
                                    
                                    self.client.announced_peers[clean_hash] = {
                                        'display_name': display_name,
                                        'last_seen': time.time(),
                                        'index': peer_index
                                    }
                                else:
                                    # Update existing peer (keep same index)
                                    self.client.announced_peers[clean_hash]['display_name'] = display_name
                                    self.client.announced_peers[clean_hash]['last_seen'] = time.time()
                            
                            # Show discovery message for new peers if enabled
                            if is_new_peer and self.client.show_announces:
                                if clean_hash not in self.client.display_name_cache or self.client.display_name_cache[clean_hash] != display_name:
                                    self.client.cache_display_name(hash_str, display_name)
                                    print(f"\n[Discovered: {display_name} <{hash_str}>]")
                                    print("> ", end="", flush=True)
                                else:
                                    self.client.cache_display_name(hash_str, display_name)
                            else:
                                # Silently cache
                                self.client.cache_display_name(hash_str, display_name)
                    
                except Exception as e:
                    pass  # Silently handle errors
        
        # Create and register our handler
        self.peer_announce_handler = LXMFPeerAnnounceHandler(self)
        RNS.Transport.register_announce_handler(self.peer_announce_handler)
        
        self._print_success("LXMF peer announce handler registered")
    
    def _print_color(self, text, color=""):
        """Print with color if available"""
        if COLOR_ENABLED:
            print(f"{color}{text}{Style.RESET_ALL}")
        else:
            print(text)
    
    def _print_success(self, text):
        """Print success message"""
        self._print_color(f"✓ {text}", Fore.GREEN)
    
    def _print_error(self, text):
        """Print error message"""
        self._print_color(f"❌ {text}", Fore.RED)
    
    def _print_warning(self, text):
        """Print warning message"""
        self._print_color(f"⚠ {text}", Fore.YELLOW)
    
    def router_job_loop(self):
        """Continuously process router jobs"""
        while not self.stop_event.is_set():
            try:
                if hasattr(self.router, 'jobs'):
                    self.router.jobs()
                
                if hasattr(self.router, 'process_outbound'):
                    if not getattr(self.router, 'processing_outbound', False):
                        self.router.process_outbound()
                
                time.sleep(0.1)
            except Exception:
                pass
    
    def thread_exception_handler(self, args):
        """Log thread exceptions"""
        # Count and skip file-related errors
        if isinstance(args.exc_value, (PermissionError, FileNotFoundError, OSError)):
            self.suppressed_errors += 1
            return
        
        # Log other unexpected errors
        self._print_warning(f"Thread error: {args.exc_type.__name__}: {args.exc_value}")
        print("> ", end="", flush=True)
    
    def load_display_name_cache(self):
        """Load cached display names"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.display_name_cache = json.load(f)
                    if self.display_name_cache:
                        self._print_success(f"Loaded {len(self.display_name_cache)} cached display names")
            except Exception as e:
                self._print_warning(f"Error loading display name cache: {e}")
                self.display_name_cache = {}
        else:
            self.display_name_cache = {}
    
    def save_display_name_cache(self):
        """Save display name cache"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.display_name_cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._print_warning(f"Error saving display name cache: {e}")
    
    def cache_display_name(self, hash_str, display_name):
        """Cache a display name for a hash"""
        if display_name and isinstance(display_name, str) and display_name.strip():
            # Normalize hash format (remove colons, spaces, brackets)
            clean_hash = hash_str.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
            self.display_name_cache[clean_hash] = display_name.strip()
            self.cache_dirty = True
            
    def save_display_name_cache(self):
        """Save display name cache (only if dirty and enough time passed)"""
        # Only save if cache has changed and at least 5 seconds since last save
        if not self.cache_dirty:
            return
        
        current_time = time.time()
        if current_time - self.last_cache_save < 5:
            return  # Too soon, skip save
        
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.display_name_cache, f, indent=2, ensure_ascii=False)
            self.cache_dirty = False
            self.last_cache_save = current_time
        except Exception as e:
            # Will retry on next call
            pass
        
    def router_job_loop(self):
        """Continuously process router jobs"""
        last_periodic_save = time.time()
        
        while not self.stop_event.is_set():
            try:
                if hasattr(self.router, 'jobs'):
                    self.router.jobs()
                
                if hasattr(self.router, 'process_outbound'):
                    if not getattr(self.router, 'processing_outbound', False):
                        self.router.process_outbound()
                
                # Periodic saves (every 10 seconds)
                current_time = time.time()
                if current_time - last_periodic_save > 10:
                    self.save_display_name_cache()
                    last_periodic_save = current_time
                
                time.sleep(0.1)
            except Exception:
                pass
    
    def announce_loop(self):
        """Periodically announce destination"""
        while not self.stop_event.is_set():
            if self.stop_event.wait(self.announce_interval):
                break
            
            if not self.stop_event.is_set():
                self.destination.announce()
                timestamp = datetime.now().strftime('%H:%M:%S')
                self._print_color(f"\n[Auto-announced at {timestamp}]", Fore.CYAN)
                print("> ", end="", flush=True)
    
    def load_config(self):
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.display_name = config.get('display_name', 'Anonymous')
                    self.announce_interval = config.get('announce_interval', 300)
                    self.show_announces = config.get('show_announces', True)
                return
            except Exception as e:
                self._print_warning(f"Error loading config: {e}")
        
        # === FIRST TIME SETUP ===
        print(f"\n{'='*60}")
        self._print_color("FIRST TIME SETUP", Fore.CYAN + Style.BRIGHT)
        print(f"{'='*60}\n")
        
        self._print_color("Welcome to LXMF Client!", Fore.GREEN)
        print("Let's get you set up with a display name.\n")
        
        # Ask for display name
        while True:
            try:
                name = input(f"{Fore.YELLOW}Enter your display name: {Style.RESET_ALL}" if COLOR_ENABLED else "Enter your display name: ").strip()
                
                if name:
                    self.display_name = name
                    break
                else:
                    self._print_warning("Display name cannot be empty. Please try again.")
            except KeyboardInterrupt:
                print("\n")
                self._print_warning("Using default name: Anonymous")
                self.display_name = 'Anonymous'
                break
            except:
                self.display_name = 'Anonymous'
                break
        
        print()
        self._print_success(f"Display name set to: {self.display_name}")
        
        # Ask for announce interval (optional)
        print(f"\n{Fore.CYAN}Auto-announce interval:{Style.RESET_ALL}" if COLOR_ENABLED else "\nAuto-announce interval:")
        print("This determines how often your presence is announced to the network.")
        
        try:
            interval_str = input(f"{Fore.YELLOW}Interval in seconds [300]: {Style.RESET_ALL}" if COLOR_ENABLED else "Interval in seconds [300]: ").strip()
            if interval_str and interval_str.isdigit():
                self.announce_interval = max(30, int(interval_str))
            else:
                self.announce_interval = 300
        except:
            self.announce_interval = 300
        
        self._print_success(f"Announce interval set to: {self.announce_interval}s")
        
        print(f"\n{'='*60}")
        self._print_color("Setup complete! Initializing...", Fore.GREEN)
        print(f"{'='*60}\n")
        
        # Save configuration
        self.save_config()

    def save_config(self):
        """Save configuration to file"""
        try:
            config = {
                'display_name': self.display_name,
                'announce_interval': self.announce_interval,
                'show_announces': self.show_announces
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            self._print_warning(f"Error saving config: {e}")
    
    def load_messages(self):
        """Load all messages from the messages folder"""
        try:
            all_messages = []
            
            for filename in os.listdir(self.messages_path):
                if filename.endswith('.json'):
                    filepath = os.path.join(self.messages_path, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            message = json.load(f)
                            all_messages.append(message)
                    except Exception as e:
                        self._print_warning(f"Error loading message {filename}: {e}")
            
            all_messages.sort(key=lambda x: x.get('timestamp', 0))
            
            with self.messages_lock:
                self.messages = all_messages
            
            if all_messages:
                self._print_success(f"Loaded {len(all_messages)} messages")
        except Exception as e:
            self._print_warning(f"Error loading messages: {e}")
    
    def save_message(self, msg_data):
        """Save a single message to its own file"""
        try:
            timestamp = msg_data['timestamp']
            direction = msg_data['direction']
            filename = f"{int(timestamp)}_{direction}.json"
            filepath = os.path.join(self.messages_path, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(msg_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._print_warning(f"Error saving message: {e}")
    
    def get_lxmf_display_name(self, hash_str):
        """Get LXMF display name from cache or by querying announce data"""
        # Normalize hash format - remove all separators and angle brackets
        clean_hash = hash_str.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
        
        # Check cache first - try both with and without formatting
        if clean_hash in self.display_name_cache:
            return self.display_name_cache[clean_hash]
        
        # Also check if cache has it with colons (legacy format)
        for cached_hash, cached_name in self.display_name_cache.items():
            if cached_hash.replace(":", "").replace(" ", "").lower() == clean_hash:
                # Found it with different formatting, normalize the cache
                self.display_name_cache[clean_hash] = cached_name
                return cached_name
        
        # Try to get from Reticulum's stored announce data
        try:
            hash_bytes = bytes.fromhex(clean_hash)
            app_data = RNS.Identity.recall_app_data(hash_bytes)
            
            if app_data:
                # Use LXMF's helper function to extract display name
                display_name = LXMF.display_name_from_app_data(app_data)
                if display_name:
                    self.cache_display_name(clean_hash, display_name)
                    return display_name
        except Exception as e:
            pass
        
        return None
    
    def on_message_received(self, message):
        """Callback when message is received"""
        try:
            content = message.content
            if isinstance(content, bytes):
                content = content.decode('utf-8', errors='replace')
            
            title = message.title
            if isinstance(title, bytes):
                title = title.decode('utf-8', errors='replace')
            
            source_hash_str = RNS.prettyhexrep(message.source_hash)
            
            # Get display name using our helper
            sender_display_name = self.get_lxmf_display_name(source_hash_str)

            # Visual notification
            self.notify_new_message()
            
            msg_data = {
                'timestamp': message.timestamp,
                'source_hash': source_hash_str,
                'title': title,
                'content': content,
                'direction': 'inbound',
                'display_name': sender_display_name
            }
            
            with self.messages_lock:
                self.messages.append(msg_data)
                self.last_sender_hash = msg_data['source_hash']
                self.last_sender_name = self.get_contact_name_by_hash(msg_data['source_hash'])
            
            self.save_message(msg_data)
            
            sender_display = self.format_contact_display(msg_data['source_hash'], show_hash=True)
            
            print(f"\n{'='*60}")
            self._print_color(f"📨 NEW MESSAGE from {sender_display}", Fore.GREEN + Style.BRIGHT)
            print(f"{'='*60}")
            print(f"Time: {datetime.fromtimestamp(message.timestamp).strftime('%Y-%m-%d %H:%M:%S')}")
            if title:
                print(f"Title: {title}")
            if content:
                print(f"\n{content}")
            print(f"{'='*60}")
            self._print_color("💡 Type 'reply <message>' or 're <message>' to respond", Fore.CYAN)
            print(f"{'='*60}\n")
            print("> ", end="", flush=True)
        
        except Exception as e:
            self._print_error(f"Error processing message: {e}")
            import traceback
            traceback.print_exc()
            print("> ", end="", flush=True)
    
    def load_contacts(self):
        """Load contacts from file"""
        if os.path.exists(self.contacts_file):
            try:
                with open(self.contacts_file, 'r', encoding='utf-8') as f:
                    self.contacts = json.load(f)
                
                # Assign indices to contacts that don't have them
                needs_save = False
                for name, data in self.contacts.items():
                    if 'index' not in data:
                        data['index'] = self.next_contact_index
                        self.next_contact_index += 1
                        needs_save = True
                    else:
                        # Update next_contact_index to be higher than any existing index
                        if data['index'] >= self.next_contact_index:
                            self.next_contact_index = data['index'] + 1
                
                if needs_save:
                    self.save_contacts()
                
                if self.contacts:
                    self._print_success(f"Loaded {len(self.contacts)} contacts")
            except Exception as e:
                self._print_warning(f"Error loading contacts: {e}")

    def load_announced_peers_from_cache(self):
        """Load already announced LXMF peers from Reticulum's identity cache"""
        try:
            # Try to access Reticulum's stored announces
            if hasattr(RNS.Transport, 'announces'):
                print(f"[DEBUG] Checking Transport.announces...")
                for destination_hash, announce_data in RNS.Transport.announces.items():
                    try:
                        hash_str = RNS.prettyhexrep(destination_hash)
                        
                        # Try to get app_data
                        app_data = RNS.Identity.recall_app_data(destination_hash)
                        
                        if app_data:
                            display_name = LXMF.display_name_from_app_data(app_data)
                            
                            if display_name and isinstance(display_name, str):
                                clean_hash = hash_str.replace(":", "").replace(" ", "").lower()
                                
                                with self.peers_lock:
                                    self.announced_peers[clean_hash] = {
                                        'display_name': display_name,
                                        'last_seen': time.time()
                                    }
                                
                                print(f"[DEBUG] Loaded cached peer: {display_name} <{hash_str}>")
                    except Exception as e:
                        pass
            
            if self.announced_peers:
                self._print_success(f"Loaded {len(self.announced_peers)} announced peers from cache")
        except Exception as e:
            print(f"[DEBUG] Error loading cached peers: {e}")
    
    def save_contacts(self):
        """Save contacts to file"""
        try:
            with open(self.contacts_file, 'w', encoding='utf-8') as f:
                json.dump(self.contacts, f, indent=2)
            self._print_success("Contacts saved")
        except Exception as e:
            self._print_error(f"Error saving contacts: {e}")
    
    def get_contact_name_by_hash(self, hash_str: str) -> str:
        """Get contact name from hash string, return hash if not found"""
        clean_hash = hash_str.replace(":", "").replace("<", "").replace(">", "").strip().lower()
        for name, data in self.contacts.items():
            stored_hash = data['hash'].replace(":", "").strip().lower()
            if stored_hash == clean_hash:
                return name
        return hash_str
    
    def format_contact_display(self, hash_str, show_hash=True):
        """
        Format contact for display with priority:
        1. LXMF display name (from network announces)
        2. Contact nickname (from local contacts list)
        3. Hash address (fallback)
        
        If both display name and nickname exist, show: Nickname (Display Name)
        """
        nickname = self.get_contact_name_by_hash(hash_str)
        display_name = self.get_lxmf_display_name(hash_str)
        
        # Check if we have a saved contact (nickname != hash means we found a contact)
        has_contact = (nickname != hash_str)
        
        if has_contact and display_name:
            # Both nickname and display name exist
            if display_name != nickname:
                # They're different, show both
                if show_hash:
                    return f"{nickname} ({display_name}) <{hash_str}>"
                else:
                    return f"{nickname} ({display_name})"
            else:
                # They're the same, just show one
                if show_hash:
                    return f"{nickname} <{hash_str}>"
                else:
                    return nickname
        elif has_contact:
            # Only nickname exists (no display name from network)
            if show_hash:
                return f"{nickname} <{hash_str}>"
            else:
                return nickname
        elif display_name:
            # Only display name exists (no saved contact)
            if show_hash:
                return f"{display_name} <{hash_str}>"
            else:
                return display_name
        else:
            # Nothing exists, just show hash
            return hash_str
    
    def format_contact_display_short(self, hash_str):
        """
        Short format for display - prioritizes readability over showing hash.
        Priority: Display Name > Nickname > Hash
        """
        display_name = self.get_lxmf_display_name(hash_str)
        if display_name:
            return display_name
        
        nickname = self.get_contact_name_by_hash(hash_str)
        if nickname != hash_str:
            return nickname
        
        return hash_str
    
    def add_contact(self, name, hash_str):
        """Add a contact"""
        clean_hash = hash_str.replace(":", "").replace(" ", "").replace("<", "").replace(">", "")
        
        self.contacts[name] = {
            'hash': clean_hash,
            'index': self.next_contact_index
        }
        self.next_contact_index += 1
        
        self.save_contacts()
        self._print_success(f"Added contact: {name}")
        
        display_name = self.get_lxmf_display_name(clean_hash)
        if display_name:
            print(f"  Display name: {display_name}")
    
    def list_contacts(self):
        """List all contacts"""
        if not self.contacts:
            print("\nNo contacts saved\n")
            return
        
        # Sort by index
        sorted_contacts = sorted(self.contacts.items(), key=lambda x: x[1].get('index', 999999))
        
        print(f"\n{'='*100}")
        self._print_color("CONTACTS", Fore.CYAN + Style.BRIGHT)
        print(f"{'='*100}")
        print(f"{'#':<5} {'Nickname':<20} {'LXMF Display Name':<30} {'Hash':<32}")
        print(f"{'-'*5} {'-'*20} {'-'*30} {'-'*32}")
        
        for name, data in sorted_contacts:
            idx = data.get('index', '?')
            hash_str = data['hash']
            display_name = self.get_lxmf_display_name(hash_str)
            
            # Truncate names if too long
            name_shown = name[:18] + ".." if len(name) > 20 else name
            
            if display_name:
                display_shown = display_name[:28] + ".." if len(display_name) > 30 else display_name
                print(f"{idx:<5} {name_shown:<20} {display_shown:<30} {hash_str}")
            else:
                print(f"{idx:<5} {name_shown:<20} {'<unknown>':<30} {hash_str}")
        
        print(f"{'='*100}")
        self._print_color("\n💡 Tip: Send messages using contact number, e.g., 's 3 hello'", Fore.YELLOW)
        print()
        
    def send_message(self, recipient, content, title=None):
        """Send a message with optimized processing"""
        try:
            send_start_time = time.time()

            # Check if recipient is a number (contact index)
            if recipient.isdigit():
                contact_idx = int(recipient)
                # Find contact by index
                found_contact = None
                for name, data in self.contacts.items():
                    if data.get('index') == contact_idx:
                        found_contact = data['hash']
                        print(f"Resolved contact #{contact_idx} to: {name}")
                        break
                
                if found_contact:
                    dest_hash_str = found_contact
                else:
                    self._print_error(f"No contact with index #{contact_idx}. Use 'contacts' to see the list")
                    return False
            # Check if it's a contact name
            elif recipient in self.contacts:
                dest_hash_str = self.contacts[recipient]['hash']
            # Otherwise treat as direct hash
            else:
                dest_hash_str = recipient

            # Normalize hash
            dest_hash_str = dest_hash_str.replace(":", "").replace(" ", "").replace("<", "").replace(">", "")
            dest_hash_bytes = bytes.fromhex(dest_hash_str)

            # Recall identity or request path
            dest_identity = RNS.Identity.recall(dest_hash_bytes)
            if dest_identity is None:
                self._print_warning("Destination identity unknown, requesting...")
                path_request_time = time.time()
                RNS.Transport.request_path(dest_hash_bytes)
                waited = 0
                while waited < 3 and dest_identity is None:
                    time.sleep(0.5)
                    waited += 0.5
                    dest_identity = RNS.Identity.recall(dest_hash_bytes)
                if dest_identity is None:
                    self._print_error("Could not get destination identity")
                    print("   Ask recipient to announce their address")
                    return False
                else:
                    path_time = time.time() - path_request_time
                    self._print_success(f"Got identity after {path_time:.1f}s")

            # Create destination
            dest = RNS.Destination(
                dest_identity,
                RNS.Destination.OUT,
                RNS.Destination.SINGLE,
                "lxmf",
                "delivery"
            )

            # Create LXMF message
            message = LXMF.LXMessage(
                destination=dest,
                source=self.destination,
                content=content,
                title=title,
                desired_method=LXMF.LXMessage.DIRECT
            )
            message.send_timestamp = send_start_time
            message.register_delivery_callback(self.on_delivery)
            message.register_failed_callback(self.on_failed)

            # Save to history
            msg_data = {
                'timestamp': time.time(),
                'destination_hash': RNS.prettyhexrep(dest_hash_bytes),
                'title': title,
                'content': content,
                'direction': 'outbound'
            }
            with self.messages_lock:
                self.messages.append(msg_data)
            self.save_message(msg_data)

            # Build recipient display string
            dest_hash = msg_data['destination_hash']
            recipient_display = self.format_contact_display(dest_hash, show_hash=True)

            self._print_color(f"📤 Sending to {recipient_display}...", Fore.CYAN)

            # Track pending
            self.pending_messages[message.hash] = {
                'message': message,
                'start_time': send_start_time,
                'recipient': recipient_display,
                'last_progress': 0
            }

            # Progress monitor
            def monitor_progress():
                msg_hash = message.hash
                last_status = ""
                while msg_hash in self.pending_messages:
                    try:
                        elapsed = time.time() - self.pending_messages[msg_hash]['start_time']
                        progress = self.router.get_outbound_progress(msg_hash)
                        if progress is not None:
                            progress_pct = progress * 100
                            status = f"[{elapsed:.0f}s] Progress: {progress_pct:.1f}%"
                            if progress < 0.02:
                                phase = " - Waiting for path..."
                            elif progress < 0.04:
                                phase = " - Establishing link..."
                            elif progress < 0.10:
                                phase = " - Link established, preparing transfer..."
                            elif progress < 0.95:
                                phase = " - Transferring data..."
                            else:
                                phase = " - Waiting for confirmation..."
                            status += phase
                            if status != last_status:
                                print(f"\r    {status}", end="", flush=True)
                                last_status = status
                        time.sleep(0.5)
                    except:
                        break
                if last_status:
                    print("\r" + " " * (len(last_status) + 4), end="\r", flush=True)

            threading.Thread(target=monitor_progress, daemon=True).start()

            # Send message
            self.router.handle_outbound(message)

            return True

        except ValueError:
            self._print_error("Invalid destination hash or contact index")
            return False
        except Exception as e:
            self._print_error(f"Error sending message: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def on_delivery(self, message):
        """Callback for successful delivery"""
        dest_hash = RNS.prettyhexrep(message.destination_hash)
        recipient_str = self.format_contact_display(dest_hash, show_hash=True)

        if message.hash in self.pending_messages:
            del self.pending_messages[message.hash]

        if hasattr(message, 'send_timestamp'):
            delivery_time = time.time() - message.send_timestamp
            if delivery_time < 60:
                time_str = f" ({delivery_time:.1f} seconds)"
            else:
                minutes = int(delivery_time // 60)
                seconds = int(delivery_time % 60)
                time_str = f" ({minutes}m {seconds}s)"
        else:
            time_str = ""

        print()
        self._print_color(f"✅ Message delivered to {recipient_str}{time_str}", Fore.GREEN + Style.BRIGHT)
        print("> ", end="", flush=True)

    def on_failed(self, message):
        """Callback for failed delivery"""
        dest_hash = RNS.prettyhexrep(message.destination_hash)
        recipient_str = self.format_contact_display(dest_hash, show_hash=True)

        if message.hash in self.pending_messages:
            del self.pending_messages[message.hash]

        if hasattr(message, 'send_timestamp'):
            fail_time = time.time() - message.send_timestamp
            if fail_time < 60:
                time_str = f" (after {fail_time:.1f} seconds)"
            else:
                minutes = int(fail_time // 60)
                seconds = int(fail_time % 60)
                time_str = f" (after {minutes}m {seconds}s)"
        else:
            time_str = ""

        print()
        self._print_color(f"❌ Delivery failed to {recipient_str}{time_str}", Fore.RED + Style.BRIGHT)
        print("> ", end="", flush=True)

    def show_status(self):
        """Show current status and connection info"""
        print(f"\n{'='*80}")
        self._print_color("SYSTEM STATUS", Fore.CYAN + Style.BRIGHT)
        print(f"{'='*80}")
        
        # Identity info
        print(f"\n{Fore.GREEN}Identity:{Style.RESET_ALL}")
        print(f"  Display Name: {self.display_name}")
        print(f"  LXMF Address: {RNS.prettyhexrep(self.destination.hash)}")
        
        # Network info
        print(f"\n{Fore.CYAN}Network:{Style.RESET_ALL}")
        print(f"  Auto-announce: Every {self.announce_interval}s")
        print(f"  Discovery alerts: {'ON' if self.show_announces else 'OFF'}")
        
        # Statistics
        with self.messages_lock:
            total_messages = len(self.messages)
            sent = sum(1 for m in self.messages if m['direction'] == 'outbound')
            received = sum(1 for m in self.messages if m['direction'] == 'inbound')
        
        with self.peers_lock:
            peer_count = len(self.announced_peers)
        
        contact_count = len(self.contacts)
        
        print(f"\n{Fore.YELLOW}Statistics:{Style.RESET_ALL}")
        print(f"  Contacts: {contact_count}")
        print(f"  Announced peers: {peer_count}")
        print(f"  Total messages: {total_messages} (↑{sent} ↓{received})")
        
        # System info
        print(f"\n{Fore.MAGENTA}System:{Style.RESET_ALL}")
        uptime = time.time() - self.start_time
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        print(f"  Uptime: {hours}h {minutes}m")
        print(f"  Suppressed errors: {self.suppressed_errors}")
        
        print(f"{'='*80}\n")

    def show_stats(self):
        """Show messaging statistics"""
        with self.messages_lock:
            messages_copy = self.messages.copy()
        
        if not messages_copy:
            print("\nNo messages yet\n")
            return
        
        # Calculate overall stats
        total_sent = sum(1 for msg in messages_copy if msg['direction'] == 'outbound')
        total_received = sum(1 for msg in messages_copy if msg['direction'] == 'inbound')
        total_messages = len(messages_copy)
        
        # Calculate per-user stats
        user_stats = {}
        
        for msg in messages_copy:
            if msg['direction'] == 'outbound':
                hash_key = msg.get('destination_hash', 'unknown')
            else:
                hash_key = msg.get('source_hash', 'unknown')
            
            if hash_key not in user_stats:
                user_stats[hash_key] = {'sent': 0, 'received': 0, 'total': 0}
            
            if msg['direction'] == 'outbound':
                user_stats[hash_key]['sent'] += 1
            else:
                user_stats[hash_key]['received'] += 1
            
            user_stats[hash_key]['total'] += 1
        
        # Display overall stats
        print(f"\n{'='*80}")
        self._print_color("MESSAGING STATISTICS", Fore.CYAN + Style.BRIGHT)
        print(f"{'='*80}")
        print(f"\n{Fore.GREEN}Overall Stats:{Style.RESET_ALL}")
        print(f"  Total Messages: {total_messages}")
        print(f"  Sent: {total_sent}")
        print(f"  Received: {total_received}")
        print(f"  Unique Contacts: {len(user_stats)}")
        
        # Display per-user stats
        print(f"\n{Fore.CYAN}Per-User Statistics:{Style.RESET_ALL}")
        print(f"{'='*80}")
        print(f"{'Contact':<40} {'Sent':<10} {'Received':<10} {'Total':<10}")
        print(f"{'-'*40} {'-'*10} {'-'*10} {'-'*10}")
        
        # Sort by total messages descending
        sorted_users = sorted(user_stats.items(), key=lambda x: x[1]['total'], reverse=True)
        
        for hash_str, stats in sorted_users:
            contact_display = self.format_contact_display_short(hash_str)
            # Truncate if too long
            if len(contact_display) > 38:
                contact_display = contact_display[:35] + "..."
            
            print(f"{contact_display:<40} {stats['sent']:<10} {stats['received']:<10} {stats['total']:<10}")
        
        print(f"{'='*80}\n")

    def show_messages(self, limit=10, filter_hash=None):
        """Show recent messages, optionally filtered by user hash"""
        with self.messages_lock:
            messages_copy = self.messages.copy()
        
        if not messages_copy:
            print("\nNo messages yet\n")
            return
        
        # Filter by hash if provided
        if filter_hash:
            # Normalize the filter hash
            clean_filter = filter_hash.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
            filtered_messages = []
            
            for msg in messages_copy:
                msg_hash = ""
                if msg['direction'] == 'outbound':
                    msg_hash = msg.get('destination_hash', '')
                else:
                    msg_hash = msg.get('source_hash', '')
                
                # Normalize the message hash
                clean_msg_hash = msg_hash.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
                
                if clean_msg_hash == clean_filter:
                    filtered_messages.append(msg)
            
            messages_copy = filtered_messages
            
            if not messages_copy:
                contact_display = self.format_contact_display_short(filter_hash)
                print(f"\nNo messages with {contact_display}\n")
                return
        
        # Show messages
        if filter_hash:
            contact_display = self.format_contact_display_short(filter_hash)
            print(f"\n{'='*80}")
            self._print_color(f"CONVERSATION WITH {contact_display.upper()}", Fore.CYAN + Style.BRIGHT)
            print(f"{'='*80}")
        else:
            print(f"\n{'='*80}")
            self._print_color(f"RECENT MESSAGES (showing last {min(limit, len(messages_copy))})", Fore.CYAN + Style.BRIGHT)
            print(f"{'='*80}")
        
        # Display messages
        display_messages = messages_copy[-limit:] if not filter_hash else messages_copy
        
        for idx, msg in enumerate(display_messages, 1):
            try:
                ts = datetime.fromtimestamp(msg['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                direction = "→" if msg['direction'] == 'outbound' else "←"
                
                if msg['direction'] == 'outbound':
                    contact = self.format_contact_display_short(msg['destination_hash'])
                else:
                    contact = self.format_contact_display_short(msg['source_hash'])
                
                if filter_hash:
                    # In conversation view, show full messages
                    print(f"\n[{idx}] {ts} {direction}")
                    if msg.get('title'):
                        print(f"Title: {msg['title']}")
                    print(f"\n{msg.get('content', '')}\n")
                    print(f"{'-'*80}")
                else:
                    # In list view, show preview
                    print(f"\n[{idx}] {ts} {direction} {contact}")
                    if msg.get('title'):
                        print(f"    Title: {msg['title']}")
                    
                    content = str(msg.get('content', ''))
                    if len(content) > 100:
                        print(f"    {content[:100]}...")
                    else:
                        print(f"    {content}")
                        
            except Exception as e:
                print(f"\n[{idx}] [Error displaying message: {e}]")
        
        print(f"\n{'='*80}")
        
        if filter_hash:
            # Set the reply target to this user when viewing their conversation
            # Store both hash and name for reply functionality
            self.last_sender_hash = filter_hash
            self.last_sender_name = self.get_contact_name_by_hash(filter_hash)
            
            self._print_color(f"\n💡 Reply target set to: {contact_display}", Fore.GREEN)
            self._print_color("   Type 'reply <message>' or 're <message>' to respond", Fore.CYAN)
        else:
            self._print_color("💡 Tip1: View conversations: 'messages list'", Fore.YELLOW)
            self._print_color("💡 Tip2: View conversation with specific user: 'messages user <#>'", Fore.YELLOW)
        
        print()

    def show_message_list_with_users(self):
        """Show a list of users you've messaged with, indexed for selection"""
        with self.messages_lock:
            messages_copy = self.messages.copy()
        
        if not messages_copy:
            print("\nNo messages yet\n")
            return
        
        # Build user list with message counts
        user_data = {}
        
        for msg in messages_copy:
            if msg['direction'] == 'outbound':
                hash_key = msg.get('destination_hash', 'unknown')
            else:
                hash_key = msg.get('source_hash', 'unknown')
            
            if hash_key == 'unknown':
                continue
            
            # Normalize hash
            clean_hash = hash_key.replace(":", "").replace(" ", "").lower()
            
            if clean_hash not in user_data:
                # Assign fixed index if new conversation
                conv_index = self.assign_conversation_index(clean_hash)
                user_data[clean_hash] = {
                    'sent': 0,
                    'received': 0,
                    'last_message_time': 0,
                    'index': conv_index,
                    'display_hash': hash_key  # Keep original format for display
                }
            
            if msg['direction'] == 'outbound':
                user_data[clean_hash]['sent'] += 1
            else:
                user_data[clean_hash]['received'] += 1
            
            # Track most recent message
            if msg['timestamp'] > user_data[clean_hash]['last_message_time']:
                user_data[clean_hash]['last_message_time'] = msg['timestamp']
        
        # Sort by fixed index (not by recent message)
        sorted_users = sorted(user_data.items(), key=lambda x: x[1]['index'])
        
        print(f"\n{'='*90}")
        self._print_color("MESSAGE CONVERSATIONS", Fore.CYAN + Style.BRIGHT)
        print(f"{'='*90}")
        print(f"{'#':<5} {'Contact':<40} {'Sent':<8} {'Received':<10} {'Last Message':<15}")
        print(f"{'-'*5} {'-'*40} {'-'*8} {'-'*10} {'-'*15}")
        
        for clean_hash, data in sorted_users:
            conv_index = data['index']
            hash_str = data['display_hash']
            contact_display = self.format_contact_display_short(hash_str)
            
            # Truncate if too long
            if len(contact_display) > 38:
                contact_display = contact_display[:35] + "..."
            
            # Format last message time
            time_diff = time.time() - data['last_message_time']
            if time_diff < 60:
                time_str = "just now"
            elif time_diff < 3600:
                minutes = int(time_diff / 60)
                time_str = f"{minutes}m ago"
            elif time_diff < 86400:
                hours = int(time_diff / 3600)
                time_str = f"{hours}h ago"
            else:
                days = int(time_diff / 86400)
                time_str = f"{days}d ago"
            
            print(f"{conv_index:<5} {contact_display:<40} {data['sent']:<8} {data['received']:<10} {time_str:<15}")
        
        print(f"{'='*90}")
        self._print_color("\n💡 Commands:", Fore.YELLOW)
        print(f"  {Fore.CYAN}messages user <#>{Fore.WHITE} - View full conversation with user by number")
        print(f"  {Fore.CYAN}messages [count]{Fore.WHITE}  - Show recent messages across all users")
        print()
        
        return sorted_users

    def show_help(self, category=None):
        """Show help with optional category filtering"""
        
        if category == 'messaging':
            self._show_messaging_help()
        elif category == 'contacts':
            self._show_contacts_help()
        elif category == 'settings':
            self._show_settings_help()
        elif category == 'system':
            self._show_system_help()
        else:
            self._show_main_help()

    def _show_main_help(self):
        """Show main help menu with categories"""
        if COLOR_ENABLED:
            print(f"\n{Fore.WHITE}╔═══════════════════════════════════════════════════════════════════════╗")
            print(f"║{' '*27}LXMF CLIENT COMMANDS{' '*27}║")
            print(f"╠═══════════════════════════════════════════════════════════════════════╣")
            
            # Messaging commands
            print(f"║                                                                       ║")
            print(f"║  {Fore.CYAN}📨 MESSAGING COMMANDS{Fore.WHITE}                                              ║")
            print(f"║  {'-'*67}  ║")
            commands = [
                ("send <name/#/hash> <msg>", "s", "Send a message"),
                ("reply <message>", "re", "Reply to last message"),
                ("messages [count]", "m", "Show recent messages"),
                ("messages list", "", "List all conversations"),
                ("messages user <#>", "", "View full conversation"),
            ]
            for long_cmd, short_cmd, description in commands:
                if short_cmd:
                    short_display = f"{Fore.YELLOW}({short_cmd}){Fore.WHITE}"
                    padding_after_short = 6 - len(short_cmd) - 2
                else:
                    short_display = " " * 6
                    padding_after_short = 0
                long_padded = f"{Fore.CYAN}{long_cmd:<24}{Fore.WHITE}"
                short_padded = short_display + " " * padding_after_short
                desc_padded = f"{description:<35}"
                print(f"║  {long_padded} {short_padded} {desc_padded}  ║")
            
            # Contacts & Peers
            print(f"║                                                                       ║")
            print(f"║  {Fore.GREEN}👥 CONTACTS & PEERS{Fore.WHITE}                                                ║")
            print(f"║  {'-'*67}  ║")
            commands = [
                ("contacts", "c", "List all contacts"),
                ("add <name> <hash>", "a", "Add a contact"),
                ("remove <name>", "rm", "Remove a contact"),
                ("peers", "p", "List announced peers"),
                ("sendpeer <#> <msg>", "sp", "Send to peer by number"),
                ("addpeer <#> [name]", "ap", "Add peer to contacts"),
            ]
            for long_cmd, short_cmd, description in commands:
                if short_cmd:
                    short_display = f"{Fore.YELLOW}({short_cmd}){Fore.WHITE}"
                    padding_after_short = 6 - len(short_cmd) - 2
                else:
                    short_display = " " * 6
                    padding_after_short = 0
                long_padded = f"{Fore.CYAN}{long_cmd:<24}{Fore.WHITE}"
                short_padded = short_display + " " * padding_after_short
                desc_padded = f"{description:<35}"
                print(f"║  {long_padded} {short_padded} {desc_padded}  ║")
            
            # Info & Stats
            print(f"║                                                                       ║")
            print(f"║  {Fore.MAGENTA}📊 INFORMATION & STATS{Fore.WHITE}                                             ║")
            print(f"║  {'-'*67}  ║")
            commands = [
                ("stats", "st", "Show messaging statistics"),
                ("status", "", "Show system status"),
                ("address", "addr", "Show your LXMF address"),
                ("replyto", "", "Show current reply target"),
            ]
            for long_cmd, short_cmd, description in commands:
                if short_cmd:
                    short_display = f"{Fore.YELLOW}({short_cmd}){Fore.WHITE}"
                    padding_after_short = 6 - len(short_cmd) - 2
                else:
                    short_display = " " * 6
                    padding_after_short = 0
                long_padded = f"{Fore.CYAN}{long_cmd:<24}{Fore.WHITE}"
                short_padded = short_display + " " * padding_after_short
                desc_padded = f"{description:<35}"
                print(f"║  {long_padded} {short_padded} {desc_padded}  ║")
            
            # Settings
            print(f"║                                                                       ║")
            print(f"║  {Fore.YELLOW}⚙️  SETTINGS{Fore.WHITE}                                                        ║")
            print(f"║  {'-'*67}  ║")
            commands = [
                ("settings", "", "Show settings menu"),
                ("name <new_name>", "n", "Change display name"),
                ("interval <seconds>", "i", "Change announce interval"),
                ("discoverannounce <on/off>", "da", "Toggle discovery alerts"),
            ]
            for long_cmd, short_cmd, description in commands:
                if short_cmd:
                    short_display = f"{Fore.YELLOW}({short_cmd}){Fore.WHITE}"
                    padding_after_short = 6 - len(short_cmd) - 2
                else:
                    short_display = " " * 6
                    padding_after_short = 0
                long_padded = f"{Fore.CYAN}{long_cmd:<24}{Fore.WHITE}"
                short_padded = short_display + " " * padding_after_short
                desc_padded = f"{description:<35}"
                print(f"║  {long_padded} {short_padded} {desc_padded}  ║")
            
            # System
            print(f"║                                                                       ║")
            print(f"║  {Fore.RED}🖥️  SYSTEM{Fore.WHITE}                                                            ║")
            print(f"║  {'-'*67}  ║")
            commands = [
                ("announce", "ann", "Announce now"),
                ("clear", "cls", "Clear the screen"),
                ("restart", "r", "Restart the client"),
                ("help", "h", "Show this help"),
                ("quit / exit", "q/e", "Exit"),
            ]
            for long_cmd, short_cmd, description in commands:
                if short_cmd:
                    short_display = f"{Fore.YELLOW}({short_cmd}){Fore.WHITE}"
                    padding_after_short = 6 - len(short_cmd) - 2
                else:
                    short_display = " " * 6
                    padding_after_short = 0
                long_padded = f"{Fore.CYAN}{long_cmd:<24}{Fore.WHITE}"
                short_padded = short_display + " " * padding_after_short
                desc_padded = f"{description:<35}"
                print(f"║  {long_padded} {short_padded} {desc_padded}  ║")
            
            print(f"╚═══════════════════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
            print(f"\n{Fore.YELLOW}💡 Tip: Type 'settings' for configuration options{Style.RESET_ALL}\n")
        
        else:
            # Fallback for no color - simplified version
            print("\n╔═══════════════════════════════════════════════════════════════════════╗")
            print("║                         LXMF CLIENT COMMANDS                          ║")
            print("╠═══════════════════════════════════════════════════════════════════════╣")
            print("║  Use 'help' to see all commands                                       ║")
            print("║  Use 'settings' for configuration                                     ║")
            print("╚═══════════════════════════════════════════════════════════════════════╝\n")

    def show_settings_menu(self):
        """Show interactive settings menu"""
        while True:
            print(f"\n{'='*70}")
            self._print_color("SETTINGS MENU", Fore.YELLOW + Style.BRIGHT)
            print(f"{'='*70}")
            
            print(f"\n{Fore.CYAN}Current Settings:{Style.RESET_ALL}")
            print(f"  [1] Display Name: {Fore.GREEN}{self.display_name}{Style.RESET_ALL}")
            print(f"  [2] Announce Interval: {Fore.GREEN}{self.announce_interval}s{Style.RESET_ALL}")
            print(f"  [3] Discovery Alerts: {Fore.GREEN}{'ON' if self.show_announces else 'OFF'}{Style.RESET_ALL}")
            
            print(f"\n{Fore.YELLOW}Options:{Style.RESET_ALL}")
            print("  [1-3] - Change setting")
            print("  [b]   - Back to main menu")
            print("  [s]   - Save and exit")
            
            print(f"{'='*70}")
            
            choice = input("\nSelect option: ").strip().lower()
            
            if choice == '1':
                new_name = input(f"\nEnter new display name [{self.display_name}]: ").strip()
                if new_name:
                    self.display_name = new_name
                    self.destination.display_name = self.display_name
                    self.save_config()
                    self.destination.announce()
                    self._print_success(f"Display name changed to: {self.display_name}")
                    self._print_success("Announced to network")
                else:
                    print("Cancelled")
            
            elif choice == '2':
                current = self.announce_interval
                interval_str = input(f"\nEnter announce interval in seconds [{current}]: ").strip()
                if interval_str:
                    try:
                        new_interval = int(interval_str)
                        if new_interval < 30:
                            self._print_warning("Minimum interval is 30 seconds, setting to 30")
                            new_interval = 30
                        
                        self.announce_interval = new_interval
                        self.save_config()
                        
                        # Restart announce loop
                        self.stop_event.set()
                        time.sleep(0.1)
                        self.stop_event.clear()
                        
                        self._print_success(f"Announce interval changed to: {self.announce_interval}s")
                    except ValueError:
                        self._print_error("Invalid number")
                else:
                    print("Cancelled")
            
            elif choice == '3':
                # Toggle discovery alerts
                self.show_announces = not self.show_announces
                self.save_config()
                status = "enabled" if self.show_announces else "disabled"
                self._print_success(f"Discovery alerts {status}")
            
            elif choice in ['b', 'back']:
                break
            
            elif choice in ['s', 'save']:
                self.save_config()
                self._print_success("Settings saved")
                break
            
            else:
                self._print_error("Invalid option")

    def resolve_command(self, cmd):
        """Resolve command aliases to full commands"""
        return self.command_aliases.get(cmd, cmd)
            
    def list_peers(self):
        """List all announced LXMF peers"""
        with self.peers_lock:
            peers_copy = dict(self.announced_peers)
        
        if not peers_copy:
            print("\nNo LXMF peers announced yet")
            print("Wait for peers to announce or ask them to announce\n")
            return
        
        # Sort by index (which is the order they were discovered)
        sorted_peers = sorted(peers_copy.items(), key=lambda x: x[1]['index'])
        
        print(f"\n{'='*95}")
        self._print_color("ANNOUNCED LXMF PEERS", Fore.CYAN + Style.BRIGHT)
        print(f"{'='*95}")
        print(f"{'#':<5} {'Display Name':<35} {'Hash':<32} {'Last Seen':<15}")
        print(f"{'-'*5} {'-'*35} {'-'*32} {'-'*15}")
        
        for hash_str, peer_data in sorted_peers:
            peer_index = peer_data['index']
            display_name = peer_data['display_name']
            last_seen = peer_data['last_seen']
            
            # Format last seen time
            time_diff = time.time() - last_seen
            if time_diff < 60:
                time_str = "just now"
            elif time_diff < 3600:
                minutes = int(time_diff / 60)
                time_str = f"{minutes}m ago"
            elif time_diff < 86400:
                hours = int(time_diff / 3600)
                time_str = f"{hours}h ago"
            else:
                days = int(time_diff / 86400)
                time_str = f"{days}d ago"
            
            # Check if already in contacts
            is_contact = False
            for contact_name, contact_data in self.contacts.items():
                if contact_data['hash'].lower() == hash_str:
                    is_contact = True
                    break
            
            # Truncate display name if too long
            display_shown = display_name[:33] + ".." if len(display_name) > 35 else display_name
            
            # Mark contacts with a star
            marker = "★" if is_contact else " "
            
            print(f"{marker}{peer_index:<4} {display_shown:<35} {hash_str:<32} {time_str:<15}")
        
        print(f"{'='*95}")
        self._print_color("\n💡 Commands:", Fore.YELLOW)
        print(f"  {Fore.CYAN}sendpeer <#> <message>{Fore.WHITE}  (sp) - Send message to peer by number")
        print(f"  {Fore.CYAN}addpeer <#> [name]{Fore.WHITE}       (ap) - Add peer to contacts")
        print(f"  {Fore.GREEN}★ = Already in contacts{Fore.WHITE}")
        print()

    def send_to_peer(self, peer_index, content, title=None):
        """Send message to a peer by index number"""
        with self.peers_lock:
            peers_copy = dict(self.announced_peers)
        
        try:
            idx = int(peer_index)
            
            # Find peer by index
            target_peer = None
            for hash_str, peer_data in peers_copy.items():
                if peer_data['index'] == idx:
                    target_peer = (hash_str, peer_data)
                    break
            
            if not target_peer:
                self._print_error(f"Invalid peer number #{idx}. Use 'peers' to see the list")
                return False
            
            hash_str, peer_data = target_peer
            display_name = peer_data['display_name']
            
            print(f"Sending to peer #{idx}: {display_name}")
            return self.send_message(hash_str, content, title)
        
        except ValueError:
            self._print_error("Peer number must be a valid number")
            return False

    def add_peer_to_contacts(self, peer_index, custom_name=None):
        """Add an announced peer to contacts"""
        with self.peers_lock:
            peers_copy = dict(self.announced_peers)
        
        try:
            idx = int(peer_index)
            
            # Find peer by index
            target_peer = None
            for hash_str, peer_data in peers_copy.items():
                if peer_data['index'] == idx:
                    target_peer = (hash_str, peer_data)
                    break
            
            if not target_peer:
                self._print_error(f"Invalid peer number #{idx}. Use 'peers' to see the list")
                return
            
            hash_str, peer_data = target_peer
            display_name = peer_data['display_name']
            
            # Check if already in contacts
            for contact_name, contact_data in self.contacts.items():
                if contact_data['hash'].lower() == hash_str:
                    self._print_warning(f"Already in contacts as: {contact_name}")
                    return
            
            # Use custom name if provided, otherwise use display name
            contact_name = custom_name if custom_name else display_name
            
            self.add_contact(contact_name, hash_str)
        
        except ValueError:
            self._print_error("Peer number must be a valid number")

    def notify_new_message(self):
        """Visual and audio notification for new message - cross-platform with Termux support"""
        import shutil
        import platform
        import os
        
        # === SOUND NOTIFICATION ===
        system = platform.system()
        is_termux = os.path.exists('/data/data/com.termux')
        
        try:
            if is_termux:
                # === TERMUX/ANDROID SPECIFIC ===
                try:
                    # Vibration pattern - short bursts matching melody
                    os.system('termux-vibrate -d 80 2>/dev/null &')
                    time.sleep(0.09)
                    os.system('termux-vibrate -d 80 2>/dev/null &')
                    time.sleep(0.09)
                    os.system('termux-vibrate -d 80 2>/dev/null &')
                    time.sleep(0.09)
                    os.system('termux-vibrate -d 150 2>/dev/null &')  # Longer vibration
                    time.sleep(0.16)
                    os.system('termux-vibrate -d 100 2>/dev/null &')
                    
                    # System notification
                    os.system('termux-notification --title "📨 LXMF Message" --content "New message received" --sound 2>/dev/null &')
                except:
                    pass
                
                # Terminal bells as backup
                for _ in range(3):
                    print("\a", end="", flush=True)
                    time.sleep(0.1)
            
            elif system == 'Windows':
                try:
                    import winsound
                    # Pleasant notification melody - fast version
                    melody = [
                        (523, 80),    # C5
                        (659, 80),    # E5
                        (784, 80),    # G5
                        (1047, 150),  # C6 (emphasis)
                        (784, 100),   # G5
                    ]
                    
                    for freq, duration in melody:
                        winsound.Beep(freq, duration)
                        time.sleep(0.01)
                    
                except:
                    # Fallback to terminal bell
                    for _ in range(3):
                        print("\a", end="", flush=True)
                        time.sleep(0.1)
            
            elif system == 'Linux':
                try:
                    # Try system sound first
                    result = os.system('paplay /usr/share/sounds/freedesktop/stereo/message-new-instant.oga 2>/dev/null &')
                    
                    if result != 0:
                        # If paplay fails, try beep command with melody
                        os.system('beep -f 523 -l 80 -n -f 659 -l 80 -n -f 784 -l 80 -n -f 1047 -l 150 -n -f 784 -l 100 2>/dev/null &')
                    
                    # Also do terminal bells
                    for _ in range(2):
                        print("\a", end="", flush=True)
                        time.sleep(0.1)
                        
                except:
                    # Fallback to terminal bell
                    for _ in range(3):
                        print("\a", end="", flush=True)
                        time.sleep(0.1)
            
            else:
                # Generic/macOS - terminal bell
                for _ in range(3):
                    print("\a", end="", flush=True)
                    time.sleep(0.1)
        
        except Exception as e:
            # Ultimate fallback
            for _ in range(3):
                print("\a", end="", flush=True)
                time.sleep(0.1)
        
        # === VISUAL NOTIFICATION ===
        if COLOR_ENABLED:
            try:
                terminal_width = shutil.get_terminal_size().columns
            except:
                terminal_width = 80
            
            # Synchronized visual - snappy ripple effect
            ripple_sequence = [
                (Fore.GREEN, '░', 0.05),
                (Fore.GREEN, '▒', 0.05),
                (Fore.GREEN, '▓', 0.05),
                (Fore.CYAN, '█', 0.08),
                (Fore.YELLOW, '▓', 0.06),
                (Fore.GREEN, '▒', 0.05),
            ]
            
            for color, char, duration in ripple_sequence:
                print(f"\r{color}{Style.BRIGHT}{char * terminal_width}{Style.RESET_ALL}", end="", flush=True)
                time.sleep(duration)
            
            # Message flash with emoji
            if is_termux:
                msg = " 📱 NEW MESSAGE! "
            else:
                msg = " 📬 NEW MESSAGE! "
            
            print(f"\r{Fore.GREEN}{Style.BRIGHT}{msg.center(terminal_width, '═')}{Style.RESET_ALL}", end="", flush=True)
            time.sleep(0.18)
            
            # Clear
            print(f"\r{' ' * terminal_width}", end="\r", flush=True)
        else:
            print("\n>>> NEW MESSAGE RECEIVED <<<\n")
    
    def shutdown(self):
        """Clean shutdown"""
        print("\nShutting down...")
        self.stop_event.set()
        
        # Force save any pending cache updates
        try:
            if self.cache_dirty:
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(self.display_name_cache, f, indent=2, ensure_ascii=False)
        except:
            pass
        
        if hasattr(self, 'announce_thread'):
            self.announce_thread.join(timeout=2)
        
        if hasattr(self, 'router_thread'):
            self.router_thread.join(timeout=2)
        
        time.sleep(0.5)

    def clear_screen(self):
        """Clear the terminal screen"""
        import os
        # Windows
        if os.name == 'nt':
            os.system('cls')
        # Unix/Linux/Mac
        else:
            os.system('clear')
        
        # Reprint the banner after clearing
        banner = """
        ██╗     ██╗  ██╗███╗   ███╗███████╗
        ██║     ╚██╗██╔╝████╗ ████║██╔════╝
        ██║      ╚███╔╝ ██╔████╔██║█████╗  
        ██║      ██╔██╗ ██║╚██╔╝██║██╔══╝  
        ███████╗██╔╝ ██╗██║ ╚═╝ ██║██║     
        ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝     
            Interactive LXMF Client
        With Proper Display Name Support
    """
        print("\n" + "="*60)
        if COLOR_ENABLED:
            print(Fore.WHITE + Style.BRIGHT + banner + Style.RESET_ALL)
        else:
            print(banner)
        print("="*60 + "\n")

    def restart_client(self):
        """Restart the client"""
        print("\n" + "="*60)
        self._print_color("Restarting LXMF Client...", Fore.YELLOW + Style.BRIGHT)
        print("="*60 + "\n")
        
        # Shutdown current instance
        self.shutdown()
        
        # Restart the Python script
        import sys
        import os
        
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def show_progress_spinner(self, message, duration=2):
        """Show a spinner for background operations"""
        import itertools
        spinner = itertools.cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])
        end_time = time.time() + duration
        
        while time.time() < end_time:
            if COLOR_ENABLED:
                print(f"\r{Fore.CYAN}{next(spinner)}{Style.RESET_ALL} {message}...", end="", flush=True)
            else:
                print(f"\r{next(spinner)} {message}...", end="", flush=True)
            time.sleep(0.1)
        print("\r" + " " * (len(message) + 10), end="\r")
    
    def run(self):
        """Main loop"""
        self.running = True
        
        # Show brief welcome message instead of full help
        print(f"\n{Fore.CYAN}Welcome to LXMF Client!{Style.RESET_ALL}" if COLOR_ENABLED else "\nWelcome to LXMF Client!")
        print(f"{Fore.YELLOW}Type 'help' or 'h' to see available commands{Style.RESET_ALL}\n" if COLOR_ENABLED else "Type 'help' or 'h' to see available commands\n")
        
        # Show initial status and help (disable, uncomment to enable)
        #self.show_status()
        #self.show_help()
        
        try:
            while self.running:
                try:
                    # Dynamic prompt showing unread indicator
                    with self.messages_lock:
                        if self.messages and self.messages[-1]['direction'] == 'inbound':
                            # Show if last message was inbound
                            prompt = f"{Fore.GREEN}●{Style.RESET_ALL} > " if COLOR_ENABLED else "● > "
                        else:
                            prompt = "> "
                    
                    cmd_line = input(prompt).strip()
                           
                    if not cmd_line:
                        continue
                    
                    parts = cmd_line.split(maxsplit=2)
                    cmd = self.resolve_command(parts[0].lower())
                    
                    if cmd in ['quit', 'exit']:
                        self.running = False
                        print("Goodbye!")
                        break
                    
                    elif cmd == 'help':
                        self.show_help()

                    elif cmd == 'status':
                        self.show_status()

                    elif cmd == 'settings':
                        self.show_settings_menu()
                    
                    elif cmd == 'address':
                        print(f"\nDisplay Name: {self.display_name}")
                        print(f"LXMF Address: {RNS.prettyhexrep(self.destination.hash)}")
                        print(f"Auto-announce: Every {self.announce_interval}s\n")
                    
                    elif cmd == 'name':
                        if len(parts) < 2:
                            print("Usage: name <new_name>")
                        else:
                            self.display_name = ' '.join(parts[1:])
                            self.destination.display_name = self.display_name
                            self.save_config()
                            self.destination.announce()
                            self._print_success(f"Display name: {self.display_name}")
                            self._print_success("Announced to network")
                    
                    elif cmd == 'interval':
                        if len(parts) < 2:
                            print(f"Current interval: {self.announce_interval}s")
                            print("Usage: interval <seconds>")
                            print("Minimum: 30 seconds")
                        else:
                            try:
                                new_interval = int(parts[1])
                                if new_interval < 30:
                                    self._print_warning("Minimum interval is 30 seconds, setting to 30")
                                    new_interval = 30
                                
                                self.announce_interval = new_interval
                                self.save_config()
                                self.stop_event.set()
                                time.sleep(0.1)
                                self.stop_event.clear()
                                
                                self._print_success(f"Announce interval changed to: {self.announce_interval}s")
                                self._print_success("New interval will apply from next cycle")
                            except ValueError:
                                self._print_error("Invalid number")
                    
                    elif cmd == 'announce':
                        self.destination.announce()
                        self._print_success("Announced manually")
                    
                    elif cmd == 'contacts':
                        self.list_contacts()
                    
                    elif cmd == 'add':
                        if len(parts) < 3:
                            print("Usage: add <name> <hash>")
                        else:
                            self.add_contact(parts[1], parts[2])
                    
                    elif cmd == 'remove':
                        if len(parts) < 2:
                            print("Usage: remove <name>")
                        else:
                            if parts[1] in self.contacts:
                                del self.contacts[parts[1]]
                                self.save_contacts()
                                self._print_success(f"Removed: {parts[1]}")
                            else:
                                self._print_error(f"Not found: {parts[1]}")
                    
                    elif cmd == 'reply':
                        if len(parts) < 2:
                            print("Usage: reply <message>")
                            if self.last_sender_hash:
                                sender_display = self.format_contact_display(self.last_sender_hash, show_hash=False)
                                print(f"Will reply to: {sender_display}")
                            else:
                                self._print_warning("No recent message to reply to")
                        else:
                            if self.last_sender_hash is None:
                                self._print_error("No recent message to reply to")
                                print("   Receive a message first, then use 'reply'")
                            else:
                                message_text = ' '.join(parts[1:])
                                self.send_message(self.last_sender_hash, message_text)
                    
                    elif cmd == 'replyto':
                        if self.last_sender_hash:
                            sender_display = self.format_contact_display(self.last_sender_hash, show_hash=True)
                            print(f"\nCurrent reply target: {sender_display}\n")
                        else:
                            print("\nNo reply target set")
                            print("Receive a message first\n")
                    
                    elif cmd == 'send':
                        if len(parts) < 3:
                            print("Usage: send <name/hash> <message>")
                        else:
                            message_text = ' '.join(parts[2:])
                            self.send_message(parts[1], message_text)
                                                            
                    elif cmd == 'messages':
                        if len(parts) >= 2 and parts[1].lower() == 'user':
                            # View conversation with specific user by index
                            if len(parts) >= 3:
                                try:
                                    user_idx = int(parts[2])
                                    
                                    # Find the conversation by fixed index
                                    target_hash = None
                                    for hash_str, conv_idx in self.conversation_indices.items():
                                        if conv_idx == user_idx:
                                            target_hash = hash_str
                                            break
                                    
                                    if target_hash:
                                        self.show_messages(limit=9999, filter_hash=target_hash)
                                    else:
                                        self._print_error(f"No conversation with index #{user_idx}. Use 'messages list' to see available conversations")
                                except ValueError:
                                    self._print_error("User number must be a valid number")
                            else:
                                print("Usage: messages user <#>")
                                print("Use 'messages list' to see numbered user list")
                        elif len(parts) >= 2 and parts[1].lower() == 'list':
                            # Show list of users with message counts
                            self.show_message_list_with_users()
                        else:
                            # Show recent messages
                            limit = 10
                            if len(parts) > 1:
                                try:
                                    limit = int(parts[1])
                                except ValueError:
                                    self._print_warning("Invalid number, showing last 10 messages")
                            self.show_messages(limit)

                    elif cmd == 'stats':
                        self.show_stats()

                    elif cmd == 'peers':
                        self.list_peers()

                    elif cmd == 'sendpeer':
                        if len(parts) < 3:
                            print("Usage: sendpeer <peer_number> <message>")
                            print("Use 'peers' to see the list first")
                        else:
                            message_text = ' '.join(parts[2:])
                            self.send_to_peer(parts[1], message_text)

                    elif cmd == 'addpeer':
                        if len(parts) < 2:
                            print("Usage: addpeer <peer_number> [custom_name]")
                            print("Use 'peers' to see the list first")
                        else:
                            custom_name = ' '.join(parts[2:]) if len(parts) > 2 else None
                            self.add_peer_to_contacts(parts[1], custom_name)

                    elif cmd == 'discoverannounce':
                        if len(parts) < 2:
                            status = "ON" if self.show_announces else "OFF"
                            print(f"\nDiscovery announces: {status}")
                            print("Usage: discoverannounce <on/off>")
                            print("  Controls whether new peer discoveries are shown\n")
                        else:
                            setting = parts[1].lower()
                            if setting in ['on', 'yes', 'true', '1']:
                                self.show_announces = True
                                self.save_config()
                                self._print_success("Discovery announces enabled")
                            elif setting in ['off', 'no', 'false', '0']:
                                self.show_announces = False
                                self.save_config()
                                self._print_success("Discovery announces disabled")
                            else:
                                self._print_error("Use 'on' or 'off'")

                    elif cmd == 'clear':
                        self.clear_screen()

                    elif cmd == 'restart':
                        self.restart_client()
                        # Note: execution will not continue past this point
                        break
                    
                    elif cmd == 'debug':
                        print(f"\n=== Debug Info ===")
                        print(f"Suppressed file errors: {self.suppressed_errors}")
                        print(f"Cache dirty: {self.cache_dirty}")
                        print(f"Last cache save: {time.time() - self.last_cache_save:.1f}s ago")
                        print(f"Announced peers: {len(self.announced_peers)}")
                        print(f"Cached display names: {len(self.display_name_cache)}")
                        print()
                    
                    else:
                        print(f"Unknown command: {cmd}")
                        print("Type 'help' or 'h' for commands")
                
                except EOFError:
                    break
                except KeyboardInterrupt:
                    print("\nType 'quit' or 'q' to exit")
                    continue
                except Exception as e:
                    self._print_error(f"Error: {e}")
        
        finally:
            self.shutdown()


def main():
    banner = """
    ██╗     ██╗  ██╗███╗   ███╗███████╗
    ██║     ╚██╗██╔╝████╗ ████║██╔════╝
    ██║      ╚███╔╝ ██╔████╔██║█████╗  
    ██║      ██╔██╗ ██║╚██╔╝██║██╔══╝  
    ███████╗██╔╝ ██╗██║ ╚═╝ ██║██║     
    ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝     
"""
    print("\n" + "="*60)
    if COLOR_ENABLED:
        print(Fore.CYAN + Style.BRIGHT + banner)
        print(Fore.WHITE + "        Interactive LXMF Client")
        print(Fore.GREEN + "    With Display Name & Peer Discovery")
        print(Style.RESET_ALL)
    else:
        print(banner)
        print("         Interactive LXMF Client")
        print("     With Display Name & Peer Discovery")
    print("="*60 + "\n")
    
    client = LXMFClient()
    client.run()


if __name__ == "__main__":
    main()
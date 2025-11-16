#!/usr/bin/env python3
"""
Terminal-Based Interactive LXMF Messaging Client

"""

import RNS
import LXMF
import time
import os
import json
import threading
from datetime import datetime
import shutil
import traceback
import itertools
import subprocess
import sys
import platform
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import HTML 

try:
    from colorama import init, Fore, Style, just_fix_windows_console  # type: ignore
    
    # Different approach for Windows
    import platform
    if platform.system() == 'Windows':
        just_fix_windows_console()
    else:
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
        self.auto_announce_enabled = True
        self.stop_event = threading.Event()
        self.show_announces = True
        self.start_time = time.time()

        # Notification settings
        self.notify_sound = True      # Platform-specific sounds (beeps/melody)
        self.notify_bell = True       # Terminal bell
        self.notify_visual = True     # Visual flash effect
        
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

        # Blacklist system
        self.blacklist = set()  # Set of blocked destination hashes
        self.blacklist_file = os.path.join(storage_path, "blacklist.json")

        # Plugin system
        self.plugins = {}
        self.plugins_dir = os.path.join(storage_path, "plugins")
        self.plugins_enabled = {}
        self.plugins_config_file = os.path.join(storage_path, "plugins_config.json")
        
        # Stamp cost settings
        self.stamp_cost = 0  # 0 = disabled
        self.stamp_cost_enabled = False
        self.ignore_invalid_stamps = True  # Reject messages with invalid stamps
        
        # Command aliases
        self.command_aliases = {
            'h': 'help',
            's': 'send',
            're': 'reply',
            'm': 'messages',
            'c': 'contacts',
            'a': 'add',
            'e': 'edit',    
            'rm': 'remove',
            'p': 'peers',
            'sp': 'sendpeer',
            'ap': 'addpeer',
            'st': 'stats',
            'addr': 'address',
            'n': 'name',
            'i': 'interval',
            'cls': 'clear',
            'r': 'restart',
            'q': 'quit',
            'set': 'settings',
            'bl': 'blacklist',
            'ann': 'announce',
            'save': 'savecontact', 
        }
        
        self.Fore = Fore
        self.Style = Style

        os.makedirs(storage_path, exist_ok=True)
        os.makedirs(self.messages_path, exist_ok=True)
        
        # === LOAD CONFIGURATION FIRST (before Reticulum) ===
        self.load_config()
        
        # === NOW INITIALIZE RETICULUM ===
        self._print_color("🌐 Initializing Reticulum...", Fore.CYAN)
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

        # Configure stamp cost on the destination
        if self.stamp_cost_enabled and self.stamp_cost > 0:
            try:
                # Set the stamp cost directly on the destination
                if hasattr(self.destination, 'stamp_cost'):
                    setattr(self.destination, 'stamp_cost', self.stamp_cost)  # type: ignore
                self._print_success(f"Stamp cost configured: {self.stamp_cost} bits")
                # Force an announce so the stamp cost is advertised
                if hasattr(self.destination, 'announce'):
                    self.destination.announce()  # type: ignore
                    self._print_success("📡 Announced with stamp cost")
            except Exception as e:
                self._print_warning(f"Could not set stamp cost: {e}")
        
        # Register callbacks
        self.router.register_delivery_callback(self.on_message_received)
        
        # Register announce handler to capture display names
        self.register_announce_handler()
        
        # Load contacts and messages
        self.load_contacts()
        self.load_messages()
        self.load_conversation_indices()
        self.load_blacklist()

        # Load plugins
        self.load_plugins()
        
        # Setup thread exception handler
        threading.excepthook = self.thread_exception_handler
                
        # Show info
        import shutil
        try:
            width = shutil.get_terminal_size().columns
        except:
            width = 60

        sep_width = min(width, 60)

        print(f"\n{'─'*sep_width}")
        self._print_color(f"Display Name: {self.display_name}", Fore.GREEN + Style.BRIGHT)
        if hasattr(self.destination, 'hash'):
            self._print_color(f"LXMF Address: {RNS.prettyhexrep(self.destination.hash)}", Fore.CYAN)  # type: ignore
        self._print_color(f"Auto-announce: Every {self.announce_interval} seconds", Fore.YELLOW)

        # Show stamp cost status
        if self.stamp_cost_enabled and self.stamp_cost > 0:
            self._print_color(f"Stamp Cost: ENABLED ({self.stamp_cost} bits)", Fore.RED + Style.BRIGHT)
        else:
            self._print_color(f"Stamp Cost: DISABLED", Fore.WHITE)

        print(f"{'─'*sep_width}\n")
        
        # Initial announce (this will now include stamp cost)
        self._print_color("📡 Announcing to network...", Fore.CYAN)
        if hasattr(self.destination, 'announce'):
            self.destination.announce()  # type: ignore
            self._print_success("Initial announce complete")
        
        # Start background threads
        self.announce_thread = threading.Thread(target=self.announce_loop, daemon=True)
        self.announce_thread.start()
        
        self.router_thread = threading.Thread(target=self.router_job_loop, daemon=True)
        self.router_thread.start()

    def resolve_contact_or_hash(self, target):
        """
        Resolve a contact name, number, or hash to a destination hash.
        Returns normalized hash string or None if not found.
        """
        if not target:
            return None
        
        # First, check if it's a direct hash (32 hex chars, possibly with colons/brackets)
        clean_target = target.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
        if len(clean_target) == 64:  # Valid hash length
            return clean_target
        
        # Try to parse as contact index number
        try:
            contact_idx = int(target)
            # Search contacts by index
            for name, data in self.contacts.items():
                if data.get('index') == contact_idx:
                    return data['hash'].replace(":", "").replace(" ", "").lower()
            
            # Search conversation indices
            for hash_str, conv_idx in self.conversation_indices.items():
                if conv_idx == contact_idx:
                    return hash_str.replace(":", "").replace(" ", "").lower()
            
            # Search peers by index
            with self.peers_lock:
                for hash_str, peer_data in self.announced_peers.items():
                    if peer_data.get('index') == contact_idx:
                        return hash_str.replace(":", "").replace(" ", "").lower()
            
            return None
        except ValueError:
            # Not a number, treat as contact name
            pass
        
        # Search by contact name
        target_lower = target.lower()
        for name, data in self.contacts.items():
            if name.lower() == target_lower:
                return data['hash'].replace(":", "").replace(" ", "").lower()
        
        # Search by display name in peers
        with self.peers_lock:
            for hash_str, peer_data in self.announced_peers.items():
                display_name = peer_data.get('display_name', '')
                if display_name.lower() == target_lower:
                    return hash_str.replace(":", "").replace(" ", "").lower()
        
        return None

    def load_plugins(self):
        """Load all enabled plugins from plugins directory"""
        import importlib.util
        import sys
        
        if not os.path.exists(self.plugins_dir):
            return
        
        # Load plugin configuration
        if os.path.exists(self.plugins_config_file):
            try:
                with open(self.plugins_config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.plugins_enabled = config.get('enabled', {})
            except Exception as e:
                self._print_warning(f"Error loading plugin config: {e}")
        
        # Scan plugins directory
        for filename in os.listdir(self.plugins_dir):
            if filename.endswith('.py') and not filename.startswith('_'):
                plugin_name = filename[:-3]
                
                # Check if plugin is enabled (default to enabled)
                if not self.plugins_enabled.get(plugin_name, True):
                    continue
                
                try:
                    # Load the plugin module
                    plugin_path = os.path.join(self.plugins_dir, filename)
                    spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[plugin_name] = module
                        spec.loader.exec_module(module)
                    else:
                        continue
                    
                    # Get plugin class
                    if hasattr(module, 'Plugin'):
                        plugin_instance = module.Plugin(self)
                        self.plugins[plugin_name] = plugin_instance
                        self._print_success(f"Loaded plugin: {plugin_name}")
                    else:
                        self._print_warning(f"Plugin {plugin_name} has no Plugin class")
                
                except Exception as e:
                    self._print_warning(f"Failed to load plugin {plugin_name}: {e}")

    def save_plugins_config(self):
        """Save plugin configuration"""
        try:
            config = {'enabled': self.plugins_enabled}
            with open(self.plugins_config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            self._print_warning(f"Error saving plugin config: {e}")

    def handle_plugin_command(self, cmd, parts):
        """Check if command should be handled by a plugin"""
        for plugin_name, plugin in self.plugins.items():
            if hasattr(plugin, 'commands') and cmd in plugin.commands:
                try:
                    plugin.handle_command(cmd, parts)
                    return True
                except Exception as e:
                    self._print_error(f"Plugin {plugin_name} error: {e}")
                    return True
        return False

    def handle_plugin_message(self, message, msg_data):
        """Let plugins process incoming messages"""
        for plugin_name, plugin in self.plugins.items():
            try:
                if hasattr(plugin, 'on_message'):
                    # Plugin can return True to indicate it handled the message
                    if plugin.on_message(message, msg_data):
                        return True
            except Exception as e:
                self._print_warning(f"Plugin {plugin_name} message handler error: {e}")
        return False

    def list_plugins(self):
        """List all available plugins"""
        import shutil
        import os
        
        try:
            width = min(shutil.get_terminal_size().columns, 80)
        except:
            width = 80
        
        print(f"\n{'─'*width}")
        self._print_color("PLUGINS", Fore.CYAN + Style.BRIGHT)
        print(f"{'─'*width}")
        
        # Scan plugins directory for all .py files
        available_plugins = {}
        
        if os.path.exists(self.plugins_dir):
            for filename in os.listdir(self.plugins_dir):
                if filename.endswith('.py') and not filename.startswith('_'):
                    plugin_name = filename[:-3]
                    available_plugins[plugin_name] = {
                        'loaded': plugin_name in self.plugins,
                        'enabled': self.plugins_enabled.get(plugin_name, True),
                        'instance': self.plugins.get(plugin_name)
                    }
        
        if not available_plugins:
            print("\nNo plugins found")
            print(f"Place plugin files in: {self.plugins_dir}\n")
            return
        
        print(f"\n{'Plugin':<20} {'Status':<15} {'Description'}")
        print(f"{'─'*20} {'─'*15} {'─'*30}")
        
        for plugin_name, info in sorted(available_plugins.items()):
            # Determine status
            if info['loaded'] and info['enabled']:
                status = f"{Fore.GREEN}Loaded{Style.RESET_ALL}"
            elif info['enabled'] and not info['loaded']:
                status = f"{Fore.YELLOW}Enabled (reload){Style.RESET_ALL}"
            else:
                status = f"{Fore.RED}Disabled{Style.RESET_ALL}"
            
            # Get description
            if info['instance']:
                description = getattr(info['instance'], 'description', 'No description')
            else:
                description = "Not loaded"
            
            # Truncate description if too long
            if len(description) > 30:
                description = description[:27] + "..."
            
            print(f"{plugin_name:<20} {status:<25} {description}")
        
        print(f"{'─'*width}")
        self._print_color("\n💡 Commands:", Fore.YELLOW)
        print("  plugin enable <name>  - Enable a plugin")
        print("  plugin disable <name> - Disable a plugin")
        print("  plugin reload         - Reload all plugins")
        print()

    def load_blacklist(self):
        """Load blacklist from file"""
        if os.path.exists(self.blacklist_file):
            try:
                with open(self.blacklist_file, 'r', encoding='utf-8') as f:
                    blacklist_data = json.load(f)
                    # Convert list to set and normalize hashes
                    self.blacklist = set(hash_str.replace(":", "").replace(" ", "").lower() 
                                    for hash_str in blacklist_data)
                if self.blacklist:
                    self._print_success(f"Loaded {len(self.blacklist)} blocked addresses")
            except Exception as e:
                self._print_warning(f"Error loading blacklist: {e}")

    def save_blacklist(self):
        """Save blacklist to file"""
        try:
            # Convert set to sorted list for JSON
            blacklist_list = sorted(list(self.blacklist))
            with open(self.blacklist_file, 'w', encoding='utf-8') as f:
                json.dump(blacklist_list, f, indent=2)
        except Exception as e:
            self._print_warning(f"Error saving blacklist: {e}")

    def is_blacklisted(self, destination_hash):
        """Check if a destination hash is blacklisted"""
        if not destination_hash:
            return False
        # Normalize the hash for comparison
        normalized = destination_hash.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
        return normalized in self.blacklist

    def add_to_blacklist(self, destination_hash):
        """Add a destination hash to the blacklist"""
        if not destination_hash:
            self._print_error("Invalid destination hash")
            return False
        
        # Normalize the hash
        normalized = destination_hash.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
        
        if normalized in self.blacklist:
            self._print_warning("Already blacklisted")
            return False
        
        self.blacklist.add(normalized)
        self.save_blacklist()
        return True

    def remove_from_blacklist(self, destination_hash):
        """Remove a destination hash from the blacklist"""
        if not destination_hash:
            self._print_error("Invalid destination hash")
            return False
        
        # Normalize the hash
        normalized = destination_hash.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
        
        if normalized not in self.blacklist:
            self._print_warning("Not in blacklist")
            return False
        
        self.blacklist.remove(normalized)
        self.save_blacklist()
        return True

    def list_blacklist(self):
        """List all blacklisted addresses"""
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 80)
        except:
            width = 80
        
        if not self.blacklist:
            print("\nNo blacklisted addresses\n")
            return
        
        print(f"\n{'─'*width}")
        self._print_color("BLACKLIST", Fore.RED + Style.BRIGHT)
        print(f"{'─'*width}")
        
        # Sort for consistent display
        sorted_blacklist = sorted(self.blacklist)
        
        print(f"\n{'#':<5} {'Hash':<32} {'Display Name'}")
        print(f"{'─'*5} {'─'*32} {'─'*30}")
        
        for idx, hash_str in enumerate(sorted_blacklist, 1):
            # Try to get display name for this hash
            display_name = self.get_lxmf_display_name(hash_str)
            contact_name = self.get_contact_name_by_hash(hash_str)
            
            if contact_name:
                name_display = f"{contact_name} ({display_name})" if display_name else contact_name
            elif display_name:
                name_display = display_name
            else:
                name_display = "<unknown>"
            
            # Truncate if too long
            if len(name_display) > 30:
                name_display = name_display[:27] + "..."
            
            print(f"{idx:<5} {hash_str[:32]:<32} {name_display}")
        
        print(f"{'─'*width}")
        self._print_color(f"\n💡 Total blocked: {len(self.blacklist)}", Fore.YELLOW)
        print()

    def get_terminal_width(self, default=70, max_width=90):
        """Get terminal width with safe defaults for mobile"""
        try:
            import shutil
            width = shutil.get_terminal_size().columns
            # On very narrow screens (mobile), use smaller width
            if width < 60:
                return min(width - 2, 50)  # Leave margin, cap at 50
            return min(width, max_width)
        except:
            return default

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
                                is_new_peer = clean_hash not in self.client.announced_peers
                                
                                if is_new_peer:
                                    peer_index = self.client.next_peer_index
                                    self.client.next_peer_index += 1
                                    
                                    self.client.announced_peers[clean_hash] = {
                                        'display_name': display_name,
                                        'last_seen': time.time(),
                                        'index': peer_index
                                    }
                                else:
                                    self.client.announced_peers[clean_hash]['display_name'] = display_name
                                    self.client.announced_peers[clean_hash]['last_seen'] = time.time()
                            
                            self.client.cache_display_name(hash_str, display_name)
                            
                            # Show discovery if enabled AND it's truly new
                            if is_new_peer and self.client.show_announces:
                                # Check if already a contact
                                is_contact = self.client.get_contact_name_by_hash(clean_hash) != clean_hash
                                
                                # Use plain text - no ANSI codes in background threads
                                print(f"\n📡 New Announce: {display_name}")
                                print(f"🔗 {hash_str}")
                                
                                if not is_contact:
                                    # Get peer index for this new peer
                                    peer_idx = self.client.announced_peers[clean_hash]['index']
                                    print(f"💡 Quick save: 'ap {peer_idx}' | Send: 'sp {peer_idx} <msg>'")

                                if is_contact:
                                    # Get peer index for this new peer
                                    peer_idx = self.client.announced_peers[clean_hash]['index']
                                    print(f"💡 Quick Send: 'sp {peer_idx} <msg>'")

                
                except Exception:
                    pass
        
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
            
            # CHECK IF AUTO-ANNOUNCE IS ENABLED
            if not self.stop_event.is_set() and self.auto_announce_enabled:
                if hasattr(self.destination, 'announce'):
                    try:
                        self.destination.announce()  # type: ignore
                        timestamp = datetime.now().strftime('%H:%M:%S')
                        print(f"\n[Auto-announced at {timestamp}]")
                    except Exception as e:
                        print(f"\n[Auto-announce failed: {e}]")
    
    def load_config(self):
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.display_name = config.get('display_name', 'Anonymous')
                    self.announce_interval = config.get('announce_interval', 300)
                    self.auto_announce_enabled = config.get('auto_announce_enabled', True)  # ADD THIS
                    self.show_announces = config.get('show_announces', True)
                    # Load notification settings
                    self.notify_sound = config.get('notify_sound', True)
                    self.notify_bell = config.get('notify_bell', True)
                    self.notify_visual = config.get('notify_visual', True)
                    # Load stamp cost settings
                    self.stamp_cost_enabled = config.get('stamp_cost_enabled', False)
                    self.stamp_cost = config.get('stamp_cost', 0)
                    self.ignore_invalid_stamps = config.get('ignore_invalid_stamps', False)
                return
            except Exception as e:
                self._print_warning(f"Error loading config: {e}")
                
        # === FIRST TIME SETUP ===
        try:
            width = shutil.get_terminal_size().columns
        except:
            width = 60

        sep_width = min(width, 60)

        print(f"\n{'─'*sep_width}")
        self._print_color("FIRST TIME SETUP", Fore.CYAN + Style.BRIGHT)
        print(f"{'─'*sep_width}\n")

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
        
        print(f"\n{'─'*sep_width}")
        self._print_color("Setup complete! Initializing...", Fore.GREEN)
        print(f"{'─'*sep_width}\n")
        
        # Save configuration
        self.save_config()

    def save_config(self):
        """Save configuration to file"""
        try:
            config = {
                'display_name': self.display_name,
                'announce_interval': self.announce_interval,
                'auto_announce_enabled': self.auto_announce_enabled,  # ADD THIS
                'show_announces': self.show_announces,
                'notify_sound': self.notify_sound,
                'notify_bell': self.notify_bell,
                'notify_visual': self.notify_visual,
                'stamp_cost_enabled': self.stamp_cost_enabled,
                'stamp_cost': self.stamp_cost,
                'ignore_invalid_stamps': self.ignore_invalid_stamps
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
            source_hash_str = RNS.prettyhexrep(message.source_hash)
            
            if self.is_blacklisted(source_hash_str):
                print(f"\n[BLOCKED] Message from blacklisted address: {source_hash_str}")
                sender_display = self.get_lxmf_display_name(source_hash_str)
                if sender_display:
                    print(f"          Display name: {sender_display}")
                return
            
            # Validate stamp cost if enabled
            if self.stamp_cost_enabled and self.stamp_cost > 0:
                pass

            content = message.content
            if isinstance(content, bytes):
                content = content.decode('utf-8', errors='replace')
            
            title = message.title
            if isinstance(title, bytes):
                title = title.decode('utf-8', errors='replace')
            
            sender_display_name = self.get_lxmf_display_name(source_hash_str)
            
            msg_data = {
                'timestamp': message.timestamp,
                'source_hash': source_hash_str,
                'title': title,
                'content': content,
                'direction': 'inbound',
                'display_name': sender_display_name
            }
            
            if self.handle_plugin_message(message, msg_data):
                return
            
            with self.messages_lock:
                self.messages.append(msg_data)
                self.last_sender_hash = msg_data['source_hash']
                self.last_sender_name = self.get_contact_name_by_hash(msg_data['source_hash'])
            
            self.save_message(msg_data)
            sender_display = self.format_contact_display(msg_data['source_hash'], show_hash=True)
            
            # Check if sender is in contacts
            is_saved_contact = self.get_contact_name_by_hash(source_hash_str) != source_hash_str
            
            # Trigger notification
            self.notify_new_message()
            
            try:
                width = min(shutil.get_terminal_size().columns, 60)
            except:
                width = 60
            
            # SIMPLE PRINTS - NO COLOR CODES IN STRINGS
            print(f"\n{'─'*width}")
            timestamp = datetime.fromtimestamp(message.timestamp).strftime('%H:%M:%S')
            print(f"📨 [{timestamp}] NEW MESSAGE from: {self.format_contact_display_short(msg_data['source_hash'])}")
            print(f"{'─'*width}")
            if title:
                print(f"Title: {title}")
            if content:
                print(f"\n{content}")
            print(f"{'─'*width}")
            
            # SHOW APPROPRIATE TIP BASED ON CONTACT STATUS
            if is_saved_contact:
                print(f"💡 Type 'reply <message>' or 're <message>' to respond")
            else:
                # Not in contacts - show save command
                print(f"💡 Reply: 're <msg>' | Save contact: 'save' or 'savecontact'")
            
            print(f"{'─'*width}\n")
        
        except Exception as e:
            print(f"❌ Error processing message: {e}")


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
                announces_dict = getattr(RNS.Transport, 'announces', {})
                for destination_hash, announce_data in announces_dict.items():
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

    def edit_contact(self, identifier):
        """Edit an existing contact's name or hash"""
        # Find contact by name or index
        target_contact = None
        contact_name = None
        
        # Try as index first
        try:
            idx = int(identifier)
            for name, data in self.contacts.items():
                if data.get('index') == idx:
                    target_contact = data
                    contact_name = name
                    break
        except ValueError:
            # Not a number, try as name
            if identifier in self.contacts:
                target_contact = self.contacts[identifier]
                contact_name = identifier
        
        if not target_contact:
            self._print_error(f"Contact not found: {identifier}")
            print("Use 'contacts' to see the list")
            return
        
        current_hash = target_contact['hash']
        current_index = target_contact.get('index', '?')
        display_name = self.get_lxmf_display_name(current_hash)
        
        print(f"\n{'─'*60}")
        self._print_color(f"EDITING CONTACT: {contact_name}", Fore.CYAN + Style.BRIGHT)
        print(f"{'─'*60}")
        print(f"Current name: {contact_name}")
        print(f"Current hash: {current_hash}")
        if display_name:
            print(f"LXMF display name: {display_name}")
        print(f"Index: #{current_index}")
        print(f"{'─'*60}\n")
        
        print("What would you like to edit?")
        print("  [1] Change nickname")
        print("  [2] Change LXMF address (hash)")
        print("  [3] Both")
        print("  [c] Cancel")
        
        choice = input("\nSelect option: ").strip().lower()
        
        new_name = contact_name
        new_hash = current_hash
        
        if choice in ['1', '3']:
            # Edit name
            name_input = input(f"\nEnter new nickname [{contact_name}]: ").strip()
            if name_input:
                # Check if name already exists
                if name_input in self.contacts and name_input != contact_name:
                    self._print_error(f"Contact '{name_input}' already exists!")
                    return
                new_name = name_input
        
        if choice in ['2', '3']:
            # Edit hash
            hash_input = input(f"\nEnter new LXMF address [{current_hash}]: ").strip()
            if hash_input:
                # Validate hash
                clean_hash = hash_input.replace(":", "").replace(" ", "").replace("<", "").replace(">", "")
                if len(clean_hash) == 64:
                    try:
                        bytes.fromhex(clean_hash)
                        new_hash = clean_hash
                    except ValueError:
                        self._print_error("Invalid hash format!")
                        return
                else:
                    self._print_error("Hash must be 64 hex characters!")
                    return
        
        if choice == 'c':
            print("Cancelled")
            return
        
        if choice not in ['1', '2', '3']:
            self._print_error("Invalid option")
            return
        
        # Confirm changes
        print(f"\n{'─'*60}")
        print("CONFIRM CHANGES:")
        if new_name != contact_name:
            print(f"  Name: {contact_name} → {new_name}")
        if new_hash != current_hash:
            print(f"  Hash: {current_hash[:16]}... → {new_hash[:16]}...")
        print(f"{'─'*60}")
        
        confirm = input("\nSave changes? [y/N]: ").strip().lower()
        if confirm == 'y':
            # Remove old contact
            del self.contacts[contact_name]
            
            # Add updated contact (keep same index)
            self.contacts[new_name] = {
                'hash': new_hash,
                'index': current_index
            }
            
            self.save_contacts()
            self._print_success(f"Contact updated: {new_name}")
            
            # Show new display name if hash changed
            if new_hash != current_hash:
                new_display = self.get_lxmf_display_name(new_hash)
                if new_display:
                    print(f"  LXMF display name: {new_display}")
        else:
            print("Cancelled")

    def save_contact_from_hash(self, hash_str, suggested_name=None):
        """Quick save a contact from hash with optional suggested name"""
        clean_hash = hash_str.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
        
        # Check if already in contacts
        for name, data in self.contacts.items():
            if data['hash'].lower() == clean_hash:
                self._print_warning(f"Already in contacts as: {name}")
                return
        
        # Get display name
        display_name = self.get_lxmf_display_name(clean_hash)
        
        # Suggest name
        if suggested_name:
            default_name = suggested_name
        elif display_name:
            default_name = display_name
        else:
            default_name = clean_hash[:8]
        
        print(f"\n{'─'*60}")
        self._print_color("SAVE NEW CONTACT", Fore.GREEN + Style.BRIGHT)
        print(f"{'─'*60}")
        print(f"LXMF Address: {clean_hash}")
        if display_name:
            print(f"Display Name: {display_name}")
        print(f"{'─'*60}\n")
        
        name = input(f"Enter nickname [{default_name}]: ").strip()
        if not name:
            name = default_name
        
        # Check if name exists
        if name in self.contacts:
            self._print_error(f"Contact '{name}' already exists!")
            return
        
        self.add_contact(name, clean_hash)
           
    def list_contacts(self):
        """List all contacts"""
        if not self.contacts:
            print("\nNo contacts saved\n")
            return
        
        import shutil
        try:
            width = shutil.get_terminal_size().columns
        except:
            width = 80
        
        sorted_contacts = sorted(self.contacts.items(), key=lambda x: x[1].get('index', 999999))
        
        sep_width = min(width, 90)
        print(f"\n{'─'*sep_width}")
        self._print_color("CONTACTS", Fore.CYAN + Style.BRIGHT)
        print(f"{'─'*sep_width}")
        
        if width < 70:
            # Mobile: Vertical layout
            for name, data in sorted_contacts:
                idx = data.get('index', '?')
                hash_str = data['hash']
                display_name = self.get_lxmf_display_name(hash_str)
                
                print(f"\n[{idx}] {Fore.CYAN}{name} - {display_name}{Style.RESET_ALL}")
                #if display_name:
                #    print(f"    {display_name}")
                print(f"      {hash_str}")
        else:
            # Desktop: Clean table with separators
            print(f"\n{'#':<5} {'Name':<20} {'Display Name':<30} {'Hash'}")
            print(f"{'─'*5} {'─'*20} {'─'*30} {'─'*32}")
            
            for name, data in sorted_contacts:
                idx = data.get('index', '?')
                hash_str = data['hash']
                display_name = self.get_lxmf_display_name(hash_str)
                
                name_shown = name[:18] + ".." if len(name) > 20 else name
                
                if display_name:
                    display_shown = display_name[:28] + ".." if len(display_name) > 30 else display_name
                    print(f"{idx:<5} {name_shown:<20} {display_shown:<30} {hash_str}")
                else:
                    print(f"{idx:<5} {name_shown:<20} {'<unknown>':<30} {hash_str}")
        
        print(f"{'─'*sep_width}")
        self._print_color("\n💡 Send: 's <#> <msg>'", Fore.YELLOW)
        print()

    def list_peers(self):
        """List all announced LXMF peers"""
        with self.peers_lock:
            peers_copy = dict(self.announced_peers)
        
        if not peers_copy:
            print("\nNo peers announced yet\n")
            return
        
        import shutil
        try:
            width = shutil.get_terminal_size().columns
        except:
            width = 80
        
        sorted_peers = sorted(peers_copy.items(), key=lambda x: x[1]['index'])
        
        sep_width = min(width, 90)
        print(f"\n{'─'*sep_width}")
        self._print_color("ANNOUNCED PEERS", Fore.CYAN + Style.BRIGHT)
        print(f"{'─'*sep_width}")
        
        if width < 70:
            # Mobile: Vertical layout
            for hash_str, peer_data in sorted_peers:
                peer_index = peer_data['index']
                display_name = peer_data['display_name']
                last_seen = peer_data['last_seen']
                
                time_diff = time.time() - last_seen
                if time_diff < 60:
                    time_str = "now"
                elif time_diff < 3600:
                    time_str = f"{int(time_diff/60)}m ago"
                elif time_diff < 86400:
                    time_str = f"{int(time_diff/3600)}h ago"
                else:
                    time_str = f"{int(time_diff/86400)}d ago"
                
                is_contact = any(data['hash'].lower() == hash_str for data in self.contacts.values())
                marker = "★ " if is_contact else ""
                
                print(f"\n{marker}[{peer_index}] {Fore.CYAN}{display_name}{Style.RESET_ALL}  •  {time_str}")
                #print(f"    {time_str}")
        else:
            # Desktop: Clean table with separators
            print(f"\n{'#':<5} {'Display Name':<35} {'Hash':<32} {'Last Seen'}")
            print(f"{'─'*5} {'─'*35} {'─'*32} {'─'*15}")
            
            for hash_str, peer_data in sorted_peers:
                peer_index = peer_data['index']
                display_name = peer_data['display_name']
                last_seen = peer_data['last_seen']
                
                time_diff = time.time() - last_seen
                if time_diff < 60:
                    time_str = "just now"
                elif time_diff < 3600:
                    time_str = f"{int(time_diff/60)}m ago"
                elif time_diff < 86400:
                    time_str = f"{int(time_diff/3600)}h ago"
                else:
                    time_str = f"{int(time_diff/86400)}d ago"
                
                is_contact = any(data['hash'].lower() == hash_str for data in self.contacts.values())
                marker = "★" if is_contact else " "
                
                display_shown = display_name[:33] + ".." if len(display_name) > 35 else display_name
                
                print(f"{marker}{peer_index:<4} {display_shown:<35} {hash_str:<32} {time_str}")
        
        print(f"{'─'*sep_width}")
        self._print_color("\n💡 sp <#> <msg> | ap <#> [name]", Fore.YELLOW)
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
                title=title or "",
                desired_method=LXMF.LXMessage.DIRECT
            )
            # Add custom attribute for tracking
            setattr(message, 'send_timestamp', send_start_time)
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

            # Build recipient display string - SHORT FORMAT (no hash)
            dest_hash = msg_data['destination_hash']
            recipient_display = self.format_contact_display_short(dest_hash)

            self._print_color(f"📤 Sending to: {recipient_display}...", Fore.CYAN)
            # DO NOT PRINT ANYTHING HERE - NO NEWLINE, NO PROMPT!

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
                # DO NOT PRINT PROMPT HERE EITHER!

            threading.Thread(target=monitor_progress, daemon=True).start()

            # Send message
            self.router.handle_outbound(message)
            # DO NOT PRINT ANYTHING AFTER THIS!

            return True

        except ValueError:
            self._print_error("Invalid destination hash or contact index")
            return False
        except Exception as e:
            self._print_error(f"Error sending message: {e}")
            traceback.print_exc()
            return False

    def on_delivery(self, message):
        """Callback for successful delivery"""
        dest_hash = RNS.prettyhexrep(message.destination_hash)
        recipient_str = self.format_contact_display_short(dest_hash)

        if message.hash in self.pending_messages:
            del self.pending_messages[message.hash]

        if hasattr(message, 'send_timestamp'):
            delivery_time = time.time() - message.send_timestamp
            if delivery_time < 60:
                time_str = f"{delivery_time:.1f}s"
            else:
                minutes = int(delivery_time // 60)
                seconds = int(delivery_time % 60)
                time_str = f"{minutes}m {seconds}s"
        else:
            time_str = "?"

        print()
        print(f"✅ Delivered to {recipient_str} ({time_str})")


    def on_failed(self, message):
        """Callback for failed delivery"""
        dest_hash = RNS.prettyhexrep(message.destination_hash)
        recipient_str = self.format_contact_display_short(dest_hash)

        if message.hash in self.pending_messages:
            del self.pending_messages[message.hash]

        if hasattr(message, 'send_timestamp'):
            fail_time = time.time() - message.send_timestamp
            if fail_time < 60:
                time_str = f"{fail_time:.1f}s"
            else:
                minutes = int(fail_time // 60)
                seconds = int(fail_time % 60)
                time_str = f"{minutes}m {seconds}s"
        else:
            time_str = "?"

        print()
        print(f"❌ Failed to {recipient_str} (after {time_str})")


    def show_stats(self):
        """Show messaging statistics"""
        with self.messages_lock:
            messages_copy = self.messages.copy()
        
        if not messages_copy:
            print("\nNo messages yet\n")
            return
        
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 80)
            is_mobile = width < 70
        except:
            width = 80
            is_mobile = False
        
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
        print(f"\n{'─'*width}")
        self._print_color("MESSAGING STATISTICS", Fore.CYAN + Style.BRIGHT)
        print(f"{'─'*width}")
        print(f"\n{Fore.GREEN}Overall Stats:{Style.RESET_ALL}")
        print(f"  Total Messages: {total_messages}")
        print(f"  Sent: {total_sent}")
        print(f"  Received: {total_received}")
        print(f"  Unique Contacts: {len(user_stats)}")
        
        # Display per-user stats
        print(f"\n{Fore.CYAN}Per-User Statistics:{Style.RESET_ALL}")
        print(f"{'─'*width}")
        
        # Sort by total messages descending
        sorted_users = sorted(user_stats.items(), key=lambda x: x[1]['total'], reverse=True)
        
        if is_mobile:
            # Mobile layout - vertical
            for hash_str, stats in sorted_users:
                contact_display = self.format_contact_display_short(hash_str)
                print(f"\n{contact_display}")
                print(f"  ↑{stats['sent']} ↓{stats['received']} (Total: {stats['total']})")
        else:
            # Desktop layout - table
            print(f"{'Contact':<35} {'Sent':<8} {'Received':<10} {'Total':<10}")
            print(f"{'─'*35} {'─'*8} {'─'*10} {'─'*10}")
            
            for hash_str, stats in sorted_users:
                contact_display = self.format_contact_display_short(hash_str)
                
                # Truncate if too long
                if len(contact_display) > 33:
                    contact_display = contact_display[:30] + "..."
                
                print(f"{contact_display:<35} {stats['sent']:<8} {stats['received']:<10} {stats['total']:<10}")
        
        print(f"{'─'*width}\n")

    def show_status(self):
        """Show current status and connection info"""
        try:
            width = min(shutil.get_terminal_size().columns, 80)
        except:
            width = 80
        
        print(f"\n{'─'*width}")
        self._print_color("SYSTEM STATUS", Fore.CYAN + Style.BRIGHT)
        print(f"{'─'*width}")
        
        # Identity info
        print(f"\n{Fore.GREEN}Identity:{Style.RESET_ALL}")
        print(f"  Display Name: {self.display_name}")
        if hasattr(self.destination, 'hash'):
            print(f"  LXMF Address: {RNS.prettyhexrep(self.destination.hash)}")  # type: ignore
        
        # Network info
        print(f"\n{Fore.CYAN}Network:{Style.RESET_ALL}")
        if self.auto_announce_enabled:
            print(f"  Auto-announce: ENABLED (every {self.announce_interval}s)")
        else:
            print(f"  Auto-announce: DISABLED")
        print(f"  Discovery alerts: {'ON' if self.show_announces else 'OFF'}")

        # Add thread status
        if hasattr(self, 'announce_thread'):
            thread_alive = self.announce_thread.is_alive()
            print(f"  Announce thread: {'RUNNING' if thread_alive else 'STOPPED'}")
                    
        # Security settings
        print(f"\n{Fore.RED}Security:{Style.RESET_ALL}")
        if self.stamp_cost_enabled and self.stamp_cost > 0:
            print(f"  Stamp Cost: {Fore.GREEN}ENABLED{Style.RESET_ALL}")
            print(f"  Required Proof: {Fore.YELLOW}{self.stamp_cost} bits{Style.RESET_ALL}")
            print(f"  Ignore Invalid: {Fore.GREEN}{'YES' if self.ignore_invalid_stamps else 'NO'}{Style.RESET_ALL}")
        else:
            print(f"  Stamp Cost: {Fore.RED}DISABLED{Style.RESET_ALL}")

        if self.blacklist:
            print(f"  Blacklist: {Fore.YELLOW}{len(self.blacklist)} blocked{Style.RESET_ALL}")
        else:
            print(f"  Blacklist: {Fore.GREEN}Empty{Style.RESET_ALL}")
        
        # Notification settings
        print(f"\n{Fore.MAGENTA}Notifications:{Style.RESET_ALL}")
        print(f"  Sound: {'ON' if self.notify_sound else 'OFF'}")
        print(f"  Terminal Bell: {'ON' if self.notify_bell else 'OFF'}")
        print(f"  Visual Flash: {'ON' if self.notify_visual else 'OFF'}")
        
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
        
        # Plugins
        if self.plugins:
            plugin_count = len(self.plugins)
            enabled_count = sum(1 for name in self.plugins.keys() if self.plugins_enabled.get(name, True))
            print(f"  Plugins: {enabled_count}/{plugin_count} enabled")
        
        # System info
        print(f"\n{Fore.WHITE}System:{Style.RESET_ALL}")
        uptime = time.time() - self.start_time
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        print(f"  Uptime: {hours}h {minutes}m")
        if self.suppressed_errors > 0:
            print(f"  Suppressed errors: {self.suppressed_errors}")
        
        print(f"{'─'*width}\n")

    def show_messages(self, limit=10, filter_hash=None):
        """Show recent messages, optionally filtered by user hash"""
        with self.messages_lock:
            messages_copy = self.messages.copy()
        
        if not messages_copy:
            print("\nNo messages yet\n")
            return
        
        # Get responsive width
        try:
            width = min(shutil.get_terminal_size().columns, 80)
        except:
            width = 80
        
        # Filter by hash if provided
        if filter_hash:
            clean_filter = filter_hash.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
            filtered_messages = []
            
            for msg in messages_copy:
                msg_hash = ""
                if msg['direction'] == 'outbound':
                    msg_hash = msg.get('destination_hash', '')
                else:
                    msg_hash = msg.get('source_hash', '')
                
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
            print(f"\n{'─'*width}")
            # Truncate contact name if too long for header
            if len(contact_display) > width - 10:
                contact_display = contact_display[:width-13] + "..."
            self._print_color(f"CHAT: {contact_display.upper()}", Fore.CYAN + Style.BRIGHT)
            print(f"{'─'*width}")
        else:
            print(f"\n{'─'*width}")
            self._print_color(f"RECENT MESSAGES ({min(limit, len(messages_copy))})", Fore.CYAN + Style.BRIGHT)
            print(f"{'─'*width}")
        
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
                    print(f"{'─'*width}")
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
        
        print(f"\n{'─'*width}")
        
        if filter_hash:
            self.last_sender_hash = filter_hash
            self.last_sender_name = self.get_contact_name_by_hash(filter_hash)
            
            self._print_color(f"\n💡 Reply: 're <msg>'", Fore.GREEN)
        else:
            self._print_color("💡 Tip: 'm list' or 'm user <#>'", Fore.YELLOW)
        
        print()

    def show_message_list_with_users(self):
        """Show a list of users you've messaged with, indexed for selection"""
        with self.messages_lock:
            messages_copy = self.messages.copy()
        
        if not messages_copy:
            print("\nNo messages yet\n")
            return
        
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 90)
            is_mobile = width < 70
        except:
            width = 90
            is_mobile = False
        
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
                    'display_hash': hash_key
                }
            
            if msg['direction'] == 'outbound':
                user_data[clean_hash]['sent'] += 1
            else:
                user_data[clean_hash]['received'] += 1
            
            if msg['timestamp'] > user_data[clean_hash]['last_message_time']:
                user_data[clean_hash]['last_message_time'] = msg['timestamp']
        
        # Sort by fixed index
        sorted_users = sorted(user_data.items(), key=lambda x: x[1]['index'])
        
        print(f"\n{'─'*width}")
        self._print_color("MESSAGE CONVERSATIONS", Fore.CYAN + Style.BRIGHT)
        print(f"{'─'*width}")
        
        if is_mobile:
            # Mobile layout - vertical list
            for clean_hash, data in sorted_users:
                conv_index = data['index']
                hash_str = data['display_hash']
                contact_display = self.format_contact_display_short(hash_str)
                
                time_diff = time.time() - data['last_message_time']
                if time_diff < 60:
                    time_str = "now"
                elif time_diff < 3600:
                    time_str = f"{int(time_diff/60)}m ago"
                elif time_diff < 86400:
                    time_str = f"{int(time_diff/3600)}h ago"
                else:
                    time_str = f"{int(time_diff/86400)}d ago"
                
                print(f"\n[{conv_index}] {Fore.CYAN}{contact_display}{Style.RESET_ALL}")
                print(f"    ↑{data['sent']} ↓{data['received']} • {time_str}")
        else:
            # Desktop layout - table
            print(f"\n{'#':<5} {'Contact':<35} {'Sent':<6} {'Recv':<6} {'Last':<12}")
            print(f"{'─'*5} {'─'*35} {'─'*6} {'─'*6} {'─'*12}")
            
            for clean_hash, data in sorted_users:
                conv_index = data['index']
                hash_str = data['display_hash']
                contact_display = self.format_contact_display_short(hash_str)
                
                # Truncate contact name if too long
                if len(contact_display) > 33:
                    contact_display = contact_display[:30] + "..."
                
                time_diff = time.time() - data['last_message_time']
                if time_diff < 60:
                    time_str = "just now"
                elif time_diff < 3600:
                    time_str = f"{int(time_diff/60)}m ago"
                elif time_diff < 86400:
                    time_str = f"{int(time_diff/3600)}h ago"
                else:
                    time_str = f"{int(time_diff/86400)}d ago"
                
                print(f"{conv_index:<5} {contact_display:<35} {data['sent']:<6} {data['received']:<6} {time_str:<12}")
        
        print(f"{'─'*width}")
        self._print_color("\n💡 Commands:", Fore.YELLOW)
        print(f"  m user <#> - View conversation")
        print(f"  m [count]  - Recent messages")
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

    def _show_messaging_help(self):
        """Show messaging help"""
        self._print_color("Messaging commands: send, reply, messages", Fore.CYAN)

    def _show_contacts_help(self):
        """Show contacts help"""
        self._print_color("Contact commands: contacts, add, remove, peers", Fore.CYAN)

    def _show_settings_help(self):
        """Show settings help"""
        self._print_color("Settings commands: settings, name, interval", Fore.CYAN)

    def _show_system_help(self):
        """Show system help"""
        self._print_color("System commands: status, restart, clear, help, quit", Fore.CYAN)

    def _show_main_help(self):
        """Show main help menu with categories"""
        
        try:
            width = shutil.get_terminal_size().columns
            is_mobile = width < 70
        except:
            width = 80
            is_mobile = False
        
        if COLOR_ENABLED:
            if is_mobile:
                # === MOBILE LAYOUT ===
                print(f"\n{Fore.WHITE}{'─'*width}")
                print(f"LXMF CLIENT COMMANDS".center(width))
                print(f"{'─'*width}{Style.RESET_ALL}\n")
                
                # Messaging
                self._print_color("📨 MESSAGING", Fore.CYAN + Style.BRIGHT)
                print(f"{'─'*width}")
                commands = [
                    ("send <#> <msg>", "s"),
                    ("reply <msg>", "re"),
                    ("messages [n]", "m"),
                    ("messages list", ""),
                    ("messages user <#>", ""),
                ]
                for cmd, alias in commands:
                    if alias:
                        print(f"{Fore.CYAN}{cmd}{Style.RESET_ALL} {Fore.YELLOW}({alias}){Style.RESET_ALL}")
                    else:
                        print(f"{Fore.CYAN}{cmd}{Style.RESET_ALL}")
                
                # Contacts & Peers
                print(f"\n{Fore.GREEN}👥 CONTACTS & PEERS{Style.RESET_ALL}")
                print(f"{'─'*width}")
                commands = [
                    ("contacts", "c"),
                    ("add <name> <hash>", "a"),
                    ("edit <name/#>", "e"),
                    ("remove <name>", "rm"),
                    ("savecontact [hash]", "save"),
                    ("peers", "p"),
                    ("sendpeer <#> <msg>", "sp"),
                    ("addpeer <#> [name]", "ap"),
                ]
                for cmd, alias in commands:
                    if alias:
                        print(f"{Fore.CYAN}{cmd}{Style.RESET_ALL} {Fore.YELLOW}({alias}){Style.RESET_ALL}")
                    else:
                        print(f"{Fore.CYAN}{cmd}{Style.RESET_ALL}")
                
                # Info & Stats
                print(f"\n{Fore.MAGENTA}📊 INFO & STATS{Style.RESET_ALL}")
                print(f"{'─'*width}")
                commands = [
                    ("stats", "st"),
                    ("status", ""),
                ]
                for cmd, alias in commands:
                    if alias:
                        print(f"{Fore.CYAN}{cmd}{Style.RESET_ALL} {Fore.YELLOW}({alias}){Style.RESET_ALL}")
                    else:
                        print(f"{Fore.CYAN}{cmd}{Style.RESET_ALL}")

                # Network
                print(f"\n{Fore.BLUE}🌐 NETWORK{Style.RESET_ALL}")
                print(f"{'─'*width}")
                commands = [
                    ("address", "addr"),
                    ("announce", "ann"),
                ]
                for cmd, alias in commands:
                    if alias:
                        print(f"{Fore.CYAN}{cmd}{Style.RESET_ALL} {Fore.YELLOW}({alias}){Style.RESET_ALL}")
                    else:
                        print(f"{Fore.CYAN}{cmd}{Style.RESET_ALL}")
                
                # Settings
                print(f"\n{Fore.YELLOW}⚙️  SETTINGS{Style.RESET_ALL}")
                print(f"{'─'*width}")
                commands = [
                    ("settings", "set"),
                    ("name <name>", "n"),
                    ("interval <sec>", "i"),
                ]
                for cmd, alias in commands:
                    if alias:
                        print(f"{Fore.CYAN}{cmd}{Style.RESET_ALL} {Fore.YELLOW}({alias}){Style.RESET_ALL}")
                    else:
                        print(f"{Fore.CYAN}{cmd}{Style.RESET_ALL}")

                # Mobile security 
                print(f"\n{Fore.RED}🛡️  SECURITY{Style.RESET_ALL}")
                print(f"{'─'*width}")
                commands = [
                    ("blacklist [list]", "bl"),
                    ("block <#/name>", ""),
                    ("unblock <#/name>", ""),
                ]
                for cmd, alias in commands:
                    if alias:
                        print(f"{Fore.CYAN}{cmd}{Style.RESET_ALL} {Fore.YELLOW}({alias}){Style.RESET_ALL}")
                    else:
                        print(f"{Fore.CYAN}{cmd}{Style.RESET_ALL}")
                                
                # System
                print(f"\n{Fore.RED}🖥️  SYSTEM{Style.RESET_ALL}")
                print(f"{'─'*width}")
                commands = [
                    ("plugin [list]", ""),
                    ("clear", "cls"),
                    ("restart", "r"),
                    ("help", "h"),
                    ("quit", "q"),
                ]
                for cmd, alias in commands:
                    if alias:
                        print(f"{Fore.CYAN}{cmd}{Style.RESET_ALL} {Fore.YELLOW}({alias}){Style.RESET_ALL}")
                    else:
                        print(f"{Fore.CYAN}{cmd}{Style.RESET_ALL}")
            
            else:
                # === DESKTOP LAYOUT (clean separator lines) ===
                print(f"\n{Fore.WHITE}{'─'*70}")
                print(f"LXMF CLIENT COMMANDS".center(70))
                print(f"{'─'*70}{Style.RESET_ALL}\n")
                
                # Messaging commands
                self._print_color("📨 MESSAGING", Fore.CYAN + Style.BRIGHT)
                print(f"{'─'*70}")
                commands = [
                    ("send <#> <msg>", "s", "Send message"),
                    ("reply <msg>", "re", "Reply to last"),
                    ("messages [n]", "m", "Recent messages"),
                    ("messages list", "", "All conversations"),
                    ("messages user <#>", "", "View conversation"),
                ]
                for long_cmd, short_cmd, description in commands:
                    if short_cmd:
                        print(f"{Fore.CYAN}{long_cmd:<20}{Style.RESET_ALL} {Fore.YELLOW}({short_cmd:<4}){Style.RESET_ALL} {description}")
                    else:
                        print(f"{Fore.CYAN}{long_cmd:<20}{Style.RESET_ALL}       {description}")
                
                # Contacts & Peers
                print(f"\n{Fore.GREEN}👥 CONTACTS & PEERS{Style.RESET_ALL}")
                print(f"{'─'*70}")
                commands = [
                    ("contacts", "c", "List contacts"),
                    ("add <name> <hash>", "a", "Add contact"),
                    ("edit <name/#>", "e", "Edit contact"),
                    ("remove <name>", "rm", "Remove contact"),
                    ("savecontact [hash]", "save", "Quick save contact"),
                    ("peers", "p", "List peers"),
                    ("sendpeer <#> <msg>", "sp", "Send to peer"),
                    ("addpeer <#> [name]", "ap", "Add to contacts"),
                ]
                for long_cmd, short_cmd, description in commands:
                    if short_cmd:
                        print(f"{Fore.CYAN}{long_cmd:<20}{Style.RESET_ALL} {Fore.YELLOW}({short_cmd:<4}){Style.RESET_ALL} {description}")
                    else:
                        print(f"{Fore.CYAN}{long_cmd:<20}{Style.RESET_ALL}       {description}")
                
                # Info & Stats
                print(f"\n{Fore.MAGENTA}📊 INFO & STATS{Style.RESET_ALL}")
                print(f"{'─'*70}")
                commands = [
                    ("stats", "st", "Messaging stats"),
                    ("status", "", "System status"),
                ]
                for long_cmd, short_cmd, description in commands:
                    if short_cmd:
                        print(f"{Fore.CYAN}{long_cmd:<20}{Style.RESET_ALL} {Fore.YELLOW}({short_cmd:<4}){Style.RESET_ALL} {description}")
                    else:
                        print(f"{Fore.CYAN}{long_cmd:<20}{Style.RESET_ALL}       {description}")

                # Network 
                print(f"\n{Fore.BLUE}🌐 NETWORK{Style.RESET_ALL}")
                print(f"{'─'*70}")
                commands = [
                    ("address", "addr", "Your LXMF address info"),
                    ("announce", "ann", "Announce manually now!"),
                ]
                for long_cmd, short_cmd, description in commands:
                    if short_cmd:
                        print(f"{Fore.CYAN}{long_cmd:<20}{Style.RESET_ALL} {Fore.YELLOW}({short_cmd:<4}){Style.RESET_ALL} {description}")
                    else:
                        print(f"{Fore.CYAN}{long_cmd:<20}{Style.RESET_ALL}       {description}")
                
                # Settings
                print(f"\n{Fore.YELLOW}⚙️  SETTINGS{Style.RESET_ALL}")
                print(f"{'─'*70}")
                commands = [
                    ("settings", "set", "Settings menu"),
                    ("name <name>", "n", "Change name"),
                    ("interval <sec>", "i", "Announce interval"),
                ]
                for long_cmd, short_cmd, description in commands:
                    if short_cmd:
                        print(f"{Fore.CYAN}{long_cmd:<20}{Style.RESET_ALL} {Fore.YELLOW}({short_cmd:<4}){Style.RESET_ALL} {description}")
                    else:
                        print(f"{Fore.CYAN}{long_cmd:<20}{Style.RESET_ALL}       {description}")

                # Security section in help menu (desktop version)
                print(f"\n{Fore.RED}🛡️  SECURITY{Style.RESET_ALL}")
                print(f"{'─'*70}")
                commands = [
                    ("blacklist [list]", "bl", "Manage blacklist"),
                    ("block <#/name>", "", "Block contact"),
                    ("unblock <#/name>", "", "Unblock contact"),
                ]
                for long_cmd, short_cmd, description in commands:
                    if short_cmd:
                        print(f"{Fore.CYAN}{long_cmd:<20}{Style.RESET_ALL} {Fore.YELLOW}({short_cmd:<4}){Style.RESET_ALL} {description}")
                    else:
                        print(f"{Fore.CYAN}{long_cmd:<20}{Style.RESET_ALL}       {description}")
                                
                # System
                print(f"\n{Fore.RED}🖥️  SYSTEM{Style.RESET_ALL}")
                print(f"{'─'*70}")
                commands = [
                    ("plugin [list]", "", "Manage plugins"),
                    ("clear", "cls", "Clear screen"),
                    ("restart", "r", "Restart client"),
                    ("help", "h", "Show help"),
                    ("quit", "q", "Exit"),
                ]
                for long_cmd, short_cmd, description in commands:
                    if short_cmd:
                        print(f"{Fore.CYAN}{long_cmd:<20}{Style.RESET_ALL} {Fore.YELLOW}({short_cmd:<4}){Style.RESET_ALL} {description}")
                    else:
                        print(f"{Fore.CYAN}{long_cmd:<20}{Style.RESET_ALL}       {description}")
                
                print(f"\n{Fore.YELLOW}💡 Type 'settings' for options{Style.RESET_ALL}")
                print(f"{'─'*70}\n")
        
        else:
            # No color fallback
            print("\nLXMF CLI - Commands available")
            print("Type 'help' for full list\n")

    def show_settings_menu(self):
        """Show interactive settings menu"""
        
        while True:
            # Get responsive width
            try:
                width = min(shutil.get_terminal_size().columns, 70)
            except:
                width = 70
            
            print(f"\n{'─'*width}")
            self._print_color("SETTINGS MENU", Fore.YELLOW + Style.BRIGHT)
            print(f"{'─'*width}")
            
            print(f"\n{Fore.CYAN}General Settings:{Style.RESET_ALL}")
            print(f"  [1] Display Name: {Fore.GREEN}{self.display_name}{Style.RESET_ALL}")
            print(f"  [2] Auto-Announce: {Fore.GREEN}{'ON' if self.auto_announce_enabled else 'OFF'}{Style.RESET_ALL}")  # ADD THIS
            print(f"  [3] Announce Interval: {Fore.GREEN}{self.announce_interval}s{Style.RESET_ALL}")
            print(f"  [4] Discovery Alerts: {Fore.GREEN}{'ON' if self.show_announces else 'OFF'}{Style.RESET_ALL}")
            
            print(f"\n{Fore.MAGENTA}Notification Settings:{Style.RESET_ALL}")
            print(f"  [5] Sound (beeps/melody): {Fore.GREEN}{'ON' if self.notify_sound else 'OFF'}{Style.RESET_ALL}")
            print(f"  [6] Terminal Bell: {Fore.GREEN}{'ON' if self.notify_bell else 'OFF'}{Style.RESET_ALL}")
            print(f"  [7] Visual Flash: {Fore.GREEN}{'ON' if self.notify_visual else 'OFF'}{Style.RESET_ALL}")
            
            print(f"\n{Fore.RED}Security Settings:{Style.RESET_ALL}")
            print(f"  [8] Stamp Cost: {Fore.GREEN}{'ON' if self.stamp_cost_enabled else 'OFF'}{Style.RESET_ALL}")
            if self.stamp_cost_enabled:
                print(f"      Amount: {Fore.YELLOW}{self.stamp_cost} bits{Style.RESET_ALL}")
            print(f"  [9] Ignore Invalid Stamps: {Fore.GREEN}{'ON' if self.ignore_invalid_stamps else 'OFF'}{Style.RESET_ALL}")
            
            print(f"\n{Fore.YELLOW}Options:{Style.RESET_ALL}")
            print("  [1-9] - Change setting")
            print("  [t]   - Test notification")
            print("  [b]   - Back to main menu")
            print("  [s]   - Save and exit")
            
            print(f"{'─'*width}")
            
            choice = input("\nSelect option: ").strip().lower()
                                    
            if choice == '1':
                new_name = input(f"\nEnter new display name [{self.display_name}]: ").strip()
                if new_name:
                    self.display_name = new_name
                    if hasattr(self.destination, 'display_name'):
                        setattr(self.destination, 'display_name', self.display_name)  # type: ignore
                    self.save_config()
                    if hasattr(self.destination, 'announce'):
                        self.destination.announce()  # type: ignore
                    self._print_success(f"Display name changed to: {self.display_name}")
                    self._print_success("Announced to network")
                else:
                    print("Cancelled")
            
            elif choice == '2':
                # Toggle auto-announce
                self.auto_announce_enabled = not self.auto_announce_enabled
                self.save_config()
                
                # Restart announce thread to apply changes
                if self.auto_announce_enabled:
                    self.stop_event.set()
                    time.sleep(0.2)
                    self.stop_event.clear()
                    
                    # Restart the thread if needed
                    if not self.announce_thread.is_alive():
                        self.announce_thread = threading.Thread(target=self.announce_loop, daemon=True)
                        self.announce_thread.start()
                        self._print_success("Auto-announce enabled and thread restarted")
                    else:
                        self._print_success("Auto-announce enabled")
                else:
                    self._print_success("Auto-announce disabled")
                    print("  You can still announce manually using 'announce' command")
            
            elif choice == '3':
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
                        
                        # Restart announce thread properly
                        self.stop_event.set()  # Signal thread to stop
                        if hasattr(self, 'announce_thread'):
                            self.announce_thread.join(timeout=2)  # Wait for it to stop
                        
                        self.stop_event.clear()  # Clear the stop signal
                        
                        # Start new thread with new interval
                        self.announce_thread = threading.Thread(target=self.announce_loop, daemon=True)
                        self.announce_thread.start()
                        
                        self._print_success(f"Announce interval changed to: {self.announce_interval}s")
                        self._print_success("Announce thread restarted")
                    except ValueError:
                        self._print_error("Invalid number")
                else:
                    print("Cancelled")
            
            elif choice == '4':
                # Toggle discovery alerts
                self.show_announces = not self.show_announces
                self.save_config()
                status = "enabled" if self.show_announces else "disabled"
                self._print_success(f"Discovery alerts {status}")
            
            elif choice == '5':
                # Toggle sound notifications
                self.notify_sound = not self.notify_sound
                self.save_config()
                status = "enabled" if self.notify_sound else "disabled"
                self._print_success(f"Sound notifications {status}")
            
            elif choice == '6':
                # Toggle terminal bell
                self.notify_bell = not self.notify_bell
                self.save_config()
                status = "enabled" if self.notify_bell else "disabled"
                self._print_success(f"Terminal bell {status}")
            
            elif choice == '7':
                # Toggle visual flash
                self.notify_visual = not self.notify_visual
                self.save_config()
                status = "enabled" if self.notify_visual else "disabled"
                self._print_success(f"Visual flash {status}")

            elif choice == '8':
                # Toggle stamp cost (existing code stays the same)
                if not self.stamp_cost_enabled:
                    # ... existing stamp cost enable code ...
                    pass
                else:
                    # ... existing stamp cost disable code ...
                    pass
            
            elif choice == '9':
                # Toggle ignore invalid stamps
                self.ignore_invalid_stamps = not self.ignore_invalid_stamps
                self.save_config()
                status = "enabled" if self.ignore_invalid_stamps else "disabled"
                self._print_success(f"Ignore invalid stamps {status}")
                if self.ignore_invalid_stamps:
                    print("  Messages with insufficient/invalid stamps will be rejected")
                else:
                    print("  Messages with insufficient/invalid stamps will be accepted")
            
            elif choice == 't':
                # Test notification
                print("\nTesting notification...")
                self.notify_new_message()
                time.sleep(1)
                self._print_success("Test complete!")
            
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
        """Visual and audio notification for new message - respects user settings"""
        
        # === SOUND NOTIFICATION ===
        if self.notify_sound or self.notify_bell:
            system = platform.system()
            is_termux = os.path.exists('/data/data/com.termux')
            
            # Check for custom sound file
            sound_file = None
            sound_dir = os.path.join(self.storage_path, "sounds")
            
            if os.path.exists(sound_dir):
                # Look for notification sound files (in order of preference)
                for filename in ['notification.wav', 'notification.mp3', 'notification.ogg', 'message.wav', 'beep.wav']:
                    filepath = os.path.join(sound_dir, filename)
                    if os.path.exists(filepath):
                        sound_file = filepath
                        break
            
            try:
                if is_termux:
                    # === TERMUX/ANDROID ===
                    if self.notify_sound:
                        try:
                            # Try to play custom sound first
                            if sound_file:
                                os.system(f'termux-media-player play "{sound_file}" >/dev/null 2>&1 &')
                                time.sleep(0.5)
                            else:
                                # Vibration pattern fallback
                                os.system('termux-vibrate -d 80 2>/dev/null &')
                                time.sleep(0.09)
                                os.system('termux-vibrate -d 80 2>/dev/null &')
                                time.sleep(0.09)
                                os.system('termux-vibrate -d 80 2>/dev/null &')
                                time.sleep(0.09)
                                os.system('termux-vibrate -d 150 2>/dev/null &')
                                time.sleep(0.16)
                                os.system('termux-vibrate -d 100 2>/dev/null &')
                            
                            # System notification
                            os.system('termux-notification --title "📨 LXMF Message" --content "New message received" --sound 2>/dev/null &')
                        except:
                            pass
                    
                    # Terminal bells
                    if self.notify_bell:
                        for _ in range(3):
                            print("\a", end="", flush=True)
                            time.sleep(0.1)
                
                elif system == 'Windows':
                    # === WINDOWS ===
                    if self.notify_sound:
                        sound_played = False
                        
                        # Try custom sound file first
                        if sound_file:
                            try:
                                import winsound  # type: ignore
                                winsound.PlaySound(sound_file, winsound.SND_FILENAME | winsound.SND_ASYNC)  # type: ignore
                                sound_played = True
                            except Exception as e:
                                pass
                        
                        # Fallback to beep melody
                        if not sound_played:
                            try:
                                import winsound  # type: ignore
                                melody = [
                                    (523, 80),    # C5
                                    (659, 80),    # E5
                                    (784, 80),    # G5
                                    (1047, 150),  # C6
                                    (784, 100),   # G5
                                ]
                                
                                for freq, duration in melody:
                                    winsound.Beep(freq, duration)  # type: ignore
                                    time.sleep(0.01)
                            except Exception:
                                if self.notify_bell:
                                    for _ in range(3):
                                        print("\a", end="", flush=True)
                                        time.sleep(0.1)
                    elif self.notify_bell:
                        for _ in range(3):
                            print("\a", end="", flush=True)
                            time.sleep(0.1)
                
                elif system == 'Darwin':
                    # === MACOS ===
                    sound_played = False
                    
                    if self.notify_sound:
                        # Try custom sound file first
                        if sound_file:
                            try:
                                subprocess.Popen(["afplay", sound_file], 
                                            stdout=subprocess.DEVNULL, 
                                            stderr=subprocess.DEVNULL)
                                sound_played = True
                            except Exception:
                                pass
                        
                        # Fallback to system sounds
                        if not sound_played:
                            try:
                                sound_candidates = [
                                    "/System/Library/Sounds/Ping.aiff",
                                    "/System/Library/Sounds/Glass.aiff",
                                    "/System/Library/Sounds/Submarine.aiff"
                                ]
                                sound_path = next((p for p in sound_candidates if os.path.exists(p)), None)
                                if sound_path:
                                    subprocess.Popen(["afplay", sound_path],
                                                stdout=subprocess.DEVNULL,
                                                stderr=subprocess.DEVNULL)
                                else:
                                    subprocess.run(["osascript", "-e", "beep"], check=False)
                            except Exception:
                                if self.notify_bell:
                                    print("\a", end="", flush=True)
                    
                    if self.notify_bell:
                        for _ in range(2):
                            print("\a", end="", flush=True)
                            time.sleep(0.12)
                
                elif system == 'Linux':
                    # === LINUX ===
                    sound_played = False
                    
                    if self.notify_sound:
                        # Try custom sound file first
                        if sound_file:
                            # Try multiple players in order of preference
                            players = [
                                f'paplay "{sound_file}"',
                                f'aplay "{sound_file}"',
                                f'mpg123 -q "{sound_file}"',
                                f'ffplay -nodisp -autoexit -hide_banner -loglevel quiet "{sound_file}"'
                            ]
                            
                            for player_cmd in players:
                                try:
                                    result = os.system(f'{player_cmd} 2>/dev/null &')
                                    if result == 0:
                                        sound_played = True
                                        break
                                except:
                                    continue
                        
                        # Fallback to system sounds
                        if not sound_played:
                            try:
                                result = os.system('paplay /usr/share/sounds/freedesktop/stereo/message-new-instant.oga 2>/dev/null &')
                                
                                if result != 0:
                                    os.system('beep -f 523 -l 80 -n -f 659 -l 80 -n -f 784 -l 80 -n -f 1047 -l 150 -n -f 784 -l 100 2>/dev/null &')
                            except:
                                pass
                    
                    if self.notify_bell:
                        for _ in range(2):
                            print("\a", end="", flush=True)
                            time.sleep(0.15)
                
                else:
                    # === OTHER/UNKNOWN SYSTEMS ===
                    if self.notify_bell:
                        for _ in range(3):
                            print("\a", end="", flush=True)
                            time.sleep(0.1)
            
            except Exception as e:
                # Ultimate fallback to bell if available
                if self.notify_bell:
                    try:
                        for _ in range(3):
                            print("\a", end="", flush=True)
                            time.sleep(0.1)
                    except:
                        pass

        # === VISUAL NOTIFICATION ===
        if self.notify_visual:
            try:
                terminal_width = shutil.get_terminal_size().columns
            except:
                terminal_width = 80
            
            is_termux = os.path.exists('/data/data/com.termux')
            
            # Determine message
            if is_termux:
                msg = " 📱 NEW MESSAGE! "
            else:
                msg = " 📬 NEW MESSAGE! "
            
            # Calculate centered position
            msg_width = min(60, terminal_width)
            padding = (terminal_width - msg_width) // 2
            
            # Quick flash sequence (3 flashes) - PLAIN TEXT
            for _ in range(3):
                # Flash on
                line = " " * padding + "─" * msg_width
                print(f"\r{line}", end="", flush=True)
                time.sleep(0.08)
                
                # Flash off (clear)
                print(f"\r{' ' * terminal_width}", end="\r", flush=True)
                time.sleep(0.08)
            
            # Final message display (brief) - PLAIN TEXT
            centered_msg = msg.center(msg_width, '═')
            line = " " * padding + centered_msg
            print(f"\r{line}", end="", flush=True)
            time.sleep(0.2)
            
            # Clear completely
            print(f"\r{' ' * terminal_width}", end="\r", flush=True)        

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
        
        # Get responsive width
        try:
            width = shutil.get_terminal_size().columns
        except:
            width = 60
        
        # Banner with proper centering
        banner_lines = [
            "██╗     ██╗  ██╗███╗   ███╗███████╗",
            "██║     ╚██╗██╔╝████╗ ████║██╔════╝",
            "██║      ╚███╔╝ ██╔████╔██║█████╗  ",
            "██║      ██╔██╗ ██║╚██╔╝██║██╔══╝  ",
            "███████╗██╔╝ ██╗██║ ╚═╝ ██║██║     ",
            "╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝     ",
            "",
            "Interactive LXMF Client"
        ]
        
        sep_width = min(width, 60)
        print("\n" + "─" * sep_width)
        
        if COLOR_ENABLED:
            for line in banner_lines:
                # Center each line
                centered = line.center(sep_width)
                print(f"{Fore.WHITE}{Style.BRIGHT}{centered}{Style.RESET_ALL}")
        else:
            for line in banner_lines:
                centered = line.center(sep_width)
                print(centered)
        
        print("─" * sep_width + "\n")

    def restart_client(self):
        """Restart the client"""
        print("\n" + "─" * 60)
        self._print_color("Restarting LXMF Client...", Fore.YELLOW + Style.BRIGHT)
        print("─" * 60 + "\n")
        
        # Shutdown current instance
        self.shutdown()
        
        # Restart the Python script
        import sys
        import os
        
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def show_progress_spinner(self, message, duration=2):
        """Show a spinner for background operations"""
        spinner = itertools.cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])
        end_time = time.time() + duration
        
        while time.time() < end_time:
            if COLOR_ENABLED:
                print(f"\r{Fore.CYAN}{next(spinner)}{Style.RESET_ALL} {message}...", end="", flush=True)
            else:
                print(f"\r{next(spinner)} {message}...", end="", flush=True)
            time.sleep(0.1)
        print("\r" + " " * (len(message) + 10), end="\r")
    
    def _handle_address_command(self, parts):
        """Handle address command"""
        print(f"\nDisplay Name: {self.display_name}")
        if hasattr(self.destination, 'hash'):
            print(f"LXMF Address: {RNS.prettyhexrep(self.destination.hash)}")  # type: ignore
        print(f"Auto-announce: Every {self.announce_interval}s\n")
    
    def _handle_name_command(self, parts):
        """Handle name change command"""
        if len(parts) < 2:
            print("💡 Usage: name <new_name>")
        else:
            self.display_name = ' '.join(parts[1:])
            if hasattr(self.destination, 'display_name'):
                setattr(self.destination, 'display_name', self.display_name)  # type: ignore
            self.save_config()
            if hasattr(self.destination, 'announce'):
                self.destination.announce()  # type: ignore
            self._print_success(f"Display name: {self.display_name}")
            self._print_success("Announced to network")
    
    def _handle_interval_command(self, parts):
        """Handle announce interval command"""
        if len(parts) < 2:
            print(f"Current interval: {self.announce_interval}s")
            print("💡 Usage: interval <seconds>")
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
    
    def _handle_announce_command(self, parts):
        """Handle manual announce command"""
        if hasattr(self.destination, 'announce'):
            self.destination.announce()  # type: ignore
            self._print_success("Announced manually")
    
    def _handle_add_command(self, parts):
        """Handle add contact command"""
        if len(parts) < 3:
            print("💡 Usage: add <name> <hash>")
        else:
            self.add_contact(parts[1], parts[2])

    def _handle_edit_command(self, parts):
        """Handle edit contact command"""
        if len(parts) < 2:
            print("💡 Usage: edit <name/#>")
            print("Example: edit Alice")
            print("Example: edit 3")
        else:
            self.edit_contact(parts[1])


    def _handle_savecontact_command(self, parts):
        """Handle quick save contact command"""
        # If called without args, use last sender
        if len(parts) < 2:
            if self.last_sender_hash:
                self.save_contact_from_hash(self.last_sender_hash, self.last_sender_name)
            else:
                print("💡 Usage: savecontact [hash]")
                print("Or receive a message first, then just type 'save'")
        else:
            # Save specific hash
            target_hash = parts[1]
            self.save_contact_from_hash(target_hash)
    
    def _handle_remove_command(self, parts):
        """Handle remove contact command"""
        if len(parts) < 2:
            print("💡 Usage: remove <name>")
        else:
            if parts[1] in self.contacts:
                del self.contacts[parts[1]]
                self.save_contacts()
                self._print_success(f"Removed: {parts[1]}")
            else:
                self._print_error(f"Not found: {parts[1]}")
    
    def _handle_reply_command(self, parts):
        """Handle reply command"""
        if len(parts) < 2:
            print("💡 Usage: reply <message>")
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
    
    def _handle_replyto_command(self, parts):
        """Handle replyto command"""
        if self.last_sender_hash:
            sender_display = self.format_contact_display(self.last_sender_hash, show_hash=True)
            print(f"\nCurrent reply target: {sender_display}\n")
        else:
            print("\nNo reply target set")
            print("Receive a message first\n")
    
    def _handle_send_command(self, parts):
        """Handle send message command"""
        if len(parts) < 3:
            print("💡 Usage: send <name/hash> <message>")
        else:
            message_text = ' '.join(parts[2:])
            self.send_message(parts[1], message_text)
    
    def _handle_messages_command(self, parts):
        """Handle messages command"""
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
                print("💡 Usage: messages user <#>")
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
    
    def _handle_sendpeer_command(self, parts):
        """Handle sendpeer command"""
        if len(parts) < 3:
            print("💡 Usage: sendpeer <peer_number> <message>")
            print("Use 'peers' to see the list first")
        else:
            message_text = ' '.join(parts[2:])
            self.send_to_peer(parts[1], message_text)
    
    def _handle_addpeer_command(self, parts):
        """Handle addpeer command"""
        if len(parts) < 2:
            print("💡 Usage: addpeer <peer_number> [custom_name]")
            print("Use 'peers' to see the list first")
        else:
            custom_name = ' '.join(parts[2:]) if len(parts) > 2 else None
            self.add_peer_to_contacts(parts[1], custom_name)
    
    def _handle_discoverannounce_command(self, parts):
        """Handle discoverannounce command"""
        if len(parts) < 2:
            status = "ON" if self.show_announces else "OFF"
            print(f"\nDiscovery announces: {status}")
            print("💡 Usage: discoverannounce <on/off>")
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
    
    def _handle_blacklist_command(self, parts):
        """Handle blacklist command"""
        if len(parts) < 2:
            self.list_blacklist()
        else:
            subcmd = parts[1].lower()
            if subcmd == 'list':
                self.list_blacklist()
            elif subcmd == 'add' and len(parts) >= 3:
                target = ' '.join(parts[2:])
                dest_hash = self.resolve_contact_or_hash(target)
                if dest_hash:
                    if self.add_to_blacklist(dest_hash):
                        contact_display = self.format_contact_display_short(dest_hash)
                        self._print_success(f"Blacklisted: {contact_display}")
                else:
                    self._print_error(f"Unknown contact or invalid hash: {target}")
            elif subcmd == 'remove' and len(parts) >= 3:
                target = ' '.join(parts[2:])
                dest_hash = self.resolve_contact_or_hash(target)
                if dest_hash:
                    if self.remove_from_blacklist(dest_hash):
                        contact_display = self.format_contact_display_short(dest_hash)
                        self._print_success(f"Unblocked: {contact_display}")
                else:
                    self._print_error(f"Unknown contact or invalid hash: {target}")
            elif subcmd == 'clear':
                confirm = input("Clear entire blacklist? [y/N]: ").strip().lower()
                if confirm == 'y':
                    count = len(self.blacklist)
                    self.blacklist.clear()
                    self.save_blacklist()
                    self._print_success(f"Cleared {count} entries from blacklist")
                else:
                    print("Cancelled")
            else:
                print("💡 Usage:")
                print("  blacklist [list]        - Show blacklist")
                print("  blacklist add <#/name>  - Block contact/peer")
                print("  blacklist remove <#/name> - Unblock")
                print("  blacklist clear         - Clear all")
    
    def _handle_block_command(self, parts):
        """Handle block command"""
        if len(parts) < 2:
            print("💡 Usage: block <contact_#/name/hash>")
        else:
            target = ' '.join(parts[1:])
            dest_hash = self.resolve_contact_or_hash(target)
            if dest_hash:
                if self.add_to_blacklist(dest_hash):
                    contact_display = self.format_contact_display_short(dest_hash)
                    self._print_success(f"Blocked: {contact_display}")
            else:
                self._print_error(f"Unknown contact: {target}")
    
    def _handle_unblock_command(self, parts):
        """Handle unblock command"""
        if len(parts) < 2:
            print("💡 Usage: unblock <contact_#/name/hash>")
        else:
            target = ' '.join(parts[1:])
            dest_hash = self.resolve_contact_or_hash(target)
            if dest_hash:
                if self.remove_from_blacklist(dest_hash):
                    contact_display = self.format_contact_display_short(dest_hash)
                    self._print_success(f"Unblocked: {contact_display}")
            else:
                self._print_error(f"Unknown contact: {target}")
    
    def _handle_plugin_command(self, parts):
        """Handle plugin command"""
        if len(parts) < 2:
            self.list_plugins()
        else:
            subcmd = parts[1].lower()
            if subcmd == 'list':
                self.list_plugins()
            elif subcmd == 'enable' and len(parts) >= 3:
                plugin_name = parts[2]
                self.plugins_enabled[plugin_name] = True
                self.save_plugins_config()
                self._print_success(f"Plugin {plugin_name} enabled")
                self._print_warning("Use 'plugin reload' to activate")
            elif subcmd == 'disable' and len(parts) >= 3:
                plugin_name = parts[2]
                self.plugins_enabled[plugin_name] = False
                self.save_plugins_config()
                self._print_success(f"Plugin {plugin_name} disabled")
                self._print_warning("Use 'plugin reload' to deactivate")
            elif subcmd == 'reload':
                self.plugins = {}
                self.load_plugins()
                self._print_success("Plugins reloaded")
            else:
                print("💡 Usage: plugin [list|enable|disable|reload]")
    
    def _handle_debug_command(self, parts):
        """Handle debug command"""
        print(f"\n=== Debug Info ===")
        print(f"Suppressed file errors: {self.suppressed_errors}")
        print(f"Cache dirty: {self.cache_dirty}")
        print(f"Last cache save: {time.time() - self.last_cache_save:.1f}s ago")
        print(f"Announced peers: {len(self.announced_peers)}")
        print(f"Cached display names: {len(self.display_name_cache)}")
        print()

    def run(self):
        """Main command loop with proper async input handling"""
        self.running = True
        
        print(f"\n{Fore.CYAN}Welcome to LXMF Client!{Style.RESET_ALL}" if COLOR_ENABLED else "\nWelcome to LXMF Client!")
        print(f"{Fore.YELLOW}Type 'help' or 'h' to see available commands{Style.RESET_ALL}\n" if COLOR_ENABLED else "Type 'help' or 'h' to see available commands\n")
        
        # Create prompt session
        session = PromptSession()
        
        try:
            while self.running:
                try:
                    # Build dynamic prompt with proper formatting
                    with self.messages_lock:
                        if self.messages and self.messages[-1]['direction'] == 'inbound':
                            # Use HTML formatting for prompt_toolkit
                            if COLOR_ENABLED:
                                prompt_text = HTML('<style color="green">●</style> &gt; ')
                            else:
                                prompt_text = "● > "
                        else:
                            prompt_text = "> "
                    
                    # Use patch_stdout to allow background prints without corrupting input
                    with patch_stdout():
                        cmd_line = session.prompt(prompt_text).strip()
                    
                    if not cmd_line:
                        continue
                    
                    parts = cmd_line.split(maxsplit=2)
                    cmd = self.resolve_command(parts[0].lower())
                    
                    # Check for plugin commands first
                    if self.handle_plugin_command(cmd, parts):
                        continue
                    
                    # Command routing
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
                        self._handle_address_command(parts)
                    elif cmd == 'name':
                        self._handle_name_command(parts)
                    elif cmd == 'interval':
                        self._handle_interval_command(parts)
                    elif cmd == 'announce':
                        self._handle_announce_command(parts)
                    elif cmd == 'contacts':
                        self.list_contacts()
                    elif cmd == 'add':
                        self._handle_add_command(parts)
                    elif cmd == 'edit':
                        self._handle_edit_command(parts)
                    elif cmd == 'remove':
                        self._handle_remove_command(parts)
                    elif cmd == 'savecontact':
                        self._handle_savecontact_command(parts)
                    elif cmd == 'reply':
                        self._handle_reply_command(parts)
                    elif cmd == 'replyto':
                        self._handle_replyto_command(parts)
                    elif cmd == 'send':
                        self._handle_send_command(parts)
                    elif cmd == 'messages':
                        self._handle_messages_command(parts)
                    elif cmd == 'stats':
                        self.show_stats()
                    elif cmd == 'peers':
                        self.list_peers()
                    elif cmd == 'sendpeer':
                        self._handle_sendpeer_command(parts)
                    elif cmd == 'addpeer':
                        self._handle_addpeer_command(parts)
                    elif cmd == 'discoverannounce':
                        self._handle_discoverannounce_command(parts)
                    elif cmd == 'blacklist':
                        self._handle_blacklist_command(parts)
                    elif cmd == 'block':
                        self._handle_block_command(parts)
                    elif cmd == 'unblock':
                        self._handle_unblock_command(parts)
                    elif cmd == 'clear':
                        self.clear_screen()
                    elif cmd == 'restart':
                        self.restart_client()
                        break
                    elif cmd == 'plugin':
                        self._handle_plugin_command(parts)
                    elif cmd == 'debug':
                        self._handle_debug_command(parts)
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
    
    # Get responsive width
    try:
        width = shutil.get_terminal_size().columns
    except:
        width = 60
    
    sep_width = min(width, 60)
    
    banner_lines = [
        "",
        " ██╗     ██╗  ██╗███╗   ███╗███████╗",
        " ██║     ╚██╗██╔╝████╗ ████║██╔════╝",
        " ██║      ╚███╔╝ ██╔████╔██║█████╗  ",
        " ██║      ██╔██╗ ██║╚██╔╝██║██╔══╝  ",
        " ███████╗██╔╝ ██╗██║ ╚═╝ ██║██║     ",
        " ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝     ",
        "",
        "Interactive LXMF Client"
    ]
    
    print("\n" + "─"*sep_width)
    
    if COLOR_ENABLED:
        for line in banner_lines:
            centered = line.center(sep_width)
            print(f"{Fore.WHITE}{Style.BRIGHT}{centered}{Style.RESET_ALL}")
    else:
        for line in banner_lines:
            centered = line.center(sep_width)
            print(centered)
    
    print("─"*sep_width + "\n")
    
    client = LXMFClient()
    client.run()

if __name__ == "__main__":
    main()

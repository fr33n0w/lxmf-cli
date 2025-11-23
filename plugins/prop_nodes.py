"""
Propagation Node Plugin for LXMF-CLI
Manages LXMF propagation nodes for offline message delivery
Supports: discovery, auto-sync, auto-retry failed messages
"""
import time
import threading
import json
import os
import sys
import tempfile
import RNS
import LXMF

class Plugin:
    def __init__(self, client):
        """Initialize the propagation node plugin"""
        self.client = client
        self.commands = ['prop']
        self.description = "Manage LXMF propagation nodes"
        
        # Propagation nodes discovered
        self.prop_nodes = {}
        self.prop_nodes_lock = threading.Lock()
        self.next_prop_index = 1
        
        # Active propagation node
        self.active_node = None
        
        # Plugin settings
        self.enabled = False
        self.auto_sync_enabled = True
        self.auto_sync_interval = 300
        self.auto_retry_failed = True
        self.show_discovery = False
        
        # Storage
        storage_path = os.path.normpath(client.storage_path)
        self.storage_file = os.path.join(storage_path, "prop_nodes.json")
        
        # Sync thread
        self.sync_thread = None
        self.stop_sync = threading.Event()
        
        # Track last synced timestamp
        self.last_synced_at = None
        
        # Load saved data
        self._load_data()
        
        # Register announce handler
        self._register_prop_announce_handler()
        
        # Hook into message delivery callbacks
        self._hook_message_callbacks()
        
        print("Propagation Node plugin loaded! Use 'prop on' to enable")
    
    def _load_data(self):
        """Load propagation nodes and settings from file"""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.active_node = data.get('active_node', None)
                    self.enabled = data.get('enabled', False)
                    self.auto_sync_enabled = data.get('auto_sync_enabled', True)
                    self.auto_sync_interval = data.get('auto_sync_interval', 300)
                    self.auto_retry_failed = data.get('auto_retry_failed', True)
                    self.show_discovery = data.get('show_discovery', False)
                    self.last_synced_at = data.get('last_synced_at', None)
                    
                    saved_nodes = data.get('nodes', {})
                    for hash_str, node_data in saved_nodes.items():
                        clean_hash = hash_str.replace("<", "").replace(">", "").replace(":", "").replace(" ", "").lower()
                        
                        clean_node = {
                            'display_name': node_data.get('display_name', ''),
                            'index': node_data.get('index', 0),
                            'last_seen': node_data.get('last_seen', 0),
                            'hash': clean_hash,
                            'identity_hash': node_data.get('identity_hash', ''),
                            'operator_name': node_data.get('operator_name', None),
                            'enabled': node_data.get('enabled', None),
                            'per_transfer_limit': node_data.get('per_transfer_limit', None),
                        }
                        self.prop_nodes[clean_hash] = clean_node
                        
                        if clean_node['index'] >= self.next_prop_index:
                            self.next_prop_index = clean_node['index'] + 1
                    
                    if self.active_node:
                        self.active_node = self.active_node.replace("<", "").replace(">", "").replace(":", "").replace(" ", "").lower()
                    
                    if self.prop_nodes:
                        print(f"[PROP] Loaded {len(self.prop_nodes)} propagation node(s)")
            
            except Exception as e:
                print(f"[PROP] Error loading data: {e}")
    
    def _save_data(self):
        """Save propagation nodes and settings to file"""
        try:
            nodes_to_save = {}
            try:
                with self.prop_nodes_lock:
                    for hash_str, node_data in self.prop_nodes.items():
                        nodes_to_save[hash_str] = {
                            'display_name': str(node_data.get('display_name', '')),
                            'index': int(node_data.get('index', 0)),
                            'last_seen': float(node_data.get('last_seen', 0)),
                            'hash': str(node_data.get('hash', hash_str)),
                            'identity_hash': str(node_data.get('identity_hash', '')),
                            'operator_name': node_data.get('operator_name', None),
                            'enabled': node_data.get('enabled', None),
                            'per_transfer_limit': node_data.get('per_transfer_limit', None),
                        }
            except:
                return
            
            data = {
                'active_node': self.active_node,
                'enabled': self.enabled,
                'auto_sync_enabled': self.auto_sync_enabled,
                'auto_sync_interval': self.auto_sync_interval,
                'auto_retry_failed': self.auto_retry_failed,
                'show_discovery': self.show_discovery,
                'last_synced_at': self.last_synced_at,
                'nodes': nodes_to_save
            }
            
            temp_fd, temp_path = tempfile.mkstemp(
                suffix='.json',
                prefix='prop_nodes_',
                dir=os.path.dirname(self.storage_file),
                text=True
            )
            
            try:
                with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                
                if os.path.exists(self.storage_file):
                    try:
                        os.remove(self.storage_file)
                    except:
                        os.remove(temp_path)
                        return
                
                os.rename(temp_path, self.storage_file)
            except:
                try:
                    os.remove(temp_path)
                except:
                    pass
                raise
        
        except:
            pass
    
    def _parse_propagation_node_app_data(self, app_data):
        """Parse propagation node app data (msgpack format)"""
        try:
            import RNS.vendor.umsgpack as msgpack
            data = msgpack.unpackb(app_data)
            return {
                'enabled': bool(data[2]),  # Index 2 is the enabled flag
                'timebase': int(data[1]),
                'per_transfer_limit': int(data[3]),
            }
        except:
            return None
    
    def _get_node_snapshot(self):
        """Get a safe copy of all nodes"""
        snapshot = {}
        try:
            with self.prop_nodes_lock:
                for hash_str, node in self.prop_nodes.items():
                    snapshot[hash_str] = {
                        'display_name': node.get('display_name', ''),
                        'index': node.get('index', 0),
                        'last_seen': node.get('last_seen', 0),
                        'hash': node.get('hash', hash_str),
                        'identity_hash': node.get('identity_hash', ''),
                        'operator_name': node.get('operator_name', None),
                        'enabled': node.get('enabled', None),
                        'per_transfer_limit': node.get('per_transfer_limit', None),
                    }
        except:
            pass
        
        return snapshot
    
    def _hook_message_callbacks(self):
        """Hook into the LXMF router to detect failed messages"""
        try:
            # Check if we've already hooked
            if hasattr(self.client.router, '_prop_plugin_hooked'):
                return
            
            # Store original fail_message method
            original_fail_message = self.client.router.fail_message
            
            def wrapped_fail_message(lxmessage):
                # Call original fail_message first
                original_fail_message(lxmessage)
                
                # If plugin is enabled and auto-retry is on, retry via propagation
                if self.enabled and self.auto_retry_failed and self.active_node:
                    # Only retry if the message was trying DIRECT or OPPORTUNISTIC
                    if lxmessage.method in [LXMF.LXMessage.DIRECT, LXMF.LXMessage.OPPORTUNISTIC]:
                        if lxmessage.desired_method != LXMF.LXMessage.PROPAGATED:
                            self._retry_failed_message(lxmessage)
            
            # Replace the method
            self.client.router.fail_message = wrapped_fail_message
            self.client.router._prop_plugin_hooked = True
            print("[PROP] Hooked into message failure callback")
        
        except Exception as e:
            print(f"[PROP] Warning: Could not hook message callbacks: {e}")

    def _retry_failed_message(self, lxmf_message):
        """Retry a failed message via propagation node"""
        try:
            if not self.active_node:
                return
            
            prop_node = self._get_active_prop_node()
            if not prop_node:
                return
            
            dest_hash = lxmf_message.destination_hash.hex()
            
            # Get content - handle both bytes and string
            if hasattr(lxmf_message, 'content'):
                content = lxmf_message.content
                if isinstance(content, bytes):
                    try:
                        content = content.decode('utf-8')
                    except:
                        pass
            else:
                return
            
            # Get title
            title = ""
            if hasattr(lxmf_message, 'title'):
                title = lxmf_message.title
                if isinstance(title, bytes):
                    try:
                        title = title.decode('utf-8')
                    except:
                        title = ""
            
            recipient_name = self.client.format_contact_display_short(dest_hash)
            operator = prop_node.get('operator_name') or 'Unknown'
            
            # Single, clean output line
            disabled_note = " (node marked disabled)" if prop_node.get('enabled') is False else ""
            print(f"\n[PROP] 🔄 Retrying to {recipient_name} via {operator}{disabled_note}")
            
            # Get destination identity
            dest_hash_bytes = bytes.fromhex(dest_hash)
            dest_identity = RNS.Identity.recall(dest_hash_bytes)
            
            if not dest_identity:
                print(f"[PROP] ❌ Cannot recall identity")
                return
            
            # Create destination
            dest = RNS.Destination(
                dest_identity,
                RNS.Destination.OUT,
                RNS.Destination.SINGLE,
                "lxmf",
                "delivery"
            )
            
            # Create new LXMF message with PROPAGATED method
            new_message = LXMF.LXMessage(
                destination=dest,
                source=self.client.destination,
                content=content,
                title=title,
                desired_method=LXMF.LXMessage.PROPAGATED
            )
            
            # Copy fields if any
            if hasattr(lxmf_message, 'fields') and lxmf_message.fields:
                new_message.fields = lxmf_message.fields
            
            # Set propagation node
            prop_hash_bytes = bytes.fromhex(prop_node['hash'])
            try:
                self.client.router.set_outbound_propagation_node(prop_hash_bytes)
            except:
                pass
            
            # Send via router
            self.client.router.handle_outbound(new_message)
            
            print(f"[PROP] ✓ Queued via propagation node")
            print("> ", end="", flush=True)
        
        except Exception as e:
            print(f"[PROP] ❌ Retry error: {e}")


    def _retry_failed_message(self, lxmf_message):
        """Retry a failed message via propagation node"""
        try:
            if not self.active_node:
                return
            
            prop_node = self._get_active_prop_node()
            if not prop_node:
                return
            
            # REMOVED: Don't skip disabled nodes - always attempt retry
            
            dest_hash = lxmf_message.destination_hash.hex()
            
            # Get content - handle both bytes and string
            if hasattr(lxmf_message, 'content'):
                content = lxmf_message.content
                if isinstance(content, bytes):
                    try:
                        content = content.decode('utf-8')
                    except:
                        pass
            else:
                print(f"[PROP] Cannot retry message without content")
                return
            
            # Get title
            title = ""
            if hasattr(lxmf_message, 'title'):
                title = lxmf_message.title
                if isinstance(title, bytes):
                    try:
                        title = title.decode('utf-8')
                    except:
                        title = ""
            
            recipient_name = self.client.format_contact_display_short(dest_hash)
            operator = prop_node.get('operator_name') or 'Unknown'
            
            print(f"[PROP] 🔄 Auto-retry: Sending to {recipient_name} via propagation node")
            print(f"[PROP] Using node operated by: {operator}")
            
            # Inform about disabled status but don't skip
            if prop_node.get('enabled') is False:
                print(f"[PROP] ℹ️  Note: Node is marked DISABLED, but attempting anyway")
            
            # Get destination identity
            dest_hash_bytes = bytes.fromhex(dest_hash)
            dest_identity = RNS.Identity.recall(dest_hash_bytes)
            
            if not dest_identity:
                print(f"[PROP] ❌ Cannot recall identity for retry")
                return
            
            # Create destination
            dest = RNS.Destination(
                dest_identity,
                RNS.Destination.OUT,
                RNS.Destination.SINGLE,
                "lxmf",
                "delivery"
            )
            
            # Create new LXMF message with PROPAGATED method
            new_message = LXMF.LXMessage(
                destination=dest,
                source=self.client.destination,
                content=content,
                title=title,
                desired_method=LXMF.LXMessage.PROPAGATED
            )
            
            # Copy fields if any
            if hasattr(lxmf_message, 'fields') and lxmf_message.fields:
                new_message.fields = lxmf_message.fields
            
            # Set propagation node
            prop_hash_bytes = bytes.fromhex(prop_node['hash'])
            try:
                self.client.router.set_outbound_propagation_node(prop_hash_bytes)
            except:
                pass
            
            # Send via router
            self.client.router.handle_outbound(new_message)
            
            print(f"[PROP] ✓ Message queued via propagation node")
            print("> ", end="", flush=True)
        
        except Exception as e:
            print(f"[PROP] ❌ Auto-retry error: {e}")
            import traceback
            traceback.print_exc()

    def _register_prop_announce_handler(self):
        """Register handler to detect propagation node announces"""
        
        class PropNodeAnnounceHandler:
            def __init__(self, plugin):
                self.plugin = plugin
                self.aspect_filter = "lxmf.propagation"
            
            def received_announce(self, destination_hash, announced_identity, app_data):
                """Called when a propagation node announces"""
                try:
                    clean_hash = destination_hash.hex()
                    identity_hash = announced_identity.hash.hex()
                    
                    prop_data = None
                    if app_data:
                        prop_data = self.plugin._parse_propagation_node_app_data(app_data)
                    
                    operator_name = None
                    try:
                        if hasattr(self.plugin.client, 'peers') and identity_hash in self.plugin.client.peers:
                            peer = self.plugin.client.peers[identity_hash]
                            operator_name = peer.get('display_name', None)
                    except:
                        pass
                    
                    try:
                        with self.plugin.prop_nodes_lock:
                            is_new = clean_hash not in self.plugin.prop_nodes
                            
                            if is_new:
                                node_index = self.plugin.next_prop_index
                                self.plugin.next_prop_index += 1
                                
                                self.plugin.prop_nodes[clean_hash] = {
                                    'display_name': f"PropNode-{clean_hash[:8]}",
                                    'index': node_index,
                                    'last_seen': time.time(),
                                    'hash': clean_hash,
                                    'identity_hash': identity_hash,
                                    'operator_name': operator_name,
                                    'enabled': prop_data['enabled'] if prop_data else None,
                                    'per_transfer_limit': prop_data['per_transfer_limit'] if prop_data else None,
                                }
                                
                                if self.plugin.show_discovery:
                                    status = "ENABLED" if (prop_data and prop_data['enabled']) else "DISABLED"
                                    print(f"\n[PROP] 🌐 Discovered: {clean_hash[:16]}... (#{node_index}) [{status}]")
                                    if operator_name:
                                        print(f"[PROP] Operated by: {operator_name}")
                                    print(f"💡 Use 'prop set {node_index}' to activate")
                                    print("> ", end="", flush=True)
                            
                            else:
                                self.plugin.prop_nodes[clean_hash]['last_seen'] = time.time()
                                self.plugin.prop_nodes[clean_hash]['identity_hash'] = identity_hash
                                
                                if operator_name and not self.plugin.prop_nodes[clean_hash].get('operator_name'):
                                    self.plugin.prop_nodes[clean_hash]['operator_name'] = operator_name
                                
                                if prop_data:
                                    self.plugin.prop_nodes[clean_hash]['enabled'] = prop_data['enabled']
                                    self.plugin.prop_nodes[clean_hash]['per_transfer_limit'] = prop_data['per_transfer_limit']
                    except:
                        pass
                    
                    self.plugin._save_data()
                
                except:
                    pass
        
        self.prop_announce_handler = PropNodeAnnounceHandler(self)
        RNS.Transport.register_announce_handler(self.prop_announce_handler)
        print("[PROP] Announce handler registered for propagation nodes")
    
    def _get_active_prop_node(self):
        """Get the active propagation node"""
        if not self.active_node:
            return None
        
        try:
            with self.prop_nodes_lock:
                if self.active_node in self.prop_nodes:
                    return self.prop_nodes[self.active_node].copy()
        except:
            pass
        
        return None
    
    def _send_to_propagation_node(self, dest_hash, content, title=None):
        """Send a message via propagation node"""
        prop_node = self._get_active_prop_node()
        
        if not prop_node:
            print("\n[PROP] ❌ No propagation node set. Use 'prop set <#>' first")
            return False
        
        if prop_node.get('enabled') is False:
            print(f"\n[PROP] ⚠️  Propagation node is DISABLED")
            print(f"[PROP] Sending anyway, but delivery may fail...")
        
        try:
            dest_hash_clean = dest_hash.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
            dest_hash_bytes = bytes.fromhex(dest_hash_clean)
            
            dest_identity = RNS.Identity.recall(dest_hash_bytes)
            
            if not dest_identity:
                print(f"\n[PROP] Requesting path for destination...")
                RNS.Transport.request_path(dest_hash_bytes)
                time.sleep(2)
                dest_identity = RNS.Identity.recall(dest_hash_bytes)
                
                if not dest_identity:
                    print(f"[PROP] ⚠️  Cannot recall identity")
            
            if dest_identity:
                dest = RNS.Destination(
                    dest_identity,
                    RNS.Destination.OUT,
                    RNS.Destination.SINGLE,
                    "lxmf",
                    "delivery"
                )
            else:
                print(f"[PROP] ❌ Cannot create destination without identity")
                return False
            
            message = LXMF.LXMessage(
                destination=dest,
                source=self.client.destination,
                content=content,
                title=title or "",
                desired_method=LXMF.LXMessage.PROPAGATED
            )
            
            prop_node_hash_bytes = bytes.fromhex(prop_node['hash'])
            
            try:
                self.client.router.set_outbound_propagation_node(prop_node_hash_bytes)
                print(f"\n[PROP] ✓ Set propagation node: {prop_node['hash'][:16]}...")
            except Exception as e:
                print(f"\n[PROP] ⚠️  Could not set propagation node: {e}")
            
            print(f"[PROP] 📤 Sending via propagation node...")
            self.client.router.handle_outbound(message)
            
            operator = prop_node.get('operator_name') or 'Unknown'
            recipient_name = self.client.format_contact_display_short(dest_hash)
            
            print(f"[PROP] ✓ Message queued for {recipient_name}")
            print(f"[PROP] Via propagation node operated by: {operator}")
            print("> ", end="", flush=True)
            
            return True
        
        except Exception as e:
            print(f"\n[PROP] ❌ Error: {e}")
            return False

    def _sync_from_propagation_nodes(self):
        """Request messages from the active propagation node"""
        if not self.active_node:
            print("\n[PROP] No propagation node configured")
            print("Use 'prop set <#>' to configure one\n")
            return
        
        node = None
        try:
            with self.prop_nodes_lock:
                if self.active_node in self.prop_nodes:
                    node = self.prop_nodes[self.active_node].copy()
        except:
            pass
        
        if not node:
            print("\n[PROP] ❌ Active propagation node not found\n")
            return
        
        try:
            operator = node.get('operator_name') or 'Unknown'
            node_hash = node.get('hash')
            
            print(f"\n[PROP] 🔄 Syncing from propagation node...")
            print(f"[PROP] Operated by: {operator}")
            
            prop_hash_bytes = bytes.fromhex(node_hash)
            
            # First, set the outbound propagation node
            try:
                self.client.router.set_outbound_propagation_node(prop_hash_bytes)
                print(f"[PROP] ✓ Set outbound propagation node")
            except Exception as e:
                print(f"[PROP] ⚠️  Could not set propagation node: {e}")
            
            # Check if we can recall the propagation node identity
            prop_identity = RNS.Identity.recall(prop_hash_bytes)
            
            if not prop_identity:
                print(f"[PROP] ⚠️  Cannot recall propagation node identity")
                print(f"[PROP] Requesting path...")
                RNS.Transport.request_path(prop_hash_bytes)
                time.sleep(3)
                prop_identity = RNS.Identity.recall(prop_hash_bytes)
                
                if not prop_identity:
                    print(f"[PROP] ❌ Still cannot recall identity. Try again later.")
                    return
            
            print(f"[PROP] ✓ Propagation node identity recalled")
            
            # Now request messages using OUR identity (the client's delivery identity)
            # The router will identify as this identity to the propagation node
            print(f"[PROP] 📥 Requesting messages for our identity...")
            self.client.router.request_messages_from_propagation_node(
                self.client.identity,
                max_messages=None
            )
            
            self.last_synced_at = int(time.time())
            self._save_data()
            
            print(f"[PROP] ✓ Sync request sent, waiting for response...")
            
            # Start monitoring the sync completion
            self._monitor_sync_completion()
        
        except Exception as e:
            print(f"[PROP] ❌ Error syncing: {e}")
            import traceback
            traceback.print_exc()        

    def _monitor_sync_completion(self):
        """Monitor sync completion and report results"""
        def monitor_thread():
            try:
                # Wait for sync to complete (max 30 seconds)
                start_time = time.time()
                last_state = None
                
                while time.time() - start_time < 30:
                    if hasattr(self.client.router, 'propagation_transfer_state'):
                        state = self.client.router.propagation_transfer_state
                        
                        # State 0x07 = COMPLETE
                        if state == 0x07:
                            if hasattr(self.client.router, 'propagation_transfer_last_result'):
                                result = self.client.router.propagation_transfer_last_result
                                if result is not None:
                                    if result == 0:
                                        print(f"\n[PROP] ℹ️  No messages waiting on propagation node")
                                    else:
                                        ms = "" if result == 1 else "s"
                                        print(f"\n[PROP] ✓ Received {result} message{ms} from propagation node")
                                    
                                    # Check for duplicates
                                    if hasattr(self.client.router, 'propagation_transfer_last_duplicates'):
                                        duplicates = self.client.router.propagation_transfer_last_duplicates
                                        if duplicates and duplicates > 0:
                                            ds = "" if duplicates == 1 else "s"
                                            print(f"[PROP] ℹ️  {duplicates} duplicate{ds} skipped")
                                    
                                    print("> ", end="", flush=True)
                                    break
                        
                        # Check for failure states (0xf0 and above)
                        elif state >= 0xf0 and state != last_state:
                            state_names = {
                                0xf0: "No path to propagation node",
                                0xf1: "Link failed",
                                0xf2: "Transfer failed",
                                0xf3: "No identity received",
                                0xf4: "No access",
                                0xfe: "Failed"
                            }
                            error_msg = state_names.get(state, f"Unknown error (0x{state:02x})")
                            print(f"\n[PROP] ❌ Sync failed: {error_msg}")
                            print("> ", end="", flush=True)
                            break
                        
                        last_state = state
                    
                    time.sleep(0.5)
            
            except Exception as e:
                print(f"\n[PROP] Error monitoring sync: {e}")
        
        # Start monitoring thread
        thread = threading.Thread(target=monitor_thread, daemon=True)
        thread.start()

    def _check_sync_status(self):
        """Check the current propagation transfer state"""
        try:
            if hasattr(self.client.router, 'propagation_transfer_state'):
                state = self.client.router.propagation_transfer_state
                progress = self.client.router.propagation_transfer_progress
                
                state_names = {
                    0x00: "IDLE",
                    0x01: "PATH_REQUESTED",
                    0x02: "LINK_ESTABLISHING",
                    0x03: "LINK_ESTABLISHED",
                    0x04: "REQUEST_SENT",
                    0x05: "RECEIVING",
                    0x06: "RESPONSE_RECEIVED",
                    0x07: "COMPLETE",
                    0xf0: "NO_PATH",
                    0xf1: "LINK_FAILED",
                    0xf2: "TRANSFER_FAILED",
                    0xf3: "NO_IDENTITY_RCVD",
                    0xf4: "NO_ACCESS",
                    0xfe: "FAILED"
                }
                
                state_name = state_names.get(state, f"UNKNOWN({state})")
                
                print(f"\n{'='*60}")
                print(f"PROPAGATION SYNC STATUS")
                print(f"{'='*60}")
                print(f"State:    {state_name}")
                print(f"Progress: {int(progress*100)}%")
                
                if hasattr(self.client.router, 'propagation_transfer_last_result'):
                    last_result = self.client.router.propagation_transfer_last_result
                    if last_result is not None:
                        print(f"Last sync: {last_result} messages received")
                
                if hasattr(self.client.router, 'outbound_propagation_link'):
                    link = self.client.router.outbound_propagation_link
                    if link:
                        link_status = {
                            0: "PENDING",
                            1: "HANDSHAKE",
                            2: "ACTIVE", 
                            3: "STALE",
                            4: "CLOSED"
                        }
                        status_name = link_status.get(link.status, f"UNKNOWN({link.status})")
                        print(f"Link:     {status_name}")
                
                print(f"{'='*60}\n")
            else:
                print("\n[PROP] No sync status available\n")
        
        except Exception as e:
            print(f"\n[PROP] Error checking status: {e}\n")

    def _auto_sync_loop(self):
        """Background thread for automatic syncing"""
        if self.auto_sync_enabled and self.enabled and self.active_node:
            time.sleep(5)
            print("\n[PROP] Initial sync...")
            self._sync_from_propagation_nodes()
            print("> ", end="", flush=True)
        
        while not self.stop_sync.is_set():
            if self.stop_sync.wait(self.auto_sync_interval):
                break
            
            if self.auto_sync_enabled and self.enabled and self.active_node:
                print(f"\n[PROP] Auto-sync at {time.strftime('%H:%M:%S')}")
                self._sync_from_propagation_nodes()
                print("> ", end="", flush=True)
    
    def _start_auto_sync(self):
        """Start auto-sync thread"""
        if self.sync_thread and self.sync_thread.is_alive():
            return
        
        self.stop_sync.clear()
        self.sync_thread = threading.Thread(target=self._auto_sync_loop, daemon=True)
        self.sync_thread.start()
        print("[PROP] Auto-sync thread started")
    
    def _stop_auto_sync(self):
        """Stop auto-sync thread"""
        if self.sync_thread and self.sync_thread.is_alive():
            self.stop_sync.set()
            self.sync_thread.join(timeout=2)
            print("[PROP] Auto-sync thread stopped")
    
    def _format_time_ago(self, timestamp):
        """Format timestamp as time ago string"""
        try:
            time_diff = time.time() - timestamp
            if time_diff < 60:
                return "just now"
            elif time_diff < 3600:
                return f"{int(time_diff/60)}m ago"
            elif time_diff < 86400:
                return f"{int(time_diff/3600)}h ago"
            else:
                return f"{int(time_diff/86400)}d ago"
        except:
            return "unknown"
    
    def _list_propagation_nodes(self):
        """List all discovered propagation nodes"""
        try:
            import shutil
            try:
                width = min(shutil.get_terminal_size().columns, 100)
            except:
                width = 100
            
            nodes_snapshot = self._get_node_snapshot()
            
            if not nodes_snapshot:
                print("\n[PROP] No propagation nodes discovered yet")
                print("Wait for propagation node announces\n")
                print("💡 Discovery is running in background")
                if not self.show_discovery:
                    print("   Alerts are OFF - use 'prop discover on' to see discoveries\n")
                return
            
            print(f"\n{'='*width}")
            print(f"PROPAGATION NODES".center(width))
            print(f"{'='*width}")
            
            sorted_nodes = sorted(nodes_snapshot.items(), 
                                key=lambda x: x[1].get('index', 999999))
            
            print(f"\n{'#':<5} {'★':<3} {'Status':<10} {'Operator':<25} {'Hash':<20} {'Last Seen':<15}")
            print(f"{'─'*5} {'─'*3} {'─'*10} {'─'*25} {'─'*20} {'─'*15}")
            
            for hash_str, node in sorted_nodes:
                try:
                    index = node.get('index', '?')
                    operator = node.get('operator_name') or 'Unknown'
                    last_seen = node.get('last_seen', 0)
                    is_active = (hash_str == self.active_node)
                    enabled = node.get('enabled', None)
                    
                    if enabled is True:
                        status = "ENABLED"
                    elif enabled is False:
                        status = "DISABLED"
                    else:
                        status = "UNKNOWN"
                    
                    time_str = self._format_time_ago(last_seen)
                    active_marker = "★" if is_active else ""
                    
                    if len(operator) > 23:
                        operator = operator[:20] + "..."
                    
                    hash_display = hash_str[:18] if hash_str else "unknown"
                    
                    print(f"{index:<5} {active_marker:<3} {status:<10} {operator:<25} {hash_display:<20} {time_str:<15}")
                except:
                    continue
            
            print(f"{'='*width}")
            print(f"\n💡 Commands:")
            print(f"  prop set <#>   - Set as active propagation node")
            print(f"  prop unset     - Deactivate propagation node")
            print(f"  prop sync      - Sync messages now")
            print()
        
        except KeyboardInterrupt:
            print("\n[PROP] Interrupted\n")
        except Exception as e:
            print(f"\n[PROP] Error: {e}\n")
    
    def _show_status(self):
        """Show detailed status of all plugin settings"""
        try:
            status = "ENABLED ✓" if self.enabled else "DISABLED ✗"
            auto_sync = "ENABLED ✓" if self.auto_sync_enabled else "DISABLED ✗"
            auto_retry = "ENABLED ✓" if self.auto_retry_failed else "DISABLED ✗"
            discovery = "ENABLED ✓" if self.show_discovery else "DISABLED ✗ (silent)"
            
            active_name = "None"
            if self.active_node:
                node = self._get_active_prop_node()
                if node:
                    operator = node.get('operator_name') or 'Unknown'
                    active_name = f"{operator} ({node['hash'][:8]}...)"
            
            last_sync = "Never"
            if self.last_synced_at:
                last_sync = self._format_time_ago(self.last_synced_at)
            
            nodes_snapshot = self._get_node_snapshot()
            total_nodes = len(nodes_snapshot)
            enabled_nodes = sum(1 for n in nodes_snapshot.values() if n.get('enabled') is True)
            disabled_nodes = sum(1 for n in nodes_snapshot.values() if n.get('enabled') is False)
            unknown_nodes = total_nodes - enabled_nodes - disabled_nodes
            
            print(f"\n{'='*70}")
            print(f"PROPAGATION NODE PLUGIN - STATUS".center(70))
            print(f"{'='*70}")
            print(f"\n{'Plugin Status:':<30} {status}")
            print(f"{'Active Propagation Node:':<30} {active_name}")
            print(f"{'Last Sync:':<30} {last_sync}")
            print(f"\n{'Settings:':<30}")
            print(f"  {'Auto-sync:':<28} {auto_sync}")
            print(f"  {'  Interval:':<28} {self.auto_sync_interval}s")
            print(f"  {'Auto-retry Failed:':<28} {auto_retry}")
            print(f"  {'Discovery Alerts:':<28} {discovery}")
            print(f"\n{'Discovered Nodes:':<30}")
            print(f"  {'Total:':<28} {total_nodes}")
            print(f"  {'Enabled:':<28} {enabled_nodes}")
            print(f"  {'Disabled:':<28} {disabled_nodes}")
            print(f"  {'Unknown:':<28} {unknown_nodes}")
            print(f"\n{'='*70}\n")
        
        except KeyboardInterrupt:
            print("\n[PROP] Interrupted\n")
        except Exception as e:
            print(f"\n[PROP] Error: {e}\n")
    
    def _set_active(self, node_identifier):
        """Set a propagation node as active by index or hash"""
        try:
            # Try to parse as index number first
            try:
                index = int(node_identifier)
                
                nodes_snapshot = self._get_node_snapshot()
                for hash_str, node in nodes_snapshot.items():
                    if node.get('index') == index:
                        self.active_node = hash_str
                        self._save_data()
                        
                        try:
                            prop_hash_bytes = bytes.fromhex(hash_str)
                            self.client.router.set_outbound_propagation_node(prop_hash_bytes)
                        except Exception as e:
                            print(f"[PROP] Warning: Could not set on router: {e}")
                        
                        operator = node.get('operator_name') or 'Unknown'
                        enabled = node.get('enabled', None)
                        
                        print(f"\n[PROP] ✓ Active propagation node set")
                        print(f"[PROP] Operator: {operator}")
                        print(f"[PROP] Hash: {hash_str[:16]}...")
                        if enabled is False:
                            print(f"[PROP] ℹ️  Note: This node is currently marked as DISABLED")
                            print(f"[PROP] Will still attempt to use it for message propagation")
                        print(f"[PROP] Messages will route via this node\n")
                        return
                
                print(f"\n[PROP] ❌ Propagation node #{index} not found\n")
                
            except ValueError:
                # Not a number, try as hash
                clean_hash = node_identifier.replace("<", "").replace(">", "").replace(":", "").replace(" ", "").lower()
                
                # Check if this hash exists in discovered nodes
                nodes_snapshot = self._get_node_snapshot()
                
                if clean_hash in nodes_snapshot:
                    node = nodes_snapshot[clean_hash]
                    self.active_node = clean_hash
                    self._save_data()
                    
                    try:
                        prop_hash_bytes = bytes.fromhex(clean_hash)
                        self.client.router.set_outbound_propagation_node(prop_hash_bytes)
                    except Exception as e:
                        print(f"[PROP] Warning: Could not set on router: {e}")
                    
                    operator = node.get('operator_name') or 'Unknown'
                    enabled = node.get('enabled', None)
                    
                    print(f"\n[PROP] ✓ Active propagation node set")
                    print(f"[PROP] Operator: {operator}")
                    print(f"[PROP] Hash: {clean_hash[:16]}...")
                    if enabled is False:
                        print(f"[PROP] ℹ️  Note: This node is currently marked as DISABLED")
                        print(f"[PROP] Will still attempt to use it for message propagation")
                    print(f"[PROP] Messages will route via this node\n")
                else:
                    # Hash not in discovered nodes, but allow setting it anyway
                    print(f"\n[PROP] ℹ️  Propagation node {clean_hash[:16]}... not in discovered list")
                    print(f"[PROP] Setting anyway (you may need to wait for an announce)...")
                    
                    self.active_node = clean_hash
                    
                    # Create a basic entry for this node
                    with self.prop_nodes_lock:
                        if clean_hash not in self.prop_nodes:
                            node_index = self.next_prop_index
                            self.next_prop_index += 1
                            
                            self.prop_nodes[clean_hash] = {
                                'display_name': f"PropNode-{clean_hash[:8]}",
                                'index': node_index,
                                'last_seen': 0,
                                'hash': clean_hash,
                                'identity_hash': '',
                                'operator_name': None,
                                'enabled': None,
                                'per_transfer_limit': None,
                            }
                    
                    self._save_data()
                    
                    try:
                        prop_hash_bytes = bytes.fromhex(clean_hash)
                        self.client.router.set_outbound_propagation_node(prop_hash_bytes)
                        # Request path to get announce
                        RNS.Transport.request_path(prop_hash_bytes)
                    except Exception as e:
                        print(f"[PROP] Warning: Could not set on router: {e}")
                    
                    print(f"[PROP] ✓ Active propagation node set to {clean_hash[:16]}...\n")
        
        except KeyboardInterrupt:
            print("\n[PROP] Interrupted\n")
        except Exception as e:
            print(f"\n[PROP] ❌ Error: {e}\n")
            import traceback
            traceback.print_exc()

    def _send_to_propagation_node(self, dest_hash, content, title=None):
        """Send a message via propagation node"""
        prop_node = self._get_active_prop_node()
        
        if not prop_node:
            print("\n[PROP] ❌ No propagation node set. Use 'prop set <#>' first")
            return False
        
        # Don't block disabled nodes - just inform the user
        if prop_node.get('enabled') is False:
            print(f"\n[PROP] ℹ️  Note: Propagation node is marked as DISABLED")
            print(f"[PROP] Attempting to send anyway...")
        
        try:
            dest_hash_clean = dest_hash.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
            dest_hash_bytes = bytes.fromhex(dest_hash_clean)
            
            dest_identity = RNS.Identity.recall(dest_hash_bytes)
            
            if not dest_identity:
                print(f"\n[PROP] Requesting path for destination...")
                RNS.Transport.request_path(dest_hash_bytes)
                time.sleep(2)
                dest_identity = RNS.Identity.recall(dest_hash_bytes)
                
                if not dest_identity:
                    print(f"[PROP] ⚠️  Cannot recall identity")
            
            if dest_identity:
                dest = RNS.Destination(
                    dest_identity,
                    RNS.Destination.OUT,
                    RNS.Destination.SINGLE,
                    "lxmf",
                    "delivery"
                )
            else:
                print(f"[PROP] ❌ Cannot create destination without identity")
                return False
            
            message = LXMF.LXMessage(
                destination=dest,
                source=self.client.destination,
                content=content,
                title=title or "",
                desired_method=LXMF.LXMessage.PROPAGATED
            )
            
            prop_node_hash_bytes = bytes.fromhex(prop_node['hash'])
            
            try:
                self.client.router.set_outbound_propagation_node(prop_node_hash_bytes)
                print(f"\n[PROP] ✓ Set propagation node: {prop_node['hash'][:16]}...")
            except Exception as e:
                print(f"\n[PROP] ⚠️  Could not set propagation node: {e}")
            
            print(f"[PROP] 📤 Sending via propagation node...")
            self.client.router.handle_outbound(message)
            
            operator = prop_node.get('operator_name') or 'Unknown'
            recipient_name = self.client.format_contact_display_short(dest_hash)
            
            print(f"[PROP] ✓ Message queued for {recipient_name}")
            print(f"[PROP] Via propagation node operated by: {operator}")
            print("> ", end="", flush=True)
            
            return True
        
        except Exception as e:
            print(f"\n[PROP] ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _unset_active(self):
        """Deactivate the current propagation node"""
        try:
            if self.active_node:
                node = self._get_active_prop_node()
                if node:
                    hash_display = node['hash'][:16]
                    self.active_node = None
                    self._save_data()
                    
                    try:
                        self.client.router.set_outbound_propagation_node(None)
                    except:
                        pass
                    
                    print(f"\n[PROP] ✓ Deactivated: {hash_display}...\n")
            else:
                print("\n[PROP] No active propagation node\n")
        except KeyboardInterrupt:
            print("\n[PROP] Interrupted\n")
            
    def handle_command(self, cmd, parts):
        """Handle prop command"""
        try:
            if cmd == 'prop':
                if len(parts) < 2:
                    print(f"\n{'='*60}")
                    print(f"PROPAGATION NODE PLUGIN")
                    print(f"{'='*60}")
                    print("\nCommands:")
                    print("  prop status          - Show detailed status")
                    print("  prop on/off          - Enable/disable plugin")
                    print("  prop list            - List propagation nodes")
                    print("  prop set <#|hash>    - Set active node by index or hash")
                    print("  prop unset           - Deactivate node")
                    print("  prop sync            - Sync messages now")
                    print("  prop send <#|hash> <message>  - Send via prop node")
                    print("  prop autosync on/off - Toggle auto-sync")
                    print("  prop interval <s>    - Set sync interval")
                    print("  prop retry on/off    - Auto-retry failed")
                    print("  prop discover on/off - Toggle alerts")
                    print(f"{'='*60}\n")
                
                else:
                    subcmd = parts[1].lower()
                    
                    if subcmd == 'status':
                        self._show_status()
                    
                    elif subcmd in ['on', 'enable']:
                        self.enabled = True
                        self._save_data()
                        if self.auto_sync_enabled:
                            self._start_auto_sync()
                        print("\n[PROP] ✓ Plugin ENABLED\n")
                    
                    elif subcmd in ['off', 'disable']:
                        self.enabled = False
                        self._save_data()
                        self._stop_auto_sync()
                        print("\n[PROP] ✓ Plugin DISABLED\n")
                    
                    elif subcmd == 'list':
                        self._list_propagation_nodes()
                    
                    elif subcmd == 'set':
                        if len(parts) < 3:
                            print("\n[PROP] Usage: prop set <#|hash>\n")
                            print("  <#>    - Node index from 'prop list'")
                            print("  <hash> - Full propagation node hash\n")
                        else:
                            self._set_active(parts[2])
                    
                    elif subcmd == 'unset':
                        self._unset_active()
                    
                    elif subcmd == 'sync':
                        if len(parts) >= 3 and parts[2].lower() == 'status':
                            self._check_sync_status()
                        else:
                            self._sync_from_propagation_nodes()
                                        
                    elif subcmd == 'send':
                        if len(parts) < 3:
                            print("\n[PROP] Usage: prop send <#|hash> <message>\n")
                            print("  <#>    - Contact index from 'c' command")
                            print("  <hash> - Full destination hash\n")
                        else:
                            # The client is joining everything after 'send' into parts[2]
                            # So we need to split it ourselves
                            remaining = parts[2].split(None, 1)  # Split on first whitespace only
                            
                            if len(remaining) < 2:
                                print("\n[PROP] Usage: prop send <#|hash> <message>\n")
                                print("  <#>    - Contact index from 'c' command")
                                print("  <hash> - Full destination hash\n")
                            else:
                                target = remaining[0]
                                message = remaining[1]
                                
                                # Try to resolve as contact index or hash
                                dest_hash = None
                                
                                # First try as contact index (number)
                                try:
                                    contact_index = int(target)
                                    # Use the client's contact resolution with the index
                                    if hasattr(self.client, 'contacts') and contact_index > 0 and contact_index <= len(self.client.contacts):
                                        contact = list(self.client.contacts.values())[contact_index - 1]
                                        dest_hash = contact['hash']
                                except (ValueError, IndexError, KeyError):
                                    pass
                                
                                # If not found as index, try as hash or contact name
                                if not dest_hash:
                                    dest_hash = self.client.resolve_contact_or_hash(target)
                                
                                if dest_hash:
                                    self._send_to_propagation_node(dest_hash, message)
                                else:
                                    print(f"\n[PROP] ❌ Contact not found: {target}\n")
                    
                    elif subcmd == 'autosync':
                        if len(parts) < 3:
                            print("\n[PROP] Usage: prop autosync <on|off>\n")
                        else:
                            setting = parts[2].lower()
                            if setting in ['on', 'enable']:
                                self.auto_sync_enabled = True
                                self._save_data()
                                if self.enabled:
                                    self._start_auto_sync()
                                print("\n[PROP] ✓ Auto-sync ENABLED\n")
                            elif setting in ['off', 'disable']:
                                self.auto_sync_enabled = False
                                self._save_data()
                                self._stop_auto_sync()
                                print("\n[PROP] ✓ Auto-sync DISABLED\n")
                            else:
                                print("\n[PROP] ❌ Invalid option. Use 'on' or 'off'\n")
                    
                    elif subcmd == 'interval':
                        if len(parts) < 3:
                            print("\n[PROP] Usage: prop interval <seconds>\n")
                        else:
                            try:
                                interval = int(parts[2])
                                if interval < 30:
                                    print("\n[PROP] ❌ Minimum: 30 seconds\n")
                                else:
                                    self.auto_sync_interval = interval
                                    self._save_data()
                                    if self.sync_thread and self.sync_thread.is_alive():
                                        self._stop_auto_sync()
                                        self._start_auto_sync()
                                    print(f"\n[PROP] ✓ Interval: {interval}s\n")
                            except ValueError:
                                print("\n[PROP] ❌ Invalid number\n")
                    
                    elif subcmd == 'retry':
                        if len(parts) < 3:
                            print("\n[PROP] Usage: prop retry <on|off>\n")
                        else:
                            setting = parts[2].lower()
                            if setting in ['on', 'enable']:
                                self.auto_retry_failed = True
                                self._save_data()
                                print("\n[PROP] ✓ Auto-retry ENABLED\n")
                            elif setting in ['off', 'disable']:
                                self.auto_retry_failed = False
                                self._save_data()
                                print("\n[PROP] ✓ Auto-retry DISABLED\n")
                            else:
                                print("\n[PROP] ❌ Invalid option. Use 'on' or 'off'\n")
                    
                    elif subcmd == 'discover':
                        if len(parts) < 3:
                            print("\n[PROP] Usage: prop discover <on|off>\n")
                        else:
                            setting = parts[2].lower()
                            if setting in ['on', 'enable']:
                                self.show_discovery = True
                                self._save_data()
                                print("\n[PROP] ✓ Discovery alerts ON\n")
                            elif setting in ['off', 'disable']:
                                self.show_discovery = False
                                self._save_data()
                                print("\n[PROP] ✓ Discovery alerts OFF (silent)\n")
                            else:
                                print("\n[PROP] ❌ Invalid option. Use 'on' or 'off'\n")
                    
                    else:
                        print(f"\n[PROP] ❌ Unknown command: {subcmd}\n")
                        print("Type 'prop' for help\n")
        
        except KeyboardInterrupt:
            print("\n\n[PROP] Interrupted\n")
        except Exception as e:
            print(f"\n[PROP] Error: {e}\n")
            import traceback
            traceback.print_exc()
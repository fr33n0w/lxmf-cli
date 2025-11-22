"""
Remote Plugin Manager for LXMF-CLI
Manage plugins remotely via LXMF messages
Supports: list, enable/disable, reload, and execute plugin commands
"""
import time
import sys
import os
import importlib.util

class Plugin:
    def __init__(self, client):
        """Initialize the remote plugin manager"""
        self.client = client
        self.commands = ['rp']  # Local command to toggle remote management
        self.description = "Remote plugin management via LXMF messages"
        self.enabled = False  # Start disabled for security
        self.authorized_users = set()  # Hashes of authorized users
        
        print("Remote Plugin Manager loaded! Use 'rp on' to enable")
    
    def _send_reply(self, dest_hash, content):
        """Send a reply message silently"""
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        
        try:
            devnull = open(os.devnull, 'w', encoding='utf-8', errors='ignore')
            sys.stdout = devnull
            sys.stderr = devnull
            
            self.client.send_message(dest_hash, content)
            
        finally:
            devnull.close()
            sys.stdout = old_stdout
            sys.stderr = old_stderr
    
    def _is_authorized(self, source_hash):
        """Check if user is authorized (for now, check if in contacts)"""
        # Security: Only allow contacts or specifically authorized users
        contact_name = self.client.get_contact_name_by_hash(source_hash)
        is_contact = (contact_name != source_hash)
        
        # Also check authorized users set
        clean_hash = source_hash.replace(":", "").replace(" ", "").lower()
        is_authorized = clean_hash in self.authorized_users
        
        return is_contact or is_authorized
    
    def _format_plugin_list(self):
        """Generate formatted plugin list"""
        lines = ["📦 PLUGIN LIST\n" + "─" * 40]
        
        # Scan plugins directory
        available_plugins = {}
        plugins_dir = self.client.plugins_dir
        
        if os.path.exists(plugins_dir):
            for filename in os.listdir(plugins_dir):
                if filename.endswith('.py') and not filename.startswith('_'):
                    plugin_name = filename[:-3]
                    available_plugins[plugin_name] = {
                        'loaded': plugin_name in self.client.plugins,
                        'enabled': self.client.plugins_enabled.get(plugin_name, True),
                        'instance': self.client.plugins.get(plugin_name)
                    }
        
        if not available_plugins:
            lines.append("\nNo plugins found")
        else:
            for plugin_name, info in sorted(available_plugins.items()):
                # Determine status
                if info['loaded'] and info['enabled']:
                    status = "✓ LOADED"
                elif info['enabled'] and not info['loaded']:
                    status = "⚠ ENABLED (need reload)"
                else:
                    status = "✗ DISABLED"
                
                # Get description
                if info['instance']:
                    desc = getattr(info['instance'], 'description', 'No description')
                else:
                    desc = "Not loaded"
                
                lines.append(f"\n[{plugin_name}]")
                lines.append(f"  Status: {status}")
                lines.append(f"  Info: {desc}")
        
        lines.append("\n" + "─" * 40)
        lines.append("\n💡 Commands:")
        lines.append("/plist - List plugins")
        lines.append("/penable <name> - Enable plugin")
        lines.append("/pdisable <name> - Disable plugin")
        lines.append("/preload - Reload all plugins")
        lines.append("/pcom - List plugin commands")
        lines.append("/pcom <plugin> <cmd> - Execute command")
        
        return "\n".join(lines)
    
    def _format_plugin_commands(self):
        """Generate list of available plugin commands"""
        lines = ["🔧 PLUGIN COMMANDS\n" + "─" * 40]
        
        has_commands = False
        for plugin_name, plugin in sorted(self.client.plugins.items()):
            if hasattr(plugin, 'commands') and plugin.commands:
                has_commands = True
                lines.append(f"\n[{plugin_name}]")
                commands = ', '.join(plugin.commands)
                lines.append(f"  Commands: {commands}")
                
                if hasattr(plugin, 'description'):
                    lines.append(f"  Info: {plugin.description}")
        
        if not has_commands:
            lines.append("\nNo plugin commands available")
        else:
            lines.append("\n" + "─" * 40)
            lines.append("\n💡 Usage:")
            lines.append("/pcom <plugin> <command> [args]")
            lines.append("\nExample:")
            lines.append("/pcom echo on")
        
        return "\n".join(lines)
    
    def _handle_enable(self, plugin_name):
        """Enable a plugin"""
        plugins_dir = self.client.plugins_dir
        plugin_file = os.path.join(plugins_dir, f"{plugin_name}.py")
        
        if not os.path.exists(plugin_file):
            return f"❌ Plugin '{plugin_name}' not found"
        
        self.client.plugins_enabled[plugin_name] = True
        self.client.save_plugins_config()
        
        return f"✓ Plugin '{plugin_name}' enabled\n💡 Use /preload to activate"
    
    def _handle_disable(self, plugin_name):
        """Disable a plugin"""
        plugins_dir = self.client.plugins_dir
        plugin_file = os.path.join(plugins_dir, f"{plugin_name}.py")
        
        if not os.path.exists(plugin_file):
            return f"❌ Plugin '{plugin_name}' not found"
        
        self.client.plugins_enabled[plugin_name] = False
        self.client.save_plugins_config()
        
        return f"✓ Plugin '{plugin_name}' disabled\n💡 Use /preload to apply"
    
    def _handle_reload(self):
        """Reload all plugins"""
        try:
            # Clear current plugins
            old_count = len(self.client.plugins)
            self.client.plugins = {}
            
            # Reload
            self.client.load_plugins()
            
            new_count = len(self.client.plugins)
            
            return f"✓ Plugins reloaded\nBefore: {old_count} | After: {new_count}"
        except Exception as e:
            return f"❌ Reload failed: {str(e)}"
    
    def _handle_plugin_command(self, plugin_name, cmd_parts):
        """Execute a plugin command remotely"""
        if plugin_name not in self.client.plugins:
            return f"❌ Plugin '{plugin_name}' not loaded"
        
        plugin = self.client.plugins[plugin_name]
        
        if not hasattr(plugin, 'commands'):
            return f"❌ Plugin '{plugin_name}' has no commands"
        
        cmd = cmd_parts[0] if cmd_parts else ''
        
        if cmd not in plugin.commands:
            available = ', '.join(plugin.commands)
            return f"❌ Unknown command '{cmd}'\nAvailable: {available}"
        
        # Execute the command
        try:
            # Capture output
            from io import StringIO
            old_stdout = sys.stdout
            sys.stdout = StringIO()
            
            try:
                plugin.handle_command(cmd, cmd_parts)
                output = sys.stdout.getvalue()
            finally:
                sys.stdout = old_stdout
            
            if output.strip():
                return f"✓ Executed: {plugin_name} {' '.join(cmd_parts)}\n\n{output}"
            else:
                return f"✓ Executed: {plugin_name} {' '.join(cmd_parts)}"
            
        except Exception as e:
            return f"❌ Command failed: {str(e)}"
    
    def on_message(self, message, msg_data):
        """Handle incoming remote commands"""
        if not self.enabled:
            return False
        
        # Only process inbound messages
        if msg_data['direction'] == 'outbound':
            return False
        
        content = msg_data.get('content', '').strip()
        source_hash = msg_data['source_hash']
        
        # Check if message starts with command prefix
        if not content.startswith('/p'):
            return False
        
        # Authorization check
        if not self._is_authorized(source_hash):
            sender = self.client.format_contact_display_short(source_hash)
            print(f"\n[RP_MAN] Unauthorized access attempt from {sender}")
            print("> ", end="", flush=True)
            
            self._send_reply(source_hash, 
                "🔒 Access Denied\nYou are not authorized to manage plugins.")
            return True  # Suppress normal notification
        
        # Parse command
        parts = content.split()
        cmd = parts[0].lower()
        
        response = None
        
        try:
            if cmd == '/plist':
                response = self._format_plugin_list()
            
            elif cmd == '/pcom':
                if len(parts) == 1:
                    # List all plugin commands
                    response = self._format_plugin_commands()
                elif len(parts) >= 2:
                    # Execute plugin command: /pcom <plugin> <command> [args]
                    plugin_name = parts[1]
                    cmd_parts = parts[2:] if len(parts) > 2 else []
                    response = self._handle_plugin_command(plugin_name, cmd_parts)
                else:
                    response = "❌ Usage: /pcom or /pcom <plugin> <command>"
            
            elif cmd == '/penable':
                if len(parts) >= 2:
                    response = self._handle_enable(parts[1])
                else:
                    response = "❌ Usage: /penable <plugin_name>"
            
            elif cmd == '/pdisable':
                if len(parts) >= 2:
                    response = self._handle_disable(parts[1])
                else:
                    response = "❌ Usage: /pdisable <plugin_name>"
            
            elif cmd == '/preload':
                response = self._handle_reload()
            
            else:
                response = "❌ Unknown command\n\nAvailable:\n/plist\n/pcom\n/penable <name>\n/pdisable <name>\n/preload"
        
        except Exception as e:
            response = f"❌ Error: {str(e)}"
        
        # Send response
        if response:
            time.sleep(0.3)
            self._send_reply(source_hash, response)
            
            sender = self.client.format_contact_display_short(source_hash)
            print(f"\n[RP_MAN] Handled command '{cmd}' from {sender}")
            print("> ", end="", flush=True)
        
        # Suppress normal notification (we handled it)
        return True
    
    def handle_command(self, cmd, parts):
        """Handle local 'rp' command to toggle remote management"""
        if cmd == 'rp':
            if len(parts) < 2:
                # Show status
                status = "ENABLED ✓" if self.enabled else "DISABLED ✗"
                print(f"\n{'='*60}")
                print(f"Remote Plugin Manager: {status}")
                print(f"{'='*60}")
                print("\nAllows authorized users to manage plugins via LXMF")
                print("\nRemote Commands:")
                print("  /plist - List all plugins")
                print("  /pcom - List plugin commands")
                print("  /pcom <plugin> <cmd> - Execute command")
                print("  /penable <name> - Enable plugin")
                print("  /pdisable <name> - Disable plugin")
                print("  /preload - Reload all plugins")
                print("\nLocal Commands:")
                print("  rp on/off - Toggle remote management")
                print("  rp auth <hash> - Authorize user")
                print("  rp deauth <hash> - Deauthorize user")
                print(f"{'='*60}\n")
            
            else:
                subcmd = parts[1].lower()
                
                if subcmd in ['on', 'enable', 'start']:
                    self.enabled = True
                    print("✓ Remote Plugin Manager ENABLED")
                    print("⚠️  Contacts can now manage plugins remotely")
                    print("💡 Send '/plist' in a message to see commands")
                
                elif subcmd in ['off', 'disable', 'stop']:
                    self.enabled = False
                    print("✓ Remote Plugin Manager DISABLED")
                
                elif subcmd == 'auth' and len(parts) >= 3:
                    # Authorize a specific user
                    hash_str = parts[2].replace(":", "").replace(" ", "").lower()
                    self.authorized_users.add(hash_str)
                    print(f"✓ Authorized: {hash_str[:16]}...")
                
                elif subcmd == 'deauth' and len(parts) >= 3:
                    # Deauthorize a user
                    hash_str = parts[2].replace(":", "").replace(" ", "").lower()
                    if hash_str in self.authorized_users:
                        self.authorized_users.remove(hash_str)
                        print(f"✓ Deauthorized: {hash_str[:16]}...")
                    else:
                        print("❌ Not in authorized list")
                
                elif subcmd in ['status', 'info']:
                    status = "ENABLED ✓" if self.enabled else "DISABLED ✗"
                    print(f"\nRemote Plugin Manager: {status}")
                    if self.authorized_users:
                        print(f"Authorized users: {len(self.authorized_users)}\n")
                    else:
                        print("No specifically authorized users (contacts only)\n")
                
                else:
                    print(f"Unknown subcommand: {subcmd}")
                    print("Use: rp [on|off|auth|deauth|status]")
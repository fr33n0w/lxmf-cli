"""
Plugin Helper - Documentation and Management for LXMF Client Plugins

Lists all loaded plugins, their commands, descriptions, and usage.
Supports both local queries and remote requests (if enabled).

Commands:
  plugin-help [plugin_name]  - Show help for all plugins or specific plugin
  plugin-list                - List all loaded plugins
  plugin-info <name>         - Detailed info about a specific plugin
  plugin-remote-toggle       - Enable/disable remote plugin help requests
"""

import os
import json
import inspect

class Plugin:
    def __init__(self, client):
        self.client = client
        self.description = "Plugin documentation and help system"
        self.commands = ['plugin-help', 'plugin-list', 'plugin-info', 'plugin-remote-toggle']
        
        # Configuration
        self.config_file = os.path.join(client.storage_path, "plugin_helper_config.json")
        self.remote_help_enabled = False
        
        self.load_config()
    
    def on_message(self, message, msg_data):
        """Handle remote plugin-help requests"""
        content = msg_data.get('content', '')
        
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='replace')
        
        content_lower = content.strip().lower()
        
        # Check for plugin-help requests
        if content_lower.startswith('plugin-help') or content_lower == 'plugins?' or content_lower == 'help plugins':
            if self.remote_help_enabled:
                source_hash = msg_data.get('source_hash')
                
                print(f"\n[📚 Plugin Help] Request from {self.client.format_contact_display_short(source_hash)}")
                
                # Parse which plugin they want help for
                parts = content.strip().split(maxsplit=1)
                plugin_name = parts[1] if len(parts) > 1 else None
                
                # Generate help response
                help_text = self._generate_remote_help(plugin_name)
                
                # Send response
                self.client.send_message(
                    source_hash,
                    help_text,
                    title="📚 Plugin Help"
                )
                
                print(f"[📚 Plugin Help] Response sent")
                print("> ", end="", flush=True)
                
                return False
            else:
                source_hash = msg_data.get('source_hash')
                print(f"\n[📚 Plugin Help] Request denied from {self.client.format_contact_display_short(source_hash)} (remote disabled)")
                print("> ", end="", flush=True)
        
        return False
    
    def handle_command(self, cmd, parts):
        """Handle plugin-help commands"""
        if cmd == 'plugin-help':
            plugin_name = parts[1] if len(parts) > 1 else None
            self._show_plugin_help(plugin_name)
        
        elif cmd == 'plugin-list':
            self._list_plugins()
        
        elif cmd == 'plugin-info':
            if len(parts) < 2:
                print("\nUsage: plugin-info <plugin_name>")
                print("Example: plugin-info share_contact")
                return
            self._show_plugin_info(parts[1])
        
        elif cmd == 'plugin-remote-toggle':
            self._toggle_remote_help()
    
    def _show_plugin_help(self, plugin_name=None):
        """Show comprehensive plugin help"""
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 90)
        except:
            width = 90
        
        if plugin_name:
            # Show help for specific plugin
            if plugin_name in self.client.plugins:
                self._show_plugin_info(plugin_name)
            else:
                print(f"\n❌ Plugin '{plugin_name}' not found")
                print("Use 'plugin-list' to see available plugins\n")
        else:
            # Show help for all plugins
            print(f"\n{'='*width}")
            print("📚 LXMF CLIENT - PLUGIN HELP")
            print(f"{'='*width}")
            
            if not self.client.plugins:
                print("\n⚠️  No plugins loaded")
                print("Place plugin files in: ./lxmf_client_storage/plugins/")
                print(f"{'='*width}\n")
                return
            
            print(f"\n✅ {len(self.client.plugins)} plugins loaded\n")
            
            # Group by category (if we can infer it)
            for plugin_name in sorted(self.client.plugins.keys()):
                plugin = self.client.plugins[plugin_name]
                
                # Get description
                description = getattr(plugin, 'description', 'No description available')
                
                # Get commands
                commands = getattr(plugin, 'commands', [])
                
                # Print plugin header
                print(f"📦 {plugin_name}")
                print(f"   {description}")
                
                if commands:
                    print(f"   Commands: {', '.join(commands)}")
                
                print()
            
            print(f"{'='*width}")
            print("\n💡 Tips:")
            print("   • plugin-help <name>      - Detailed help for specific plugin")
            print("   • plugin-info <name>      - Technical info about plugin")
            print("   • plugin-list             - Compact plugin list")
            print("   • plugin-remote-toggle    - Enable/disable remote help")
            
            # Show remote status
            status = "✅ ENABLED" if self.remote_help_enabled else "❌ DISABLED"
            print(f"\n🌐 Remote Help: {status}")
            
            print(f"{'='*width}\n")
    
    def _show_plugin_info(self, plugin_name):
        """Show detailed information about a specific plugin"""
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 80)
        except:
            width = 80
        
        if plugin_name not in self.client.plugins:
            print(f"\n❌ Plugin '{plugin_name}' not found")
            print("Use 'plugin-list' to see available plugins\n")
            return
        
        plugin = self.client.plugins[plugin_name]
        
        print(f"\n{'='*width}")
        print(f"📦 PLUGIN: {plugin_name}")
        print(f"{'='*width}")
        
        # Description
        description = getattr(plugin, 'description', 'No description available')
        print(f"\n📝 Description:")
        print(f"   {description}")
        
        # Commands
        commands = getattr(plugin, 'commands', [])
        if commands:
            print(f"\n⚙️  Commands:")
            for cmd in commands:
                print(f"   • {cmd}")
        else:
            print(f"\n⚠️  No commands registered")
        
        # Check if plugin has message handler
        has_message_handler = hasattr(plugin, 'on_message')
        if has_message_handler:
            print(f"\n📨 Handles incoming messages: ✅ Yes")
            print(f"   This plugin can process received messages")
        else:
            print(f"\n📨 Handles incoming messages: ❌ No")
        
        # Check for documentation
        if hasattr(plugin, '__doc__') and plugin.__doc__:
            doc = plugin.__doc__.strip()
            if doc:
                print(f"\n📖 Documentation:")
                # Print first few lines of docstring
                doc_lines = doc.split('\n')[:10]
                for line in doc_lines:
                    print(f"   {line}")
                if len(plugin.__doc__.split('\n')) > 10:
                    print("   ...")
        
        # Check for custom help method
        if hasattr(plugin, 'show_help') or hasattr(plugin, 'help'):
            print(f"\n💡 For detailed usage, try the plugin's help command")
        
        # Try to find plugin file
        try:
            plugin_file = inspect.getfile(plugin.__class__)
            print(f"\n📁 File location:")
            print(f"   {plugin_file}")
        except:
            pass
        
        print(f"\n{'='*width}\n")
    
    def _list_plugins(self):
        """Show compact list of all plugins"""
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 80)
        except:
            width = 80
        
        print(f"\n{'='*width}")
        print("📦 LOADED PLUGINS")
        print(f"{'='*width}")
        
        if not self.client.plugins:
            print("\n⚠️  No plugins loaded\n")
            return
        
        print(f"\n{'Plugin':<25} {'Commands':<10} {'Description'}")
        print(f"{'-'*25} {'-'*10} {'-'*35}")
        
        for plugin_name in sorted(self.client.plugins.keys()):
            plugin = self.client.plugins[plugin_name]
            
            # Get info
            commands = getattr(plugin, 'commands', [])
            cmd_count = len(commands)
            description = getattr(plugin, 'description', 'No description')
            
            # Truncate for display
            name_display = plugin_name[:23] + ".." if len(plugin_name) > 25 else plugin_name
            desc_display = description[:33] + ".." if len(description) > 35 else description
            
            print(f"{name_display:<25} {cmd_count:<10} {desc_display}")
        
        print(f"\n{'='*width}")
        print(f"💡 Use 'plugin-help <name>' for details\n")
    
    def _generate_remote_help(self, plugin_name=None):
        """Generate help text for remote requests"""
        if plugin_name:
            # Specific plugin help
            if plugin_name in self.client.plugins:
                plugin = self.client.plugins[plugin_name]
                
                msg = "╔══════════════════════════════════╗\n"
                msg += f"║   PLUGIN: {plugin_name[:20]:<20} ║\n"
                msg += "╚══════════════════════════════════╝\n\n"
                
                description = getattr(plugin, 'description', 'No description')
                msg += f"📝 {description}\n\n"
                
                commands = getattr(plugin, 'commands', [])
                if commands:
                    msg += "⚙️  COMMANDS:\n"
                    for cmd in commands:
                        msg += f"   • {cmd}\n"
                else:
                    msg += "⚠️  No commands available\n"
                
                if hasattr(plugin, 'on_message'):
                    msg += "\n📨 Handles incoming messages\n"
                
                return msg
            else:
                return f"❌ Plugin '{plugin_name}' not found\n\nUse 'plugin-help' to see all plugins"
        
        else:
            # All plugins overview
            msg = "╔══════════════════════════════════╗\n"
            msg += "║     AVAILABLE PLUGINS            ║\n"
            msg += "╚══════════════════════════════════╝\n\n"
            
            if not self.client.plugins:
                msg += "⚠️  No plugins loaded\n"
                return msg
            
            msg += f"✅ {len(self.client.plugins)} plugins available:\n\n"
            
            for plugin_name in sorted(self.client.plugins.keys()):
                plugin = self.client.plugins[plugin_name]
                description = getattr(plugin, 'description', 'No description')
                commands = getattr(plugin, 'commands', [])
                
                msg += f"📦 {plugin_name}\n"
                msg += f"   {description}\n"
                if commands:
                    msg += f"   Commands: {', '.join(commands[:3])}"
                    if len(commands) > 3:
                        msg += f" +{len(commands)-3} more"
                    msg += "\n"
                msg += "\n"
            
            msg += "────────────────────────────────────\n"
            msg += "💡 Request specific plugin help:\n"
            msg += "   plugin-help <name>\n"
            
            return msg
    
    def _toggle_remote_help(self):
        """Toggle remote plugin help requests"""
        self.remote_help_enabled = not self.remote_help_enabled
        self.save_config()
        
        status_icon = "✅" if self.remote_help_enabled else "❌"
        status = "ENABLED" if self.remote_help_enabled else "DISABLED"
        
        print(f"\n{status_icon} Remote Plugin Help: {status}")
        
        if self.remote_help_enabled:
            print("   Remote peers can request plugin information")
            print("   They can send 'plugin-help' or 'plugin-help <name>'")
        else:
            print("   Remote help requests will be ignored")
        
        print()
    
    def load_config(self):
        """Load configuration"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.remote_help_enabled = config.get('remote_help_enabled', False)
            except Exception as e:
                print(f"Error loading plugin_helper config: {e}")
    
    def save_config(self):
        """Save configuration"""
        try:
            config = {
                'remote_help_enabled': self.remote_help_enabled
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error saving plugin_helper config: {e}")

if __name__ == '__main__':
    print("This is a plugin for LXMF Client")
    print("Place in: ./lxmf_client_storage/plugins/")
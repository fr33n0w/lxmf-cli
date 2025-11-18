"""
Plugin Status - Real-time status monitoring for all loaded plugins

Shows the current state and configuration of all loaded plugins.
Displays which plugins are active, their settings, and runtime status.

Commands:
  plugin-status          - Show status of all plugins
  plugin-status <name>   - Show detailed status for specific plugin
"""

import os
import time

class Plugin:
    def __init__(self, client):
        self.client = client
        self.description = "Monitor plugin status and configuration"
        self.commands = ['plugin-status', 'pluginstatus', 'pstatus']
    
    def handle_command(self, cmd, parts):
        """Handle plugin-status commands"""
        plugin_name = parts[1] if len(parts) > 1 else None
        
        if plugin_name:
            self._show_plugin_status(plugin_name)
        else:
            self._show_all_status()
    
    def _show_all_status(self):
        """Show status overview of all plugins"""
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 90)
        except:
            width = 90
        
        print(f"\n{'='*width}")
        print("📊 PLUGIN STATUS OVERVIEW")
        print(f"{'='*width}")
        
        if not self.client.plugins:
            print("\n⚠️  No plugins loaded\n")
            return
        
        total_plugins = len(self.client.plugins)
        enabled_count = 0
        
        # Count enabled plugins
        for plugin_name in self.client.plugins:
            if self.client.plugins_enabled.get(plugin_name, True):
                enabled_count += 1
        
        print(f"\n📦 Total Plugins: {total_plugins}")
        print(f"✅ Enabled: {enabled_count}")
        print(f"❌ Disabled: {total_plugins - enabled_count}")
        print()
        
        # Show each plugin's status
        for plugin_name in sorted(self.client.plugins.keys()):
            plugin = self.client.plugins[plugin_name]
            is_enabled = self.client.plugins_enabled.get(plugin_name, True)
            
            # Status icon
            status_icon = "✅" if is_enabled else "❌"
            
            # Get basic info
            description = getattr(plugin, 'description', 'No description')
            commands = getattr(plugin, 'commands', [])
            
            # Plugin header
            print(f"\n{status_icon} {plugin_name}")
            print(f"   {description}")
            
            if commands:
                cmd_display = ', '.join(commands[:4])
                if len(commands) > 4:
                    cmd_display += f" +{len(commands)-4} more"
                print(f"   Commands: {cmd_display}")
            
            # Get runtime status (the key feature!)
            runtime_status = self._get_runtime_status(plugin_name, plugin)
            if runtime_status:
                for line in runtime_status:
                    print(f"   {line}")
        
        print(f"\n{'='*width}")
        print("\n💡 Use 'plugin-status <name>' for detailed status")
        print()
    
    def _show_plugin_status(self, plugin_name):
        """Show detailed status for a specific plugin"""
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 80)
        except:
            width = 80
        
        if plugin_name not in self.client.plugins:
            print(f"\n❌ Plugin '{plugin_name}' not found")
            print("Use 'plugin-status' to see all plugins\n")
            return
        
        plugin = self.client.plugins[plugin_name]
        is_enabled = self.client.plugins_enabled.get(plugin_name, True)
        
        print(f"\n{'='*width}")
        print(f"📊 PLUGIN STATUS: {plugin_name}")
        print(f"{'='*width}")
        
        # Basic status
        status_icon = "✅" if is_enabled else "❌"
        status_text = "ENABLED" if is_enabled else "DISABLED"
        print(f"\n{status_icon} Status: {status_text}")
        
        # Description
        description = getattr(plugin, 'description', 'No description available')
        print(f"\n📝 Description:")
        print(f"   {description}")
        
        # Commands
        commands = getattr(plugin, 'commands', [])
        if commands:
            print(f"\n⚙️  Available Commands:")
            for cmd in commands:
                print(f"   • {cmd}")
        
        # Message handler
        has_message_handler = hasattr(plugin, 'on_message')
        print(f"\n📨 Message Handler: {'✅ Active' if has_message_handler else '❌ None'}")
        
        # Runtime status (detailed view)
        print(f"\n🔧 Current State:")
        runtime_status = self._get_runtime_status(plugin_name, plugin)
        
        if runtime_status:
            for line in runtime_status:
                print(f"   {line}")
        else:
            print(f"   No runtime state available")
        
        # Plugin-specific configuration
        config_info = self._get_plugin_config(plugin_name, plugin)
        if config_info:
            print(f"\n⚙️  Configuration:")
            for key, value in config_info.items():
                print(f"   {key}: {value}")
        
        # Plugin uptime (if we can determine it)
        if hasattr(plugin, 'client_start_time'):
            uptime = time.time() - plugin.client_start_time
            print(f"\n⏱️  Uptime: {self._format_duration(uptime)}")
        
        print(f"\n{'='*width}\n")
    
    def _get_runtime_status(self, plugin_name, plugin):
        """Get the current runtime status of a plugin"""
        status_lines = []
        
        # ============ AWAY BOT ============
        if plugin_name == 'away_bot':
            # Try multiple attribute names for compatibility
            away_enabled = (
                getattr(plugin, 'away_enabled', None) or
                getattr(plugin, 'enabled', None) or
                getattr(plugin, 'is_away', None)
            )
            
            if away_enabled is not None:
                if away_enabled:
                    status_lines.append("🟢 Status: AWAY MODE ACTIVE")
                    
                    # Get away message
                    away_msg = (
                        getattr(plugin, 'away_message', None) or
                        getattr(plugin, 'message', None)
                    )
                    if away_msg:
                        msg = str(away_msg)
                        if len(msg) > 45:
                            msg = msg[:42] + "..."
                        status_lines.append(f"💬 Message: \"{msg}\"")
                    
                    # Get away time
                    away_since = (
                        getattr(plugin, 'away_since', None) or
                        getattr(plugin, 'start_time', None)
                    )
                    if away_since:
                        away_time = time.time() - away_since
                        status_lines.append(f"⏱️  Away for: {self._format_duration(away_time)}")
                else:
                    status_lines.append("⚪ Status: NOT AWAY (ready to activate)")
            else:
                status_lines.append("⚠️  Status: Unknown (check plugin)")
            
            return status_lines
        
        # ============ ECHO BOT ============
        if plugin_name == 'echo_bot':
            # Try multiple attribute names
            echo_enabled = (
                getattr(plugin, 'echo_enabled', None) or
                getattr(plugin, 'enabled', None) or
                getattr(plugin, 'active', None)
            )
            
            if echo_enabled is not None:
                if echo_enabled:
                    status_lines.append("🟢 Status: ECHO ACTIVE")
                    status_lines.append("📢 Auto-replying to all messages")
                    
                    echo_count = getattr(plugin, 'echo_count', None)
                    if echo_count is not None:
                        status_lines.append(f"📊 Echoed: {echo_count} messages")
                else:
                    status_lines.append("⚪ Status: ECHO DISABLED (ready to activate)")
            else:
                # If no enabled flag found, assume it's off
                status_lines.append("⚪ Status: ECHO DISABLED (ready to activate)")
            
            return status_lines
        
        # ============ KEYWORD ALERT ============
        if plugin_name == 'keyword_alert':
            keywords = (
                getattr(plugin, 'keywords', None) or
                getattr(plugin, 'keyword_list', None) or
                []
            )
            
            if isinstance(keywords, (list, set)) and len(keywords) > 0:
                status_lines.append(f"🟢 Status: MONITORING {len(keywords)} keywords")
                # Show keywords
                keyword_list = list(keywords)[:5]
                keyword_display = ', '.join(f'"{k}"' for k in keyword_list)
                if len(keywords) > 5:
                    keyword_display += f" +{len(keywords)-5} more"
                status_lines.append(f"🔍 Keywords: {keyword_display}")
                
                # Show alert count if available
                alert_count = getattr(plugin, 'alert_count', None)
                if alert_count is not None:
                    status_lines.append(f"🚨 Alerts: {alert_count} triggered")
            else:
                status_lines.append("⚪ Status: NO KEYWORDS SET")
                status_lines.append("💡 Use 'keyword add <word>' to start monitoring")
            
            return status_lines
        
        # ============ SYS_INFO ============
        if plugin_name == 'sys_info':
            remote_enabled = getattr(plugin, 'remote_enabled', None)
            if remote_enabled is not None:
                if remote_enabled:
                    status_lines.append("🟢 Remote Access: ENABLED")
                else:
                    status_lines.append("⚪ Remote Access: DISABLED")
            
            share_config = getattr(plugin, 'share_config', None)
            if share_config:
                enabled_items = sum(1 for v in share_config.values() if v)
                total_items = len(share_config)
                status_lines.append(f"📊 Sharing: {enabled_items}/{total_items} data items")
            
            stats = getattr(plugin, 'stats', {})
            if 'messages_received' in stats:
                status_lines.append(f"📬 Tracked: {stats['messages_received']} messages")
            
            return status_lines
        
        # ============ PLUGIN HELPER ============
        if plugin_name == 'plugin_helper':
            remote_help_enabled = getattr(plugin, 'remote_help_enabled', None)
            if remote_help_enabled is not None:
                if remote_help_enabled:
                    status_lines.append("🟢 Remote Help: ENABLED")
                    status_lines.append("📚 Peers can query plugin info")
                else:
                    status_lines.append("⚪ Remote Help: DISABLED")
            return status_lines
        
        # ============ SHARE CONTACT ============
        if plugin_name == 'share_contact':
            status_lines.append("📇 Ready to share/import contacts")
            if hasattr(plugin, 'contact_card_pattern'):
                status_lines.append("✅ Auto-detection: Active")
            return status_lines
        
        # ============ MASS MSG ============
        if plugin_name == 'mass_msg':
            contact_count = len(self.client.contacts)
            status_lines.append(f"📢 Ready to broadcast to {contact_count} contacts")
            return status_lines
        
        # ============ AUTO REPLY ============
        if plugin_name == 'auto_reply':
            auto_reply_enabled = getattr(plugin, 'auto_reply_enabled', None)
            if auto_reply_enabled is not None:
                if auto_reply_enabled:
                    status_lines.append("🟢 Auto-Reply: ACTIVE")
                    
                    reply_message = getattr(plugin, 'reply_message', None)
                    if reply_message:
                        msg = str(reply_message)[:45]
                        if len(str(reply_message)) > 45:
                            msg += "..."
                        status_lines.append(f"💬 Message: \"{msg}\"")
                    
                    reply_count = getattr(plugin, 'reply_count', None)
                    if reply_count is not None:
                        status_lines.append(f"📊 Sent: {reply_count} auto-replies")
                else:
                    status_lines.append("⚪ Auto-Reply: DISABLED")
            return status_lines
        
        # ============ SCHEDULED MESSAGES ============
        if plugin_name == 'scheduled_messages':
            scheduled_msgs = getattr(plugin, 'scheduled_msgs', [])
            if scheduled_msgs and len(scheduled_msgs) > 0:
                count = len(scheduled_msgs)
                status_lines.append(f"🟢 Status: {count} message(s) scheduled")
                # Show next scheduled message
                next_msg = min(scheduled_msgs, key=lambda m: m.get('time', float('inf')))
                next_time = next_msg.get('time', 0)
                time_until = next_time - time.time()
                if time_until > 0:
                    status_lines.append(f"⏰ Next: in {self._format_duration(time_until)}")
            else:
                status_lines.append("⚪ Status: No scheduled messages")
            return status_lines
        
        # ============ NODE MONITOR ============
        if plugin_name == 'node_monitor':
            monitoring_enabled = getattr(plugin, 'monitoring_enabled', None)
            if monitoring_enabled is not None:
                if monitoring_enabled:
                    status_lines.append("🟢 Monitoring: ACTIVE")
                    
                    monitored_nodes = getattr(plugin, 'monitored_nodes', [])
                    if monitored_nodes:
                        count = len(monitored_nodes)
                        status_lines.append(f"📡 Watching: {count} nodes")
                    
                    offline_nodes = getattr(plugin, 'offline_nodes', [])
                    if offline_nodes and len(offline_nodes) > 0:
                        offline = len(offline_nodes)
                        status_lines.append(f"⚠️  Offline: {offline} nodes")
                else:
                    status_lines.append("⚪ Monitoring: DISABLED")
            return status_lines
        
        # Generic fallback - check for common patterns
        return self._get_generic_status(plugin)
    
    def _get_generic_status(self, plugin):
        """Generic status detection for plugins"""
        status_lines = []
        
        # Check for enabled/disabled flags with multiple possible names
        enabled_attrs = [
            'enabled', 'active', 'running', 'monitoring',
            'is_enabled', 'is_active', 'is_running'
        ]
        
        for attr in enabled_attrs:
            if hasattr(plugin, attr):
                value = getattr(plugin, attr)
                if isinstance(value, bool):
                    icon = "🟢" if value else "⚪"
                    name = attr.replace('_', ' ').replace('is ', '').title()
                    status = "ACTIVE" if value else "DISABLED"
                    status_lines.append(f"{icon} {name}: {status}")
                    return status_lines
        
        return status_lines
    
    def _get_plugin_config(self, plugin_name, plugin):
        """Extract configuration information from a plugin"""
        config = {}
        
        # Common configuration attributes
        config_attrs = [
            ('config_file', 'Config File'),
            ('announce_interval', 'Announce Interval'),
            ('stamp_cost', 'Stamp Cost'),
            ('blacklist', 'Blacklist Size'),
            ('display_name_cache', 'Cache Size'),
        ]
        
        for attr_name, display_name in config_attrs:
            if hasattr(plugin, attr_name):
                value = getattr(plugin, attr_name)
                
                if attr_name == 'config_file':
                    if os.path.exists(value):
                        config[display_name] = "✅ Found"
                    else:
                        config[display_name] = "❌ Not found"
                
                elif attr_name == 'blacklist':
                    if isinstance(value, (list, set)) and len(value) > 0:
                        config[display_name] = f"{len(value)} entries"
                
                elif attr_name == 'display_name_cache':
                    if isinstance(value, dict) and len(value) > 0:
                        config[display_name] = f"{len(value)} names"
                
                elif isinstance(value, (int, float)):
                    config[display_name] = str(value)
        
        return config
    
    def _format_duration(self, seconds):
        """Format duration to human readable"""
        if seconds < 0:
            return "0s"
        
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs}s")
        
        return ' '.join(parts)

if __name__ == '__main__':
    print("This is a plugin for LXMF Client")
    print("Place in: ./lxmf_client_storage/plugins/")
"""
Command Logger Plugin for LXMF-CLI
Logs all messages and activity with advanced viewing and filtering
"""
import os
import json
from datetime import datetime

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['viewlog', 'clearlog', 'log-filter', 'log-export', 'log-search']
        self.description = "Advanced activity logging and analysis"
        self.log_file = os.path.join(client.storage_path, "activity_log.json")
        self.log_entries = []
        self.load_log()
        print(f"✓ Logger loaded! Log: {self.log_file}")
    
    def load_log(self):
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r') as f:
                    self.log_entries = json.load(f)
            except:
                self.log_entries = []
    
    def save_log(self):
        try:
            # Keep only last 1000 entries
            with open(self.log_file, 'w') as f:
                json.dump(self.log_entries[-1000:], f, indent=2)
        except Exception as e:
            print(f"[LOG ERROR] {e}")
    
    def log_activity(self, activity_type, data):
        entry = {
            'timestamp': datetime.now().isoformat(),
            'type': activity_type,
            'data': data
        }
        self.log_entries.append(entry)
        self.save_log()
    
    def on_message(self, message, msg_data):
        # Log incoming message with more detail
        self.log_activity('message_received', {
            'from': msg_data.get('source_hash', 'unknown'),
            'display_name': msg_data.get('display_name', 'unknown'),
            'content_preview': str(msg_data.get('content', ''))[:50],
            'content_length': len(str(msg_data.get('content', ''))),
            'title': msg_data.get('title', ''),
            'has_title': bool(msg_data.get('title'))
        })
        return False
    
    def handle_command(self, cmd, parts):
        if cmd == 'viewlog':
            limit = 20
            log_type = None
            contact_filter = None
            
            # Parse arguments: viewlog [limit] [type] [contact]
            if len(parts) >= 2:
                try:
                    limit = int(parts[1])
                except ValueError:
                    # Not a number, might be a type filter
                    log_type = parts[1]
            
            if len(parts) >= 3:
                if parts[2] not in ['message_received', 'message_sent']:
                    contact_filter = parts[2]
                else:
                    log_type = parts[2]
            
            self._show_log(limit, log_type, contact_filter)
        
        elif cmd == 'log-filter':
            if len(parts) < 2:
                print("\n📋 Log Filtering")
                print("="*60)
                print("Usage: log-filter <type> [limit]")
                print("\nAvailable types:")
                print("  • message_received - Incoming messages")
                print("  • message_sent     - Outgoing messages")
                print("  • all              - All activity")
                print("\nExamples:")
                print("  log-filter message_received 50")
                print("  log-filter message_sent")
                print("="*60)
                print()
                return
            
            log_type = parts[1]
            limit = int(parts[2]) if len(parts) >= 3 else 20
            self._show_log(limit, log_type, None)
        
        elif cmd == 'log-search':
            if len(parts) < 2:
                print("\nUsage: log-search <text>")
                print("Search for text in log messages")
                return
            
            search_term = ' '.join(parts[1:]).lower()
            self._search_log(search_term)
        
        elif cmd == 'log-export':
            if len(parts) < 2:
                print("\nUsage: log-export <filename.txt>")
                print("Export log to text file")
                return
            
            filename = parts[1]
            self._export_log(filename)
        
        elif cmd == 'clearlog':
            confirm = input("Clear entire activity log? [y/N]: ").strip().lower()
            if confirm == 'y':
                count = len(self.log_entries)
                self.log_entries = []
                self.save_log()
                self.client._print_success(f"Cleared {count} log entries")
            else:
                print("Cancelled")
    
    def _show_log(self, limit, log_type=None, contact_filter=None):
        """Display log entries with formatting"""
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 90)
        except:
            width = 90
        
        # Filter entries
        filtered = self.log_entries
        
        if log_type and log_type != 'all':
            filtered = [e for e in filtered if e['type'] == log_type]
        
        if contact_filter:
            filtered = [e for e in filtered 
                       if contact_filter.lower() in e.get('data', {}).get('display_name', '').lower()
                       or contact_filter.lower() in e.get('data', {}).get('from', '').lower()]
        
        if not filtered:
            print("\n📋 No matching log entries\n")
            return
        
        # Get last N entries
        entries_to_show = filtered[-limit:]
        
        print(f"\n{'='*width}")
        print(f"📋 ACTIVITY LOG")
        if log_type:
            print(f"   Filter: {log_type}")
        if contact_filter:
            print(f"   Contact: {contact_filter}")
        print(f"   Showing: {len(entries_to_show)} of {len(filtered)} entries")
        print(f"{'='*width}\n")
        
        for entry in entries_to_show:
            self._format_log_entry(entry)
        
        print(f"{'='*width}")
        print(f"\n💡 Total in log: {len(self.log_entries)} entries")
        print(f"💡 Commands: log-filter, log-search, log-export")
        print()
    
    def _format_log_entry(self, entry):
        """Format a single log entry for display"""
        timestamp = entry.get('timestamp', '')
        activity_type = entry.get('type', 'unknown')
        data = entry.get('data', {})
        
        # Format timestamp
        try:
            dt = datetime.fromisoformat(timestamp)
            time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            time_str = timestamp
        
        # Format based on type
        if activity_type == 'message_received':
            from_hash = data.get('from', 'unknown')
            display_name = data.get('display_name', 'Unknown')
            
            # Try to resolve to contact name
            contact_name = self.client.format_contact_display_short(from_hash)
            
            # Get title and content preview
            title = data.get('title', '')
            content_preview = data.get('content_preview', '')
            content_length = data.get('content_length', 0)
            
            print(f"📨 {time_str}")
            print(f"   From: {contact_name}")
            
            if title:
                print(f"   Title: {title}")
            
            if content_preview:
                print(f"   Preview: {content_preview}")
                if content_length > 50:
                    print(f"   Length: {content_length} chars")
            else:
                print(f"   Content: {content_length} chars")
            
            print()
        
        elif activity_type == 'message_sent':
            to_hash = data.get('to', 'unknown')
            display_name = data.get('display_name', 'Unknown')
            
            contact_name = self.client.format_contact_display_short(to_hash)
            
            title = data.get('title', '')
            content_preview = data.get('content_preview', '')
            
            print(f"📤 {time_str}")
            print(f"   To: {contact_name}")
            
            if title:
                print(f"   Title: {title}")
            
            if content_preview:
                print(f"   Preview: {content_preview}")
            
            print()
        
        else:
            # Generic format
            print(f"📋 {time_str}")
            print(f"   Type: {activity_type}")
            print(f"   Data: {data}")
            print()
    
    def _search_log(self, search_term):
        """Search for text in log entries"""
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 80)
        except:
            width = 80
        
        results = []
        
        for entry in self.log_entries:
            data = entry.get('data', {})
            
            # Search in various fields
            searchable_text = ' '.join([
                str(data.get('display_name', '')),
                str(data.get('title', '')),
                str(data.get('content_preview', '')),
                str(data.get('from', '')),
                str(data.get('to', ''))
            ]).lower()
            
            if search_term in searchable_text:
                results.append(entry)
        
        if not results:
            print(f"\n🔍 No results found for: '{search_term}'\n")
            return
        
        print(f"\n{'='*width}")
        print(f"🔍 SEARCH RESULTS: '{search_term}'")
        print(f"   Found: {len(results)} matches")
        print(f"{'='*width}\n")
        
        for entry in results[-20:]:  # Show last 20 matches
            self._format_log_entry(entry)
        
        if len(results) > 20:
            print(f"💡 Showing last 20 of {len(results)} results")
        
        print(f"{'='*width}\n")
    
    def _export_log(self, filename):
        """Export log to text file"""
        try:
            export_path = os.path.join(self.client.storage_path, filename)
            
            with open(export_path, 'w', encoding='utf-8') as f:
                f.write("="*80 + "\n")
                f.write("LXMF CLIENT ACTIVITY LOG\n")
                f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total entries: {len(self.log_entries)}\n")
                f.write("="*80 + "\n\n")
                
                for entry in self.log_entries:
                    timestamp = entry.get('timestamp', '')
                    activity_type = entry.get('type', 'unknown')
                    data = entry.get('data', {})
                    
                    try:
                        dt = datetime.fromisoformat(timestamp)
                        time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        time_str = timestamp
                    
                    f.write(f"{time_str} | {activity_type}\n")
                    
                    if activity_type == 'message_received':
                        f.write(f"  From: {data.get('display_name', 'Unknown')}\n")
                        if data.get('title'):
                            f.write(f"  Title: {data.get('title')}\n")
                        if data.get('content_preview'):
                            f.write(f"  Preview: {data.get('content_preview')}\n")
                    elif activity_type == 'message_sent':
                        f.write(f"  To: {data.get('display_name', 'Unknown')}\n")
                        if data.get('title'):
                            f.write(f"  Title: {data.get('title')}\n")
                    else:
                        f.write(f"  Data: {data}\n")
                    
                    f.write("\n")
                
                f.write("="*80 + "\n")
                f.write("END OF LOG\n")
            
            self.client._print_success(f"Exported log to: {export_path}")
            print(f"   Entries: {len(self.log_entries)}")
            print()
            
        except Exception as e:
            self.client._print_error(f"Export failed: {e}")

if __name__ == '__main__':
    print("This is a plugin for LXMF Client")
    print("Place in: ./lxmf_client_storage/plugins/")
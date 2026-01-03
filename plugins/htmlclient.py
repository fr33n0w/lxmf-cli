# html_client.py - LXMF HTML Client Plugin
import os
import tempfile
import webbrowser
import json
import time
from datetime import datetime

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['browse', 'br', 'htmlget', 'bookmarks', 'bm', 'htmlsettings']
        self.description = "Browse HTML pages over LXMF"
        
        # Setup paths
        self.html_path = os.path.join(client.storage_path, "html_client")
        self.cache_path = os.path.join(self.html_path, "cache")
        self.downloads_path = os.path.join(self.html_path, "downloads")
        self.bookmarks_file = os.path.join(self.html_path, "bookmarks.json")
        self.history_file = os.path.join(self.html_path, "history.json")
        self.config_file = os.path.join(self.html_path, "config.json")
        
        # HTML field constants (must match server)
        self.FIELD_HTML_CONTENT = 10  # HTML content from server
        self.FIELD_HTML_REQUEST = 11  # HTML request to server
        
        # Settings
        self.auto_open = True
        self.cache_pages = True
        self.save_history = True
        self.default_browser = None  # None = system default
        
        # Initialize
        self._init_storage()
        self._load_config()
        self.bookmarks = self._load_bookmarks()
        self.history = self._load_history()
        self._check_termux_setup()
    
    def _init_storage(self):
        """Create storage directories"""
        for path in [self.html_path, self.cache_path, self.downloads_path]:
            if not os.path.exists(path):
                os.makedirs(path)
    
    def _check_termux_setup(self):
        """Check Termux browser setup"""
        is_termux = os.path.exists('/data/data/com.termux')
        
        if is_termux:
            import subprocess
            try:
                subprocess.run(['which', 'termux-open'], 
                             capture_output=True, check=True, timeout=2)
            except:
                print("\n⚠️  Termux Setup Recommended:")
                print("   Install termux-tools for auto-open browser:")
                print("   pkg install termux-tools")
                print("   Pages will still be saved without it.\n")
    
    def _load_config(self):
        """Load client configuration"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.auto_open = config.get('auto_open', True)
                    self.cache_pages = config.get('cache_pages', True)
                    self.save_history = config.get('save_history', True)
                    self.default_browser = config.get('default_browser', None)
            except:
                pass
    
    def _save_config(self):
        """Save client configuration"""
        config = {
            'auto_open': self.auto_open,
            'cache_pages': self.cache_pages,
            'save_history': self.save_history,
            'default_browser': self.default_browser
        }
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
    
    def _load_bookmarks(self):
        """Load bookmarks"""
        if os.path.exists(self.bookmarks_file):
            try:
                with open(self.bookmarks_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def _save_bookmarks(self):
        """Save bookmarks"""
        with open(self.bookmarks_file, 'w') as f:
            json.dump(self.bookmarks, f, indent=2)
    
    def _load_history(self):
        """Load browsing history"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def _save_history(self):
        """Save browsing history"""
        # Keep only last 100 entries
        if len(self.history) > 100:
            self.history = self.history[-100:]
        
        with open(self.history_file, 'w') as f:
            json.dump(self.history, f, indent=2)
    
    def _add_to_history(self, server, page_name, title=""):
        """Add page to history"""
        if not self.save_history:
            return
        
        entry = {
            'server': server,
            'page': page_name,
            'title': title,
            'timestamp': time.time()
        }
        
        self.history.append(entry)
        self._save_history()
    
    def _open_browser(self, file_path):
        """Open file in browser with Termux support"""
        import subprocess
        import platform
        
        try:
            abs_path = os.path.abspath(file_path)
            file_url = 'file://' + abs_path
            
            # Detect Termux
            is_termux = os.path.exists('/data/data/com.termux')
            
            if is_termux:
                # Termux: Use termux-open or am start
                try:
                    # Try termux-open first (requires termux-tools package)
                    result = subprocess.run(
                        ['termux-open', abs_path],
                        capture_output=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        return True
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass
                
                try:
                    # Try Android intent via am
                    subprocess.run([
                        'am', 'start',
                        '-a', 'android.intent.action.VIEW',
                        '-d', file_url,
                        '-t', 'text/html'
                    ], capture_output=True, timeout=5)
                    return True
                except:
                    pass
                
                # Fallback: try common Android browsers
                browsers = [
                    'com.android.chrome/.Main',
                    'org.mozilla.firefox/.App',
                    'com.brave.browser/.Main',
                    'com.duckduckgo.mobile.android/.ui.main.MainActivity'
                ]
                
                for browser in browsers:
                    try:
                        subprocess.run([
                            'am', 'start',
                            '-n', browser,
                            '-a', 'android.intent.action.VIEW',
                            '-d', file_url
                        ], capture_output=True, timeout=5)
                        return True
                    except:
                        continue
                
                return False
            
            else:
                # Desktop: Use webbrowser module
                if self.default_browser:
                    browser = webbrowser.get(self.default_browser)
                    browser.open(file_url)
                else:
                    webbrowser.open(file_url)
                return True
                
        except Exception as e:
            print(f"⚠ Browser open error: {e}")
            return False
    
    def _open_html(self, html_content, page_name="page.html", server_name=""):
        """Open HTML content in browser"""
        try:
            # Create temporary file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_name = page_name.replace('/', '_').replace('\\', '_')
            
            if self.cache_pages:
                # Save to cache
                cache_file = os.path.join(self.cache_path, f"{timestamp}_{safe_name}")
            else:
                # Use temp file
                fd, cache_file = tempfile.mkstemp(suffix='.html', prefix='lxmf_')
                os.close(fd)
            
            # Write HTML
            with open(cache_file, 'w', encoding='utf-8') as f:
                # Add metadata banner
                banner = f"""<!-- 
LXMF HTML Page
Server: {server_name}
Page: {page_name}
Received: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
-->
"""
                f.write(banner + html_content)
            
            print(f"✓ Saved to: {cache_file}")
            
            # Open in browser
            if self.auto_open:
                opened = self._open_browser(cache_file)
                if opened:
                    print(f"✓ Opened in browser")
                else:
                    print(f"💡 Open manually: file://{os.path.abspath(cache_file)}")
            else:
                print(f"💡 Open manually: file://{os.path.abspath(cache_file)}")
            
            return cache_file
            
        except Exception as e:
            print(f"❌ Error opening HTML: {e}")
            return None
    
    def _save_html_file(self, html_data, page_name, server_name=""):
        """Save received HTML file to downloads"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_name = page_name.replace('/', '_').replace('\\', '_')
            file_path = os.path.join(self.downloads_path, f"{timestamp}_{safe_name}")
            
            with open(file_path, 'wb') as f:
                f.write(html_data)
            
            print(f"✓ Saved HTML file: {os.path.basename(file_path)}")
            
            # Try to open
            if self.auto_open:
                opened = self._open_browser(file_path)
                if opened:
                    print(f"✓ Opened in browser")
            
            return file_path
            
        except Exception as e:
            print(f"❌ Error saving HTML file: {e}")
            return None
    
    def on_message(self, message, msg_data):
        """Handle incoming messages - check for HTML content"""
        try:
            server_hash = msg_data['source_hash']
            server_name = self.client.format_contact_display_short(server_hash)
            
            # Check for embedded HTML content
            if hasattr(message, 'fields') and message.fields:
                if self.FIELD_HTML_CONTENT in message.fields:
                    html_content = message.fields[self.FIELD_HTML_CONTENT]
                    
                    # Extract page name from message content
                    content = msg_data.get('content', '')
                    page_name = "page.html"
                    if content.startswith("📄 Serving:"):
                        page_name = content.replace("📄 Serving:", "").strip()
                    elif content.startswith("📑"):
                        page_name = "index.html"
                    elif "404" in content:
                        page_name = "404.html"
                    
                    print(f"\n{'─'*60}")
                    print(f"📄 HTML PAGE RECEIVED")
                    print(f"{'─'*60}")
                    print(f"   From: {server_name}")
                    print(f"   Page: {page_name}")
                    print(f"   Size: {len(html_content):,} bytes")
                    print(f"{'─'*60}\n")
                    
                    # Open HTML
                    cache_file = self._open_html(html_content, page_name, server_name)
                    
                    # Add to history
                    if cache_file:
                        self._add_to_history(server_hash, page_name)
                    
                    return True  # Suppress normal notification
                
                # Check for HTML file attachment (field 6)
                FIELD_FILE_ATTACHMENTS = 6
                if FIELD_FILE_ATTACHMENTS in message.fields:
                    attachment_data = message.fields[FIELD_FILE_ATTACHMENTS]
                    
                    if isinstance(attachment_data, list) and len(attachment_data) >= 2:
                        file_ext = attachment_data[0]
                        file_data = attachment_data[1]
                        
                        # Check if it's HTML
                        if file_ext in ['html', 'htm']:
                            content = msg_data.get('content', '')
                            page_name = content.replace("📄", "").strip() if content else "page.html"
                            
                            print(f"\n{'─'*60}")
                            print(f"📄 HTML FILE RECEIVED")
                            print(f"{'─'*60}")
                            print(f"   From: {server_name}")
                            print(f"   File: {page_name}")
                            print(f"   Size: {len(file_data):,} bytes")
                            print(f"{'─'*60}\n")
                            
                            # Save and open
                            file_path = self._save_html_file(file_data, page_name, server_name)
                            
                            # Add to history
                            if file_path:
                                self._add_to_history(server_hash, page_name)
                            
                            return True  # Suppress normal notification
        
        except Exception as e:
            print(f"⚠ Error processing HTML: {e}")
        
        return False
    
    def _request_page(self, server, page_name):
        """Request an HTML page or index from a server"""
        try:
            # Resolve server
            dest_hash = self.client.resolve_contact_or_hash(server)
            if not dest_hash:
                print(f"❌ Could not resolve server: {server}")
                return False
            
            server_name = self.client.format_contact_display_short(dest_hash)
            
            # Check if requesting index
            if page_name.lower() in ['index', 'list', '']:
                print(f"\n📡 Requesting page index from {server_name}...")
                page_name = 'index'  # Server will understand this
            else:
                print(f"\n📡 Requesting '{page_name}' from {server_name}...")
            
            # Send request using custom field
            fields = {
                self.FIELD_HTML_REQUEST: page_name
            }
            
            success = self.client.send_message(
                dest_hash,
                f"GET:{page_name}",  # Also send as text for compatibility
                fields=fields
            )
            
            if success:
                print(f"✓ Request sent. Waiting for response...")
                return True
            else:
                print(f"❌ Failed to send request")
                return False
            
        except Exception as e:
            print(f"❌ Error requesting page: {e}")
            return False
    
    def _show_history(self):
        """Show browsing history"""
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 80)
        except:
            width = 80
        
        print(f"\n{'─'*width}")
        print(f"📜 BROWSING HISTORY")
        print(f"{'─'*width}\n")
        
        if not self.history:
            print("  No history yet\n")
        else:
            # Show last 20 entries
            for i, entry in enumerate(reversed(self.history[-20:]), 1):
                timestamp = datetime.fromtimestamp(entry['timestamp']).strftime('%Y-%m-%d %H:%M')
                server = self.client.format_contact_display_short(entry['server'])
                print(f"[{i}] {entry['page']}")
                print(f"    Server: {server}")
                print(f"    Time: {timestamp}")
                if entry.get('title'):
                    print(f"    Title: {entry['title']}")
                print()
        
        print(f"{'─'*width}\n")
    
    def _manage_bookmarks(self):
        """Manage bookmarks"""
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 70)
        except:
            width = 70
        
        while True:
            print(f"\n{'─'*width}")
            print(f"🔖 BOOKMARKS ({len(self.bookmarks)})")
            print(f"{'─'*width}\n")
            
            if self.bookmarks:
                for i, bm in enumerate(self.bookmarks, 1):
                    server = self.client.format_contact_display_short(bm['server'])
                    print(f"[{i}] {bm.get('title', bm['page'])}")
                    print(f"    Server: {server} | Page: {bm['page']}")
                    print()
            else:
                print("  No bookmarks yet\n")
            
            print(f"{'─'*width}")
            print(f"\n[a] Add bookmark")
            print(f"[r] Remove bookmark")
            print(f"[o] Open bookmark")
            print(f"[b] Back")
            print(f"{'─'*width}")
            
            choice = input("\nSelect option: ").strip().lower()
            
            if choice == 'a':
                server = input("Server (contact name or hash): ").strip()
                page = input("Page name: ").strip()
                title = input("Title (optional): ").strip()
                
                dest_hash = self.client.resolve_contact_or_hash(server)
                if dest_hash:
                    bookmark = {
                        'server': dest_hash,
                        'page': page,
                        'title': title if title else page
                    }
                    self.bookmarks.append(bookmark)
                    self._save_bookmarks()
                    print(f"✓ Bookmark added")
                else:
                    print(f"❌ Could not resolve server")
            
            elif choice == 'r':
                if self.bookmarks:
                    try:
                        num = int(input("Remove bookmark #: "))
                        if 1 <= num <= len(self.bookmarks):
                            removed = self.bookmarks.pop(num - 1)
                            self._save_bookmarks()
                            print(f"✓ Removed: {removed.get('title', removed['page'])}")
                        else:
                            print("❌ Invalid number")
                    except:
                        print("❌ Invalid input")
            
            elif choice == 'o':
                if self.bookmarks:
                    try:
                        num = int(input("Open bookmark #: "))
                        if 1 <= num <= len(self.bookmarks):
                            bm = self.bookmarks[num - 1]
                            self._request_page(bm['server'], bm['page'])
                        else:
                            print("❌ Invalid number")
                    except:
                        print("❌ Invalid input")
            
            elif choice in ['b', 'back', '']:
                break
    
    def _show_settings(self):
        """Show and modify client settings"""
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 70)
        except:
            width = 70
        
        while True:
            print(f"\n{'─'*width}")
            print(f"⚙️  HTML CLIENT SETTINGS")
            print(f"{'─'*width}")
            print(f"\n[1] Auto-open in browser: {'ON' if self.auto_open else 'OFF'}")
            print(f"[2] Cache pages: {'ON' if self.cache_pages else 'OFF'}")
            print(f"[3] Save history: {'ON' if self.save_history else 'OFF'}")
            print(f"[4] Default browser: {self.default_browser or 'System default'}")
            print(f"\n[5] Clear cache")
            print(f"[6] Clear history")
            print(f"[7] View history")
            print(f"[8] Open cache folder")
            print(f"\n[b] Back")
            print(f"{'─'*width}")
            
            choice = input("\nSelect option: ").strip().lower()
            
            if choice == '1':
                self.auto_open = not self.auto_open
                self._save_config()
                print(f"✓ Auto-open: {'ON' if self.auto_open else 'OFF'}")
            
            elif choice == '2':
                self.cache_pages = not self.cache_pages
                self._save_config()
                print(f"✓ Cache pages: {'ON' if self.cache_pages else 'OFF'}")
            
            elif choice == '3':
                self.save_history = not self.save_history
                self._save_config()
                print(f"✓ Save history: {'ON' if self.save_history else 'OFF'}")
            
            elif choice == '4':
                browser = input("Browser command (blank for default): ").strip()
                self.default_browser = browser if browser else None
                self._save_config()
                print(f"✓ Browser set to: {self.default_browser or 'system default'}")
            
            elif choice == '5':
                confirm = input("Clear all cached pages? [y/N]: ").strip().lower()
                if confirm == 'y':
                    try:
                        for file in os.listdir(self.cache_path):
                            os.remove(os.path.join(self.cache_path, file))
                        print("✓ Cache cleared")
                    except Exception as e:
                        print(f"❌ Error: {e}")
            
            elif choice == '6':
                confirm = input("Clear browsing history? [y/N]: ").strip().lower()
                if confirm == 'y':
                    self.history = []
                    self._save_history()
                    print("✓ History cleared")
            
            elif choice == '7':
                self._show_history()
            
            elif choice == '8':
                print(f"\n📂 Cache location: {self.cache_path}")
                print(f"📂 Downloads: {self.downloads_path}")
                print(f"\n💡 Open these in your file manager")
            
            elif choice in ['b', 'back', '']:
                break
    
    def handle_command(self, cmd, parts):
        """Handle HTML client commands"""
        
        if cmd in ['browse', 'br', 'htmlget']:
            if len(parts) < 2:
                print("\n💡 Usage: browse <server> [page]")
                print("   Examples:")
                print("     browse Alice              # Request page index")
                print("     browse Alice index.html")
                print("     br 5 about.html")
                print("     browse Alice index        # Special: page listing")
                print("\n   Default: Opens page index")
                print("\n   Also supports bookmarks:")
                print("     bookmarks - Manage bookmarks")
                print("     browse #1 - Open bookmark #1\n")
            else:
                server = parts[1]
                page = parts[2] if len(parts) > 2 else "index"  # Default to index listing
                
                # Check if requesting bookmark
                if server.startswith('#'):
                    try:
                        bm_num = int(server[1:])
                        if 1 <= bm_num <= len(self.bookmarks):
                            bm = self.bookmarks[bm_num - 1]
                            self._request_page(bm['server'], bm['page'])
                        else:
                            print(f"❌ Bookmark #{bm_num} not found")
                    except:
                        print(f"❌ Invalid bookmark number")
                else:
                    self._request_page(server, page)
        
        elif cmd in ['bookmarks', 'bm']:
            self._manage_bookmarks()
        
        elif cmd == 'htmlsettings':
            self._show_settings()

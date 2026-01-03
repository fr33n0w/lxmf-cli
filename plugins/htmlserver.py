# html_server.py - LXMF HTML Server Plugin
import os
import json
import time
from datetime import datetime

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['htmlserver', 'htmlstatus', 'htmllist', 'addpage']
        self.description = "Serve HTML pages over LXMF"
        
        # Setup paths
        self.html_path = os.path.join(client.storage_path, "html_server")
        self.pages_path = os.path.join(self.html_path, "pages")
        self.config_file = os.path.join(self.html_path, "config.json")
        self.access_log = os.path.join(self.html_path, "access.log")
        
        # Server settings
        self.enabled = True
        self.transfer_mode = "embedded"  # or "file"
        self.auto_index = True
        self.require_auth = False
        
        # Special field for HTML content
        self.FIELD_HTML_CONTENT = 10  # Custom field for HTML
        self.FIELD_HTML_REQUEST = 11  # Custom field for page requests
        
        # Initialize
        self._init_storage()
        self._load_config()
        
    def _init_storage(self):
        """Create storage directories"""
        for path in [self.html_path, self.pages_path]:
            if not os.path.exists(path):
                os.makedirs(path)
                
        # Create default index page if none exists
        index_path = os.path.join(self.pages_path, "index.html")
        if not os.path.exists(index_path):
            self._create_default_index()
    
    def _create_default_index(self):
        """Create a default index.html"""
        default_html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LXMF HTML Server</title>
    <style>
        body {
            font-family: monospace;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: #1a1a1a;
            color: #0f0;
        }
        h1 { color: #0f0; border-bottom: 2px solid #0f0; }
        .info { background: #2a2a2a; padding: 15px; border-radius: 5px; }
        a { color: #0ff; }
    </style>
</head>
<body>
    <h1>📡 LXMF HTML Server</h1>
    <div class="info">
        <p><strong>Welcome to the Reticulum HTML Server!</strong></p>
        <p>This page is being served over the LXMF protocol.</p>
        <p>Server time: {{timestamp}}</p>
        <p>Available pages:</p>
        <ul>{{page_list}}</ul>
    </div>
</body>
</html>"""
        
        index_path = os.path.join(self.pages_path, "index.html")
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(default_html)
    
    def _load_config(self):
        """Load server configuration"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.enabled = config.get('enabled', True)
                    self.transfer_mode = config.get('transfer_mode', 'embedded')
                    self.auto_index = config.get('auto_index', True)
                    self.require_auth = config.get('require_auth', False)
            except:
                pass
    
    def _save_config(self):
        """Save server configuration"""
        config = {
            'enabled': self.enabled,
            'transfer_mode': self.transfer_mode,
            'auto_index': self.auto_index,
            'require_auth': self.require_auth
        }
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
    
    def _log_access(self, requester, page, success):
        """Log page access"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        requester_name = self.client.format_contact_display_short(requester)
        status = "SUCCESS" if success else "FAILED"
        
        log_entry = f"[{timestamp}] {requester_name} requested '{page}' - {status}\n"
        
        with open(self.access_log, 'a') as f:
            f.write(log_entry)
    
    def _get_page_list(self):
        """Get list of available HTML pages"""
        pages = []
        try:
            for filename in os.listdir(self.pages_path):
                if filename.endswith('.html') or filename.endswith('.htm'):
                    pages.append(filename)
        except:
            pass
        return sorted(pages)
    
    def _process_template(self, html_content):
        """Process simple template variables"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        pages = self._get_page_list()
        
        page_list_html = '\n'.join([f'<li><a href="{p}">{p}</a></li>' for p in pages])
        
        html_content = html_content.replace('{{timestamp}}', timestamp)
        html_content = html_content.replace('{{page_list}}', page_list_html)
        
        return html_content
    
    def _serve_page_embedded(self, requester, page_name):
        """Serve HTML page as embedded content"""
        try:
            # Sanitize page name
            page_name = os.path.basename(page_name)
            if not page_name:
                page_name = "index.html"
            
            page_path = os.path.join(self.pages_path, page_name)
            
            # Check if page exists
            if not os.path.exists(page_path):
                # Send 404
                error_html = f"""<!DOCTYPE html>
<html>
<head><title>404 Not Found</title></head>
<body style="font-family:monospace;background:#1a1a1a;color:#f00;padding:50px;">
<h1>404 - Page Not Found</h1>
<p>The requested page '{page_name}' does not exist.</p>
</body>
</html>"""
                
                self.client.send_message(
                    requester,
                    f"404: Page '{page_name}' not found",
                    fields={self.FIELD_HTML_CONTENT: error_html}
                )
                self._log_access(requester, page_name, False)
                return False
            
            # Read and process HTML
            with open(page_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Process templates
            html_content = self._process_template(html_content)
            
            # Send HTML in custom field
            self.client.send_message(
                requester,
                f"📄 Serving: {page_name}",
                fields={self.FIELD_HTML_CONTENT: html_content}
            )
            
            self._log_access(requester, page_name, True)
            print(f"✓ Served '{page_name}' to {self.client.format_contact_display_short(requester)}")
            return True
            
        except Exception as e:
            print(f"❌ Error serving page: {e}")
            self._log_access(requester, page_name, False)
            return False
    
    def _serve_page_file(self, requester, page_name):
        """Serve HTML page as file attachment"""
        try:
            page_name = os.path.basename(page_name)
            if not page_name:
                page_name = "index.html"
            
            page_path = os.path.join(self.pages_path, page_name)
            
            if not os.path.exists(page_path):
                self.client.send_message(requester, f"❌ Page '{page_name}' not found")
                self._log_access(requester, page_name, False)
                return False
            
            # Read HTML
            with open(page_path, 'rb') as f:
                html_data = f.read()
            
            # Send as file attachment (using file manager approach)
            FIELD_FILE_ATTACHMENTS = 6
            fields = {
                FIELD_FILE_ATTACHMENTS: ['html', html_data]
            }
            
            self.client.send_message(
                requester,
                f"📄 {page_name}",
                fields=fields
            )
            
            self._log_access(requester, page_name, True)
            print(f"✓ Sent '{page_name}' to {self.client.format_contact_display_short(requester)}")
            return True
            
        except Exception as e:
            print(f"❌ Error serving page: {e}")
            self._log_access(requester, page_name, False)
            return False
    
    def on_message(self, message, msg_data):
        """Handle incoming messages - check for page requests"""
        if not self.enabled:
            return False
        
        try:
            content = msg_data.get('content', '').strip()
            
            # Check for HTML request in fields
            if hasattr(message, 'fields') and message.fields:
                if self.FIELD_HTML_REQUEST in message.fields:
                    page_name = message.fields[self.FIELD_HTML_REQUEST]
                    
                    requester_name = self.client.format_contact_display_short(msg_data['source_hash'])
                    print(f"\n📡 HTML Request from {requester_name}: {page_name}")
                    
                    if self.transfer_mode == "embedded":
                        self._serve_page_embedded(msg_data['source_hash'], page_name)
                    else:
                        self._serve_page_file(msg_data['source_hash'], page_name)
                    
                    return True  # Suppress normal notification
            
            # Also support text-based requests: "GET:page.html"
            if content.startswith("GET:") or content.startswith("get:"):
                page_name = content[4:].strip()
                
                requester_name = self.client.format_contact_display_short(msg_data['source_hash'])
                print(f"\n📡 HTML Request from {requester_name}: {page_name}")
                
                if self.transfer_mode == "embedded":
                    self._serve_page_embedded(msg_data['source_hash'], page_name)
                else:
                    self._serve_page_file(msg_data['source_hash'], page_name)
                
                return True
            
        except Exception as e:
            print(f"⚠ Error handling HTML request: {e}")
        
        return False
    
    def _show_status(self):
        """Show server status"""
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 70)
        except:
            width = 70
        
        print(f"\n{'─'*width}")
        print(f"📡 HTML SERVER STATUS")
        print(f"{'─'*width}")
        print(f"\nServer: {'🟢 ENABLED' if self.enabled else '🔴 DISABLED'}")
        print(f"Transfer mode: {self.transfer_mode.upper()}")
        print(f"Auto index: {'ON' if self.auto_index else 'OFF'}")
        print(f"Authentication: {'REQUIRED' if self.require_auth else 'OPEN'}")
        print(f"\n📂 Pages directory: {self.pages_path}")
        print(f"📊 Available pages: {len(self._get_page_list())}")
        print(f"\n💡 Request format:")
        print(f"   Text: Send 'GET:page.html'")
        print(f"   Field: Use FIELD_HTML_REQUEST (11)")
        print(f"{'─'*width}\n")
    
    def _list_pages(self):
        """List available HTML pages"""
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 70)
        except:
            width = 70
        
        pages = self._get_page_list()
        
        print(f"\n{'─'*width}")
        print(f"📄 AVAILABLE PAGES ({len(pages)})")
        print(f"{'─'*width}\n")
        
        if pages:
            for i, page in enumerate(pages, 1):
                page_path = os.path.join(self.pages_path, page)
                size = os.path.getsize(page_path)
                size_str = f"{size:,} bytes" if size < 1024 else f"{size/1024:.1f} KB"
                print(f"[{i}] {page}")
                print(f"    Size: {size_str}")
                print()
        else:
            print("  No pages available\n")
        
        print(f"{'─'*width}\n")
    
    def _add_page(self, filename, content=None):
        """Add a new HTML page"""
        if not filename.endswith('.html') and not filename.endswith('.htm'):
            filename += '.html'
        
        page_path = os.path.join(self.pages_path, filename)
        
        if content is None:
            # Create template
            content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{filename}</title>
    <style>
        body {{ font-family: monospace; margin: 50px; background: #1a1a1a; color: #0f0; }}
    </style>
</head>
<body>
    <h1>New Page: {filename}</h1>
    <p>Edit this file at: {page_path}</p>
</body>
</html>"""
        
        with open(page_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✓ Created page: {filename}")
        print(f"  Location: {page_path}")
    
    def handle_command(self, cmd, parts):
        """Handle HTML server commands"""
        
        if cmd == 'htmlserver':
            if len(parts) < 2:
                print("\n💡 Usage: htmlserver [on|off|embedded|file]")
                print("   on/off - Enable/disable server")
                print("   embedded - Serve HTML in message content")
                print("   file - Serve HTML as file attachment\n")
            else:
                action = parts[1].lower()
                
                if action == 'on':
                    self.enabled = True
                    self._save_config()
                    print("✓ HTML server enabled")
                elif action == 'off':
                    self.enabled = False
                    self._save_config()
                    print("✓ HTML server disabled")
                elif action == 'embedded':
                    self.transfer_mode = 'embedded'
                    self._save_config()
                    print("✓ Using embedded mode")
                elif action == 'file':
                    self.transfer_mode = 'file'
                    self._save_config()
                    print("✓ Using file transfer mode")
        
        elif cmd == 'htmlstatus':
            self._show_status()
        
        elif cmd == 'htmllist':
            self._list_pages()
        
        elif cmd == 'addpage':
            if len(parts) < 2:
                print("\n💡 Usage: addpage <filename.html>")
            else:
                self._add_page(parts[1])
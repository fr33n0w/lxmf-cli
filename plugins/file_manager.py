# file_manager.py - PRODUCTION VERSION
import os
import json
import base64
import time
import mimetypes
from datetime import datetime

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['sendfile', 'sf', 'listfiles', 'lf', 'savefile', 'filesettings']
        self.description = "File transfer manager over LXMF"
        
        # Setup storage
        self.storage_path = os.path.join(client.storage_path, "files")
        self.sent_path = os.path.join(self.storage_path, "sent")
        self.received_path = os.path.join(self.storage_path, "received")
        self.db_file = os.path.join(self.storage_path, "file_transfers.json")
        
        # Settings
        self.max_file_size = 1024 * 1024 * 2  # 2MB default (safe for most networks)
        self.auto_save = True
        self.show_progress = True
        
        # LXMF field constants
        self.FIELD_FILE_ATTACHMENTS = 6  # Standard LXMF file attachment field
        
        # Initialize storage
        self._init_storage()
        self.transfers = self._load_transfers()
        
    def _init_storage(self):
        """Create storage directories if they don't exist"""
        for path in [self.storage_path, self.sent_path, self.received_path]:
            if not os.path.exists(path):
                os.makedirs(path)
                
    def _load_transfers(self):
        """Load file transfer history"""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r') as f:
                    return json.load(f)
            except:
                return {"sent": [], "received": []}
        return {"sent": [], "received": []}
    
    def _save_transfers(self):
        """Save file transfer history"""
        try:
            with open(self.db_file, 'w') as f:
                json.dump(self.transfers, f, indent=2)
        except Exception as e:
            print(f"⚠ Error saving transfer history: {e}")
    
    def _format_size(self, size_bytes):
        """Format bytes to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f}TB"
    
    def _detect_file_attachment(self, message):
        """Detect if message contains a file attachment"""
        try:
            if not hasattr(message, 'fields') or not message.fields:
                return None
            
            fields = message.fields
            
            # Check for standard LXMF file attachment field (field 6)
            if self.FIELD_FILE_ATTACHMENTS in fields:
                attachment_data = fields[self.FIELD_FILE_ATTACHMENTS]
                
                # Format: [extension, binary_data] or [filename, binary_data]
                if isinstance(attachment_data, list) and len(attachment_data) >= 2:
                    file_ext_or_name = attachment_data[0]
                    file_data = attachment_data[1]
                    
                    # Determine filename
                    if '.' in str(file_ext_or_name):
                        file_name = str(file_ext_or_name)
                    else:
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        file_name = f"attachment_{timestamp}.{file_ext_or_name}"
                    
                    # Determine MIME type
                    mime_type, _ = mimetypes.guess_type(file_name)
                    if not mime_type:
                        mime_type = 'application/octet-stream'
                    
                    if isinstance(file_data, bytes):
                        return {
                            'file_name': file_name,
                            'file_data': file_data,
                            'file_size': len(file_data),
                            'mime_type': mime_type
                        }
            
            return None
            
        except Exception as e:
            print(f"⚠ Error detecting file attachment: {e}")
            return None
    
    def on_message(self, message, msg_data):
        """Handle incoming messages - check for file attachments"""
        try:
            # Try to detect file attachment
            file_info = self._detect_file_attachment(message)
            
            if file_info:
                file_name = file_info['file_name']
                file_size = file_info['file_size']
                mime_type = file_info['mime_type']
                sender = self.client.format_contact_display_short(msg_data['source_hash'])
                
                print(f"\n{'─'*60}")
                print(f"📎 FILE RECEIVED: {file_name}")
                print(f"{'─'*60}")
                print(f"   From: {sender}")
                print(f"   Size: {self._format_size(file_size)}")
                print(f"   Type: {mime_type}")
                
                if self.auto_save:
                    saved_path = self._save_received_file(message, msg_data, file_info)
                    if saved_path:
                        print(f"   ✓ Saved to: {os.path.basename(saved_path)}")
                else:
                    print(f"   💡 Use 'savefile' to save")
                
                print(f"{'─'*60}\n")
                
                # Log transfer
                self._log_received_transfer(msg_data['source_hash'], file_name, file_size, msg_data['timestamp'])
                
                return True  # Suppress normal notification
                    
        except Exception as e:
            print(f"⚠ Error processing file: {e}")
        
        return False
    
    def _save_received_file(self, message, msg_data, file_info):
        """Save received file to disk"""
        try:
            file_name = file_info['file_name']
            file_data = file_info['file_data']
            
            # Generate safe filename with timestamp
            timestamp = datetime.fromtimestamp(msg_data['timestamp']).strftime('%Y%m%d_%H%M%S')
            safe_filename = f"{timestamp}_{file_name}"
            file_path = os.path.join(self.received_path, safe_filename)
            
            # Save file
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            return file_path
            
        except Exception as e:
            print(f"   ✗ Error saving file: {e}")
            return None
    
    def _log_received_transfer(self, source_hash, file_name, file_size, timestamp):
        """Log received file transfer"""
        self.transfers["received"].append({
            "from": source_hash,
            "file_name": file_name,
            "file_size": file_size,
            "timestamp": timestamp,
            "saved": self.auto_save
        })
        self._save_transfers()
    
    def _log_sent_transfer(self, dest_hash, file_name, file_size):
        """Log sent file transfer"""
        self.transfers["sent"].append({
            "to": dest_hash,
            "file_name": file_name,
            "file_size": file_size,
            "timestamp": time.time()
        })
        self._save_transfers()
    
    def _send_file(self, recipient, file_path):
        """Send a file via LXMF"""
        try:
            # Check file exists
            if not os.path.exists(file_path):
                print(f"❌ File not found: {file_path}")
                return False
            
            # Get file info
            file_size = os.path.getsize(file_path)
            file_name = os.path.basename(file_path)
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = 'application/octet-stream'
            
            # Check size limit
            if file_size > self.max_file_size:
                print(f"\n❌ File too large!")
                print(f"   File size: {self._format_size(file_size)}")
                print(f"   Maximum: {self._format_size(self.max_file_size)}")
                print(f"   💡 Use 'filesettings' to adjust limit\n")
                return False
            
            # Read file
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            # Resolve recipient
            dest_hash = self.client.resolve_contact_or_hash(recipient)
            if not dest_hash:
                print(f"❌ Could not resolve recipient: {recipient}")
                return False
            
            recipient_name = self.client.format_contact_display_short(dest_hash)
            
            print(f"\n{'─'*60}")
            print(f"📤 SENDING FILE: {file_name}")
            print(f"{'─'*60}")
            print(f"   To: {recipient_name}")
            print(f"   Size: {self._format_size(file_size)}")
            print(f"   Type: {mime_type}")
            print(f"{'─'*60}\n")
            
            # Get file extension
            file_ext = os.path.splitext(file_name)[1].lstrip('.')
            if not file_ext:
                file_ext = 'bin'
            
            # Prepare LXMF message using standard field 6 format
            fields = {
                self.FIELD_FILE_ATTACHMENTS: [file_ext, file_data]
            }
            
            content = f"📎 {file_name}"
            title = ""
            
            # Send via client
            success = self.client.send_message(
                dest_hash, 
                content,
                title=title,
                fields=fields
            )
            
            if success:
                self._log_sent_transfer(dest_hash, file_name, file_size)
                
                # Copy to sent folder
                try:
                    sent_file = os.path.join(self.sent_path, file_name)
                    if not os.path.exists(sent_file):
                        import shutil
                        shutil.copy2(file_path, sent_file)
                except:
                    pass
                
                return True
            else:
                print(f"❌ Failed to send file\n")
                return False
                
        except Exception as e:
            print(f"❌ Error sending file: {e}\n")
            return False
    
    def _list_files(self, filter_type=None):
        """List sent/received files"""
        import shutil
        
        try:
            width = min(shutil.get_terminal_size().columns, 90)
        except:
            width = 90
        
        print(f"\n{'─'*width}")
        print(f"📁 FILE TRANSFERS")
        print(f"{'─'*width}")
        
        # Show received files
        if filter_type in [None, 'received']:
            print(f"\n📥 RECEIVED FILES ({len(self.transfers['received'])})")
            print(f"{'─'*width}")
            
            if len(self.transfers['received']) > 0:
                for i, transfer in enumerate(reversed(self.transfers['received'][-10:]), 1):
                    timestamp = datetime.fromtimestamp(transfer['timestamp']).strftime('%Y-%m-%d %H:%M')
                    from_str = self.client.format_contact_display_short(transfer['from'])
                    print(f"[{i}] {transfer['file_name']}")
                    print(f"    From: {from_str}")
                    print(f"    Size: {self._format_size(transfer['file_size'])} | {timestamp}")
                    if transfer.get('saved'):
                        print(f"    ✓ Saved")
                    print()
            else:
                print("  No files received yet\n")
        
        # Show sent files  
        if filter_type in [None, 'sent']:
            print(f"📤 SENT FILES ({len(self.transfers['sent'])})")
            print(f"{'─'*width}")
            
            if len(self.transfers['sent']) > 0:
                for i, transfer in enumerate(reversed(self.transfers['sent'][-10:]), 1):
                    timestamp = datetime.fromtimestamp(transfer['timestamp']).strftime('%Y-%m-%d %H:%M')
                    to_str = self.client.format_contact_display_short(transfer['to'])
                    print(f"[{i}] {transfer['file_name']}")
                    print(f"    To: {to_str}")
                    print(f"    Size: {self._format_size(transfer['file_size'])} | {timestamp}")
                    print()
            else:
                print("  No files sent yet\n")
        
        print(f"{'─'*width}")
        print(f"💾 Received: {self.received_path}")
        print(f"💾 Sent: {self.sent_path}")
        print(f"📊 Max file size: {self._format_size(self.max_file_size)}")
        print()
    
    def _show_settings(self):
        """Show and modify file manager settings"""
        import shutil
        
        try:
            width = min(shutil.get_terminal_size().columns, 70)
        except:
            width = 70
        
        while True:
            print(f"\n{'─'*width}")
            print(f"⚙️  FILE MANAGER SETTINGS")
            print(f"{'─'*width}")
            print(f"\n[1] Max file size: {self._format_size(self.max_file_size)}")
            print(f"[2] Auto-save received files: {'ON' if self.auto_save else 'OFF'}")
            print(f"[3] Show transfer progress: {'ON' if self.show_progress else 'OFF'}")
            print(f"\n[4] Clear transfer history")
            print(f"[5] Open storage folder")
            print(f"\n[b] Back")
            print(f"{'─'*width}")
            
            choice = input("\nSelect option: ").strip().lower()
            
            if choice == '1':
                size_mb = input("Enter max size in MB [current: {:.1f}]: ".format(self.max_file_size/1024/1024)).strip()
                try:
                    size = float(size_mb) if size_mb else (self.max_file_size/1024/1024)
                    self.max_file_size = int(size * 1024 * 1024)
                    print(f"✓ Max file size set to {self._format_size(self.max_file_size)}")
                except:
                    print("❌ Invalid size")
            
            elif choice == '2':
                self.auto_save = not self.auto_save
                print(f"✓ Auto-save: {'ON' if self.auto_save else 'OFF'}")
            
            elif choice == '3':
                self.show_progress = not self.show_progress
                print(f"✓ Progress display: {'ON' if self.show_progress else 'OFF'}")
            
            elif choice == '4':
                confirm = input("Clear all transfer history? [y/N]: ").strip().lower()
                if confirm == 'y':
                    self.transfers = {"sent": [], "received": []}
                    self._save_transfers()
                    print("✓ Transfer history cleared")
            
            elif choice == '5':
                print(f"\n📂 Storage locations:")
                print(f"   Received: {self.received_path}")
                print(f"   Sent: {self.sent_path}")
                print(f"\n💡 Open these in your file manager")
            
            elif choice in ['b', 'back', '']:
                break
    
    def handle_command(self, cmd, parts):
        """Handle file manager commands"""
        
        if cmd in ['sendfile', 'sf']:
            if len(parts) < 3:
                print("\n💡 Usage: sendfile <contact/#> <filepath>")
                print("   Examples:")
                print("     sendfile Alice document.pdf")
                print("     sf 3 ~/photo.jpg")
                print("     sendfile Bob \"~/My Documents/report.docx\"")
                print("\n   Supported formats:")
                print("     📄 Documents: PDF, DOCX, TXT, etc.")
                print("     🖼️  Images: JPG, PNG, GIF, etc.")
                print("     🎵 Audio: MP3, WAV, OGG, etc.")
                print("     🎬 Video: MP4, AVI, MKV, etc.")
                print("     📦 Archives: ZIP, TAR, etc.")
                print("     💾 Any binary file\n")
            else:
                recipient = parts[1]
                file_path = ' '.join(parts[2:])
                file_path = os.path.expanduser(file_path)
                file_path = file_path.strip('"').strip("'")
                self._send_file(recipient, file_path)
        
        elif cmd in ['listfiles', 'lf']:
            filter_type = parts[1].lower() if len(parts) > 1 else None
            if filter_type and filter_type not in ['sent', 'received']:
                print("💡 Usage: listfiles [sent|received]")
            else:
                self._list_files(filter_type)
        
        elif cmd == 'savefile':
            print("\n💡 File Save Settings:")
            print(f"   Auto-save: {'ON' if self.auto_save else 'OFF'}")
            print(f"   Location: {self.received_path}")
            print("\n   Use 'filesettings' to change auto-save setting\n")
        
        elif cmd == 'filesettings':
            self._show_settings()
"""
Contact Info Plugin for LXMF-CLI
Show detailed contact information and copy to clipboard
Supports: contacts, peers, search by name/hash/index
"""
import sys
import os
import platform

class Plugin:
    def __init__(self, client):
        """Initialize the contact info plugin"""
        self.client = client
        self.commands = ['show', 'copy']
        self.description = "Show contact info and copy to clipboard"
        
        # Store last shown contact hash for easy copying
        self.last_shown_hash = None
        
        print("Contact Info plugin loaded! Use 'show <contact>' to view details")
    
    def _copy_to_clipboard(self, text):
        """Copy text to clipboard (cross-platform)"""
        system = platform.system()
        
        try:
            if system == 'Windows':
                # Windows
                import subprocess
                process = subprocess.Popen(['clip'], stdin=subprocess.PIPE, shell=True)
                process.communicate(text.encode('utf-8'))
                return True
            
            elif system == 'Darwin':
                # macOS
                import subprocess
                process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
                process.communicate(text.encode('utf-8'))
                return True
            
            elif system == 'Linux':
                # Check if running in Termux
                if os.path.exists('/data/data/com.termux'):
                    # Termux
                    import subprocess
                    process = subprocess.Popen(['termux-clipboard-set'], stdin=subprocess.PIPE)
                    process.communicate(text.encode('utf-8'))
                    return True
                else:
                    # Linux with xclip or xsel
                    import subprocess
                    try:
                        # Try xclip first
                        process = subprocess.Popen(['xclip', '-selection', 'clipboard'], 
                                                 stdin=subprocess.PIPE)
                        process.communicate(text.encode('utf-8'))
                        return True
                    except FileNotFoundError:
                        try:
                            # Try xsel
                            process = subprocess.Popen(['xsel', '--clipboard', '--input'], 
                                                     stdin=subprocess.PIPE)
                            process.communicate(text.encode('utf-8'))
                            return True
                        except FileNotFoundError:
                            return False
            else:
                return False
        
        except Exception as e:
            return False
    
    def _find_contact(self, search_term):
        """
        Find a contact by index, name, nickname, hash, or partial hash
        Returns: (hash, type, name) or None
        type can be: 'contact', 'peer', 'conversation'
        """
        if not search_term:
            return None
        
        search_lower = search_term.lower()
        
        # 1. Try as index number
        try:
            idx = int(search_term)
            
            # Search in contacts
            for name, data in self.client.contacts.items():
                if data.get('index') == idx:
                    return (data['hash'], 'contact', name)
            
            # Search in conversations
            for hash_str, conv_idx in self.client.conversation_indices.items():
                if conv_idx == idx:
                    contact_name = self.client.get_contact_name_by_hash(hash_str)
                    return (hash_str, 'conversation', contact_name)
            
            # Search in peers
            with self.client.peers_lock:
                for hash_str, peer_data in self.client.announced_peers.items():
                    if peer_data.get('index') == idx:
                        display_name = peer_data.get('display_name', 'Unknown')
                        return (hash_str, 'peer', display_name)
        
        except ValueError:
            pass
        
        # 2. Try as exact contact name (case-insensitive)
        for name, data in self.client.contacts.items():
            if name.lower() == search_lower:
                return (data['hash'], 'contact', name)
        
        # 3. Try as partial contact name
        for name, data in self.client.contacts.items():
            if search_lower in name.lower():
                return (data['hash'], 'contact', name)
        
        # 4. Try as peer display name
        with self.client.peers_lock:
            for hash_str, peer_data in self.client.announced_peers.items():
                display_name = peer_data.get('display_name', '').lower()
                if display_name == search_lower or search_lower in display_name:
                    return (hash_str, 'peer', peer_data.get('display_name', 'Unknown'))
        
        # 5. Try as full hash
        clean_search = search_term.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
        if len(clean_search) == 64:
            # Valid full hash
            try:
                bytes.fromhex(clean_search)
                contact_name = self.client.get_contact_name_by_hash(clean_search)
                return (clean_search, 'hash', contact_name)
            except ValueError:
                pass
        
        # 6. Try as partial hash
        if len(clean_search) >= 8:
            # Check contacts
            for name, data in self.client.contacts.items():
                contact_hash = data['hash'].replace(":", "").replace(" ", "").lower()
                if contact_hash.startswith(clean_search):
                    return (data['hash'], 'contact', name)
            
            # Check peers
            with self.client.peers_lock:
                for hash_str, peer_data in self.client.announced_peers.items():
                    if hash_str.startswith(clean_search):
                        return (hash_str, 'peer', peer_data.get('display_name', 'Unknown'))
            
            # Check conversations
            for hash_str in self.client.conversation_indices.keys():
                if hash_str.startswith(clean_search):
                    contact_name = self.client.get_contact_name_by_hash(hash_str)
                    return (hash_str, 'conversation', contact_name)
        
        return None
    
    def _show_contact_info(self, hash_str, source_type, source_name):
        """Display detailed contact information"""
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 80)
        except:
            width = 70
        
        # Normalize hash
        clean_hash = hash_str.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
        
        # Store for easy copying
        self.last_shown_hash = clean_hash
        
        # Get all available information
        contact_name = None
        contact_index = None
        for name, data in self.client.contacts.items():
            if data['hash'].replace(":", "").replace(" ", "").lower() == clean_hash:
                contact_name = name
                contact_index = data.get('index')
                break
        
        display_name = self.client.get_lxmf_display_name(clean_hash)
        
        peer_info = None
        with self.client.peers_lock:
            if clean_hash in self.client.announced_peers:
                peer_info = self.client.announced_peers[clean_hash]
        
        conversation_index = self.client.conversation_indices.get(clean_hash)
        
        # Check if blacklisted
        is_blacklisted = self.client.is_blacklisted(clean_hash)
        
        # Build info display
        print(f"\n{'='*width}")
        print(f"CONTACT INFORMATION".center(width))
        print(f"{'='*width}")
        
        # Source
        print(f"\n📍 Found in: {source_type.upper()}")
        
        # Contact Name (saved nickname)
        if contact_name:
            print(f"\n👤 Saved Contact:")
            print(f"   Name: {contact_name}")
            print(f"   Index: #{contact_index}")
        else:
            print(f"\n👤 Saved Contact: None")
            print(f"   💡 Use 'save' or 'savecontact' to add")
        
        # LXMF Display Name (from network)
        if display_name:
            print(f"\n📡 LXMF Display Name:")
            print(f"   {display_name}")
        else:
            print(f"\n📡 LXMF Display Name: Not announced")
        
        # Peer Information
        if peer_info:
            import time
            last_seen = peer_info.get('last_seen', 0)
            time_diff = time.time() - last_seen
            
            if time_diff < 60:
                time_str = "just now"
            elif time_diff < 3600:
                time_str = f"{int(time_diff/60)} min ago"
            elif time_diff < 86400:
                time_str = f"{int(time_diff/3600)} hours ago"
            else:
                time_str = f"{int(time_diff/86400)} days ago"
            
            print(f"\n🌐 Peer Status:")
            print(f"   Last seen: {time_str}")
            print(f"   Peer index: #{peer_info.get('index', '?')}")
        
        # Conversation Index
        if conversation_index:
            print(f"\n💬 Conversation Index: #{conversation_index}")
        
        # Hash Address (single string, no colons)
        print(f"\n🔑 LXMF Address:")
        print(f"   {clean_hash}")
        
        # Security Status
        if is_blacklisted:
            print(f"\n🚫 Security: BLACKLISTED")
        
        print(f"\n{'='*width}")
        
        # Quick Actions
        print(f"\n💡 Quick Actions:")
        print(f"   copy - Copy hash to clipboard")
        if contact_name:
            print(f"   send {contact_name} <msg> - Send message")
            print(f"   edit {contact_name} - Edit contact")
        else:
            print(f"   save - Save to contacts")
        
        if conversation_index:
            print(f"   messages user {conversation_index} - View conversation")
        
        print()
        
        return clean_hash
    
    def handle_command(self, cmd, parts):
        """Handle show and copy commands"""
        
        if cmd == 'show':
            if len(parts) < 2:
                print("\n💡 Usage: show <contact>")
                print("\nSearch by:")
                print("  - Contact index: show 1")
                print("  - Contact name: show Alice")
                print("  - Peer index: show 5")
                print("  - Display name: show Bob")
                print("  - Hash: show abc123...")
                print("  - Partial hash: show abc123\n")
                return
            
            search_term = ' '.join(parts[1:])
            
            result = self._find_contact(search_term)
            
            if result:
                hash_str, source_type, source_name = result
                self._show_contact_info(hash_str, source_type, source_name)
            else:
                print(f"\n❌ Contact not found: {search_term}")
                print("\n💡 Try:")
                print("  - 'contacts' to see saved contacts")
                print("  - 'peers' to see announced peers")
                print("  - 'messages list' to see conversations\n")
        
        elif cmd == 'copy':
            # If argument provided, find and copy that contact
            if len(parts) >= 2:
                search_term = ' '.join(parts[1:])
                
                result = self._find_contact(search_term)
                
                if result:
                    hash_str, source_type, source_name = result
                    clean_hash = hash_str.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
                    
                    # Try to copy to clipboard
                    if self._copy_to_clipboard(clean_hash):
                        display = self.client.format_contact_display_short(clean_hash)
                        print(f"\n✓ Copied to clipboard: {display}")
                        print(f"  Hash: {clean_hash}")
                        print(f"  Source: {source_type}\n")
                    else:
                        # Fallback: just display
                        print(f"\n⚠️  Clipboard not available on this system")
                        print(f"\nHash for {source_name}:")
                        print(f"{clean_hash}")
                        print("\n💡 Manual copy: Select and copy the hash above\n")
                else:
                    print(f"\n❌ Contact not found: {search_term}\n")
            
            # No argument - copy last shown contact
            else:
                if self.last_shown_hash:
                    if self._copy_to_clipboard(self.last_shown_hash):
                        display = self.client.format_contact_display_short(self.last_shown_hash)
                        print(f"\n✓ Copied to clipboard: {display}")
                        print(f"  Hash: {self.last_shown_hash}\n")
                    else:
                        # Fallback: just display
                        print(f"\n⚠️  Clipboard not available on this system")
                        print(f"\nHash:")
                        print(f"{self.last_shown_hash}")
                        print("\n💡 Manual copy: Select and copy the hash above\n")
                else:
                    print("\n❌ No contact shown yet")
                    print("\n💡 Use 'show <contact>' first, then 'copy'")
                    print("   Or use 'copy <contact>' directly\n")

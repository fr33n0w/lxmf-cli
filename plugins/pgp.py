#!/usr/bin/env python3
"""
PGP Plugin for LXMF CLI
Provides end-to-end encryption and signing for LXMF messages using PGP/GPG
"""

import os
import json
import time
import gnupg
from datetime import datetime

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['pgp']
        self.description = "End-to-end PGP encryption and signing for messages"
        
        # Setup plugin storage
        self.plugin_dir = os.path.join(client.storage_path, "plugins", "pgp")
        self.keyring_dir = os.path.join(self.plugin_dir, "keyring")
        self.config_file = os.path.join(self.plugin_dir, "config.json")
        self.trusted_keys_file = os.path.join(self.plugin_dir, "trusted_keys.json")
        
        os.makedirs(self.keyring_dir, exist_ok=True)
        
        # Initialize GPG with options for non-interactive environments (Termux fix)
        gpg_options = [
            '--batch',
            '--no-tty',
            '--pinentry-mode', 'loopback'
        ]
        self.gpg = gnupg.GPG(gnupghome=self.keyring_dir, options=gpg_options)
        
        # Load configuration
        self.config = self.load_config()
        self.trusted_keys = self.load_trusted_keys()
        
        # Auto-enable settings
        self.auto_encrypt = self.config.get('auto_encrypt', False)
        self.auto_sign = self.config.get('auto_sign', True)
        self.auto_verify = self.config.get('auto_verify', True)
        self.auto_decrypt = self.config.get('auto_decrypt', True)
        self.reject_unsigned = self.config.get('reject_unsigned', False)
        self.reject_unencrypted = self.config.get('reject_unencrypted', False)
        
        # Passphrase for the key (empty by default for batch-generated keys)
        self.passphrase = self.config.get('passphrase', '')
        
        # Current user's key
        self.my_key_id = self.config.get('my_key_id', None)
        
        # Initialize key if needed
        if not self.my_key_id:
            self._first_time_setup()
        
        self._print_success("PGP plugin loaded")
        if self.my_key_id:
            self._print_success(f"Using key: {self.my_key_id[:16]}...")
    
    def _print_success(self, msg):
        """Print success message"""
        if hasattr(self.client, '_print_success'):
            self.client._print_success(f"[PGP] {msg}")
        else:
            print(f"✓ [PGP] {msg}")
    
    def _print_error(self, msg):
        """Print error message"""
        if hasattr(self.client, '_print_error'):
            self.client._print_error(f"[PGP] {msg}")
        else:
            print(f"❌ [PGP] {msg}")
    
    def _print_warning(self, msg):
        """Print warning message"""
        if hasattr(self.client, '_print_warning'):
            self.client._print_warning(f"[PGP] {msg}")
        else:
            print(f"⚠ [PGP] {msg}")
    
    def load_config(self):
        """Load plugin configuration"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self._print_warning(f"Error loading config: {e}")
        return {}
    
    def save_config(self):
        """Save plugin configuration"""
        try:
            config = {
                'my_key_id': self.my_key_id,
                'auto_encrypt': self.auto_encrypt,
                'auto_sign': self.auto_sign,
                'auto_verify': self.auto_verify,
                'auto_decrypt': self.auto_decrypt,
                'reject_unsigned': self.reject_unsigned,
                'reject_unencrypted': self.reject_unencrypted,
                'passphrase': self.passphrase
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            self._print_warning(f"Error saving config: {e}")
    
    def load_trusted_keys(self):
        """Load trusted public keys mapping (hash -> key_id)"""
        if os.path.exists(self.trusted_keys_file):
            try:
                with open(self.trusted_keys_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self._print_warning(f"Error loading trusted keys: {e}")
        return {}
    
    def save_trusted_keys(self):
        """Save trusted keys mapping"""
        try:
            with open(self.trusted_keys_file, 'w') as f:
                json.dump(self.trusted_keys, f, indent=2)
        except Exception as e:
            self._print_warning(f"Error saving trusted keys: {e}")
    
    def _first_time_setup(self):
        """First time setup - generate PGP key"""
        print("\n" + "─"*60)
        print("PGP PLUGIN - FIRST TIME SETUP")
        print("─"*60)
        print("\nNo PGP key found. Let's create one for you.")
        print("This will be used to sign and encrypt your messages.\n")
        
        # Use display name from client
        name = self.client.display_name if hasattr(self.client, 'display_name') else "LXMF User"
        
        # Generate email from LXMF address
        if hasattr(self.client.destination, 'hash'):
            import RNS
            lxmf_addr = RNS.prettyhexrep(self.client.destination.hash).replace(":", "")
            email = f"{lxmf_addr[:16]}@lxmf.local"
        else:
            email = "user@lxmf.local"
        
        print(f"Name: {name}")
        print(f"Email: {email}")
        print("\nGenerating 2048-bit RSA key pair...")
        print("This may take a minute (especially on mobile devices)...\n")
        
        try:
            # Check if GPG is working
            gpg_version = self.gpg.version
            if not gpg_version:
                self._print_error("GPG not properly initialized!")
                self._print_error(f"GPG home: {self.keyring_dir}")
                print("\nTo fix this, try:")
                print("  1. Check GPG is installed: gpg --version")
                print("  2. Manually run: pgp keygen")
                return
            
            print(f"Using GPG version: {gpg_version}")
            
            # Use quick-gen-key for batch mode (Termux compatible)
            # This bypasses the interactive prompts entirely
            import subprocess
            
            print("Key input parameters generated")
            print("Starting key generation (please wait, this can take 30-60 seconds on mobile)...")
            print("TIP: Move your device around to help generate randomness!")
            
            # Build the user ID
            user_id = f"{name} <{email}>"
            
            # Try using gpg command directly with --quick-gen-key
            try:
                cmd = [
                    'gpg',
                    '--homedir', self.keyring_dir,
                    '--batch',
                    '--passphrase', '',
                    '--quick-gen-key', user_id,
                    'rsa2048',
                    'default',
                    '0'  # Never expire
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120  # 2 minute timeout
                )
                
                print(f"\nGPG command completed with return code: {result.returncode}")
                
                if result.returncode == 0:
                    # Key generated successfully, get the fingerprint
                    list_result = subprocess.run(
                        ['gpg', '--homedir', self.keyring_dir, '--list-keys', '--with-colons'],
                        capture_output=True,
                        text=True
                    )
                    
                    # Parse fingerprint from output
                    for line in list_result.stdout.split('\n'):
                        if line.startswith('fpr:'):
                            fingerprint = line.split(':')[9]
                            if fingerprint:
                                self.my_key_id = fingerprint
                                self.save_config()
                                self._print_success("PGP key pair generated!")
                                self._print_success(f"Key ID: {self.my_key_id}")
                                print("\n" + "─"*60 + "\n")
                                return
                    
                    # If we got here, couldn't find fingerprint
                    self._print_error("Key generated but couldn't retrieve fingerprint")
                    print("Run 'pgp list' to see available keys")
                else:
                    self._print_error(f"GPG command failed with code {result.returncode}")
                    if result.stderr:
                        print(f"Error: {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                self._print_error("Key generation timed out after 2 minutes")
                print("This can happen on low-entropy systems")
                print("Try: pkg install haveged && haveged -w 1024")
            except Exception as e:
                self._print_error(f"Failed to run GPG command: {e}")
                print("\n💡 Falling back to python-gnupg method...")
                
                # Fallback to python-gnupg if subprocess fails
                key_input = self.gpg.gen_key_input(
                    name_real=name,
                    name_email=email,
                    key_type='RSA',
                    key_length=2048,
                    expire_date=0,
                    passphrase=''
                )
                
                key = self.gpg.gen_key(key_input)
                
                if key and str(key) and str(key).strip():
                    self.my_key_id = str(key)
                    self.save_config()
                    self._print_success("PGP key pair generated!")
                    self._print_success(f"Key ID: {self.my_key_id}")
                    print("\n" + "─"*60 + "\n")
                    return
            
            # If we got here, everything failed
            self._print_error("Failed to generate key")
            print(f"\n💡 Troubleshooting:")
            print("   1. Try manually: gpg --batch --passphrase '' --quick-gen-key 'Test' rsa2048")
            print("   2. Or see manual setup in TERMUX_TROUBLESHOOTING.md")
        except Exception as e:
            self._print_error(f"Key generation failed: {e}")
            import traceback
            print("\nDebug info:")
            traceback.print_exc()
            print("\n💡 To retry manually, use: pgp keygen")
    
    def get_recipient_key(self, dest_hash):
        """Get recipient's public key ID"""
        # Normalize hash
        clean_hash = dest_hash.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
        return self.trusted_keys.get(clean_hash)
    
    def import_public_key(self, dest_hash, key_data):
        """Import a recipient's public key"""
        try:
            result = self.gpg.import_keys(key_data)
            if result.count > 0:
                key_id = result.fingerprints[0]
                
                # Set trust level to ultimate for imported keys
                # This is needed for GPG to consider the key "usable"
                try:
                    import subprocess
                    # Trust the key using GPG command
                    trust_cmd = f"echo -e \"5\ny\n\" | gpg --homedir {self.keyring_dir} --command-fd 0 --expert --edit-key {key_id} trust quit"
                    subprocess.run(trust_cmd, shell=True, capture_output=True)
                except Exception as e:
                    # If trust setting fails, try alternative method
                    pass
                
                # Store mapping
                clean_hash = dest_hash.replace(":", "").replace(" ", "").replace("<", "").replace(">", "").lower()
                self.trusted_keys[clean_hash] = key_id
                self.save_trusted_keys()
                
                self._print_success(f"Imported public key: {key_id[:16]}...")
                return key_id
            else:
                self._print_error("Failed to import key")
                return None
        except Exception as e:
            self._print_error(f"Import failed: {e}")
            return None
    
    def export_my_public_key(self):
        """Export current user's public key"""
        if not self.my_key_id:
            return None
        
        try:
            ascii_key = self.gpg.export_keys(self.my_key_id)
            return ascii_key
        except Exception as e:
            self._print_error(f"Export failed: {e}")
            return None
    
    def encrypt_message(self, content, recipient_key_id):
        """Encrypt message content for recipient"""
        try:
            # Ensure recipient_key_id is valid (might be fingerprint or key ID)
            # Try to verify the key exists first
            keys = self.gpg.list_keys()
            recipient_found = False
            for key in keys:
                if recipient_key_id in [key['fingerprint'], key['keyid']]:
                    recipient_found = True
                    # Use fingerprint for encryption (most reliable)
                    recipient_key_id = key['fingerprint']
                    break
            
            if not recipient_found:
                self._print_error(f"Recipient key not found in keyring")
                print(f"  Looking for: {recipient_key_id[:16]}...")
                print(f"  Available keys: {len(keys)}")
                return None
            
            encrypted = self.gpg.encrypt(
                content,
                recipient_key_id,
                always_trust=True,
                armor=True
            )
            
            if encrypted.ok:
                return str(encrypted)
            else:
                self._print_error(f"Encryption failed: {encrypted.status}")
                if hasattr(encrypted, 'stderr'):
                    print(f"  GPG error: {encrypted.stderr}")
                return None
        except Exception as e:
            self._print_error(f"Encryption error: {e}")
            return None
    
    def decrypt_message(self, encrypted_content):
        """Decrypt encrypted message"""
        try:
            decrypted = self.gpg.decrypt(
                encrypted_content,
                passphrase=self.passphrase
            )
            
            if decrypted.ok:
                return str(decrypted)
            else:
                self._print_error(f"Decryption failed: {decrypted.status}")
                return None
        except Exception as e:
            self._print_error(f"Decryption error: {e}")
            return None
    
    def sign_message(self, content):
        """Sign message content"""
        try:
            signed = self.gpg.sign(
                content,
                keyid=self.my_key_id,
                clearsign=True,
                passphrase=self.passphrase
            )
            
            if signed and str(signed):
                return str(signed)
            else:
                self._print_error("Signing failed")
                # Debug info
                if hasattr(signed, 'status'):
                    print(f"  Status: {signed.status}")
                if hasattr(signed, 'stderr'):
                    print(f"  Error: {signed.stderr}")
                return None
        except Exception as e:
            self._print_error(f"Signing error: {e}")
            return None
    
    def verify_signature(self, signed_content):
        """Verify signed message"""
        try:
            verified = self.gpg.verify(signed_content)
            
            if verified.valid:
                # Extract original message
                lines = signed_content.split('\n')
                message_lines = []
                in_message = False
                
                for line in lines:
                    if line.startswith('-----BEGIN PGP SIGNED MESSAGE-----'):
                        in_message = True
                        continue
                    elif line.startswith('-----BEGIN PGP SIGNATURE-----'):
                        break
                    elif in_message and not line.startswith('Hash: '):
                        if line or message_lines:  # Skip initial empty lines
                            message_lines.append(line)
                
                original_message = '\n'.join(message_lines).strip()
                
                return {
                    'valid': True,
                    'key_id': verified.key_id,
                    'username': verified.username,
                    'message': original_message
                }
            else:
                return {
                    'valid': False,
                    'message': signed_content
                }
        except Exception as e:
            self._print_error(f"Verification error: {e}")
            return {'valid': False, 'message': signed_content}
    
    def on_message(self, message, msg_data):
        """Handle incoming messages - auto decrypt/verify and handle key exchange"""
        try:
            content = msg_data['content']
            source_hash = msg_data['source_hash']
            title = msg_data.get('title', '')
            
            # === AUTOMATIC KEY EXCHANGE ===
            
            # 1. Handle key requests
            if content.strip() == "PGP_KEY_REQUEST" or title == "PGP Key Request":
                self._print_success(f"Received key request from {self.client.format_contact_display_short(source_hash)}")
                
                # Auto-send our public key back
                my_public_key = self.export_my_public_key()
                if my_public_key:
                    self.client.send_message(
                        source_hash, 
                        my_public_key,
                        title="PGP Public Key"
                    )
                    self._print_success("Automatically sent our public key in response")
                
                return True  # Suppress normal notification
            
            # 2. Handle key responses (auto-import)
            if "-----BEGIN PGP PUBLIC KEY BLOCK-----" in content and "-----END PGP PUBLIC KEY BLOCK-----" in content:
                # This looks like a PGP public key
                
                # Check if we already have this key
                existing_key = self.get_recipient_key(source_hash)
                
                if not existing_key:
                    self._print_success(f"Received public key from {self.client.format_contact_display_short(source_hash)}")
                    
                    # Auto-import the key
                    key_id = self.import_public_key(source_hash, content)
                    
                    if key_id:
                        contact_name = self.client.format_contact_display_short(source_hash)
                        self._print_success(f"✓ Auto-imported and trusted key for {contact_name}")
                        print(f"  You can now send encrypted messages: pgp send {contact_name} <message>")
                    
                    return True  # Suppress normal notification
                else:
                    # We already have their key, just show it arrived
                    print(f"\n📩 Received public key from {self.client.format_contact_display_short(source_hash)}")
                    print("   (Already have their key, ignoring)")
                    return True
            
            # === NORMAL MESSAGE PROCESSING ===
            
            # Check if message is encrypted
            is_encrypted = '-----BEGIN PGP MESSAGE-----' in content
            is_signed = '-----BEGIN PGP SIGNED MESSAGE-----' in content
            
            # Check rejection policies
            if self.reject_unencrypted and not is_encrypted:
                self._print_warning(f"Rejected unencrypted message from {source_hash[:16]}...")
                print("  Enable 'pgp set reject_unencrypted off' to receive unencrypted messages")
                return True  # Suppress normal notification
            
            if self.reject_unsigned and not is_signed and not is_encrypted:
                self._print_warning(f"Rejected unsigned message from {source_hash[:16]}...")
                print("  Enable 'pgp set reject_unsigned off' to receive unsigned messages")
                return True  # Suppress normal notification
            
            modified = False
            
            # Auto-decrypt if enabled
            if self.auto_decrypt and is_encrypted:
                print(f"\n🔐 Encrypted message from {self.client.format_contact_display_short(source_hash)}")
                decrypted = self.decrypt_message(content)
                
                if decrypted:
                    # UPDATE the message content so LXMF shows decrypted version
                    msg_data['content'] = decrypted
                    content = decrypted
                    modified = True
                    self._print_success("Message decrypted")
                    
                    # Check if decrypted content is also signed
                    is_signed = '-----BEGIN PGP SIGNED MESSAGE-----' in content
                else:
                    self._print_error("Failed to decrypt message")
                    return True  # Suppress - couldn't decrypt
            
            # Auto-verify if enabled
            if self.auto_verify and is_signed:
                result = self.verify_signature(content)
                
                if result['valid']:
                    # UPDATE content to show the verified message without signature
                    msg_data['content'] = result['message']
                    modified = True
                    self._print_success(f"✓ Signature valid - From: {result.get('username', 'Unknown')}")
                    print(f"  Key ID: {result['key_id'][:16]}...")
                else:
                    self._print_warning("⚠ Invalid or missing signature!")
                    if self.reject_unsigned:
                        return True  # Suppress
            
            # Return False so normal notification shows the DECRYPTED content
            return False
            
        except Exception as e:
            self._print_error(f"Message processing error: {e}")
            return False
    
    def handle_command(self, cmd, parts):
        """Handle PGP commands"""
        if len(parts) < 2:
            self.show_help()
            return
        
        subcmd = parts[1].lower()
        
        if subcmd == 'help':
            self.show_help()
        
        elif subcmd == 'status':
            self.show_status()
        
        elif subcmd == 'keygen':
            self.generate_new_key()
        
        elif subcmd == 'diagnose' or subcmd == 'debug':
            self.diagnose_gpg()
        
        elif subcmd == 'export':
            self.export_key_command()
        
        elif subcmd == 'import':
            self.import_key_command(parts)
        
        elif subcmd == 'exchange':
            self.exchange_keys_command(parts)
        
        elif subcmd == 'trust':
            self.trust_key_command(parts)
        
        elif subcmd == 'list':
            self.list_keys()
        
        elif subcmd == 'send':
            self.send_encrypted_command(parts)
        
        elif subcmd == 'set':
            self.change_setting(parts)
        
        elif subcmd == 'passphrase':
            self.set_passphrase_command()
        
        elif subcmd == 'trustlevel':
            self.trust_level_command(parts)
        
        else:
            print(f"Unknown subcommand: {subcmd}")
            self.show_help()
    
    def diagnose_gpg(self):
        """Diagnose GPG installation and configuration"""
        print("\n" + "─"*70)
        print("PGP DIAGNOSTIC INFORMATION")
        print("─"*70)
        
        # Check GPG binary
        print("\n🔍 GPG Binary:")
        try:
            import subprocess
            result = subprocess.run(['gpg', '--version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                first_line = result.stdout.split('\n')[0]
                print(f"  ✓ Found: {first_line}")
            else:
                print(f"  ❌ GPG check failed: {result.stderr}")
        except FileNotFoundError:
            print("  ❌ GPG binary not found in PATH")
            print("     Install: pkg install gnupg (Termux)")
            print("     Or: sudo apt install gnupg (Linux)")
        except Exception as e:
            print(f"  ❌ Error running GPG: {e}")
        
        # Check python-gnupg
        print("\n🐍 Python GnuPG Library:")
        try:
            import gnupg
            print(f"  ✓ Module loaded: {gnupg.__file__}")
        except ImportError:
            print("  ❌ python-gnupg not installed")
            print("     Install: pip install python-gnupg --break-system-packages")
        
        # Check GPG home directory
        print(f"\n📁 Keyring Directory:")
        print(f"  Path: {self.keyring_dir}")
        print(f"  Exists: {os.path.exists(self.keyring_dir)}")
        print(f"  Writable: {os.access(self.keyring_dir, os.W_OK)}")
        
        # Check GPG version via python-gnupg
        print(f"\n🔧 Python-GnuPG Status:")
        try:
            gpg_version = self.gpg.version
            if gpg_version:
                print(f"  ✓ GPG version: {gpg_version}")
            else:
                print("  ❌ Could not get GPG version")
                print("     GPG may not be properly configured")
        except Exception as e:
            print(f"  ❌ Error: {e}")
        
        # List existing keys
        print(f"\n🔑 Current Keys in Keyring:")
        try:
            keys = self.gpg.list_keys()
            if keys:
                print(f"  Found {len(keys)} key(s):")
                for key in keys:
                    key_id = key['keyid'][-16:]
                    name = key['uids'][0] if key['uids'] else 'Unknown'
                    marker = "  ★" if key['fingerprint'] == self.my_key_id else "   "
                    print(f"{marker} {key_id}: {name}")
            else:
                print("  No keys found in keyring")
        except Exception as e:
            print(f"  ❌ Error listing keys: {e}")
        
        # Check config
        print(f"\n⚙️  Plugin Configuration:")
        print(f"  Config file: {self.config_file}")
        print(f"  Configured key ID: {self.my_key_id if self.my_key_id else 'None'}")
        
        # Recommendations
        print("\n" + "─"*70)
        print("💡 Recommendations:")
        
        if not self.my_key_id:
            print("  • No key configured - run: pgp keygen")
        
        try:
            subprocess.run(['gpg', '--version'], 
                         capture_output=True, timeout=1, check=True)
        except:
            print("  • Install GPG: pkg install gnupg")
        
        try:
            import gnupg
        except:
            print("  • Install python-gnupg:")
            print("    pip install python-gnupg --break-system-packages")
        
        if not os.access(self.keyring_dir, os.W_OK):
            print(f"  • Fix permissions: chmod 700 {self.keyring_dir}")
        
        print("\n" + "─"*70 + "\n")
    
    def show_help(self):
        """Show plugin help"""
        print("\n" + "─"*70)
        print("PGP PLUGIN - COMMANDS")
        print("─"*70)
        
        print("\n📊 Status & Info:")
        print("  pgp status              - Show PGP status and settings")
        print("  pgp list                - List all keys in keyring")
        print("  pgp diagnose            - Diagnose GPG installation issues")
        
        print("\n🔑 Key Management:")
        print("  pgp keygen              - Generate new PGP key pair")
        print("  pgp export              - Export your public key")
        print("  pgp passphrase          - Set/change key passphrase")
        print("  pgp exchange <contact>  - 🆕 AUTO key exchange (easiest!)")
        print("  pgp import <contact>    - Request public key from contact")
        print("  pgp trust <contact> <key> - Manually import and trust a key")
        
        print("\n📨 Messaging:")
        print("  pgp send <contact> <msg> - Send encrypted message")
        
        print("\n⚙️  Settings:")
        print("  pgp set auto_encrypt on/off    - Auto-encrypt outgoing")
        print("  pgp set auto_sign on/off        - Auto-sign outgoing")
        print("  pgp set auto_decrypt on/off     - Auto-decrypt incoming")
        print("  pgp set auto_verify on/off      - Auto-verify signatures")
        print("  pgp set reject_unsigned on/off  - Reject unsigned messages")
        print("  pgp set reject_unencrypted on/off - Reject unencrypted")
        
        print("\n💡 Quick Start:")
        print("  1. pgp exchange <contact>    - Automatic key exchange!")
        print("  2. Wait 5-10 seconds")
        print("  3. pgp send <contact> <msg>  - Send encrypted message")
        
        print("\n" + "─"*70 + "\n")
    
    def show_status(self):
        """Show PGP status"""
        print("\n" + "─"*70)
        print("PGP STATUS")
        print("─"*70)
        
        print(f"\n🔑 Your Key:")
        if self.my_key_id:
            print(f"  Key ID: {self.my_key_id}")
            keys = self.gpg.list_keys()
            my_key = next((k for k in keys if k['fingerprint'] == self.my_key_id), None)
            if my_key:
                print(f"  Name: {my_key['uids'][0] if my_key['uids'] else 'Unknown'}")
                print(f"  Type: {my_key['type']} {my_key['length']}-bit")
        else:
            print("  No key configured")
        
        print(f"\n⚙️  Settings:")
        print(f"  Auto-encrypt:  {'ON' if self.auto_encrypt else 'OFF'}")
        print(f"  Auto-sign:     {'ON' if self.auto_sign else 'OFF'}")
        print(f"  Auto-decrypt:  {'ON' if self.auto_decrypt else 'OFF'}")
        print(f"  Auto-verify:   {'ON' if self.auto_verify else 'OFF'}")
        print(f"  Reject unsigned:    {'ON' if self.reject_unsigned else 'OFF'}")
        print(f"  Reject unencrypted: {'ON' if self.reject_unencrypted else 'OFF'}")
        
        print(f"\n👥 Trusted Keys: {len(self.trusted_keys)}")
        if self.trusted_keys:
            for hash_str, key_id in list(self.trusted_keys.items())[:5]:
                contact_name = self.client.format_contact_display_short(hash_str)
                print(f"  {contact_name}: {key_id[:16]}...")
            if len(self.trusted_keys) > 5:
                print(f"  ... and {len(self.trusted_keys) - 5} more")
        
        print("\n" + "─"*70 + "\n")
    
    def generate_new_key(self):
        """Generate a new PGP key"""
        if self.my_key_id:
            print("\n⚠ Warning: This will replace your current key!")
            print(f"Current key: {self.my_key_id}")
            confirm = input("Continue? [y/N]: ").strip().lower()
            
            if confirm != 'y':
                print("Cancelled")
                return
        else:
            print("\n📝 Generating new PGP key...")
        
        # Clear current key
        old_key = self.my_key_id
        self.my_key_id = None
        
        # Run setup
        self._first_time_setup()
        
        # Verify it worked
        if self.my_key_id:
            self._print_success("Key generation complete!")
        else:
            self._print_error("Key generation incomplete")
            print("\n🔍 Troubleshooting steps:")
            print("  1. Check GPG: gpg --version")
            print("  2. Test GPG: gpg --gen-key")
            print("  3. Check permissions on: " + self.keyring_dir)
            print("  4. On Termux, ensure: pkg install gnupg")
            if old_key:
                print(f"\n  Your old key ID was: {old_key}")
                print("  (It has not been deleted from the keyring)")

    
    def export_key_command(self):
        """Export public key and prepare for sending"""
        public_key = self.export_my_public_key()
        
        if public_key:
            print("\n" + "─"*70)
            print("YOUR PUBLIC KEY")
            print("─"*70)
            print(public_key)
            print("─"*70)
            print("\n💡 Share this with contacts so they can send you encrypted messages")
            print("   You can send it via: send <contact> <paste key here>")
            print()
    
    def import_key_command(self, parts):
        """Request public key from contact - sends automatic key request"""
        if len(parts) < 3:
            print("💡 Usage: pgp import <contact>")
            print("   This will send an automatic key request to the contact")
            return
        
        contact = parts[2]
        
        # Resolve contact
        dest_hash = self.client.resolve_contact_or_hash(contact)
        if not dest_hash:
            self._print_error(f"Unknown contact: {contact}")
            return
        
        # Check if we already have their key
        existing_key = self.get_recipient_key(dest_hash)
        if existing_key:
            contact_name = self.client.format_contact_display_short(dest_hash)
            self._print_warning(f"You already have a key for {contact_name}")
            print(f"   Key ID: {existing_key[:16]}...")
            
            confirm = input("Request new key anyway? [y/N]: ").strip().lower()
            if confirm != 'y':
                print("Cancelled")
                return
        
        # Send automatic key request
        self.client.send_message(dest_hash, "PGP_KEY_REQUEST", title="PGP Key Request")
        
        contact_name = self.client.format_contact_display_short(dest_hash)
        self._print_success(f"📨 Sent automatic key request to {contact_name}")
        print("   They will receive a request and their client will auto-respond")
        print("   You'll receive and auto-import their key when they respond")
        print(f"\n💡 Wait a few seconds, then check: pgp list")
    
    def exchange_keys_command(self, parts):
        """Automatic bidirectional key exchange with a contact"""
        if len(parts) < 3:
            print("💡 Usage: pgp exchange <contact>")
            print("   This will:")
            print("   1. Send your public key to the contact")
            print("   2. Request their public key")
            print("   3. Auto-import when they respond")
            return
        
        contact = parts[2]
        
        # Resolve contact
        dest_hash = self.client.resolve_contact_or_hash(contact)
        if not dest_hash:
            self._print_error(f"Unknown contact: {contact}")
            return
        
        contact_name = self.client.format_contact_display_short(dest_hash)
        
        print(f"\n🔄 Starting key exchange with {contact_name}...")
        print("─"*60)
        
        # Step 1: Send our public key
        my_public_key = self.export_my_public_key()
        if my_public_key:
            self.client.send_message(dest_hash, my_public_key, title="PGP Public Key")
            self._print_success("✓ Sent our public key")
        else:
            self._print_error("Failed to export our key")
            return
        
        # Step 2: Request their public key
        self.client.send_message(dest_hash, "PGP_KEY_REQUEST", title="PGP Key Request")
        self._print_success("✓ Sent key request")
        
        print("─"*60)
        print(f"\n✅ Key exchange initiated with {contact_name}")
        print("\n📥 What happens next:")
        print("   1. They receive your public key (auto-imported)")
        print("   2. They receive your key request (auto-responded)")
        print("   3. You receive their key (auto-imported)")
        print("\n⏱️  Wait ~5-10 seconds for messages to arrive")
        print(f"   Then check: pgp list")
        print(f"   Then test:  pgp send {contact_name} Hello encrypted!")
    
    def trust_key_command(self, parts):
        """Import and trust a public key"""
        # parts = ['pgp', 'trust', 'contact key_data...']
        
        if len(parts) < 3:
            print("💡 Usage: pgp trust <contact> <key_data>")
            print("   Or paste the key on the next line")
            return
        
        # Split: "contact key_data..." -> ["contact", "key_data..."]
        rest = parts[2].split(maxsplit=1)
        
        if len(rest) < 2:
            print("💡 Usage: pgp trust <contact> <key_data>")
            print("   Paste the entire PGP public key block")
            return
        
        contact = rest[0]
        key_data = rest[1]
        
        # Resolve contact to hash
        dest_hash = self.client.resolve_contact_or_hash(contact)
        if not dest_hash:
            self._print_error(f"Unknown contact: {contact}")
            return
        
        # Import the key
        result = self.import_public_key(dest_hash, key_data)
        
        if result:
            contact_display = self.client.format_contact_display_short(dest_hash)
            self._print_success(f"Trusted key for {contact_display}")
    
    def list_keys(self):
        """List all keys in keyring"""
        print("\n" + "─"*70)
        print("PGP KEYRING")
        print("─"*70)
        
        keys = self.gpg.list_keys()
        
        if not keys:
            print("\nNo keys in keyring\n")
            return
        
        print(f"\n{'Key ID':<18} {'Type':<12} {'Name':<30} {'Can Encrypt'}")
        print("─"*70)
        
        for key in keys:
            key_id = key['keyid'][-16:]
            key_type = f"{key['type']} {key['length']}-bit"
            name = key['uids'][0] if key['uids'] else 'Unknown'
            
            # Truncate name if too long
            if len(name) > 28:
                name = name[:25] + "..."
            
            # Check if this is a public key (can encrypt)
            can_encrypt = "Yes" if key['type'] in ['pub', 'RSA'] else "No"
            
            marker = "★ " if key['fingerprint'] == self.my_key_id else "  "
            
            print(f"{marker}{key_id:<16} {key_type:<12} {name:<30} {can_encrypt}")
        
        print("─"*70)
        print("\n★ = Your key\n")
        
        # Show trusted keys mapping
        if self.trusted_keys:
            print("Trusted Keys Mapping:")
            for hash_str, key_id in list(self.trusted_keys.items())[:5]:
                contact_name = self.client.format_contact_display_short(hash_str)
                print(f"  {contact_name}: {key_id[:16]}...")
            if len(self.trusted_keys) > 5:
                print(f"  ... and {len(self.trusted_keys) - 5} more")
            print()
    
    def send_encrypted_command(self, parts):
        """Send encrypted and signed message"""
        # parts = ['pgp', 'send', 'contact message...']
        # We need to split parts[2] to get contact and message
        
        if len(parts) < 3:
            print("💡 Usage: pgp send <contact> <message>")
            return
        
        # Split the rest: "contact message..." -> ["contact", "message..."]
        rest = parts[2].split(maxsplit=1)
        
        if len(rest) < 2:
            print("💡 Usage: pgp send <contact> <message>")
            print("Example: pgp send Alice Hello!")
            print("Example: pgp send 2 Hello!")
            return
        
        contact = rest[0]
        message = rest[1]
        
        # Resolve contact to hash
        dest_hash = self.client.resolve_contact_or_hash(contact)
        if not dest_hash:
            self._print_error(f"Unknown contact: {contact}")
            return
        
        # Get recipient's public key
        recipient_key = self.get_recipient_key(dest_hash)
        
        if not recipient_key:
            self._print_error(f"No public key for {contact}")
            print("   Use 'pgp import <contact>' to request their key")
            print("   Or 'pgp trust <contact> <key>' to import manually")
            return
        
        # Sign the message first
        signed = self.sign_message(message)
        if not signed:
            return
        
        # Then encrypt the signed message
        encrypted = self.encrypt_message(signed, recipient_key)
        if not encrypted:
            return
        
        # Send via normal LXMF
        self.client.send_message(dest_hash, encrypted, title="🔐 Encrypted")
        
        self._print_success("Sent encrypted & signed message")
    
    
    
    def trust_level_command(self, parts):
        """Manually set trust level on a key to make it usable"""
        if len(parts) < 3:
            print("💡 Usage: pgp trustlevel <contact_or_key_id>")
            return
        
        target = parts[2]
        
        # Try to resolve as contact first
        dest_hash = self.client.resolve_contact_or_hash(target)
        key_id = None
        
        if dest_hash:
            # Get their key ID
            key_id = self.get_recipient_key(dest_hash)
        else:
            # Might be a direct key ID
            key_id = target
        
        if not key_id:
            self._print_error(f"Unknown contact or key: {target}")
            return
        
        print(f"\nSetting trust level for key: {key_id[:16]}...")
        
        import subprocess
        
        # Method 1: Interactive trust setting
        try:
            # Use echo to pipe "5" (ultimate trust) and "y" (confirm)
            cmd = f'echo -e "5\\ny\\n" | gpg --homedir "{self.keyring_dir}" --command-fd 0 --expert --edit-key {key_id} trust quit'
            
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                self._print_success("Trust level set to ULTIMATE")
                print("  The key should now be usable for encryption")
            else:
                self._print_error("Failed to set trust level")
                print(f"  Error: {result.stderr}")
                
                # Try Windows-compatible method
                print("\n  Trying alternative method...")
                self._trust_key_windows(key_id)
        
        except Exception as e:
            self._print_error(f"Error: {e}")
            # Try Windows method
            self._trust_key_windows(key_id)
    
    def _trust_key_windows(self, key_id):
        """Windows-compatible method to trust a key"""
        import subprocess
        
        try:
            # Create a temporary file with trust commands
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
                f.write("5\ny\n")
                temp_file = f.name
            
            try:
                cmd = f'gpg --homedir "{self.keyring_dir}" --command-file "{temp_file}" --expert --edit-key {key_id} trust quit'
                
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    self._print_success("Trust level set (Windows method)")
                else:
                    self._print_error("Windows method also failed")
                    print("\n  Manual fix:")
                    print(f"  1. Run: gpg --edit-key {key_id}")
                    print(f"  2. Type: trust")
                    print(f"  3. Type: 5 (ultimate)")
                    print(f"  4. Type: y (confirm)")
                    print(f"  5. Type: quit")
            finally:
                os.unlink(temp_file)
        
        except Exception as e:
            self._print_error(f"Windows method error: {e}")
    
    def set_passphrase_command(self):
        """Set or change the passphrase for the PGP key"""
        print("\n" + "─"*60)
        print("SET KEY PASSPHRASE")
        print("─"*60)
        print("\nThis sets the passphrase used to unlock your PGP key.")
        print("If your key has no passphrase, leave it empty.")
        print()
        
        import getpass
        try:
            passphrase = getpass.getpass("Enter passphrase (or press Enter for none): ")
            confirm = getpass.getpass("Confirm passphrase: ")
            
            if passphrase != confirm:
                self._print_error("Passphrases don't match!")
                return
            
            self.passphrase = passphrase
            self.save_config()
            
            if passphrase:
                self._print_success("Passphrase set successfully")
            else:
                self._print_success("Passphrase removed (empty)")
            
            print("\n💡 Test it: pgp send <contact> test")
            
        except KeyboardInterrupt:
            print("\nCancelled")
        except:
            # Fallback for terminals without getpass
            print("Getpass not available, using visible input:")
            passphrase = input("Enter passphrase (visible!): ").strip()
            self.passphrase = passphrase
            self.save_config()
            self._print_success("Passphrase set")
    
    def change_setting(self, parts):
        """Change plugin settings"""
        if len(parts) < 4:
            print("💡 Usage: pgp set <setting> <on/off>")
            print("\nAvailable settings:")
            print("  auto_encrypt, auto_sign, auto_decrypt, auto_verify")
            print("  reject_unsigned, reject_unencrypted")
            return
        
        setting = parts[2].lower()
        value = parts[3].lower() in ['on', 'yes', 'true', '1']
        
        if setting == 'auto_encrypt':
            self.auto_encrypt = value
        elif setting == 'auto_sign':
            self.auto_sign = value
        elif setting == 'auto_decrypt':
            self.auto_decrypt = value
        elif setting == 'auto_verify':
            self.auto_verify = value
        elif setting == 'reject_unsigned':
            self.reject_unsigned = value
        elif setting == 'reject_unencrypted':
            self.reject_unencrypted = value
        else:
            self._print_error(f"Unknown setting: {setting}")
            return
        
        self.save_config()
        status = "enabled" if value else "disabled"
        self._print_success(f"{setting}: {status}")

"""
Anti-Spam Plugin for LXMF-CLI
Block messages containing specific spam words/phrases
"""
import os
import json

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['antispam', 'spam']
        self.description = "Block messages with spam keywords"
        
        # Settings
        self.enabled = True
        self.spam_words = set()
        self.case_sensitive = False
        self.block_mode = 'silent'  # 'silent' or 'notify'
        
        # Statistics
        self.blocked_count = 0
        self.blocked_senders = {}  # Track blocked messages per sender
        
        # Load settings
        self.config_file = os.path.join(client.storage_path, "antispam_config.json")
        self.load_config()
        
        print(f"✓ Anti-Spam loaded! ({len(self.spam_words)} words, {'ON' if self.enabled else 'OFF'})")
    
    def load_config(self):
        """Load anti-spam configuration"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.enabled = config.get('enabled', True)
                    self.spam_words = set(config.get('spam_words', []))
                    self.case_sensitive = config.get('case_sensitive', False)
                    self.block_mode = config.get('block_mode', 'silent')
                    self.blocked_count = config.get('blocked_count', 0)
                    self.blocked_senders = config.get('blocked_senders', {})
            except Exception as e:
                print(f"[ANTISPAM] Error loading config: {e}")
    
    def save_config(self):
        """Save anti-spam configuration"""
        try:
            config = {
                'enabled': self.enabled,
                'spam_words': list(self.spam_words),
                'case_sensitive': self.case_sensitive,
                'block_mode': self.block_mode,
                'blocked_count': self.blocked_count,
                'blocked_senders': self.blocked_senders
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"[ANTISPAM] Error saving config: {e}")
    
    def check_spam(self, content):
        """Check if content contains spam words"""
        if not content:
            return False, []
        
        check_content = content if self.case_sensitive else content.lower()
        found_words = []
        
        for spam_word in self.spam_words:
            check_word = spam_word if self.case_sensitive else spam_word.lower()
            if check_word in check_content:
                found_words.append(spam_word)
        
        return len(found_words) > 0, found_words
    
    def on_message(self, message, msg_data):
        """Check incoming messages for spam"""
        # Only check incoming messages
        if msg_data['direction'] == 'outbound':
            return False
        
        # Skip if disabled
        if not self.enabled:
            return False
        
        # Get message content
        content = msg_data.get('content', '')
        source_hash = msg_data['source_hash']
        
        # Check for spam
        is_spam, found_words = self.check_spam(content)
        
        if is_spam:
            # Update statistics
            self.blocked_count += 1
            
            normalized_hash = source_hash.replace(":", "").replace(" ", "").lower()
            if normalized_hash not in self.blocked_senders:
                self.blocked_senders[normalized_hash] = 0
            self.blocked_senders[normalized_hash] += 1
            
            self.save_config()
            
            # Get sender display
            sender_display = self.client.format_contact_display_short(source_hash)
            
            # Show alert based on mode
            if self.block_mode == 'notify':
                print(f"\n{'='*60}")
                print(f"🚫 ANTISPAM: Blocked message from {sender_display}")
                print(f"Spam words found: {', '.join(found_words)}")
                
                # Show message preview (censored)
                preview = content[:100]
                if len(content) > 100:
                    preview += "..."
                
                # Censor the spam words in preview
                censored_preview = preview
                for word in found_words:
                    if self.case_sensitive:
                        censored_preview = censored_preview.replace(word, '*' * len(word))
                    else:
                        # Case-insensitive replacement
                        import re
                        pattern = re.compile(re.escape(word), re.IGNORECASE)
                        censored_preview = pattern.sub('*' * len(word), censored_preview)
                
                print(f"Preview: {censored_preview}")
                print(f"{'='*60}")
                print("> ", end="", flush=True)
            else:
                # Silent mode - just log to console
                print(f"\n[🚫 ANTISPAM] Blocked message from {sender_display} ({', '.join(found_words)})")
                print("> ", end="", flush=True)
            
            # Block the message (don't process normally)
            return True
        
        return False
    
    def handle_command(self, cmd, parts):
        """Handle antispam commands"""
        if len(parts) < 2:
            # Show status
            status = "✅ ENABLED" if self.enabled else "❌ DISABLED"
            
            print(f"\n{'='*70}")
            print("🚫 ANTI-SPAM FILTER")
            print(f"{'='*70}")
            print(f"Status: {status}")
            print(f"Block mode: {self.block_mode.upper()}")
            print(f"Case sensitive: {'YES' if self.case_sensitive else 'NO'}")
            print(f"Spam words: {len(self.spam_words)}")
            print(f"Messages blocked: {self.blocked_count}")
            
            if self.spam_words:
                print(f"\n📝 Blocked words:")
                for word in sorted(self.spam_words):
                    print(f"  • {word}")
            
            if self.blocked_senders:
                print(f"\n📊 Top spam senders:")
                sorted_senders = sorted(self.blocked_senders.items(), key=lambda x: x[1], reverse=True)[:5]
                for hash_str, count in sorted_senders:
                    name = self.client.format_contact_display_short(hash_str)
                    print(f"  • {name}: {count} blocked")
            
            print(f"\n💡 Commands:")
            print(f"  antispam add <word>       - Add spam word")
            print(f"  antispam remove <word>    - Remove word")
            print(f"  antispam clear            - Clear all words")
            print(f"  antispam on/off           - Enable/disable")
            print(f"  antispam mode silent      - Silent blocking")
            print(f"  antispam mode notify      - Show notifications")
            print(f"  antispam case on/off      - Case sensitivity")
            print(f"  antispam stats            - Show statistics")
            print(f"  antispam reset            - Reset statistics")
            print(f"{'='*70}\n")
            return
        
        subcmd = parts[1].lower()
        
        if subcmd == 'add' and len(parts) >= 3:
            word = ' '.join(parts[2:])
            self.spam_words.add(word)
            self.save_config()
            self.client._print_success(f"Added spam word: {word}")
            print(f"Total spam words: {len(self.spam_words)}")
        
        elif subcmd == 'remove' and len(parts) >= 3:
            word = ' '.join(parts[2:])
            if word in self.spam_words:
                self.spam_words.remove(word)
                self.save_config()
                self.client._print_success(f"Removed spam word: {word}")
            else:
                self.client._print_error("Word not in spam list")
        
        elif subcmd == 'clear':
            confirm = input(f"Clear all {len(self.spam_words)} spam words? [y/N]: ").strip().lower()
            if confirm == 'y':
                count = len(self.spam_words)
                self.spam_words.clear()
                self.save_config()
                self.client._print_success(f"Cleared {count} spam words")
            else:
                print("Cancelled")
        
        elif subcmd == 'on':
            self.enabled = True
            self.save_config()
            self.client._print_success("Anti-spam filter ENABLED")
        
        elif subcmd == 'off':
            self.enabled = False
            self.save_config()
            self.client._print_success("Anti-spam filter DISABLED")
        
        elif subcmd == 'mode' and len(parts) >= 3:
            mode = parts[2].lower()
            if mode in ['silent', 'quiet']:
                self.block_mode = 'silent'
                self.save_config()
                self.client._print_success("Block mode: SILENT (minimal alerts)")
            elif mode in ['notify', 'alert', 'verbose']:
                self.block_mode = 'notify'
                self.save_config()
                self.client._print_success("Block mode: NOTIFY (show full alerts)")
            else:
                self.client._print_error("Mode must be 'silent' or 'notify'")
        
        elif subcmd == 'case' and len(parts) >= 3:
            setting = parts[2].lower()
            if setting in ['on', 'true', '1', 'yes']:
                self.case_sensitive = True
                self.save_config()
                self.client._print_success("Case sensitivity ON")
            else:
                self.case_sensitive = False
                self.save_config()
                self.client._print_success("Case sensitivity OFF")
        
        elif subcmd == 'stats':
            print(f"\n{'='*70}")
            print("📊 ANTI-SPAM STATISTICS")
            print(f"{'='*70}")
            print(f"Total messages blocked: {self.blocked_count}")
            print(f"Unique senders blocked: {len(self.blocked_senders)}")
            print(f"Active spam words: {len(self.spam_words)}")
            
            if self.blocked_senders:
                print(f"\n📈 Blocked messages by sender:")
                sorted_senders = sorted(self.blocked_senders.items(), key=lambda x: x[1], reverse=True)
                for hash_str, count in sorted_senders:
                    name = self.client.format_contact_display_short(hash_str)
                    percentage = (count / self.blocked_count * 100) if self.blocked_count > 0 else 0
                    print(f"  • {name}: {count} messages ({percentage:.1f}%)")
            
            print(f"{'='*70}\n")
        
        elif subcmd == 'reset':
            confirm = input("Reset all anti-spam statistics? [y/N]: ").strip().lower()
            if confirm == 'y':
                self.blocked_count = 0
                self.blocked_senders = {}
                self.save_config()
                self.client._print_success("Statistics reset")
            else:
                print("Cancelled")
        
        elif subcmd in ['list', 'show']:
            # Same as no arguments
            self.handle_command(cmd, [cmd])
        
        else:
            self.client._print_error(f"Unknown subcommand: {subcmd}")
            print("Use 'antispam' to see available commands")

if __name__ == '__main__':
    print("This is a plugin for LXMF Client")
    print("Place in: ./lxmf_client_storage/plugins/")
"""
Telegram Bridge Plugin for LXMF-CLI
Routes messages bidirectionally between LXMF and Telegram.
"""

import threading
import time
import requests
import json

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['tgbridge', 'tg']
        self.description = "Bridge LXMF messages to/from Telegram"

        # Bridge configuration
        self.enabled = False
        self.bot_token = None
        self.chat_id = None
        self.poll_thread = None
        self.running = False
        self.last_update_id = 0

        # Load configuration
        self._load_config()

        print("Telegram Bridge Plugin loaded!")

    def _load_config(self):
        """Load Telegram bridge configuration"""
        try:
            with open('telegram_bridge_config.json', 'r') as f:
                config = json.load(f)
                self.bot_token = config.get('bot_token')
                self.chat_id = config.get('chat_id')
                self.enabled = config.get('enabled', False)
                self.last_update_id = config.get('last_update_id', 0)
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"Error loading Telegram bridge config: {e}")

    def _save_config(self):
        """Save Telegram bridge configuration"""
        try:
            config = {
                'bot_token': self.bot_token,
                'chat_id': self.chat_id,
                'enabled': self.enabled,
                'last_update_id': self.last_update_id
            }
            with open('telegram_bridge_config.json', 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error saving Telegram bridge config: {e}")

    def _escape_markdown_v2(self, text):
        """Escape special characters for Telegram MarkdownV2"""
        # Characters that need escaping in MarkdownV2
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']

        escaped = text
        for char in special_chars:
            escaped = escaped.replace(char, f'\\{char}')

        return escaped

    def on_message(self, message, msg_data):
        """Forward incoming LXMF messages to Telegram"""
        if not self.enabled or not self.bot_token or not self.chat_id:
            return False

        try:
            sender = msg_data.get('display_name', 'Unknown')
            source_hash = msg_data.get('source_hash', '')
            title = msg_data.get('title', '')
            content = msg_data.get('content', '')

            # Format message for Telegram (plain text, formatting added by _send_telegram_message)
            if title:
                tg_message = f"📨 LXMF from {sender}\n"
                tg_message += f"Title: {title}\n"
                tg_message += f"Hash: {source_hash[:16]}...\n\n"
                tg_message += f"{content}"
            else:
                tg_message = f"📨 LXMF from {sender}\n"
                tg_message += f"Hash: {source_hash[:16]}...\n\n"
                tg_message += f"{content}"

            # Send to Telegram
            self._send_telegram_message(tg_message)

        except Exception as e:
            print(f"Error forwarding to Telegram: {e}")

        return False

    def handle_command(self, cmd, parts):
        if cmd not in ['tgbridge', 'tg']:
            return

        if len(parts) < 2:
            print("Usage: tg <start|stop|status|config|test>")
            print("  tg config <bot_token> <chat_id>")
            print("  tg start")
            print("  tg stop")
            print("  tg status")
            print("  tg test      - Test bot connection and get bot info")
            return

        action = parts[1].lower()

        if action == 'config':
            self._handle_config(parts)
        elif action == 'start':
            self._start_bridge()
        elif action == 'stop':
            self._stop_bridge()
        elif action == 'status':
            self._show_status()
        elif action == 'test':
            self._test_bot()
        else:
            print(f"Unknown action: {action}")

    def _handle_config(self, parts):
        """Configure Telegram bot"""
        if len(parts) < 3:
            print("Usage: tg config <bot_token> <chat_id>")
            print("\nGet bot token from @BotFather")
            print("Get chat ID from @userinfobot")
            return

        # lxmf-cli joins args: "tg config token chat_id" becomes ['tg', 'config', 'token chat_id']
        raw_args = parts[2]
        arg_parts = raw_args.split()

        if len(arg_parts) < 2:
            print("Usage: tg config <bot_token> <chat_id>")
            print("\nGet bot token from @BotFather")
            print("Get chat ID from @userinfobot")
            return

        self.bot_token = arg_parts[0]
        self.chat_id = arg_parts[1]
        self._save_config()

        print(f"\nTelegram bridge configured!")
        print(f"  Bot: {self.bot_token[:10]}...{self.bot_token[-10:]}")
        print(f"  Chat: {self.chat_id}")
        print(f"\nUse 'tg start' to enable\n")

    def _start_bridge(self):
        """Start the bridge"""
        if not self.bot_token or not self.chat_id:
            print("Configure bridge first: tg config")
            return

        if self.enabled and self.running:
            print("Bridge already running")
            return

        self.enabled = True
        self.running = True
        self._save_config()

        self.poll_thread = threading.Thread(
            target=self._poll_telegram,
            daemon=True
        )
        self.poll_thread.start()

        print("Telegram bridge started!")

    def _stop_bridge(self):
        """Stop the bridge"""
        if not self.enabled:
            print("Bridge not running")
            return

        self.enabled = False
        self.running = False
        self._save_config()

        print("Telegram bridge stopped")

    def _show_status(self):
        """Show status"""
        print("\n--- Telegram Bridge ---")
        print(f"  Enabled: {'Yes' if self.enabled else 'No'}")
        print(f"  Bot: {'Yes' if self.bot_token else 'No'}")
        print(f"  Chat: {'Yes' if self.chat_id else 'No'}")
        if self.bot_token:
            print(f"  Token: {self.bot_token[:10]}...{self.bot_token[-10:]}")
        if self.chat_id:
            print(f"  Chat ID: {self.chat_id}")
        print(f"  Polling: {'Active' if self.running else 'Inactive'}")
        print()

    def _test_bot(self):
        """Test bot connection and show bot info"""
        if not self.bot_token:
            print("No bot token configured. Use 'tg config' first")
            return

        print("\nTesting Telegram bot connection...\n")

        try:
            # Get bot info
            url = f"https://api.telegram.org/bot{self.bot_token}/getMe"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    bot_info = data.get('result', {})
                    print("✓ Bot connection successful!")
                    print(f"  Bot name: @{bot_info.get('username', 'unknown')}")
                    print(f"  Bot ID: {bot_info.get('id', 'unknown')}")
                    print(f"  First name: {bot_info.get('first_name', 'unknown')}")
                    print(f"  Can join groups: {'Yes' if bot_info.get('can_join_groups') else 'No'}")
                else:
                    print(f"✗ API returned error: {data}")
            else:
                try:
                    error_info = response.json()
                    print(f"✗ Connection failed: {response.status_code}")
                    print(f"  Error: {error_info.get('description', 'Unknown error')}")
                except:
                    print(f"✗ Connection failed: {response.status_code}")

            # Check webhook status
            print("\nChecking webhook status...")
            url = f"https://api.telegram.org/bot{self.bot_token}/getWebhookInfo"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    webhook_info = data.get('result', {})
                    webhook_url = webhook_info.get('url', '')

                    if webhook_url:
                        print(f"⚠️  WEBHOOK IS SET: {webhook_url}")
                        print(f"  This will cause 409 conflicts with polling!")
                        print(f"  Pending updates: {webhook_info.get('pending_update_count', 0)}")
                        print(f"\n  To fix: Use 'tg start' (it will try to clear the webhook)")
                    else:
                        print("✓ No webhook configured (good for polling)")
                        print(f"  Pending updates: {webhook_info.get('pending_update_count', 0)}")

            # Try to get updates (without long polling)
            print("\nTesting getUpdates (short poll)...")
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            params = {'timeout': 0, 'limit': 1}
            response = requests.get(url, params=params, timeout=5)

            if response.status_code == 200:
                print("✓ getUpdates works (no 409 conflict)")
            elif response.status_code == 409:
                error_info = response.json()
                print(f"✗ 409 Conflict detected!")
                print(f"  {error_info.get('description', 'Unknown error')}")
                print(f"\n  This means another bot instance is running.")
                print(f"  Check for:")
                print(f"    - Other terminal windows running lxmf-cli")
                print(f"    - Python processes with this bot token")
                print(f"    - Other bot software using the same token")
            else:
                try:
                    error_info = response.json()
                    print(f"✗ getUpdates failed: {response.status_code}")
                    print(f"  {error_info.get('description', 'Unknown error')}")
                except:
                    print(f"✗ getUpdates failed: {response.status_code}")

            print()

        except Exception as e:
            print(f"✗ Error testing bot: {e}\n")

    def _send_telegram_message(self, text):
        """Send to Telegram"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

            # Try with MarkdownV2 first, which is more strict but safer
            data = {
                'chat_id': self.chat_id,
                'text': self._escape_markdown_v2(text),
                'parse_mode': 'MarkdownV2',
                'disable_web_page_preview': True
            }
            response = requests.post(url, json=data, timeout=10)

            # If MarkdownV2 fails, retry with plain text (no formatting)
            if response.status_code != 200:
                data = {
                    'chat_id': self.chat_id,
                    'text': text,
                    'disable_web_page_preview': True
                }
                response = requests.post(url, json=data, timeout=10)

                if response.status_code != 200:
                    try:
                        error_info = response.json()
                        print(f"Telegram error {response.status_code}: {error_info.get('description', 'Unknown error')}")
                    except:
                        print(f"Telegram error: {response.status_code}")

        except Exception as e:
            print(f"Error sending to Telegram: {e}")

    def _clear_webhook_conflict(self):
        """Clear webhook to resolve 409 conflicts"""
        try:
            # Delete webhook (in case one is set)
            url = f"https://api.telegram.org/bot{self.bot_token}/deleteWebhook"
            params = {'drop_pending_updates': True}
            response = requests.post(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    print("Cleared any existing webhook")
        except Exception as e:
            print(f"Error clearing webhook: {e}")

    def _poll_telegram(self):
        """Poll for Telegram messages"""
        print("Telegram polling started")

        # Handle 409 conflict by getting pending updates first
        self._clear_webhook_conflict()

        # Wait a moment for any previous polling to fully terminate
        time.sleep(2)

        consecutive_409_errors = 0
        max_409_retries = 3

        while self.running:
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
                params = {
                    'offset': self.last_update_id + 1,
                    'timeout': 30,
                    'allowed_updates': ['message']
                }

                response = requests.get(url, params=params, timeout=35)

                if response.status_code == 200:
                    data = response.json()

                    if data.get('ok'):
                        updates = data.get('result', [])

                        # Reset 409 error counter on success
                        consecutive_409_errors = 0

                        for update in updates:
                            self.last_update_id = update['update_id']
                            self._save_config()

                            if 'message' in update:
                                self._handle_telegram_message(update['message'])
                elif response.status_code == 409:
                    # Conflict: another instance is polling or webhook is set
                    consecutive_409_errors += 1

                    try:
                        error_info = response.json()
                        error_desc = error_info.get('description', '')
                        print(f"Telegram conflict (409): {error_desc}")
                    except:
                        print(f"Telegram poll error: 409 - Another instance may be running")

                    if consecutive_409_errors >= max_409_retries:
                        print(f"\n⚠️  Persistent 409 conflicts detected!")
                        print(f"  Another bot instance is actively polling this bot token.")
                        print(f"  Please check for:")
                        print(f"    - Other terminal windows running lxmf-cli")
                        print(f"    - Python processes using this bot")
                        print(f"    - The same bot running elsewhere")
                        print(f"\n  Stopping bridge to prevent conflicts...")
                        self.enabled = False
                        self.running = False
                        self._save_config()
                        return

                    # Wait longer between retries for 409 errors
                    # This gives time for any conflicting instance to timeout
                    print(f"  Waiting 30 seconds before retry...")
                    time.sleep(30)
                else:
                    try:
                        error_info = response.json()
                        print(f"Telegram poll error {response.status_code}: {error_info.get('description', 'Unknown error')}")
                    except:
                        print(f"Telegram poll error: {response.status_code}")
                    time.sleep(5)

            except requests.exceptions.Timeout:
                # Timeout is normal for long polling, just continue
                pass
            except Exception as e:
                print(f"Telegram poll error: {e}")
                time.sleep(5)

    def _handle_telegram_message(self, message):
        """Handle Telegram message"""
        try:
            if message.get('from', {}).get('is_bot'):
                return

            text = message.get('text', '')
            if not text:
                return

            sender = message.get('from', {}).get('first_name', 'User')
            username = message.get('from', {}).get('username')

            if username:
                sender_info = f"{sender} (@{username})"
            else:
                sender_info = sender

            # Handle /send command
            if text.startswith('/send '):
                parts = text.split(' ', 2)
                if len(parts) >= 3:
                    target = parts[1]
                    msg_content = parts[2]

                    target_hash = self._resolve_lxmf_target(target)

                    if target_hash:
                        lxmf_msg = f"[Telegram: {sender_info}]\n{msg_content}"
                        self.client.send_message(target_hash, lxmf_msg)
                        self._send_telegram_message(f"Sent to {target}")
                    else:
                        self._send_telegram_message(f"Contact not found: {target}")
                else:
                    self._send_telegram_message("Usage: /send <contact> <message>")

            elif text == '/contacts':
                self._list_contacts_to_telegram()

            elif text == '/help':
                help_text = (
                    "*Commands:*\n\n"
                    "/send <contact> <msg>\n"
                    "/contacts\n"
                    "/help"
                )
                self._send_telegram_message(help_text)

        except Exception as e:
            print(f"Error handling Telegram message: {e}")

    def _resolve_lxmf_target(self, target):
        """Resolve contact to hash"""
        if target.isdigit():
            index = int(target)
            for name, data in self.client.contacts.items():
                if data.get('index') == index:
                    return data['hash']

        if target in self.client.contacts:
            return self.client.contacts[target]['hash']

        clean_hash = target.replace(':', '').replace(' ', '')
        if len(clean_hash) == 32:
            return clean_hash

        return None

    def _list_contacts_to_telegram(self):
        """List contacts on Telegram"""
        if not self.client.contacts:
            self._send_telegram_message("No contacts")
            return

        contacts_text = "*LXMF Contacts:*\n\n"

        sorted_contacts = sorted(
            self.client.contacts.items(),
            key=lambda x: x[1].get('index', 999)
        )

        for name, data in sorted_contacts[:20]:
            index = data.get('index', '?')
            contacts_text += f"`[{index}]` {name}\n"

        if len(self.client.contacts) > 20:
            contacts_text += f"\n... +{len(self.client.contacts) - 20} more"

        self._send_telegram_message(contacts_text)

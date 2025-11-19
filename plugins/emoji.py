"""
Emoji Sender Plugin for LXMF-CLI
Browse and send emoji/emoticons easily.
Supports shortcodes in messages: use $tu for thumbs up, $sun for sun emoji, etc.
"""

import re

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['emoji', 'emo', 'emoticon']
        self.description = "Browse and send emoji easily (supports $shortcodes in messages)"

        # Format: (emoji, name, shortcode)
        # Shortcodes are easy-to-type shortcuts for use in messages
        self.emojis = [
            # Essential faces (10)
            ('😊', 'happy', 'happy'),
            ('😂', 'laugh', 'lol'),
            ('😍', 'love', 'love'),
            ('😎', 'cool', 'cool'),
            ('😢', 'sad', 'sad'),
            ('😭', 'cry', 'cry'),
            ('😡', 'angry', 'angry'),
            ('😱', 'shock', 'shock'),
            ('🤔', 'think', 'think'),
            ('😴', 'sleep', 'sleep'),

            # Key gestures (8)
            ('👍', 'thumbsup', 'tu'),
            ('👎', 'thumbsdown', 'td'),
            ('👌', 'ok', 'ok'),
            ('✌️', 'peace', 'peace'),
            ('🤝', 'shake', 'shake'),
            ('👋', 'wave', 'wave'),
            ('🙏', 'pray', 'pray'),
            ('💪', 'strong', 'strong'),

            # Hearts & symbols (8)
            ('❤️', 'heart', 'heart'),
            ('💔', 'broken', 'broken'),
            ('💯', 'hundo', '100'),
            ('🔥', 'fire', 'fire'),
            ('⚡', 'zap', 'zap'),
            ('✨', 'sparkle', 'sparkle'),
            ('⭐', 'star', 'star'),
            ('💫', 'dizzy', 'dizzy'),

            # Common animals (6)
            ('🐶', 'dog', 'dog'),
            ('🐱', 'cat', 'cat'),
            ('🐻', 'bear', 'bear'),
            ('🦊', 'fox', 'fox'),
            ('🐧', 'penguin', 'penguin'),
            ('🦄', 'unicorn', 'unicorn'),

            # Popular food (8)
            ('🍕', 'pizza', 'pizza'),
            ('🍔', 'burger', 'burger'),
            ('🍺', 'beer', 'beer'),
            ('☕', 'coffee', 'coffee'),
            ('🍰', 'cake', 'cake'),
            ('🍎', 'apple', 'apple'),
            ('🍉', 'melon', 'melon'),
            ('🌮', 'taco', 'taco'),

            # Activities (6)
            ('⚽', 'soccer', 'soccer'),
            ('🏀', 'bball', 'bball'),
            ('🎮', 'game', 'game'),
            ('🎵', 'music', 'music'),
            ('🎬', 'movie', 'movie'),
            ('📚', 'book', 'book'),

            # Travel & vehicles (6)
            ('🚗', 'car', 'car'),
            ('✈️', 'plane', 'plane'),
            ('🚀', 'rocket', 'rocket'),
            ('🏠', 'home', 'home'),
            ('🌍', 'earth', 'earth'),
            ('🗺️', 'map', 'map'),

            # Tech & objects (6)
            ('💻', 'laptop', 'laptop'),
            ('📱', 'phone', 'phone'),
            ('⌚', 'watch', 'watch'),
            ('💡', 'idea', 'idea'),
            ('🔧', 'tool', 'tool'),
            ('🔋', 'battery', 'bat'),

            # Nature (6)
            ('🌞', 'sun', 'sun'),
            ('🌙', 'moon', 'moon'),
            ('🌈', 'rainbow', 'rainbow'),
            ('🌸', 'flower', 'flower'),
            ('🌲', 'tree', 'tree'),
            ('🌊', 'ocean', 'ocean'),

            # Extra useful (6)
            ('🎉', 'party', 'party'),
            ('🎁', 'gift', 'gift'),
            ('💰', 'money', 'money'),
            ('⏰', 'clock', 'clock'),
            ('📅', 'calendar', 'cal'),
            ('✅', 'check', 'check'),
        ]

        # Build shortcode lookup dictionary for fast access
        self.shortcode_map = {}
        for emoji, name, shortcode in self.emojis:
            self.shortcode_map[shortcode] = emoji
            # Also allow full name as shortcode
            if name != shortcode:
                self.shortcode_map[name] = emoji

        # Hook into send message to intercept and replace emojis
        self._hook_send_message()

        print(f"✓ Emoji plugin loaded! {len(self.emojis)} emojis with shortcodes")
    
    def _hook_send_message(self):
        """Hook into client's send_message to replace emoji shortcodes"""
        # Store original send_message
        self._original_send_message = self.client.send_message

        # Create wrapper function
        def send_message_with_emoji_replacement(dest_hash, content, title=None, fields=None):
            # Replace emoji shortcodes in content
            if content:
                content = self.replace_shortcodes(content)
            # Replace emoji shortcodes in title
            if title:
                title = self.replace_shortcodes(title)
            # Call original send_message
            return self._original_send_message(dest_hash, content, title, fields)

        # Replace client's send_message with our wrapper
        self.client.send_message = send_message_with_emoji_replacement

    def replace_shortcodes(self, text):
        """Replace $shortcode with actual emojis in text"""
        # Pattern: $word (alphanumeric)
        def replacer(match):
            shortcode = match.group(1).lower()
            return self.shortcode_map.get(shortcode, match.group(0))

        # Replace all $shortcode patterns
        return re.sub(r'\$([a-zA-Z0-9]+)', replacer, text)

    def on_message(self, message, msg_data):
        """Not used by emoji plugin"""
        return False

    def handle_command(self, cmd, parts):
        if len(parts) >= 2:
            subcmd = parts[1].lower()

            # Check for subcommands first
            if subcmd == 'search':
                if len(parts) < 3:
                    print("\nUsage: emoji search <keyword>")
                    return
                keyword = ' '.join(parts[2:])
                self._search_emoji(keyword)
                return

            elif subcmd == 'random':
                recipient = None
                if len(parts) >= 3:
                    recipient = ' '.join(parts[2:])
                self._send_random_emoji(recipient)
                return

            elif subcmd == 'list':
                self._list_shortcodes()
                return

            # Check if it's emoji indices (numbers or ranges)
            # Support: emo 0 5 12  OR  emo 0-5  OR  emo 0,3,5
            else:
                recipient = None
                indices = []

                # Parse all arguments to separate indices from recipient
                args = parts[1:]
                recipient_start_idx = None

                for i, arg in enumerate(args):
                    # Check if this looks like an index pattern (number, range, or comma-separated)
                    if re.match(r'^[\d,\-]+$', arg):
                        # Parse indices from this arg
                        indices.extend(self._parse_indices(arg))
                    else:
                        # This is the recipient
                        recipient_start_idx = i
                        break

                if recipient_start_idx is not None:
                    recipient = ' '.join(args[recipient_start_idx:])

                if indices:
                    self._send_multiple_emojis(indices, recipient)
                    return

        # Default: show all emojis
        self._show_emojis()

    def _parse_indices(self, arg):
        """Parse emoji indices from string like '0', '0-5', '0,3,5' """
        indices = []

        # Handle comma-separated
        parts = arg.split(',')

        for part in parts:
            # Handle range (e.g., '0-5')
            if '-' in part:
                try:
                    start, end = part.split('-')
                    start_idx = int(start)
                    end_idx = int(end)
                    indices.extend(range(start_idx, end_idx + 1))
                except ValueError:
                    pass
            else:
                # Single number
                try:
                    indices.append(int(part))
                except ValueError:
                    pass

        return indices
    
    def _show_emojis(self):
        """Show all emojis in 2 columns with shortcodes"""
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 100)
        except:
            width = 100

        print(f"\n{'='*width}")
        print(f"😊 EMOJI PICKER ({len(self.emojis)} emojis)")
        print(f"{'='*width}\n")

        # Show in 2 columns with shortcodes
        half = (len(self.emojis) + 1) // 2

        for i in range(half):
            # Left column
            left_idx = i
            left_emoji, left_name, left_code = self.emojis[left_idx]
            left_str = f"[{left_idx:2d}] {left_emoji}  ${left_code:<12} {left_name:<12}"

            # Right column (if exists)
            right_idx = i + half
            if right_idx < len(self.emojis):
                right_emoji, right_name, right_code = self.emojis[right_idx]
                right_str = f"[{right_idx:2d}] {right_emoji}  ${right_code:<12} {right_name:<12}"
                print(f"{left_str}  {right_str}")
            else:
                print(left_str)

        print(f"\n{'='*width}")
        print(f"💡 Quick send:")
        print(f"   Single: emo 0              Multiple: emo 0 5 10")
        print(f"   Range:  emo 0-5            Combo:    emo 0,5,10-15")
        print(f"   To someone: emo 10 alice   Search:   emo search love")
        print(f"   Random: emo random         Shortcodes: emo list")
        print(f"\n💬 Use in messages:")
        print(f"   Type: s alice Hey $tu $fire looking good!")
        print(f"   Sends: Hey 👍 🔥 looking good!")

        print(f"\n📬 Last contact: ", end="")
        if self.client.last_sender_hash:
            print(self.client.format_contact_display_short(self.client.last_sender_hash))
        else:
            print("None (specify recipient)")

        print(f"{'='*width}\n")

    def _list_shortcodes(self):
        """List all available shortcodes"""
        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 100)
        except:
            width = 100

        print(f"\n{'='*width}")
        print(f"🔤 EMOJI SHORTCODES")
        print(f"{'='*width}\n")
        print("Use $shortcode in any message to insert emojis!\n")

        # Group by category
        categories = [
            ("Faces", 0, 10),
            ("Gestures", 10, 18),
            ("Hearts & Symbols", 18, 26),
            ("Animals", 26, 32),
            ("Food", 32, 40),
            ("Activities", 40, 46),
            ("Travel", 46, 52),
            ("Tech", 52, 58),
            ("Nature", 58, 64),
            ("Extras", 64, 70),
        ]

        for category_name, start, end in categories:
            print(f"\n{category_name}:")
            items = []
            for i in range(start, min(end, len(self.emojis))):
                emoji, name, code = self.emojis[i]
                items.append(f"  ${code:<10} {emoji}  {name}")

            # Print in 2 columns
            half = (len(items) + 1) // 2
            for i in range(half):
                left = items[i]
                if i + half < len(items):
                    right = items[i + half]
                    print(f"{left:<40}{right}")
                else:
                    print(left)

        print(f"\n{'='*width}")
        print(f"💡 Example: s alice Hey $tu great work $fire$party")
        print(f"   Result:   Hey 👍 great work 🔥🎉")
        print(f"{'='*width}\n")
    
    def _search_emoji(self, keyword):
        """Search for emoji by keyword or shortcode"""
        keyword_lower = keyword.lower()
        results = []

        for i, (emoji, name, code) in enumerate(self.emojis):
            if keyword_lower in name.lower() or keyword_lower in code.lower():
                results.append((i, emoji, name, code))

        if not results:
            print(f"\n🔍 No emojis found for: '{keyword}'\n")
            return

        import shutil
        try:
            width = min(shutil.get_terminal_size().columns, 100)
        except:
            width = 100

        print(f"\n{'='*width}")
        print(f"🔍 SEARCH: '{keyword}' ({len(results)} found)")
        print(f"{'='*width}\n")

        for idx, emoji, name, code in results:
            print(f"[{idx:2d}] {emoji}  ${code:<12} {name}")

        print(f"\n{'='*width}")
        print(f"💡 Send: emo <#> [contact]  |  Use in message: $shortcode")
        print(f"{'='*width}\n")

    def _send_multiple_emojis(self, indices, recipient=None):
        """Send multiple emojis"""
        # Validate all indices first
        valid_emojis = []
        invalid = []

        for idx in indices:
            if 0 <= idx < len(self.emojis):
                emoji, name, code = self.emojis[idx]
                valid_emojis.append((idx, emoji, name))
            else:
                invalid.append(idx)

        if invalid:
            print(f"\n⚠️  Invalid emoji indices: {invalid}")
            print(f"Valid range: 0-{len(self.emojis)-1}\n")
            if not valid_emojis:
                return

        # Determine recipient
        if recipient:
            dest_hash = self.client.resolve_contact_or_hash(recipient)
            if not dest_hash:
                self.client._print_error(f"Unknown contact: {recipient}")
                return
        else:
            if not self.client.last_sender_hash:
                self.client._print_error("No recent conversation")
                print("Specify recipient: emo <#> <contact>")
                return
            dest_hash = self.client.last_sender_hash

        recipient_name = self.client.format_contact_display_short(dest_hash)

        # Build message with all emojis
        emoji_string = ' '.join([emoji for _, emoji, _ in valid_emojis])
        emoji_names = ', '.join([name for _, _, name in valid_emojis])

        # Send the emojis
        print(f"\n📤 Sending {len(valid_emojis)} emoji(s) → {recipient_name}")
        print(f"   {emoji_string}")
        print(f"   ({emoji_names})")

        success = self.client.send_message(dest_hash, emoji_string)

        if success:
            print(f"✓ Sent!\n")

    def _send_emoji(self, emoji_idx, recipient=None):
        """Send a single emoji (legacy support)"""
        self._send_multiple_emojis([emoji_idx], recipient)

    def _send_random_emoji(self, recipient=None):
        """Send a random emoji"""
        import random
        emoji_idx = random.randint(0, len(self.emojis) - 1)
        emoji, name, code = self.emojis[emoji_idx]

        print(f"\n🎲 Random: {emoji} ({name})")
        self._send_multiple_emojis([emoji_idx], recipient)

if __name__ == '__main__':
    print("This is a plugin for LXMF Client")
    print("Place in: ./lxmf_client_storage/plugins/")

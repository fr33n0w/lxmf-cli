"""
Search Plugin for LXMF-CLI
Allows searching contacts (-c), messages (-m), or announced peers (-p) by keyword.
Supports regex (--regex) and searches contacts by name or hash, peers by display name or hash.
"""

import re
from datetime import datetime

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['search', 'se']
        self.description = "Search contacts (-c), peers (-p), or messages (-m) by keyword (supports --regex)"
        print("Search Plugin loaded!")

    def on_message(self, message, msg_data):
        return False

    def handle_command(self, cmd, parts):
        if cmd not in ['search', 'se']:
            return

        if len(parts) < 2:
            print("Usage: se <term> | se -c <term> | se -p <term> | se -m <term> [--regex]")
            return

        # Check if regex flag is present
        use_regex = '--regex' in parts
        if use_regex:
            parts.remove('--regex')

        # Check if first argument is a flag
        flag = parts[1] if len(parts) > 1 and parts[1].startswith('-') else None

        if flag:
            # Flag-based search
            if len(parts) < 3:
                print("Usage: se <term> | se -c <term> | se -p <term> | se -m <term> [--regex]")
                return

            search_term = " ".join(parts[2:])

            if flag == '-c':
                self.search_contacts(search_term, use_regex)
            elif flag == '-p':
                self.search_peers(search_term, use_regex)
            elif flag == '-m':
                self.search_messages(search_term, use_regex)
            else:
                print("Invalid flag. Use -c for contacts, -p for peers, or -m for messages.")
        else:
            # Overall search (no flag)
            search_term = " ".join(parts[1:])
            self.search_all(search_term, use_regex)

    def search_contacts(self, term, use_regex=False):
        """Search through contacts by name or hash"""
        results = []

        # Prepare regex or lowercase term
        regex = re.compile(term, re.IGNORECASE) if use_regex else None
        term_lower = term.lower()

        # Search in contacts: {name: {'hash': ..., 'index': ...}}
        for contact_name, contact_data in self.client.contacts.items():
            contact_hash = contact_data.get('hash', '')
            contact_index = contact_data.get('index', '?')

            # Match against contact name or hash
            if use_regex:
                if regex.search(contact_name) or regex.search(contact_hash):
                    results.append((contact_index, contact_name, contact_hash))
            else:
                if term_lower in contact_name.lower() or term_lower in contact_hash.lower():
                    results.append((contact_index, contact_name, contact_hash))

        if results:
            print(f"\n{self.client.Fore.GREEN}Contacts found ({len(results)}):{self.client.Style.RESET_ALL}")
            # Sort by index for consistent display
            results.sort(key=lambda x: x[0])
            for index, name, contact_hash in results:
                print(f"  [{index}] {name} - {contact_hash}")
            print(f"\n💡 Send: 's <#> <msg>' | Remove: 'rm <#>'")
        else:
            print(f"{self.client.Fore.YELLOW}No contacts matched your search.{self.client.Style.RESET_ALL}")

    def search_peers(self, term, use_regex=False):
        """Search through announced peers by display name (nick) or hash"""
        results = []

        # Prepare regex or lowercase term
        regex = re.compile(term, re.IGNORECASE) if use_regex else None
        term_lower = term.lower()

        # Search in announced_peers: {hash: {'display_name': ..., 'index': ..., 'last_seen': ...}}
        for peer_hash, peer_data in self.client.announced_peers.items():
            peer_name = peer_data.get('display_name', '')
            peer_index = peer_data.get('index', '?')

            # Match against peer display name (nick) or hash
            if use_regex:
                if regex.search(peer_name) or regex.search(peer_hash):
                    results.append((peer_index, peer_name, peer_hash))
            else:
                if term_lower in peer_name.lower() or term_lower in peer_hash.lower():
                    results.append((peer_index, peer_name, peer_hash))

        if results:
            print(f"\n{self.client.Fore.GREEN}Announced peers found ({len(results)}):{self.client.Style.RESET_ALL}")
            # Sort by index for consistent display
            results.sort(key=lambda x: x[0])
            for index, name, peer_hash in results:
                # Check if peer is saved in contacts (normalize hash by removing <>)
                clean_hash = peer_hash.replace('<', '').replace('>', '')
                is_saved = any(contact_data.get('hash') == clean_hash for contact_data in self.client.contacts.values())
                status_icon = "💾" if is_saved else "📌"
                print(f"  {status_icon} [{index}] {name} - {peer_hash}")
            print(f"\n💡 Send: 'sp <#> <msg>' | Add: 'ap <#> <name>' | 💾=saved 📌=unsaved")
        else:
            print(f"{self.client.Fore.YELLOW}No announced peers matched your search.{self.client.Style.RESET_ALL}")

    def search_messages(self, term, use_regex=False):
        """Search through stored messages by content or title"""
        results = []

        # Prepare regex or lowercase term
        regex = re.compile(term, re.IGNORECASE) if use_regex else None
        term_lower = term.lower()

        for idx, msg in enumerate(self.client.messages):
            content = msg.get('content', '') or ''
            title = msg.get('title', '') or ''
            display_name = msg.get('display_name', '') or ''
            timestamp = msg.get('timestamp', '') or ''
            source_hash = msg.get('source_hash', '') or ''

            # Match against message content or title
            matched = False
            if use_regex:
                matched = regex.search(content) or regex.search(title)
            else:
                matched = term_lower in content.lower() or term_lower in title.lower()

            if matched:
                # Format: index, timestamp, sender, content preview, full msg
                content_preview = content[:80] + "..." if len(content) > 80 else content
                sender_name = display_name or source_hash
                # Convert timestamp to readable format
                try:
                    dt = datetime.fromtimestamp(float(timestamp))
                    readable_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    readable_time = str(timestamp)
                results.append((idx, readable_time, sender_name, title, content_preview, msg))

        if results:
            print(f"\n{self.client.Fore.GREEN}Messages found ({len(results)}):{self.client.Style.RESET_ALL}")
            for i, (idx, timestamp, sender, title, content, msg) in enumerate(results):
                title_str = f" [{title}]" if title else ""
                print(f"  {i+1}. [{idx}] {timestamp} - {sender}{title_str}")
                print(f"      {content}")

            # Prompt for reply
            try:
                print(f"\n💡 Reply to message (1-{len(results)}) or press Enter to skip: ", end="")
                choice = input().strip()

                if choice:
                    selection = int(choice) - 1
                    if 0 <= selection < len(results):
                        _, _, sender, _, _, msg = results[selection]
                        source_hash = msg.get('source_hash', '')

                        if not source_hash:
                            print(f"{self.client.Fore.RED}Cannot reply: No source hash found in message.{self.client.Style.RESET_ALL}")
                        else:
                            print(f"Enter your reply to {sender}: ", end="")
                            reply_msg = input().strip()

                            if reply_msg:
                                # Send reply using the source hash
                                self.client.send_message(source_hash, reply_msg)
                                print(f"{self.client.Fore.GREEN}✓ Reply sent to {sender}!{self.client.Style.RESET_ALL}")
                    else:
                        print(f"{self.client.Fore.RED}Invalid selection.{self.client.Style.RESET_ALL}")
            except ValueError:
                print(f"{self.client.Fore.RED}Invalid input.{self.client.Style.RESET_ALL}")
            except Exception as e:
                print(f"{self.client.Fore.RED}Error: {e}{self.client.Style.RESET_ALL}")
        else:
            print(f"{self.client.Fore.YELLOW}No messages matched your search.{self.client.Style.RESET_ALL}")

    def search_all(self, term, use_regex=False):
        """Search through contacts, peers, and messages"""
        print(f"\n{self.client.Fore.CYAN}Searching everywhere for: '{term}'{self.client.Style.RESET_ALL}")

        # Search contacts
        contact_results = []
        regex = re.compile(term, re.IGNORECASE) if use_regex else None
        term_lower = term.lower()

        for contact_name, contact_data in self.client.contacts.items():
            contact_hash = contact_data.get('hash', '')
            contact_index = contact_data.get('index', '?')

            if use_regex:
                if regex.search(contact_name) or regex.search(contact_hash):
                    contact_results.append((contact_index, contact_name, contact_hash))
            else:
                if term_lower in contact_name.lower() or term_lower in contact_hash.lower():
                    contact_results.append((contact_index, contact_name, contact_hash))

        if contact_results:
            print(f"\n{self.client.Fore.GREEN}📇 Contacts ({len(contact_results)}):{self.client.Style.RESET_ALL}")
            contact_results.sort(key=lambda x: x[0])
            for index, name, contact_hash in contact_results:
                print(f"  [{index}] {name} - {contact_hash}")

        # Search peers
        peer_results = []
        for peer_hash, peer_data in self.client.announced_peers.items():
            peer_name = peer_data.get('display_name', '')
            peer_index = peer_data.get('index', '?')

            if use_regex:
                if regex.search(peer_name) or regex.search(peer_hash):
                    peer_results.append((peer_index, peer_name, peer_hash))
            else:
                if term_lower in peer_name.lower() or term_lower in peer_hash.lower():
                    peer_results.append((peer_index, peer_name, peer_hash))

        if peer_results:
            print(f"\n{self.client.Fore.GREEN}📡 Announced Peers ({len(peer_results)}):{self.client.Style.RESET_ALL}")
            peer_results.sort(key=lambda x: x[0])
            for index, name, peer_hash in peer_results:
                # Check if peer is saved in contacts (normalize hash by removing <>)
                clean_hash = peer_hash.replace('<', '').replace('>', '')
                is_saved = any(contact_data.get('hash') == clean_hash for contact_data in self.client.contacts.values())
                status_icon = "💾" if is_saved else "📌"
                print(f"  {status_icon} [{index}] {name} - {peer_hash}")

        # Search messages
        message_results = []
        for idx, msg in enumerate(self.client.messages):
            content = msg.get('content', '') or ''
            title = msg.get('title', '') or ''
            display_name = msg.get('display_name', '') or ''
            timestamp = msg.get('timestamp', '') or ''
            source_hash = msg.get('source_hash', '') or ''

            matched = False
            if use_regex:
                matched = regex.search(content) or regex.search(title)
            else:
                matched = term_lower in content.lower() or term_lower in title.lower()

            if matched:
                content_preview = content[:60] + "..." if len(content) > 60 else content
                sender_name = display_name or source_hash
                # Convert timestamp to readable format
                try:
                    dt = datetime.fromtimestamp(float(timestamp))
                    readable_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    readable_time = str(timestamp)
                message_results.append((idx, readable_time, sender_name, title, content_preview))

        if message_results:
            print(f"\n{self.client.Fore.GREEN}💬 Messages ({len(message_results)}):{self.client.Style.RESET_ALL}")
            for idx, timestamp, sender, title, content in message_results[:5]:  # Show max 5 messages
                title_str = f" [{title}]" if title else ""
                print(f"  [{idx}] {timestamp} - {sender}{title_str}")
                print(f"      {content}")
            if len(message_results) > 5:
                print(f"  ... and {len(message_results) - 5} more. Use 'se -m {term}' to see all.")

        # Summary
        total = len(contact_results) + len(peer_results) + len(message_results)
        if total > 0:
            print(f"\n{self.client.Fore.CYAN}Total: {total} result(s) found{self.client.Style.RESET_ALL}")
        else:
            print(f"\n{self.client.Fore.YELLOW}No results found for '{term}'{self.client.Style.RESET_ALL}")

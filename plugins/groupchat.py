"""
Group Chat Plugin for LXMF-CLI
Create and manage group conversations with automatic message redistribution.
Messages received from group members are automatically forwarded to all other members.
Messages are tagged with [Group: name] prefix for easy identification.
"""

import json
import time
import sys
import io
from datetime import datetime

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['group', 'gc']
        self.description = "Create and manage group chats with auto-forwarding"

        # Group storage: {group_name: {'members': [hash1, hash2], 'created': timestamp, 'relay': bool}}
        self.groups = {}

        # Load saved groups
        self._load_groups()

        # Set default relay to True for all groups
        for group_data in self.groups.values():
            if 'relay' not in group_data:
                group_data['relay'] = True

        print("Group Chat Plugin loaded!")

    def _send_message_silent(self, dest_hash, content, title=None, fields=None):
        """Send message while suppressing client's output"""
        # Temporarily redirect stdout to suppress the client's "Sending to:" messages
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            result = self.client.send_message(dest_hash, content, title, fields)
        finally:
            sys.stdout = old_stdout
        return result

    def _load_groups(self):
        """Load saved groups from file"""
        try:
            with open('groupchat_config.json', 'r') as f:
                self.groups = json.load(f)
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"Error loading groups: {e}")

    def _save_groups(self):
        """Save groups to file"""
        try:
            with open('groupchat_config.json', 'w') as f:
                json.dump(self.groups, f, indent=2)
        except Exception as e:
            print(f"Error saving groups: {e}")

    def _resolve_members(self, member_specs):
        """
        Resolve member specifications to hashes.
        Supports: contact names, -c <index>, -p <index>, direct hashes, bare indices
        Returns: (list of valid hashes, list of invalid specs)
        """
        member_hashes = []
        invalid = []
        i = 0

        while i < len(member_specs):
            spec = member_specs[i]

            # Handle flags
            if spec == '-c':
                # Contact by index
                if i + 1 < len(member_specs) and member_specs[i + 1].isdigit():
                    contact_idx = int(member_specs[i + 1])
                    found = False
                    for name, data in self.client.contacts.items():
                        if data.get('index') == contact_idx:
                            hash_val = data['hash']
                            if hash_val not in member_hashes:
                                member_hashes.append(hash_val)
                            found = True
                            break
                    if not found:
                        invalid.append(f"-c {contact_idx}")
                    i += 2
                else:
                    invalid.append('-c')
                    i += 1

            elif spec == '-p':
                # Peer by index
                if i + 1 < len(member_specs) and member_specs[i + 1].isdigit():
                    peer_idx = int(member_specs[i + 1])
                    found = False
                    for peer_hash, peer_data in self.client.announced_peers.items():
                        if peer_data.get('index') == peer_idx:
                            clean_hash = peer_hash.replace('<', '').replace('>', '')
                            if clean_hash not in member_hashes:
                                member_hashes.append(clean_hash)
                            found = True
                            break
                    if not found:
                        invalid.append(f"-p {peer_idx}")
                    i += 2
                else:
                    invalid.append('-p')
                    i += 1

            # Check if it's a bare number (treat as contact index)
            elif spec.isdigit():
                contact_idx = int(spec)
                found = False
                for name, data in self.client.contacts.items():
                    if data.get('index') == contact_idx:
                        hash_val = data['hash']
                        if hash_val not in member_hashes:
                            member_hashes.append(hash_val)
                        found = True
                        break
                if not found:
                    invalid.append(f"#{contact_idx}")
                i += 1

            else:
                # Try as contact name or direct hash
                contact_hash = self.client.resolve_contact_or_hash(spec)
                if contact_hash:
                    if contact_hash not in member_hashes:
                        member_hashes.append(contact_hash)
                else:
                    invalid.append(spec)
                i += 1

        return member_hashes, invalid

    def on_message(self, message, msg_data):
        """Intercept messages from group members and relay to all other members"""
        source_hash = msg_data.get('source_hash', '')
        content = msg_data.get('content', '')

        if not source_hash or not content:
            return False

        # Normalize source hash - remove angle brackets if present
        clean_source_hash = source_hash.replace('<', '').replace('>', '')

        # Handle remote commands first (commands start with /)
        if content.startswith('/'):
            return self._handle_remote_command(clean_source_hash, content, msg_data)

        # Skip messages that are already group-relayed (to prevent loops)
        # Group messages have the format: 💬 [Group: name] sender: content
        if content.startswith('💬 [Group: ') and '] ' in content:
            return False  # Don't relay group messages again

        # Check if message is from any group member
        for group_name, group_data in self.groups.items():
            # Skip if relay is disabled for this group
            if not group_data.get('relay', True):
                continue

            members = group_data.get('members', [])

            if clean_source_hash in members:
                # This is a message from a group member - relay to all others
                sender_name = msg_data.get('display_name', 'Unknown')

                # Create relayed message with group tag and sender name
                relayed_message = f"💬 [Group: {group_name}] {sender_name}: {content}"

                print(f"\n📤 Relaying group message to {len(members)-1} members...")

                # Send to all other members (not the sender)
                success_count = 0
                for member_hash in members:
                    if member_hash != clean_source_hash:
                        try:
                            # Get member name for display
                            member_name = None
                            for name, data in self.client.contacts.items():
                                if data.get('hash') == member_hash:
                                    member_name = name
                                    break

                            display_name = member_name or member_hash[:16]

                            # Send the relayed message (silently)
                            self._send_message_silent(member_hash, relayed_message)
                            print(f"  ✓ {display_name}")
                            success_count += 1
                        except Exception as e:
                            print(f"  ✗ {member_hash[:16]}: {e}")

                print(f"Relayed to {success_count}/{len(members)-1} members\n")

                # Don't break - message could belong to multiple groups
                # Continue checking other groups

        return False  # Don't suppress message display (show the original message)

    def _handle_remote_command(self, sender_hash, content, msg_data):
        """Handle remote commands sent by users via messages"""
        sender_name = msg_data.get('display_name', 'Unknown')

        # Parse command
        parts = content.strip().split()
        if not parts:
            return False

        cmd = parts[0].lower()

        # /grouplist - List available groups
        if cmd == '/grouplist':
            self._remote_list_groups(sender_hash, sender_name)
            return True  # Suppress display of command message

        # /groupjoin <groupname> - Join a group
        elif cmd == '/groupjoin':
            if len(parts) < 2:
                self._send_message_silent(sender_hash,
                    "Usage: /groupjoin <groupname>\nUse /grouplist to see available groups")
            else:
                group_name = parts[1]
                self._remote_join_group(sender_hash, sender_name, group_name)
            return True

        # /groupleave <groupname> - Leave a group
        elif cmd == '/groupleave':
            if len(parts) < 2:
                self._send_message_silent(sender_hash,
                    "Usage: /groupleave <groupname>")
            else:
                group_name = parts[1]
                self._remote_leave_group(sender_hash, sender_name, group_name)
            return True

        # /grouphelp - Show help
        elif cmd == '/grouphelp':
            self._remote_help(sender_hash)
            return True

        # Not a recognized command, let it process normally
        return False

    def _remote_list_groups(self, sender_hash, sender_name):
        """Send list of available groups to requester"""
        print(f"\n📋 Group list request from {sender_name}")

        if not self.groups:
            self._send_message_silent(sender_hash, "No groups available on this server.")
            return

        # Build group list message
        msg_lines = ["📋 Available Groups:\n"]

        for group_name, group_data in sorted(self.groups.items()):
            members = group_data.get('members', [])
            member_count = len(members)

            # Check if user is already a member
            is_member = sender_hash in members
            status = "✓ Joined" if is_member else ""

            msg_lines.append(f"  • {group_name} ({member_count} members) {status}")

        msg_lines.append("\nCommands:")
        msg_lines.append("  /groupjoin <name> - Join a group")
        msg_lines.append("  /groupleave <name> - Leave a group")

        self._send_message_silent(sender_hash, "\n".join(msg_lines))
        print(f"  ✓ Sent group list")

    def _remote_join_group(self, sender_hash, sender_name, group_name):
        """Add user to a group remotely"""
        print(f"\n➕ Join request from {sender_name} for '{group_name}'")

        # Check if group exists
        if group_name not in self.groups:
            self._send_message_silent(sender_hash,
                f"❌ Group '{group_name}' not found.\nUse /grouplist to see available groups.")
            print(f"  ✗ Group not found")
            return

        members = self.groups[group_name]['members']

        # Check if already a member
        if sender_hash in members:
            self._send_message_silent(sender_hash,
                f"ℹ️ You are already a member of '{group_name}'")
            print(f"  ℹ Already a member")
            return

        # Add to group
        members.append(sender_hash)
        self._save_groups()

        # Confirm to user
        self._send_message_silent(sender_hash,
            f"✅ You have joined '{group_name}'!\nYou will now receive messages from this group.")

        # Announce to other group members
        announcement = f"💬 [Group: {group_name}] ChatServer: {sender_name} has joined the group!"
        for member_hash in members:
            if member_hash != sender_hash:
                try:
                    self._send_message_silent(member_hash, announcement)
                except:
                    pass

        print(f"  ✓ Added to '{group_name}' ({len(members)} members)")

    def _remote_leave_group(self, sender_hash, sender_name, group_name):
        """Remove user from a group remotely"""
        print(f"\n➖ Leave request from {sender_name} for '{group_name}'")

        # Check if group exists
        if group_name not in self.groups:
            self._send_message_silent(sender_hash,
                f"❌ Group '{group_name}' not found.")
            print(f"  ✗ Group not found")
            return

        members = self.groups[group_name]['members']

        # Check if member
        if sender_hash not in members:
            self._send_message_silent(sender_hash,
                f"ℹ️ You are not a member of '{group_name}'")
            print(f"  ℹ Not a member")
            return

        # Remove from group
        members.remove(sender_hash)
        self._save_groups()

        # Confirm to user
        self._send_message_silent(sender_hash,
            f"✅ You have left '{group_name}'")

        # Announce to remaining members
        if members:  # Only if there are still members
            announcement = f"💬 [Group: {group_name}] ChatServer: {sender_name} has left the group."
            for member_hash in members:
                try:
                    self._send_message_silent(member_hash, announcement)
                except:
                    pass

        print(f"  ✓ Removed from '{group_name}' ({len(members)} members remaining)")

    def _remote_help(self, sender_hash):
        """Send help information to requester"""
        help_text = """🤖 Group Chat Commands:

/grouplist
  - List all available groups

/groupjoin <groupname>
  - Join a group to receive messages

/groupleave <groupname>
  - Leave a group

/grouphelp
  - Show this help message

After joining a group, any message you send to this server will be relayed to all group members!"""

        self._send_message_silent(sender_hash, help_text)

    def handle_command(self, cmd, parts):
        if cmd not in ['group', 'gc']:
            return

        if len(parts) < 2:
            self._show_help()
            return

        action = parts[1].lower()

        if action == 'create':
            self._create_group(parts)
        elif action == 'list':
            self._list_groups()
        elif action in ['add', 'addmember']:
            self._add_member(parts)
        elif action in ['remove', 'rm', 'removemember']:
            self._remove_member(parts)
        elif action in ['delete', 'del']:
            self._delete_group(parts)
        elif action == 'info':
            self._show_group_info(parts)
        elif action in ['send', 's']:
            self._send_to_group(parts)
        elif action == 'rename':
            self._rename_group(parts)
        elif action == 'relay':
            self._toggle_relay(parts)
        else:
            self._show_help()

    def _show_help(self):
        """Show help message"""
        print("\n" + "="*70)
        print("GROUP CHAT")
        print("="*70)
        print("\nManage Groups:")
        print("  gc create <name> <member> [member2] ...      - Create new group")
        print("  gc list                                      - List all groups")
        print("  gc info <name>                               - Show group details")
        print("  gc delete <name>                             - Delete group")
        print("  gc rename <old> <new>                        - Rename group")
        print("  gc relay <name> <on|off>                     - Toggle auto-relay")
        print("\nManage Members:")
        print("  gc add <group> <member> [member2] ...        - Add members")
        print("  gc remove <group> <member> [member2] ...     - Remove members")
        print("\nSend Messages:")
        print("  gc send <group> <message>                    - Send to group")
        print("  gc s <group> <message>                       - Send to group (short)")
        print("\nMember Specification:")
        print("  <member> can be:")
        print("    - Contact name: alice")
        print("    - Contact index: 5  (automatically uses contact #5)")
        print("    - Contact flag: -c 5")
        print("    - Peer flag: -p 10")
        print("    - Direct hash: 4eb4d4d592081a55cac5a479c3701d90")
        print("\nExamples:")
        print("  gc create friends alice bob charlie      (by name)")
        print("  gc create team 2 5 12                    (contacts #2, #5, #12)")
        print("  gc add friends david 7 -p 10             (name, contact #7, peer #10)")
        print("  gc relay friends off                     (disable auto-forwarding)")
        print("  gc send friends Hey everyone! $wave")
        print("  gc s friends Meeting at 3pm $clock")
        print("\nAuto-Relay:")
        print("  Messages from group members are automatically forwarded to all")
        print("  other members with [Group: name] prefix. Disable with 'gc relay'")
        print("="*70 + "\n")

    def _create_group(self, parts):
        """Create a new group"""
        if len(parts) < 3:
            print("Usage: gc create <name> <contact1> [contact2] ...")
            return

        # Parse: gc create groupname contact1 contact2 ...
        # LXMF-CLI joins args: "gc create test 2 3" becomes ['gc', 'create', 'test 2 3']
        raw_args = ' '.join(parts[2:])
        arg_parts = raw_args.split()

        if len(arg_parts) < 2:
            print("Usage: gc create <name> <contact1> [contact2] ...")
            return

        group_name = arg_parts[0]
        member_specs = arg_parts[1:]

        # Check if group already exists
        if group_name in self.groups:
            print(f"\n❌ Group '{group_name}' already exists!")
            print(f"Use 'gc add {group_name} <contact>' to add members\n")
            return

        # Resolve all members to hashes (supports names, indices, hashes)
        member_hashes, invalid = self._resolve_members(member_specs)

        if invalid:
            print(f"\n⚠️  Unknown contacts (skipped): {', '.join(invalid)}")

        if not member_hashes:
            print(f"\n❌ No valid contacts provided!\n")
            return

        # Create group with relay enabled by default
        self.groups[group_name] = {
            'members': member_hashes,
            'created': time.time(),
            'relay': True
        }
        self._save_groups()

        # Show confirmation
        print(f"\n✓ Group '{group_name}' created with {len(member_hashes)} member(s)")
        print(f"Auto-relay: Enabled")
        self._display_group_members(group_name, member_hashes)
        print()

    def _list_groups(self):
        """List all groups"""
        if not self.groups:
            print("\nℹ No groups created yet.")
            print("Use 'gc create <name> <contacts>' to create one\n")
            return

        print("\n" + "="*70)
        print(f"GROUPS ({len(self.groups)})")
        print("="*70 + "\n")

        # Sort by creation time (newest first)
        sorted_groups = sorted(
            self.groups.items(),
            key=lambda x: x[1].get('created', 0),
            reverse=True
        )

        for group_name, group_data in sorted_groups:
            member_count = len(group_data.get('members', []))
            created_ts = group_data.get('created', 0)
            relay_enabled = group_data.get('relay', True)

            # Format creation date
            try:
                dt = datetime.fromtimestamp(created_ts)
                created_str = dt.strftime('%Y-%m-%d')
            except:
                created_str = "Unknown"

            # Relay indicator
            relay_indicator = "🔄" if relay_enabled else "⏸️"

            print(f"  {group_name} {relay_indicator}")
            print(f"    Members: {member_count} | Created: {created_str} | Relay: {'On' if relay_enabled else 'Off'}")

        print("\n" + "="*70)
        print("💡 Use 'gc info <name>' to see members")
        print("💡 Use 'gc send <name> <msg>' to message a group")
        print("="*70 + "\n")

    def _show_group_info(self, parts):
        """Show detailed group information"""
        if len(parts) < 3:
            print("Usage: gc info <name>")
            return

        raw_args = ' '.join(parts[2:])
        group_name = raw_args.split()[0]

        if group_name not in self.groups:
            print(f"\n❌ Group '{group_name}' not found\n")
            return

        group_data = self.groups[group_name]
        members = group_data.get('members', [])
        created_ts = group_data.get('created', 0)
        relay_enabled = group_data.get('relay', True)

        print("\n" + "="*70)
        print(f"GROUP: {group_name}")
        print("="*70)

        # Creation date
        try:
            dt = datetime.fromtimestamp(created_ts)
            created_str = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            created_str = "Unknown"

        # Relay status
        if relay_enabled:
            relay_str = "✓ Enabled"
        else:
            relay_str = "✗ Disabled"

        print(f"\n  Created: {created_str}")
        print(f"  Members: {len(members)}")
        print(f"  Auto-relay: {relay_str}\n")

        self._display_group_members(group_name, members)

        print("\n" + "="*70)
        print(f"💡 Send message: gc send {group_name} <message>")
        print(f"💡 Add member: gc add {group_name} <contact>")
        print(f"💡 Toggle relay: gc relay {group_name} <on|off>")
        print("="*70 + "\n")

    def _display_group_members(self, group_name, member_hashes):
        """Display group members with names"""
        if not member_hashes:
            print("  (No members)")
            return

        print("  Members:")
        for i, member_hash in enumerate(member_hashes, 1):
            # Find contact name
            contact_name = None
            for name, data in self.client.contacts.items():
                if data.get('hash') == member_hash:
                    contact_name = name
                    break

            if contact_name:
                print(f"    {i}. {contact_name} ({member_hash[:16]}...)")
            else:
                print(f"    {i}. {member_hash}")

    def _add_member(self, parts):
        """Add member(s) to a group"""
        if len(parts) < 3:
            print("Usage: gc add <group> <contact> [contact2] ...")
            print("       gc add <group> -c <index> -p <index>")
            return

        # LXMF-CLI joins args: "gc add test 2 3" becomes ['gc', 'add', 'test 2 3']
        raw_args = ' '.join(parts[2:])
        arg_parts = raw_args.split()

        if len(arg_parts) < 2:
            print("Usage: gc add <group> <contact> [contact2] ...")
            print("       gc add <group> -c <index> -p <index>")
            return

        group_name = arg_parts[0]
        member_specs = arg_parts[1:]

        if group_name not in self.groups:
            print(f"\n❌ Group '{group_name}' not found\n")
            return

        # Resolve members using helper
        new_hashes, invalid = self._resolve_members(member_specs)

        members = self.groups[group_name]['members']
        added = []
        already_member = []

        for contact_hash in new_hashes:
            if contact_hash in members:
                already_member.append(contact_hash[:16])
            else:
                members.append(contact_hash)
                added.append(contact_hash)

        # Save if any changes
        if added:
            self._save_groups()
            print(f"\n✓ Added {len(added)} member(s) to '{group_name}'")
            for hash_val in added:
                # Try to find a name for display
                display = hash_val[:16]
                for name, data in self.client.contacts.items():
                    if data.get('hash') == hash_val:
                        display = name
                        break
                print(f"  + {display}")

        if already_member:
            print(f"\nℹ Already in group: {', '.join(already_member)}...")

        if invalid:
            print(f"\n⚠️  Unknown contacts: {', '.join(invalid)}")

        if not added and not already_member and not invalid:
            print(f"\nℹ No members to add\n")
        else:
            print()

    def _remove_member(self, parts):
        """Remove member(s) from a group"""
        if len(parts) < 3:
            print("Usage: gc remove <group> <contact> [contact2] ...")
            print("       gc remove <group> -c <index> -p <index>")
            return

        # LXMF-CLI joins args: "gc remove test 2 3" becomes ['gc', 'remove', 'test 2 3']
        raw_args = ' '.join(parts[2:])
        arg_parts = raw_args.split()

        if len(arg_parts) < 2:
            print("Usage: gc remove <group> <contact> [contact2] ...")
            print("       gc remove <group> -c <index> -p <index>")
            return

        group_name = arg_parts[0]
        member_specs = arg_parts[1:]

        if group_name not in self.groups:
            print(f"\n❌ Group '{group_name}' not found\n")
            return

        # Resolve members using helper
        remove_hashes, invalid = self._resolve_members(member_specs)

        members = self.groups[group_name]['members']
        removed = []
        not_member = []

        for contact_hash in remove_hashes:
            if contact_hash in members:
                members.remove(contact_hash)
                removed.append(contact_hash)
            else:
                not_member.append(contact_hash[:16])

        # Save if any changes
        if removed:
            self._save_groups()
            print(f"\n✓ Removed {len(removed)} member(s) from '{group_name}'")
            for hash_val in removed:
                # Try to find a name for display
                display = hash_val[:16]
                for name, data in self.client.contacts.items():
                    if data.get('hash') == hash_val:
                        display = name
                        break
                print(f"  - {display}")

        if not_member:
            print(f"\nℹ Not in group: {', '.join(not_member)}...")

        if invalid:
            print(f"\n⚠️  Unknown contacts: {', '.join(invalid)}")

        if not removed and not not_member and not invalid:
            print(f"\nℹ No members to remove\n")
        else:
            print()

    def _delete_group(self, parts):
        """Delete a group"""
        if len(parts) < 3:
            print("Usage: gc delete <name>")
            return

        raw_args = ' '.join(parts[2:])
        group_name = raw_args.split()[0]

        if group_name not in self.groups:
            print(f"\n❌ Group '{group_name}' not found\n")
            return

        # Confirm deletion
        member_count = len(self.groups[group_name]['members'])
        print(f"\n⚠️  Delete group '{group_name}' with {member_count} member(s)?")
        confirm = input("Type 'yes' to confirm: ").strip().lower()

        if confirm == 'yes':
            del self.groups[group_name]
            self._save_groups()
            print(f"\n✓ Group '{group_name}' deleted\n")
        else:
            print("Cancelled\n")

    def _rename_group(self, parts):
        """Rename a group"""
        if len(parts) < 4:
            print("Usage: gc rename <old_name> <new_name>")
            return

        raw_args = ' '.join(parts[2:])
        arg_parts = raw_args.split()

        if len(arg_parts) < 2:
            print("Usage: gc rename <old_name> <new_name>")
            return

        old_name = arg_parts[0]
        new_name = arg_parts[1]

        if old_name not in self.groups:
            print(f"\n❌ Group '{old_name}' not found\n")
            return

        if new_name in self.groups:
            print(f"\n❌ Group '{new_name}' already exists!\n")
            return

        # Rename
        self.groups[new_name] = self.groups[old_name]
        del self.groups[old_name]
        self._save_groups()

        print(f"\n✓ Renamed '{old_name}' → '{new_name}'\n")

    def _toggle_relay(self, parts):
        """Toggle auto-relay for a group"""
        if len(parts) < 4:
            print("Usage: gc relay <group> <on|off>")
            return

        raw_args = ' '.join(parts[2:])
        arg_parts = raw_args.split()

        if len(arg_parts) < 2:
            print("Usage: gc relay <group> <on|off>")
            return

        group_name = arg_parts[0]
        setting = arg_parts[1].lower()

        if group_name not in self.groups:
            print(f"\n❌ Group '{group_name}' not found\n")
            return

        if setting not in ['on', 'off', 'true', 'false', '1', '0', 'enable', 'disable']:
            print(f"\n❌ Invalid setting: {setting}")
            print("Use: on, off, enable, disable, true, false, 1, or 0\n")
            return

        # Set relay flag
        enabled = setting in ['on', 'true', '1', 'enable']
        self.groups[group_name]['relay'] = enabled
        self._save_groups()

        status = "✓ Enabled" if enabled else "✗ Disabled"
        print(f"\n✓ Auto-relay for '{group_name}': {status}")

        if enabled:
            print("  Messages from group members will be forwarded to all other members")
        else:
            print("  Messages from group members will NOT be auto-forwarded")
        print()

    def _send_to_group(self, parts):
        """Send message to all group members"""
        if len(parts) < 3:
            print("Usage: gc send <group> <message>")
            return

        # Parse: gc send groupname message text here
        # LXMF-CLI joins args: "gc send test hello world" becomes ['gc', 'send', 'test hello world']
        raw_args = ' '.join(parts[2:])
        arg_parts = raw_args.split(maxsplit=1)

        if len(arg_parts) < 2:
            print("Usage: gc send <group> <message>")
            return

        group_name = arg_parts[0]
        message = arg_parts[1]

        if group_name not in self.groups:
            print(f"\n❌ Group '{group_name}' not found\n")
            return

        members = self.groups[group_name]['members']

        if not members:
            print(f"\n⚠️  Group '{group_name}' has no members!\n")
            return

        # Prefix message with group tag and server identifier
        tagged_message = f"💬 [Group: {group_name}] ChatServer: {message}"

        # Send to all members
        print(f"\n📤 Sending to group '{group_name}' ({len(members)} members)...\n")

        success_count = 0
        for member_hash in members:
            # Get member name for display
            member_name = None
            for name, data in self.client.contacts.items():
                if data.get('hash') == member_hash:
                    member_name = name
                    break

            display_name = member_name or member_hash[:16]

            # Send message (silently)
            try:
                success = self._send_message_silent(member_hash, tagged_message)
                if success:
                    print(f"  ✓ {display_name}")
                    success_count += 1
                else:
                    print(f"  ✗ {display_name}")
            except Exception as e:
                print(f"  ✗ {display_name} - {e}")

        # Summary
        print(f"\nSent to {success_count}/{len(members)} members\n")

if __name__ == '__main__':
    print("This is a plugin for LXMF Client")
    print("Place in: ./lxmf_client_storage/plugins/")

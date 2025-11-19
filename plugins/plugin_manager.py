"""
Plugin Manager for LXMF-CLI
Allows browsing and installing plugins from the official repository.
"""

import os
import shutil
import json

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['pluginstore', 'pstore']
        self.description = "Browse and install plugins from repository"

        # Detect repository root
        self.repo_root = self._find_repo_root()
        self.available_plugins_dir = os.path.join(self.repo_root, "plugins") if self.repo_root else None
        self.installed_plugins_dir = self.client.plugins_dir

        print("Plugin Manager loaded!")

    def _find_repo_root(self):
        """Try to find the lxmf-cli repository root"""
        # Start from current directory and walk up
        current = os.getcwd()

        # Try up to 5 levels up
        for _ in range(5):
            # Check if this looks like the repo root (has plugins/ and lxmf-cli.py)
            if os.path.exists(os.path.join(current, "plugins")) and \
               os.path.exists(os.path.join(current, "lxmf-cli.py")):
                return current

            # Go up one level
            parent = os.path.dirname(current)
            if parent == current:  # Reached root
                break
            current = parent

        return None

    def on_message(self, message, msg_data):
        return False

    def handle_command(self, cmd, parts):
        if cmd not in ['pluginstore', 'pstore']:
            return

        if len(parts) < 2:
            self._show_help()
            return

        action = parts[1].lower()

        if action == 'list':
            self._list_available_plugins()
        elif action == 'installed':
            self._list_installed_plugins()
        elif action == 'info' and len(parts) >= 3:
            plugin_name = parts[2]
            self._show_plugin_info(plugin_name)
        elif action == 'install' and len(parts) >= 3:
            plugin_name = parts[2]
            self._install_plugin(plugin_name)
        elif action == 'uninstall' and len(parts) >= 3:
            plugin_name = parts[2]
            self._uninstall_plugin(plugin_name)
        elif action == 'update' and len(parts) >= 3:
            plugin_name = parts[2]
            self._update_plugin(plugin_name)
        elif action == 'update-all':
            self._update_all_plugins()
        else:
            self._show_help()

    def _show_help(self):
        """Show plugin store help"""
        print("\n" + "─" * 70)
        print(f"{self.client.Fore.CYAN}PLUGIN STORE{self.client.Style.RESET_ALL}")
        print("─" * 70)
        print("\nCommands:")
        print(f"  {self.client.Fore.CYAN}pstore list{self.client.Style.RESET_ALL}              - List available plugins")
        print(f"  {self.client.Fore.CYAN}pstore installed{self.client.Style.RESET_ALL}        - List installed plugins")
        print(f"  {self.client.Fore.CYAN}pstore info <name>{self.client.Style.RESET_ALL}      - Show plugin details")
        print(f"  {self.client.Fore.CYAN}pstore install <name>{self.client.Style.RESET_ALL}   - Install a plugin")
        print(f"  {self.client.Fore.CYAN}pstore uninstall <name>{self.client.Style.RESET_ALL} - Remove a plugin")
        print(f"  {self.client.Fore.CYAN}pstore update <name>{self.client.Style.RESET_ALL}    - Update a plugin")
        print(f"  {self.client.Fore.CYAN}pstore update-all{self.client.Style.RESET_ALL}       - Update all plugins")
        print("─" * 70 + "\n")

    def _list_available_plugins(self):
        """List all available plugins from repository"""
        if not self.available_plugins_dir or not os.path.exists(self.available_plugins_dir):
            print(f"\n{self.client.Fore.RED}Repository plugins folder not found!{self.client.Style.RESET_ALL}")
            print("Make sure you're running from the lxmf-cli directory.")
            print(f"Searched in: {self.available_plugins_dir}\n")
            return

        print("\n" + "─" * 70)
        print(f"{self.client.Fore.GREEN}AVAILABLE PLUGINS{self.client.Style.RESET_ALL}")
        print("─" * 70)

        plugins = self._scan_directory(self.available_plugins_dir)

        if not plugins:
            print("\nNo plugins found in repository\n")
            return

        print(f"\n{'Plugin':<20} {'Status':<12} {'Description'}")
        print(f"{'─'*20} {'─'*12} {'─'*35}")

        for plugin_name, plugin_info in sorted(plugins.items()):
            # Check if installed
            installed_path = os.path.join(self.installed_plugins_dir, f"{plugin_name}.py")

            if os.path.exists(installed_path):
                # Check if it's the same version (compare file size as simple check)
                repo_size = os.path.getsize(plugin_info['path'])
                installed_size = os.path.getsize(installed_path)

                if repo_size == installed_size:
                    status = f"{self.client.Fore.GREEN}Installed{self.client.Style.RESET_ALL}"
                else:
                    status = f"{self.client.Fore.YELLOW}Update{self.client.Style.RESET_ALL}"
            else:
                status = f"{self.client.Fore.WHITE}Available{self.client.Style.RESET_ALL}"

            description = plugin_info.get('description', 'No description')[:35]
            print(f"{plugin_name:<20} {status:<22} {description}")

        print("─" * 70)
        print(f"\n{self.client.Fore.YELLOW}💡 Use 'pstore info <name>' for details{self.client.Style.RESET_ALL}")
        print(f"{self.client.Fore.YELLOW}💡 Use 'pstore install <name>' to install{self.client.Style.RESET_ALL}\n")

    def _list_installed_plugins(self):
        """List all installed plugins"""
        if not os.path.exists(self.installed_plugins_dir):
            print("\nNo plugins installed\n")
            return

        plugins = self._scan_directory(self.installed_plugins_dir)

        if not plugins:
            print("\nNo plugins installed\n")
            return

        print("\n" + "─" * 70)
        print(f"{self.client.Fore.CYAN}INSTALLED PLUGINS{self.client.Style.RESET_ALL}")
        print("─" * 70)

        print(f"\n{'Plugin':<20} {'Status':<12} {'Description'}")
        print(f"{'─'*20} {'─'*12} {'─'*35}")

        for plugin_name, plugin_info in sorted(plugins.items()):
            # Check if loaded
            if plugin_name in self.client.plugins:
                status = f"{self.client.Fore.GREEN}Loaded{self.client.Style.RESET_ALL}"
            elif self.client.plugins_enabled.get(plugin_name, True):
                status = f"{self.client.Fore.YELLOW}Enabled{self.client.Style.RESET_ALL}"
            else:
                status = f"{self.client.Fore.RED}Disabled{self.client.Style.RESET_ALL}"

            description = plugin_info.get('description', 'No description')[:35]
            print(f"{plugin_name:<20} {status:<22} {description}")

        print("─" * 70 + "\n")

    def _scan_directory(self, directory):
        """Scan a directory for plugins and extract info"""
        plugins = {}

        if not os.path.exists(directory):
            return plugins

        for filename in os.listdir(directory):
            if filename.endswith('.py') and not filename.startswith('_'):
                plugin_name = filename[:-3]
                filepath = os.path.join(directory, filename)

                # Try to extract description from file
                description = self._extract_description(filepath)

                plugins[plugin_name] = {
                    'path': filepath,
                    'description': description
                }

        return plugins

    def _extract_description(self, filepath):
        """Extract description from plugin file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

                # Look for docstring
                in_docstring = False
                docstring_lines = []

                for line in lines[:20]:  # Only check first 20 lines
                    if '"""' in line or "'''" in line:
                        if in_docstring:
                            # End of docstring
                            break
                        else:
                            # Start of docstring
                            in_docstring = True
                            # Check if single-line docstring
                            if line.count('"""') == 2 or line.count("'''") == 2:
                                content = line.split('"""')[1] if '"""' in line else line.split("'''")[1]
                                return content.strip()
                            continue

                    if in_docstring:
                        docstring_lines.append(line.strip())

                # Return first non-empty line of docstring
                for line in docstring_lines:
                    if line:
                        return line

                return "No description"
        except:
            return "No description"

    def _show_plugin_info(self, plugin_name):
        """Show detailed info about a plugin"""
        if not self.available_plugins_dir:
            print(f"\n{self.client.Fore.RED}Repository not found{self.client.Style.RESET_ALL}\n")
            return

        plugin_path = os.path.join(self.available_plugins_dir, f"{plugin_name}.py")

        if not os.path.exists(plugin_path):
            print(f"\n{self.client.Fore.RED}Plugin not found: {plugin_name}{self.client.Style.RESET_ALL}\n")
            return

        # Extract info
        description = self._extract_description(plugin_path)
        file_size = os.path.getsize(plugin_path)

        # Check if installed
        installed_path = os.path.join(self.installed_plugins_dir, f"{plugin_name}.py")
        is_installed = os.path.exists(installed_path)

        print("\n" + "─" * 70)
        print(f"{self.client.Fore.CYAN}{plugin_name.upper()}{self.client.Style.RESET_ALL}")
        print("─" * 70)
        print(f"\nDescription: {description}")
        print(f"Size: {file_size} bytes")
        print(f"Status: {'Installed' if is_installed else 'Not installed'}")

        if is_installed:
            installed_size = os.path.getsize(installed_path)
            if installed_size != file_size:
                print(f"{self.client.Fore.YELLOW}Update available!{self.client.Style.RESET_ALL}")

        print(f"\nPath: {plugin_path}")
        print("─" * 70)

        if is_installed:
            print(f"\n{self.client.Fore.YELLOW}💡 Use 'pstore update {plugin_name}' to update{self.client.Style.RESET_ALL}")
            print(f"{self.client.Fore.YELLOW}💡 Use 'pstore uninstall {plugin_name}' to remove{self.client.Style.RESET_ALL}\n")
        else:
            print(f"\n{self.client.Fore.YELLOW}💡 Use 'pstore install {plugin_name}' to install{self.client.Style.RESET_ALL}\n")

    def _install_plugin(self, plugin_name):
        """Install a plugin from repository"""
        if not self.available_plugins_dir:
            print(f"\n{self.client.Fore.RED}Repository not found{self.client.Style.RESET_ALL}\n")
            return

        source_path = os.path.join(self.available_plugins_dir, f"{plugin_name}.py")

        if not os.path.exists(source_path):
            print(f"\n{self.client.Fore.RED}Plugin not found: {plugin_name}{self.client.Style.RESET_ALL}\n")
            return

        dest_path = os.path.join(self.installed_plugins_dir, f"{plugin_name}.py")

        # Check if already installed
        if os.path.exists(dest_path):
            print(f"\n{self.client.Fore.YELLOW}Plugin already installed: {plugin_name}{self.client.Style.RESET_ALL}")
            print(f"Use 'pstore update {plugin_name}' to update\n")
            return

        # Create plugins directory if it doesn't exist
        os.makedirs(self.installed_plugins_dir, exist_ok=True)

        # Copy plugin file
        try:
            shutil.copy2(source_path, dest_path)
            print(f"\n{self.client.Fore.GREEN}✓ Installed: {plugin_name}{self.client.Style.RESET_ALL}")
            print(f"{self.client.Fore.YELLOW}💡 Use 'plugin reload' to activate{self.client.Style.RESET_ALL}\n")
        except Exception as e:
            print(f"\n{self.client.Fore.RED}Error installing plugin: {e}{self.client.Style.RESET_ALL}\n")

    def _uninstall_plugin(self, plugin_name):
        """Uninstall a plugin"""
        dest_path = os.path.join(self.installed_plugins_dir, f"{plugin_name}.py")

        if not os.path.exists(dest_path):
            print(f"\n{self.client.Fore.RED}Plugin not installed: {plugin_name}{self.client.Style.RESET_ALL}\n")
            return

        # Confirm
        confirm = input(f"Uninstall '{plugin_name}'? [y/N]: ").strip().lower()
        if confirm != 'y':
            print("Cancelled")
            return

        try:
            os.remove(dest_path)
            print(f"\n{self.client.Fore.GREEN}✓ Uninstalled: {plugin_name}{self.client.Style.RESET_ALL}")
            print(f"{self.client.Fore.YELLOW}💡 Use 'plugin reload' to complete removal{self.client.Style.RESET_ALL}\n")
        except Exception as e:
            print(f"\n{self.client.Fore.RED}Error uninstalling plugin: {e}{self.client.Style.RESET_ALL}\n")

    def _update_plugin(self, plugin_name):
        """Update an installed plugin"""
        if not self.available_plugins_dir:
            print(f"\n{self.client.Fore.RED}Repository not found{self.client.Style.RESET_ALL}\n")
            return

        source_path = os.path.join(self.available_plugins_dir, f"{plugin_name}.py")
        dest_path = os.path.join(self.installed_plugins_dir, f"{plugin_name}.py")

        if not os.path.exists(source_path):
            print(f"\n{self.client.Fore.RED}Plugin not found in repository: {plugin_name}{self.client.Style.RESET_ALL}\n")
            return

        if not os.path.exists(dest_path):
            print(f"\n{self.client.Fore.RED}Plugin not installed: {plugin_name}{self.client.Style.RESET_ALL}")
            print(f"Use 'pstore install {plugin_name}' to install\n")
            return

        # Check if update needed
        source_size = os.path.getsize(source_path)
        dest_size = os.path.getsize(dest_path)

        if source_size == dest_size:
            print(f"\n{self.client.Fore.GREEN}Plugin already up to date: {plugin_name}{self.client.Style.RESET_ALL}\n")
            return

        # Copy plugin file
        try:
            shutil.copy2(source_path, dest_path)
            print(f"\n{self.client.Fore.GREEN}✓ Updated: {plugin_name}{self.client.Style.RESET_ALL}")
            print(f"{self.client.Fore.YELLOW}💡 Use 'plugin reload' to apply update{self.client.Style.RESET_ALL}\n")
        except Exception as e:
            print(f"\n{self.client.Fore.RED}Error updating plugin: {e}{self.client.Style.RESET_ALL}\n")

    def _update_all_plugins(self):
        """Update all installed plugins"""
        if not self.available_plugins_dir:
            print(f"\n{self.client.Fore.RED}Repository not found{self.client.Style.RESET_ALL}\n")
            return

        installed = self._scan_directory(self.installed_plugins_dir)

        if not installed:
            print("\nNo plugins installed\n")
            return

        updated_count = 0
        uptodate_count = 0

        print(f"\n{self.client.Fore.CYAN}Checking for updates...{self.client.Style.RESET_ALL}\n")

        for plugin_name in installed:
            source_path = os.path.join(self.available_plugins_dir, f"{plugin_name}.py")
            dest_path = os.path.join(self.installed_plugins_dir, f"{plugin_name}.py")

            if not os.path.exists(source_path):
                print(f"  {self.client.Fore.YELLOW}⚠ {plugin_name}: Not in repository{self.client.Style.RESET_ALL}")
                continue

            source_size = os.path.getsize(source_path)
            dest_size = os.path.getsize(dest_path)

            if source_size != dest_size:
                try:
                    shutil.copy2(source_path, dest_path)
                    print(f"  {self.client.Fore.GREEN}✓ {plugin_name}: Updated{self.client.Style.RESET_ALL}")
                    updated_count += 1
                except Exception as e:
                    print(f"  {self.client.Fore.RED}✗ {plugin_name}: Error - {e}{self.client.Style.RESET_ALL}")
            else:
                print(f"  {self.client.Fore.WHITE}○ {plugin_name}: Up to date{self.client.Style.RESET_ALL}")
                uptodate_count += 1

        print(f"\n{self.client.Fore.CYAN}Summary:{self.client.Style.RESET_ALL}")
        print(f"  Updated: {updated_count}")
        print(f"  Up to date: {uptodate_count}")

        if updated_count > 0:
            print(f"\n{self.client.Fore.YELLOW}💡 Use 'plugin reload' to apply updates{self.client.Style.RESET_ALL}\n")
        else:
            print()

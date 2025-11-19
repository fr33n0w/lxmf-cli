#!/usr/bin/env python3
"""
LXMF-CLI Plugin Installer
Interactive tool to install and manage plugins from the repository.
Run this script to choose which plugins to install into your lxmf_client_storage.
"""

import os
import sys
import shutil
import json
from pathlib import Path

class PluginInstaller:
    def __init__(self):
        # Detect paths
        self.script_dir = Path(__file__).parent.absolute()
        self.repo_plugins_dir = self.script_dir / "plugins"
        self.storage_plugins_dir = self.script_dir / "lxmf_client_storage" / "plugins"

        # Colors for terminal output
        self.colors = {
            'GREEN': '\033[92m',
            'YELLOW': '\033[93m',
            'RED': '\033[91m',
            'CYAN': '\033[96m',
            'WHITE': '\033[97m',
            'RESET': '\033[0m',
            'BOLD': '\033[1m'
        }

    def color(self, text, color_name):
        """Apply color to text"""
        return f"{self.colors.get(color_name, '')}{text}{self.colors['RESET']}"

    def clear_screen(self):
        """Clear terminal screen"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def print_header(self, text):
        """Print a styled header"""
        print("\n" + "═" * 70)
        print(self.color(f"  {text}", 'CYAN'))
        print("═" * 70 + "\n")

    def scan_plugins(self, directory):
        """Scan directory for plugin files"""
        plugins = {}

        if not directory.exists():
            return plugins

        for file in directory.glob("*.py"):
            if file.name.startswith('_'):
                continue

            plugin_name = file.stem
            description = self.extract_description(file)

            plugins[plugin_name] = {
                'path': file,
                'description': description,
                'size': file.stat().st_size
            }

        return plugins

    def extract_description(self, filepath):
        """Extract description from plugin docstring"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

                in_docstring = False
                docstring_lines = []

                for line in lines[:20]:
                    if '"""' in line or "'''" in line:
                        if in_docstring:
                            break
                        else:
                            in_docstring = True
                            # Single-line docstring
                            if line.count('"""') == 2 or line.count("'''") == 2:
                                content = line.split('"""')[1] if '"""' in line else line.split("'''")[1]
                                return content.strip()
                            continue

                    if in_docstring:
                        docstring_lines.append(line.strip())

                # Return first non-empty line
                for line in docstring_lines:
                    if line:
                        return line

                return "No description available"
        except:
            return "No description available"

    def list_available_plugins(self):
        """Display available plugins from repository"""
        self.print_header("AVAILABLE PLUGINS (Repository)")

        repo_plugins = self.scan_plugins(self.repo_plugins_dir)
        installed_plugins = self.scan_plugins(self.storage_plugins_dir)

        if not repo_plugins:
            print(self.color("  No plugins found in repository!", 'RED'))
            print(f"  Searched: {self.repo_plugins_dir}\n")
            return None

        # Display table
        print(f"  {'#':<4} {'Plugin Name':<20} {'Status':<12} {'Description'}")
        print(f"  {'-'*4} {'-'*20} {'-'*12} {'-'*30}")

        plugin_list = []
        for idx, (name, info) in enumerate(sorted(repo_plugins.items()), 1):
            # Check installation status
            if name in installed_plugins:
                if installed_plugins[name]['size'] == info['size']:
                    status = self.color("Installed", 'GREEN')
                else:
                    status = self.color("Update", 'YELLOW')
            else:
                status = self.color("Available", 'WHITE')

            desc = info['description'][:30]
            print(f"  {idx:<4} {name:<20} {status:<22} {desc}")
            plugin_list.append(name)

        print("\n" + "─" * 70 + "\n")
        return plugin_list

    def list_installed_plugins(self):
        """Display installed plugins"""
        self.print_header("INSTALLED PLUGINS")

        installed_plugins = self.scan_plugins(self.storage_plugins_dir)

        if not installed_plugins:
            print(self.color("  No plugins installed yet.", 'YELLOW'))
            print(f"  Install location: {self.storage_plugins_dir}\n")
            return None

        # Display table
        print(f"  {'#':<4} {'Plugin Name':<20} {'Size':<10} {'Description'}")
        print(f"  {'-'*4} {'-'*20} {'-'*10} {'-'*30}")

        plugin_list = []
        for idx, (name, info) in enumerate(sorted(installed_plugins.items()), 1):
            size_kb = info['size'] / 1024
            desc = info['description'][:30]
            print(f"  {idx:<4} {name:<20} {size_kb:>7.1f} KB {desc}")
            plugin_list.append(name)

        print("\n" + "─" * 70 + "\n")
        return plugin_list

    def install_plugin(self, plugin_name):
        """Install a single plugin"""
        source = self.repo_plugins_dir / f"{plugin_name}.py"

        if not source.exists():
            print(self.color(f"  ✗ Plugin not found: {plugin_name}", 'RED'))
            return False

        # Create storage directory if needed
        self.storage_plugins_dir.mkdir(parents=True, exist_ok=True)

        dest = self.storage_plugins_dir / f"{plugin_name}.py"

        # Check if already installed
        if dest.exists():
            source_size = source.stat().st_size
            dest_size = dest.stat().st_size

            if source_size == dest_size:
                print(self.color(f"  ○ {plugin_name} already installed (up to date)", 'YELLOW'))
                return True
            else:
                # Update needed
                try:
                    shutil.copy2(source, dest)
                    print(self.color(f"  ✓ {plugin_name} updated successfully", 'GREEN'))
                    return True
                except Exception as e:
                    print(self.color(f"  ✗ Error updating {plugin_name}: {e}", 'RED'))
                    return False

        # Install new plugin
        try:
            shutil.copy2(source, dest)
            print(self.color(f"  ✓ {plugin_name} installed successfully", 'GREEN'))
            return True
        except Exception as e:
            print(self.color(f"  ✗ Error installing {plugin_name}: {e}", 'RED'))
            return False

    def uninstall_plugin(self, plugin_name):
        """Uninstall a plugin"""
        dest = self.storage_plugins_dir / f"{plugin_name}.py"

        if not dest.exists():
            print(self.color(f"  ✗ Plugin not installed: {plugin_name}", 'RED'))
            return False

        try:
            dest.unlink()
            print(self.color(f"  ✓ {plugin_name} uninstalled successfully", 'GREEN'))
            return True
        except Exception as e:
            print(self.color(f"  ✗ Error uninstalling {plugin_name}: {e}", 'RED'))
            return False

    def install_all_plugins(self):
        """Install all available plugins"""
        repo_plugins = self.scan_plugins(self.repo_plugins_dir)

        if not repo_plugins:
            print(self.color("  No plugins found to install!", 'RED'))
            return

        print(self.color(f"\n  Installing {len(repo_plugins)} plugins...\n", 'CYAN'))

        success_count = 0
        for plugin_name in sorted(repo_plugins.keys()):
            if self.install_plugin(plugin_name):
                success_count += 1

        print(f"\n  {self.color('Summary:', 'BOLD')} {success_count}/{len(repo_plugins)} plugins installed")

    def update_all_plugins(self):
        """Update all installed plugins"""
        installed_plugins = self.scan_plugins(self.storage_plugins_dir)
        repo_plugins = self.scan_plugins(self.repo_plugins_dir)

        if not installed_plugins:
            print(self.color("  No plugins installed to update!", 'YELLOW'))
            return

        print(self.color(f"\n  Checking {len(installed_plugins)} plugins for updates...\n", 'CYAN'))

        update_count = 0
        uptodate_count = 0

        for plugin_name in sorted(installed_plugins.keys()):
            if plugin_name not in repo_plugins:
                print(self.color(f"  ⚠ {plugin_name}: Not in repository (custom plugin?)", 'YELLOW'))
                continue

            source_size = repo_plugins[plugin_name]['size']
            dest_size = installed_plugins[plugin_name]['size']

            if source_size != dest_size:
                if self.install_plugin(plugin_name):
                    update_count += 1
            else:
                print(self.color(f"  ○ {plugin_name}: Up to date", 'WHITE'))
                uptodate_count += 1

        print(f"\n  {self.color('Summary:', 'BOLD')} {update_count} updated, {uptodate_count} up to date")

    def interactive_install(self):
        """Interactive plugin selection and installation"""
        plugin_list = self.list_available_plugins()

        if not plugin_list:
            return

        print("  Enter plugin numbers to install (e.g., 1 3 5 or 1-4)")
        print("  Or type 'all' to install everything")
        choice = input(f"  {self.color('Selection:', 'CYAN')} ").strip()

        if not choice:
            print("  Cancelled.")
            return

        # Parse selection
        selected_plugins = []

        if choice.lower() == 'all':
            selected_plugins = plugin_list
        else:
            # Parse numbers and ranges
            parts = choice.replace(',', ' ').split()
            for part in parts:
                if '-' in part:
                    # Range
                    try:
                        start, end = part.split('-')
                        start_idx = int(start) - 1
                        end_idx = int(end) - 1

                        if 0 <= start_idx < len(plugin_list) and 0 <= end_idx < len(plugin_list):
                            selected_plugins.extend(plugin_list[start_idx:end_idx+1])
                    except ValueError:
                        print(self.color(f"  Invalid range: {part}", 'RED'))
                else:
                    # Single number
                    try:
                        idx = int(part) - 1
                        if 0 <= idx < len(plugin_list):
                            selected_plugins.append(plugin_list[idx])
                    except ValueError:
                        print(self.color(f"  Invalid number: {part}", 'RED'))

        if not selected_plugins:
            print("  No valid plugins selected.")
            return

        # Install selected plugins
        print(f"\n  Installing {len(selected_plugins)} plugin(s)...\n")

        success_count = 0
        for plugin_name in selected_plugins:
            if self.install_plugin(plugin_name):
                success_count += 1

        print(f"\n  {self.color('Done!', 'GREEN')} {success_count}/{len(selected_plugins)} plugins installed successfully.\n")

    def interactive_uninstall(self):
        """Interactive plugin uninstallation"""
        plugin_list = self.list_installed_plugins()

        if not plugin_list:
            return

        print("  Enter plugin numbers to uninstall (e.g., 1 3 5)")
        choice = input(f"  {self.color('Selection:', 'CYAN')} ").strip()

        if not choice:
            print("  Cancelled.")
            return

        # Parse selection
        selected_plugins = []
        parts = choice.replace(',', ' ').split()

        for part in parts:
            try:
                idx = int(part) - 1
                if 0 <= idx < len(plugin_list):
                    selected_plugins.append(plugin_list[idx])
            except ValueError:
                print(self.color(f"  Invalid number: {part}", 'RED'))

        if not selected_plugins:
            print("  No valid plugins selected.")
            return

        # Confirm
        print(f"\n  About to uninstall: {', '.join(selected_plugins)}")
        confirm = input(f"  {self.color('Confirm? [y/N]:', 'YELLOW')} ").strip().lower()

        if confirm != 'y':
            print("  Cancelled.")
            return

        # Uninstall
        print()
        success_count = 0
        for plugin_name in selected_plugins:
            if self.uninstall_plugin(plugin_name):
                success_count += 1

        print(f"\n  {self.color('Done!', 'GREEN')} {success_count}/{len(selected_plugins)} plugins uninstalled.\n")

    def show_info(self, plugin_name):
        """Show detailed plugin information"""
        repo_plugins = self.scan_plugins(self.repo_plugins_dir)
        installed_plugins = self.scan_plugins(self.storage_plugins_dir)

        if plugin_name not in repo_plugins:
            print(self.color(f"\n  Plugin not found: {plugin_name}\n", 'RED'))
            return

        info = repo_plugins[plugin_name]

        self.print_header(f"PLUGIN INFO: {plugin_name.upper()}")

        print(f"  Description: {info['description']}")
        print(f"  Size: {info['size'] / 1024:.1f} KB")
        print(f"  Location: {info['path']}")

        # Installation status
        if plugin_name in installed_plugins:
            installed_info = installed_plugins[plugin_name]
            if installed_info['size'] == info['size']:
                status = self.color("Installed (up to date)", 'GREEN')
            else:
                status = self.color("Installed (update available)", 'YELLOW')
        else:
            status = self.color("Not installed", 'WHITE')

        print(f"  Status: {status}")
        print()

    def main_menu(self):
        """Display main menu and handle user input"""
        while True:
            self.clear_screen()

            print(self.color("\n  ╔══════════════════════════════════════════════════════════════════╗", 'CYAN'))
            print(self.color("  ║          LXMF-CLI PLUGIN INSTALLER & MANAGER                     ║", 'CYAN'))
            print(self.color("  ╚══════════════════════════════════════════════════════════════════╝\n", 'CYAN'))

            print(f"  Repository: {self.color(str(self.repo_plugins_dir), 'YELLOW')}")
            print(f"  Install to: {self.color(str(self.storage_plugins_dir), 'YELLOW')}\n")

            print("  " + "─" * 66)
            print(f"  {self.color('1', 'GREEN')}. List available plugins (from repository)")
            print(f"  {self.color('2', 'GREEN')}. List installed plugins")
            print(f"  {self.color('3', 'GREEN')}. Install plugins (interactive)")
            print(f"  {self.color('4', 'GREEN')}. Install ALL plugins")
            print(f"  {self.color('5', 'GREEN')}. Update all installed plugins")
            print(f"  {self.color('6', 'GREEN')}. Uninstall plugins")
            print(f"  {self.color('7', 'GREEN')}. Plugin info")
            print(f"  {self.color('0', 'RED')}. Exit")
            print("  " + "─" * 66)

            choice = input(f"\n  {self.color('Select option:', 'CYAN')} ").strip()

            if choice == '1':
                self.list_available_plugins()
                input(f"\n  {self.color('Press Enter to continue...', 'YELLOW')}")

            elif choice == '2':
                self.list_installed_plugins()
                input(f"\n  {self.color('Press Enter to continue...', 'YELLOW')}")

            elif choice == '3':
                self.interactive_install()
                input(f"\n  {self.color('Press Enter to continue...', 'YELLOW')}")

            elif choice == '4':
                confirm = input(f"\n  {self.color('Install ALL plugins? [y/N]:', 'YELLOW')} ").strip().lower()
                if confirm == 'y':
                    self.install_all_plugins()
                input(f"\n  {self.color('Press Enter to continue...', 'YELLOW')}")

            elif choice == '5':
                self.update_all_plugins()
                input(f"\n  {self.color('Press Enter to continue...', 'YELLOW')}")

            elif choice == '6':
                self.interactive_uninstall()
                input(f"\n  {self.color('Press Enter to continue...', 'YELLOW')}")

            elif choice == '7':
                plugin_name = input(f"\n  {self.color('Plugin name:', 'CYAN')} ").strip()
                if plugin_name:
                    self.show_info(plugin_name)
                input(f"\n  {self.color('Press Enter to continue...', 'YELLOW')}")

            elif choice == '0':
                print(self.color("\n  Goodbye!\n", 'CYAN'))
                break

            else:
                print(self.color("\n  Invalid option!", 'RED'))
                input(f"\n  {self.color('Press Enter to continue...', 'YELLOW')}")


def main():
    """Main entry point"""
    installer = PluginInstaller()

    # Check if running from correct directory
    if not installer.repo_plugins_dir.exists():
        print(f"\n{installer.color('ERROR:', 'RED')} Repository plugins directory not found!")
        print(f"Expected: {installer.repo_plugins_dir}")
        print("\nMake sure you're running this script from the lxmf-cli root directory.\n")
        sys.exit(1)

    # Run interactive menu
    try:
        installer.main_menu()
    except KeyboardInterrupt:
        print(installer.color("\n\n  Interrupted by user. Goodbye!\n", 'YELLOW'))
    except Exception as e:
        print(installer.color(f"\n\n  Error: {e}\n", 'RED'))
        sys.exit(1)


if __name__ == "__main__":
    main()

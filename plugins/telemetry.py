"""
Telemetry Plugin for LXMF-CLI
Compatible with Sideband telemetry exchange protocol.
Allows sending and receiving telemetry data (location, battery, sensors, etc).
"""

import time
import json
import msgpack
import threading
from datetime import datetime

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['telemetry', 'telem']
        self.description = "Send/receive telemetry data (compatible with Sideband)"

        # Telemetry storage: {contact_hash: [[timestamp, packed_data], ...]}
        self.telemetry_data = {}

        # Collector thread management
        self.collector_thread = None
        self.collector_running = False
        self.last_collector_send = 0

        # Local telemetry configuration
        self.config = {
            'enabled': True,  # Enable telemetry plugin
            'location': None,  # [latitude, longitude, altitude]
            'battery': None,
            'temperature': None,
            'pressure': None,
            'humidity': None,
            'custom': {},

            # Request handling
            'allow_requests': True,  # Allow telemetry requests
            'trusted_only': False,  # Only respond to trusted contacts
            'trusted_contacts': [],  # List of trusted contact hashes

            # Collector settings
            'collector_enabled': False,  # Enable automatic sending to collector
            'collector_address': None,  # Collector LXMF address (hash)
            'collector_interval': 3600  # Send interval in seconds (default: 1 hour)
        }

        # LXMF field constants (official LXMF specification)
        self.FIELD_TELEMETRY = 0x02
        self.FIELD_TELEMETRY_STREAM = 0x03
        self.FIELD_COMMANDS = 0x09

        # Command constants (matching Sideband)
        self.CMD_TELEMETRY_REQUEST = 0x01
        self.CMD_PING = 0x02
        self.CMD_ECHO = 0x03
        self.CMD_SIGNAL_REPORT = 0x04

        # Sensor type constants (matching Sideband sense.py)
        self.S_TIME = 0x01
        self.S_LOCATION = 0x02
        self.S_PRESSURE = 0x03
        self.S_BATTERY = 0x04
        self.S_PHYSICAL_LINK = 0x05
        self.S_ACCELERATION = 0x06
        self.S_TEMPERATURE = 0x07
        self.S_HUMIDITY = 0x08
        self.S_MAGNETIC_FIELD = 0x09
        self.S_AMBIENT_LIGHT = 0x0A
        self.S_GRAVITY = 0x0B
        self.S_ANGULAR_VELOCITY = 0x0C
        self.S_PROXIMITY = 0x0E
        self.S_CUSTOM = 0xFF

        self._load_config()

        # Start collector if enabled
        if self.config.get('collector_enabled', False):
            self._start_collector()

        print("Telemetry Plugin loaded!")

    def _load_config(self):
        """Load telemetry configuration"""
        try:
            with open('telemetry_config.json', 'r') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"Error loading telemetry config: {e}")

    def _save_config(self):
        """Save telemetry configuration"""
        try:
            with open('telemetry_config.json', 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Error saving telemetry config: {e}")

    def on_message(self, message, msg_data):
        """Process incoming telemetry data and requests"""
        handled_telemetry = False

        try:
            # Check if message has telemetry fields
            lxm_fields = message.fields if hasattr(message, 'fields') else None

            if lxm_fields:
                source_hash = msg_data.get('source_hash', '')
                display_name = msg_data.get('display_name', 'Unknown')

                # Handle commands (telemetry request, ping, etc)
                if self.FIELD_COMMANDS in lxm_fields:
                    commands = lxm_fields[self.FIELD_COMMANDS]

                    # Commands is a list of command dictionaries
                    for cmd_dict in commands:
                        # Check for telemetry request command
                        if self.CMD_TELEMETRY_REQUEST in cmd_dict:
                            print(f"\nTelemetry request received from {display_name}")
                            handled_telemetry = True

                            # Check if requests are allowed
                            if not self.config.get('allow_requests', True):
                                print(f"  → Requests disabled, ignoring")
                                continue

                            # Check if trusted-only mode is enabled
                            if self.config.get('trusted_only', False):
                                trusted = self.config.get('trusted_contacts', [])
                                if source_hash not in trusted:
                                    print(f"  → Request from untrusted contact, ignoring")
                                    continue

                            # Auto-respond with our telemetry if configured
                            telemetry_data = self._pack_telemetry()
                            if telemetry_data:
                                try:
                                    # Send silent telemetry response (empty content/title)
                                    fields = {
                                        self.FIELD_TELEMETRY: telemetry_data
                                    }
                                    self.client.send_message(
                                        source_hash,
                                        "",  # Empty content for silent telemetry
                                        title="",  # Empty title
                                        fields=fields
                                    )
                                    print(f"  → Sent telemetry to {display_name}")
                                except Exception as e:
                                    print(f"  → Error sending telemetry: {e}")
                            else:
                                print(f"  → No telemetry configured to send")

                # Single telemetry snapshot
                if self.FIELD_TELEMETRY in lxm_fields:
                    telemetry = lxm_fields[self.FIELD_TELEMETRY]
                    print(f"\n[DEBUG] Received FIELD_TELEMETRY: {len(telemetry)} bytes, type: {type(telemetry)}")
                    print(f"[DEBUG] Received hex: {telemetry.hex()[:60]}...")
                    # Try to decode to see structure
                    try:
                        decoded = msgpack.unpackb(telemetry, strict_map_key=False)
                        print(f"[DEBUG] Decoded structure: {decoded}")
                    except:
                        pass
                    self._store_telemetry(source_hash, time.time(), telemetry)
                    print(f"\nTelemetry received from {display_name}:")
                    self._display_telemetry(source_hash, telemetry)
                    handled_telemetry = True

                # Telemetry stream (multiple entries)
                if self.FIELD_TELEMETRY_STREAM in lxm_fields:
                    stream = lxm_fields[self.FIELD_TELEMETRY_STREAM]
                    for entry in stream:
                        if len(entry) >= 2:
                            timestamp, telemetry = entry[0], entry[1]
                            self._store_telemetry(source_hash, timestamp, telemetry)

                    print(f"\nTelemetry stream received from {display_name}")
                    print(f"  Entries: {len(stream)}")
                    handled_telemetry = True

        except Exception as e:
            print(f"Error processing telemetry: {e}")

        # Return True to suppress default message display if we handled telemetry
        # and the message has no content (silent telemetry message)
        content = msg_data.get('content', '')
        if handled_telemetry and not content:
            return True

        return False

    def handle_command(self, cmd, parts):
        if cmd not in ['telemetry', 'telem']:
            return

        if len(parts) < 2:
            print("Usage: telem <set|send|request|show|clear|config|trust|collector>")
            print("\nData commands:")
            print("  telem set location <lat> <lon> [alt]")
            print("  telem set battery <percent>")
            print("  telem set temp <celsius>")
            print("  telem set pressure <hPa>")
            print("  telem set humidity <percent>")
            print("  telem send <contact>")
            print("  telem request <contact>")
            print("  telem show [contact]")
            print("  telem clear")
            print("\nConfiguration:")
            print("  telem config                        - Show current settings")
            print("  telem config requests <on|off>      - Allow/deny telemetry requests")
            print("  telem config trusted <on|off>       - Enable trusted-only mode")
            print("\nTrust management:")
            print("  telem trust list                    - List trusted contacts")
            print("  telem trust add <contact>           - Add contact to trusted list")
            print("  telem trust remove <contact>        - Remove contact from trusted list")
            print("\nCollector:")
            print("  telem collector status              - Show collector status")
            print("  telem collector set <address>       - Set collector address")
            print("  telem collector enable              - Enable collector")
            print("  telem collector disable             - Disable collector")
            print("  telem collector interval <seconds>  - Set send interval")
            return

        action = parts[1].lower()

        if action == 'set':
            self._handle_set(parts)
        elif action == 'send':
            self._handle_send(parts)
        elif action == 'request':
            self._handle_request(parts)
        elif action == 'show':
            self._handle_show(parts)
        elif action == 'clear':
            self._handle_clear()
        elif action == 'config':
            self._handle_config(parts)
        elif action == 'trust':
            self._handle_trust(parts)
        elif action == 'collector':
            self._handle_collector(parts)
        else:
            print(f"Unknown action: {action}")

    def _handle_set(self, parts):
        """Set local telemetry values"""
        if len(parts) < 3:
            print("Usage: telem set <type> <value...>")
            return

        # lxmf-cli joins args: "telem set battery 35" becomes ['telem', 'set', 'battery 35']
        raw_args = parts[2]
        arg_parts = raw_args.split()

        if len(arg_parts) < 2:
            print("Usage: telem set <type> <value...>")
            return

        sensor_type = arg_parts[0].lower()

        if sensor_type in ['location', 'loc', 'position', 'pos']:
            if len(arg_parts) < 3:
                print("Usage: telem set location <lat> <lon> [alt]")
                return

            try:
                lat = float(arg_parts[1])
                lon = float(arg_parts[2])
                alt = float(arg_parts[3]) if len(arg_parts) > 3 else 0.0

                self.config['location'] = [lat, lon, alt]
                self._save_config()

                print(f"Location set: {lat}, {lon}, {alt}m")

            except ValueError:
                print("Invalid coordinates")

        elif sensor_type in ['battery', 'bat']:
            try:
                percent = float(arg_parts[1])
                self.config['battery'] = percent
                self._save_config()
                print(f"Battery set: {percent}%")
            except ValueError:
                print("Invalid battery value")

        elif sensor_type in ['temp', 'temperature']:
            try:
                temp = float(arg_parts[1])
                self.config['temperature'] = temp
                self._save_config()
                print(f"Temperature set: {temp}C")
            except ValueError:
                print("Invalid temperature")

        elif sensor_type == 'pressure':
            try:
                pressure = float(arg_parts[1])
                self.config['pressure'] = pressure
                self._save_config()
                print(f"Pressure set: {pressure} hPa")
            except ValueError:
                print("Invalid pressure")

        elif sensor_type in ['humidity', 'hum']:
            try:
                humidity = float(arg_parts[1])
                self.config['humidity'] = humidity
                self._save_config()
                print(f"Humidity set: {humidity}%")
            except ValueError:
                print("Invalid humidity")

        else:
            print(f"Unknown sensor type: {sensor_type}")

    def _handle_send(self, parts):
        """Send telemetry to contact"""
        if len(parts) < 3:
            print("Usage: telem send <contact>")
            return

        # lxmf-cli joins args: "telem send alice" becomes ['telem', 'send', 'alice']
        raw_args = parts[2]
        arg_parts = raw_args.split()
        target = arg_parts[0]

        # Resolve target
        target_hash = self._resolve_target(target)
        if not target_hash:
            print(f"Contact not found: {target}")
            return

        # Pack telemetry data
        telemetry_data = self._pack_telemetry()

        if not telemetry_data:
            print("No telemetry data configured. Use 'telem set' first")
            return

        try:
            # Send silent telemetry (empty content/title, Sideband compatible)
            fields = {
                self.FIELD_TELEMETRY: telemetry_data
            }

            self.client.send_message(
                target_hash,
                "",  # Empty content for silent telemetry
                title="",  # Empty title
                fields=fields
            )

            print(f"Telemetry sent to {target}")

        except Exception as e:
            print(f"Error sending telemetry: {e}")

    def _handle_request(self, parts):
        """Request telemetry from contact"""
        if len(parts) < 3:
            print("Usage: telem request <contact>")
            return

        # lxmf-cli joins args: "telem request alice" becomes ['telem', 'request', 'alice']
        raw_args = parts[2]
        arg_parts = raw_args.split()
        target = arg_parts[0]

        target_hash = self._resolve_target(target)

        if not target_hash:
            print(f"Contact not found: {target}")
            return

        # Send telemetry request using Sideband protocol
        try:
            # Use FIELD_COMMANDS with CMD_TELEMETRY_REQUEST (matching Sideband)
            # Request format: [timebase, is_collector_request]
            fields = {
                self.FIELD_COMMANDS: [
                    {self.CMD_TELEMETRY_REQUEST: [time.time(), False]}
                ]
            }

            self.client.send_message(
                target_hash,
                "",  # Empty content for silent telemetry request
                title="",  # Empty title
                fields=fields
            )
            print(f"Telemetry request sent to {target}")
        except Exception as e:
            print(f"Error sending telemetry request: {e}")

    def _handle_show(self, parts):
        """Show telemetry data"""
        if len(parts) >= 3:
            # Show telemetry from specific contact
            target = parts[2]
            target_hash = self._resolve_target(target)

            if not target_hash:
                print(f"Contact not found: {target}")
                return

            if target_hash in self.telemetry_data:
                print(f"\nTelemetry from {target}:")
                for timestamp, data in self.telemetry_data[target_hash]:
                    dt = datetime.fromtimestamp(timestamp)
                    print(f"\n  {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                    self._display_telemetry(target_hash, data, indent=4)
            else:
                print(f"No telemetry data from {target}")

        else:
            # Show local telemetry config
            print("\nLocal Telemetry Configuration:")
            if self.config.get('location'):
                lat, lon, alt = self.config['location']
                print(f"  Location: {lat}, {lon} ({alt}m)")
            if self.config.get('battery') is not None:
                print(f"  Battery: {self.config['battery']}%")
            if self.config.get('temperature') is not None:
                print(f"  Temperature: {self.config['temperature']}C")
            if self.config.get('pressure') is not None:
                print(f"  Pressure: {self.config['pressure']} hPa")
            if self.config.get('humidity') is not None:
                print(f"  Humidity: {self.config['humidity']}%")

    def _handle_clear(self):
        """Clear all telemetry data"""
        self.telemetry_data = {}
        print("Telemetry data cleared")

    def _pack_telemetry(self):
        """Pack local telemetry data (Sideband compatible format)"""
        import struct

        sensors = {}

        # Add timestamp (Sideband always includes this)
        sensors[self.S_TIME] = int(time.time())

        if self.config.get('location'):
            lat, lon, alt = self.config['location']
            # Sideband packs location as 4-byte integers (multiply by 1e6 for precision - microdegrees)
            lat_packed = struct.pack(">i", int(lat * 1e6))
            lon_packed = struct.pack(">i", int(lon * 1e6))
            alt_packed = struct.pack(">i", int(alt * 100))  # centimeters

            # Add speed and heading as zero (not moving)
            speed_packed = struct.pack(">i", 0)
            heading_packed = struct.pack(">i", 0)

            # Add accuracy as 1m
            accuracy_packed = struct.pack(">H", 1)

            # Add timestamp
            sensors[self.S_LOCATION] = [
                lat_packed, lon_packed, alt_packed,
                speed_packed, heading_packed, accuracy_packed,
                int(time.time())
            ]

        if self.config.get('battery') is not None:
            # Sideband format: [percent, charging_state, extra_info]
            sensors[self.S_BATTERY] = [
                float(self.config['battery']),
                False,  # Not charging
                None    # No extra info
            ]

        if self.config.get('temperature') is not None:
            sensors[self.S_TEMPERATURE] = float(self.config['temperature'])

        if self.config.get('pressure') is not None:
            sensors[self.S_PRESSURE] = float(self.config['pressure'])

        if self.config.get('humidity') is not None:
            sensors[self.S_HUMIDITY] = float(self.config['humidity'])

        if not sensors:
            return None

        # Pack using msgpack (Sideband format)
        try:
            packed = msgpack.packb(sensors)
            print(f"  [DEBUG] Packed telemetry: {len(packed)} bytes, sensors: {list(sensors.keys())}")
            print(f"  [DEBUG] Sensor data keys: {list(sensors.keys())}")
            print(f"  [DEBUG] Packed hex: {packed.hex()[:60]}...")
            return packed
        except Exception as e:
            print(f"Error packing telemetry: {e}")
            return None

    def _store_telemetry(self, source_hash, timestamp, data):
        """Store received telemetry"""
        if source_hash not in self.telemetry_data:
            self.telemetry_data[source_hash] = []

        self.telemetry_data[source_hash].append([timestamp, data])

        # Keep only last 100 entries per contact
        if len(self.telemetry_data[source_hash]) > 100:
            self.telemetry_data[source_hash] = self.telemetry_data[source_hash][-100:]

    def _display_telemetry(self, source_hash, data, indent=2):
        """Display telemetry data"""
        import struct
        prefix = " " * indent
        try:
            # Unpack msgpack data (allow integer keys for Sideband compatibility)
            sensors = msgpack.unpackb(data, strict_map_key=False)

            for sensor_type, value in sensors.items():
                if sensor_type == self.S_TIME:
                    dt = datetime.fromtimestamp(value)
                    print(f"{prefix}Time: {dt.strftime('%Y-%m-%d %H:%M:%S')}")

                elif sensor_type == self.S_LOCATION:
                    # Sideband format: [lat_bytes, lon_bytes, alt_bytes, speed, heading, accuracy, timestamp]
                    if isinstance(value, list) and len(value) >= 3:
                        try:
                            lat = struct.unpack(">i", value[0])[0] / 1e6  # Sideband uses 1e6 multiplier (microdegrees)
                            lon = struct.unpack(">i", value[1])[0] / 1e6  # Sideband uses 1e6 multiplier (microdegrees)
                            alt = struct.unpack(">i", value[2])[0] / 100
                            print(f"{prefix}Location: {lat:.6f}, {lon:.6f} ({alt:.1f}m)")
                        except:
                            print(f"{prefix}Location: [packed data]")
                    else:
                        print(f"{prefix}Location: {value}")

                elif sensor_type == self.S_BATTERY:
                    # Sideband format: [percent, charging, extra]
                    if isinstance(value, list) and len(value) > 0:
                        percent = value[0]
                        charging = value[1] if len(value) > 1 else False
                        charge_str = " (charging)" if charging else ""
                        print(f"{prefix}Battery: {percent}%{charge_str}")
                    else:
                        print(f"{prefix}Battery: {value}%")

                elif sensor_type == self.S_TEMPERATURE:
                    print(f"{prefix}Temperature: {value}C")
                elif sensor_type == self.S_PRESSURE:
                    print(f"{prefix}Pressure: {value} hPa")
                elif sensor_type == self.S_HUMIDITY:
                    print(f"{prefix}Humidity: {value}%")
                elif sensor_type == 15:  # Device name
                    print(f"{prefix}Device: {value}")
                else:
                    print(f"{prefix}Sensor {sensor_type}: {value}")

        except Exception as e:
            print(f"{prefix}[Unable to decode telemetry: {e}]")

    def _format_telemetry_text(self, data):
        """Format telemetry as readable text"""
        import struct
        try:
            sensors = msgpack.unpackb(data, strict_map_key=False)
            lines = []

            for sensor_type, value in sensors.items():
                if sensor_type == self.S_LOCATION:
                    if isinstance(value, list) and len(value) >= 3:
                        try:
                            lat = struct.unpack(">i", value[0])[0] / 1e6
                            lon = struct.unpack(">i", value[1])[0] / 1e6
                            alt = struct.unpack(">i", value[2])[0] / 100
                            lines.append(f"Location: {lat:.6f}, {lon:.6f} ({alt:.1f}m)")
                        except:
                            lines.append(f"Location: [packed data]")
                elif sensor_type == self.S_BATTERY:
                    if isinstance(value, list) and len(value) > 0:
                        lines.append(f"Battery: {value[0]}%")
                    else:
                        lines.append(f"Battery: {value}%")
                elif sensor_type == self.S_TEMPERATURE:
                    lines.append(f"Temperature: {value}C")
                elif sensor_type == self.S_PRESSURE:
                    lines.append(f"Pressure: {value} hPa")
                elif sensor_type == self.S_HUMIDITY:
                    lines.append(f"Humidity: {value}%")

            return "\n".join(lines)

        except Exception as e:
            return f"[Telemetry data: {len(data)} bytes]"

    def _resolve_target(self, target):
        """Resolve contact name or index to hash"""
        # Try by index
        if target.isdigit():
            index = int(target)
            for name, data in self.client.contacts.items():
                if data.get('index') == index:
                    return data['hash']

        # Try by name
        if target in self.client.contacts:
            return self.client.contacts[target]['hash']

        # Try as direct hash
        clean_hash = target.replace(':', '').replace(' ', '')
        if len(clean_hash) == 32:
            return clean_hash

        return None

    def _handle_config(self, parts):
        """Handle config commands"""
        if len(parts) < 3:
            # Show current configuration
            print("\n--- Telemetry Configuration ---")
            print(f"  Requests allowed: {'Yes' if self.config.get('allow_requests', True) else 'No'}")
            print(f"  Trusted-only mode: {'Yes' if self.config.get('trusted_only', False) else 'No'}")
            print(f"  Trusted contacts: {len(self.config.get('trusted_contacts', []))}")
            print(f"  Collector enabled: {'Yes' if self.config.get('collector_enabled', False) else 'No'}")
            if self.config.get('collector_address'):
                print(f"  Collector address: {self.config['collector_address'][:16]}...")
            print(f"  Collector interval: {self.config.get('collector_interval', 3600)}s")
            print()
            return

        # Parse config subcommand
        raw_args = parts[2]
        arg_parts = raw_args.split()

        if len(arg_parts) < 2:
            print("Usage: telem config <requests|trusted> <on|off>")
            return

        setting = arg_parts[0].lower()
        value = arg_parts[1].lower()

        if setting == 'requests':
            if value in ['on', 'enable', 'true', '1']:
                self.config['allow_requests'] = True
                self._save_config()
                print("Telemetry requests enabled")
            elif value in ['off', 'disable', 'false', '0']:
                self.config['allow_requests'] = False
                self._save_config()
                print("Telemetry requests disabled")
            else:
                print("Usage: telem config requests <on|off>")

        elif setting in ['trusted', 'trustedonly', 'trusted-only']:
            if value in ['on', 'enable', 'true', '1']:
                self.config['trusted_only'] = True
                self._save_config()
                print("Trusted-only mode enabled")
                print(f"Only {len(self.config.get('trusted_contacts', []))} trusted contacts can request telemetry")
            elif value in ['off', 'disable', 'false', '0']:
                self.config['trusted_only'] = False
                self._save_config()
                print("Trusted-only mode disabled")
            else:
                print("Usage: telem config trusted <on|off>")
        else:
            print("Unknown setting. Use 'requests' or 'trusted'")

    def _handle_trust(self, parts):
        """Handle trust management commands"""
        if len(parts) < 3:
            print("Usage: telem trust <list|add|remove> [contact]")
            return

        raw_args = parts[2]
        arg_parts = raw_args.split()
        action = arg_parts[0].lower()

        if action == 'list':
            trusted = self.config.get('trusted_contacts', [])
            if not trusted:
                print("No trusted contacts")
                return

            print(f"\n--- Trusted Contacts ({len(trusted)}) ---")
            for contact_hash in trusted:
                # Find contact name
                name = None
                for contact_name, contact_data in self.client.contacts.items():
                    if contact_data.get('hash') == contact_hash:
                        name = contact_name
                        break

                if name:
                    print(f"  ✓ {name} ({contact_hash[:16]}...)")
                else:
                    print(f"  ✓ {contact_hash}")
            print()

        elif action in ['add', 'trust']:
            if len(arg_parts) < 2:
                print("Usage: telem trust add <contact>")
                return

            target = arg_parts[1]
            target_hash = self._resolve_target(target)

            if not target_hash:
                print(f"Contact not found: {target}")
                return

            trusted = self.config.get('trusted_contacts', [])
            if target_hash in trusted:
                print(f"Contact already trusted: {target}")
                return

            trusted.append(target_hash)
            self.config['trusted_contacts'] = trusted
            self._save_config()
            print(f"Added {target} to trusted contacts")

        elif action in ['remove', 'untrust', 'rm', 'del']:
            if len(arg_parts) < 2:
                print("Usage: telem trust remove <contact>")
                return

            target = arg_parts[1]
            target_hash = self._resolve_target(target)

            if not target_hash:
                print(f"Contact not found: {target}")
                return

            trusted = self.config.get('trusted_contacts', [])
            if target_hash not in trusted:
                print(f"Contact not in trusted list: {target}")
                return

            trusted.remove(target_hash)
            self.config['trusted_contacts'] = trusted
            self._save_config()
            print(f"Removed {target} from trusted contacts")

        else:
            print("Unknown action. Use 'list', 'add', or 'remove'")

    def _handle_collector(self, parts):
        """Handle collector commands"""
        if len(parts) < 3:
            print("Usage: telem collector <status|set|enable|disable|interval>")
            return

        raw_args = parts[2]
        arg_parts = raw_args.split()
        action = arg_parts[0].lower()

        if action == 'status':
            print("\n--- Telemetry Collector ---")
            print(f"  Status: {'Enabled' if self.config.get('collector_enabled', False) else 'Disabled'}")
            if self.config.get('collector_address'):
                addr = self.config['collector_address']
                # Try to find name
                name = None
                for contact_name, contact_data in self.client.contacts.items():
                    if contact_data.get('hash') == addr:
                        name = contact_name
                        break

                if name:
                    print(f"  Address: {name} ({addr[:16]}...)")
                else:
                    print(f"  Address: {addr}")
            else:
                print(f"  Address: Not set")

            interval = self.config.get('collector_interval', 3600)
            print(f"  Interval: {interval}s ({interval//60} minutes)")
            print()

        elif action == 'set':
            if len(arg_parts) < 2:
                print("Usage: telem collector set <contact>")
                return

            target = arg_parts[1]
            target_hash = self._resolve_target(target)

            if not target_hash:
                print(f"Contact not found: {target}")
                return

            self.config['collector_address'] = target_hash
            self._save_config()
            print(f"Collector address set to: {target}")
            print("Use 'telem collector enable' to start automatic sending")

        elif action == 'enable':
            if not self.config.get('collector_address'):
                print("Set collector address first: telem collector set <contact>")
                return

            self.config['collector_enabled'] = True
            self._save_config()
            self._start_collector()
            print("Collector enabled")
            print(f"Telemetry will be sent every {self.config.get('collector_interval', 3600)}s")

        elif action == 'disable':
            self.config['collector_enabled'] = False
            self._save_config()
            self._stop_collector()
            print("Collector disabled")

        elif action == 'interval':
            if len(arg_parts) < 2:
                print("Usage: telem collector interval <seconds>")
                return

            try:
                seconds = int(arg_parts[1])
                if seconds < 60:
                    print("Interval must be at least 60 seconds")
                    return

                self.config['collector_interval'] = seconds
                self._save_config()
                print(f"Collector interval set to {seconds}s ({seconds//60} minutes)")
            except ValueError:
                print("Invalid interval value")

        else:
            print("Unknown action. Use 'status', 'set', 'enable', 'disable', or 'interval'")

    def _start_collector(self):
        """Start the collector background thread"""
        if self.collector_running:
            return

        if not self.config.get('collector_enabled', False):
            return

        if not self.config.get('collector_address'):
            return

        self.collector_running = True
        self.collector_thread = threading.Thread(
            target=self._collector_loop,
            daemon=True
        )
        self.collector_thread.start()
        print(f"Collector thread started (interval: {self.config.get('collector_interval', 3600)}s)")

    def _stop_collector(self):
        """Stop the collector background thread"""
        if not self.collector_running:
            return

        self.collector_running = False
        print("Collector thread stopped")

    def _collector_loop(self):
        """Background thread that sends telemetry to collector at intervals"""
        print("Collector: Background loop started")

        while self.collector_running:
            try:
                # Check if enough time has passed since last send
                current_time = time.time()
                interval = self.config.get('collector_interval', 3600)

                if current_time - self.last_collector_send >= interval:
                    # Send telemetry to collector
                    self._send_to_collector()
                    self.last_collector_send = current_time

                # Sleep for a short time before checking again
                time.sleep(10)  # Check every 10 seconds

            except Exception as e:
                print(f"Collector error: {e}")
                time.sleep(30)  # Wait longer on error

        print("Collector: Background loop stopped")

    def _send_to_collector(self):
        """Send telemetry to the configured collector"""
        try:
            collector_address = self.config.get('collector_address')
            if not collector_address:
                return

            # Pack telemetry data
            telemetry_data = self._pack_telemetry()
            if not telemetry_data:
                print("Collector: No telemetry data to send")
                return

            # Find collector name for display
            collector_name = None
            for contact_name, contact_data in self.client.contacts.items():
                if contact_data.get('hash') == collector_address:
                    collector_name = contact_name
                    break

            display_name = collector_name or collector_address[:16] + "..."

            # Send as collector request (timebase, is_collector_request=True)
            fields = {
                self.FIELD_TELEMETRY: telemetry_data
            }

            self.client.send_message(
                collector_address,
                "",  # Empty content for silent telemetry
                title="",  # Empty title
                fields=fields
            )

            print(f"📊 Collector: Sent telemetry to {display_name}")

        except Exception as e:
            print(f"Collector: Error sending telemetry: {e}")

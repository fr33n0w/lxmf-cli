"""
Ping Plugin for LXMF-CLI
Uses Reticulum's Link mechanism to ping destinations and measure response time.
"""

import time
import RNS
import threading

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['ping']
        self.description = "Ping destinations using RNS path requests (usage: ping [-c|-p] <target>)"

        print("Ping Plugin loaded!")

    def on_message(self, message, msg_data):
        """Not used for RNS ping"""
        return False

    def handle_command(self, cmd, parts):
        if cmd != 'ping':
            return

        if len(parts) < 2:
            print("Usage: ping [-c|-p] <target> [count]")
            print("Examples:")
            print("  ping Alice          (ping contact by name)")
            print("  ping -c 5           (ping contact #5)")
            print("  ping -c 5 3         (ping contact #5 three times)")
            print("  ping -p 30          (ping peer #30)")
            print("  ping -p 30 5        (ping peer #30 five times)")
            print("  ping abc123def      (ping hash directly)")
            print("  ping Alice 3        (ping 3 times)")
            return

        # Check for flags
        flag = None
        target_idx = 1
        if parts[1].startswith('-'):
            flag = parts[1]
            if len(parts) < 3:
                print(f"{self.client.Fore.RED}Error: Flag {flag} requires a target{self.client.Style.RESET_ALL}")
                return
            target_idx = 2

        # Extract target and count
        # lxmf-cli may join multiple args after a flag into one string
        # e.g., "ping -c 11 2" becomes parts=['ping', '-c', '11 2']
        raw_target = parts[target_idx]

        # Split the target in case it contains the count
        target_parts = raw_target.split()
        target = target_parts[0]

        # Check if count was included in the same string
        if len(target_parts) > 1 and target_parts[1].isdigit():
            count = int(target_parts[1])
        # Otherwise check if there's a separate count parameter
        elif len(parts) > target_idx + 1 and parts[target_idx + 1].isdigit():
            count = int(parts[target_idx + 1])
        else:
            count = 1

        # Resolve target to hash
        target_hash = self._resolve_target(target, flag)

        if not target_hash:
            print(f"{self.client.Fore.RED}Error: Could not resolve target '{target}'{self.client.Style.RESET_ALL}")
            if flag:
                print(f"Make sure the {flag} target exists")
            else:
                print("Target can be: contact name, hash, or use -c/-p flags for index")
            return

        # Convert hex string to bytes
        try:
            dest_hash_bytes = bytes.fromhex(target_hash)
        except ValueError:
            print(f"{self.client.Fore.RED}Error: Invalid hash format{self.client.Style.RESET_ALL}")
            return

        # Get display name for target
        target_name = self._get_display_name(target, target_hash)

        # Send ping(s) in background thread
        print(f"\n{self.client.Fore.CYAN}Pinging {target_name} ({target_hash[:16]}...) {count} time(s):{self.client.Style.RESET_ALL}")

        ping_thread = threading.Thread(
            target=self._run_ping_sequence,
            args=(dest_hash_bytes, target_name, count),
            daemon=True
        )
        ping_thread.start()

        print(f"{self.client.Fore.YELLOW}💡 Ping running in background. You can continue working.{self.client.Style.RESET_ALL}\n")

    def _resolve_target(self, target, flag=None):
        """Resolve target to hash (supports contact name, peer index, or direct hash)"""

        # Handle flags
        if flag == '-c':
            # Contact by index
            if target.isdigit():
                contact_index = int(target)
                for name, data in self.client.contacts.items():
                    if data.get('index') == contact_index:
                        return data['hash']
            return None

        elif flag == '-p':
            # Peer by index
            if target.isdigit():
                peer_index = int(target)
                for peer_hash, peer_data in self.client.announced_peers.items():
                    if peer_data.get('index') == peer_index:
                        return peer_hash.replace('<', '').replace('>', '')
            # Also allow hash with -p flag
            clean_hash = target.replace(':', '').replace(' ', '').replace('<', '').replace('>', '')
            if len(clean_hash) == 32:
                return clean_hash
            return None

        # No flag - auto-detect
        # Try as contact name
        if target in self.client.contacts:
            return self.client.contacts[target]['hash']

        # Try as direct hash (clean it)
        clean_hash = target.replace(':', '').replace(' ', '').replace('<', '').replace('>', '')
        if len(clean_hash) == 32:  # Valid hash length
            return clean_hash

        return None

    def _get_display_name(self, target, target_hash):
        """Get display name for target"""

        # Check if it's a contact
        for name, data in self.client.contacts.items():
            if data['hash'] == target_hash:
                return name

        # Check if it's a peer
        for peer_hash, peer_data in self.client.announced_peers.items():
            clean_peer_hash = peer_hash.replace('<', '').replace('>', '')
            if clean_peer_hash == target_hash:
                return peer_data.get('display_name', target_hash[:16])

        return target_hash[:16]

    def _run_ping_sequence(self, dest_hash_bytes, target_name, count):
        """Run a sequence of pings in the background"""
        stats = {
            'sent': 0,
            'received': 0,
            'failed': 0,
            'rtts': []
        }

        for i in range(count):
            if i > 0:
                time.sleep(1)  # Wait 1 second between pings

            result = self._send_ping(dest_hash_bytes, target_name, i + 1, count)
            stats['sent'] += 1

            if result is not None:
                if result > 0:  # Success with RTT
                    stats['received'] += 1
                    stats['rtts'].append(result)
                else:  # Failed
                    stats['failed'] += 1
            else:  # No result (path/identity error)
                stats['failed'] += 1

        # Print statistics
        self._print_stats(target_name, stats)

    def _print_stats(self, target_name, stats):
        """Print ping statistics"""
        print(f"\n--- Ping statistics for {target_name} ---")
        print(f"  Packets: {stats['sent']} sent, {stats['received']} received, {stats['failed']} failed")

        if stats['received'] > 0:
            loss_pct = (stats['failed'] / stats['sent']) * 100
            print(f"  Packet loss: {loss_pct:.1f}%")

            min_rtt = min(stats['rtts'])
            max_rtt = max(stats['rtts'])
            avg_rtt = sum(stats['rtts']) / len(stats['rtts'])

            print(f"  Round-trip times: min={min_rtt:.2f}ms, avg={avg_rtt:.2f}ms, max={max_rtt:.2f}ms")
        else:
            print(f"  Packet loss: 100%")
        print()

    def _send_ping(self, dest_hash_bytes, target_name, seq, total):
        """Send a ping using RNS packet with proof request
        Returns: RTT in ms if successful, 0 if failed, None if no path/identity
        """

        print(f"  [{seq}/{total}] Pinging...", end="", flush=True)

        # First ensure we have a path
        if not RNS.Transport.has_path(dest_hash_bytes):
            RNS.Transport.request_path(dest_hash_bytes)

            # Wait for path with short timeout
            path_timeout = 10.0
            check_interval = 0.1
            elapsed = 0

            while elapsed < path_timeout:
                time.sleep(check_interval)
                elapsed += check_interval
                if RNS.Transport.has_path(dest_hash_bytes):
                    break

            if not RNS.Transport.has_path(dest_hash_bytes):
                print(f"\r  [{seq}/{total}] ✗ No path to {target_name}" + " " * 20)
                return None

        # Create a destination to send the packet to
        dest_identity = RNS.Identity.recall(dest_hash_bytes)
        if not dest_identity:
            print(f"\r  [{seq}/{total}] ✗ Could not recall identity" + " " * 20)
            return None

        destination = RNS.Destination(
            dest_identity,
            RNS.Destination.OUT,
            RNS.Destination.SINGLE,
            "lxmf",
            "delivery"
        )

        # Create ping packet with proof request
        ping_data = f"PING_{seq}".encode("utf-8")

        # Track timing
        start_time = time.time()
        proof_received = threading.Event()
        rtt_ms = [0]  # Use list to allow modification in callback

        def proof_callback(receipt):
            if receipt.get_status() == RNS.PacketReceipt.DELIVERED:
                rtt_ms[0] = (time.time() - start_time) * 1000
                proof_received.set()

        # Send packet and get receipt
        packet = RNS.Packet(destination, ping_data)
        receipt = packet.send()

        # Check if receipt was created
        if not receipt:
            print(f"\r  [{seq}/{total}] ✗ Failed to send packet (no receipt)" + " " * 20)
            return 0

        # Set receipt callback
        receipt.set_delivery_callback(proof_callback)

        # Wait for proof
        if proof_received.wait(timeout=30.0):
            hops = RNS.Transport.hops_to(dest_hash_bytes)
            # Clear line and print result
            print(f"\r  [{seq}/{total}] ✓ Reply from {target_name}: {rtt_ms[0]:.2f}ms, {hops} hops" + " " * 20)
            return rtt_ms[0]
        else:
            # Check receipt status
            status = receipt.get_status()
            if status == RNS.PacketReceipt.FAILED:
                print(f"\r  [{seq}/{total}] ✗ Packet delivery failed" + " " * 20)
            else:
                print(f"\r  [{seq}/{total}] ✗ Timeout: No proof received" + " " * 20)
            return 0

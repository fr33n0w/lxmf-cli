# rangetest_server.py
import time
import threading
from datetime import datetime
import RNS
import LXMF

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['rangetest', 'rt', 'rangestop', 'rs', 'rangestatus']
        self.description = "Range Test Server - Send opportunistic pings for mobile testing"
        
        # Active tests: {user_hash: test_data}
        self.active_tests = {}
        self.test_threads = {}
        
        # Safety limits
        self.MAX_PINGS = 500
        self.MIN_INTERVAL = 5
        self.MAX_INTERVAL = 300
    
    def on_message(self, message, msg_data):
        """Handle incoming commands - wrapped in try/except to never crash"""
        try:
            content = msg_data['content'].strip()
            source_hash = msg_data['source_hash']
            
            # Start test command (rangetest or rt)
            if content.lower().startswith('rangetest ') or content.lower().startswith('rt '):
                try:
                    parts = content.split()
                    if len(parts) < 3:
                        self.safe_send(source_hash, 
                            "❌ Usage: rt <count> <interval>\n"
                            "Example: rt 50 10")
                        return True
                    
                    count = int(parts[1])
                    interval = int(parts[2])
                    
                    # Validate
                    if count < 1 or count > self.MAX_PINGS:
                        self.safe_send(source_hash, 
                            f"❌ Count must be 1-{self.MAX_PINGS}")
                        return True
                    
                    if interval < self.MIN_INTERVAL or interval > self.MAX_INTERVAL:
                        self.safe_send(source_hash, 
                            f"❌ Interval must be {self.MIN_INTERVAL}-{self.MAX_INTERVAL} seconds")
                        return True
                    
                    # Start test
                    self.start_test(source_hash, count, interval)
                    return True
                
                except ValueError:
                    self.safe_send(source_hash, 
                        "❌ Invalid numbers\n"
                        "Usage: rt <count> <interval>")
                    return True
                except Exception as e:
                    print(f"[Range Test] ⚠️ Error parsing command: {e}")
                    self.safe_send(source_hash, "❌ Command error")
                    return True
            
            # Stop test command (rangestop or rs)
            elif content.lower() == 'rangestop' or content.lower() == 'rs':
                if source_hash in self.active_tests:
                    self.stop_test(source_hash)
                    return True
                else:
                    self.safe_send(source_hash, "❌ No active test")
                    return True
            
            # Status command
            elif content.lower() == 'rangestatus':
                try:
                    if source_hash in self.active_tests:
                        test = self.active_tests[source_hash]
                        elapsed = int(time.time() - test['start_time'])
                        remaining = int((test['count'] - test['current']) * test['interval'])
                        percent = int((test['current'] / test['count']) * 100)
                        
                        self.safe_send(source_hash,
                            f"📡 Range Test Active\n"
                            f"Progress: {test['current']}/{test['count']} ({percent}%)\n"
                            f"Elapsed: {elapsed}s\n"
                            f"Remaining: ~{remaining}s")
                    else:
                        self.safe_send(source_hash, "✅ No active test")
                except Exception as e:
                    print(f"[Range Test] ⚠️ Status error: {e}")
                    self.safe_send(source_hash, "❌ Status error")
                return True
        
        except Exception as e:
            print(f"[Range Test] ⚠️ Message handler error: {e}")
            # Never crash - just log and continue
        
        return False
    
    def start_test(self, user_hash, count, interval):
        """Start sending pings to user"""
        try:
            # Stop existing test if any
            if user_hash in self.active_tests:
                self.stop_test(user_hash, notify=False)
            
            # Create test record
            self.active_tests[user_hash] = {
                'count': count,
                'interval': interval,
                'current': 0,
                'start_time': time.time(),
                'stop_flag': threading.Event(),
                'failed_sends': 0  # Track failures but don't stop
            }
            
            contact = self.client.format_contact_display_short(user_hash)
            start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Log locally
            print(f"\n{'='*60}")
            print(f"🚀 Range Test Started")
            print(f"{'='*60}")
            print(f"Client: {contact}")
            print(f"Pings: {count} @ {interval}s interval")
            print(f"Duration: ~{(count * interval) // 60}m {(count * interval) % 60}s")
            print(f"Started: {start_time}")
            print(f"{'='*60}\n")
            
            # Send confirmation and start message
            self.safe_send(user_hash,
                f"✅ Range Test Starting\n"
                f"Pings: {count} @ {interval}s\n"
                f"Duration: ~{(count * interval) // 60}m {(count * interval) % 60}s\n\n"
                f"💡 Quick commands:\n"
                f"  rs = stop test\n"
                f"  rangestatus = check progress")
            
            time.sleep(1)  # Small delay before first ping
            
            start_time_short = datetime.now().strftime('%H:%M')
            self.send_opportunistic(user_hash, 
                f"[RangeTest] [{start_time_short}] 🚀 Test started")
            
            # Start worker thread
            thread = threading.Thread(
                target=self._test_worker,
                args=(user_hash,),
                daemon=True
            )
            self.test_threads[user_hash] = thread
            thread.start()
        
        except Exception as e:
            print(f"[Range Test] ❌ Start error: {e}")
            import traceback
            traceback.print_exc()
    
    def _test_worker(self, user_hash):
        """Worker thread - sends pings - NEVER STOPS on errors"""
        test = self.active_tests.get(user_hash)
        if not test:
            return
        
        contact = self.client.format_contact_display_short(user_hash)
        
        # CRITICAL: Wrap entire worker in try/except to prevent thread crash
        try:
            while test['current'] < test['count']:
                # Check stop flag
                if test['stop_flag'].is_set():
                    print(f"[Range Test] ⚠️ Test stopped for {contact}")
                    break
                
                # Increment counter BEFORE sending (so we track attempts, not successes)
                test['current'] += 1
                current_ping = test['current']
                
                # Calculate progress
                percent = int((current_ping / test['count']) * 100)
                remaining_pings = test['count'] - current_ping
                remaining_seconds = remaining_pings * test['interval']
                
                # Format remaining time
                if remaining_seconds >= 60:
                    remaining_str = f"{remaining_seconds // 60}m"
                else:
                    remaining_str = f"{remaining_seconds}s"
                
                # Get current time for ping message
                ping_time = datetime.now().strftime('%H:%M')
                
                # Build message with % and remaining time
                msg = f"[RangeTest] [{ping_time}] 📡 Ping #{current_ping} of {test['count']} • {percent}% • ~{remaining_str}"
                
                # Try to send - but NEVER stop on error
                try:
                    print(f"[Range Test] Sending ping {current_ping}/{test['count']} ({percent}%, ~{remaining_str}) @ {ping_time} → {contact}")
                    self.send_opportunistic(user_hash, msg)
                except Exception as send_error:
                    # Log but CONTINUE
                    print(f"[Range Test] ⚠️ Send failed (continuing): {send_error}")
                    test['failed_sends'] += 1
                
                # Wait for next interval (check stop flag every second)
                # CRITICAL: Even if interval wait fails, we continue
                try:
                    for _ in range(test['interval']):
                        if test['stop_flag'].wait(1):
                            break
                except Exception as wait_error:
                    print(f"[Range Test] ⚠️ Wait error (continuing): {wait_error}")
                    time.sleep(1)  # Fallback sleep
            
            # Test complete (if not stopped)
            if not test['stop_flag'].is_set():
                end_time = datetime.now().strftime('%H:%M')
                elapsed = int(time.time() - test['start_time'])
                
                print(f"\n{'='*60}")
                print(f"✅ Range Test Complete")
                print(f"{'='*60}")
                print(f"Client: {contact}")
                print(f"Sent: {test['current']}/{test['count']} pings")
                if test['failed_sends'] > 0:
                    print(f"Failed: {test['failed_sends']} (continued anyway)")
                print(f"Duration: {elapsed // 60}m {elapsed % 60}s")
                print(f"Finished: {end_time}")
                print(f"{'='*60}\n")
                
                # Try to send completion message, but don't crash if it fails
                try:
                    self.send_opportunistic(user_hash,
                        f"[RangeTest] [{end_time}] ✅ Test complete! 100%")
                except Exception as e:
                    print(f"[Range Test] ⚠️ Could not send completion message: {e}")
        
        except Exception as e:
            # LAST RESORT: Log catastrophic error but don't crash
            print(f"[Range Test] ❌ CRITICAL worker error: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            # ALWAYS cleanup, even if something goes wrong
            try:
                if user_hash in self.active_tests:
                    del self.active_tests[user_hash]
                if user_hash in self.test_threads:
                    del self.test_threads[user_hash]
            except Exception as cleanup_error:
                print(f"[Range Test] ⚠️ Cleanup error: {cleanup_error}")
    
    def stop_test(self, user_hash, notify=True):
        """Stop active test"""
        try:
            if user_hash not in self.active_tests:
                return
            
            test = self.active_tests[user_hash]
            test['stop_flag'].set()
            
            contact = self.client.format_contact_display_short(user_hash)
            percent = int((test['current'] / test['count']) * 100)
            print(f"\n[Range Test] ⚠️ Stopping test for {contact} at {percent}%\n")
            
            if notify:
                stop_time = datetime.now().strftime('%H:%M')
                self.send_opportunistic(user_hash,
                    f"[RangeTest] [{stop_time}] ⚠️ Test stopped at {percent}%")
        
        except Exception as e:
            print(f"[Range Test] ⚠️ Stop error: {e}")
    
    def send_opportunistic(self, dest_hash, content):
        """Send opportunistic message (fire-and-forget) - wrapped for safety"""
        try:
            # Normalize hash
            dest_hash_str = dest_hash.replace(":", "").replace(" ", "").replace("<", "").replace(">", "")
            dest_hash_bytes = bytes.fromhex(dest_hash_str)
            
            # Get identity
            dest_identity = RNS.Identity.recall(dest_hash_bytes)
            if dest_identity is None:
                # Try to request path, but don't wait too long
                RNS.Transport.request_path(dest_hash_bytes)
                time.sleep(0.3)  # Shorter wait
                dest_identity = RNS.Identity.recall(dest_hash_bytes)
                
                if dest_identity is None:
                    print(f"[Range Test] ⚠️ Cannot reach destination (continuing anyway)")
                    return  # Don't crash - just skip this message
            
            # Create destination
            dest = RNS.Destination(
                dest_identity,
                RNS.Destination.OUT,
                RNS.Destination.SINGLE,
                "lxmf",
                "delivery"
            )
            
            # Create opportunistic message
            message = LXMF.LXMessage(
                destination=dest,
                source=self.client.destination,
                content=content,
                title="",
                desired_method=LXMF.LXMessage.OPPORTUNISTIC
            )
            
            # Send without tracking
            self.client.router.handle_outbound(message)
        
        except Exception as e:
            # Log but don't crash
            print(f"[Range Test] ⚠️ Send error (continuing): {e}")
    
    def safe_send(self, dest_hash, content):
        """Send message with standard delivery - used for commands/confirmations"""
        try:
            self.client.send_message(dest_hash, content)
        except Exception as e:
            print(f"[Range Test] ⚠️ Safe send error: {e}")
    
    def handle_command(self, cmd, parts):
        """Handle local commands"""
        try:
            if cmd in ['rangetest', 'rt']:
                if self.active_tests:
                    print("\n📡 Active Range Tests:")
                    print("─"*60)
                    for user_hash, test in self.active_tests.items():
                        contact = self.client.format_contact_display_short(user_hash)
                        elapsed = int(time.time() - test['start_time'])
                        remaining = int((test['count'] - test['current']) * test['interval'])
                        percent = int((test['current'] / test['count']) * 100)
                        print(f"  {contact}:")
                        print(f"    Progress: {test['current']}/{test['count']} ({percent}%)")
                        print(f"    Elapsed: {elapsed}s | Remaining: ~{remaining}s")
                        if test['failed_sends'] > 0:
                            print(f"    Failed: {test['failed_sends']} (test continuing)")
                    print("─"*60 + "\n")
                else:
                    print("\n✅ No active tests\n")
                    print("💡 Quick start: send <contact> rt 50 10")
                    print("   (50 pings, 10 second interval)")
                    print("\n💡 Full command: send <contact> rangetest 50 10\n")
        
        except Exception as e:
            print(f"[Range Test] ⚠️ Command handler error: {e}")

# rangetest.py
import time
import threading
import json
import subprocess
import platform
import os
from datetime import datetime

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['rangetest', 'rangestop', 'rangestatus']
        self.description = "Range testing - automated bidirectional testing with GPS"
        
        # Active test sessions
        self.active_tests = {}  # Tests we're RUNNING (as server)
        self.test_threads = {}
        
        # Active client sessions (tests we requested)
        self.client_tests = {}  # Tests we're DRIVING (as client)
        self.client_threads = {}
        
    def on_message(self, message, msg_data):
        """Handle incoming range test commands and responses"""
        content = msg_data['content'].strip()
        source_hash = msg_data['source_hash']
        
        # === SERVER SIDE: Handle commands from mobile clients ===
        
        # Check if this is a rangetest START command
        if content.lower().startswith('rangetest '):
            try:
                parts = content.split()
                if len(parts) >= 3:
                    count = int(parts[1])
                    interval = int(parts[2])
                    
                    # Validate parameters
                    if count < 1 or count > 1000:
                        self.client.send_message(source_hash, "❌ Count must be 1-1000")
                        return True
                    
                    if interval < 5 or interval > 300:
                        self.client.send_message(source_hash, "❌ Interval must be 5-300 seconds")
                        return True
                    
                    # Start range test SERVER
                    self.start_range_test_server(source_hash, count, interval)
                    return True
                else:
                    self.client.send_message(source_hash, "❌ Usage: rangetest <count> <interval>\nExample: rangetest 10 20")
                    return True
            except ValueError:
                self.client.send_message(source_hash, "❌ Invalid numbers. Usage: rangetest <count> <interval>")
                return True
        
        # Check if this is a rangestop command
        elif content.lower() == 'rangestop':
            self.stop_range_test_server(source_hash)
            return True
        
        # === CLIENT SIDE: Handle responses from server (we're driving) ===
        
        # Check if this is a response to OUR test request
        elif content.startswith('📡 RANGE TEST ['):
            # This is a test ping FROM the server TO us (we're the mobile client)
            # Extract message number
            try:
                # Parse: "📡 RANGE TEST [5/10]"
                import re
                match = re.search(r'\[(\d+)/(\d+)\]', content)
                if match:
                    current = int(match.group(1))
                    total = int(match.group(2))
                    
                    # Reply with GPS data
                    self.send_gps_response(source_hash, current, total)
                    
                    # Show notification with sound/vibration
                    self.notify_range_ping(current, total)
                    
                    return False  # Let normal notification show too
            except:
                pass
        
        return False
    
    def start_range_test_server(self, source_hash, count, interval):
        """Start an automated range test session (SERVER MODE - we send pings)"""
        # Stop any existing test for this source
        if source_hash in self.active_tests:
            self.stop_range_test_server(source_hash)
        
        # Store test configuration
        self.active_tests[source_hash] = {
            'count': count,
            'interval': interval,
            'current': 0,
            'start_time': time.time(),
            'stop_flag': threading.Event(),
            'gps_log': []  # Store GPS data from client responses
        }
        
        # Get display name for logging
        contact_display = self.client.format_contact_display_short(source_hash)
        
        print(f"\n🎯 RANGE TEST STARTED (SERVER MODE)")
        print(f"   Target: {contact_display}")
        print(f"   Messages: {count}")
        print(f"   Interval: {interval}s\n")
        
        # Send confirmation
        self.client.send_message(
            source_hash, 
            f"✅ Range test started!\n📊 {count} pings @ {interval}s interval\n⏱️ Duration: ~{(count * interval) // 60}m {(count * interval) % 60}s\n\n🚗 Drive and I'll track your GPS!\n\nType 'rangestop' to abort"
        )
        
        # Start test thread
        thread = threading.Thread(
            target=self._range_test_server_worker,
            args=(source_hash,),
            daemon=True
        )
        self.test_threads[source_hash] = thread
        thread.start()
    
    def _range_test_server_worker(self, source_hash):
        """Worker thread that sends test pings (SERVER MODE)"""
        test_config = self.active_tests[source_hash]
        contact_display = self.client.format_contact_display_short(source_hash)
        
        try:
            while test_config['current'] < test_config['count']:
                # Check stop flag
                if test_config['stop_flag'].is_set():
                    break
                
                test_config['current'] += 1
                current = test_config['current']
                total = test_config['count']
                
                # Calculate timing
                elapsed = time.time() - test_config['start_time']
                estimated_total = test_config['interval'] * total
                remaining = estimated_total - elapsed
                
                # Get local time
                timestamp = datetime.now().strftime('%H:%M:%S')
                
                # Build message
                msg = f"📡 RANGE TEST [{current}/{total}]\n"
                msg += f"🕐 Time: {timestamp}\n"
                msg += f"⏱️ Elapsed: {int(elapsed)}s\n"
                msg += f"⏳ Remaining: ~{int(remaining)}s\n"
                msg += f"📊 Progress: {int((current/total)*100)}%\n"
                msg += f"\n🚗 Reply with your GPS position!"
                
                # Send message
                print(f"[Range Test] 📡 Ping {current}/{total} → {contact_display}")
                self.client.send_message(source_hash, msg)
                
                # Wait for interval (check stop flag periodically)
                for _ in range(test_config['interval']):
                    if test_config['stop_flag'].wait(1):
                        break
            
            # Test completed - generate summary
            if not test_config['stop_flag'].is_set():
                self.send_test_summary(source_hash)
        
        except Exception as e:
            print(f"\n❌ Range test error for {contact_display}: {e}\n")
            try:
                self.client.send_message(source_hash, f"❌ Range test error: {e}")
            except:
                pass
        
        finally:
            # Cleanup
            if source_hash in self.active_tests:
                del self.active_tests[source_hash]
            if source_hash in self.test_threads:
                del self.test_threads[source_hash]
    
    def send_test_summary(self, source_hash):
        """Send final summary with GPS log"""
        test_config = self.active_tests[source_hash]
        elapsed = time.time() - test_config['start_time']
        gps_log = test_config.get('gps_log', [])
        
        contact_display = self.client.format_contact_display_short(source_hash)
        
        summary = f"✅ RANGE TEST COMPLETE!\n"
        summary += f"📨 Sent: {test_config['current']}/{test_config['count']} pings\n"
        summary += f"⏱️ Duration: {int(elapsed)}s ({int(elapsed/60)}m {int(elapsed%60)}s)\n"
        summary += f"📊 Avg interval: {int(elapsed/test_config['current'])}s\n"
        
        if gps_log:
            summary += f"\n📍 GPS Responses: {len(gps_log)}/{test_config['current']}\n"
            summary += f"📶 Reception rate: {int((len(gps_log)/test_config['current'])*100)}%\n"
            
            # Calculate distance traveled (rough estimation)
            if len(gps_log) >= 2:
                try:
                    first_gps = gps_log[0]
                    last_gps = gps_log[-1]
                    distance = self.calculate_distance(
                        first_gps['lat'], first_gps['lon'],
                        last_gps['lat'], last_gps['lon']
                    )
                    summary += f"\n🛣️ Distance traveled: ~{distance:.1f}km"
                except:
                    pass
        
        self.client.send_message(source_hash, summary)
        print(f"\n✅ Range test complete for {contact_display}")
        print(f"   📍 Received {len(gps_log)}/{test_config['current']} GPS responses\n")
        
        # Save GPS log to file
        if gps_log:
            self.save_gps_log(source_hash, contact_display, gps_log)
    
    def send_gps_response(self, source_hash, current, total):
        """Send GPS position back to server (CLIENT MODE - we're driving)"""
        gps_data = self.get_gps_location()
        
        if gps_data:
            lat = gps_data.get('latitude')
            lon = gps_data.get('longitude')
            accuracy = gps_data.get('accuracy', 0)
            speed = gps_data.get('speed', 0)
            altitude = gps_data.get('altitude', 0)
            timestamp = datetime.now().strftime('%H:%M:%S')
            
            msg = f"📍 GPS RESPONSE [{current}/{total}]\n"
            msg += f"🕐 {timestamp}\n"
            msg += f"🌍 Lat: {lat:.6f}\n"
            msg += f"🌍 Lon: {lon:.6f}\n"
            
            if accuracy:
                msg += f"🎯 Accuracy: ±{accuracy:.0f}m\n"
            if speed and speed > 0:
                msg += f"🚗 Speed: {speed*3.6:.1f} km/h\n"  # Convert m/s to km/h
            if altitude:
                msg += f"⛰️ Altitude: {altitude:.0f}m\n"
            
            # Add Google Maps link
            msg += f"\n🗺️ https://maps.google.com/?q={lat},{lon}"
            
            self.client.send_message(source_hash, msg)
            print(f"[Range Test] 📍 Sent GPS {current}/{total} → {self.client.format_contact_display_short(source_hash)}")
        else:
            # Fallback if GPS not available
            msg = f"📍 GPS RESPONSE [{current}/{total}]\n"
            msg += f"🕐 {datetime.now().strftime('%H:%M:%S')}\n"
            msg += f"⚠️ GPS unavailable"
            self.client.send_message(source_hash, msg)
    
    def get_gps_location(self):
        """Get GPS location (cross-platform)"""
        system = platform.system()
        is_termux = os.path.exists('/data/data/com.termux')
        
        try:
            if is_termux:
                # === TERMUX/ANDROID ===
                result = subprocess.run(
                    ['termux-location', '-p', 'gps'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return json.loads(result.stdout)
            
            elif system == 'Linux':
                # === LINUX - Try gpsd ===
                try:
                    import gpsd  # type: ignore
                    gpsd.connect()
                    packet = gpsd.get_current()
                    return {
                        'latitude': packet.lat,
                        'longitude': packet.lon,
                        'altitude': packet.alt,
                        'speed': packet.hspeed,
                        'accuracy': packet.error['epx']  # Horizontal error
                    }
                except:
                    pass
            
            elif system == 'Darwin':
                # === MACOS - Try CoreLocation ===
                # Would need PyObjC, skip for now
                pass
        
        except Exception as e:
            print(f"[GPS] Error: {e}")
        
        return None
    
    def notify_range_ping(self, current, total):
        """Visual/audio notification for received ping (CLIENT MODE)"""
        system = platform.system()
        is_termux = os.path.exists('/data/data/com.termux')
        
        try:
            if is_termux:
                # Vibrate
                os.system(f'termux-vibrate -d 100 2>/dev/null &')
                # Notification
                os.system(f'termux-notification --title "📡 Range Ping {current}/{total}" --content "GPS sent back!" 2>/dev/null &')
            else:
                # Terminal bell
                print("\a", end="", flush=True)
        except:
            pass
    
    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two GPS coordinates (Haversine formula)"""
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371  # Earth radius in km
        
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        distance = R * c
        
        return distance
    
    def save_gps_log(self, source_hash, contact_name, gps_log):
        """Save GPS log to file for later analysis"""
        try:
            log_dir = os.path.join(self.client.storage_path, "rangetest_logs")
            os.makedirs(log_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"rangetest_{contact_name}_{timestamp}.json"
            filepath = os.path.join(log_dir, filename)
            
            log_data = {
                'contact': contact_name,
                'hash': source_hash,
                'timestamp': timestamp,
                'gps_points': gps_log
            }
            
            with open(filepath, 'w') as f:
                json.dump(log_data, f, indent=2)
            
            print(f"   💾 GPS log saved: {filename}")
            
            # Also create KML file for Google Earth
            self.create_kml_file(filepath.replace('.json', '.kml'), gps_log, contact_name)
            
        except Exception as e:
            print(f"   ⚠️ Could not save GPS log: {e}")
    
    def create_kml_file(self, filepath, gps_log, contact_name):
        """Create KML file for Google Earth visualization"""
        try:
            kml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Range Test - {contact_name}</name>
    <description>LXMF Range Test GPS Track</description>
    
    <Style id="rangeTestLine">
      <LineStyle>
        <color>ff0000ff</color>
        <width>3</width>
      </LineStyle>
    </Style>
    
    <Placemark>
      <name>Range Test Path</name>
      <styleUrl>#rangeTestLine</styleUrl>
      <LineString>
        <coordinates>
'''
            
            # Add coordinates
            for point in gps_log:
                lon = point['lon']
                lat = point['lat']
                alt = point.get('altitude', 0)
                kml_content += f"          {lon},{lat},{alt}\n"
            
            kml_content += '''        </coordinates>
      </LineString>
    </Placemark>
    
'''
            
            # Add markers for each ping
            for i, point in enumerate(gps_log, 1):
                kml_content += f'''    <Placemark>
      <name>Ping {i}</name>
      <description>Time: {point.get('time', 'N/A')}</description>
      <Point>
        <coordinates>{point['lon']},{point['lat']},{point.get('altitude', 0)}</coordinates>
      </Point>
    </Placemark>
    
'''
            
            kml_content += '''  </Document>
</kml>'''
            
            with open(filepath, 'w') as f:
                f.write(kml_content)
            
            print(f"   🌍 KML file created: {os.path.basename(filepath)}")
        
        except Exception as e:
            print(f"   ⚠️ Could not create KML: {e}")
    
    def stop_range_test_server(self, source_hash):
        """Stop an active range test (SERVER MODE)"""
        if source_hash in self.active_tests:
            test_config = self.active_tests[source_hash]
            test_config['stop_flag'].set()
            
            contact_display = self.client.format_contact_display_short(source_hash)
            print(f"\n⚠️ Stopping range test for {contact_display}\n")
            
            self.client.send_message(source_hash, "⚠️ Range test stopped by server")
        else:
            self.client.send_message(source_hash, "❌ No active range test")
    
    def handle_command(self, cmd, parts):
        """Handle local commands"""
        if cmd == 'rangetest':
            # Show active tests
            self.show_active_tests()
        
        elif cmd == 'rangestop':
            if len(parts) < 2:
                print("💡 Usage: rangestop <contact_#/name>")
            else:
                target = ' '.join(parts[1:])
                dest_hash = self.client.resolve_contact_or_hash(target)
                if dest_hash:
                    self.stop_range_test_server(dest_hash)
                else:
                    print(f"❌ Unknown contact: {target}")
        
        elif cmd == 'rangestatus':
            self.show_detailed_status()
    
    def show_active_tests(self):
        """Show active range tests"""
        if not self.active_tests:
            print("\n📡 No active range tests\n")
        else:
            print("\n" + "─"*70)
            print("📡 ACTIVE RANGE TESTS (SERVER MODE)")
            print("─"*70)
            for hash_str, config in self.active_tests.items():
                contact = self.client.format_contact_display_short(hash_str)
                elapsed = int(time.time() - config['start_time'])
                gps_count = len(config.get('gps_log', []))
                
                print(f"\n🎯 {contact}")
                print(f"   Progress: {config['current']}/{config['count']}")
                print(f"   Interval: {config['interval']}s")
                print(f"   Elapsed: {elapsed}s")
                print(f"   GPS responses: {gps_count}/{config['current']}")
            print("─"*70 + "\n")
    
    def show_detailed_status(self):
        """Show detailed status with GPS info"""
        self.show_active_tests()
        
        # Check GPS availability
        print("─"*70)
        print("📍 GPS STATUS")
        print("─"*70)
        
        gps_data = self.get_gps_location()
        if gps_data:
            print(f"✅ GPS Available")
            print(f"   Latitude: {gps_data.get('latitude', 'N/A')}")
            print(f"   Longitude: {gps_data.get('longitude', 'N/A')}")
            if gps_data.get('accuracy'):
                print(f"   Accuracy: ±{gps_data['accuracy']:.0f}m")
        else:
            print("❌ GPS Not Available")
            print("   For Android/Termux: Install 'termux-api' and 'Termux:API' app")
            print("   For Linux: Install and configure 'gpsd'")
        
        print("─"*70 + "\n")

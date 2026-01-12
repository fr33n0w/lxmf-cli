# rangetest.py
import time
import threading
import json
import subprocess
import platform
import os
import sys
from datetime import datetime
import re

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['rangetest', 'rangestop', 'rangestatus', 'rangegetlogs']
        self.description = "Range testing - incremental GPS logging"
        
        # Server mode (PC) - sends pings
        self.active_server_tests = {}
        self.server_threads = {}
        
        # Client mode (Mobile) - receives pings and logs GPS incrementally
        self.active_client_tests = {}
        
    def on_message(self, message, msg_data):
        """Handle incoming messages"""
        content = msg_data['content'].strip()
        source_hash = msg_data['source_hash']
        
        # === MOBILE SENDS COMMAND TO PC ===
        if content.lower().startswith('rangetest '):
            try:
                parts = content.split()
                if len(parts) >= 3:
                    count = int(parts[1])
                    interval = int(parts[2])
                    
                    if count < 1 or count > 1000:
                        self.client.send_message(source_hash, "❌ Count must be 1-1000")
                        return True
                    
                    if interval < 5 or interval > 300:
                        self.client.send_message(source_hash, "❌ Interval must be 5-300 seconds")
                        return True
                    
                    # Start as CLIENT (mobile - logs GPS incrementally)
                    self.start_as_client(source_hash, count, interval)
                    return True
            except ValueError:
                self.client.send_message(source_hash, "❌ Invalid numbers")
                return True
        
        # === PC CONFIRMS READY ===
        elif 'RANGE TEST READY' in content:
            try:
                count_match = re.search(r'Expecting (\d+) pings', content)
                interval_match = re.search(r'interval: (\d+)s', content)
                
                if count_match and interval_match:
                    count = int(count_match.group(1))
                    interval = int(interval_match.group(1))
                    
                    contact = self.client.format_contact_display_short(source_hash)
                    print(f"\n[Range Test] 📱 {contact} ready!")
                    print(f"[Range Test] 🚀 Starting ping sequence...\n")
                    
                    self.start_as_server(source_hash, count, interval)
            except Exception as e:
                print(f"[Range Test] Error: {e}")
            
            return True
        
        # === MOBILE RECEIVES PING ===
        if source_hash in self.active_client_tests:
            if '📡 RANGE TEST [' in content or 'RANGE TEST [' in content:
                try:
                    match = re.search(r'\[(\d+)/(\d+)\]', content)
                    if match:
                        current = int(match.group(1))
                        total = int(match.group(2))
                        
                        print(f"\n{'='*60}")
                        print(f"📡 PING #{current}/{total} RECEIVED")
                        print(f"{'='*60}")
                        
                        # Get GPS
                        timestamp = datetime.now().strftime('%H:%M:%S')
                        gps_data = self.get_gps_location()
                        
                        if gps_data:
                            lat = gps_data['latitude']
                            lon = gps_data['longitude']
                            acc = gps_data.get('accuracy', 0)
                            speed = gps_data.get('speed', 0)
                            alt = gps_data.get('altitude', 0)
                            provider = gps_data.get('provider', 'unknown')
                            
                            gps_point = {
                                'index': current,
                                'lat': lat,
                                'lon': lon,
                                'time': timestamp,
                                'speed': speed,
                                'altitude': alt,
                                'accuracy': acc,
                                'provider': provider
                            }
                            
                            # WRITE TO FILES IMMEDIATELY
                            test = self.active_client_tests[source_hash]
                            self.append_to_json(test['json_path'], gps_point)
                            self.append_to_kml(test['kml_path'], gps_point, current == 1, current == total)
                            
                            print(f"[GPS] ✅ Logged: {lat:.6f}, {lon:.6f} (±{acc:.0f}m)")
                            print(f"[GPS] 💾 Written to files")
                        else:
                            print(f"[GPS] ⚠️ GPS unavailable - ping logged without location")
                        
                        # Update count
                        self.active_client_tests[source_hash]['received'] = current
                        
                        # Notify
                        self.notify_range_ping(current, total)
                        
                        print(f"{'='*60}\n")
                        
                        # Check if complete
                        if current >= total:
                            self.complete_client_test(source_hash)
                        
                        return False  # Show ping message
                
                except Exception as e:
                    print(f"[Range Test] Error: {e}")
                    import traceback
                    traceback.print_exc()
        
        # === STOP COMMAND ===
        elif content.lower() == 'rangestop':
            if source_hash in self.active_server_tests:
                self.stop_server_test(source_hash)
            elif source_hash in self.active_client_tests:
                self.finalize_client_test(source_hash)
                self.client.send_message(source_hash, "⚠️ Range test stopped - files saved")
            else:
                self.client.send_message(source_hash, "❌ No active test")
            return True
        
        return False
    
    def start_as_client(self, server_hash, count, interval):
        """Start as CLIENT (mobile) - create files and prepare for incremental logging"""
        contact = self.client.format_contact_display_short(server_hash)
        
        # Create log directory
        log_dir = os.path.join(self.client.storage_path, "rangetest_logs")
        os.makedirs(log_dir, exist_ok=True)
        
        # Create file names
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = "".join(c for c in contact if c.isalnum() or c in (' ', '-', '_')).strip() or "server"
        
        json_file = f"rangetest_{safe_name}_{timestamp}.json"
        kml_file = f"rangetest_{safe_name}_{timestamp}.kml"
        
        json_path = os.path.join(log_dir, json_file)
        kml_path = os.path.join(log_dir, kml_file)
        
        # Initialize JSON file
        with open(json_path, 'w') as f:
            json.dump({
                'server': contact,
                'timestamp': timestamp,
                'test_start': datetime.now().isoformat(),
                'expected_pings': count,
                'interval': interval,
                'gps_points': []
            }, f, indent=2)
        
        # Initialize KML file
        self.init_kml_file(kml_path, contact)
        
        self.active_client_tests[server_hash] = {
            'count': count,
            'interval': interval,
            'received': 0,
            'start_time': time.time(),
            'json_path': json_path,
            'kml_path': kml_path,
            'server_name': contact
        }
        
        print(f"\n{'─'*70}")
        print(f"📱 RANGE TEST - CLIENT MODE (Mobile)")
        print(f"{'─'*70}")
        print(f"📡 Server: {contact}")
        print(f"📊 Expecting: {count} pings @ {interval}s interval")
        print(f"⏱️ Duration: ~{(count * interval) // 60}m {(count * interval) % 60}s")
        print(f"📍 GPS: Incremental logging")
        print(f"💾 Files created:")
        print(f"   {json_file}")
        print(f"   {kml_file}")
        print(f"{'─'*70}\n")
        
        # Send confirmation
        self.client.send_message(
            server_hash,
            f"✅ RANGE TEST READY\n\n"
            f"📱 Mobile ready\n"
            f"📊 Expecting {count} pings @ interval: {interval}s\n"
            f"📍 Incremental GPS logging active\n\n"
            f"🚀 Start sending pings!"
        )
        
        print(f"✅ Sent READY to {contact}")
        print(f"📍 Waiting for pings...\n")
    
    def init_kml_file(self, filepath, server_name):
        """Initialize KML file with header"""
        kml = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Range Test - {server_name}</name>
    <description>LXMF Range Test - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</description>
    
    <Style id="lineStyle">
      <LineStyle>
        <color>ff0000ff</color>
        <width>4</width>
      </LineStyle>
    </Style>
    
    <Style id="pingPoint">
      <IconStyle>
        <color>ff00ff00</color>
        <scale>0.8</scale>
      </IconStyle>
    </Style>
    
    <Placemark>
      <name>GPS Track</name>
      <styleUrl>#lineStyle</styleUrl>
      <LineString>
        <altitudeMode>absolute</altitudeMode>
        <coordinates>
'''
        
        with open(filepath, 'w') as f:
            f.write(kml)
    
    def append_to_json(self, json_path, gps_point):
        """Append GPS point to JSON file"""
        try:
            # Read current data
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            # Append new point
            data['gps_points'].append(gps_point)
            
            # Write back
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=2)
        
        except Exception as e:
            print(f"[JSON] ⚠️ Error: {e}")
    
    def append_to_kml(self, kml_path, gps_point, is_first, is_last):
        """Append GPS point to KML file"""
        try:
            # Append coordinate to LineString
            with open(kml_path, 'a') as f:
                lon = gps_point['lon']
                lat = gps_point['lat']
                alt = gps_point.get('altitude', 0)
                f.write(f"          {lon},{lat},{alt}\n")
            
            # If last point, close the file properly
            if is_last:
                self.finalize_kml(kml_path, gps_point)
        
        except Exception as e:
            print(f"[KML] ⚠️ Error: {e}")
    
    def finalize_kml(self, kml_path, last_point=None):
        """Close KML file properly"""
        try:
            with open(kml_path, 'a') as f:
                f.write('''        </coordinates>
      </LineString>
    </Placemark>
''')
                
                # Add end marker if we have the last point
                if last_point:
                    f.write(f'''    
    <Placemark>
      <name>END</name>
      <description>Last ping - {last_point.get('time', 'N/A')}</description>
      <styleUrl>#pingPoint</styleUrl>
      <Point>
        <coordinates>{last_point['lon']},{last_point['lat']},{last_point.get('altitude', 0)}</coordinates>
      </Point>
    </Placemark>
''')
                
                f.write('''  </Document>
</kml>''')
        
        except Exception as e:
            print(f"[KML] ⚠️ Finalize error: {e}")
    
    def complete_client_test(self, server_hash):
        """Complete test - finalize files"""
        test = self.active_client_tests[server_hash]
        
        # Finalize KML if not already done
        # (last point already finalized it, but this is a safety check)
        
        elapsed = time.time() - test['start_time']
        
        print(f"\n{'─'*70}")
        print(f"🎉 RANGE TEST COMPLETE!")
        print(f"{'─'*70}")
        print(f"📡 Server: {test['server_name']}")
        print(f"📊 Pings received: {test['received']}/{test['count']}")
        print(f"⏱️ Duration: {int(elapsed/60)}m {int(elapsed%60)}s")
        print(f"💾 Files saved:")
        print(f"   {os.path.basename(test['json_path'])}")
        print(f"   {os.path.basename(test['kml_path'])}")
        print(f"{'─'*70}")
        print(f"\n💡 Copy to shared storage:")
        print(f"   cp {test['kml_path']} /sdcard/Download/")
        print(f"\n💡 Open in Google Earth on your phone!\n")
        
        # Cleanup
        del self.active_client_tests[server_hash]
        
        # Notify server
        self.client.send_message(server_hash, 
            f"✅ Test complete!\n"
            f"📊 Received: {test['received']}/{test['count']}\n"
            f"💾 Files saved on mobile")
    
    def finalize_client_test(self, server_hash):
        """Finalize test early (e.g., manual stop)"""
        if server_hash not in self.active_client_tests:
            return
        
        test = self.active_client_tests[server_hash]
        
        # Close KML file
        self.finalize_kml(test['kml_path'])
        
        print(f"\n⚠️ Test stopped early")
        print(f"📊 Received: {test['received']}/{test['count']} pings")
        print(f"💾 Files saved:\n   {os.path.basename(test['json_path'])}\n   {os.path.basename(test['kml_path'])}\n")
        
        del self.active_client_tests[server_hash]
    
    def start_as_server(self, client_hash, count, interval):
        """Start as SERVER (PC) - just send pings"""
        
        if client_hash in self.active_server_tests:
            self.stop_server_test(client_hash)
        
        self.active_server_tests[client_hash] = {
            'count': count,
            'interval': interval,
            'current': 0,
            'start_time': time.time(),
            'stop_flag': threading.Event()
        }
        
        contact = self.client.format_contact_display_short(client_hash)
        
        print(f"\n{'─'*70}")
        print(f"🏠 RANGE TEST - SERVER MODE (Fixed)")
        print(f"{'─'*70}")
        print(f"📱 Mobile: {contact}")
        print(f"📊 Pings: {count} @ {interval}s interval")
        print(f"⏱️ Duration: ~{(count * interval) // 60}m {(count * interval) % 60}s")
        print(f"{'─'*70}\n")
        
        # Start thread
        thread = threading.Thread(
            target=self._server_worker,
            args=(client_hash,),
            daemon=True
        )
        self.server_threads[client_hash] = thread
        thread.start()
    
    def _server_worker(self, client_hash):
        """Server worker - sends pings"""
        test = self.active_server_tests[client_hash]
        contact = self.client.format_contact_display_short(client_hash)
        
        try:
            while test['current'] < test['count']:
                if test['stop_flag'].is_set():
                    break
                
                test['current'] += 1
                current = test['current']
                total = test['count']
                
                elapsed = time.time() - test['start_time']
                remaining = (test['interval'] * total) - elapsed
                timestamp = datetime.now().strftime('%H:%M:%S')
                
                msg = f"📡 RANGE TEST [{current}/{total}]\n"
                msg += f"🕐 {timestamp}\n"
                msg += f"⏱️ Elapsed: {int(elapsed)}s\n"
                msg += f"⏳ Remaining: ~{int(remaining)}s\n"
                msg += f"📊 Progress: {int((current/total)*100)}%"
                
                print(f"[Range Test] 📡 Ping {current}/{total} → {contact}")
                self.client.send_message(client_hash, msg)
                
                # Wait
                for _ in range(test['interval']):
                    if test['stop_flag'].wait(1):
                        break
            
            # Complete
            if not test['stop_flag'].is_set():
                print(f"\n[Range Test] ✅ Ping sequence complete\n")
                self.client.send_message(client_hash, 
                    f"✅ PING SEQUENCE COMPLETE\n"
                    f"📊 Sent {test['current']}/{test['count']} pings\n"
                    f"📍 Check your mobile for GPS logs!")
        
        except Exception as e:
            print(f"\n❌ Server error: {e}\n")
        
        finally:
            if client_hash in self.active_server_tests:
                del self.active_server_tests[client_hash]
            if client_hash in self.server_threads:
                del self.server_threads[client_hash]
    
    def stop_server_test(self, client_hash):
        """Stop server"""
        if client_hash in self.active_server_tests:
            self.active_server_tests[client_hash]['stop_flag'].set()
            contact = self.client.format_contact_display_short(client_hash)
            print(f"\n⚠️ Stopping test with {contact}\n")
            self.client.send_message(client_hash, "⚠️ Test stopped by server")
    
    def get_gps_location(self):
        """Get GPS location"""
        is_termux = os.path.exists('/data/data/com.termux')
        
        if not is_termux:
            return None
        
        try:
            providers = [
                ('network', 5, 'Network'),
                ('gps', 8, 'GPS'),
                ('passive', 2, 'Cached')
            ]
            
            for provider, timeout, desc in providers:
                try:
                    result = subprocess.run(
                        ['termux-location', '-p', provider],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        env=os.environ.copy()
                    )
                    
                    if result.returncode == 0 and result.stdout:
                        data = json.loads(result.stdout.strip())
                        
                        if 'latitude' in data and 'longitude' in data:
                            lat = data.get('latitude')
                            lon = data.get('longitude')
                            
                            if lat and lon and (abs(lat) > 0.001 or abs(lon) > 0.001):
                                data['provider'] = provider
                                return data
                
                except (subprocess.TimeoutExpired, json.JSONDecodeError):
                    continue
                except Exception:
                    continue
            
            return None
        
        except Exception:
            return None
    
    def notify_range_ping(self, current, total):
        """Notify"""
        is_termux = os.path.exists('/data/data/com.termux')
        
        try:
            if is_termux:
                os.system('termux-vibrate -d 100 2>/dev/null &')
                os.system(f'termux-notification --title "📡 Ping {current}/{total}" --content "GPS saved!" 2>/dev/null &')
        except:
            pass
    
    def handle_command(self, cmd, parts):
        """Handle commands"""
        if cmd == 'rangetest':
            if self.active_server_tests:
                print("\n📡 SERVER MODE - Sending pings")
                for h, c in self.active_server_tests.items():
                    print(f"  {self.client.format_contact_display_short(h)}: {c['current']}/{c['count']}")
            elif self.active_client_tests:
                print("\n📡 CLIENT MODE - Logging GPS")
                for h, c in self.active_client_tests.items():
                    print(f"  {self.client.format_contact_display_short(h)}: {c['received']}/{c['count']}")
                    print(f"     Files: {os.path.basename(c['json_path'])}")
            else:
                print("\n📡 No active tests\n")
        
        elif cmd == 'rangestatus':
            print("\n📍 GPS STATUS")
            print("─"*70)
            gps = self.get_gps_location()
            if gps:
                print(f"✅ GPS Available")
                print(f"   Lat: {gps['latitude']:.6f}")
                print(f"   Lon: {gps['longitude']:.6f}")
                print(f"   Accuracy: ±{gps.get('accuracy', 0):.0f}m")
                print(f"   Provider: {gps.get('provider', 'unknown')}")
            else:
                print("❌ GPS Unavailable")
            print("─"*70 + "\n")
        
        elif cmd == 'rangegetlogs':
            # Show local logs
            log_dir = os.path.join(self.client.storage_path, "rangetest_logs")
            if os.path.exists(log_dir):
                files = [f for f in os.listdir(log_dir) if f.endswith(('.kml', '.json'))]
                if files:
                    print("\n📁 Range Test Logs:")
                    print("─"*70)
                    for f in sorted(files, reverse=True):
                        path = os.path.join(log_dir, f)
                        size = os.path.getsize(path)
                        print(f"  {f} ({size} bytes)")
                    print("─"*70)
                    print(f"\nPath: {log_dir}")
                    print(f"\n💡 Copy to phone storage:")
                    print(f"   cp {log_dir}/*.kml /sdcard/Download/")
                    print(f"\n💡 View latest:")
                    if files:
                        latest_kml = sorted([f for f in files if f.endswith('.kml')], reverse=True)[0]
                        print(f"   termux-open {log_dir}/{latest_kml}\n")
                else:
                    print("\n📁 No logs found\n")
            else:
                print("\n📁 No logs directory\n")
        
        elif cmd == 'rangestop':
            if len(parts) < 2:
                print("💡 Usage: rangestop <contact>")
            else:
                target = ' '.join(parts[1:])
                dest_hash = self.client.resolve_contact_or_hash(target)
                if dest_hash:
                    if dest_hash in self.active_server_tests:
                        self.stop_server_test(dest_hash)
                    elif dest_hash in self.active_client_tests:
                        self.finalize_client_test(dest_hash)
                        print("⚠️ Client test stopped - files saved")
                    else:
                        print("❌ No active test")
                else:
                    print(f"❌ Unknown: {target}")

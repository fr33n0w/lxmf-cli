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
        
        # PHONE MODE - receives pings, logs GPS
        self.active_tests = {}  # Tests where WE receive pings
        
        # PC MODE - sends pings
        self.server_tests = {}
        self.server_threads = {}
        
    def on_message(self, message, msg_data):
        """Handle incoming messages"""
        content = msg_data['content'].strip()
        source_hash = msg_data['source_hash']
        
        # === PC RECEIVES COMMAND FROM PHONE ===
        # Phone: "send PC rangetest 50 15"
        # PC receives this
        
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
                    
                    # PC BECOMES SERVER - sends pings
                    self.start_server(source_hash, count, interval)
                    return True
            except ValueError:
                self.client.send_message(source_hash, "❌ Invalid numbers")
                return True
        
        # === PHONE RECEIVES CONFIRMATION FROM PC ===
        # PC: "I'm starting to send pings"
        # Phone receives this
        
        elif 'STARTING PING SEQUENCE' in content:
            try:
                count_match = re.search(r'Sending (\d+) pings', content)
                interval_match = re.search(r'@ (\d+)s', content)
                
                if count_match and interval_match:
                    count = int(count_match.group(1))
                    interval = int(interval_match.group(1))
                    
                    contact = self.client.format_contact_display_short(source_hash)
                    print(f"\n[Range Test] 🏠 {contact} starting ping sequence!\n")
                    
                    # PHONE PREPARES TO RECEIVE AND LOG
                    self.start_client(source_hash, count, interval, contact)
            except Exception as e:
                print(f"[Range Test] Error: {e}")
            
            return True
        
        # === PHONE RECEIVES PING FROM PC ===
        # PC sends ping, phone receives it
        
        if source_hash in self.active_tests:
            if '📡 RANGE TEST [' in content or 'RANGE TEST [' in content:
                try:
                    match = re.search(r'\[(\d+)/(\d+)\]', content)
                    if match:
                        current = int(match.group(1))
                        total = int(match.group(2))
                        
                        print(f"\n{'='*60}")
                        print(f"📡 PING #{current}/{total} RECEIVED")
                        print(f"{'='*60}")
                        
                        # Get GPS and save immediately
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
                            test = self.active_tests[source_hash]
                            self.append_to_json(test['json_path'], gps_point)
                            self.append_to_kml(test['kml_path'], gps_point, current == 1, current == total)
                            
                            print(f"[GPS] ✅ Logged: {lat:.6f}, {lon:.6f} (±{acc:.0f}m)")
                            print(f"[GPS] 💾 Written to files")
                        else:
                            print(f"[GPS] ⚠️ GPS unavailable")
                        
                        # Update count
                        self.active_tests[source_hash]['received'] = current
                        
                        # Notify
                        self.notify_ping(current, total)
                        
                        print(f"{'='*60}\n")
                        
                        # Check if complete
                        if current >= total:
                            self.complete_test(source_hash)
                        
                        return False
                
                except Exception as e:
                    print(f"[Range Test] Error: {e}")
                    import traceback
                    traceback.print_exc()
        
        # === STOP COMMAND ===
        elif content.lower() == 'rangestop':
            if source_hash in self.server_tests:
                self.stop_server(source_hash)
            elif source_hash in self.active_tests:
                self.finalize_test(source_hash)
                self.client.send_message(source_hash, "⚠️ Test stopped - files saved")
            else:
                self.client.send_message(source_hash, "❌ No active test")
            return True
        
        return False
    
    def start_server(self, phone_hash, count, interval):
        """PC MODE - Start sending pings"""
        
        if phone_hash in self.server_tests:
            self.stop_server(phone_hash)
        
        self.server_tests[phone_hash] = {
            'count': count,
            'interval': interval,
            'current': 0,
            'start_time': time.time(),
            'stop_flag': threading.Event()
        }
        
        contact = self.client.format_contact_display_short(phone_hash)
        
        print(f"\n{'─'*70}")
        print(f"🏠 PC MODE - Sending Pings (Fixed Station)")
        print(f"{'─'*70}")
        print(f"📱 Mobile: {contact}")
        print(f"📊 Pings: {count} @ {interval}s interval")
        print(f"⏱️ Duration: ~{(count * interval) // 60}m {(count * interval) % 60}s")
        print(f"{'─'*70}\n")
        
        # Notify phone
        self.client.send_message(
            phone_hash,
            f"✅ STARTING PING SEQUENCE\n\n"
            f"📡 Sending {count} pings @ {interval}s\n"
            f"⏱️ Duration: ~{(count * interval) // 60}m {(count * interval) % 60}s\n\n"
            f"📍 Prepare to log GPS!"
        )
        
        # Start thread
        thread = threading.Thread(
            target=self._server_worker,
            args=(phone_hash,),
            daemon=True
        )
        self.server_threads[phone_hash] = thread
        thread.start()
    
    def _server_worker(self, phone_hash):
        """PC worker - sends pings"""
        test = self.server_tests[phone_hash]
        contact = self.client.format_contact_display_short(phone_hash)
        
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
                self.client.send_message(phone_hash, msg)
                
                # Wait
                for _ in range(test['interval']):
                    if test['stop_flag'].wait(1):
                        break
            
            # Complete
            if not test['stop_flag'].is_set():
                print(f"\n[Range Test] ✅ Ping sequence complete\n")
                self.client.send_message(phone_hash, 
                    f"✅ PING SEQUENCE COMPLETE\n"
                    f"📊 Sent {test['current']}/{test['count']} pings")
        
        except Exception as e:
            print(f"\n❌ Server error: {e}\n")
        
        finally:
            if phone_hash in self.server_tests:
                del self.server_tests[phone_hash]
            if phone_hash in self.server_threads:
                del self.server_threads[phone_hash]
    
    def start_client(self, server_hash, count, interval, server_name):
        """PHONE MODE - Prepare to receive pings and log GPS"""
        
        # Create log directory
        log_dir = os.path.join(self.client.storage_path, "rangetest_logs")
        os.makedirs(log_dir, exist_ok=True)
        
        # Create file names
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = "".join(c for c in server_name if c.isalnum() or c in (' ', '-', '_')).strip() or "server"
        
        json_file = f"rangetest_{safe_name}_{timestamp}.json"
        kml_file = f"rangetest_{safe_name}_{timestamp}.kml"
        
        json_path = os.path.join(log_dir, json_file)
        kml_path = os.path.join(log_dir, kml_file)
        
        # Initialize JSON
        with open(json_path, 'w') as f:
            json.dump({
                'server': server_name,
                'timestamp': timestamp,
                'test_start': datetime.now().isoformat(),
                'expected_pings': count,
                'interval': interval,
                'gps_points': []
            }, f, indent=2)
        
        # Initialize KML
        self.init_kml_file(kml_path, server_name)
        
        self.active_tests[server_hash] = {
            'count': count,
            'interval': interval,
            'received': 0,
            'start_time': time.time(),
            'json_path': json_path,
            'kml_path': kml_path,
            'server_name': server_name
        }
        
        print(f"\n{'─'*70}")
        print(f"📱 PHONE MODE - Receiving Pings (Mobile)")
        print(f"{'─'*70}")
        print(f"📡 Server: {server_name}")
        print(f"📊 Expecting: {count} pings @ {interval}s")
        print(f"📍 GPS: Incremental logging")
        print(f"💾 Files:")
        print(f"   {json_file}")
        print(f"   {kml_file}")
        print(f"{'─'*70}\n")
    
    def init_kml_file(self, filepath, server_name):
        """Initialize KML"""
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
        """Append GPS to JSON"""
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            data['gps_points'].append(gps_point)
            
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=2)
        
        except Exception as e:
            print(f"[JSON] ⚠️ Error: {e}")
    
    def append_to_kml(self, kml_path, gps_point, is_first, is_last):
        """Append GPS to KML"""
        try:
            with open(kml_path, 'a') as f:
                f.write(f"          {gps_point['lon']},{gps_point['lat']},{gps_point.get('altitude', 0)}\n")
            
            if is_last:
                self.finalize_kml(kml_path, gps_point)
        
        except Exception as e:
            print(f"[KML] ⚠️ Error: {e}")
    
    def finalize_kml(self, kml_path, last_point=None):
        """Close KML"""
        try:
            with open(kml_path, 'a') as f:
                f.write('''        </coordinates>
      </LineString>
    </Placemark>
''')
                
                if last_point:
                    f.write(f'''    
    <Placemark>
      <name>END</name>
      <description>Last ping - {last_point.get('time', 'N/A')}</description>
      <Point>
        <coordinates>{last_point['lon']},{last_point['lat']},{last_point.get('altitude', 0)}</coordinates>
      </Point>
    </Placemark>
''')
                
                f.write('''  </Document>
</kml>''')
        
        except Exception as e:
            print(f"[KML] Error: {e}")
    
    def complete_test(self, server_hash):
        """PHONE - Test complete"""
        test = self.active_tests[server_hash]
        elapsed = time.time() - test['start_time']
        
        print(f"\n{'─'*70}")
        print(f"🎉 RANGE TEST COMPLETE!")
        print(f"{'─'*70}")
        print(f"📡 Server: {test['server_name']}")
        print(f"📊 Received: {test['received']}/{test['count']}")
        print(f"⏱️ Duration: {int(elapsed/60)}m {int(elapsed%60)}s")
        print(f"💾 Files:")
        print(f"   {os.path.basename(test['json_path'])}")
        print(f"   {os.path.basename(test['kml_path'])}")
        print(f"{'─'*70}")
        print(f"\n💡 Copy to shared storage:")
        print(f"   cp {test['kml_path']} /sdcard/Download/")
        print(f"\n💡 Open in Google Earth!\n")
        
        del self.active_tests[server_hash]
    
    def finalize_test(self, server_hash):
        """PHONE - Stop early"""
        if server_hash not in self.active_tests:
            return
        
        test = self.active_tests[server_hash]
        self.finalize_kml(test['kml_path'])
        
        print(f"\n⚠️ Test stopped")
        print(f"📊 Received: {test['received']}/{test['count']}")
        print(f"💾 Files saved\n")
        
        del self.active_tests[server_hash]
    
    def stop_server(self, phone_hash):
        """PC - Stop sending"""
        if phone_hash in self.server_tests:
            self.server_tests[phone_hash]['stop_flag'].set()
            print(f"\n⚠️ Stopping ping sequence\n")
            self.client.send_message(phone_hash, "⚠️ Test stopped")
    
    def get_gps_location(self):
        """Get GPS"""
        is_termux = os.path.exists('/data/data/com.termux')
        
        if not is_termux:
            return None
        
        try:
            providers = [('network', 5), ('gps', 8), ('passive', 2)]
            
            for provider, timeout in providers:
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
                
                except:
                    continue
            
            return None
        except:
            return None
    
    def notify_ping(self, current, total):
        """Notify"""
        is_termux = os.path.exists('/data/data/com.termux')
        
        try:
            if is_termux:
                os.system('termux-vibrate -d 100 2>/dev/null &')
                os.system(f'termux-notification --title "📡 Ping {current}/{total}" --content "GPS saved!" 2>/dev/null &')
        except:
            pass
    
    def handle_command(self, cmd, parts):
        """Commands"""
        if cmd == 'rangetest':
            if self.server_tests:
                print("\n🏠 PC MODE - Sending pings")
                for h, c in self.server_tests.items():
                    print(f"  {self.client.format_contact_display_short(h)}: {c['current']}/{c['count']}")
            elif self.active_tests:
                print("\n📱 PHONE MODE - Logging GPS")
                for h, c in self.active_tests.items():
                    print(f"  {self.client.format_contact_display_short(h)}: {c['received']}/{c['count']}")
                    print(f"     {os.path.basename(c['json_path'])}")
            else:
                print("\n📡 No active tests\n")
        
        elif cmd == 'rangestatus':
            print("\n📍 GPS STATUS")
            print("─"*70)
            gps = self.get_gps_location()
            if gps:
                print(f"✅ Available: {gps['latitude']:.6f}, {gps['longitude']:.6f} (±{gps.get('accuracy', 0):.0f}m)")
            else:
                print("❌ Unavailable")
            print("─"*70 + "\n")
        
        elif cmd == 'rangegetlogs':
            log_dir = os.path.join(self.client.storage_path, "rangetest_logs")
            if os.path.exists(log_dir):
                files = [f for f in os.listdir(log_dir) if f.endswith(('.kml', '.json'))]
                if files:
                    print("\n📁 Logs:")
                    print("─"*70)
                    for f in sorted(files, reverse=True):
                        print(f"  {f} ({os.path.getsize(os.path.join(log_dir, f))} bytes)")
                    print("─"*70)
                    print(f"\n💡 Copy: cp {log_dir}/*.kml /sdcard/Download/\n")
                else:
                    print("\n📁 No logs\n")
            else:
                print("\n📁 No logs\n")
        
        elif cmd == 'rangestop':
            if len(parts) < 2:
                print("💡 Usage: rangestop <contact>")
            else:
                target = ' '.join(parts[1:])
                dest_hash = self.client.resolve_contact_or_hash(target)
                if dest_hash:
                    if dest_hash in self.server_tests:
                        self.stop_server(dest_hash)
                    elif dest_hash in self.active_tests:
                        self.finalize_test(dest_hash)
                    else:
                        print("❌ No active test")
                else:
                    print(f"❌ Unknown: {target}")

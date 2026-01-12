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
import base64

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['rangetest', 'rangestop', 'rangestatus', 'rangegetfile']
        self.description = "Range testing - automated bidirectional testing with GPS"
        
        # When WE are the SERVER (PC) - sending pings
        self.active_server_tests = {}
        self.server_threads = {}
        
        # When WE are the CLIENT (Mobile) - receiving pings and sending GPS
        self.active_client_tests = {}
        
        # Store completed test data
        self.last_completed_tests = {}
        
    def on_message(self, message, msg_data):
        """Handle incoming range test commands and responses"""
        content = msg_data['content'].strip()
        source_hash = msg_data['source_hash']
        
        # === PC SENDS "rangetest N T" TO PHONE ===
        # Phone receives this and confirms "I'm ready to receive pings"
        
        if content.lower().startswith('rangetest '):
            try:
                parts = content.split()
                if len(parts) >= 3:
                    count = int(parts[1])
                    interval = int(parts[2])
                    
                    # Validate
                    if count < 1 or count > 1000:
                        self.client.send_message(source_hash, "❌ Count must be 1-1000")
                        return True
                    
                    if interval < 5 or interval > 300:
                        self.client.send_message(source_hash, "❌ Interval must be 5-300 seconds")
                        return True
                    
                    # WE (mobile) become the CLIENT - ready to receive pings
                    self.start_as_client(source_hash, count, interval)
                    return True
            except ValueError:
                self.client.send_message(source_hash, "❌ Invalid numbers")
                return True
        
        # === PHONE CONFIRMS "READY" ===
        # PC receives this and starts sending pings
        
        elif 'RANGE TEST READY' in content:
            # Phone confirmed ready - start sending pings
            try:
                # Extract config from confirmation message
                count_match = re.search(r'Expecting (\d+) pings', content)
                if count_match and source_hash not in self.active_server_tests:
                    count = int(count_match.group(1))
                    # We stored the interval when we sent the command
                    # For now, use default 10s (you can improve this)
                    interval = 10
                    
                    contact = self.client.format_contact_display_short(source_hash)
                    print(f"\n[Range Test] 📱 {contact} is ready!")
                    print(f"[Range Test] 🚀 Starting to send pings...\n")
                    
                    self.start_as_server(source_hash, count, interval)
            except Exception as e:
                print(f"[Range Test] Error starting server: {e}")
            
            return True
        
        # === PHONE IS CLIENT - Receives pings from PC ===
        # Auto-reply with GPS
        
        if source_hash in self.active_client_tests:
            if '📡 RANGE TEST [' in content or 'RANGE TEST [' in content:
                try:
                    match = re.search(r'\[(\d+)/(\d+)\]', content)
                    if match:
                        current = int(match.group(1))
                        total = int(match.group(2))
                        
                        print(f"\n{'='*60}")
                        print(f"📡 PING RECEIVED [{current}/{total}]")
                        print(f"{'='*60}")
                        
                        # Update count
                        self.active_client_tests[source_hash]['received'] = current
                        
                        # Get GPS and reply
                        timestamp = datetime.now().strftime('%H:%M:%S')
                        
                        print(f"[GPS] Getting location...")
                        gps_data = self.get_gps_location()
                        
                        if gps_data:
                            lat = gps_data['latitude']
                            lon = gps_data['longitude']
                            acc = gps_data.get('accuracy', 0)
                            speed = gps_data.get('speed', 0)
                            alt = gps_data.get('altitude', 0)
                            provider = gps_data.get('provider', 'unknown')
                            
                            msg = f"📍 GPS RESPONSE [{current}/{total}]\n"
                            msg += f"🕐 {timestamp}\n"
                            msg += f"🌍 Lat: {lat:.6f}\n"
                            msg += f"🌍 Lon: {lon:.6f}\n"
                            if acc:
                                msg += f"🎯 Accuracy: ±{acc:.0f}m\n"
                            if speed > 0:
                                msg += f"🚗 Speed: {speed*3.6:.1f} km/h\n"
                            if alt:
                                msg += f"⛰️ Altitude: {alt:.0f}m\n"
                            msg += f"\n🗺️ https://maps.google.com/?q={lat},{lon}"
                            
                            print(f"[GPS] ✅ Got location via {provider}")
                            print(f"      {lat:.6f}, {lon:.6f} (±{acc:.0f}m)")
                            print(f"[GPS] 📤 Sending response...")
                        else:
                            msg = f"📍 GPS RESPONSE [{current}/{total}]\n"
                            msg += f"🕐 {timestamp}\n"
                            msg += f"⚠️ GPS unavailable"
                            print(f"[GPS] ⚠️ GPS unavailable")
                        
                        self.client.send_message(source_hash, msg)
                        self.notify_range_ping(current, total)
                        
                        print(f"✅ Response sent")
                        print(f"{'='*60}\n")
                        
                        # Check if test complete
                        if current >= total:
                            print(f"\n🎉 Range test complete! Received all {total} pings\n")
                            del self.active_client_tests[source_hash]
                        
                        return False  # Let message display normally
                
                except Exception as e:
                    print(f"[Range Test] Error handling ping: {e}")
                    import traceback
                    traceback.print_exc()
        
        # === PC IS SERVER - Receives GPS responses from phone ===
        
        elif content.startswith('📍 GPS RESPONSE ['):
            try:
                match = re.search(r'\[(\d+)/(\d+)\]', content)
                if match:
                    current = int(match.group(1))
                    
                    # Extract GPS
                    lat_match = re.search(r'Lat: ([-\d.]+)', content)
                    lon_match = re.search(r'Lon: ([-\d.]+)', content)
                    
                    if lat_match and lon_match and source_hash in self.active_server_tests:
                        lat = float(lat_match.group(1))
                        lon = float(lon_match.group(1))
                        
                        # Extract fields
                        speed_match = re.search(r'Speed: ([\d.]+)', content)
                        alt_match = re.search(r'Altitude: ([\d.]+)', content)
                        acc_match = re.search(r'Accuracy: ±([\d.]+)', content)
                        time_match = re.search(r'🕐 (\d{2}:\d{2}:\d{2})', content)
                        
                        gps_point = {
                            'index': current,
                            'lat': lat,
                            'lon': lon,
                            'time': time_match.group(1) if time_match else 'N/A',
                            'speed': float(speed_match.group(1)) if speed_match else 0,
                            'altitude': float(alt_match.group(1)) if alt_match else 0,
                            'accuracy': float(acc_match.group(1)) if acc_match else 0,
                        }
                        
                        # Store
                        self.active_server_tests[source_hash]['gps_log'].append(gps_point)
                        
                        contact = self.client.format_contact_display_short(source_hash)
                        print(f"[Range Test] 📍 GPS #{current} from {contact} (±{gps_point['accuracy']:.0f}m)")
                        
                        return True  # Don't show full GPS message
            except Exception as e:
                print(f"[Range Test] Error parsing GPS: {e}")
        
        # === File transfer ===
        
        elif content.lower().startswith('rangegetfile'):
            self.handle_file_request(source_hash, content)
            return True
        
        elif content.startswith('📦 FILE:'):
            self.handle_file_receive(source_hash, content)
            return True
        
        elif content.lower() == 'rangestop':
            # Stop either mode
            if source_hash in self.active_server_tests:
                self.stop_server_test(source_hash)
            elif source_hash in self.active_client_tests:
                del self.active_client_tests[source_hash]
                self.client.send_message(source_hash, "⚠️ Range test stopped")
            else:
                self.client.send_message(source_hash, "❌ No active test")
            return True
        
        return False
    
    def start_as_client(self, server_hash, count, interval):
        """Start as CLIENT (mobile) - receive pings and send GPS"""
        contact = self.client.format_contact_display_short(server_hash)
        
        self.active_client_tests[server_hash] = {
            'count': count,
            'interval': interval,
            'received': 0,
            'start_time': time.time()
        }
        
        print(f"\n{'─'*70}")
        print(f"🎯 RANGE TEST - CLIENT MODE (Mobile)")
        print(f"{'─'*70}")
        print(f"📡 Server: {contact}")
        print(f"📊 Expecting: {count} pings @ {interval}s interval")
        print(f"⏱️ Duration: ~{(count * interval) // 60}m {(count * interval) % 60}s")
        print(f"📍 GPS auto-reply: ENABLED")
        print(f"{'─'*70}\n")
        
        # Confirm ready to server
        self.client.send_message(
            server_hash,
            f"✅ RANGE TEST READY\n\n"
            f"📱 Mobile node ready\n"
            f"📊 Expecting {count} pings\n"
            f"📍 GPS auto-reply enabled\n\n"
            f"🚀 You can start sending pings!"
        )
        
        print(f"✅ Sent 'READY' confirmation to {contact}")
        print(f"📍 Waiting for pings...\n")
    
    def start_as_server(self, client_hash, count, interval):
        """Start as SERVER (PC) - send pings to mobile"""
        
        # Stop existing test
        if client_hash in self.active_server_tests:
            self.stop_server_test(client_hash)
        
        self.active_server_tests[client_hash] = {
            'count': count,
            'interval': interval,
            'current': 0,
            'start_time': time.time(),
            'stop_flag': threading.Event(),
            'gps_log': []
        }
        
        contact = self.client.format_contact_display_short(client_hash)
        
        print(f"\n{'─'*70}")
        print(f"🎯 RANGE TEST - SERVER MODE (Fixed)")
        print(f"{'─'*70}")
        print(f"📱 Mobile client: {contact}")
        print(f"📊 Sending: {count} pings @ {interval}s interval")
        print(f"⏱️ Duration: ~{(count * interval) // 60}m {(count * interval) % 60}s")
        print(f"📍 GPS tracking: ENABLED")
        print(f"{'─'*70}\n")
        
        # Start ping thread
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
                msg += f"🕐 Time: {timestamp}\n"
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
                self.send_test_summary(client_hash)
        
        except Exception as e:
            print(f"\n❌ Server error: {e}\n")
        
        finally:
            if client_hash in self.active_server_tests:
                del self.active_server_tests[client_hash]
            if client_hash in self.server_threads:
                del self.server_threads[client_hash]
    
    def send_test_summary(self, client_hash):
        """Send summary to client"""
        test = self.active_server_tests[client_hash]
        elapsed = time.time() - test['start_time']
        gps_log = test['gps_log']
        
        contact = self.client.format_contact_display_short(client_hash)
        
        summary = f"✅ RANGE TEST COMPLETE!\n\n"
        summary += f"📨 Sent: {test['current']}/{test['count']} pings\n"
        summary += f"⏱️ Duration: {int(elapsed/60)}m {int(elapsed%60)}s\n"
        
        reception_rate = 0
        if gps_log:
            summary += f"\n📍 GPS Responses: {len(gps_log)}/{test['current']}\n"
            reception_rate = int((len(gps_log)/test['current'])*100)
            summary += f"📶 Reception rate: {reception_rate}%\n"
            
            if len(gps_log) >= 2:
                try:
                    distance = self.calculate_total_distance(gps_log)
                    summary += f"\n🛣️ Distance: ~{distance:.1f} km\n"
                    
                    max_speed = max([p.get('speed', 0) for p in gps_log])
                    if max_speed > 0:
                        summary += f"🚗 Max speed: {max_speed:.1f} km/h\n"
                except:
                    pass
            
            summary += f"\n📥 Get files:\n"
            summary += f"  rangegetfile kml\n"
            summary += f"  rangegetfile json\n"
            summary += f"  rangegetfile both"
        else:
            summary += f"\n⚠️ No GPS responses received"
        
        self.client.send_message(client_hash, summary)
        
        print(f"\n{'─'*70}")
        print(f"✅ RANGE TEST COMPLETE: {contact}")
        print(f"{'─'*70}")
        print(f"📨 Pings sent: {test['current']}/{test['count']}")
        print(f"📍 GPS received: {len(gps_log)}/{test['current']}")
        if gps_log:
            print(f"📶 Reception: {reception_rate}%")
        print(f"{'─'*70}\n")
        
        # Save logs
        if gps_log:
            json_path, kml_path = self.save_gps_log(client_hash, contact, gps_log)
            self.last_completed_tests[client_hash] = {
                'json_path': json_path,
                'kml_path': kml_path,
                'timestamp': time.time()
            }
    
    def stop_server_test(self, client_hash):
        """Stop server test"""
        if client_hash in self.active_server_tests:
            self.active_server_tests[client_hash]['stop_flag'].set()
            contact = self.client.format_contact_display_short(client_hash)
            print(f"\n⚠️ Stopping test with {contact}\n")
            self.client.send_message(client_hash, "⚠️ Range test stopped by server")
    
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
                
                except subprocess.TimeoutExpired:
                    continue
                except Exception:
                    continue
            
            return None
        
        except Exception as e:
            print(f"[GPS] Error: {e}")
            return None
    
    def notify_range_ping(self, current, total):
        """Notify user"""
        is_termux = os.path.exists('/data/data/com.termux')
        
        try:
            if is_termux:
                os.system('termux-vibrate -d 100 2>/dev/null &')
                os.system(f'termux-notification --title "📡 Ping {current}/{total}" --content "GPS sent!" 2>/dev/null &')
        except:
            pass
    
    def calculate_total_distance(self, gps_log):
        """Calculate distance"""
        from math import radians, sin, cos, sqrt, atan2
        
        total = 0
        for i in range(len(gps_log) - 1):
            lat1, lon1 = gps_log[i]['lat'], gps_log[i]['lon']
            lat2, lon2 = gps_log[i+1]['lat'], gps_log[i+1]['lon']
            
            R = 6371
            lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            total += R * c
        
        return total
    
    def save_gps_log(self, source_hash, contact_name, gps_log):
        """Save GPS log"""
        try:
            log_dir = os.path.join(self.client.storage_path, "rangetest_logs")
            os.makedirs(log_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_name = "".join(c for c in contact_name if c.isalnum() or c in (' ', '-', '_')).strip() or "unknown"
            
            # JSON
            json_file = f"rangetest_{safe_name}_{timestamp}.json"
            json_path = os.path.join(log_dir, json_file)
            
            with open(json_path, 'w') as f:
                json.dump({
                    'contact': contact_name,
                    'hash': source_hash,
                    'timestamp': timestamp,
                    'total_points': len(gps_log),
                    'gps_points': gps_log
                }, f, indent=2)
            
            print(f"💾 Saved: {json_file}")
            
            # KML
            kml_file = f"rangetest_{safe_name}_{timestamp}.kml"
            kml_path = os.path.join(log_dir, kml_file)
            self.create_kml_file(kml_path, gps_log, contact_name)
            
            return json_path, kml_path
        except Exception as e:
            print(f"⚠️ Save error: {e}")
            return None, None
    
    def create_kml_file(self, filepath, gps_log, contact_name):
        """Create KML"""
        try:
            kml = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Range Test - {contact_name}</name>
    <description>LXMF Range Test - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</description>
    
    <Style id="lineStyle">
      <LineStyle>
        <color>ff0000ff</color>
        <width>4</width>
      </LineStyle>
    </Style>
    
    <Style id="startPoint">
      <IconStyle>
        <color>ff00ff00</color>
        <scale>1.2</scale>
      </IconStyle>
    </Style>
    
    <Style id="endPoint">
      <IconStyle>
        <color>ff0000ff</color>
        <scale>1.2</scale>
      </IconStyle>
    </Style>
    
    <Placemark>
      <name>GPS Track</name>
      <styleUrl>#lineStyle</styleUrl>
      <LineString>
        <altitudeMode>absolute</altitudeMode>
        <coordinates>
'''
            
            for point in gps_log:
                lon = point['lon']
                lat = point['lat']
                alt = point.get('altitude', 0)
                kml += f"          {lon},{lat},{alt}\n"
            
            kml += '''        </coordinates>
      </LineString>
    </Placemark>
    
'''
            
            if gps_log:
                first = gps_log[0]
                kml += f'''    <Placemark>
      <name>START</name>
      <description>First ping - {first.get('time', 'N/A')}</description>
      <styleUrl>#startPoint</styleUrl>
      <Point>
        <coordinates>{first['lon']},{first['lat']},{first.get('altitude', 0)}</coordinates>
      </Point>
    </Placemark>
    
'''
                
                last = gps_log[-1]
                kml += f'''    <Placemark>
      <name>END</name>
      <description>Last ping - {last.get('time', 'N/A')}</description>
      <styleUrl>#endPoint</styleUrl>
      <Point>
        <coordinates>{last['lon']},{last['lat']},{last.get('altitude', 0)}</coordinates>
      </Point>
    </Placemark>
    
'''
            
            kml += '''  </Document>
</kml>'''
            
            with open(filepath, 'w') as f:
                f.write(kml)
            
            print(f"🌍 Saved: {os.path.basename(filepath)}")
        
        except Exception as e:
            print(f"⚠️ KML error: {e}")
    
    def handle_file_request(self, source_hash, content):
        """Handle file request"""
        parts = content.lower().split()
        
        if source_hash not in self.last_completed_tests:
            self.client.send_message(source_hash, "❌ No completed test found")
            return
        
        file_info = self.last_completed_tests[source_hash]
        file_type = parts[1] if len(parts) >= 2 else 'kml'
        
        if file_type == 'kml':
            filepath = file_info.get('kml_path')
        elif file_type == 'json':
            filepath = file_info.get('json_path')
        elif file_type == 'both':
            self.send_file(source_hash, file_info.get('kml_path'), 'KML')
            time.sleep(1)
            self.send_file(source_hash, file_info.get('json_path'), 'JSON')
            return
        else:
            self.client.send_message(source_hash, "❌ Unknown type\nUsage: rangegetfile [kml|json|both]")
            return
        
        if filepath and os.path.exists(filepath):
            self.send_file(source_hash, filepath, file_type.upper())
        else:
            self.client.send_message(source_hash, f"❌ File not found")
    
    def send_file(self, dest_hash, filepath, file_type):
        """Send file"""
        try:
            contact = self.client.format_contact_display_short(dest_hash)
            filename = os.path.basename(filepath)
            filesize = os.path.getsize(filepath)
            
            if filesize > 51200:
                self.client.send_message(dest_hash, f"❌ File too large: {filesize/1024:.1f}KB")
                return
            
            with open(filepath, 'rb') as f:
                file_data = f.read()
            
            encoded = base64.b64encode(file_data).decode('utf-8')
            
            print(f"[Range Test] 📤 Sending {file_type} to {contact} ({filesize} bytes)")
            
            chunk_size = 8000
            chunks = [encoded[i:i+chunk_size] for i in range(0, len(encoded), chunk_size)]
            total_chunks = len(chunks)
            
            if total_chunks == 1:
                msg = f"📦 FILE: {filename}\nType: {file_type}\nSize: {filesize} bytes\nChunks: 1/1\n───\n{encoded}"
                self.client.send_message(dest_hash, msg)
            else:
                for i, chunk in enumerate(chunks, 1):
                    msg = f"📦 FILE: {filename}\nType: {file_type}\nSize: {filesize} bytes\nChunks: {i}/{total_chunks}\n───\n{chunk}"
                    self.client.send_message(dest_hash, msg)
                    time.sleep(0.5)
            
            print(f"[Range Test] ✅ File sent ({total_chunks} chunk(s))")
        
        except Exception as e:
            print(f"[Range Test] ❌ Send error: {e}")
    
    def handle_file_receive(self, source_hash, content):
        """Handle file receive"""
        try:
            lines = content.split('\n')
            filename = None
            file_type = None
            chunks_info = None
            
            for line in lines:
                if line.startswith('📦 FILE:'):
                    filename = line.replace('📦 FILE:', '').strip()
                elif line.startswith('Type:'):
                    file_type = line.replace('Type:', '').strip()
                elif line.startswith('Chunks:'):
                    chunks_info = line.replace('Chunks:', '').strip()
                elif line.startswith('───'):
                    data_start = lines.index(line) + 1
                    encoded_data = '\n'.join(lines[data_start:])
                    break
            
            if not filename or not encoded_data:
                return
            
            current_chunk, total_chunks = map(int, chunks_info.split('/'))
            
            receive_dir = os.path.join(self.client.storage_path, "rangetest_received")
            os.makedirs(receive_dir, exist_ok=True)
            
            if total_chunks > 1:
                chunk_dir = os.path.join(receive_dir, f".chunks_{filename}")
                os.makedirs(chunk_dir, exist_ok=True)
                
                with open(os.path.join(chunk_dir, f"chunk_{current_chunk}"), 'w') as f:
                    f.write(encoded_data)
                
                print(f"[Range Test] 📥 Chunk {current_chunk}/{total_chunks}")
                
                existing = [f for f in os.listdir(chunk_dir) if f.startswith('chunk_')]
                if len(existing) == total_chunks:
                    full_data = ""
                    for i in range(1, total_chunks + 1):
                        with open(os.path.join(chunk_dir, f"chunk_{i}"), 'r') as f:
                            full_data += f.read()
                    
                    self.save_received_file(receive_dir, filename, full_data, file_type, source_hash)
                    
                    import shutil
                    shutil.rmtree(chunk_dir)
            else:
                self.save_received_file(receive_dir, filename, encoded_data, file_type, source_hash)
        
        except Exception as e:
            print(f"[Range Test] ❌ Receive error: {e}")
    
    def save_received_file(self, receive_dir, filename, encoded_data, file_type, source_hash):
        """Save received file"""
        try:
            file_data = base64.b64decode(encoded_data)
            filepath = os.path.join(receive_dir, filename)
            
            with open(filepath, 'wb') as f:
                f.write(file_data)
            
            contact = self.client.format_contact_display_short(source_hash)
            
            print(f"\n{'─'*70}")
            print(f"✅ FILE RECEIVED!")
            print(f"{'─'*70}")
            print(f"From: {contact}")
            print(f"File: {filename}")
            print(f"Size: {len(file_data)} bytes")
            print(f"Saved: {filepath}")
            print(f"{'─'*70}\n")
            
            if file_type == 'KML':
                print(f"💡 Open in Google Earth!\n")
            
            self.client.send_message(source_hash, f"✅ File received!\n📁 {filename}")
        
        except Exception as e:
            print(f"[Range Test] ❌ Save error: {e}")
    
    def handle_command(self, cmd, parts):
        """Handle commands"""
        if cmd == 'rangetest':
            if self.active_server_tests:
                print("\n📡 ACTIVE TESTS (SERVER)")
                for h, c in self.active_server_tests.items():
                    print(f"  {self.client.format_contact_display_short(h)}: {c['current']}/{c['count']} sent, {len(c['gps_log'])} GPS")
            elif self.active_client_tests:
                print("\n📡 ACTIVE TESTS (CLIENT)")
                for h, c in self.active_client_tests.items():
                    print(f"  {self.client.format_contact_display_short(h)}: {c['received']}/{c['count']} received")
            else:
                print("\n📡 No active tests\n")
        
        elif cmd == 'rangestatus':
            print("\n📍 GPS STATUS")
            print("─"*70)
            gps = self.get_gps_location()
            if gps:
                print(f"✅ Available")
                print(f"   Lat: {gps['latitude']:.6f}")
                print(f"   Lon: {gps['longitude']:.6f}")
                print(f"   Accuracy: ±{gps.get('accuracy', 0):.0f}m")
                print(f"   Provider: {gps.get('provider', 'unknown')}")
            else:
                print("❌ Unavailable")
                print("\n   For Termux:")
                print("   pkg install termux-api")
                print("   Install Termux:API from F-Droid")
                print("   Grant location permission")
            print("─"*70 + "\n")
        
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
                        del self.active_client_tests[dest_hash]
                        print(f"⚠️ Stopped client test")
                    else:
                        print("❌ No active test with that contact")
                else:
                    print(f"❌ Unknown: {target}")
        
        elif cmd == 'rangegetfile':
            if len(parts) < 2:
                print("💡 Usage: rangegetfile <contact> [kml|json|both]")
            else:
                target = parts[1]
                file_type = parts[2] if len(parts) > 2 else 'kml'
                dest_hash = self.client.resolve_contact_or_hash(target)
                if dest_hash:
                    print(f"\n📥 Requesting {file_type.upper()} from {self.client.format_contact_display_short(dest_hash)}...")
                    self.client.send_message(dest_hash, f"rangegetfile {file_type}")
                else:
                    print(f"❌ Unknown: {target}")

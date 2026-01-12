# rangetest.py
import time
import threading
import json
import subprocess
import platform
import os
from datetime import datetime
import re
import base64

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['rangetest', 'rangestop', 'rangestatus', 'rangegetfile']
        self.description = "Range testing - automated bidirectional testing with GPS"
        
        # Active test sessions (when WE are the server - fixed node)
        self.active_tests = {}
        self.test_threads = {}
        
        # Store last completed test info for file retrieval
        self.last_completed_tests = {}  # {source_hash: {'json_path': ..., 'kml_path': ...}}
        
    def on_message(self, message, msg_data):
        """Handle incoming range test commands and responses"""
        content = msg_data['content'].strip()
        source_hash = msg_data['source_hash']
        
        # === DETECT IF WE'RE THE FIXED NODE (SERVER) ===
        
        # Someone sent us "rangetest N T" - we become the server
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
                    
                    # Start range test as SERVER (we send pings)
                    self.start_range_test_server(source_hash, count, interval)
                    return True
                else:
                    self.client.send_message(source_hash, 
                        "❌ Usage: rangetest <count> <interval>\n"
                        "Example: rangetest 50 15\n\n"
                        "I will send you pings, you reply with GPS!")
                    return True
            except ValueError:
                self.client.send_message(source_hash, "❌ Invalid numbers")
                return True
        
        # Stop command
        elif content.lower() == 'rangestop':
            self.stop_range_test_server(source_hash)
            return True
        
        # Request to get KML/JSON files
        elif content.lower().startswith('rangegetfile'):
            self.handle_file_request(source_hash, content)
            return True
        
        # === DETECT IF WE'RE THE MOBILE NODE (CLIENT) ===
        
        # We received a ping - auto-reply with GPS
        elif content.startswith('📡 RANGE TEST ['):
            try:
                # Extract message number
                match = re.search(r'\[(\d+)/(\d+)\]', content)
                if match:
                    current = int(match.group(1))
                    total = int(match.group(2))
                    
                    # Auto-reply with GPS (NO user action needed!)
                    self.send_gps_response(source_hash, current, total)
                    
                    # Notify user (vibration/sound)
                    self.notify_range_ping(current, total)
                    
                    # Let the message show normally too
                    return False
            except Exception as e:
                print(f"[Range Test] Error handling ping: {e}")
        
        # We received a GPS response (we're the server)
        elif content.startswith('📍 GPS RESPONSE ['):
            try:
                # Parse and log GPS data
                match = re.search(r'\[(\d+)/(\d+)\]', content)
                if match:
                    current = int(match.group(1))
                    
                    # Extract GPS coordinates
                    lat_match = re.search(r'Lat: ([-\d.]+)', content)
                    lon_match = re.search(r'Lon: ([-\d.]+)', content)
                    
                    if lat_match and lon_match and source_hash in self.active_tests:
                        lat = float(lat_match.group(1))
                        lon = float(lon_match.group(1))
                        
                        # Extract optional fields
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
                        
                        # Store in log
                        self.active_tests[source_hash]['gps_log'].append(gps_point)
                        
                        contact = self.client.format_contact_display_short(source_hash)
                        print(f"[Range Test] 📍 GPS #{current} received from {contact}")
                        
                        # Don't show the full GPS message to user
                        return True
            except Exception as e:
                print(f"[Range Test] Error parsing GPS: {e}")
        
        # Receiving file transfer
        elif content.startswith('📦 FILE:'):
            self.handle_file_receive(source_hash, content)
            return True
        
        return False
    
    def handle_file_request(self, source_hash, content):
        """Handle request to send KML/JSON files"""
        parts = content.lower().split()
        
        # Check if we have files for this source
        if source_hash not in self.last_completed_tests:
            self.client.send_message(source_hash, 
                "❌ No completed range test found\n"
                "Complete a range test first!")
            return
        
        file_info = self.last_completed_tests[source_hash]
        
        # Determine which file to send
        if len(parts) >= 2:
            file_type = parts[1]
        else:
            file_type = 'kml'  # Default to KML
        
        if file_type == 'kml':
            filepath = file_info.get('kml_path')
            file_desc = "KML (Google Earth)"
        elif file_type == 'json':
            filepath = file_info.get('json_path')
            file_desc = "JSON (Full data)"
        elif file_type == 'both':
            # Send both files
            self.send_file(source_hash, file_info.get('kml_path'), 'KML')
            time.sleep(1)  # Small delay between files
            self.send_file(source_hash, file_info.get('json_path'), 'JSON')
            return
        else:
            self.client.send_message(source_hash,
                "❌ Unknown file type\n"
                "Usage: rangegetfile [kml|json|both]\n"
                "Default: kml")
            return
        
        # Send the file
        if filepath and os.path.exists(filepath):
            self.send_file(source_hash, filepath, file_type.upper())
        else:
            self.client.send_message(source_hash, f"❌ {file_desc} file not found")
    
    def send_file(self, dest_hash, filepath, file_type):
        """Send file via LXMF message"""
        try:
            contact = self.client.format_contact_display_short(dest_hash)
            filename = os.path.basename(filepath)
            filesize = os.path.getsize(filepath)
            
            # Check file size (limit to 50KB for LXMF)
            if filesize > 51200:  # 50KB
                self.client.send_message(dest_hash, 
                    f"❌ File too large: {filesize/1024:.1f}KB\n"
                    f"Maximum: 50KB\n"
                    f"Tip: Use a shorter range test")
                return
            
            # Read and encode file
            with open(filepath, 'rb') as f:
                file_data = f.read()
            
            encoded = base64.b64encode(file_data).decode('utf-8')
            
            # Send file metadata first
            print(f"[Range Test] 📤 Sending {file_type} file to {contact} ({filesize} bytes)")
            
            # Split into chunks if needed (LXMF has message size limits)
            chunk_size = 8000  # Conservative chunk size
            chunks = [encoded[i:i+chunk_size] for i in range(0, len(encoded), chunk_size)]
            total_chunks = len(chunks)
            
            if total_chunks == 1:
                # Single message
                msg = f"📦 FILE: {filename}\n"
                msg += f"Type: {file_type}\n"
                msg += f"Size: {filesize} bytes\n"
                msg += f"Chunks: 1/1\n"
                msg += f"───\n{encoded}"
                
                self.client.send_message(dest_hash, msg)
            else:
                # Multiple chunks
                for i, chunk in enumerate(chunks, 1):
                    msg = f"📦 FILE: {filename}\n"
                    msg += f"Type: {file_type}\n"
                    msg += f"Size: {filesize} bytes\n"
                    msg += f"Chunks: {i}/{total_chunks}\n"
                    msg += f"───\n{chunk}"
                    
                    self.client.send_message(dest_hash, msg)
                    time.sleep(0.5)  # Small delay between chunks
            
            print(f"[Range Test] ✅ File sent successfully ({total_chunks} chunk(s))")
            
        except Exception as e:
            print(f"[Range Test] ❌ Error sending file: {e}")
            self.client.send_message(dest_hash, f"❌ Error sending file: {e}")
    
    def handle_file_receive(self, source_hash, content):
        """Handle received file chunks and save"""
        try:
            # Parse file header
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
                    # Data starts after this line
                    data_start = lines.index(line) + 1
                    encoded_data = '\n'.join(lines[data_start:])
                    break
            
            if not filename or not encoded_data:
                print("[Range Test] ⚠️ Invalid file format")
                return
            
            # Parse chunk info
            current_chunk, total_chunks = map(int, chunks_info.split('/'))
            
            # Create receive directory
            receive_dir = os.path.join(self.client.storage_path, "rangetest_received")
            os.makedirs(receive_dir, exist_ok=True)
            
            # Handle multi-chunk files
            if total_chunks > 1:
                # Store chunks temporarily
                chunk_dir = os.path.join(receive_dir, f".chunks_{filename}")
                os.makedirs(chunk_dir, exist_ok=True)
                
                chunk_file = os.path.join(chunk_dir, f"chunk_{current_chunk}")
                with open(chunk_file, 'w') as f:
                    f.write(encoded_data)
                
                print(f"[Range Test] 📥 Received chunk {current_chunk}/{total_chunks} of {filename}")
                
                # Check if we have all chunks
                existing_chunks = [f for f in os.listdir(chunk_dir) if f.startswith('chunk_')]
                if len(existing_chunks) == total_chunks:
                    # Reconstruct file
                    print(f"[Range Test] 🔨 Reconstructing file...")
                    full_data = ""
                    for i in range(1, total_chunks + 1):
                        chunk_path = os.path.join(chunk_dir, f"chunk_{i}")
                        with open(chunk_path, 'r') as f:
                            full_data += f.read()
                    
                    # Decode and save
                    self.save_received_file(receive_dir, filename, full_data, file_type, source_hash)
                    
                    # Cleanup chunks
                    import shutil
                    shutil.rmtree(chunk_dir)
            else:
                # Single chunk - save directly
                self.save_received_file(receive_dir, filename, encoded_data, file_type, source_hash)
        
        except Exception as e:
            print(f"[Range Test] ❌ Error receiving file: {e}")
    
    def save_received_file(self, receive_dir, filename, encoded_data, file_type, source_hash):
        """Decode and save received file"""
        try:
            # Decode base64
            file_data = base64.b64decode(encoded_data)
            
            # Save file
            filepath = os.path.join(receive_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(file_data)
            
            filesize = len(file_data)
            contact = self.client.format_contact_display_short(source_hash)
            
            print(f"\n{'─'*70}")
            print(f"✅ FILE RECEIVED!")
            print(f"{'─'*70}")
            print(f"From: {contact}")
            print(f"File: {filename}")
            print(f"Type: {file_type}")
            print(f"Size: {filesize} bytes")
            print(f"Saved: {filepath}")
            print(f"{'─'*70}\n")
            
            # Show helpful message based on file type
            if file_type == 'KML':
                print("💡 Open in Google Earth to view your route!")
                print(f"   File: {filepath}\n")
            elif file_type == 'JSON':
                print("💡 Contains full GPS data with timestamps")
                print(f"   File: {filepath}\n")
            
            # Send confirmation
            self.client.send_message(source_hash, 
                f"✅ File received!\n"
                f"📁 {filename}\n"
                f"💾 Saved to: rangetest_received/")
        
        except Exception as e:
            print(f"[Range Test] ❌ Error saving file: {e}")
    
    def start_range_test_server(self, source_hash, count, interval):
        """Start range test as SERVER (we send pings, mobile sends GPS)"""
        # Stop any existing test
        if source_hash in self.active_tests:
            self.stop_range_test_server(source_hash)
        
        # Store test configuration
        self.active_tests[source_hash] = {
            'count': count,
            'interval': interval,
            'current': 0,
            'start_time': time.time(),
            'stop_flag': threading.Event(),
            'gps_log': []
        }
        
        contact_display = self.client.format_contact_display_short(source_hash)
        
        print(f"\n{'─'*70}")
        print(f"🎯 RANGE TEST STARTED")
        print(f"{'─'*70}")
        print(f"📱 Mobile client: {contact_display}")
        print(f"📊 Configuration: {count} pings @ {interval}s interval")
        print(f"⏱️ Estimated duration: ~{(count * interval) // 60}m {(count * interval) % 60}s")
        print(f"📍 GPS tracking: ENABLED")
        print(f"{'─'*70}\n")
        
        # Send confirmation to mobile
        self.client.send_message(
            source_hash, 
            f"✅ RANGE TEST ACTIVE\n\n"
            f"📊 Config: {count} pings @ {interval}s\n"
            f"⏱️ Duration: ~{(count * interval) // 60}m {(count * interval) % 60}s\n\n"
            f"🚗 Start driving!\n"
            f"📍 GPS will be sent automatically\n"
            f"🔊 You'll get notifications for each ping\n\n"
            f"Commands:\n"
            f"  rangestop - Stop test\n"
            f"  rangegetfile - Get KML/JSON after test"
        )
        
        # Start background thread
        thread = threading.Thread(
            target=self._range_test_server_worker,
            args=(source_hash,),
            daemon=True
        )
        self.test_threads[source_hash] = thread
        thread.start()
    
    def _range_test_server_worker(self, source_hash):
        """Background worker - sends pings periodically"""
        test_config = self.active_tests[source_hash]
        contact_display = self.client.format_contact_display_short(source_hash)
        
        try:
            while test_config['current'] < test_config['count']:
                if test_config['stop_flag'].is_set():
                    break
                
                test_config['current'] += 1
                current = test_config['current']
                total = test_config['count']
                
                # Calculate timing
                elapsed = time.time() - test_config['start_time']
                estimated_total = test_config['interval'] * total
                remaining = estimated_total - elapsed
                
                timestamp = datetime.now().strftime('%H:%M:%S')
                
                # Build ping message
                msg = f"📡 RANGE TEST [{current}/{total}]\n"
                msg += f"🕐 Time: {timestamp}\n"
                msg += f"⏱️ Elapsed: {int(elapsed)}s\n"
                msg += f"⏳ Remaining: ~{int(remaining)}s\n"
                msg += f"📊 Progress: {int((current/total)*100)}%"
                
                # Send ping
                print(f"[Range Test] 📡 Ping {current}/{total} → {contact_display}")
                self.client.send_message(source_hash, msg)
                
                # Wait for interval
                for _ in range(test_config['interval']):
                    if test_config['stop_flag'].wait(1):
                        break
            
            # Test complete
            if not test_config['stop_flag'].is_set():
                self.send_test_summary(source_hash)
        
        except Exception as e:
            print(f"\n❌ Range test error: {e}\n")
            try:
                self.client.send_message(source_hash, f"❌ Range test error: {e}")
            except:
                pass
        
        finally:
            if source_hash in self.active_tests:
                del self.active_tests[source_hash]
            if source_hash in self.test_threads:
                del self.test_threads[source_hash]
    
    def send_gps_response(self, source_hash, current, total):
        """AUTO-REPLY with GPS when we receive a ping (MOBILE CLIENT)"""
        gps_data = self.get_gps_location()
        
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        if gps_data:
            lat = gps_data.get('latitude')
            lon = gps_data.get('longitude')
            accuracy = gps_data.get('accuracy', 0)
            speed = gps_data.get('speed', 0)
            altitude = gps_data.get('altitude', 0)
            
            msg = f"📍 GPS RESPONSE [{current}/{total}]\n"
            msg += f"🕐 {timestamp}\n"
            msg += f"🌍 Lat: {lat:.6f}\n"
            msg += f"🌍 Lon: {lon:.6f}\n"
            
            if accuracy:
                msg += f"🎯 Accuracy: ±{accuracy:.0f}m\n"
            if speed and speed > 0:
                msg += f"🚗 Speed: {speed*3.6:.1f} km/h\n"
            if altitude:
                msg += f"⛰️ Altitude: {altitude:.0f}m\n"
            
            msg += f"\n🗺️ https://maps.google.com/?q={lat},{lon}"
            
            print(f"[Range Test] 📍 Sending GPS {current}/{total}")
        else:
            # GPS unavailable
            msg = f"📍 GPS RESPONSE [{current}/{total}]\n"
            msg += f"🕐 {timestamp}\n"
            msg += f"⚠️ GPS unavailable"
            print(f"[Range Test] ⚠️ GPS unavailable for ping {current}/{total}")
        
        # Send GPS response
        self.client.send_message(source_hash, msg)
    
    def get_gps_location(self):
        """Get GPS location (cross-platform)"""
        system = platform.system()
        is_termux = os.path.exists('/data/data/com.termux')
        
        try:
            if is_termux:
                # TERMUX/ANDROID - use termux-location
                result = subprocess.run(
                    ['termux-location', '-p', 'gps'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    data = json.loads(result.stdout)
                    # Check if we got valid data
                    if 'latitude' in data and 'longitude' in data:
                        return data
                    else:
                        print("[GPS] No GPS fix yet")
                        return None
            
            elif system == 'Linux':
                # LINUX - try gpsd
                try:
                    import gpsd  # type: ignore
                    gpsd.connect()
                    packet = gpsd.get_current()
                    if packet.mode >= 2:  # 2D or 3D fix
                        return {
                            'latitude': packet.lat,
                            'longitude': packet.lon,
                            'altitude': packet.alt if packet.mode == 3 else 0,
                            'speed': packet.hspeed,
                            'accuracy': packet.error.get('epx', 0)
                        }
                except ImportError:
                    print("[GPS] gpsd module not installed: pip install gpsd-py3")
                except Exception as e:
                    print(f"[GPS] gpsd error: {e}")
        
        except subprocess.TimeoutExpired:
            print("[GPS] Timeout waiting for GPS fix")
        except Exception as e:
            print(f"[GPS] Error: {e}")
        
        return None
    
    def notify_range_ping(self, current, total):
        """Notify user of received ping (MOBILE CLIENT)"""
        is_termux = os.path.exists('/data/data/com.termux')
        
        try:
            if is_termux:
                # Vibrate
                os.system('termux-vibrate -d 100 2>/dev/null &')
                # Show notification
                os.system(f'termux-notification --title "📡 Range Ping {current}/{total}" --content "GPS auto-sent!" 2>/dev/null &')
            else:
                # Terminal bell
                print("\a", end="", flush=True)
        except:
            pass
    
    def send_test_summary(self, source_hash):
        """Send final summary with statistics"""
        test_config = self.active_tests[source_hash]
        elapsed = time.time() - test_config['start_time']
        gps_log = test_config.get('gps_log', [])
        
        contact_display = self.client.format_contact_display_short(source_hash)
        
        summary = f"✅ RANGE TEST COMPLETE!\n\n"
        summary += f"📨 Sent: {test_config['current']}/{test_config['count']} pings\n"
        summary += f"⏱️ Duration: {int(elapsed/60)}m {int(elapsed%60)}s\n"
        summary += f"📊 Avg interval: {int(elapsed/test_config['current'])}s\n"
        
        reception_rate = 0
        if gps_log:
            summary += f"\n📍 GPS Responses: {len(gps_log)}/{test_config['current']}\n"
            reception_rate = int((len(gps_log)/test_config['current'])*100)
            summary += f"📶 Reception rate: {reception_rate}%\n"
            
            # Calculate distance
            if len(gps_log) >= 2:
                try:
                    distance = self.calculate_total_distance(gps_log)
                    summary += f"\n🛣️ Distance traveled: ~{distance:.1f} km\n"
                    
                    # Max speed
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
        
        # Send summary
        self.client.send_message(source_hash, summary)
        
        print(f"\n{'─'*70}")
        print(f"✅ RANGE TEST COMPLETE: {contact_display}")
        print(f"{'─'*70}")
        print(f"📨 Pings sent: {test_config['current']}/{test_config['count']}")
        print(f"📍 GPS received: {len(gps_log)}/{test_config['current']}")
        if gps_log:
            print(f"📶 Reception: {reception_rate}%")
        print(f"{'─'*70}\n")
        
        # Save logs and store paths for file transfer
        if gps_log:
            json_path, kml_path = self.save_gps_log(source_hash, contact_display, gps_log)
            # Store for later file requests
            self.last_completed_tests[source_hash] = {
                'json_path': json_path,
                'kml_path': kml_path,
                'timestamp': time.time()
            }
    
    def calculate_total_distance(self, gps_log):
        """Calculate total distance from GPS points"""
        from math import radians, sin, cos, sqrt, atan2
        
        total_distance = 0
        for i in range(len(gps_log) - 1):
            lat1, lon1 = gps_log[i]['lat'], gps_log[i]['lon']
            lat2, lon2 = gps_log[i+1]['lat'], gps_log[i+1]['lon']
            
            R = 6371  # Earth radius in km
            
            lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            distance = R * c
            
            total_distance += distance
        
        return total_distance
    
    def save_gps_log(self, source_hash, contact_name, gps_log):
        """Save GPS log to JSON and KML - returns file paths"""
        json_path = None
        kml_path = None
        
        try:
            log_dir = os.path.join(self.client.storage_path, "rangetest_logs")
            os.makedirs(log_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Clean contact name for filename
            safe_name = "".join(c for c in contact_name if c.isalnum() or c in (' ', '-', '_')).strip()
            
            # Save JSON
            json_file = f"rangetest_{safe_name}_{timestamp}.json"
            json_path = os.path.join(log_dir, json_file)
            
            log_data = {
                'contact': contact_name,
                'hash': source_hash,
                'timestamp': timestamp,
                'total_points': len(gps_log),
                'gps_points': gps_log
            }
            
            with open(json_path, 'w') as f:
                json.dump(log_data, f, indent=2)
            
            print(f"💾 Saved: {json_file}")
            
            # Save KML
            kml_file = f"rangetest_{safe_name}_{timestamp}.kml"
            kml_path = os.path.join(log_dir, kml_file)
            self.create_kml_file(kml_path, gps_log, contact_name)
            
            return json_path, kml_path
            
        except Exception as e:
            print(f"⚠️ Could not save logs: {e}")
            return None, None
    
    def create_kml_file(self, filepath, gps_log, contact_name):
        """Create KML for Google Earth"""
        try:
            kml = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Range Test - {contact_name}</name>
    <description>LXMF Range Test GPS Track - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</description>
    
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
            
            # Add start marker
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
                
                # Add end marker
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
            print(f"⚠️ Could not create KML: {e}")
    
    def stop_range_test_server(self, source_hash):
        """Stop active test"""
        if source_hash in self.active_tests:
            test_config = self.active_tests[source_hash]
            test_config['stop_flag'].set()
            
            contact_display = self.client.format_contact_display_short(source_hash)
            print(f"\n⚠️ Stopping range test for {contact_display}\n")
            
            self.client.send_message(source_hash, "⚠️ Range test stopped")
        else:
            self.client.send_message(source_hash, "❌ No active range test")
    
    def handle_command(self, cmd, parts):
        """Handle local commands"""
        if cmd == 'rangetest':
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
        
        elif cmd == 'rangegetfile':
            # Local command to request file from server
            if len(parts) < 2:
                print("💡 Usage: rangegetfile <contact_#/name> [kml|json|both]")
                print("Example: rangegetfile HomeNode kml")
            else:
                target = parts[1]
                file_type = parts[2] if len(parts) > 2 else 'kml'
                
                dest_hash = self.client.resolve_contact_or_hash(target)
                if dest_hash:
                    contact = self.client.format_contact_display_short(dest_hash)
                    print(f"\n📥 Requesting {file_type.upper()} file from {contact}...")
                    self.client.send_message(dest_hash, f"rangegetfile {file_type}")
                else:
                    print(f"❌ Unknown contact: {target}")
    
    def show_active_tests(self):
        """Show active tests"""
        if not self.active_tests:
            print("\n📡 No active range tests\n")
        else:
            print("\n" + "─"*70)
            print("📡 ACTIVE RANGE TESTS")
            print("─"*70)
            for hash_str, config in self.active_tests.items():
                contact = self.client.format_contact_display_short(hash_str)
                elapsed = int(time.time() - config['start_time'])
                gps_count = len(config.get('gps_log', []))
                
                print(f"\n🎯 {contact}")
                print(f"   Progress: {config['current']}/{config['count']}")
                print(f"   Interval: {config['interval']}s")
                print(f"   Elapsed: {elapsed}s")
                print(f"   GPS received: {gps_count}/{config['current']}")
                if gps_count > 0:
                    reception = int((gps_count/config['current'])*100) if config['current'] > 0 else 0
                    print(f"   Reception: {reception}%")
            print("─"*70 + "\n")
    
    def show_detailed_status(self):
        """Show detailed status"""
        self.show_active_tests()
        
        print("─"*70)
        print("📍 GPS STATUS")
        print("─"*70)
        
        gps_data = self.get_gps_location()
        if gps_data:
            print("✅ GPS Available")
            print(f"   Lat: {gps_data.get('latitude', 'N/A'):.6f}")
            print(f"   Lon: {gps_data.get('longitude', 'N/A'):.6f}")
            if gps_data.get('accuracy'):
                print(f"   Accuracy: ±{gps_data['accuracy']:.0f}m")
        else:
            print("❌ GPS Not Available")
            print("\n   📱 Termux setup:")
            print("      pkg install termux-api")
            print("      Install 'Termux:API' from F-Droid")
            print("      termux-location  # test GPS")
        
        print("─"*70 + "\n")

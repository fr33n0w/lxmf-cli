# rangetest_client.py
import time
import json
import subprocess
import os
import shutil
from datetime import datetime

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['rangelogs', 'rl', 'rangeexport', 'rex', 'rangestatus']
        self.description = "Range Test Client - Log GPS positions from range test pings"
        
        # File paths in Termux storage (persistent, incremental)
        self.storage_dir = self.client.storage_path
        self.json_file = os.path.join(self.storage_dir, "rangetest.json")
        self.kml_file = os.path.join(self.storage_dir, "rangetest.kml")
        self.csv_file = os.path.join(self.storage_dir, "rangetest.csv")
        self.geojson_file = os.path.join(self.storage_dir, "rangetest.geojson")
        self.html_file = os.path.join(self.storage_dir, "rangetest.html")
        
        # Initialize files if they don't exist
        self.init_files()
        
        # GPS provider preference
        self.gps_providers = ['gps', 'network', 'passive']
    
    def init_files(self):
        """Initialize all data files if they don't exist"""
        try:
            # JSON
            if not os.path.exists(self.json_file):
                with open(self.json_file, 'w') as f:
                    json.dump({'points': []}, f, indent=2)
            
            # CSV
            if not os.path.exists(self.csv_file):
                with open(self.csv_file, 'w') as f:
                    f.write("timestamp,date,time,latitude,longitude,accuracy,speed,altitude,provider,rssi,snr,q\n")
            
            # KML
            if not os.path.exists(self.kml_file):
                self.init_kml()
            
            # GeoJSON
            if not os.path.exists(self.geojson_file):
                with open(self.geojson_file, 'w') as f:
                    json.dump({
                        "type": "FeatureCollection",
                        "features": []
                    }, f, indent=2)
            
            # HTML
            if not os.path.exists(self.html_file):
                self.init_html()
        
        except Exception as e:
            print(f"[Range Client] ⚠️ Init error: {e}")
    
    def init_kml(self):
        """Initialize KML file with header"""
        kml_header = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Range Test Coverage</name>
    <description>LXMF Range Test - All Coverage Points</description>
    
    <Style id="rangePoint">
      <IconStyle>
        <color>ff0078d4</color>
        <scale>0.8</scale>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/paddle/blu-circle.png</href>
        </Icon>
      </IconStyle>
    </Style>
    
    <Style id="pathStyle">
      <LineStyle>
        <color>ffff0000</color>
        <width>3</width>
      </LineStyle>
    </Style>
    
    <Folder>
      <name>Coverage Points</name>
'''
        
        kml_footer = '''    </Folder>
  </Document>
</kml>'''
        
        with open(self.kml_file, 'w') as f:
            f.write(kml_header + kml_footer)
    
    def init_html(self):
        """Initialize HTML map file"""
        html = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Range Test Coverage Map</title>
    <style>
        body { margin: 0; padding: 0; font-family: Arial, sans-serif; }
        #map { position: absolute; top: 0; bottom: 100px; width: 100%; }
        #info {
            position: absolute; bottom: 0; width: 100%; height: 100px;
            background: rgba(255, 255, 255, 0.95); padding: 15px;
            box-sizing: border-box; border-top: 3px solid #0078d4;
            overflow-y: auto;
        }
        .stat { display: inline-block; margin-right: 20px; font-size: 14px; }
        .stat-label { font-weight: bold; color: #0078d4; }
        @media (max-width: 600px) {
            #info { height: 120px; }
            .stat { display: block; margin: 3px 0; }
        }
    </style>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body>
    <div id="map"></div>
    <div id="info">
        <div class="stat"><span class="stat-label">Total Points:</span> <span id="points">0</span></div>
        <div class="stat"><span class="stat-label">Last Update:</span> <span id="lastupdate">-</span></div>
        <div class="stat"><span class="stat-label">Coverage:</span> <span id="coverage">-</span></div>
    </div>

    <script>
        var map = L.map('map').setView([45.0, 7.0], 13);
        
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '© OpenStreetMap contributors'
        }).addTo(map);
        
        var markers = [];
        var points = [];
        
        function getSignalColor(rssi) {
            if (rssi === null || rssi === undefined) return '#0078d4';
            if (rssi >= -60) return '#00ff00';
            if (rssi >= -70) return '#7fff00';
            if (rssi >= -80) return '#ffff00';
            if (rssi >= -90) return '#ffa500';
            if (rssi >= -100) return '#ff6600';
            return '#ff0000';
        }
        
        function addPoint(lat, lon, timestamp, date, time, accuracy, rssi, snr, q, provider) {
            points.push([lat, lon]);
            
            var color = getSignalColor(rssi);
            var marker = L.circleMarker([lat, lon], {
                radius: 6,
                fillColor: color,
                color: '#fff',
                weight: 2,
                opacity: 1,
                fillOpacity: 0.8
            }).addTo(map);
            
            var popup = '<b>' + date + ' ' + time + '</b><br>' +
                       'Lat: ' + lat.toFixed(6) + '<br>' +
                       'Lon: ' + lon.toFixed(6) + '<br>' +
                       'Accuracy: ±' + accuracy + 'm<br>' +
                       'Provider: ' + provider + '<br>';
            
            if (rssi !== null && rssi !== undefined) {
                popup += 'RSSI: ' + rssi + ' dBm<br>';
            }
            if (snr !== null && snr !== undefined) {
                popup += 'SNR: ' + snr + ' dB<br>';
            }
            if (q !== null && q !== undefined) {
                popup += 'Quality: ' + q + '%<br>';
            }
            
            marker.bindPopup(popup);
            markers.push(marker);
            
            document.getElementById('points').textContent = points.length;
            document.getElementById('lastupdate').textContent = date + ' ' + time;
            
            if (points.length > 0) {
                var bounds = L.latLngBounds(points);
                map.fitBounds(bounds, {padding: [50, 50]});
            }
        }
        
        // POINTS DATA WILL BE INSERTED HERE
        // POINTS_START
    </script>
</body>
</html>'''
        
        with open(self.html_file, 'w') as f:
            f.write(html)
    
    def on_message(self, message, msg_data):
        """Handle incoming RangeTest messages"""
        try:
            content = msg_data['content'].strip()
            
            # Check if it's a RangeTest message
            if '[RangeTest]' in content or '[rangetest]' in content.lower():
                # Log GPS position
                print(f"\n{'='*60}")
                print(f"📡 Range Test Ping Received!")
                print(f"{'='*60}")
                print(f"Message: {content}")
                
                # Get GPS location
                gps_data = self.get_gps_location()
                
                if gps_data:
                    # Extract signal data from message
                    rssi, snr, q = self.extract_link_stats(message)
                    
                    # Save to all formats
                    self.save_point(gps_data, rssi, snr, q)
                    
                    print(f"[GPS] ✅ Logged: {gps_data['latitude']:.6f}, {gps_data['longitude']:.6f}")
                    print(f"      Accuracy: ±{gps_data.get('accuracy', 0):.0f}m")
                    print(f"      Provider: {gps_data.get('provider', 'unknown')}")
                    
                    if rssi is not None:
                        print(f"[RSSI] {rssi:.1f} dBm", end="")
                        if snr is not None:
                            print(f" | SNR: {snr:.1f} dB", end="")
                        if q is not None:
                            print(f" | Q: {q:.1f}%", end="")
                        print()
                    
                    # Notify
                    self.notify_saved()
                else:
                    print(f"[GPS] ❌ GPS unavailable - point not logged")
                
                print(f"{'='*60}\n")
                
                return False  # Let message be processed normally
        
        except Exception as e:
            print(f"[Range Client] ⚠️ Message handler error: {e}")
            import traceback
            traceback.print_exc()
        
        return False
    
    def extract_link_stats(self, message):
        """Extract RSSI, SNR, and link quality from LXMF message"""
        rssi = None
        snr = None
        q = None
        
        try:
            if hasattr(message, 'packet') and message.packet:
                packet = message.packet
                
                if hasattr(packet, 'rssi'):
                    rssi = packet.rssi
                
                if hasattr(packet, 'snr'):
                    snr = packet.snr
                
                if hasattr(packet, 'q'):
                    q = packet.q
            
            if hasattr(message, 'receipt') and message.receipt:
                receipt = message.receipt
                
                if rssi is None and hasattr(receipt, 'rssi'):
                    rssi = receipt.rssi
                
                if snr is None and hasattr(receipt, 'snr'):
                    snr = receipt.snr
                
                if q is None and hasattr(receipt, 'q'):
                    q = receipt.q
        
        except Exception:
            pass
        
        return rssi, snr, q
    
    def get_gps_location(self):
        """Get GPS location - prefer GPS, fallback to network"""
        is_termux = os.path.exists('/data/data/com.termux')
        
        if not is_termux:
            return None
        
        try:
            # Try providers in order: gps (satellite), network, passive
            for provider in self.gps_providers:
                try:
                    result = subprocess.run(
                        ['termux-location', '-p', provider],
                        capture_output=True,
                        text=True,
                        timeout=8 if provider == 'gps' else 5,
                        env=os.environ.copy()
                    )
                    
                    if result.returncode == 0 and result.stdout:
                        data = json.loads(result.stdout.strip())
                        
                        if 'latitude' in data and 'longitude' in data:
                            lat = data.get('latitude')
                            lon = data.get('longitude')
                            
                            if lat and lon and (abs(lat) > 0.001 or abs(lon) > 0.001):
                                data['provider'] = provider
                                print(f"[GPS] Using provider: {provider}")
                                return data
                
                except subprocess.TimeoutExpired:
                    print(f"[GPS] Provider {provider} timeout, trying next...")
                    continue
                except json.JSONDecodeError:
                    continue
                except Exception:
                    continue
            
            return None
        
        except Exception:
            return None
    
    def save_point(self, gps_data, rssi=None, snr=None, q=None):
        """Save GPS point to all file formats"""
        try:
            timestamp = datetime.now()
            timestamp_str = timestamp.isoformat()
            date_str = timestamp.strftime('%Y-%m-%d')
            time_str = timestamp.strftime('%H:%M:%S')
            
            lat = gps_data['latitude']
            lon = gps_data['longitude']
            accuracy = gps_data.get('accuracy', 0)
            speed = gps_data.get('speed', 0)
            altitude = gps_data.get('altitude', 0)
            provider = gps_data.get('provider', 'unknown')
            
            # Save to JSON
            self.append_to_json(timestamp_str, date_str, time_str, lat, lon, 
                              accuracy, speed, altitude, provider, rssi, snr, q)
            
            # Save to CSV
            self.append_to_csv(timestamp_str, date_str, time_str, lat, lon, 
                             accuracy, speed, altitude, provider, rssi, snr, q)
            
            # Save to KML
            self.append_to_kml(timestamp_str, date_str, time_str, lat, lon, 
                             accuracy, speed, altitude, provider, rssi, snr, q)
            
            # Save to GeoJSON
            self.append_to_geojson(timestamp_str, date_str, time_str, lat, lon, 
                                  accuracy, speed, altitude, provider, rssi, snr, q)
            
            # Save to HTML
            self.append_to_html(date_str, time_str, lat, lon, accuracy, 
                              provider, rssi, snr, q)
        
        except Exception as e:
            print(f"[Range Client] ⚠️ Save error: {e}")
            import traceback
            traceback.print_exc()
    
    def append_to_json(self, timestamp, date, time, lat, lon, accuracy, 
                       speed, altitude, provider, rssi, snr, q):
        """Append point to JSON file"""
        try:
            with open(self.json_file, 'r') as f:
                data = json.load(f)
            
            point = {
                'timestamp': timestamp,
                'date': date,
                'time': time,
                'latitude': lat,
                'longitude': lon,
                'accuracy': accuracy,
                'speed': speed,
                'altitude': altitude,
                'provider': provider,
                'rssi': rssi,
                'snr': snr,
                'q': q
            }
            
            data['points'].append(point)
            
            with open(self.json_file, 'w') as f:
                json.dump(data, f, indent=2)
        
        except Exception as e:
            print(f"[JSON] ⚠️ Error: {e}")
    
    def append_to_csv(self, timestamp, date, time, lat, lon, accuracy, 
                      speed, altitude, provider, rssi, snr, q):
        """Append point to CSV file"""
        try:
            with open(self.csv_file, 'a') as f:
                f.write(f"{timestamp},{date},{time},{lat},{lon},{accuracy},"
                       f"{speed},{altitude},{provider},{rssi},{snr},{q}\n")
        
        except Exception as e:
            print(f"[CSV] ⚠️ Error: {e}")
    
    def append_to_kml(self, timestamp, date, time, lat, lon, accuracy, 
                      speed, altitude, provider, rssi, snr, q):
        """Append point to KML file"""
        try:
            # Read existing file
            with open(self.kml_file, 'r') as f:
                content = f.read()
            
            # Build description
            desc = f"{date} {time}\\n"
            desc += f"Accuracy: ±{accuracy:.0f}m\\n"
            desc += f"Speed: {speed:.1f} km/h\\n"
            desc += f"Altitude: {altitude:.1f}m\\n"
            desc += f"Provider: {provider}"
            
            if rssi is not None:
                desc += f"\\nRSSI: {rssi:.1f} dBm"
            if snr is not None:
                desc += f"\\nSNR: {snr:.1f} dB"
            if q is not None:
                desc += f"\\nQuality: {q:.1f}%"
            
            # Create placemark
            placemark = f'''      <Placemark>
        <name>{date} {time}</name>
        <description>{desc}</description>
        <styleUrl>#rangePoint</styleUrl>
        <Point>
          <coordinates>{lon:.6f},{lat:.6f},{altitude:.1f}</coordinates>
        </Point>
      </Placemark>
'''
            
            # Insert before closing Folder tag
            content = content.replace('    </Folder>', placemark + '    </Folder>')
            
            with open(self.kml_file, 'w') as f:
                f.write(content)
        
        except Exception as e:
            print(f"[KML] ⚠️ Error: {e}")
    
    def append_to_geojson(self, timestamp, date, time, lat, lon, accuracy, 
                          speed, altitude, provider, rssi, snr, q):
        """Append point to GeoJSON file"""
        try:
            with open(self.geojson_file, 'r') as f:
                data = json.load(f)
            
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat, altitude]
                },
                "properties": {
                    "timestamp": timestamp,
                    "date": date,
                    "time": time,
                    "accuracy": accuracy,
                    "speed": speed,
                    "altitude": altitude,
                    "provider": provider,
                    "rssi": rssi,
                    "snr": snr,
                    "q": q
                }
            }
            
            data['features'].append(feature)
            
            with open(self.geojson_file, 'w') as f:
                json.dump(data, f, indent=2)
        
        except Exception as e:
            print(f"[GeoJSON] ⚠️ Error: {e}")
    
    def append_to_html(self, date, time, lat, lon, accuracy, provider, rssi, snr, q):
        """Append point to HTML file"""
        try:
            # Format None values as null for JavaScript
            rssi_str = str(rssi) if rssi is not None else 'null'
            snr_str = str(snr) if snr is not None else 'null'
            q_str = str(q) if q is not None else 'null'
            
            js_line = f"        addPoint({lat}, {lon}, '{date}', '{time}', {accuracy}, {rssi_str}, {snr_str}, {q_str}, '{provider}');\n"
            
            with open(self.html_file, 'r') as f:
                content = f.read()
            
            if '// POINTS_START' in content:
                content = content.replace('// POINTS_START', js_line + '// POINTS_START')
            
            with open(self.html_file, 'w') as f:
                f.write(content)
        
        except Exception as e:
            print(f"[HTML] ⚠️ Error: {e}")
    
    def notify_saved(self):
        """Notify user that point was saved"""
        is_termux = os.path.exists('/data/data/com.termux')
        
        try:
            if is_termux:
                os.system('termux-vibrate -d 100 2>/dev/null &')
                os.system('termux-notification --title "📡 Range Test" --content "GPS point logged!" 2>/dev/null &')
        except:
            pass
    
    def export_files(self):
        """Export files to /sdcard/Download with timestamp"""
        is_termux = os.path.exists('/data/data/com.termux')
        
        if not is_termux:
            print("\n❌ Export only works on Termux/Android\n")
            return False
        
        download_dir = '/sdcard/Download'
        
        if not os.path.exists(download_dir):
            print(f"\n❌ /sdcard/Download/ not found\n")
            return False
        
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            files_to_export = [
                (self.json_file, f'rangetest_{timestamp}.json'),
                (self.kml_file, f'rangetest_{timestamp}.kml'),
                (self.csv_file, f'rangetest_{timestamp}.csv'),
                (self.geojson_file, f'rangetest_{timestamp}.geojson'),
                (self.html_file, f'rangetest_{timestamp}.html')
            ]
            
            exported = []
            
            for src_path, dest_name in files_to_export:
                if os.path.exists(src_path):
                    dest_path = os.path.join(download_dir, dest_name)
                    shutil.copy(src_path, dest_path)
                    exported.append(dest_name)
            
            if exported:
                print(f"\n✅ Exported {len(exported)} files to /sdcard/Download/:")
                for name in exported:
                    print(f"   {name}")
                print(f"\n📱 Access from File Manager → Download folder\n")
                return True
            else:
                print(f"\n❌ No files to export\n")
                return False
        
        except Exception as e:
            print(f"\n❌ Export error: {e}\n")
            return False
    
    def handle_command(self, cmd, parts):
        """Handle local commands"""
        try:
            if cmd in ['rangelogs', 'rl']:
                # Show logged files and stats
                print(f"\n📁 Range Test Logs")
                print("─"*60)
                
                files = [
                    (self.json_file, 'JSON'),
                    (self.kml_file, 'KML'),
                    (self.csv_file, 'CSV'),
                    (self.geojson_file, 'GeoJSON'),
                    (self.html_file, 'HTML Map')
                ]
                
                for filepath, filetype in files:
                    if os.path.exists(filepath):
                        size = os.path.getsize(filepath)
                        print(f"  {filetype:10s} {filepath}")
                        print(f"             Size: {size:,} bytes")
                
                # Count points
                try:
                    with open(self.json_file, 'r') as f:
                        data = json.load(f)
                        point_count = len(data.get('points', []))
                        print(f"\n  Total Points: {point_count}")
                except:
                    pass
                
                print("─"*60)
                print(f"\n💡 Commands:")
                print(f"   rangeexport (rex) - Export to /sdcard/Download/")
                print(f"   rangestatus       - Check GPS status\n")
            
            elif cmd in ['rangeexport', 'rex']:
                self.export_files()
            
            elif cmd == 'rangestatus':
                print(f"\n📍 GPS STATUS")
                print("─"*60)
                
                is_termux = os.path.exists('/data/data/com.termux')
                
                if not is_termux:
                    print("❌ Not running on Termux")
                    print("   GPS logging only works on Android with Termux\n")
                    return
                
                # Test GPS
                print("Testing GPS providers...\n")
                
                for provider in self.gps_providers:
                    print(f"Testing {provider}...", end=" ")
                    try:
                        result = subprocess.run(
                            ['termux-location', '-p', provider],
                            capture_output=True,
                            text=True,
                            timeout=8 if provider == 'gps' else 5,
                            env=os.environ.copy()
                        )
                        
                        if result.returncode == 0 and result.stdout:
                            data = json.loads(result.stdout.strip())
                            
                            if 'latitude' in data and 'longitude' in data:
                                lat = data.get('latitude')
                                lon = data.get('longitude')
                                acc = data.get('accuracy', 0)
                                
                                if lat and lon and (abs(lat) > 0.001 or abs(lon) > 0.001):
                                    print(f"✅ Working")
                                    print(f"   Lat: {lat:.6f}, Lon: {lon:.6f}")
                                    print(f"   Accuracy: ±{acc:.0f}m")
                                else:
                                    print("⚠️ Invalid coordinates")
                            else:
                                print("❌ No location data")
                        else:
                            print("❌ Failed")
                    
                    except subprocess.TimeoutExpired:
                        print("⏱️ Timeout")
                    except json.JSONDecodeError:
                        print("❌ Invalid data")
                    except Exception as e:
                        print(f"❌ Error: {e}")
                
                print("\n📱 GPS SETUP")
                print("   • Install: pkg install termux-api")
                print("   • Install: Termux:API app from F-Droid")
                print("   • Grant: Location permission in Settings")
                
                # Check storage
                print(f"\n📁 STORAGE STATUS")
                if os.path.exists('/sdcard/Download'):
                    print(f"✅ /sdcard/Download/ accessible")
                    
                    test_file = '/sdcard/Download/.rangetest_permtest'
                    try:
                        with open(test_file, 'w') as f:
                            f.write('test')
                        os.remove(test_file)
                        print(f"✅ Write permissions OK")
                    except:
                        print(f"❌ Write permission denied")
                        print(f"   Grant storage permission in Settings")
                else:
                    print(f"❌ /sdcard/Download/ not found")
                
                print("─"*60 + "\n")
        
        except Exception as e:
            print(f"[Range Client] ⚠️ Command handler error: {e}")
            import traceback
            traceback.print_exc()

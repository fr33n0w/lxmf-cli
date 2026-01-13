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
        self.description = "Range testing - incremental GPS logging with HTML map, KML, and JSON"
        
        # PHONE MODE - receives pings, logs GPS
        self.active_tests = {}  # Tests where WE receive pings
        
        # PC MODE - sends pings
        self.server_tests = {}
        self.server_threads = {}
        
    def extract_link_stats(self, message):
        """Extract RSSI, SNR, and link quality from LXMF message"""
        rssi = None
        snr = None
        q = None
        
        try:
            # Try to get packet from message
            if hasattr(message, 'packet') and message.packet:
                packet = message.packet
                
                # RSSI (Received Signal Strength Indicator)
                if hasattr(packet, 'rssi'):
                    rssi = packet.rssi
                
                # SNR (Signal-to-Noise Ratio)
                if hasattr(packet, 'snr'):
                    snr = packet.snr
                
                # Link quality
                if hasattr(packet, 'q'):
                    q = packet.q
            
            # Alternative: Try to get from transport receipt
            if hasattr(message, 'receipt') and message.receipt:
                receipt = message.receipt
                
                if rssi is None and hasattr(receipt, 'rssi'):
                    rssi = receipt.rssi
                
                if snr is None and hasattr(receipt, 'snr'):
                    snr = receipt.snr
                
                if q is None and hasattr(receipt, 'q'):
                    q = receipt.q
        
        except Exception as e:
            pass
        
        return rssi, snr, q
    
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
                        
                        # Extract RSSI and SNR from message
                        rssi, snr, q = self.extract_link_stats(message)
                        
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
                                'provider': provider,
                                'rssi': rssi,
                                'snr': snr,
                                'q': q
                            }
                            
                            # WRITE TO ALL FILES IMMEDIATELY
                            test = self.active_tests[source_hash]
                            self.append_to_json(test['json_path'], gps_point)
                            self.append_to_kml(test['kml_path'], gps_point, current == 1, current == total)
                            self.append_to_html(test['html_path'], gps_point, current == 1, current == total)
                            
                            print(f"[GPS] ✅ Logged: {lat:.6f}, {lon:.6f} (±{acc:.0f}m)")
                            if rssi is not None:
                                print(f"[RSSI] {rssi:.1f} dBm", end="")
                                if snr is not None:
                                    print(f" | SNR: {snr:.1f} dB", end="")
                                if q is not None:
                                    print(f" | Q: {q:.1f}%", end="")
                                print()
                            print(f"[GPS] 💾 Written to JSON, KML, HTML")
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
        html_file = f"rangetest_{safe_name}_{timestamp}.html"
        kml_file = f"rangetest_{safe_name}_{timestamp}.kml"
        
        json_path = os.path.join(log_dir, json_file)
        html_path = os.path.join(log_dir, html_file)
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
        
        # Initialize HTML map
        self.init_html_file(html_path, server_name)
        
        self.active_tests[server_hash] = {
            'count': count,
            'interval': interval,
            'received': 0,
            'start_time': time.time(),
            'json_path': json_path,
            'html_path': html_path,
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
        print(f"   {html_file}")
        print(f"{'─'*70}\n")
    
    def init_kml_file(self, filepath, server_name):
        """Initialize KML file with header"""
        kml_header = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Range Test - {server_name}</name>
    <description>LXMF Range Test - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</description>
    
    <Style id="startPoint">
      <IconStyle>
        <color>ff00ff00</color>
        <scale>1.2</scale>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/paddle/grn-circle.png</href>
        </Icon>
      </IconStyle>
    </Style>
    
    <Style id="normalPoint">
      <IconStyle>
        <color>ff0078d4</color>
        <scale>0.8</scale>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/paddle/blu-circle.png</href>
        </Icon>
      </IconStyle>
    </Style>
    
    <Style id="endPoint">
      <IconStyle>
        <color>ff0000ff</color>
        <scale>1.2</scale>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/paddle/red-circle.png</href>
        </Icon>
      </IconStyle>
    </Style>
    
    <Style id="pathStyle">
      <LineStyle>
        <color>ffff0000</color>
        <width>4</width>
      </LineStyle>
    </Style>
    
    <Folder>
      <name>GPS Points</name>
<!-- POINTS_START -->
'''
        
        with open(filepath, 'w') as f:
            f.write(kml_header)
    
    def append_to_kml(self, kml_path, gps_point, is_first, is_last):
        """Append GPS point to KML file"""
        try:
            # Determine style
            if is_first:
                style = "startPoint"
                name = f"START - Ping #{gps_point['index']}"
            elif is_last:
                style = "endPoint"
                name = f"END - Ping #{gps_point['index']}"
            else:
                style = "normalPoint"
                name = f"Ping #{gps_point['index']}"
            
            # Create placemark
            placemark = f'''      <Placemark>
        <name>{name}</name>
        <description><![CDATA[
          <b>Ping #{gps_point['index']}</b><br/>
          Time: {gps_point['time']}<br/>
          Speed: {gps_point['speed']:.1f} km/h<br/>
          Altitude: {gps_point['altitude']:.1f} m<br/>
          Accuracy: ±{gps_point['accuracy']:.0f} m<br/>
          Provider: {gps_point['provider']}<br/>
          Lat: {gps_point['lat']:.6f}<br/>
          Lon: {gps_point['lon']:.6f}
        ]]></description>
        <styleUrl>#{style}</styleUrl>
        <Point>
          <coordinates>{gps_point['lon']:.6f},{gps_point['lat']:.6f},{gps_point['altitude']:.1f}</coordinates>
        </Point>
      </Placemark>
'''
            
            # Read file
            with open(kml_path, 'r') as f:
                content = f.read()
            
            # Insert placemark before POINTS_START marker
            if '<!-- POINTS_START -->' in content:
                content = content.replace('<!-- POINTS_START -->', placemark + '<!-- POINTS_START -->')
            
            # Write back
            with open(kml_path, 'w') as f:
                f.write(content)
            
            # If last point, finalize KML
            if is_last:
                self.finalize_kml(kml_path)
        
        except Exception as e:
            print(f"[KML] ⚠️ Error: {e}")
    
    def finalize_kml(self, kml_path):
        """Finalize KML file with path and closing tags"""
        try:
            # Read current file
            with open(kml_path, 'r') as f:
                content = f.read()
            
            # Extract all coordinates from placemarks
            coords = []
            import re
            coord_matches = re.findall(r'<coordinates>([-\d.]+),([-\d.]+),([-\d.]+)</coordinates>', content)
            
            if coord_matches:
                # Build path coordinates
                coord_str = '\n            '.join([f"{lon},{lat},{alt}" for lon, lat, alt in coord_matches])
                
                # Create path placemark
                path_placemark = f'''      <Placemark>
        <name>Path</name>
        <description>Complete route</description>
        <styleUrl>#pathStyle</styleUrl>
        <LineString>
          <tessellate>1</tessellate>
          <coordinates>
            {coord_str}
          </coordinates>
        </LineString>
      </Placemark>
'''
                
                # Add path before closing folder
                content = content.replace('<!-- POINTS_START -->', path_placemark + '<!-- POINTS_START -->')
            
            # Add closing tags
            closing = '''    </Folder>
  </Document>
</kml>'''
            
            content += closing
            
            # Write final file
            with open(kml_path, 'w') as f:
                f.write(content)
        
        except Exception as e:
            print(f"[KML] ⚠️ Finalize error: {e}")
    
    def init_html_file(self, filepath, server_name):
        """Initialize self-contained HTML map file with enhanced styling"""
        html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Range Test - {server_name}</title>
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: Arial, sans-serif;
        }}
        #map {{
            position: absolute;
            top: 0;
            bottom: 140px;
            width: 100%;
        }}
        #info {{
            position: absolute;
            bottom: 0;
            width: 100%;
            height: 140px;
            background: rgba(255, 255, 255, 0.95);
            padding: 15px;
            box-sizing: border-box;
            border-top: 3px solid #0078d4;
            overflow-y: auto;
        }}
        .stat {{
            display: inline-block;
            margin-right: 20px;
            margin-bottom: 5px;
            font-size: 14px;
        }}
        .stat-label {{
            font-weight: bold;
            color: #0078d4;
        }}
        .legend {{
            background: white;
            padding: 10px;
            border-radius: 5px;
            box-shadow: 0 1px 5px rgba(0,0,0,0.4);
        }}
        .legend-item {{
            margin: 5px 0;
            font-size: 12px;
        }}
        .signal-bar {{
            display: inline-block;
            width: 60px;
            height: 8px;
            border-radius: 4px;
            margin-left: 5px;
        }}
        @media (max-width: 600px) {{
            #info {{
                height: 160px;
            }}
            .stat {{
                display: block;
                margin: 3px 0;
            }}
        }}
    </style>
    
    <!-- Leaflet CSS -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    
    <!-- Leaflet JS -->
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body>
    <div id="map"></div>
    <div id="info">
        <div class="stat"><span class="stat-label">Server:</span> <span id="server">{server_name}</span></div>
        <div class="stat"><span class="stat-label">Started:</span> <span id="start">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span></div>
        <div class="stat"><span class="stat-label">Points:</span> <span id="points">0</span></div>
        <div class="stat"><span class="stat-label">Distance:</span> <span id="distance">0 km</span></div>
        <div class="stat"><span class="stat-label">Max Speed:</span> <span id="maxspeed">0 km/h</span></div>
        <div class="stat"><span class="stat-label">Avg RSSI:</span> <span id="avgrssi">N/A</span></div>
        <div class="stat"><span class="stat-label">Avg SNR:</span> <span id="avgsnr">N/A</span></div>
        <div class="stat"><span class="stat-label">Last Update:</span> <span id="lastupdate">-</span></div>
    </div>

    <script>
        // Initialize map - default center (will auto-adjust to points)
        var map = L.map('map').setView([45.0, 7.0], 13);
        
        // Add OpenStreetMap tiles
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            maxZoom: 19,
            attribution: '© OpenStreetMap contributors'
        }}).addTo(map);
        
        // Initialize layers
        var polyline = L.polyline([], {{
            color: 'red',
            weight: 4,
            opacity: 0.7
        }}).addTo(map);
        
        var markers = [];
        var gpsPoints = [];
        var maxSpeed = 0;
        var rssiValues = [];
        var snrValues = [];
        
        // Function to get signal quality color based on RSSI
        function getSignalColor(rssi) {{
            if (rssi === null || rssi === undefined) return '#999999';
            if (rssi >= -60) return '#00ff00';  // Excellent (green)
            if (rssi >= -70) return '#7fff00';  // Very Good (lime)
            if (rssi >= -80) return '#ffff00';  // Good (yellow)
            if (rssi >= -90) return '#ffa500';  // Fair (orange)
            if (rssi >= -100) return '#ff6600'; // Poor (dark orange)
            return '#ff0000';                    // Very Poor (red)
        }}
        
        // Function to get marker size based on signal quality
        function getMarkerSize(rssi) {{
            if (rssi === null || rssi === undefined) return 10;
            if (rssi >= -60) return 14;
            if (rssi >= -70) return 12;
            if (rssi >= -80) return 10;
            return 8;
        }}
        
        // Create custom marker with signal color
        function createSignalIcon(rssi, isStart, isEnd) {{
            if (isStart) {{
                return L.divIcon({{
                    className: 'custom-marker',
                    html: '<div style="background-color: #00ff00; width: 16px; height: 16px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 6px rgba(0,0,0,0.6);"></div>',
                    iconSize: [16, 16],
                    iconAnchor: [8, 8]
                }});
            }}
            if (isEnd) {{
                return L.divIcon({{
                    className: 'custom-marker',
                    html: '<div style="background-color: #ff0000; width: 16px; height: 16px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 6px rgba(0,0,0,0.6);"></div>',
                    iconSize: [16, 16],
                    iconAnchor: [8, 8]
                }});
            }}
            
            var color = getSignalColor(rssi);
            var size = getMarkerSize(rssi);
            return L.divIcon({{
                className: 'custom-marker',
                html: '<div style="background-color: ' + color + '; width: ' + size + 'px; height: ' + size + 'px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 4px rgba(0,0,0,0.5);"></div>',
                iconSize: [size, size],
                iconAnchor: [size/2, size/2]
            }});
        }}
        
        // Enhanced legend with signal quality
        var legend = L.control({{position: 'topright'}});
        legend.onAdd = function(map) {{
            var div = L.DomUtil.create('div', 'legend');
            div.innerHTML = '<div style="font-weight: bold; margin-bottom: 5px;">Range Test</div>' +
                          '<div class="legend-item">🟢 Start Point</div>' +
                          '<div class="legend-item">🔴 End Point</div>' +
                          '<div class="legend-item">━━ Path</div>' +
                          '<div style="margin-top: 10px; font-weight: bold; font-size: 11px;">Signal Quality (RSSI):</div>' +
                          '<div class="legend-item" style="font-size: 11px;">🟢 Excellent (≥-60 dBm)</div>' +
                          '<div class="legend-item" style="font-size: 11px;">🟡 Good (-70 to -80 dBm)</div>' +
                          '<div class="legend-item" style="font-size: 11px;">🟠 Fair (-80 to -90 dBm)</div>' +
                          '<div class="legend-item" style="font-size: 11px;">🔴 Poor (≤-90 dBm)</div>';
            return div;
        }};
        legend.addTo(map);
        
        // Haversine distance calculation
        function calculateDistance(lat1, lon1, lat2, lon2) {{
            var R = 6371; // Earth radius in km
            var dLat = (lat2 - lat1) * Math.PI / 180;
            var dLon = (lon2 - lon1) * Math.PI / 180;
            var a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                    Math.sin(dLon/2) * Math.sin(dLon/2);
            var c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
            return R * c;
        }}
        
        // Function to get signal bar HTML
        function getSignalBar(value, min, max, label) {{
            if (value === null || value === undefined) return '';
            var percent = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
            var color = getSignalColor(value);
            return '<div style="margin: 5px 0;">' +
                   '<span style="font-size: 11px;">' + label + ': ' + value.toFixed(1) + '</span>' +
                   '<div style="background: #ddd; width: 100px; height: 6px; display: inline-block; margin-left: 5px; border-radius: 3px; vertical-align: middle;">' +
                   '<div style="background: ' + color + '; width: ' + percent + '%; height: 100%; border-radius: 3px;"></div>' +
                   '</div></div>';
        }}
        
        // Add point function with enhanced signal data
        function addPoint(lat, lon, index, time, speed, accuracy, rssi, snr, q) {{
            var point = [lat, lon];
            gpsPoints.push(point);
            
            // Track signal stats
            if (rssi !== null && rssi !== undefined) {{
                rssiValues.push(rssi);
            }}
            if (snr !== null && snr !== undefined) {{
                snrValues.push(snr);
            }}
            
            // Update polyline with gradient based on signal quality
            polyline.setLatLngs(gpsPoints);
            
            // Track max speed
            if (speed > maxSpeed) {{
                maxSpeed = speed;
            }}
            
            // Create marker with signal-based coloring
            var isStart = (index === 1);
            var isEnd = false; // Will be set later
            var icon = createSignalIcon(rssi, isStart, isEnd);
            var marker = L.marker(point, {{icon: icon}}).addTo(map);
            
            // Enhanced popup with signal data
            var popupContent = '<div style="min-width: 200px;"><b>Ping #' + index + '</b><br>' +
                'Time: ' + time + '<br>' +
                'Speed: ' + speed.toFixed(1) + ' km/h<br>' +
                'Accuracy: ±' + accuracy.toFixed(0) + 'm<br>';
            
            if (rssi !== null && rssi !== undefined) {{
                popupContent += getSignalBar(rssi, -110, -50, 'RSSI') + '<br>';
            }}
            if (snr !== null && snr !== undefined) {{
                popupContent += getSignalBar(snr, -10, 20, 'SNR') + '<br>';
            }}
            if (q !== null && q !== undefined) {{
                popupContent += 'Link Quality: ' + q.toFixed(1) + '%<br>';
            }}
            
            popupContent += 'Lat: ' + lat.toFixed(6) + '<br>' +
                'Lon: ' + lon.toFixed(6) + '</div>';
            
            marker.bindPopup(popupContent);
            markers.push(marker);
            
            // Calculate total distance
            var totalDist = 0;
            for (var i = 1; i < gpsPoints.length; i++) {{
                totalDist += calculateDistance(
                    gpsPoints[i-1][0], gpsPoints[i-1][1],
                    gpsPoints[i][0], gpsPoints[i][1]
                );
            }}
            
            // Calculate average RSSI and SNR
            var avgRssi = rssiValues.length > 0 ? 
                rssiValues.reduce((a, b) => a + b, 0) / rssiValues.length : null;
            var avgSnr = snrValues.length > 0 ? 
                snrValues.reduce((a, b) => a + b, 0) / snrValues.length : null;
            
            // Update stats
            document.getElementById('points').textContent = gpsPoints.length;
            document.getElementById('distance').textContent = totalDist.toFixed(2) + ' km';
            document.getElementById('maxspeed').textContent = maxSpeed.toFixed(1) + ' km/h';
            document.getElementById('avgrssi').textContent = avgRssi !== null ? avgRssi.toFixed(1) + ' dBm' : 'N/A';
            document.getElementById('avgsnr').textContent = avgSnr !== null ? avgSnr.toFixed(1) + ' dB' : 'N/A';
            document.getElementById('lastupdate').textContent = time;
            
            // Fit map to show all points with padding
            if (gpsPoints.length > 0) {{
                map.fitBounds(polyline.getBounds(), {{padding: [50, 50]}});
            }}
        }}
        
        // Mark end point
        function markEndPoint() {{
            if (markers.length > 0) {{
                // Remove last marker and replace with end icon
                map.removeLayer(markers[markers.length - 1]);
                var lastPoint = gpsPoints[gpsPoints.length - 1];
                var endMarker = L.marker(lastPoint, {{icon: createSignalIcon(null, false, true)}}).addTo(map);
                endMarker.bindPopup('<b>END</b><br>Final Position<br>Total Points: ' + gpsPoints.length);
                markers[markers.length - 1] = endMarker;
            }}
        }}
        
        // GPS POINTS DATA WILL BE INSERTED HERE
        // POINTS_START
'''
        
        with open(filepath, 'w') as f:
            f.write(html)
    
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
    
    def append_to_html(self, html_path, gps_point, is_first, is_last):
        """Append GPS point to HTML file"""
        try:
            # Create JavaScript line to add point with signal data
            rssi = gps_point.get('rssi')
            snr = gps_point.get('snr')
            q = gps_point.get('q')
            
            # Format None values as null for JavaScript
            rssi_str = str(rssi) if rssi is not None else 'null'
            snr_str = str(snr) if snr is not None else 'null'
            q_str = str(q) if q is not None else 'null'
            
            js_line = f"        addPoint({gps_point['lat']}, {gps_point['lon']}, {gps_point['index']}, '{gps_point['time']}', {gps_point['speed']:.1f}, {gps_point['accuracy']:.0f}, {rssi_str}, {snr_str}, {q_str});\n"
            
            # Read file
            with open(html_path, 'r') as f:
                content = f.read()
            
            # Insert point before POINTS_START marker
            if '// POINTS_START' in content:
                content = content.replace('// POINTS_START', js_line + '// POINTS_START')
            
            # Write back
            with open(html_path, 'w') as f:
                f.write(content)
            
            # If last point, finalize
            if is_last:
                self.finalize_html(html_path)
        
        except Exception as e:
            print(f"[HTML] ⚠️ Error: {e}")
    
    def finalize_html(self, html_path):
        """Finalize HTML file"""
        try:
            with open(html_path, 'r') as f:
                content = f.read()
            
            # Add end marker call
            end_js = "\n        markEndPoint();\n"
            content = content.replace('// POINTS_START', end_js + '// POINTS_START')
            
            # Close script and body tags
            closing = '''
    </script>
</body>
</html>'''
            
            content += closing
            
            with open(html_path, 'w') as f:
                f.write(content)
        
        except Exception as e:
            print(f"[HTML] ⚠️ Finalize error: {e}")
    
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
        print(f"   {os.path.basename(test['html_path'])}")
        
        # Auto-copy to /sdcard/Download/ if on Termux
        is_termux = os.path.exists('/data/data/com.termux')
        if is_termux:
            download_dir = '/sdcard/Download'
            if os.path.exists(download_dir):
                try:
                    import shutil
                    
                    # Copy all three files
                    for src_path in [test['json_path'], test['kml_path'], test['html_path']]:
                        filename = os.path.basename(src_path)
                        dest_path = os.path.join(download_dir, filename)
                        shutil.copy2(src_path, dest_path)
                    
                    print(f"{'─'*70}")
                    print(f"✅ Auto-copied to /sdcard/Download/")
                    print(f"{'─'*70}")
                    print(f"\n📱 Access files in:")
                    print(f"   • File Manager → Download folder")
                    print(f"   • Share from Download folder to apps")
                except Exception as e:
                    print(f"{'─'*70}")
                    print(f"⚠️ Auto-copy failed: {e}")
                    print(f"\n💡 Manual copy:")
                    print(f"   cp {test['json_path']} /sdcard/Download/")
                    print(f"   cp {test['kml_path']} /sdcard/Download/")
                    print(f"   cp {test['html_path']} /sdcard/Download/")
            else:
                print(f"{'─'*70}")
                print(f"⚠️ /sdcard/Download/ not found")
                print(f"\n💡 Copy manually if needed")
        else:
            print(f"{'─'*70}")
        
        print(f"\n💡 Open HTML map:")
        print(f"   termux-open {test['html_path']}")
        print(f"\n💡 Import KML to maps:")
        print(f"   Open in Google Earth, OsmAnd, or other mapping app")
        print(f"\n🗺️ All formats ready!\n")
        
        del self.active_tests[server_hash]
    
    def finalize_test(self, server_hash):
        """PHONE - Stop early"""
        if server_hash not in self.active_tests:
            return
        
        test = self.active_tests[server_hash]
        
        # Finalize all files
        self.finalize_html(test['html_path'])
        self.finalize_kml(test['kml_path'])
        
        print(f"\n⚠️ Test stopped early")
        print(f"📊 Received: {test['received']}/{test['count']}")
        print(f"💾 All files saved (JSON, KML, HTML)")
        
        # Auto-copy to /sdcard/Download/ if on Termux
        is_termux = os.path.exists('/data/data/com.termux')
        if is_termux:
            download_dir = '/sdcard/Download'
            if os.path.exists(download_dir):
                try:
                    import shutil
                    
                    # Copy all three files
                    for src_path in [test['json_path'], test['kml_path'], test['html_path']]:
                        filename = os.path.basename(src_path)
                        dest_path = os.path.join(download_dir, filename)
                        shutil.copy2(src_path, dest_path)
                    
                    print(f"\n✅ Auto-copied to /sdcard/Download/\n")
                except Exception as e:
                    print(f"\n⚠️ Auto-copy failed: {e}\n")
        
        del self.active_tests[server_hash]
    
    def stop_server(self, phone_hash):
        """PC - Stop sending"""
        if phone_hash in self.server_tests:
            self.server_tests[phone_hash]['stop_flag'].set()
            contact = self.client.format_contact_display_short(phone_hash)
            print(f"\n⚠️ Stopping ping sequence for {contact}\n")
            self.client.send_message(phone_hash, "⚠️ Test stopped by server")
    
    def get_gps_location(self):
        """Get GPS location"""
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
                
                except (subprocess.TimeoutExpired, json.JSONDecodeError):
                    continue
                except Exception:
                    continue
            
            return None
        
        except Exception:
            return None
    
    def notify_ping(self, current, total):
        """Notify user of ping received"""
        is_termux = os.path.exists('/data/data/com.termux')
        
        try:
            if is_termux:
                os.system('termux-vibrate -d 100 2>/dev/null &')
                os.system(f'termux-notification --title "📡 Ping {current}/{total}" --content "GPS + Signal data saved!" 2>/dev/null &')
        except:
            pass
    
    def handle_command(self, cmd, parts):
        """Handle local commands"""
        if cmd == 'rangetest':
            if self.server_tests:
                print("\n🏠 PC MODE - Sending Pings")
                print("─"*70)
                for h, c in self.server_tests.items():
                    contact = self.client.format_contact_display_short(h)
                    print(f"  {contact}: {c['current']}/{c['count']} sent")
                print("─"*70 + "\n")
            elif self.active_tests:
                print("\n📱 PHONE MODE - Logging GPS")
                print("─"*70)
                for h, c in self.active_tests.items():
                    contact = self.client.format_contact_display_short(h)
                    print(f"  {contact}: {c['received']}/{c['count']} received")
                    print(f"     JSON: {os.path.basename(c['json_path'])}")
                    print(f"     KML:  {os.path.basename(c['kml_path'])}")
                    print(f"     HTML: {os.path.basename(c['html_path'])}")
                print("─"*70 + "\n")
            else:
                print("\n📡 No active tests\n")
        
        elif cmd == 'rangestatus':
            print("\n📍 GPS STATUS")
            print("─"*70)
            gps = self.get_gps_location()
            if gps:
                print(f"✅ GPS Available")
                print(f"   Latitude:  {gps['latitude']:.6f}")
                print(f"   Longitude: {gps['longitude']:.6f}")
                print(f"   Accuracy:  ±{gps.get('accuracy', 0):.0f}m")
                print(f"   Provider:  {gps.get('provider', 'unknown')}")
                if gps.get('speed', 0) > 0:
                    print(f"   Speed:     {gps['speed']:.1f} km/h")
            else:
                print("❌ GPS Unavailable")
                print("\n   For Termux:")
                print("   • pkg install termux-api")
                print("   • Install Termux:API from F-Droid")
                print("   • Grant location permission in Settings")
            print("─"*70 + "\n")
        
        elif cmd == 'rangegetlogs':
            log_dir = os.path.join(self.client.storage_path, "rangetest_logs")
            if os.path.exists(log_dir):
                files = sorted([f for f in os.listdir(log_dir) if f.endswith(('.html', '.json', '.kml'))], reverse=True)
                if files:
                    print("\n📁 Range Test Logs:")
                    print("─"*70)
                    for f in files:
                        path = os.path.join(log_dir, f)
                        size = os.path.getsize(path)
                        print(f"  {f} ({size:,} bytes)")
                    print("─"*70)
                    print(f"\nLog directory: {log_dir}")
                    print(f"\n💡 Copy to shared storage:")
                    print(f"   cp {log_dir}/*.{{html,json,kml}} /sdcard/Download/")
                    print(f"\n💡 Open latest map:")
                    latest_html = next((f for f in files if f.endswith('.html')), None)
                    if latest_html:
                        print(f"   termux-open {log_dir}/{latest_html}")
                    print(f"\n💡 Import KML to mapping apps:")
                    latest_kml = next((f for f in files if f.endswith('.kml')), None)
                    if latest_kml:
                        print(f"   Open {latest_kml} in Google Earth, OsmAnd, etc.")
                    print(f"\n💡 Share file:")
                    if latest_html:
                        print(f"   termux-share {log_dir}/{latest_html}\n")
                else:
                    print("\n📁 No logs found\n")
            else:
                print("\n📁 No logs directory found\n")
        
        elif cmd == 'rangestop':
            if len(parts) < 2:
                print("\n💡 Usage: rangestop <contact>\n")
                print("Example:")
                print("  rangestop HomePC")
                print("  rangestop 1\n")
            else:
                target = ' '.join(parts[1:])
                dest_hash = self.client.resolve_contact_or_hash(target)
                if dest_hash:
                    if dest_hash in self.server_tests:
                        self.stop_server(dest_hash)
                        print(f"✅ Stopped sending pings")
                    elif dest_hash in self.active_tests:
                        self.finalize_test(dest_hash)
                        self.client.send_message(dest_hash, "⚠️ Test stopped by mobile")
                        print(f"✅ Test stopped, files saved")
                    else:
                        print(f"❌ No active test with {target}")
                else:
                    print(f"❌ Unknown contact: {target}")

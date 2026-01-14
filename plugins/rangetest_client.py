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
        self.commands = ['rangelogs', 'rl', 'rangeexport', 'rex', 'rangestatus', 'rangeclear']
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
        """Initialize HTML map file with path and signal-based coloring"""
        html = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Range Test Coverage Map</title>
    <style>
        body { margin: 0; padding: 0; font-family: Arial, sans-serif; }
        #map { position: absolute; top: 0; bottom: 140px; width: 100%; }
        #info {
            position: absolute; bottom: 0; width: 100%; height: 140px;
            background: rgba(255, 255, 255, 0.95); padding: 15px;
            box-sizing: border-box; border-top: 3px solid #0078d4;
            overflow-y: auto;
        }
        .stat { display: inline-block; margin-right: 20px; margin-bottom: 5px; font-size: 14px; }
        .stat-label { font-weight: bold; color: #0078d4; }
        .legend {
            background: white;
            padding: 10px;
            border-radius: 5px;
            box-shadow: 0 1px 5px rgba(0,0,0,0.4);
        }
        .legend-item {
            margin: 5px 0;
            font-size: 12px;
        }
        @media (max-width: 600px) {
            #info { height: 160px; }
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
        <div class="stat"><span class="stat-label">Distance:</span> <span id="distance">0 km</span></div>
        <div class="stat"><span class="stat-label">Avg RSSI:</span> <span id="avgrssi">N/A</span></div>
        <div class="stat"><span class="stat-label">Avg SNR:</span> <span id="avgsnr">N/A</span></div>
        <div class="stat"><span class="stat-label">Max Speed:</span> <span id="maxspeed">0 km/h</span></div>
        <div class="stat"><span class="stat-label">Last Update:</span> <span id="lastupdate">-</span></div>
    </div>

    <script>
        var map = L.map('map').setView([45.0, 7.0], 13);
        
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '© OpenStreetMap contributors'
        }).addTo(map);
        
        var markers = [];
        var gpsPoints = [];
        var polyline = null;
        var rssiValues = [];
        var snrValues = [];
        var maxSpeed = 0;
        
        function getSignalColor(rssi) {
            if (rssi === null || rssi === undefined) return '#0078d4';  // Blue if no RSSI
            if (rssi >= -60) return '#00ff00';  // Excellent (green)
            if (rssi >= -70) return '#7fff00';  // Very Good (lime)
            if (rssi >= -80) return '#ffff00';  // Good (yellow)
            if (rssi >= -90) return '#ffa500';  // Fair (orange)
            if (rssi >= -100) return '#ff6600'; // Poor (dark orange)
            return '#ff0000';                    // Very Poor (red)
        }
        
        function getMarkerSize(rssi) {
            if (rssi === null || rssi === undefined) return 10;
            if (rssi >= -60) return 14;
            if (rssi >= -70) return 12;
            if (rssi >= -80) return 10;
            return 8;
        }
        
        function createSignalIcon(rssi, isStart, isEnd) {
            if (isStart) {
                return L.divIcon({
                    className: 'custom-marker',
                    html: '<div style="background-color: #00ff00; width: 16px; height: 16px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 6px rgba(0,0,0,0.6);"></div>',
                    iconSize: [16, 16],
                    iconAnchor: [8, 8]
                });
            }
            if (isEnd) {
                return L.divIcon({
                    className: 'custom-marker',
                    html: '<div style="background-color: #ff0000; width: 16px; height: 16px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 6px rgba(0,0,0,0.6);"></div>',
                    iconSize: [16, 16],
                    iconAnchor: [8, 8]
                });
            }
            
            var color = getSignalColor(rssi);
            var size = getMarkerSize(rssi);
            return L.divIcon({
                className: 'custom-marker',
                html: '<div style="background-color: ' + color + '; width: ' + size + 'px; height: ' + size + 'px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 4px rgba(0,0,0,0.5);"></div>',
                iconSize: [size, size],
                iconAnchor: [size/2, size/2]
            });
        }
        
        var legend = L.control({position: 'topright'});
        legend.onAdd = function(map) {
            var div = L.DomUtil.create('div', 'legend');
            div.innerHTML = '<div style="font-weight: bold; margin-bottom: 5px;">Range Test</div>' +
                          '<div class="legend-item">🟢 Start Point</div>' +
                          '<div class="legend-item">🔴 End Point</div>' +
                          '<div class="legend-item">━━ Path</div>' +
                          '<div style="margin-top: 10px; font-weight: bold; font-size: 11px;">Signal Quality (RSSI):</div>' +
                          '<div class="legend-item" style="font-size: 11px;">🟢 Excellent (≥-60 dBm)</div>' +
                          '<div class="legend-item" style="font-size: 11px;">🟡 Good (-70 to -80 dBm)</div>' +
                          '<div class="legend-item" style="font-size: 11px;">🟠 Fair (-80 to -90 dBm)</div>' +
                          '<div class="legend-item" style="font-size: 11px;">🔴 Poor (≤-90 dBm)</div>' +
                          '<div class="legend-item" style="font-size: 11px;">🔵 No Signal Data</div>';
            return div;
        };
        legend.addTo(map);
        
        function calculateDistance(lat1, lon1, lat2, lon2) {
            var R = 6371; // Earth radius in km
            var dLat = (lat2 - lat1) * Math.PI / 180;
            var dLon = (lon2 - lon1) * Math.PI / 180;
            var a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                    Math.sin(dLon/2) * Math.sin(dLon/2);
            var c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
            return R * c;
        }
        
        function getSignalBar(value, min, max, label) {
            if (value === null || value === undefined) return '';
            var percent = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
            var color = getSignalColor(value);
            return '<div style="margin: 5px 0;">' +
                   '<span style="font-size: 11px;">' + label + ': ' + value.toFixed(1) + '</span>' +
                   '<div style="background: #ddd; width: 100px; height: 6px; display: inline-block; margin-left: 5px; border-radius: 3px; vertical-align: middle;">' +
                   '<div style="background: ' + color + '; width: ' + percent + '%; height: 100%; border-radius: 3px;"></div>' +
                   '</div></div>';
        }
        
        function addPoint(lat, lon, index, time, speed, accuracy, altitude, provider, rssi, snr, q) {
            var point = [lat, lon];
            gpsPoints.push(point);
            
            var isStart = (index === 1);
            var isEnd = false; // Will be set later with markEndPoint()
            
            // Track signal stats
            if (rssi !== null && rssi !== undefined) {
                rssiValues.push(rssi);
            }
            if (snr !== null && snr !== undefined) {
                snrValues.push(snr);
            }
            
            // Track max speed
            if (speed > maxSpeed) {
                maxSpeed = speed;
            }
            
            // Update or create polyline (path)
            if (polyline) {
                map.removeLayer(polyline);
            }
            polyline = L.polyline(gpsPoints, {
                color: 'red',
                weight: 4,
                opacity: 0.7
            }).addTo(map);
            
            // Create marker with signal-based coloring
            var icon = createSignalIcon(rssi, isStart, isEnd);
            var marker = L.marker(point, {icon: icon}).addTo(map);
            
            // Enhanced popup with ALL GPS and signal data
            var popupContent = '<div style="min-width: 200px;"><b>Point #' + index + '</b><br>' +
                'Time: ' + time + '<br>' +
                'Latitude: ' + lat.toFixed(6) + '<br>' +
                'Longitude: ' + lon.toFixed(6) + '<br>' +
                'Altitude: ' + altitude.toFixed(1) + ' m<br>' +
                'Speed: ' + speed.toFixed(1) + ' km/h<br>' +
                'Accuracy: ±' + accuracy.toFixed(0) + ' m<br>' +
                'Provider: ' + provider + '<br>';
            
            if (rssi !== null && rssi !== undefined) {
                popupContent += getSignalBar(rssi, -110, -50, 'RSSI') + '<br>';
            }
            if (snr !== null && snr !== undefined) {
                popupContent += getSignalBar(snr, -10, 20, 'SNR') + '<br>';
            }
            if (q !== null && q !== undefined) {
                popupContent += 'Link Quality: ' + q.toFixed(1) + '%<br>';
            }
            
            popupContent += '</div>';
            
            marker.bindPopup(popupContent);
            markers.push(marker);
            
            // Calculate total distance
            var totalDist = 0;
            for (var i = 1; i < gpsPoints.length; i++) {
                totalDist += calculateDistance(
                    gpsPoints[i-1][0], gpsPoints[i-1][1],
                    gpsPoints[i][0], gpsPoints[i][1]
                );
            }
            
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
            if (gpsPoints.length > 0) {
                map.fitBounds(polyline.getBounds(), {padding: [50, 50]});
            }
        }
        
        function markEndPoint() {
            if (markers.length > 0) {
                // Remove last marker and replace with end icon
                map.removeLayer(markers[markers.length - 1]);
                var lastPoint = gpsPoints[gpsPoints.length - 1];
                var endMarker = L.marker(lastPoint, {icon: createSignalIcon(null, false, true)}).addTo(map);
                endMarker.bindPopup('<b>END</b><br>Final Position<br>Total Points: ' + gpsPoints.length);
                markers[markers.length - 1] = endMarker;
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
                
                # Get GPS location (satellite first, network fallback)
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
                        print(f"[Signal] RSSI: {rssi:.1f} dBm", end="")
                        if snr is not None:
                            print(f" | SNR: {snr:.1f} dB", end="")
                        if q is not None:
                            print(f" | Q: {q:.1f}%", end="")
                        print()
                    
                    # Notify
                    self.notify_saved()
                else:
                    print(f"[GPS] ❌ GPS unavailable - point NOT logged")
                
                print(f"{'='*60}\n")
                
                return False  # Let message be processed normally
        
        except Exception as e:
            print(f"[Range Client] ⚠️ Message handler error: {e}")
            import traceback
            traceback.print_exc()
        
        return False
    
    def get_gps_location(self):
        """Get GPS location - satellite first (10s), fallback to network (3s)"""
        is_termux = os.path.exists('/data/data/com.termux')
        
        if not is_termux:
            return None
        
        # Strategy 1: Try GPS (satellite) first with 10 second timeout
        print("[GPS] Attempt 1: GPS satellite (10s timeout)...")
        gps = self.try_gps_provider('gps', timeout=10)
        if gps:
            return gps
        
        # Strategy 2: Fallback to network provider with 3 second timeout
        print("[GPS] Attempt 2: Network provider (3s timeout)...")
        gps = self.try_gps_provider('network', timeout=3)
        if gps:
            return gps
        
        # No GPS available
        return None
    
    def try_gps_provider(self, provider, timeout=5):
        """Try to get GPS from specific provider"""
        try:
            cmd = ['termux-location', '-p', provider, '-r', 'once']
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=os.environ.copy()
            )
            
            if result.returncode == 0 and result.stdout.strip():
                try:
                    data = json.loads(result.stdout.strip())
                    
                    if 'latitude' in data and 'longitude' in data:
                        lat = data.get('latitude')
                        lon = data.get('longitude')
                        
                        # Validate coordinates (must be non-zero)
                        if lat and lon and (abs(lat) > 0.001 or abs(lon) > 0.001):
                            # Add provider info
                            if 'provider' not in data:
                                data['provider'] = provider
                            
                            print(f"[GPS] ✅ Got location from {data['provider']}")
                            return data
                except json.JSONDecodeError as e:
                    print(f"[GPS] ⚠️ JSON decode error: {e}")
        
        except subprocess.TimeoutExpired:
            print(f"[GPS] ⏱️ {provider} timeout")
        except FileNotFoundError:
            print(f"[GPS] ❌ termux-location not found")
        except Exception as e:
            print(f"[GPS] ⚠️ Error: {e}")
        
        return None
    
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
            
            # Get current point index
            try:
                with open(self.json_file, 'r') as f:
                    data = json.load(f)
                    point_index = len(data['points']) + 1
            except:
                point_index = 1
            
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
            self.append_to_html(point_index, date_str, time_str, lat, lon, 
                              accuracy, speed, altitude, provider, rssi, snr, q)
        
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
    
    def append_to_html(self, index, date, time, lat, lon, accuracy, speed, altitude, provider, rssi, snr, q):
        """Append point to HTML file"""
        try:
            # Format None values as null for JavaScript
            rssi_str = str(rssi) if rssi is not None else 'null'
            snr_str = str(snr) if snr is not None else 'null'
            q_str = str(q) if q is not None else 'null'
            
            # Create JavaScript line with ALL parameters
            js_line = f"        addPoint({lat}, {lon}, {index}, '{time}', {speed:.1f}, {accuracy:.0f}, {altitude:.1f}, '{provider}', {rssi_str}, {snr_str}, {q_str});\n"
            
            with open(self.html_file, 'r') as f:
                content = f.read()
            
            # Insert point before POINTS_START marker
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
                        
                        if point_count > 0:
                            # Show last point info
                            last_point = data['points'][-1]
                            print(f"  Last Point: {last_point.get('date')} {last_point.get('time')}")
                            print(f"              {last_point.get('latitude'):.6f}, {last_point.get('longitude'):.6f}")
                            print(f"              Provider: {last_point.get('provider')}")
                except:
                    pass
                
                print("─"*60)
                print(f"\n💡 Commands:")
                print(f"   rangeexport (rex)  - Export to /sdcard/Download/")
                print(f"   rangestatus        - Check GPS status")
                print(f"   rangeclear         - Clear all logged points\n")
            
            elif cmd in ['rangeexport', 'rex']:
                self.export_files()
            
            elif cmd == 'rangeclear':
                # Clear all range test files immediately
                print(f"\n🗑️ Clearing range test files...")
                
                files_to_delete = [
                    self.json_file,
                    self.kml_file,
                    self.csv_file,
                    self.geojson_file,
                    self.html_file
                ]
                
                deleted = 0
                for filepath in files_to_delete:
                    if os.path.exists(filepath):
                        try:
                            os.remove(filepath)
                            deleted += 1
                        except Exception as e:
                            print(f"⚠️ Could not delete {os.path.basename(filepath)}: {e}")
                
                if deleted > 0:
                    # Re-initialize files
                    self.init_files()
                    print(f"✅ Cleared {deleted} files and reset\n")
                else:
                    print(f"✅ No files to clear\n")
            
            elif cmd == 'rangestatus':
                print(f"\n📍 GPS STATUS")
                print("─"*60)
                
                is_termux = os.path.exists('/data/data/com.termux')
                
                if not is_termux:
                    print("❌ Not running on Termux")
                    print("   GPS logging only works on Android with Termux\n")
                    return
                
                # Check if termux-api is installed
                try:
                    result = subprocess.run(['which', 'termux-location'], 
                                          capture_output=True, text=True)
                    if result.returncode != 0:
                        print("❌ termux-location not found")
                        print("\n💡 Install with:")
                        print("   pkg install termux-api")
                        print("   (Also install Termux:API app from F-Droid)\n")
                        return
                except:
                    pass
                
                # Test GPS providers in order
                print("Testing GPS providers...\n")
                
                print("1. GPS Satellite (10s timeout)... ", end="", flush=True)
                gps = self.try_gps_provider('gps', timeout=10)
                if gps:
                    print(f"✅ Working")
                    print(f"   Lat: {gps['latitude']:.6f}, Lon: {gps['longitude']:.6f}")
                    print(f"   Accuracy: ±{gps.get('accuracy', 0):.0f}m")
                else:
                    print(f"❌ Failed")
                    
                    print("\n2. Network (3s timeout)... ", end="", flush=True)
                    gps = self.try_gps_provider('network', timeout=3)
                    if gps:
                        print(f"✅ Working (fallback)")
                        print(f"   Lat: {gps['latitude']:.6f}, Lon: {gps['longitude']:.6f}")
                        print(f"   Accuracy: ±{gps.get('accuracy', 0):.0f}m")
                    else:
                        print(f"❌ Failed")
                        print(f"\n⚠️ No GPS providers working!")
                        print(f"\n💡 Make sure GPS Locker (or similar app) is running!")
                
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
                else:
                    print(f"❌ /sdcard/Download/ not found")
                
                print("─"*60 + "\n")
        
        except Exception as e:
            print(f"[Range Client] ⚠️ Command handler error: {e}")
            import traceback
            traceback.print_exc()

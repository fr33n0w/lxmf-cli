"""
Meteo Plugin for LXMF-CLI
Show weather information for any city
Uses Open-Meteo API (free, no API key needed)
"""
import sys
import os
import json
import time

class Plugin:
    def __init__(self, client):
        """Initialize the meteo plugin"""
        self.client = client
        self.commands = ['meteo', 'weather']
        self.description = "Show weather forecast for cities"
        
        # Default city (can be configured)
        self.default_city = "Rome"
        
        # City coordinates cache
        self.cache_file = os.path.join(client.storage_path, "meteo_cache.json")
        self.city_cache = self._load_cache()
        
        print("Meteo plugin loaded! Use 'meteo <city>' to check weather")
    
    def _load_cache(self):
        """Load cached city coordinates"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_cache(self):
        """Save city coordinates cache"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.city_cache, f, indent=2)
        except:
            pass
    
    def _geocode_city(self, city_name):
        """
        Get coordinates for a city using Open-Meteo's geocoding API
        (no need for geopy, Open-Meteo has built-in geocoding)
        """
        try:
            import urllib.request
            import urllib.parse
            
            # Check cache first
            cache_key = city_name.lower()
            if cache_key in self.city_cache:
                return self.city_cache[cache_key]
            
            # Use Open-Meteo geocoding API
            encoded_city = urllib.parse.quote(city_name)
            url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_city}&count=1&language=en&format=json"
            
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            if 'results' in data and len(data['results']) > 0:
                result = data['results'][0]
                location = {
                    'name': result.get('name', city_name),
                    'country': result.get('country', ''),
                    'lat': result.get('latitude'),
                    'lon': result.get('longitude'),
                    'admin1': result.get('admin1', '')  # State/Region
                }
                
                # Cache the result
                self.city_cache[cache_key] = location
                self._save_cache()
                
                return location
            else:
                return None
        
        except Exception as e:
            return None
    
    def _get_weather(self, lat, lon):
        """Get weather data from Open-Meteo API"""
        try:
            import urllib.request
            
            # Open-Meteo API endpoint
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
                f"precipitation,weather_code,wind_speed_10m,wind_direction_10m"
                f"&daily=weather_code,temperature_2m_max,temperature_2m_min,"
                f"precipitation_sum,wind_speed_10m_max"
                f"&timezone=auto&forecast_days=3"
            )
            
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            return data
        
        except Exception as e:
            return None
    
    def _weather_code_to_emoji(self, code):
        """Convert WMO weather code to emoji and description"""
        weather_codes = {
            0: ("☀️", "Clear sky"),
            1: ("🌤️", "Mainly clear"),
            2: ("⛅", "Partly cloudy"),
            3: ("☁️", "Overcast"),
            45: ("🌫️", "Foggy"),
            48: ("🌫️", "Depositing rime fog"),
            51: ("🌦️", "Light drizzle"),
            53: ("🌦️", "Moderate drizzle"),
            55: ("🌧️", "Dense drizzle"),
            61: ("🌧️", "Slight rain"),
            63: ("🌧️", "Moderate rain"),
            65: ("🌧️", "Heavy rain"),
            71: ("🌨️", "Slight snow"),
            73: ("🌨️", "Moderate snow"),
            75: ("❄️", "Heavy snow"),
            77: ("🌨️", "Snow grains"),
            80: ("🌦️", "Slight rain showers"),
            81: ("🌧️", "Moderate rain showers"),
            82: ("⛈️", "Violent rain showers"),
            85: ("🌨️", "Slight snow showers"),
            86: ("❄️", "Heavy snow showers"),
            95: ("⛈️", "Thunderstorm"),
            96: ("⛈️", "Thunderstorm with hail"),
            99: ("⛈️", "Thunderstorm with heavy hail"),
        }
        
        return weather_codes.get(code, ("🌡️", "Unknown"))
    
    def _wind_direction_to_arrow(self, degrees):
        """Convert wind direction degrees to arrow"""
        directions = ["↓", "↙", "←", "↖", "↑", "↗", "→", "↘"]
        index = int((degrees + 22.5) / 45) % 8
        return directions[index]
    
    def _format_weather_report(self, location, weather_data):
        """Format weather data into readable report"""
        try:
            current = weather_data.get('current', {})
            daily = weather_data.get('daily', {})
            
            # Location info
            city_name = location['name']
            country = location.get('country', '')
            admin1 = location.get('admin1', '')
            
            location_str = f"{city_name}"
            if admin1:
                location_str += f", {admin1}"
            if country:
                location_str += f", {country}"
            
            # Current weather
            temp = current.get('temperature_2m', 0)
            feels_like = current.get('apparent_temperature', 0)
            humidity = current.get('relative_humidity_2m', 0)
            wind_speed = current.get('wind_speed_10m', 0)
            wind_dir = current.get('wind_direction_10m', 0)
            precip = current.get('precipitation', 0)
            weather_code = current.get('weather_code', 0)
            
            emoji, condition = self._weather_code_to_emoji(weather_code)
            wind_arrow = self._wind_direction_to_arrow(wind_dir)
            
            # Build report
            lines = []
            lines.append("=" * 50)
            lines.append(f"🌍 WEATHER FORECAST")
            lines.append("=" * 50)
            lines.append(f"\n📍 {location_str}")
            lines.append(f"\n{emoji} CURRENT CONDITIONS")
            lines.append("-" * 50)
            lines.append(f"Condition: {condition}")
            lines.append(f"Temperature: {temp:.1f}°C (feels like {feels_like:.1f}°C)")
            lines.append(f"Humidity: {humidity}%")
            lines.append(f"Wind: {wind_arrow} {wind_speed:.1f} km/h")
            if precip > 0:
                lines.append(f"Precipitation: {precip} mm")
            
            # 3-day forecast
            if 'time' in daily and len(daily['time']) >= 3:
                lines.append(f"\n📅 3-DAY FORECAST")
                lines.append("-" * 50)
                
                for i in range(min(3, len(daily['time']))):
                    date = daily['time'][i]
                    temp_max = daily['temperature_2m_max'][i]
                    temp_min = daily['temperature_2m_min'][i]
                    precip_sum = daily['precipitation_sum'][i]
                    wind_max = daily['wind_speed_10m_max'][i]
                    day_code = daily['weather_code'][i]
                    
                    day_emoji, day_condition = self._weather_code_to_emoji(day_code)
                    
                    # Parse date
                    from datetime import datetime
                    date_obj = datetime.fromisoformat(date)
                    day_name = date_obj.strftime('%A')[:3]  # Mon, Tue, etc.
                    
                    lines.append(f"\n{day_name} {date}: {day_emoji} {day_condition}")
                    lines.append(f"  Temp: {temp_min:.1f}°C - {temp_max:.1f}°C")
                    if precip_sum > 0:
                        lines.append(f"  Rain: {precip_sum} mm")
                    lines.append(f"  Wind: {wind_max:.1f} km/h")
            
            lines.append("\n" + "=" * 50)
            lines.append("Data: Open-Meteo.com")
            
            return "\n".join(lines)
        
        except Exception as e:
            return f"❌ Error formatting weather data: {e}"
    
    def _send_reply(self, dest_hash, content):
        """Send a reply message silently"""
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        
        try:
            devnull = open(os.devnull, 'w', encoding='utf-8', errors='ignore')
            sys.stdout = devnull
            sys.stderr = devnull
            
            self.client.send_message(dest_hash, content)
            
        finally:
            devnull.close()
            sys.stdout = old_stdout
            sys.stderr = old_stderr
    
    def _get_weather_report(self, city_name):
        """Get complete weather report for a city"""
        # Geocode the city
        location = self._geocode_city(city_name)
        
        if not location:
            return f"❌ City not found: {city_name}\n\n💡 Try a different spelling or include country name"
        
        # Get weather data
        weather_data = self._get_weather(location['lat'], location['lon'])
        
        if not weather_data:
            return f"❌ Could not retrieve weather data for {city_name}"
        
        # Format and return report
        return self._format_weather_report(location, weather_data)
    
    def on_message(self, message, msg_data):
        """Handle incoming weather requests via message"""
        if msg_data['direction'] == 'outbound':
            return False
        
        content = msg_data.get('content', '').strip()
        source_hash = msg_data['source_hash']
        
        # Check for weather command
        if content.lower().startswith(('/meteo', '/weather')):
            parts = content.split(maxsplit=1)
            
            # Get city name or use default
            if len(parts) > 1:
                city_name = parts[1].strip()
            else:
                city_name = self.default_city
            
            # Get weather report
            print(f"\n[METEO] Processing request from {self.client.format_contact_display_short(source_hash)}")
            print(f"[METEO] Fetching weather for: {city_name}")
            print("> ", end="", flush=True)
            
            report = self._get_weather_report(city_name)
            
            # Send reply
            time.sleep(0.5)
            self._send_reply(source_hash, report)
            
            print(f"\n[METEO] Sent weather report")
            print("> ", end="", flush=True)
            
            return True  # Suppress normal notification
        
        return False
    
    def handle_command(self, cmd, parts):
        """Handle local meteo/weather command"""
        if cmd in ['meteo', 'weather']:
            if len(parts) < 2:
                # Use default city
                city_name = self.default_city
                print(f"\nFetching weather for default city: {city_name}...")
            else:
                # Parse arguments
                subcommand = parts[1].lower()
                
                if subcommand == 'set' and len(parts) >= 3:
                    # Set default city
                    new_city = ' '.join(parts[2:])
                    
                    # Verify city exists
                    location = self._geocode_city(new_city)
                    if location:
                        self.default_city = location['name']
                        print(f"\n✓ Default city set to: {self.default_city}")
                        if location.get('country'):
                            print(f"  Location: {location['name']}, {location['country']}\n")
                        return
                    else:
                        print(f"\n❌ City not found: {new_city}\n")
                        return
                
                elif subcommand == 'default':
                    # Show default city
                    print(f"\nDefault city: {self.default_city}")
                    print(f"\n💡 Use 'meteo set <city>' to change\n")
                    return
                
                else:
                    # Get weather for specified city
                    city_name = ' '.join(parts[1:])
                    print(f"\nFetching weather for: {city_name}...")
            
            # Get and display weather report
            report = self._get_weather_report(city_name)
            print(f"\n{report}\n")
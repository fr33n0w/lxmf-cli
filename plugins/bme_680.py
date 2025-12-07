# bme680_bot.py
# BME680 Environmental Sensor Plugin for LXMF-CLI
# Provides temperature, humidity, pressure, gas resistance and AQI readings
# Made By Cascafico / Edited By F.

import time
import json
import os

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['bme']
        self.description = "BME680 Environmental Sensor with AQI"
        
        # Import sensor library
        try:
            import bme680 as bme680_lib
            self.bme680 = bme680_lib
            self.sensor_enabled = True
        except ImportError:
            self.sensor_enabled = False
            self.bme680 = None
            print("[BME680] Error: bme680 library not installed")
            print("[BME680] Install with: pip3 install bme680 --break-system-packages")
        except AttributeError as e:
            self.sensor_enabled = False
            self.bme680 = None
            print(f"[BME680] Error: name conflict - {e}")
            print("[BME680] Make sure the plugin is NOT named 'bme680.py'")
        
        self.sensor = None
        
        # AQI calculation parameters
        self.gas_baseline = None
        self.hum_baseline = 40.0  # Optimal indoor humidity
        self.hum_weighting = 0.25  # Humidity contributes 25% to air quality score
        self.baseline_file = os.path.expanduser("~/.bme680_baseline.json")
        
        # Initialize sensor and load baseline
        if self.sensor_enabled:
            self._init_sensor()
            self._load_baseline()
    
    # ------------------------------------------------------------------
    def _init_sensor(self):
        """Initialize BME680 sensor, trying both I2C addresses"""
        try:
            # Try 0x77 first (SECONDARY) - common for CJMCU-680
            try:
                self.sensor = self.bme680.BME680(self.bme680.I2C_ADDR_SECONDARY)
                print(f"[BME680] Sensor found at 0x77 (SECONDARY)")
            except (IOError, RuntimeError, OSError):
                # If 0x77 fails, try 0x76 (PRIMARY)
                print(f"[BME680] 0x77 failed, trying 0x76...")
                self.sensor = self.bme680.BME680(self.bme680.I2C_ADDR_PRIMARY)
                print(f"[BME680] Sensor found at 0x76 (PRIMARY)")
            
            # Configure sensor for optimal performance
            self.sensor.set_humidity_oversample(self.bme680.OS_2X)
            self.sensor.set_pressure_oversample(self.bme680.OS_4X)
            self.sensor.set_temperature_oversample(self.bme680.OS_8X)
            self.sensor.set_filter(self.bme680.FILTER_SIZE_3)
            
            # Configure gas sensor
            self.sensor.set_gas_status(self.bme680.ENABLE_GAS_MEAS)
            self.sensor.set_gas_heater_temperature(320)  # degrees Celsius
            self.sensor.set_gas_heater_duration(150)     # milliseconds
            self.sensor.select_gas_heater_profile(0)
            
            print("[BME680] Sensor initialized successfully")
            
            # Warm up sensor
            print("[BME680] Warming up gas sensor (10 seconds)...")
            start_time = time.time()
            while time.time() - start_time < 10:
                self.sensor.get_sensor_data()
                time.sleep(1)
            print("[BME680] Warm-up complete")
            
        except Exception as e:
            print(f"[BME680] Sensor initialization error: {e}")
            print(f"[BME680] Error type: {type(e).__name__}")
            self.sensor = None
            self.sensor_enabled = False
    
    # ------------------------------------------------------------------
    def _load_baseline(self):
        """Load baseline from file if it exists"""
        try:
            if os.path.exists(self.baseline_file):
                with open(self.baseline_file, 'r') as f:
                    data = json.load(f)
                    self.gas_baseline = data.get('gas_baseline')
                    self.hum_baseline = data.get('hum_baseline', 40.0)
                    print(f"[BME680] Baseline loaded: Gas={self.gas_baseline:.0f}Ω, Humidity={self.hum_baseline:.1f}%")
            else:
                print(f"[BME680] No baseline found. Use 'bme calibrate' to calibrate.")
        except Exception as e:
            print(f"[BME680] Error loading baseline: {e}")
    
    # ------------------------------------------------------------------
    def _save_baseline(self):
        """Save baseline to file"""
        try:
            data = {
                'gas_baseline': self.gas_baseline,
                'hum_baseline': self.hum_baseline,
                'timestamp': time.time()
            }
            with open(self.baseline_file, 'w') as f:
                json.dump(data, f)
            print(f"[BME680] Baseline saved to {self.baseline_file}")
        except Exception as e:
            print(f"[BME680] Error saving baseline: {e}")
    
    # ------------------------------------------------------------------
    def calibrate_baseline(self, duration=60):
        """Calibrate gas baseline by sampling for duration seconds"""
        if not self.sensor:
            print("[BME680] Sensor not available")
            return False
        
        print(f"[BME680] Calibrating baseline for {duration} seconds...")
        print("[BME680] Make sure sensor is in clean air!")
        
        gas_samples = []
        hum_samples = []
        start_time = time.time()
        
        while time.time() - start_time < duration:
            if self.sensor.get_sensor_data():
                if self.sensor.data.heat_stable:
                    gas_samples.append(self.sensor.data.gas_resistance)
                    hum_samples.append(self.sensor.data.humidity)
                    elapsed = int(time.time() - start_time)
                    print(f"[BME680] Calibrating... {elapsed}/{duration}s - Gas: {self.sensor.data.gas_resistance:.0f}Ω")
            time.sleep(2)
        
        if gas_samples:
            self.gas_baseline = sum(gas_samples) / len(gas_samples)
            self.hum_baseline = sum(hum_samples) / len(hum_samples)
            self._save_baseline()
            print(f"[BME680] ✓ Baseline calibrated:")
            print(f"[BME680]   Gas: {self.gas_baseline:.0f}Ω")
            print(f"[BME680]   Humidity: {self.hum_baseline:.1f}%")
            return True
        else:
            print("[BME680] ✗ Calibration failed: no valid samples")
            return False
    
    # ------------------------------------------------------------------
    def calculate_air_quality_score(self, gas_resistance, humidity):
        """Calculate air quality score (0-100, higher is better)"""
        if self.gas_baseline is None:
            return None, "Not calibrated"
        
        # Gas resistance contribution (75% of score)
        gas_offset = self.gas_baseline - gas_resistance
        
        if gas_offset > 0:
            gas_score = (self.gas_baseline - gas_offset) / self.gas_baseline
            gas_score = max(0, min(gas_score * 100, 100))
        else:
            gas_score = min(100, (gas_resistance / self.gas_baseline) * 100)
        
        gas_score *= (100 - self.hum_weighting * 100) / 100
        
        # Humidity contribution (25% of score)
        hum_offset = humidity - self.hum_baseline
        
        if hum_offset > 0:
            hum_score = (100 - self.hum_baseline - hum_offset) / (100 - self.hum_baseline)
        else:
            hum_score = (self.hum_baseline + hum_offset) / self.hum_baseline
        
        hum_score = max(0, min(hum_score * 100, 100))
        hum_score *= self.hum_weighting * 100 / 100
        
        air_quality_score = gas_score + hum_score
        
        return air_quality_score, self.get_air_quality_label(air_quality_score)
    
    # ------------------------------------------------------------------
    def get_air_quality_label(self, score):
        """Convert air quality score to descriptive label"""
        if score is None:
            return "Unknown"
        elif score >= 90:
            return "Excellent"
        elif score >= 70:
            return "Good"
        elif score >= 50:
            return "Moderate"
        elif score >= 30:
            return "Poor"
        else:
            return "Very Poor"
    
    # ------------------------------------------------------------------
    def gas_to_aqi(self, gas_resistance):
        """Convert gas resistance to AQI-like scale (0-500)"""
        if self.gas_baseline is None:
            return None
        
        ratio = gas_resistance / self.gas_baseline
        
        if ratio >= 1.0:
            aqi = max(0, 50 * (2 - ratio))
        else:
            aqi = 50 + (450 * (1 - ratio))
        
        return min(500, max(0, aqi))
    
    # ------------------------------------------------------------------
    def get_aqi_category(self, aqi):
        """Get AQI category label"""
        if aqi is None:
            return "Unknown"
        elif aqi <= 50:
            return "Good"
        elif aqi <= 100:
            return "Moderate"
        elif aqi <= 150:
            return "Unhealthy (Sensitive)"
        elif aqi <= 200:
            return "Unhealthy"
        elif aqi <= 300:
            return "Very Unhealthy"
        else:
            return "Hazardous"
    
    # ------------------------------------------------------------------
    def get_telemetry(self, include_aqi=True):
        """Read sensor data and return telemetry dictionary"""
        if not self.sensor:
            return {
                "status": "SENSOR_NOT_INITIALIZED",
                "temperature": None,
                "humidity": None,
                "pressure": None,
                "gas": None,
                "air_quality_score": None,
                "air_quality_label": None,
                "aqi": None,
                "aqi_category": None,
            }
        
        try:
            if self.sensor.get_sensor_data():
                temp = self.sensor.data.temperature
                humidity = self.sensor.data.humidity
                pressure = self.sensor.data.pressure
                gas = self.sensor.data.gas_resistance if self.sensor.data.heat_stable else None
                
                # Calculate AQI if enabled and gas reading is available
                aq_score = None
                aq_label = None
                aqi = None
                aqi_category = None
                
                if include_aqi and gas:
                    aq_score, aq_label = self.calculate_air_quality_score(gas, humidity)
                    aqi = self.gas_to_aqi(gas)
                    aqi_category = self.get_aqi_category(aqi)
                
                return {
                    "status": "OK",
                    "temperature": round(temp, 2),
                    "humidity": round(humidity, 2),
                    "pressure": round(pressure, 2),
                    "gas": round(gas, 0) if gas else "Heating",
                    "air_quality_score": round(aq_score, 1) if aq_score else None,
                    "air_quality_label": aq_label,
                    "aqi": round(aqi, 0) if aqi else None,
                    "aqi_category": aqi_category,
                }
            else:
                return {
                    "status": "READ_FAILED",
                    "temperature": None,
                    "humidity": None,
                    "pressure": None,
                    "gas": None,
                    "air_quality_score": None,
                    "air_quality_label": None,
                    "aqi": None,
                    "aqi_category": None,
                }
        except Exception as e:
            print(f"[BME680] Sensor read error: {e}")
            return {
                "status": f"ERROR: {e}",
                "temperature": None,
                "humidity": None,
                "pressure": None,
                "gas": None,
                "air_quality_score": None,
                "air_quality_label": None,
                "aqi": None,
                "aqi_category": None,
            }
    
    # ------------------------------------------------------------------
    def format_telemetry(self, d):
        """Format telemetry data as human-readable string (full format)"""
        temp_str = f"{d['temperature']:.1f}°C" if d['temperature'] is not None else "N/A"
        hum_str = f"{d['humidity']:.1f}%" if d['humidity'] is not None else "N/A"
        press_str = f"{d['pressure']:.1f}hPa" if d['pressure'] is not None else "N/A"
        gas_str = f"{d['gas']:.0f}Ω" if isinstance(d['gas'], (int, float)) else str(d['gas'])
        
        # Always use full format (for both console and LXMF)
        msg = (
            f"🌡 BME680 Telemetry\n"
            f"{'='*30}\n"
            f"Status:      {d['status']}\n"
            f"Temperature: {temp_str}\n"
            f"Humidity:    {hum_str}\n"
            f"Pressure:    {press_str}\n"
            f"Gas:         {gas_str}\n"
        )
        
        if d.get('air_quality_score'):
            msg += f"{'='*00}\n"
            msg += f"AQ Score:    {d['air_quality_score']:.1f}/100 ({d['air_quality_label']})\n"
        
        if d.get('aqi'):
            msg += f"AQI:         {d['aqi']:.0f} ({d['aqi_category']})\n"
        
        if self.gas_baseline and d['status'] == 'OK':
            msg += f"{'='*30}\n"
            msg += f"Baseline:    {self.gas_baseline:.0f}Ω\n"
        
        return msg
    
    # ------------------------------------------------------------------
    #     LXMF MESSAGE HANDLER
    # ------------------------------------------------------------------
    def on_message(self, message, msg_data):
        """Handle incoming LXMF messages"""
        content = msg_data["content"].strip().lower()
        if not content.startswith("bme"):
            return False
        
        # Get telemetry with AQI
        data = self.get_telemetry(include_aqi=True)
        
        # Use full format for LXMF messages
        reply = self.format_telemetry(data)
        
        self.client.send_message(msg_data["source_hash"], reply)
        return True
    
    # ------------------------------------------------------------------
    #     CONSOLE COMMAND HANDLER
    # ------------------------------------------------------------------
    def handle_command(self, cmd, parts):
        """Handle console commands"""
        if cmd != "bme":
            return
        
        # No arguments → help
        if len(parts) == 1:
            print("\n" + "="*45)
            print("BME680 Environmental Sensor Commands")
            print("="*45)
            print("  bme read         - Show telemetry with AQI")
            print("  bme simple       - Show telemetry without AQI")
            print("  bme raw          - Show raw JSON output")
            print("  bme calibrate    - Calibrate baseline (60s)")
            print("  bme calibrate N  - Calibrate baseline (N seconds)")
            print("  bme baseline     - Show current baseline")
            print("  bme reinit       - Reinitialize sensor")
            print("="*45 + "\n")
            return
        
        sub = parts[1].lower()
        
        if sub == "read":
            data = self.get_telemetry(include_aqi=True)
            print(self.format_telemetry(data))
            return
        
        elif sub == "simple":
            data = self.get_telemetry(include_aqi=False)
            print(self.format_telemetry(data))
            return
        
        elif sub == "raw":
            import json
            data = self.get_telemetry(include_aqi=True)
            print(json.dumps(data, indent=2))
            return
        
        elif sub == "calibrate":
            duration = 60
            if len(parts) > 2:
                try:
                    duration = int(parts[2])
                except ValueError:
                    print("Invalid duration, using 60 seconds")
            
            self.calibrate_baseline(duration=duration)
            return
        
        elif sub == "baseline":
            if self.gas_baseline:
                print(f"Gas Baseline:      {self.gas_baseline:.0f}Ω")
                print(f"Humidity Baseline: {self.hum_baseline:.1f}%")
                print(f"File: {self.baseline_file}")
            else:
                print("No baseline configured.")
                print("Use 'bme calibrate' to calibrate.")
            return
        
        elif sub == "reinit":
            print("[BME680] Reinitializing sensor...")
            self._init_sensor()
            if self.sensor:
                data = self.get_telemetry(include_aqi=True)
                print(self.format_telemetry(data))
            return
        
        else:
            print(f"Unknown command: {sub}")
            print("Use 'bme' to see available commands")
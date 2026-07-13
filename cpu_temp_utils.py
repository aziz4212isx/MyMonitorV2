import subprocess

class CPUTempFetcher:
    def __init__(self):
        self.method = None
        
        try:
            cmd = ["typeperf", "\\Thermal Zone Information(*)\\High Precision Temperature", "\\Energy Meter(*)\\Power", "-sc", "1"]
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
            if res.returncode == 0 and "High Precision Temperature" in res.stdout:
                self.method = "perf_high"
        except Exception as e: print(f"[CPU Init Perf High] {e}")

        if not self.method:
            try:
                cmd = ["typeperf", "\\Thermal Zone Information(*)\\Temperature", "\\Energy Meter(*)\\Power", "-sc", "1"]
                res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
                if res.returncode == 0 and "Temperature" in res.stdout:
                    self.method = "perf_normal"
            except Exception as e: print(f"[CPU Init Perf Norm] {e}")

    def fetch(self, sys_data):
        sys_data.cpu_temp = "N/A"
        sys_data.cpu_pow = "--"
        
        if not self.method:
            return

        try:
            if self.method == "perf_high":
                cmd = ["typeperf", "\\Thermal Zone Information(*)\\High Precision Temperature", "\\Energy Meter(*)\\Power", "-sc", "1"]
            else:
                cmd = ["typeperf", "\\Thermal Zone Information(*)\\Temperature", "\\Energy Meter(*)\\Power", "-sc", "1"]
                
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
            lines = [line.strip() for line in res.stdout.strip().split("\n") if line.strip()]
            
            if len(lines) >= 2:
                headers = lines[0].split(",")
                vals = lines[1].split(",")
                
                # Parse Temperature
                temp_idx = -1
                for i, h in enumerate(headers):
                    if "Temperature" in h:
                        temp_idx = i
                        break
                if temp_idx != -1 and temp_idx < len(vals):
                    val_str = vals[temp_idx].replace('"', '')
                    try:
                        if self.method == "perf_high":
                            sys_data.cpu_temp = str(round((float(val_str) / 10) - 273.15, 1))
                        else:
                            sys_data.cpu_temp = str(round(float(val_str) - 273.15, 1))
                    except: pass
                
                # Parse Power
                pow_idx = -1
                for i, h in enumerate(headers):
                    # Prefer PKG for CPU Package Power
                    if "PKG" in h and "Power" in h:
                        pow_idx = i
                        break
                if pow_idx == -1:
                    for i, h in enumerate(headers):
                        if "Power" in h:
                            pow_idx = i
                            break
                            
                if pow_idx != -1 and pow_idx < len(vals):
                    val_str = vals[pow_idx].replace('"', '')
                    try:
                        # Convert milliwatts to watts
                        sys_data.cpu_pow = str(round(float(val_str) / 1000.0, 1))
                    except: pass
                    
        except subprocess.TimeoutExpired as e:
            print(f"[CPU Fetch Timeout] {e}")
        except Exception as e:
            print(f"[CPU Fetch Error] {e}")

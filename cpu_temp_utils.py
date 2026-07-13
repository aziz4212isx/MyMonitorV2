import subprocess

class CPUTempFetcher:
    def __init__(self):
        self.method = None
        
        try:
            cmd = ["powershell", "-NoProfile", "-Command", "Get-CimInstance -Namespace root/WMI -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop | Select-Object -First 1 -ExpandProperty CurrentTemperature"]
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
            if res.returncode == 0 and res.stdout.strip():
                val = float(res.stdout.strip())
                if val > 0:
                    self.method = "wmi"
        except Exception as e: print(f"[CPU Init WMI] {e}")

        if not self.method:
            try:
                cmd = ["powershell", "-NoProfile", "-Command", "(Get-Counter '\\Thermal Zone Information(*)\\High Precision Temperature' -ErrorAction Stop | Select-Object -ExpandProperty CounterSamples | Select-Object -First 1 CookedValue).CookedValue"]
                res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
                if res.returncode == 0 and res.stdout.strip():
                    self.method = "perf_high"
            except Exception as e: print(f"[CPU Init Perf High] {e}")

        if not self.method:
            try:
                cmd = ["powershell", "-NoProfile", "-Command", "(Get-Counter '\\Thermal Zone Information(*)\\Temperature' -ErrorAction Stop | Select-Object -ExpandProperty CounterSamples | Select-Object -First 1 CookedValue).CookedValue"]
                res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
                if res.returncode == 0 and res.stdout.strip():
                    self.method = "perf_normal"
            except Exception as e: print(f"[CPU Init Perf Norm] {e}")

    def fetch(self, sys_data):
        if self.method == "wmi":
            try:
                cmd = ["powershell", "-NoProfile", "-Command", "Get-CimInstance -Namespace root/WMI -ClassName MSAcpi_ThermalZoneTemperature | Select-Object -First 1 -ExpandProperty CurrentTemperature"]
                res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
                if res.stdout.strip():
                    sys_data.cpu_temp = str(round((float(res.stdout.strip()) / 10) - 273.15, 1))
            except: pass
        elif self.method == "perf_high":
            try:
                cmd = ["powershell", "-NoProfile", "-Command", "(Get-Counter '\\Thermal Zone Information(*)\\High Precision Temperature' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty CounterSamples | Select-Object -First 1 CookedValue).CookedValue"]
                res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
                if res.stdout.strip():
                    sys_data.cpu_temp = str(round((float(res.stdout.strip()) / 10) - 273.15, 1))
            except: pass
        elif self.method == "perf_normal":
            try:
                cmd = ["powershell", "-NoProfile", "-Command", "(Get-Counter '\\Thermal Zone Information(*)\\Temperature' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty CounterSamples | Select-Object -First 1 CookedValue).CookedValue"]
                res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
                if res.stdout.strip():
                    sys_data.cpu_temp = str(round(float(res.stdout.strip()) - 273.15, 1))
            except: pass
        else:
            sys_data.cpu_temp = "N/A"

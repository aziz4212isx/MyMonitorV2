import subprocess

class CPUTempFetcher:
    def __init__(self):
        self.method = None
        
        try:
            cmd = ["typeperf", "\\Thermal Zone Information(*)\\High Precision Temperature", "-sc", "1"]
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
            if res.returncode == 0 and "High Precision Temperature" in res.stdout:
                self.method = "perf_high"
        except Exception as e: print(f"[CPU Init Perf High] {e}")

        if not self.method:
            try:
                cmd = ["typeperf", "\\Thermal Zone Information(*)\\Temperature", "-sc", "1"]
                res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
                if res.returncode == 0 and "Temperature" in res.stdout:
                    self.method = "perf_normal"
            except Exception as e: print(f"[CPU Init Perf Norm] {e}")

    def fetch(self, sys_data):
        if self.method == "perf_high":
            try:
                cmd = ["typeperf", "\\Thermal Zone Information(*)\\High Precision Temperature", "-sc", "1"]
                res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
                lines = [line.strip() for line in res.stdout.strip().split("\n") if line.strip()]
                if len(lines) >= 2:
                    val = lines[1].split(",")[1].replace('"', '')
                    sys_data.cpu_temp = str(round((float(val) / 10) - 273.15, 1))
            except subprocess.TimeoutExpired as e:
                print(f"[CPU Fetch PerfHigh Timeout] {e}")
            except Exception as e:
                print(f"[CPU Fetch PerfHigh Error] {e}")
        elif self.method == "perf_normal":
            try:
                cmd = ["typeperf", "\\Thermal Zone Information(*)\\Temperature", "-sc", "1"]
                res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
                lines = [line.strip() for line in res.stdout.strip().split("\n") if line.strip()]
                if len(lines) >= 2:
                    val = lines[1].split(",")[1].replace('"', '')
                    sys_data.cpu_temp = str(round(float(val) - 273.15, 1))
            except subprocess.TimeoutExpired as e:
                print(f"[CPU Fetch PerfNorm Timeout] {e}")
            except Exception as e:
                print(f"[CPU Fetch PerfNorm Error] {e}")
        else:
            sys_data.cpu_temp = "N/A"

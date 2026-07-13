import subprocess
import shutil

class GPUFetcher:
    def __init__(self):
        self.vendor = "unknown"
        self.name = "--"
        self.has_nvidia = shutil.which("nvidia-smi") is not None
        
        if self.has_nvidia:
            self.vendor = "nvidia"
            try:
                cmd = ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"]
                res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
                if res.stdout.strip():
                    self.name = res.stdout.strip()
            except Exception as e: print(f"[GPU Init] {e}")
        else:
            try:
                cmd = ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"]
                res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
                output = res.stdout.strip()
                if output:
                    names = [n for n in output.split('\n') if n.strip()]
                    if names:
                        self.name = names[0].strip()
                        if "AMD" in self.name.upper() or "RADEON" in self.name.upper():
                            self.vendor = "amd"
                        elif "INTEL" in self.name.upper():
                            self.vendor = "intel"
                        else:
                            self.vendor = "other"
                            
                        # Cache static AdapterRAM once!
                        safe_name = self.name.replace("'", "''")
                        cmd2 = ["powershell", "-NoProfile", "-Command", f"Get-CimInstance Win32_VideoController | Where-Object Name -eq '{safe_name}' | Select-Object -ExpandProperty AdapterRAM"]
                        res2 = subprocess.run(cmd2, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
                        if res2.stdout.strip():
                            try:
                                vram_bytes = int(res2.stdout.strip())
                                self.cached_vram = str(vram_bytes // (1024*1024))
                            except ValueError:
                                self.cached_vram = "--"
                        else:
                            self.cached_vram = "--"
            except Exception as e: print(f"[GPU Init] {e}")

    def is_valid(self):
        return self.vendor != "unknown"

    def fetch(self, sys_data):
        sys_data.gpu_name = self.name
        
        if self.vendor == "nvidia":
            try:
                smi_cmd = ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu,memory.used,power.draw,power.limit,clocks.current.graphics,clocks.current.memory,fan.speed", "--format=csv,noheader,nounits"]
                smi_res = subprocess.run(smi_cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
                if smi_res.stdout.strip():
                    parts = [p.strip() for p in smi_res.stdout.strip().split(',')]
                    if len(parts) >= 8:
                        sys_data.gpu_temp, sys_data.gpu_use, sys_data.gpu_mem = parts[0], parts[1], parts[2]
                        sys_data.gpu_pow, sys_data.gpu_pow_limit, sys_data.gpu_c_clock, sys_data.gpu_m_clock, sys_data.gpu_fan = parts[3], parts[4], parts[5], parts[6], parts[7]
            except subprocess.TimeoutExpired as e:
                print(f"[GPU Fetch NV Timeout] {e}")
            except Exception as e:
                print(f"[GPU Fetch NV Error] {e}")
        elif self.vendor in ("amd", "intel", "other"):
            sys_data.gpu_mem = getattr(self, "cached_vram", "--")

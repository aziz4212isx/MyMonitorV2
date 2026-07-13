import time
import datetime
import traceback
import logging
import psutil
import os
import csv
import collections
from dataclasses import dataclass, field
from typing import List, Dict

from PySide6.QtCore import QObject, Signal

from cpu_temp_utils import CPUTempFetcher
from gpu_utils import GPUFetcher

logger = logging.getLogger("LightMonitor")

def get_color_by_value(val, metric_type="usage"):
    try:
        v = float(val)
    except:
        return "gray"
    
    if metric_type == "temp":
        if v < 60: return "#2ECC71"  # green
        elif v <= 80: return "#F1C40F"  # yellow
        else: return "#E74C3C"  # red
    elif metric_type == "usage":
        if v < 60: return "#2ECC71"
        elif v <= 85: return "#F1C40F"
        else: return "#E74C3C"
    return "white"

@dataclass
class SystemData:
    uptime: str = "--"
    cpu_use: float = 0.0
    cpu_temp: str = "--"
    cpu_freq: str = "--"
    cpu_cores: List[float] = field(default_factory=list)
    
    gpu_name: str = "--"
    gpu_use: str = "--"
    gpu_temp: str = "--"
    gpu_mem: str = "--"
    gpu_pow: str = "--"
    gpu_pow_limit: str = "--"
    top5_cpu: List[str] = field(default_factory=list)
    top5_ram: List[str] = field(default_factory=list)
    gpu_c_clock: str = "--"
    gpu_m_clock: str = "--"
    gpu_fan: str = "--"
    
    ram_pct: float = 0.0
    ram_used: float = 0.0
    ram_total: float = 0.0
    swap_pct: float = 0.0
    
    disk_data: Dict[str, dict] = field(default_factory=dict)
    
    dl_speed: float = 0.0
    ul_speed: float = 0.0
    net_tot_dl: float = 0.0
    net_tot_ul: float = 0.0

class DataWorker(QObject):
    data_updated = Signal(object)
    
    def __init__(self, config_mgr):
        super().__init__()
        self.running = True
        self.config_mgr = config_mgr
        
        self.cpu_fetcher = CPUTempFetcher()
        self.gpu_fetcher = GPUFetcher()
        
        self.last_time = time.monotonic()
        self.last_net_io = psutil.net_io_counters() or type('obj', (object,), {'bytes_recv':0, 'bytes_sent':0})
        self.last_disk_io = psutil.disk_io_counters(perdisk=True) or {}
        
        self.last_top5_time = 0
        self._proc_cache = {}
        
        # Determine disks to monitor
        self.disk_mounts = {}
        try:
            for p in psutil.disk_partitions(all=False):
                if os.name == 'nt' and ('cdrom' in p.opts or p.fstype == ''):
                    continue
                letter = p.mountpoint.replace('\\', '').replace('/', '')
                self.disk_mounts[letter] = p.mountpoint
        except Exception:
            pass

    def run_loop(self):
        while self.running:
            d = SystemData()
            try:
                try:
                    bt = datetime.datetime.fromtimestamp(psutil.boot_time())
                    d.uptime = str(datetime.datetime.now() - bt).split('.')[0]
                except Exception as e: logger.error(f"[Uptime] {e}")

                try:
                    d.cpu_use = psutil.cpu_percent(interval=None)
                    d.cpu_cores = psutil.cpu_percent(interval=None, percpu=True)
                except Exception as e: logger.error(f"[CPU Usage] {e}")
                    
                try: 
                    freq = psutil.cpu_freq()
                    d.cpu_freq = str(round(freq.current)) if freq else "N/A"
                except Exception as e: logger.error(f"[CPU Freq] {e}")
                
                self.cpu_fetcher.fetch(d)

                try:
                    ram = psutil.virtual_memory()
                    d.ram_pct = ram.percent
                    d.ram_used = ram.used / (1024**3)
                    d.ram_total = ram.total / (1024**3)
                    d.swap_pct = psutil.swap_memory().percent
                except Exception as e: logger.error(f"[Memory] {e}")

                if self.gpu_fetcher.is_valid():
                    self.gpu_fetcher.fetch(d)

                current_time = time.monotonic()
                current_net_io = psutil.net_io_counters()
                if current_net_io is None:
                    current_net_io = self.last_net_io
                current_disk_io = psutil.disk_io_counters(perdisk=True) or {}
                time_diff = current_time - self.last_time

                # Refresh disk mounts every loop to detect hot-plugs
                self.disk_mounts = {}
                try:
                    for p in psutil.disk_partitions(all=False):
                        if os.name == 'nt' and ('cdrom' in p.opts or p.fstype == ''):
                            continue
                        letter = p.mountpoint.replace('\\', '').replace('/', '')
                        self.disk_mounts[letter] = p.mountpoint
                except Exception as e:
                    logger.error(f"[Disk Mounts Refresh] {e}")

                for letter, mount in self.disk_mounts.items():
                    try:
                        usage = psutil.disk_usage(mount)
                        d.disk_data[letter] = {"pct": usage.percent, "free": usage.free / (1024**3)}
                    except Exception as e:
                        logger.error(f"[Disk Usage {letter}] {e}")
                        d.disk_data[letter] = None  # Unreadable

                d_read = d_write = 0.0
                if time_diff < 0 or time_diff > 10:
                    self.last_net_io = current_net_io
                    self.last_disk_io = current_disk_io
                    self.last_time = current_time
                    time_diff = 0
                elif time_diff >= 0.1:
                    common_disks = current_disk_io.keys() & self.last_disk_io.keys()
                    total_read_now = sum(current_disk_io[k].read_bytes for k in common_disks)
                    total_write_now = sum(current_disk_io[k].write_bytes for k in common_disks)
                    total_read_last = sum(self.last_disk_io[k].read_bytes for k in common_disks)
                    total_write_last = sum(self.last_disk_io[k].write_bytes for k in common_disks)
                    
                    d_read = max(0.0, (total_read_now - total_read_last) / time_diff / (1024**2))
                    d_write = max(0.0, (total_write_now - total_write_last) / time_diff / (1024**2))

                    d.dl_speed = max(0.0, (current_net_io.bytes_recv - self.last_net_io.bytes_recv) / time_diff / 1024)
                    d.ul_speed = max(0.0, (current_net_io.bytes_sent - self.last_net_io.bytes_sent) / time_diff / 1024)
                
                d.disk_data["GLOBAL_IO"] = {"read": d_read, "write": d_write}
                d.net_tot_dl = getattr(current_net_io, 'bytes_recv', 0) / (1024**3)
                d.net_tot_ul = getattr(current_net_io, 'bytes_sent', 0) / (1024**3)

                self.last_net_io = current_net_io
                self.last_disk_io = current_disk_io
                self.last_time = current_time
                
                # Features logic
                feat = self.config_mgr.get_features_conf()
                
                # Top 5 Process (every ~5 seconds)
                if feat.get("top5_process"):
                    if current_time - self.last_top5_time >= 5:
                        try:
                            new_cache = {}
                            procs = []
                            for p in psutil.process_iter(['name', 'pid', 'memory_percent']):
                                try:
                                    pid = p.pid
                                    name = p.info['name']
                                    if not name or name == 'System Idle Process':
                                        continue
                                    cached = self._proc_cache.get(pid, p)
                                    cpu_pct = cached.cpu_percent(interval=None)
                                    mem_pct = p.info['memory_percent'] or 0.0
                                    procs.append({'name': name, 'cpu_percent': cpu_pct, 'memory_percent': mem_pct})
                                    new_cache[pid] = cached
                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                    pass
                            self._proc_cache = new_cache
                            top_cpu = sorted(procs, key=lambda x: x['cpu_percent'], reverse=True)[:5]
                            d.top5_cpu = [f"{p['name'][:15]}: {p['cpu_percent']:.1f}%" for p in top_cpu]
                            top_ram = sorted(procs, key=lambda x: x['memory_percent'], reverse=True)[:5]
                            d.top5_ram = [f"{p['name'][:15]}: {p['memory_percent']:.1f}%" for p in top_ram]
                        except Exception as e:
                            logger.error(f"[Top5] {e}")
                        self.last_top5_time = current_time

                # CSV Logging
                if feat.get("csv_logging"):
                    try:
                        csv_path = os.path.join(self.config_mgr.app_dir, "log.csv")
                        with open(csv_path, "a", newline='') as f:
                            write_header = f.tell() == 0
                            writer = csv.writer(f)
                            if write_header:
                                writer.writerow(["Time", "CPU_Use", "CPU_Temp", "GPU_Use", "GPU_Temp", "RAM_Use"])
                            writer.writerow([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), d.cpu_use, d.cpu_temp, d.gpu_use, d.gpu_temp, d.ram_pct])
                    except Exception as e:
                        logger.error(f"[CSV Log] {e}")
                        
                # Emit data to UI Thread
                if self.running:
                    self.data_updated.emit(d)

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"[DataWorker] CRASH:\n{tb}")
            
            # Safe sleep loop checking self.running every 100ms
            for _ in range(20):
                if not self.running:
                    break
                time.sleep(0.1)

import os
import json
import threading
import copy

class ConfigManager:
    def __init__(self):
        self.lock = threading.Lock()
        appdata = os.getenv('APPDATA')
        if not appdata:
            appdata = os.path.expanduser('~')
        self.app_dir = os.path.join(appdata, 'LightMonitor')
        self.config_path = os.path.join(self.app_dir, 'config.json')
        
        self.default_config = {
            "overlay": {
                "position": {"x": 100, "y": 100},
                "click_through": False,
                "ghost_mode": False,
                "transparency": 0.85,
                "layout": "RTSS Compact",
                "theme": "Cyan",
                "font_size": 12,
                "enabled_metrics": ["cpu_usage", "gpu_usage", "vram_usage", "ram_usage"],
                "metric_order": ["cpu_usage", "gpu_usage", "vram_usage", "ram_usage"]
            },
            "features": {
                "top5_process": False,
                "csv_logging": False,
                "run_on_startup": False,
                "alerts_enabled": False,
                "alert_cpu_temp": 85,
                "alert_gpu_temp": 85,
                "hotkey_enabled": False
            }
        }
        self.config = self.load_config()

    def load_config(self):
        with self.lock:
            if not os.path.exists(self.config_path):
                # Bug #3 fix: return a DEEP COPY, not the same object reference
                return copy.deepcopy(self.default_config)
            try:
                with open(self.config_path, 'r') as f:
                    loaded = json.load(f)
                    # Merge missing keys from default (forward-compat for new config fields)
                    for section, vals in self.default_config.items():
                        if section not in loaded:
                            loaded[section] = copy.deepcopy(vals)
                        else:
                            for key, val in vals.items():
                                if key not in loaded[section]:
                                    loaded[section][key] = val
                    return loaded
            except Exception:
                return copy.deepcopy(self.default_config)

    def save_config(self):
        with self.lock:
            self._save_config_no_lock()
            
    def get_overlay_conf(self):
        with self.lock:
            if "overlay" not in self.config:
                self.config["overlay"] = copy.deepcopy(self.default_config["overlay"])
            for key, val in self.default_config["overlay"].items():
                if key not in self.config["overlay"]:
                    self.config["overlay"][key] = val
            return copy.deepcopy(self.config["overlay"])

    def set_overlay_conf(self, new_conf):
        with self.lock:
            self.config["overlay"] = copy.deepcopy(new_conf)
            self._save_config_no_lock()

    def get_features_conf(self):
        with self.lock:
            if "features" not in self.config:
                self.config["features"] = copy.deepcopy(self.default_config["features"])
            for key, val in self.default_config["features"].items():
                if key not in self.config["features"]:
                    self.config["features"][key] = val
            return copy.deepcopy(self.config["features"])

    def set_features_conf(self, new_conf):
        with self.lock:
            self.config["features"] = copy.deepcopy(new_conf)
            self._save_config_no_lock()

    def _save_config_no_lock(self):
        os.makedirs(self.app_dir, exist_ok=True)
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"[Config] Error saving config: {e}")

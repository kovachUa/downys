import os
import json
import logging
from pathlib import Path

class SettingsManager:
    def __init__(self, app_name="DownYS"):
        if os.name == 'nt':
            config_dir = Path(os.environ.get('APPDATA', Path.home())) / app_name
        else:
            config_dir = Path.home() / '.config' / app_name
            
        config_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = config_dir / 'settings.json'
        self.settings = self._load_settings()

    def _load_settings(self):
        try:
            if self.settings_path.exists():
                with open(self.settings_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logging.warning(f"Не вдалося завантажити налаштування з {self.settings_path}: {e}")
        return {}

    def _save_settings(self):
        try:
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logging.error(f"Не вдалося зберегти налаштування в {self.settings_path}: {e}")

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self._save_settings()

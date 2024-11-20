import os
import json

FAVORITES_FILE = "favorites.json"

class FavoritesManager:
    def __init__(self):
        # Завантажуємо існуючі улюблені відео та канали
        self.favorites = self.load_favorites()

    def load_favorites(self):
        """Завантажуємо улюблені відео та канали з файлу"""
        if os.path.exists(FAVORITES_FILE):
            with open(FAVORITES_FILE, "r") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {"videos": [], "channels": []}
        else:
            return {"videos": [], "channels": []}

    def save_favorites(self):
        """Зберігаємо улюблені відео та канали до файлу"""
        with open(FAVORITES_FILE, "w") as f:
            json.dump(self.favorites, f, indent=4)

    def add_video(self, video_id, title, url):
        """Додаємо відео до улюблених"""
        favorite_video = {
            "video_id": video_id,
            "title": title,
            "url": url
        }
        self.favorites['videos'].append(favorite_video)
        self.save_favorites()

    def add_channel(self, channel_id, name, url):
        """Додаємо канал до улюблених"""
        favorite_channel = {
            "channel_id": channel_id,
            "name": name,
            "url": url
        }
        self.favorites['channels'].append(favorite_channel)
        self.save_favorites()

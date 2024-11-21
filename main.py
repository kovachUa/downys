import gi
import json
from pathlib import Path
from gi.repository import Gtk
from scripts import youtube
from scripts.upload_server import upload_file_to_server
from ui.ffmpeg_menu import FFmpegMenu

gi.require_version('Gtk', '3.0')

BUFFER_SIZE = 4096
CONFIG_FILE = "config.json"

class DownysApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="Downys")
        self.set_default_size(400, 250)
        self.set_resizable(False)

        # Load server configuration
        self.host, self.port, self.sleep_interval, self.max_sleep_interval, self.output_dir = self.load_server_config()

        # Initialize the favorites list
        self.favorites = self.load_favorites()

        # Main UI layout
        grid = Gtk.Grid(column_spacing=10, row_spacing=5)
        self.add(grid)

        # URL input field
        self.url_entry = Gtk.Entry()
        grid.attach(self.create_label("URL:"), 0, 0, 1, 1)
        grid.attach(self.url_entry, 1, 0, 2, 1)

        # Buttons
        self.httrack_button = self.create_button("HTTrack", self.on_httrack_clicked)
        grid.attach(self.httrack_button, 0, 1, 1, 1)

        self.youtube_button = self.create_button("YouTube", self.on_youtube_clicked)
        grid.attach(self.youtube_button, 1, 1, 1, 1)

        self.upload_button = self.create_button("Завантажити на сервер", self.on_upload_clicked)
        grid.attach(self.upload_button, 2, 1, 1, 1)

        self.ffmpeg_button = self.create_button("FFmpeg", self.on_ffmpeg_clicked)
        grid.attach(self.ffmpeg_button, 1, 2, 1, 1)

        # Progress bar
        self.progress_bar = Gtk.ProgressBar()
        grid.attach(self.progress_bar, 0, 3, 3, 1)

        # Settings button
        self.settings_button = Gtk.Button(label="Налаштування")
        self.settings_button.connect("clicked", self.on_server_settings_clicked)
        grid.attach(self.settings_button, 0, 4, 1, 1)

    def create_label(self, text):
        return Gtk.Label(label=text)

    def create_button(self, label, handler):
        button = Gtk.Button(label=label)
        button.connect("clicked", handler)
        return button

    # Button actions
    def on_httrack_clicked(self, widget):
        self.run_httrack_script()

    def on_youtube_clicked(self, widget):
        self.run_youtube_script()

    def on_upload_clicked(self, widget):
        self.run_upload_script()

    def on_ffmpeg_clicked(self, widget):
        ffmpeg_menu = FFmpegMenu(self)
        ffmpeg_menu.show_all()

    def on_server_settings_clicked(self, widget):
        dialog = Gtk.Dialog("Налаштування сервера", self, Gtk.DialogFlags.MODAL,
                            ("Скасувати", Gtk.ResponseType.CANCEL, "Зберегти", Gtk.ResponseType.OK))
        dialog.set_default_size(300, 200)

        # Fields for server settings
        host_entry = Gtk.Entry(text=self.host)
        port_entry = Gtk.Entry(text=str(self.port))
        sleep_interval_entry = Gtk.Entry(text=str(self.sleep_interval))
        max_sleep_interval_entry = Gtk.Entry(text=str(self.max_sleep_interval))
        output_dir_entry = Gtk.Entry(text=self.output_dir)

        box = dialog.get_content_area()
        box.add(self.create_label("Адреса сервера:"))
        box.add(host_entry)
        box.add(self.create_label("Порт сервера:"))
        box.add(port_entry)
        box.add(self.create_label("Інтервал (с):"))
        box.add(sleep_interval_entry)
        box.add(self.create_label("Макс. інтервал (с):"))
        box.add(max_sleep_interval_entry)
        box.add(self.create_label("Папка для завантажень:"))
        box.add(output_dir_entry)

        dialog.show_all()

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.host = host_entry.get_text().strip()
            self.port = int(port_entry.get_text().strip())
            self.sleep_interval = float(sleep_interval_entry.get_text().strip())
            self.max_sleep_interval = float(max_sleep_interval_entry.get_text().strip())
            self.output_dir = output_dir_entry.get_text().strip()
            self.save_server_config(self.host, self.port, self.sleep_interval, self.max_sleep_interval, self.output_dir)
        dialog.destroy()

    # Script logic
    def run_httrack_script(self):
        from scripts import httrack
        httrack.run_httrack()

    def run_youtube_script(self):
        url = self.url_entry.get_text().strip()
        if not url:
            self.show_warning_dialog("Будь ласка, введіть URL.")
            return

        result = youtube.download_youtube_video(url)
        
        # Перевірка результату
        if result and isinstance(result, tuple) and len(result) == 2:
            uploader, title = result
            uploader = uploader or "Unknown_Uploader"
            title = title or "Unknown_Title"

            video_path = f'{self.output_dir}/{uploader}/{title}.mp4'
            upload_file_to_server(self.host, self.port, video_path)

            # Показуємо тільки повідомлення про успішне завантаження
            self.show_info_dialog(f"Відео '{title}' успішно завантажено!")
        else:
            # Показуємо повідомлення про помилку тільки якщо результат некоректний
            self.show_warning_dialog("Відео завантаженно.")

    def run_upload_script(self):
        dialog = Gtk.FileChooserDialog("Оберіть файл для завантаження", self, Gtk.FileChooserAction.OPEN,
                                       ("Скасувати", Gtk.ResponseType.CANCEL, "Відкрити", Gtk.ResponseType.OK))
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            file_path = dialog.get_filename()
            upload_file_to_server(self.host, self.port, file_path)
        dialog.destroy()

    def show_warning_dialog(self, message):
        dialog = Gtk.MessageDialog(self, modal=True, message_type=Gtk.MessageType.WARNING,
                                   buttons=Gtk.ButtonsType.OK, text=message)
        dialog.run()
        dialog.destroy()

    def show_info_dialog(self, message):
        dialog = Gtk.MessageDialog(self, modal=True, message_type=Gtk.MessageType.INFO,
                                   buttons=Gtk.ButtonsType.OK, text=message)
        dialog.run()
        dialog.destroy()

    def load_server_config(self):
        config_file = Path(CONFIG_FILE)
        if config_file.exists():
            with config_file.open("r") as f:
                config = json.load(f)
                return config.get("host", "localhost"), config.get("port", 12345), config.get("sleep_interval", 0.02), config.get("max_sleep_interval", 0.05), config.get("output_dir", "./downloads")
        return "localhost", 12345, 0.02, 0.05, "./downloads"

    def save_server_config(self, host, port, sleep_interval, max_sleep_interval, output_dir):
        config = {
            "host": host,
            "port": port,
            "sleep_interval": sleep_interval,
            "max_sleep_interval": max_sleep_interval,
            "output_dir": output_dir
        }
        with Path(CONFIG_FILE).open("w") as f:
            json.dump(config, f)

    def load_favorites(self):
        favorites_file = Path("favorites.json")
        if favorites_file.exists():
            with favorites_file.open("r") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return []
        return []

if __name__ == "__main__":
    app = DownysApp()
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()

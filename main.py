import gi
import json
from pathlib import Path
from gi.repository import Gtk
from scripts.youtube_viewer import YouTubeViewer
from scripts import youtube
from scripts.upload_server import upload_file_to_server
from ui.ffmpeg_menu import FFmpegMenu

gi.require_version('Gtk', '3.0')

BUFFER_SIZE = 4096
CONFIG_FILE = "config.json"

class DownysApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="Downys")
        self.set_default_size(400, 200)
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

        self.upload_button = self.create_button("Upload to Server", self.on_upload_clicked)
        grid.attach(self.upload_button, 2, 1, 1, 1)

        self.youtube_viewer_button = self.create_button("YouTube Viewer", self.on_youtube_viewer_clicked)  # New button
        grid.attach(self.youtube_viewer_button, 0, 2, 1, 1)

        self.ffmpeg_button = self.create_button("FFmpeg", self.on_ffmpeg_clicked)
        grid.attach(self.ffmpeg_button, 1, 2, 1, 1)

        # Progress bar
        self.progress_bar = Gtk.ProgressBar()
        grid.attach(self.progress_bar, 0, 3, 3, 1)

        # Settings button
        self.settings_button = Gtk.Button(label="Settings")
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

    def on_youtube_viewer_clicked(self, widget):
        url = self.url_entry.get_text().strip()  # Get the URL from the input field
        if not url:
            self.show_warning_dialog("Please enter a YouTube URL.")  # Warn if the URL is empty
            return

        viewer = YouTubeViewer(url)  # Pass the URL to the YouTube Viewer
        viewer.show_all()

    def on_ffmpeg_clicked(self, widget):
        ffmpeg_menu = FFmpegMenu(self)
        ffmpeg_menu.show_all()

    def on_server_settings_clicked(self, widget):
        self.open_server_settings()

    # Script logic
    def run_httrack_script(self):
        from scripts import httrack
        httrack.run_httrack()  # Викликаємо функцію без використання os.system

    def run_youtube_script(self):
        url = self.url_entry.get_text().strip()
        if not url:
            self.show_warning_dialog("Please enter a URL.")
            return

        # Call the download function and check if it returns valid data
        result = youtube.download_youtube_video(url)

        # Ensure the result is not None and has the expected structure
        if result:
            uploader, title = result  # Unpack the result
            # Ensure the uploader and title are valid
            if not uploader:
                uploader = "Unknown_Uploader"
            if not title:
                title = "Unknown_Title"

            # Construct the video path and upload it
            video_path = f'{self.output_dir}/{uploader}/{title}.mp4'
            upload_file_to_server(self.host, self.port, video_path)

            # Show a success dialog
            self.show_info_dialog(f"Video '{title}' downloaded and uploaded successfully!")
        else:
            # If download failed, just show a generic failure dialog (without the 'Failed' message)
            self.show_warning_dialog("Video uploaded.")

    def run_upload_script(self):
        dialog = Gtk.FileChooserDialog("Choose a file to upload", self, Gtk.FileChooserAction.OPEN,
                                       ("Cancel", Gtk.ResponseType.CANCEL, "Open", Gtk.ResponseType.OK))
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            file_path = dialog.get_filename()
            upload_file_to_server(self.host, self.port, file_path)
        dialog.destroy()

    def open_server_settings(self):
        dialog = Gtk.Dialog("Server Settings", self, Gtk.DialogFlags.MODAL,
                            ("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK))
        host_entry = Gtk.Entry(text=self.host)
        port_entry = Gtk.Entry(text=str(self.port))
        sleep_interval_entry = Gtk.Entry(text=str(self.sleep_interval))
        max_sleep_interval_entry = Gtk.Entry(text=str(self.max_sleep_interval))
        output_dir_entry = Gtk.Entry(text=self.output_dir)

        box = dialog.get_content_area()
        box.add(Gtk.Label(label="Server Address:"))
        box.add(host_entry)
        box.add(Gtk.Label(label="Server Port:"))
        box.add(port_entry)
        box.add(Gtk.Label(label="Sleep Interval:"))
        box.add(sleep_interval_entry)
        box.add(Gtk.Label(label="Max Sleep Interval:"))
        box.add(max_sleep_interval_entry)
        box.add(Gtk.Label(label="Output Directory:"))
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

    def show_warning_dialog(self, message):
        # Updated deprecated constructor warning
        dialog = Gtk.MessageDialog(
            self,
            Gtk.DialogFlags.MODAL,
            Gtk.MessageType.WARNING,
            Gtk.ButtonsType.OK,
            text=message  # Replaced 'message_format' with 'text'
        )
        dialog.run()
        dialog.destroy()

    def show_info_dialog(self, message):
        # Success dialog to show when the video is successfully downloaded
        dialog = Gtk.MessageDialog(
            self,
            Gtk.DialogFlags.MODAL,
            Gtk.MessageType.INFO,
            Gtk.ButtonsType.OK,
            text=message
        )
        dialog.run()
        dialog.destroy()

    def load_server_config(self):
        config_file = Path(CONFIG_FILE)  # Створюємо об'єкт Path для файлу конфігурації
        if config_file.exists():  # Перевіряємо, чи існує файл
            with config_file.open("r") as f:  # Відкриваємо файл для читання
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
        config_file = Path(CONFIG_FILE)
        with config_file.open("w") as f:  # Використовуємо `open` на об'єкті Path
            json.dump(config, f)

    def load_favorites(self):
        favorites_file = Path("favorites.json")  # Створюємо об'єкт Path для файлу улюблених
        if favorites_file.exists():
            with favorites_file.open("r") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return []
        return []

    def save_favorites(self):
        favorites_file = Path("favorites.json")
        with favorites_file.open("w") as f:
            json.dump(self.favorites, f)

if __name__ == "__main__":
    app = DownysApp()
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()

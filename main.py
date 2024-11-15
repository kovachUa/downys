import gi
import os
import json
import subprocess
from gi.repository import Gtk
from scripts import youtube
from scripts.upload_server import upload_file_to_server
from ui.ffmpeg_menu import FFmpegMenu  # Import FFmpeg menu from ui/ffmpeg_menu.py

gi.require_version('Gtk', '3.0')

BUFFER_SIZE = 4096
CONFIG_FILE = "config.json"

class DownysApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="Downys")
        self.set_default_size(400, 200)
        self.set_resizable(False)

        # Load server configuration
        self.host, self.port = self.load_server_config()

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

        self.ffmpeg_button = self.create_button("FFmpeg", self.on_ffmpeg_clicked)  # New FFmpeg button
        grid.attach(self.ffmpeg_button, 0, 2, 1, 1)

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

    def on_ffmpeg_clicked(self, widget):
        ffmpeg_menu = FFmpegMenu(self)  # Create FFmpeg settings menu window
        ffmpeg_menu.show_all()  # Display the FFmpeg menu window

    def on_server_settings_clicked(self, widget):
        self.open_server_settings()

    # Script logic
    def run_httrack_script(self):
        os.system("python3 scripts/httrack.py")

    def run_youtube_script(self):
        url = self.url_entry.get_text().strip()
        if not url:
            self.show_warning_dialog("Please enter a URL.")
            return
        uploader = youtube.download_youtube_video(url)
        video_path = f'./downloads/{uploader}/{os.path.basename(url)}.mp4'
        upload_file_to_server(self.host, self.port, video_path)

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

        box = dialog.get_content_area()
        box.add(Gtk.Label(label="Server Address:"))
        box.add(host_entry)
        box.add(Gtk.Label(label="Server Port:"))
        box.add(port_entry)

        dialog.show_all()

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.host = host_entry.get_text().strip()
            self.port = int(port_entry.get_text().strip())
            self.save_server_config(self.host, self.port)
        dialog.destroy()

    def show_warning_dialog(self, message):
        dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, message)
        dialog.run()
        dialog.destroy()

    def load_server_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                return config.get("host", "localhost"), config.get("port", 12345)
        return "localhost", 12345

    def save_server_config(self, host, port):
        config = {"host": host, "port": port}
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f)


if __name__ == "__main__":
    app = DownysApp()
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()

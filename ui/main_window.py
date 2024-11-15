import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from scripts.media_conversion import convert_video, convert_audio  # Import functions

class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Downys")

        # Set up main layout
        vbox = Gtk.VBox(spacing=10)
        self.add(vbox)

        # URL input field
        hbox_url = Gtk.HBox(spacing=5)
        vbox.pack_start(hbox_url, False, False, 0)
        
        self.url_label = Gtk.Label(label="URL:")
        hbox_url.pack_start(self.url_label, False, False, 0)
        
        self.url_entry = Gtk.Entry()
        hbox_url.pack_start(self.url_entry, True, True, 0)

        # Buttons
        self.httrack_button = Gtk.Button(label="HTTrack")
        vbox.pack_start(self.httrack_button, False, False, 0)
        
        self.youtube_button = Gtk.Button(label="YouTube")
        vbox.pack_start(self.youtube_button, False, False, 0)
        
        self.upload_button = Gtk.Button(label="Upload to Server")
        vbox.pack_start(self.upload_button, False, False, 0)
        
        self.server_settings_button = Gtk.Button(label="Server Settings")
        vbox.pack_start(self.server_settings_button, False, False, 0)

        # Add new buttons for conversion
        self.convert_video_button = Gtk.Button(label="Convert Video")
        self.convert_audio_button = Gtk.Button(label="Convert Audio")
        
        vbox.pack_start(self.convert_video_button, False, False, 0)
        vbox.pack_start(self.convert_audio_button, False, False, 0)

        # Connect buttons to functions
        self.convert_video_button.connect("clicked", self.on_convert_video)
        self.convert_audio_button.connect("clicked", self.on_convert_audio)

        # Progress Bar
        self.progress_bar = Gtk.ProgressBar()
        vbox.pack_start(self.progress_bar, False, False, 0)

    def on_convert_video(self, widget):
        # Example input/output for video conversion
        input_file = "input_video.mkv"  # Replace with actual path or URL
        output_file = "output_video.mp4"
        convert_video(input_file, output_file)
        
    def on_convert_audio(self, widget):
        # Example input/output for audio conversion
        input_file = "input_audio.mp4"  # Replace with actual path or URL
        output_file = "output_audio.aac"
        convert_audio(input_file, output_file)

    def show_warning_dialog(self, message):
        dialog = Gtk.MessageDialog(
            self,
            0,
            Gtk.MessageType.WARNING,
            Gtk.ButtonsType.OK,
            "Warning",
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

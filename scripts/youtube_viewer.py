import gi
import os
import json
from scripts.youtube import download_youtube_video
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, WebKit2, Gio

FAVORITES_FILE = "favorites.json"

class YouTubeViewer(Gtk.Window):
    def __init__(self, url):
        super().__init__(title="YouTube Viewer")
        self.set_default_size(800, 600)

        # Main layout
        vbox = Gtk.VBox(spacing=5)
        self.add(vbox)

        # Web view
        self.webview = WebKit2.WebView()
        self.webview.load_uri(url)
        vbox.pack_start(self.webview, True, True, 0)

        # Buttons
        hbox = Gtk.HBox(spacing=5)
        vbox.pack_start(hbox, False, False, 0)

        self.download_button = Gtk.Button(label="Download Video")
        self.download_button.connect("clicked", self.on_download_clicked)
        hbox.pack_start(self.download_button, False, False, 0)

        self.favorite_button = Gtk.Button(label="Add to Favorites")
        self.favorite_button.connect("clicked", self.on_favorite_clicked)
        hbox.pack_start(self.favorite_button, False, False, 0)

        self.add_channel_button = Gtk.Button(label="Add Channel")
        self.add_channel_button.connect("clicked", self.on_add_channel_clicked)
        hbox.pack_start(self.add_channel_button, False, False, 0)

        # Save URL
        self.current_url = url

        # After the page is loaded, fetch video and channel names
        self.webview.connect("load-changed", self.on_page_loaded)

    def on_page_loaded(self, webview, event):
        if event == WebKit2.LoadEvent.COMMITTED:
            self.get_video_and_channel_info()

    def get_video_and_channel_info(self):
        # JavaScript code to extract video title and channel name
        js_code = """
        var videoTitle = document.title;
        var channelName = document.querySelector('ytd-channel-name #text').innerText;
        videoTitle + '|' + channelName;
        """

        # Execute the JavaScript to get the information
        self.webview.run_javascript(js_code, None, self.on_js_execution_complete)

    def on_js_execution_complete(self, result):
        # Extract video title and channel name
        video_title, channel_name = result.split("|", 1)

        # Print the video title and channel name
        print(f"Video Title: {video_title}")
        print(f"Channel Name: {channel_name}")

        # Optionally, display the video title and channel name in the window's title
        self.set_title(f"{video_title} - {channel_name}")

    def on_download_clicked(self, widget):
        download_youtube_video(self.current_url)
        dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, "Download Started")
        dialog.format_secondary_text("The video is being downloaded.")
        dialog.run()
        dialog.destroy()

    def on_favorite_clicked(self, widget):
        if not os.path.exists(FAVORITES_FILE):
            with open(FAVORITES_FILE, "w") as f:
                json.dump({"videos": []}, f)

        with open(FAVORITES_FILE, "r") as f:
            favorites = json.load(f)

        if self.current_url not in favorites["videos"]:
            favorites["videos"].append(self.current_url)

        with open(FAVORITES_FILE, "w") as f:
            json.dump(favorites, f)

        dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, "Added to Favorites")
        dialog.format_secondary_text("The video has been added to your favorites.")
        dialog.run()
        dialog.destroy()

    def on_add_channel_clicked(self, widget):
        channel_url = "/".join(self.current_url.split("/")[:-1])  # Extract channel URL
        dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, "Channel Added")
        dialog.format_secondary_text(f"Channel {channel_url} has been added to your list.")
        dialog.run()
        dialog.destroy()

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import os
import sys
import subprocess
import math

class BasePage:
    def __init__(self, app_window, url_handler):
        self.app = app_window
        self.url_handler = url_handler
        self.page_widget = None

    def build_ui(self):
        raise NotImplementedError

    def get_page_widget(self):
        return self.page_widget

    def _start_task(self, *args, **kwargs):
        self.app._start_task_with_callbacks(*args, **kwargs)

    def _select_file_dialog(self, entry_widget, title, save_mode=False):
        self.app._select_file_dialog(entry_widget, title, save_mode=save_mode)

    def _select_folder_dialog(self, entry_widget, title):
        self.app._select_folder_dialog(entry_widget, title)

    def show_warning_dialog(self, message):
        self.app.show_warning_dialog(message)
    
    def show_info_dialog(self, title, message):
        self.app.show_info_dialog(title, message)
        
    def _format_size(self, size_bytes):
        if size_bytes == 0:
            return "0 B"
        size_name = ("B", "KB", "MB", "GB", "TB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_name[i]}"
        
    def _open_path_externally(self, path):
        try:
            if sys.platform == "win32":
                os.startfile(os.path.realpath(path))
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=True)
            else:
                subprocess.run(["xdg-open", path], check=True)
        except (OSError, FileNotFoundError, subprocess.CalledProcessError) as e:
            self.show_warning_dialog(f"Не вдалося відкрити шлях '{path}':\n{e}")

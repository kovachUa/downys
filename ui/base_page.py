# scripts/ui/base_page.py

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

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

    def _select_file_dialog(self, *args, **kwargs):
        self.app._select_file_dialog(*args, **kwargs)

    def _select_folder_dialog(self, *args, **kwargs):
        self.app._select_folder_dialog(*args, **kwargs)

    def show_warning_dialog(self, *args, **kwargs):
        self.app.show_warning_dialog(*args, **kwargs)
    
    def show_info_dialog(self, *args, **kwargs):
        self.app.show_info_dialog(*args, **kwargs)

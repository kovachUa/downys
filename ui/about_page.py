# scripts/ui/about_page.py

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Pango

from .base_page import BasePage

class AboutPage(BasePage):
    def build_ui(self):
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        self.page_widget.pack_start(Gtk.Label(label="<b><big>Про програму</big></b>", use_markup=True), False, False, 0)
        
        about_text = """<b>DownYS</b> - багатофункціональна програма для роботи з контентом.
<b>Можливості:</b>
 • Завантаження відео з YouTube (yt-dlp)
 • Конвертація відео/аудіо (FFmpeg)
 • Віддзеркалення веб-сайтів (HTTrack)
 • Архівування директорій (tar.gz)
 • Закладки URL
<b>Вимоги:</b> Python 3.x, PyGObject (GTK 3), yt-dlp, FFmpeg, HTTrack
<i>Переконайтеся, що залежності встановлені та доступні у PATH.</i>"""
        
        label = Gtk.Label(label=about_text, use_markup=True, justify=Gtk.Justification.LEFT, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, xalign=0.0)
        label.set_selectable(True) 
        self.page_widget.pack_start(label, False, False, 5) 
        
        return self.page_widget

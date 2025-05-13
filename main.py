#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango
import os
import json
import subprocess
import re
import shutil
import threading
from urllib.parse import urlparse
import time
import datetime
import pprint # Used for debugging if needed
import sys # For sys.platform for opening files

try:
    # Import task functions and page classes from script files
    from scripts.youtube import download_youtube_media, extract_youtube_info
    # Файл upload_server.py та імпорт з нього видалено
    from scripts.httrack_tasks import run_httrack_web_threaded, archive_directory_threaded
    from scripts.ffmpeg_tasks import run_ffmpeg_task
except ImportError as e:
     print(f"Помилка імпорту скриптів: {e}")
     print("Переконайтеся, що файли *.py знаходяться в папці 'scripts' поруч з main.py")
     exit(1)

try:
    # Import BookmarksPage, attempting relative import first, then direct
    from scripts.bookmarks_page import BookmarksPage
except ImportError:
    try:
        from bookmarks_page import BookmarksPage
    except ImportError as e:
         print(f"Помилка імпорту BookmarksPage: {e}")
         print("Переконайтеся, що файл 'bookmarks_page.py' знаходиться поруч з main.py або в папці 'scripts'")
         exit(1)


# --- FFmpeg Task Definitions ---
FFMPEG_TASKS = {
    "Відео -> MP4 (Просто)": {"type": "convert_simple","output_ext": ".mp4","params": []},
    "Відео -> AVI": {"type": "convert_format","output_ext": ".avi","params": []},
    "Відео -> Аудіо (AAC)": {"type": "extract_audio_aac","output_ext": ".aac","params": []},
    "Відео -> Аудіо (MP3)": {"type": "extract_audio_mp3","output_ext": ".mp3","params": []},
    "Стиснути Відео (Бітрейт)": {"type": "compress_bitrate","output_ext": ".mp4","params": [{"name": "bitrate", "label": "Відео Бітрейт (напр., 1M)", "type": "entry", "default": "1M", "required": True}]},
    "Змінити Роздільну здатність": {"type": "adjust_resolution","output_ext": ".mp4","params": [{"name": "width", "label": "Ширина", "type": "entry", "default": "1280", "required": True},{"name": "height", "label": "Висота", "type": "entry", "default": "720", "required": True}]}
}

# --- Utility Classes ---

class URLHandler:
    def __init__(self):
        pass

    def validate_httrack_url(self, url_string):
        if not url_string:
            raise ValueError("URL не може бути порожнім.")
        try:
            parsed_url = urlparse(url_string)
            allowed_schemes = ('http', 'https', 'ftp')
            if not parsed_url.scheme or parsed_url.scheme.lower() not in allowed_schemes:
                raise ValueError(f"Непідтримувана схема URL (очікується {', '.join(allowed_schemes)}).")
            if not parsed_url.netloc: 
                raise ValueError("Відсутнє ім'я хоста (домен) в URL.")
            return True
        except ValueError as e: 
             raise ValueError(f"Неприпустимий URL: {e}")
        except Exception as e: 
             raise ValueError(f"Не вдалося проаналізувати URL '{url_string}': {e}")

    def get_hostname_from_url(self, url_string, sanitize=True):
        if not url_string:
            return None
        try:
            parsed_url = urlparse(url_string)
            hostname = parsed_url.hostname
            if hostname:
                if hostname.startswith("www."):
                     hostname = hostname[4:]
                if sanitize:
                    hostname = re.sub(r'[^\w.-]+', '_', hostname).strip('_')
                    if not hostname: 
                        return None
                return hostname
            return None 
        except Exception as e:
            print(f"Warning: Could not parse URL '{url_string}' for hostname: {e}")
            return None

# --- Base Class for Application Pages ---

class BasePage:
    def __init__(self, app_window, url_handler):
        self.app = app_window        
        self.url_handler = url_handler 
        self.page_widget = None      

    def build_ui(self):
        raise NotImplementedError

    def _start_task(self, *args, **kwargs):
        self.app._start_task_with_callbacks(*args, **kwargs) # Виправлено на новий метод

    def _select_file_dialog(self, *args, **kwargs):
        self.app._select_file_dialog(*args, **kwargs)

    def _select_folder_dialog(self, *args, **kwargs):
        self.app._select_folder_dialog(*args, **kwargs)

    def show_warning_dialog(self, *args, **kwargs):
         self.app.show_warning_dialog(*args, **kwargs)
    
    def show_info_dialog(self, *args, **kwargs): 
         self.app.show_info_dialog(*args, **kwargs)

    def get_page_widget(self):
         if hasattr(self, 'page_widget') and isinstance(self.page_widget, Gtk.Widget):
             return self.page_widget
         elif self.page_widget is not None: 
             return self.page_widget
         print(f"Warning: get_page_widget called on {type(self).__name__} but page_widget is not set or invalid.")
         return None

# --- Page Implementations ---

class YouTubePage(BasePage):
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        self.url_entry = None
        self.output_dir_entry = None
        self.download_button = None
        self.format_combo = None
        self.audio_format_label = None
        self.audio_format_combo = None
        self.download_subs_check = None
        self.sub_langs_label = None
        self.sub_langs_entry = None
        self.embed_subs_check = None
        self.file_list_store = None
        self.file_tree_view = None
        self.btn_refresh_files = None
        self.btn_open_selected_file = None
        self.btn_open_output_dir_fs = None

    def _open_path_externally(self, item_path):
        if not item_path:
            self.show_warning_dialog("Шлях для відкриття не вказано.")
            return
        try:
            if sys.platform == "win32":
                subprocess.run(['start', '', item_path], check=True, shell=True)
            elif sys.platform == "darwin": 
                subprocess.run(['open', item_path], check=True)
            else: 
                subprocess.run(['xdg-open', item_path], check=True)
            GLib.idle_add(self.app.status_label.set_text, f"Спроба відкрити: {os.path.basename(item_path)}")
        except FileNotFoundError as e:
            err_cmd = e.cmd if hasattr(e, 'cmd') else (e.args[0] if e.args else "Невідома команда")
            err_msg = f"Помилка: Команду для відкриття файлу/папки не знайдено ('{err_cmd}')."
            print(err_msg)
            self.show_warning_dialog(err_msg)
        except subprocess.CalledProcessError as e:
            err_msg = f"Не вдалося відкрити '{os.path.basename(item_path)}'. Код: {e.returncode}."
            print(err_msg)
            self.show_warning_dialog(err_msg)
        except Exception as e:
            err_msg = f"Неочікувана помилка при спробі відкрити '{os.path.basename(item_path)}': {e}"
            print(err_msg)
            self.show_warning_dialog(err_msg)

    def _format_size(self, size_bytes):
        if size_bytes is None: return ""
        if size_bytes < 0: return "N/A"
        if size_bytes < 1024: return f"{size_bytes} B"
        elif size_bytes < 1024**2: return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024**3: return f"{size_bytes/1024**2:.1f} MB"
        else: return f"{size_bytes/1024**3:.1f} GB"

    def _populate_file_browser(self, widget=None): 
        if not self.file_list_store or not self.output_dir_entry: return
        self.file_list_store.clear()
        directory_path = self.output_dir_entry.get_text().strip()
        if not directory_path: return
        if not os.path.isdir(directory_path):
            self.file_list_store.append([f"'{os.path.basename(directory_path)}'", "Директорія не знайдена", "", directory_path])
            return
        try:
            items = sorted(os.listdir(directory_path))
            if not items:
                self.file_list_store.append([None, "Папка порожня", None, None])
            for item_name in items:
                full_path = os.path.join(directory_path, item_name)
                try:
                    if os.path.isdir(full_path):
                        item_type, item_size_str = "Папка", ""
                    elif os.path.isfile(full_path):
                        item_type, item_size_str = "Файл", self._format_size(os.path.getsize(full_path))
                    else:
                        item_type, item_size_str = "Інше", ""
                    self.file_list_store.append([item_name, item_type, item_size_str, full_path])
                except OSError:
                     self.file_list_store.append([item_name, "Недоступно", "", full_path])
        except OSError as e:
            self.file_list_store.append([f"Помилка доступу до '{os.path.basename(directory_path)}'", str(e), "", directory_path])

    def build_ui(self):
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        self.page_widget.pack_start(Gtk.Label(label="<b><big>Завантаження YouTube</big></b>", use_markup=True), False, False, 0)
        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        self.page_widget.pack_start(grid, False, False, 0)
        grid.attach(Gtk.Label(label="URL відео/списку:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.url_entry = Gtk.Entry(hexpand=True, placeholder_text="Вставте URL відео або плейлиста YouTube")
        grid.attach(self.url_entry, 1, 0, 3, 1)
        grid.attach(Gtk.Label(label="Дир. збереження:", halign=Gtk.Align.END), 0, 1, 1, 1)
        self.output_dir_entry = Gtk.Entry(hexpand=True)
        self.output_dir_entry.connect("changed", self._populate_file_browser) 
        grid.attach(self.output_dir_entry, 1, 1, 2, 1)
        btn_out = Gtk.Button(label="...")
        btn_out.connect("clicked", lambda w: self._select_folder_dialog(self.output_dir_entry, "Оберіть директорію"))
        grid.attach(btn_out, 3, 1, 1, 1)
        grid.attach(Gtk.Label(label="Формат/Якість:", halign=Gtk.Align.END), 0, 2, 1, 1)
        self.format_combo = Gtk.ComboBoxText()
        formats = {"best": "Найкраще Відео+Аудіо (WebM/MKV)", "best_mp4": "Найкраще Відео+Аудіо (MP4)", "audio_best": "Лише аудіо (Найкраще)", "audio_mp3": "Лише аудіо (MP3)", "audio_m4a": "Лише аудіо (M4A/AAC)"}
        for key, value in formats.items(): self.format_combo.append(key, value)
        self.format_combo.set_active_id("best") 
        self.format_combo.connect("changed", self._on_format_changed)
        grid.attach(self.format_combo, 1, 2, 3, 1)
        self.audio_format_label = Gtk.Label(label="Аудіо кодек:", halign=Gtk.Align.END)
        self.audio_format_combo = Gtk.ComboBoxText()
        audio_formats = ['best', 'mp3', 'aac', 'm4a', 'opus', 'vorbis', 'wav']
        for fmt in audio_formats: self.audio_format_combo.append(fmt, fmt.upper())
        self.audio_format_combo.set_active_id("best")
        grid.attach(self.audio_format_label, 0, 3, 1, 1)
        grid.attach(self.audio_format_combo, 1, 3, 3, 1)
        self.download_subs_check = Gtk.CheckButton(label="Завантажити субтитри")
        self.download_subs_check.connect("toggled", self._on_subs_toggled)
        grid.attach(self.download_subs_check, 0, 4, 2, 1)
        self.sub_langs_label = Gtk.Label(label="Мови суб. (через кому):", halign=Gtk.Align.END)
        self.sub_langs_entry = Gtk.Entry(text="uk,en")
        grid.attach(self.sub_langs_label, 2, 4, 1, 1)
        grid.attach(self.sub_langs_entry, 3, 4, 1, 1)
        self.embed_subs_check = Gtk.CheckButton(label="Вбудувати субтитри (якщо можливо)")
        grid.attach(self.embed_subs_check, 0, 5, 2, 1)
        self.download_button = Gtk.Button(label="Завантажити")
        self.download_button.connect("clicked", self._on_download_clicked)
        self.page_widget.pack_start(self.download_button, False, False, 5)
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL, margin_top=10, margin_bottom=5)
        self.page_widget.pack_start(sep, False, False, 0)
        browser_label = Gtk.Label(label="<b>Перегляд завантажених файлів:</b>", use_markup=True, xalign=0.0, margin_bottom=5)
        self.page_widget.pack_start(browser_label, False, False, 0)
        self.file_list_store = Gtk.ListStore(str, str, str, str)
        self.file_tree_view = Gtk.TreeView(model=self.file_list_store)
        self.file_tree_view.connect("row-activated", self._on_file_tree_view_row_activated)
        render_text = Gtk.CellRendererText()
        for i, title in enumerate(["Ім'я файлу", "Тип", "Розмір"]):
            col = Gtk.TreeViewColumn(title, render_text, text=i)
            col.set_sort_column_id(i)
            self.file_tree_view.append_column(col)
        scrolled_window_files = Gtk.ScrolledWindow(shadow_type=Gtk.ShadowType.IN, hexpand=True, vexpand=True)
        scrolled_window_files.set_min_content_height(150)
        scrolled_window_files.add(self.file_tree_view)
        self.page_widget.pack_start(scrolled_window_files, True, True, 0)
        browser_buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin_top=5)
        self.page_widget.pack_start(browser_buttons_box, False, False, 0)
        self.btn_refresh_files = Gtk.Button(label="Оновити список")
        self.btn_refresh_files.connect("clicked", self._populate_file_browser)
        browser_buttons_box.pack_start(self.btn_refresh_files, False, False, 0)
        self.btn_open_selected_file = Gtk.Button(label="Відкрити вибране")
        self.btn_open_selected_file.connect("clicked", self._on_open_selected_file_clicked)
        browser_buttons_box.pack_start(self.btn_open_selected_file, False, False, 0)
        self.btn_open_output_dir_fs = Gtk.Button(label="Відкрити папку завантажень")
        self.btn_open_output_dir_fs.connect("clicked", self._on_open_output_dir_fs_clicked)
        browser_buttons_box.pack_start(self.btn_open_output_dir_fs, False, False, 0)
        self._suggest_default_output_dir()
        self._update_options_visibility() 
        GLib.idle_add(self._populate_file_browser)
        self.page_widget.show_all()
        return self.page_widget

    def _on_file_tree_view_row_activated(self, treeview, path, column):
        model, iter_ = treeview.get_model(), treeview.get_model().get_iter(path)
        if iter_: self._open_path_externally(model.get_value(iter_, 3))

    def _on_open_selected_file_clicked(self, widget):
        model, iter_ = self.file_tree_view.get_selection().get_selected()
        if iter_: self._open_path_externally(model.get_value(iter_, 3))
        else: self.show_warning_dialog("Будь ласка, виберіть файл або папку.")

    def _on_open_output_dir_fs_clicked(self, widget):
        dir_path = self.output_dir_entry.get_text().strip()
        if dir_path and os.path.isdir(dir_path): self._open_path_externally(dir_path)
        elif dir_path: self.show_warning_dialog(f"Шлях не є директорією: {dir_path}")
        else: self.show_warning_dialog("Вкажіть директорію збереження.")

    def _suggest_default_output_dir(self):
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads", "YouTube_DownYS")
        if self.output_dir_entry and not self.output_dir_entry.get_text():
            self.output_dir_entry.set_text(default_dir)

    def _update_options_visibility(self):
        if not all([hasattr(self, w) and getattr(self, w) for w in ['format_combo', 'download_subs_check', 'audio_format_label', 'audio_format_combo', 'sub_langs_label', 'sub_langs_entry', 'embed_subs_check']]): return 
        format_id, is_audio, subs_active = self.format_combo.get_active_id(), False, self.download_subs_check.get_active()
        if format_id: is_audio = format_id.startswith("audio_")
        for w, v in [(self.audio_format_label, is_audio), (self.audio_format_combo, is_audio), (self.sub_langs_label, subs_active), (self.sub_langs_entry, subs_active), (self.embed_subs_check, subs_active and not is_audio)]: w.set_visible(v)

    def _on_format_changed(self, combo):
        self._update_options_visibility() 
        format_id = combo.get_active_id()
        if hasattr(self, 'audio_format_combo') and self.audio_format_combo:
            if format_id == "audio_mp3": self.audio_format_combo.set_active_id("mp3")
            elif format_id == "audio_m4a": self.audio_format_combo.set_active_id("m4a")
            elif format_id and format_id.startswith("audio_"): self.audio_format_combo.set_active_id("best")

    def _on_subs_toggled(self, check): self._update_options_visibility()

    def _on_download_clicked(self, widget):
        if self.app._is_task_running: self.show_warning_dialog("Завдання вже виконується."); return
        try:
            if not all([hasattr(self, w) and getattr(self, w) for w in ['url_entry', 'output_dir_entry', 'format_combo', 'audio_format_combo', 'download_subs_check', 'sub_langs_entry', 'embed_subs_check']]): raise RuntimeError("Віджети YouTube не ініціалізовані.")
            url, output_dir, format_selection = self.url_entry.get_text().strip(), self.output_dir_entry.get_text().strip(), self.format_combo.get_active_id() or "best"
            audio_format_override = self.audio_format_combo.get_active_id() if (self.format_combo.get_active_id() or "").startswith("audio_") else None
            download_subs, sub_langs, embed_subs = self.download_subs_check.get_active(), self.sub_langs_entry.get_text().strip(), self.embed_subs_check.get_active()
            if not url: raise ValueError("URL відео YouTube не може бути порожнім.")
            if not output_dir: raise ValueError("Оберіть директорію для збереження.")
            if download_subs and not sub_langs: self.show_warning_dialog("Не вказано мови субтитрів, використано стандартні (uk,en)."); sub_langs = "uk,en"
            if not os.path.isdir(output_dir): os.makedirs(output_dir, exist_ok=True)
            self._start_task(download_youtube_media, args=(url, output_dir), kwargs={'format_selection': format_selection, 'audio_format_override': audio_format_override, 'download_subs': download_subs, 'sub_langs': sub_langs, 'embed_subs': embed_subs}, success_callback=self._populate_file_browser)
        except (ValueError, RuntimeError, FileNotFoundError) as e: self.show_warning_dialog(str(e))
        except Exception as e: import traceback; traceback.print_exc(); self.show_warning_dialog(f"Неочікувана помилка YouTube: {e}")

class FFmpegPage(BasePage):
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        self.task_combo = None
        self.params_box = None      
        self.param_entries = {}     
        self.input_entry = None
        self.output_entry = None
        self.execute_button = None

    def build_ui(self):
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        self.page_widget.pack_start(Gtk.Label(label="<b><big>FFmpeg Конвертація</big></b>", use_markup=True), False, False, 0)
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self.page_widget.pack_start(grid, False, False, 0)
        grid.attach(Gtk.Label(label="Завдання FFmpeg:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.task_combo = Gtk.ComboBoxText()
        for label in FFMPEG_TASKS.keys(): self.task_combo.append_text(label)
        self.task_combo.set_active(0) 
        self.task_combo.connect("changed", self._on_task_changed)
        grid.attach(self.task_combo, 1, 0, 3, 1)
        self.params_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        grid.attach(self.params_box, 0, 1, 4, 1) 
        grid.attach(Gtk.Label(label="Вхідний файл:", halign=Gtk.Align.END), 0, 2, 1, 1)
        self.input_entry = Gtk.Entry(hexpand=True)
        self.input_entry.connect("changed", self._update_output_suggestion) 
        grid.attach(self.input_entry, 1, 2, 2, 1)
        btn_in = Gtk.Button(label="...")
        btn_in.connect("clicked", lambda w: self._select_file_dialog(self.input_entry, "Оберіть вхідний файл"))
        grid.attach(btn_in, 3, 2, 1, 1)
        grid.attach(Gtk.Label(label="Вихідний файл:", halign=Gtk.Align.END), 0, 3, 1, 1)
        self.output_entry = Gtk.Entry(hexpand=True)
        grid.attach(self.output_entry, 1, 3, 2, 1)
        btn_out = Gtk.Button(label="...")
        btn_out.connect("clicked", lambda w: self._select_file_dialog(self.output_entry, "Оберіть вихідний файл", save_mode=True))
        grid.attach(btn_out, 3, 3, 1, 1)
        self.execute_button = Gtk.Button(label="Виконати")
        self.execute_button.connect("clicked", self._on_execute_clicked)
        self.page_widget.pack_start(self.execute_button, False, False, 5) 
        self.page_widget.show_all()
        GLib.idle_add(self._on_task_changed, self.task_combo) 
        return self.page_widget

    def _on_task_changed(self, combo):
        selected_label = combo.get_active_text()
        if not selected_label: return
        task_info = FFMPEG_TASKS.get(selected_label)
        if not task_info: return
        if hasattr(self, 'params_box') and self.params_box:
             for widget in self.params_box.get_children(): self.params_box.remove(widget)
        self.param_entries = {} 
        if hasattr(self, 'params_box') and self.params_box:
             for param_spec in task_info.get("params", []):
                 hbox = Gtk.Box(spacing=5) 
                 hbox.pack_start(Gtk.Label(label=f"{param_spec['label']}:"), False, False, 0)
                 if param_spec["type"] == "entry":
                     entry = Gtk.Entry(text=param_spec.get("default", ""))
                     entry.set_hexpand(True) 
                     hbox.pack_start(entry, True, True, 0)
                     self.param_entries[param_spec["name"]] = entry
                 self.params_box.pack_start(hbox, False, False, 0)
             self.params_box.show_all() 
        self._update_output_suggestion()

    def _update_output_suggestion(self, *args):
        if not all([hasattr(self, w) and getattr(self, w) for w in ['input_entry', 'output_entry', 'task_combo']]): return
        input_path, output_path, active_task_label = self.input_entry.get_text().strip(), self.output_entry.get_text().strip(), self.task_combo.get_active_text()
        if not active_task_label: return 
        task_info = FFMPEG_TASKS.get(active_task_label)
        output_ext = task_info.get("output_ext", ".out") if task_info else ".out"
        update_needed, suggested_path = False, ""
        if input_path and os.path.isfile(input_path):
            input_dir, base = os.path.dirname(input_path) or ".", os.path.splitext(os.path.basename(input_path))[0]
            suggested_path = os.path.join(input_dir, f"{base}_converted{output_ext}")
            if not output_path: update_needed = True
            else:
                 out_dir, out_base, out_ext_curr = os.path.dirname(output_path), *os.path.splitext(os.path.basename(output_path))
                 if out_dir == input_dir and (out_base.startswith(f"{base}_converted") or out_ext_curr.lower() != output_ext.lower()): update_needed = True
        elif not input_path and not output_path:
            suggested_path, update_needed = os.path.join(os.path.expanduser("~"), f"output_converted{output_ext}"), True
        if update_needed and suggested_path: self.output_entry.set_text(suggested_path)

    def _on_execute_clicked(self, widget):
        if self.app._is_task_running: self.show_warning_dialog("Завдання вже виконується."); return
        try:
            if not all([hasattr(self, w) and getattr(self, w) for w in ['task_combo', 'input_entry', 'output_entry']]): raise RuntimeError("Віджети FFmpeg не ініціалізовані.")
            active_task_label = self.task_combo.get_active_text()
            if not active_task_label: raise ValueError("Оберіть завдання FFmpeg.")
            task_info = FFMPEG_TASKS.get(active_task_label);
            if not task_info: raise ValueError("Обрано невідоме завдання FFmpeg.")
            task_type, task_options = task_info["type"], {}
            for spec in task_info.get("params", []):
                name, entry = spec["name"], self.param_entries.get(name)
                if entry:
                    value = entry.get_text().strip()
                    if not value and spec.get("required"): raise ValueError(f"Параметр '{spec['label']}' є обов'язковим.")
                    task_options[name] = value
                elif spec.get("required"): raise RuntimeError(f"Віджет для параметра '{spec['label']}' не знайдено.")
            input_path, output_path = self.input_entry.get_text().strip(), self.output_entry.get_text().strip()
            if not input_path: raise ValueError("Оберіть вхідний файл.")
            if not os.path.isfile(input_path): raise ValueError(f"Вхідний файл не знайдено: {input_path}")
            if not output_path: raise ValueError("Вкажіть вихідний файл.")
            out_dir = os.path.dirname(output_path)
            if out_dir and not os.path.isdir(out_dir): os.makedirs(out_dir, exist_ok=True)
            if os.path.exists(input_path) and os.path.exists(output_path):
                try: 
                    if os.path.samefile(input_path, output_path): raise ValueError("Вхідний та вихідний файли не можуть бути однаковими.")
                except FileNotFoundError: pass 
                except OSError as e: print(f"Помилка samefile: {e}") 
            self._start_task(run_ffmpeg_task, args=(input_path, output_path), kwargs={'task_type': task_type, 'task_options': task_options})
        except (ValueError, RuntimeError, FileNotFoundError) as e: self.show_warning_dialog(str(e))
        except Exception as e: import traceback; traceback.print_exc(); self.show_warning_dialog(f"Неочікувана помилка FFmpeg: {e}")

class HTTrackPage(BasePage):
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        self.mirror_radio, self.archive_radio, self.stack, self.execute_button = None, None, None, None
        self.url_entry, self.mirror_output_dir_entry, self.archive_after_mirror_check = None, None, None
        self.post_mirror_archive_hbox, self.post_mirror_archive_entry = None, None
        self.dir_to_archive_entry, self.archive_file_entry = None, None

    def build_ui(self):
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        self.page_widget.pack_start(Gtk.Label(label="<b><big>HTTrack та Архівування</big></b>", use_markup=True), False, False, 0)
        grid = Gtk.Grid(column_spacing=10, row_spacing=10); self.page_widget.pack_start(grid, False, False, 0)
        grid.attach(Gtk.Label(label="Дія:", halign=Gtk.Align.END), 0, 0, 1, 1)
        hbox_op = Gtk.Box(spacing=10); grid.attach(hbox_op, 1, 0, 3, 1)
        self.mirror_radio = Gtk.RadioButton.new_with_label_from_widget(None, "Віддзеркалити / Оновити сайт")
        self.mirror_radio.set_active(True); self.mirror_radio.connect("toggled", self._on_operation_toggled)
        hbox_op.pack_start(self.mirror_radio, False, False, 0)
        self.archive_radio = Gtk.RadioButton.new_with_label_from_widget(self.mirror_radio, "Архівувати директорію")
        self.archive_radio.connect("toggled", self._on_operation_toggled)
        hbox_op.pack_start(self.archive_radio, False, False, 0)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        grid.attach(self.stack, 0, 1, 4, 1) 
        self.stack.add_titled(self._build_mirror_ui(), "mirror_section", "Mirror Options") 
        self.stack.add_titled(self._build_archive_ui(), "archive_section", "Archive Options") 
        self.execute_button = Gtk.Button(label="Виконати HTTrack") 
        self.execute_button.connect("clicked", self._on_execute_clicked)
        self.page_widget.pack_start(self.execute_button, False, False, 5) 
        self._suggest_default_paths() 
        self.stack.set_visible_child_name("mirror_section") 
        GLib.idle_add(self._update_ui_state) 
        self.page_widget.show_all()
        if self.post_mirror_archive_hbox: self.post_mirror_archive_hbox.set_visible(False)
        return self.page_widget

    def _build_mirror_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        grid1 = Gtk.Grid(column_spacing=10, row_spacing=5); vbox.pack_start(grid1, False, False, 0)
        grid1.attach(Gtk.Label(label="URL сайту:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.url_entry = Gtk.Entry(hexpand=True, placeholder_text="Введіть URL сайту")
        self.url_entry.connect("changed", self._on_mirror_input_changed) 
        grid1.attach(self.url_entry, 1, 0, 3, 1)
        grid2 = Gtk.Grid(column_spacing=10, row_spacing=5); vbox.pack_start(grid2, False, False, 0)
        grid2.attach(Gtk.Label(label="Дир. збереження:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.mirror_output_dir_entry = Gtk.Entry(hexpand=True)
        self.mirror_output_dir_entry.connect("changed", self._on_mirror_input_changed) 
        grid2.attach(self.mirror_output_dir_entry, 1, 0, 2, 1)
        btn1 = Gtk.Button(label="..."); btn1.connect("clicked", lambda w: self._select_folder_dialog(self.mirror_output_dir_entry, "Оберіть директорію"))
        grid2.attach(btn1, 3, 0, 1, 1)
        self.archive_after_mirror_check = Gtk.CheckButton(label="Архівувати результат")
        self.archive_after_mirror_check.connect("toggled", self._on_archive_after_mirror_toggled)
        vbox.pack_start(self.archive_after_mirror_check, False, False, 0)
        self.post_mirror_archive_hbox = Gtk.Box(spacing=10, no_show_all=True)
        vbox.pack_start(self.post_mirror_archive_hbox, False, False, 0)
        self.post_mirror_archive_hbox.pack_start(Gtk.Label(label="Файл архіву:"), False, False, 0)
        self.post_mirror_archive_entry = Gtk.Entry(hexpand=True)
        self.post_mirror_archive_hbox.pack_start(self.post_mirror_archive_entry, True, True, 0)
        btn2 = Gtk.Button(label="..."); btn2.connect("clicked", lambda w: self._select_file_dialog(self.post_mirror_archive_entry, "Оберіть файл архіву", save_mode=True))
        self.post_mirror_archive_hbox.pack_start(btn2, False, False, 0)
        return vbox

    def _build_archive_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        grid1 = Gtk.Grid(column_spacing=10, row_spacing=5); vbox.pack_start(grid1, False, False, 0)
        grid1.attach(Gtk.Label(label="Дир. для архів.:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.dir_to_archive_entry = Gtk.Entry(hexpand=True)
        self.dir_to_archive_entry.connect("changed", self._on_archive_input_changed) 
        grid1.attach(self.dir_to_archive_entry, 1, 0, 2, 1)
        btn1 = Gtk.Button(label="..."); btn1.connect("clicked", lambda w: self._select_folder_dialog(self.dir_to_archive_entry, "Оберіть директорію"))
        grid1.attach(btn1, 3, 0, 1, 1)
        grid2 = Gtk.Grid(column_spacing=10, row_spacing=5); vbox.pack_start(grid2, False, False, 0)
        grid2.attach(Gtk.Label(label="Файл архіву:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.archive_file_entry = Gtk.Entry(hexpand=True)
        grid2.attach(self.archive_file_entry, 1, 0, 2, 1)
        btn2 = Gtk.Button(label="..."); btn2.connect("clicked", lambda w: self._select_file_dialog(self.archive_file_entry, "Оберіть шлях для архіву", save_mode=True))
        grid2.attach(btn2, 3, 0, 1, 1)
        return vbox

    def _suggest_default_paths(self):
        default_mirror_dir = os.path.join(os.path.expanduser("~"), "httrack_mirrors")
        if hasattr(self, 'mirror_output_dir_entry') and self.mirror_output_dir_entry and not self.mirror_output_dir_entry.get_text(): self.mirror_output_dir_entry.set_text(default_mirror_dir)
        if hasattr(self, 'dir_to_archive_entry') and self.dir_to_archive_entry and not self.dir_to_archive_entry.get_text():
             self.dir_to_archive_entry.set_text(default_mirror_dir)
             if hasattr(self, 'archive_radio') and self.archive_radio and self.archive_radio.get_active(): self._suggest_archive_filename(default_mirror_dir)

    def _suggest_archive_filename(self, source_dir, dialog=None):
        if not hasattr(self, 'archive_file_entry') or not self.archive_file_entry: return
        target_entry, default_ext, suggested_name, base_save_path = self.archive_file_entry, ".tar.gz", f"archive.tar.gz", os.path.expanduser("~")
        if source_dir and os.path.isdir(source_dir):
            base_save_path = os.path.dirname(os.path.abspath(source_dir)) or base_save_path
            base = re.sub(r'[^\w.-]+', '_', os.path.basename(os.path.normpath(source_dir)) or "archive").strip('_') or "archive"
            suggested_name = f"{datetime.datetime.now().strftime('%Y%m%d')}_{base}{default_ext}"
        elif source_dir:
            base = re.sub(r'[^\w.-]+', '_', os.path.basename(os.path.normpath(source_dir)) or "archive").strip('_') or "archive"
            if base: suggested_name = f"{datetime.datetime.now().strftime('%Y%m%d')}_{base}{default_ext}"
        suggested_path = os.path.join(base_save_path, suggested_name)
        if dialog: 
            dialog.set_current_name(suggested_name)
            folder_to_set = os.path.dirname(suggested_path)
            if os.path.isdir(folder_to_set): dialog.set_current_folder(folder_to_set)
            elif os.path.isdir(base_save_path): dialog.set_current_folder(base_save_path)
        elif not target_entry.get_text().strip() or os.path.basename(target_entry.get_text().strip()).startswith("archive."): target_entry.set_text(suggested_path)

    def _suggest_post_mirror_archive_filename(self, mirror_dir, url, dialog=None):
        if not hasattr(self, 'post_mirror_archive_entry') or not self.post_mirror_archive_entry: return
        target_entry, default_ext, base_name, base_save_path = self.post_mirror_archive_entry, ".tar.gz", "website", os.path.expanduser("~")
        hostname = self.url_handler.get_hostname_from_url(url)
        if hostname: base_name = hostname
        elif mirror_dir and os.path.isdir(mirror_dir):
             dir_base = re.sub(r'[^\w.-]+', '_', os.path.basename(os.path.normpath(mirror_dir)) or "").strip('_')
             if dir_base: base_name = dir_base
        suggested_name = f"{datetime.datetime.now().strftime('%Y%m%d')}_{base_name}_archive{default_ext}"
        if mirror_dir:
             try: 
                 parent = os.path.dirname(os.path.abspath(mirror_dir)) or base_save_path
                 if os.path.isdir(parent): base_save_path = parent
             except Exception as e: print(f"Warning getting parent dir: {e}")
        suggested_path = os.path.join(base_save_path, suggested_name)
        if dialog: 
            dialog.set_current_name(suggested_name)
            folder_to_set = os.path.dirname(suggested_path)
            if os.path.isdir(folder_to_set): dialog.set_current_folder(folder_to_set)
            elif os.path.isdir(base_save_path): dialog.set_current_folder(base_save_path)
        elif not target_entry.get_text().strip() or os.path.basename(target_entry.get_text().strip()).startswith(("website_archive.", "archive.")): target_entry.set_text(suggested_path)

    def _update_ui_state(self, *args):
        if not all([hasattr(self, w) and getattr(self, w) for w in ['mirror_radio', 'stack', 'execute_button', 'archive_after_mirror_check', 'post_mirror_archive_hbox']]): return
        is_mirror_mode = self.mirror_radio.get_active()
        self.stack.set_visible_child_name("mirror_section" if is_mirror_mode else "archive_section")
        self.execute_button.set_label("Виконати HTTrack" if is_mirror_mode else "Архівувати")
        self.post_mirror_archive_hbox.set_visible(is_mirror_mode and self.archive_after_mirror_check.get_active())

    def _on_operation_toggled(self, radio_button):
        if radio_button.get_active():
            self._update_ui_state() 
            is_mirror_mode = (radio_button == self.mirror_radio)
            url, mirror_dir = (getattr(self, 'url_entry', None).get_text().strip() if hasattr(self, 'url_entry') else ""), (getattr(self, 'mirror_output_dir_entry', None).get_text().strip() if hasattr(self, 'mirror_output_dir_entry') else "")
            if is_mirror_mode and self.archive_after_mirror_check.get_active(): self._suggest_post_mirror_archive_filename(mirror_dir, url)
            elif not is_mirror_mode: self._suggest_archive_filename(getattr(self, 'dir_to_archive_entry', None).get_text().strip() if hasattr(self, 'dir_to_archive_entry') else "")

    def _on_archive_after_mirror_toggled(self, check_button):
        self._update_ui_state() 
        if check_button.get_active():
             url, mirror_dir = (getattr(self, 'url_entry', None).get_text().strip() if hasattr(self, 'url_entry') else ""), (getattr(self, 'mirror_output_dir_entry', None).get_text().strip() if hasattr(self, 'mirror_output_dir_entry') else "")
             self._suggest_post_mirror_archive_filename(mirror_dir, url)

    def _on_mirror_input_changed(self, entry):
        if hasattr(self, 'mirror_radio') and self.mirror_radio.get_active() and hasattr(self, 'archive_after_mirror_check') and self.archive_after_mirror_check.get_active():
             url, mirror_dir = (getattr(self, 'url_entry', None).get_text().strip() if hasattr(self, 'url_entry') else ""), (getattr(self, 'mirror_output_dir_entry', None).get_text().strip() if hasattr(self, 'mirror_output_dir_entry') else "")
             self._suggest_post_mirror_archive_filename(mirror_dir, url)

    def _on_archive_input_changed(self, entry):
         if hasattr(self, 'archive_radio') and self.archive_radio.get_active(): self._suggest_archive_filename(entry.get_text().strip())

    def _on_execute_clicked(self, widget):
        if self.app._is_task_running: self.show_warning_dialog("Завдання вже виконується."); return
        try:
            if not all([hasattr(self, w) and getattr(self, w) for w in ['mirror_radio', 'archive_radio']]): raise RuntimeError("Радіокнопки HTTrack/Архів не ініціалізовані.")
            if self.mirror_radio.get_active(): self._execute_mirror()
            elif self.archive_radio.get_active(): self._execute_archive()
        except (ValueError, RuntimeError, FileNotFoundError) as e: self.show_warning_dialog(str(e))
        except Exception as e: import traceback; traceback.print_exc(); self.show_warning_dialog(f"Неочікувана помилка HTTrack/Архів: {e}")

    def _execute_mirror(self):
        if not all([hasattr(self, attr) and getattr(self, attr) for attr in ['url_entry', 'mirror_output_dir_entry', 'archive_after_mirror_check', 'post_mirror_archive_entry']]): raise RuntimeError("Віджети Mirror не ініціалізовані.")
        url, mirror_dir, archive_after, archive_path = self.url_entry.get_text().strip(), self.mirror_output_dir_entry.get_text().strip(), self.archive_after_mirror_check.get_active(), self.post_mirror_archive_entry.get_text().strip() if self.archive_after_mirror_check.get_active() else None
        try: self.url_handler.validate_httrack_url(url)
        except ValueError as e: self.show_warning_dialog(f"Неприпустимий URL: {e}"); return 
        if not mirror_dir: raise ValueError("Вкажіть директорію для дзеркала.")
        try: os.makedirs(mirror_dir, exist_ok=True)
        except OSError as e: raise ValueError(f"Не вдалося створити/перевірити директорію '{mirror_dir}': {e}")
        if archive_after:
            if not archive_path: raise ValueError("Вкажіть шлях для архіву.")
            arc_dir = os.path.dirname(archive_path)
            if arc_dir: 
                 try: os.makedirs(arc_dir, exist_ok=True)
                 except OSError as e: raise ValueError(f"Не вдалося створити директорію для архіву '{arc_dir}': {e}")
            try:
                abs_mirror_dir, abs_archive_path = os.path.abspath(mirror_dir), os.path.abspath(archive_path)
                if abs_archive_path != abs_mirror_dir and abs_archive_path.startswith(abs_mirror_dir + os.sep): self.show_warning_dialog("Попередження: Архів зберігається всередині директорії дзеркала.")
            except Exception as path_e: print(f"Warning checking archive path: {path_e}")
        self._start_task(run_httrack_web_threaded, args=(url, mirror_dir), kwargs={'archive_after_mirror': archive_after, 'post_mirror_archive_path': archive_path, 'mirror_output_dir': mirror_dir, 'site_url': url})

    def _execute_archive(self):
         if not all([hasattr(self, w) and getattr(self, w) for w in ['dir_to_archive_entry', 'archive_file_entry']]): raise RuntimeError("Віджети Archive не ініціалізовані.")
         source_dir, archive_path = self.dir_to_archive_entry.get_text().strip(), self.archive_file_entry.get_text().strip()
         if not source_dir: raise ValueError("Вкажіть директорію для архівування.")
         if not os.path.isdir(source_dir): raise ValueError(f"Директорія не знайдена: {source_dir}")
         if not archive_path: raise ValueError("Вкажіть шлях для архіву.")
         arc_dir = os.path.dirname(archive_path)
         if arc_dir: 
             try: os.makedirs(arc_dir, exist_ok=True)
             except OSError as e: raise ValueError(f"Не вдалося створити директорію для архіву '{arc_dir}': {e}")
         try:
             abs_source_dir, abs_archive_path = os.path.abspath(source_dir), os.path.abspath(archive_path)
             if abs_archive_path != abs_source_dir and abs_archive_path.startswith(abs_source_dir + os.sep): raise ValueError("Не можна зберігати архів всередині директорії, що архівується.")
         except ValueError as ve: self.show_warning_dialog(str(ve)); return 
         except Exception as path_e: print(f"Warning checking archive path: {path_e}")
         self._start_task(archive_directory_threaded, args=(source_dir, archive_path), kwargs={})

# Клас UploadPage видалено

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
<i>Переконайтеся, що залежності встановлені та доступні у PATH.</i>""" # Видалено згадку про завантаження на сервер
        label = Gtk.Label(label=about_text, use_markup=True, justify=Gtk.Justification.LEFT, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, xalign=0.0)
        label.set_selectable(True) 
        self.page_widget.pack_start(label, False, False, 5) 
        self.page_widget.show_all()
        return self.page_widget

class AppWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="DownYS", default_width=800, default_height=700) 
        self.connect("destroy", Gtk.main_quit) 
        # self.host, self.port видалено, бо UploadPage видалено
        self._is_task_running, self._current_task_thread, self._last_task_had_error = False, None, False
        self.url_handler = URLHandler()
        header_bar = Gtk.HeaderBar(title="DownYS", show_close_button=True); self.set_titlebar(header_bar)
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0); self.add(main_vbox)
        content_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        main_vbox.pack_start(content_hbox, True, True, 0) 
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack_sidebar = Gtk.StackSidebar(stack=self.stack)
        content_hbox.pack_start(self.stack_sidebar, False, False, 0) 
        content_hbox.pack_start(self.stack, True, True, 0)          
        self.pages = {} 
        page_defs = [
            ("bookmarks", "Закладки", BookmarksPage), 
            ("youtube", "YouTube", YouTubePage), 
            ("ffmpeg", "FFmpeg", FFmpegPage), 
            ("httrack", "HTTrack/Архів", HTTrackPage), 
            # ("upload", "Завантаження", UploadPage), # Рядок UploadPage видалено
            ("about", "Про програму", AboutPage)
        ]
        for name, title, p_class in page_defs:
             try:
                 p_instance, p_widget = p_class(self, self.url_handler), None
                 p_widget = p_instance.build_ui() 
                 if not isinstance(p_widget, Gtk.Widget): p_widget = Gtk.Label(label=f"Помилка завантаження '{title}'")
                 self.stack.add_titled(p_widget, name + "_page", title); self.pages[name] = p_instance
             except Exception as e: print(f"ПОМИЛКА створення '{name}': {e}"); import traceback; traceback.print_exc(); self.stack.add_titled(Gtk.Label(label=f"Помилка '{title}'\nДив. консоль."), name + "_page", f"{title} (Помилка)"); self.pages[name] = None
        status_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, border_width=5)
        main_vbox.pack_end(status_hbox, False, False, 0)
        self.status_label = Gtk.Label(label="Готово.", halign=Gtk.Align.START) 
        status_hbox.pack_start(self.status_label, True, True, 0) 
        self.progress_bar = Gtk.ProgressBar(show_text=True, text="")
        status_hbox.pack_end(self.progress_bar, False, False, 0)
        self.show_all()
        self.progress_bar.set_fraction(0.0); self.progress_bar.set_text("")

    def get_page_instance(self, page_name): return self.pages.get(page_name)

    def go_to_page_with_url(self, page_name, url):
        target_widget = self.stack.get_child_by_name(page_name + "_page")
        if target_widget:
            self.stack.set_visible_child(target_widget)
            page_instance = self.pages.get(page_name)
            if page_instance:
                url_entry = getattr(page_instance, 'url_entry', None)
                if isinstance(url_entry, Gtk.Entry): url_entry.set_text(url)
                else: print(f"Попередження: Не знайдено поле 'url_entry' на '{page_name}'.")
            else: print(f"Помилка: Не знайдено екземпляр '{page_name}'.")
        else: print(f"Помилка: Не знайдено сторінку '{page_name + '_page'}'.")

    def _start_task_with_callbacks(self, task_func, args=(), kwargs=None, success_callback=None):
        if self._is_task_running: 
            self.show_warning_dialog("Завдання вже виконується.")
            return

        self._is_task_running = True
        self._last_task_had_error = False 
        GLib.idle_add(self._set_controls_sensitive, False)
        GLib.idle_add(self._update_progress, 0.0)
        GLib.idle_add(self._update_status, f"Запуск: {task_func.__name__}...")

        call_kwargs = kwargs.copy() if kwargs else {}
        chain_kwargs = kwargs.copy() if kwargs else {} 

        # Колбеки для upload_item_to_server більше не потрібні, оскільки модуль видалено
        # Залишаємо загальну логіку для інших функцій
        if 'status_callback' not in call_kwargs:
            call_kwargs['status_callback'] = self._update_status
        
        if task_func in [download_youtube_media, run_ffmpeg_task]: 
            if 'progress_callback' not in call_kwargs:
                call_kwargs['progress_callback'] = self._update_progress
        
        if task_func == run_httrack_web_threaded:
            for key in ['archive_after_mirror', 'post_mirror_archive_path', 'mirror_output_dir', 'site_url']:
                if key in call_kwargs: 
                    del call_kwargs[key] 

        def wrapper():
            try:
                task_func(*args, **call_kwargs) 
                final_message = "Завдання успішно завершено."
                if task_func == run_httrack_web_threaded and chain_kwargs.get('archive_after_mirror'):
                    m_dir = chain_kwargs.get('mirror_output_dir')
                    a_path = chain_kwargs.get('post_mirror_archive_path')
                    s_url = chain_kwargs.get('site_url')
                    if m_dir and a_path:
                        if not os.path.isdir(m_dir): 
                            raise RuntimeError(f"Директорія HTTrack '{m_dir}' не знайдена.")
                        GLib.idle_add(self._update_status, "HTTrack завершено. Архівування...")
                        archive_directory_threaded(
                            directory_to_archive=m_dir, 
                            archive_path=a_path, 
                            status_callback=self._update_status,
                            site_url=s_url
                        )
                        final_message = "HTTrack та архівування успішно завершено."
                    else: 
                        final_message = "HTTrack завершено, архівування не виконано (параметри)."
                
                if success_callback and callable(success_callback): 
                    GLib.idle_add(success_callback)
                GLib.idle_add(self._on_task_complete, final_message)
            except Exception as e: 
                import traceback
                traceback.print_exc()
                self._last_task_had_error = True 
                GLib.idle_add(self._on_task_error, str(e))
        self._current_task_thread = threading.Thread(target=wrapper, daemon=True)
        self._current_task_thread.start()

    def _start_task(self, task_func, args=(), kwargs=None, success_callback=None): # Для сумісності
        self._start_task_with_callbacks(task_func, args, kwargs, success_callback)

    def _on_task_complete(self, final_message="Завдання завершено."):
        self._is_task_running = False
        GLib.idle_add(self._set_controls_sensitive, True)
        GLib.idle_add(self._update_progress, 1.0)
        GLib.idle_add(self._update_status, final_message)
        self._current_task_thread = None

    def _on_task_error(self, error_message):
        self._is_task_running = False
        GLib.idle_add(self._set_controls_sensitive, True)
        GLib.idle_add(self._update_progress, 0.0)
        GLib.idle_add(self._update_status, f"Помилка: {error_message}")
        GLib.idle_add(self.show_warning_dialog, f"Помилка завдання:\n{error_message}")
        self._current_task_thread = None

    def _set_controls_sensitive(self, sensitive):
        current_page_key, visible_child = None, self.stack.get_visible_child()
        if visible_child:
            for pk, pi in self.pages.items():
                if pi and (getattr(pi, 'get_page_widget', lambda: getattr(pi, 'page_widget', None))() == visible_child): current_page_key = pk; break
        if current_page_key and self.pages[current_page_key]:
            page_instance = self.pages[current_page_key]
            button = getattr(page_instance, 'execute_button', None) or getattr(page_instance, 'download_button', None)
            if button and hasattr(button, 'set_sensitive'):
                 try: button.set_sensitive(sensitive)
                 except Exception as e: print(f"Warning: Could not set sensitivity for button on {current_page_key}: {e}")
            # Кнопки, специфічні для UploadPage, більше не потрібні тут

    def _update_progress(self, fraction):
        try: fraction = max(0.0, min(1.0, float(fraction)))
        except (ValueError, TypeError): fraction = 0.0 
        self.progress_bar.set_fraction(fraction)
        self.progress_bar.set_text(f"{int(fraction*100)}%" if fraction > 0 or fraction == 1.0 else "")

    def _update_status(self, message):
        try: message_str = str(message)
        except Exception as e: message_str = f"Помилка оновлення статусу: {e}"
        self.status_label.set_text(message_str); print(f"STATUS: {message_str}") 

    def show_warning_dialog(self, message):
        def show_dialog_idle():
            try:
                dialog = Gtk.MessageDialog(transient_for=self, modal=True, destroy_with_parent=True, message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK, text="Попередження") 
                dialog.format_secondary_text(str(message)); dialog.run(); dialog.destroy()
            except Exception as e: print(f"Error displaying warning dialog: {e}")
        GLib.idle_add(show_dialog_idle)

    def show_info_dialog(self, title, message):
        def show_dialog_idle():
            try:
                dialog = Gtk.MessageDialog(transient_for=self, modal=True, destroy_with_parent=True, message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK, text=title) 
                dialog.format_secondary_text(str(message)); dialog.run(); dialog.destroy()
            except Exception as e: print(f"Error displaying info dialog: {e}")
        GLib.idle_add(show_dialog_idle)

    def _select_file_dialog(self, entry_widget, title, save_mode=False):
        if not isinstance(entry_widget, Gtk.Entry): self.show_warning_dialog(f"Внутрішня помилка діалогу файлу."); return
        action, btn_label = (Gtk.FileChooserAction.SAVE, "_Зберегти") if save_mode else (Gtk.FileChooserAction.OPEN, "_Відкрити")
        dialog = Gtk.FileChooserDialog(title=title, parent=self, action=action)
        dialog.add_buttons("_Скасувати", Gtk.ResponseType.CANCEL, btn_label, Gtk.ResponseType.OK)
        if save_mode: dialog.set_do_overwrite_confirmation(True)
        current_path, current_page_key, page_instance = entry_widget.get_text().strip(), None, None
        visible_child = self.stack.get_visible_child()
        if visible_child:
            for pk, pi in self.pages.items(): 
                if pi and (getattr(pi, 'get_page_widget', lambda: getattr(pi, 'page_widget', None))() == visible_child): current_page_key, page_instance = pk, pi; break
        try:
             if current_path:
                 current_dir = os.path.dirname(current_path)
                 if os.path.isdir(current_dir): dialog.set_current_folder(current_dir)
                 elif os.path.isdir(current_path): dialog.set_current_folder(current_path)
                 else: dialog.set_current_folder(os.path.expanduser("~"))
                 if save_mode and not os.path.isdir(current_path): dialog.set_current_name(os.path.basename(current_path))
                 elif not save_mode and os.path.isfile(current_path): dialog.set_filename(current_path) 
             else:
                 dialog.set_current_folder(os.path.expanduser("~"))
                 if save_mode and page_instance and current_page_key != "bookmarks": # Upload page більше не існує
                     suggested_name_set = False
                     if current_page_key == "httrack":
                         if hasattr(page_instance, 'archive_radio') and page_instance.archive_radio.get_active() and entry_widget == getattr(page_instance, 'archive_file_entry', None) and hasattr(page_instance, '_suggest_archive_filename'):
                              page_instance._suggest_archive_filename(getattr(page_instance, 'dir_to_archive_entry', Gtk.Entry()).get_text().strip(), dialog=dialog); suggested_name_set = True
                         elif hasattr(page_instance, 'mirror_radio') and page_instance.mirror_radio.get_active() and hasattr(page_instance, 'archive_after_mirror_check') and page_instance.archive_after_mirror_check.get_active() and entry_widget == getattr(page_instance, 'post_mirror_archive_entry', None) and hasattr(page_instance, '_suggest_post_mirror_archive_filename'):
                              page_instance._suggest_post_mirror_archive_filename(getattr(page_instance, 'mirror_output_dir_entry', Gtk.Entry()).get_text().strip(), getattr(page_instance, 'url_entry', Gtk.Entry()).get_text().strip(), dialog=dialog); suggested_name_set = True
                     elif current_page_key == "ffmpeg" and entry_widget == getattr(page_instance, 'output_entry', None) and hasattr(page_instance, 'task_combo'):
                          task_info = FFMPEG_TASKS.get(getattr(page_instance, 'task_combo', Gtk.ComboBoxText()).get_active_text())
                          if task_info: dialog.set_current_name(f"output_converted{task_info.get('output_ext', '.out')}"); suggested_name_set = True
                     if not suggested_name_set: # Видалено перевірку current_page_key != 'upload'
                           dialog.set_current_name("output_file")
                 elif save_mode: dialog.set_current_name("output_file")
        except Exception as e: print(f"Warning setting up file dialog: {e}");_ = [dialog.set_current_folder(os.path.expanduser("~")) for _ in range(1) if not dialog.get_current_folder()]
        if dialog.run() == Gtk.ResponseType.OK:
            entry_widget.set_text(dialog.get_filename()) 
            if page_instance and current_page_key != "bookmarks":
                 try:
                     if current_page_key == "ffmpeg" and entry_widget == getattr(page_instance, 'input_entry', None) and hasattr(page_instance, '_update_output_suggestion'): page_instance._update_output_suggestion()
                     elif current_page_key == "httrack":
                          if entry_widget == getattr(page_instance, 'mirror_output_dir_entry', None) and hasattr(page_instance, '_on_mirror_input_changed'): page_instance._on_mirror_input_changed(entry_widget)
                          elif entry_widget == getattr(page_instance, 'dir_to_archive_entry', None) and hasattr(page_instance, '_on_archive_input_changed'): page_instance._on_archive_input_changed(entry_widget)
                          elif entry_widget == getattr(page_instance, 'archive_file_entry', None) and hasattr(page_instance, '_on_archive_input_changed'): _ = [page_instance._on_archive_input_changed(de) for de in [getattr(page_instance, 'dir_to_archive_entry', None)] if de]
                          elif entry_widget == getattr(page_instance, 'post_mirror_archive_entry', None) and hasattr(page_instance, '_on_mirror_input_changed'): _ = [page_instance._on_mirror_input_changed(mde) for mde in [getattr(page_instance, 'mirror_output_dir_entry', None)] if mde]
                 except Exception as e: print(f"Warning triggering page update post dialog: {e}")
        dialog.destroy()

    def _select_folder_dialog(self, entry_widget, title):
        if not isinstance(entry_widget, Gtk.Entry): self.show_warning_dialog(f"Внутрішня помилка діалогу папки."); return
        dialog = Gtk.FileChooserDialog(title=title, parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons("_Скасувати", Gtk.ResponseType.CANCEL, "_Обрати", Gtk.ResponseType.OK)
        current_dir = entry_widget.get_text().strip()
        try:
            if current_dir and os.path.isdir(current_dir): dialog.set_current_folder(current_dir)
            else: dialog.set_current_folder(os.path.expanduser("~"))
        except Exception as e: print(f"Warning setting folder dialog current: {e}"); _=[dialog.set_current_folder(os.path.expanduser("~")) for _ in range(1) if not dialog.get_current_folder()]
        if dialog.run() == Gtk.ResponseType.OK:
            entry_widget.set_text(dialog.get_filename()) 
            current_page_key, page_instance = None, None
            visible_child = self.stack.get_visible_child()
            if visible_child:
                for pk, pi in self.pages.items():
                    if pi and (getattr(pi, 'get_page_widget', lambda: getattr(pi, 'page_widget', None))() == visible_child): current_page_key, page_instance = pk, pi; break
            if current_page_key == "httrack" and page_instance:
                 try:
                      if entry_widget == getattr(page_instance, 'mirror_output_dir_entry', None) and hasattr(page_instance, '_on_mirror_input_changed'): page_instance._on_mirror_input_changed(entry_widget)
                      elif entry_widget == getattr(page_instance, 'dir_to_archive_entry', None) and hasattr(page_instance, '_on_archive_input_changed'): page_instance._on_archive_input_changed(entry_widget)
                 except Exception as e: print(f"Warning triggering page update post folder dialog: {e}")
            elif current_page_key == "youtube" and page_instance and entry_widget == getattr(page_instance, 'output_dir_entry', None) and hasattr(page_instance, '_populate_file_browser'): GLib.idle_add(page_instance._populate_file_browser)
        dialog.destroy()

if __name__ == "__main__":
    missing_deps = []
    print("Перевірка залежностей...")
    for dep_name, cmd_args in [("FFmpeg", ['ffmpeg', '-version']), ("HTTrack", ['httrack', '--version']), ("yt-dlp", ['yt-dlp', '--version'])]:
        print(f" - {dep_name}...", end="")
        try: subprocess.run(cmd_args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); print(" OK")
        except (FileNotFoundError, subprocess.CalledProcessError, OSError) as e: 
            print(f" НЕ ЗНАЙДЕНО ({e})")
            if dep_name == "yt-dlp": # Fallback for youtube-dl
                print("   (Перевірка youtube-dl...)", end="")
                try: subprocess.run(['youtube-dl', '--version'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); print(" OK (рекомендується yt-dlp)")
                except (FileNotFoundError, subprocess.CalledProcessError, OSError) as e_yt_dl: print(f" НЕ ЗНАЙДЕНО ({e_yt_dl})"); missing_deps.append("yt-dlp (або youtube-dl)")
            else: missing_deps.append(dep_name)
    if missing_deps:
         msg = f"Не знайдено: {', '.join(missing_deps)}.\nВстановіть їх та додайте до PATH."
         print(f"\n!!! ПОПЕРЕДЖЕННЯ: {msg} !!!\n")
         try:
             win_temp = Gtk.Window(); dialog = Gtk.MessageDialog(transient_for=win_temp, modal=True, message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK, text="Відсутні Залежності")
             dialog.format_secondary_text(msg); dialog.run(); dialog.destroy(); win_temp.destroy()
         except Exception as e: print(f"Помилка діалогу попередження: {e}\n(Продовження...)")
    print("\nЗапуск DownYS...")
    try: app = AppWindow(); Gtk.main() 
    except Exception as e: print(f"\n!!! Критична помилка: {e} !!!"); import traceback; traceback.print_exc()
    print("DownYS завершив роботу.")

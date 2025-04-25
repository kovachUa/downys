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
import pprint
try:
    from scripts.youtube import download_youtube_video_with_progress
    from scripts.upload_server import upload_file_to_server
    from scripts.httrack_tasks import run_httrack_web_threaded, archive_directory_threaded
    from scripts.ffmpeg_tasks import run_ffmpeg_task
except ImportError as e:
     print(f"Помилка імпорту: {e}")
     print("Переконайтеся, що файли *.py знаходяться в папці 'scripts' поруч з main.py")
     exit(1)
FFMPEG_TASKS = {
    "Відео -> MP4 (Просто)": {"type": "convert_simple","output_ext": ".mp4","params": []},
    "Відео -> AVI": {"type": "convert_format","output_ext": ".avi","params": []},
    "Відео -> Аудіо (AAC)": {"type": "extract_audio_aac","output_ext": ".aac","params": []},
    "Відео -> Аудіо (MP3)": {"type": "extract_audio_mp3","output_ext": ".mp3","params": []},
    "Стиснути Відео (Бітрейт)": {"type": "compress_bitrate","output_ext": ".mp4","params": [{"name": "bitrate", "label": "Відео Бітрейт (напр., 1M)", "type": "entry", "default": "1M", "required": True}]},
    "Змінити Роздільну здатність": {"type": "adjust_resolution","output_ext": ".mp4","params": [{"name": "width", "label": "Ширина", "type": "entry", "default": "1280", "required": True},{"name": "height", "label": "Висота", "type": "entry", "default": "720", "required": True}]}
}
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
class BasePage:
    def __init__(self, app_window, url_handler):
        self.app = app_window
        self.url_handler = url_handler
    def build_ui(self):
        raise NotImplementedError
    def _start_task(self, *args, **kwargs):
        self.app._start_task(*args, **kwargs)
    def _select_file_dialog(self, *args, **kwargs):
        self.app._select_file_dialog(*args, **kwargs)
    def _select_folder_dialog(self, *args, **kwargs):
        self.app._select_folder_dialog(*args, **kwargs)
    def show_warning_dialog(self, *args, **kwargs):
         self.app.show_warning_dialog(*args, **kwargs)
    def get_page_widget(self):
         # Метод для отримання головного віджету сторінки, якщо build_ui його повертає
         if hasattr(self, 'page_widget') and isinstance(self.page_widget, Gtk.Widget):
             return self.page_widget
         return None # Або викликати помилку, якщо віджет не створено
class YouTubePage(BasePage):
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        self.page_widget = None
        self.url_entry = None
        self.output_dir_entry = None
        self.download_button = None
        self.format_combo = None
        self.audio_format_combo = None
        self.download_subs_check = None
        self.sub_langs_entry = None
        self.embed_subs_check = None
    def build_ui(self):
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        self.page_widget.pack_start(Gtk.Label(label="<b><big>Завантаження YouTube</big></b>", use_markup=True), False, False, 0)
        grid = Gtk.Grid(column_spacing=10, row_spacing=8) # Зменшено row_spacing
        self.page_widget.pack_start(grid, False, False, 0)
        # --- URL and Output ---
        grid.attach(Gtk.Label(label="URL відео/списку:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.url_entry = Gtk.Entry(hexpand=True)
        grid.attach(self.url_entry, 1, 0, 3, 1)
        grid.attach(Gtk.Label(label="Дир. збереження:", halign=Gtk.Align.END), 0, 1, 1, 1)
        self.output_dir_entry = Gtk.Entry(hexpand=True)
        grid.attach(self.output_dir_entry, 1, 1, 2, 1)
        btn_out = Gtk.Button(label="...")
        btn_out.connect("clicked", lambda w: self._select_folder_dialog(self.output_dir_entry, "Оберіть директорію"))
        grid.attach(btn_out, 3, 1, 1, 1)
        # --- Format Selection ---
        grid.attach(Gtk.Label(label="Формат/Якість:", halign=Gtk.Align.END), 0, 2, 1, 1)
        self.format_combo = Gtk.ComboBoxText()
        formats = {
            "best": "Найкраще Відео+Аудіо (WebM/MKV)",
            "best_mp4": "Найкраще Відео+Аудіо (MP4)",
            "audio_best": "Лише аудіо (Найкраще)",
            "audio_mp3": "Лише аудіо (MP3)",
            "audio_m4a": "Лише аудіо (M4A/AAC)"
        }
        for key, value in formats.items():
            self.format_combo.append(key, value)
        self.format_combo.set_active_id("best")
        self.format_combo.connect("changed", self._on_format_changed)
        grid.attach(self.format_combo, 1, 2, 3, 1)
        # --- Audio Format (visible only for audio_*) ---
        self.audio_format_label = Gtk.Label(label="Аудіо кодек:", halign=Gtk.Align.END)
        self.audio_format_combo = Gtk.ComboBoxText()
        audio_formats = ['best', 'mp3', 'aac', 'm4a', 'opus', 'vorbis', 'wav']
        for fmt in audio_formats:
            self.audio_format_combo.append(fmt, fmt.upper())
        self.audio_format_combo.set_active_id("best") # Default to best if audio only chosen
        grid.attach(self.audio_format_label, 0, 3, 1, 1)
        grid.attach(self.audio_format_combo, 1, 3, 3, 1)
        # --- Subtitles ---
        self.download_subs_check = Gtk.CheckButton(label="Завантажити субтитри")
        self.download_subs_check.connect("toggled", self._on_subs_toggled)
        grid.attach(self.download_subs_check, 0, 4, 2, 1)
        self.sub_langs_label = Gtk.Label(label="Мови суб. (через кому):", halign=Gtk.Align.END)
        self.sub_langs_entry = Gtk.Entry(text="uk,en")
        grid.attach(self.sub_langs_label, 2, 4, 1, 1)
        grid.attach(self.sub_langs_entry, 3, 4, 1, 1)
        self.embed_subs_check = Gtk.CheckButton(label="Вбудувати субтитри (в MKV)")
        grid.attach(self.embed_subs_check, 0, 5, 2, 1)
        # --- Download Button ---
        self.download_button = Gtk.Button(label="Завантажити")
        self.download_button.connect("clicked", self._on_download_clicked)
        self.page_widget.pack_start(self.download_button, False, False, 5) # Add some padding
        # --- Initial State ---
        self._suggest_default_output_dir()
        self._update_options_visibility()
        self.page_widget.show_all()
        return self.page_widget
    def _suggest_default_output_dir(self):
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads", "YouTube_DownYS")
        if self.output_dir_entry and not self.output_dir_entry.get_text():
            self.output_dir_entry.set_text(default_dir)
    def _update_options_visibility(self):
        format_id = self.format_combo.get_active_id()
        is_audio = format_id is not None and format_id.startswith("audio_")
        subs_active = self.download_subs_check.get_active()
        self.audio_format_label.set_visible(is_audio)
        self.audio_format_combo.set_visible(is_audio)
        self.sub_langs_label.set_visible(subs_active)
        self.sub_langs_entry.set_visible(subs_active)
        self.embed_subs_check.set_visible(subs_active and not is_audio) # Embed only makes sense for video
    def _on_format_changed(self, combo):
        self._update_options_visibility()
        # Automatically select a relevant audio format if user chooses audio_mp3/audio_m4a
        format_id = combo.get_active_id()
        if format_id == "audio_mp3": self.audio_format_combo.set_active_id("mp3")
        elif format_id == "audio_m4a": self.audio_format_combo.set_active_id("m4a")
        elif format_id is not None and format_id.startswith("audio_"): self.audio_format_combo.set_active_id("best")
    def _on_subs_toggled(self, check):
        self._update_options_visibility()
    def _on_download_clicked(self, widget):
        if self.app._is_task_running:
            self.show_warning_dialog("Завдання вже виконується.")
            return
        try:
            if not all([self.url_entry, self.output_dir_entry, self.format_combo, self.audio_format_combo,
                        self.download_subs_check, self.sub_langs_entry, self.embed_subs_check]):
                 raise RuntimeError("Внутрішня помилка: Віджети YouTube не ініціалізовані.")
            url = self.url_entry.get_text().strip()
            output_dir = self.output_dir_entry.get_text().strip()
            format_selection = self.format_combo.get_active_id() or "best"
            audio_format_override = self.audio_format_combo.get_active_id() if format_selection.startswith("audio_") else None
            download_subs = self.download_subs_check.get_active()
            sub_langs = self.sub_langs_entry.get_text().strip() if download_subs else None
            embed_subs = self.embed_subs_check.get_active() if download_subs else False
            if not url: raise ValueError("URL відео YouTube не може бути порожнім.")
            if not output_dir: raise ValueError("Будь ласка, оберіть директорію для збереження.")
            if download_subs and not sub_langs:
                 self.show_warning_dialog("Вказано завантаження субтитрів, але не вказано мови. Будуть використані стандартні (uk,en).")
                 sub_langs = "uk,en"
            if not os.path.isdir(output_dir):
                try: os.makedirs(output_dir, exist_ok=True)
                except OSError as e: raise ValueError(f"Не вдалося створити директорію '{output_dir}': {e}")
            self._start_task(
                download_youtube_video_with_progress,
                args=(url, output_dir),
                kwargs={
                    'format_selection': format_selection,
                    'audio_format_override': audio_format_override,
                    'download_subs': download_subs,
                    'sub_langs': sub_langs,
                    'embed_subs': embed_subs,
                }
            )
        except (ValueError, RuntimeError, FileNotFoundError) as e: self.show_warning_dialog(str(e))
        except Exception as e: self.show_warning_dialog(f"Неочікувана помилка YouTube: {e}")
class FFmpegPage(BasePage):
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        self.page_widget = None
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
        for label in FFMPEG_TASKS.keys():
            self.task_combo.append_text(label)
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
        self._on_task_changed(self.task_combo)
        return self.page_widget
    def _on_task_changed(self, combo):
        selected_label = combo.get_active_text()
        if not selected_label: return
        task_info = FFMPEG_TASKS.get(selected_label)
        if not task_info: return
        if self.params_box:
             for widget in self.params_box.get_children(): self.params_box.remove(widget)
        self.param_entries = {}
        if self.params_box:
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
        if not all([self.input_entry, self.output_entry, self.task_combo]): return
        input_path = self.input_entry.get_text().strip()
        output_path = self.output_entry.get_text().strip()
        task_info = FFMPEG_TASKS.get(self.task_combo.get_active_text())
        output_ext = task_info.get("output_ext", ".out") if task_info else ".out"
        if input_path:
            input_dir = os.path.dirname(input_path) or "."
            base, _ = os.path.splitext(os.path.basename(input_path))
            suggested_path = os.path.join(input_dir, f"{base}_converted{output_ext}")
            update = False
            if not output_path: update = True
            else:
                 out_base, out_ext = os.path.splitext(os.path.basename(output_path))
                 if out_base.startswith(f"{base}_converted") or out_ext.lower() != output_ext.lower(): update = True
            if update: self.output_entry.set_text(suggested_path)
        elif not output_path:
             self.output_entry.set_text(os.path.join(os.path.expanduser("~"), f"output_converted{output_ext}"))
    def _on_execute_clicked(self, widget):
        if self.app._is_task_running:
            self.show_warning_dialog("Завдання вже виконується.")
            return
        try:
            if not all([self.task_combo, self.input_entry, self.output_entry]):
                 raise RuntimeError("Внутрішня помилка: Віджети FFmpeg не ініціалізовані.")
            task_info = FFMPEG_TASKS.get(self.task_combo.get_active_text())
            if not task_info: raise ValueError("Будь ласка, оберіть завдання FFmpeg.")
            task_type = task_info["type"]
            task_options = {}
            for spec in task_info.get("params", []):
                name = spec["name"]
                entry = self.param_entries.get(name)
                if entry:
                    value = entry.get_text().strip()
                    if not value and spec.get("required"): raise ValueError(f"Параметр '{spec['label']}' є обов'язковим.")
                    task_options[name] = value
                elif spec.get("required"): raise RuntimeError(f"Внутрішня помилка: віджет для '{spec['label']}' не знайдено.")
            input_path = self.input_entry.get_text().strip()
            output_path = self.output_entry.get_text().strip()
            if not input_path: raise ValueError("Оберіть вхідний файл.")
            if not os.path.isfile(input_path): raise ValueError(f"Вхідний файл не знайдено: {input_path}")
            if not output_path: raise ValueError("Вкажіть вихідний файл.")
            out_dir = os.path.dirname(output_path)
            if out_dir and not os.path.isdir(out_dir):
                try: os.makedirs(out_dir, exist_ok=True)
                except OSError as e: raise ValueError(f"Не вдалося створити директорію '{out_dir}': {e}")
            if os.path.exists(input_path) and os.path.exists(output_path) and os.path.samefile(input_path, output_path):
                raise ValueError("Вхідний та вихідний файли не можуть бути однаковими.")
            self._start_task(run_ffmpeg_task, args=(input_path, output_path), kwargs={'task_type': task_type, 'task_options': task_options})
        except (ValueError, RuntimeError, FileNotFoundError) as e: self.show_warning_dialog(str(e))
        except Exception as e: self.show_warning_dialog(f"Неочікувана помилка FFmpeg: {e}")
class HTTrackPage(BasePage):
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        self.page_widget = None
        self.mirror_radio = None; self.archive_radio = None; self.stack = None; self.execute_button = None
        self.url_entry = None; self.mirror_output_dir_entry = None; self.archive_after_mirror_check = None
        self.post_mirror_archive_hbox = None; self.post_mirror_archive_entry = None
        self.dir_to_archive_entry = None; self.archive_file_entry = None
    def build_ui(self):
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        self.page_widget.pack_start(Gtk.Label(label="<b><big>HTTrack та Архівування</big></b>", use_markup=True), False, False, 0)
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self.page_widget.pack_start(grid, False, False, 0)
        grid.attach(Gtk.Label(label="Дія:", halign=Gtk.Align.END), 0, 0, 1, 1)
        hbox_op = Gtk.Box(spacing=10)
        grid.attach(hbox_op, 1, 0, 3, 1)
        self.mirror_radio = Gtk.RadioButton.new_with_label_from_widget(None, "Віддзеркалити / Оновити сайт")
        self.mirror_radio.set_active(True)
        self.mirror_radio.connect("toggled", self._on_operation_toggled)
        hbox_op.pack_start(self.mirror_radio, False, False, 0)
        self.archive_radio = Gtk.RadioButton.new_with_label_from_widget(self.mirror_radio, "Архівувати директорію")
        self.archive_radio.connect("toggled", self._on_operation_toggled)
        hbox_op.pack_start(self.archive_radio, False, False, 0)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        grid.attach(self.stack, 0, 1, 4, 1)
        mirror_vbox = self._build_mirror_ui()
        self.stack.add_titled(mirror_vbox, "mirror_section", "Mirror")
        archive_vbox = self._build_archive_ui()
        self.stack.add_titled(archive_vbox, "archive_section", "Archive")
        self.execute_button = Gtk.Button(label="Виконати HTTrack")
        self.execute_button.connect("clicked", self._on_execute_clicked)
        self.page_widget.pack_start(self.execute_button, False, False, 5)
        self._suggest_default_paths()
        self.stack.set_visible_child_name("mirror_section")
        self._update_ui_state()
        self.page_widget.show_all()
        GLib.idle_add(self._update_ui_state)
        return self.page_widget
    def _build_mirror_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        grid1 = Gtk.Grid(column_spacing=10, row_spacing=5)
        vbox.pack_start(grid1, False, False, 0)
        grid1.attach(Gtk.Label(label="URL сайту:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.url_entry = Gtk.Entry(hexpand=True)
        self.url_entry.connect("changed", self._on_mirror_input_changed)
        grid1.attach(self.url_entry, 1, 0, 3, 1)
        grid2 = Gtk.Grid(column_spacing=10, row_spacing=5)
        vbox.pack_start(grid2, False, False, 0)
        grid2.attach(Gtk.Label(label="Дир. збереження:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.mirror_output_dir_entry = Gtk.Entry(hexpand=True)
        self.mirror_output_dir_entry.connect("changed", self._on_mirror_input_changed)
        grid2.attach(self.mirror_output_dir_entry, 1, 0, 2, 1)
        btn1 = Gtk.Button(label="...")
        btn1.connect("clicked", lambda w: self._select_folder_dialog(self.mirror_output_dir_entry, "Оберіть директорію"))
        grid2.attach(btn1, 3, 0, 1, 1)
        self.archive_after_mirror_check = Gtk.CheckButton(label="Архівувати результат віддзеркалення")
        self.archive_after_mirror_check.connect("toggled", self._on_archive_after_mirror_toggled)
        vbox.pack_start(self.archive_after_mirror_check, False, False, 0)
        self.post_mirror_archive_hbox = Gtk.Box(spacing=10, no_show_all=True, visible=False)
        vbox.pack_start(self.post_mirror_archive_hbox, False, False, 0)
        lbl = Gtk.Label(label="Файл архіву:")
        self.post_mirror_archive_hbox.pack_start(lbl, False, False, 0)
        self.post_mirror_archive_entry = Gtk.Entry(hexpand=True)
        self.post_mirror_archive_hbox.pack_start(self.post_mirror_archive_entry, True, True, 0)
        btn2 = Gtk.Button(label="...")
        btn2.connect("clicked", lambda w: self._select_file_dialog(self.post_mirror_archive_entry, "Оберіть файл архіву", save_mode=True))
        self.post_mirror_archive_hbox.pack_start(btn2, False, False, 0)
        return vbox
    def _build_archive_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        grid1 = Gtk.Grid(column_spacing=10, row_spacing=5)
        vbox.pack_start(grid1, False, False, 0)
        grid1.attach(Gtk.Label(label="Дир. для архів.:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.dir_to_archive_entry = Gtk.Entry(hexpand=True)
        self.dir_to_archive_entry.connect("changed", self._on_archive_input_changed)
        grid1.attach(self.dir_to_archive_entry, 1, 0, 2, 1)
        btn1 = Gtk.Button(label="...")
        btn1.connect("clicked", lambda w: self._select_folder_dialog(self.dir_to_archive_entry, "Оберіть директорію"))
        grid1.attach(btn1, 3, 0, 1, 1)
        grid2 = Gtk.Grid(column_spacing=10, row_spacing=5)
        vbox.pack_start(grid2, False, False, 0)
        grid2.attach(Gtk.Label(label="Файл архіву:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.archive_file_entry = Gtk.Entry(hexpand=True)
        grid2.attach(self.archive_file_entry, 1, 0, 2, 1)
        btn2 = Gtk.Button(label="...")
        btn2.connect("clicked", lambda w: self._select_file_dialog(self.archive_file_entry, "Оберіть шлях для архіву", save_mode=True))
        grid2.attach(btn2, 3, 0, 1, 1)
        return vbox
    def _suggest_default_paths(self):
        default_mirror_dir = os.path.join(os.path.expanduser("~"), "httrack_mirrors")
        if self.mirror_output_dir_entry and not self.mirror_output_dir_entry.get_text():
            self.mirror_output_dir_entry.set_text(default_mirror_dir)
        if self.dir_to_archive_entry and not self.dir_to_archive_entry.get_text():
             self.dir_to_archive_entry.set_text(default_mirror_dir)
             self._suggest_archive_filename(default_mirror_dir)
    def _suggest_archive_filename(self, source_dir, dialog=None):
        if not self.archive_file_entry: return
        target_entry = self.archive_file_entry; default_ext = ".tar.gz"
        suggested_name = f"archive{default_ext}"; suggested_path = os.path.join(os.path.expanduser("~"), suggested_name)
        if source_dir and os.path.isdir(source_dir):
            base = os.path.basename(os.path.normpath(source_dir)) or "archive"
            clean = re.sub(r'[^\w.-]+', '_', base).strip('_') or "archive"
            ts = datetime.datetime.now().strftime("%Y%m%d")
            suggested_name = f"{ts}_{clean}{default_ext}"
            parent = os.path.dirname(os.path.abspath(source_dir)) or os.path.expanduser("~")
            suggested_path = os.path.join(parent, suggested_name)
        if dialog:
            dialog.set_current_name(suggested_name)
            folder = os.path.dirname(suggested_path)
            if os.path.isdir(folder): dialog.set_current_folder(folder)
        else:
            current = target_entry.get_text().strip()
            if not current or os.path.basename(current).startswith("archive."): target_entry.set_text(suggested_path)
    def _suggest_post_mirror_archive_filename(self, mirror_dir, url, dialog=None):
        if not self.post_mirror_archive_entry: return
        target_entry = self.post_mirror_archive_entry; default_ext = ".tar.gz"
        hostname = self.url_handler.get_hostname_from_url(url); base_name = "website"
        if hostname: base_name = hostname
        elif mirror_dir and os.path.isdir(mirror_dir):
             dir_base = os.path.basename(os.path.normpath(mirror_dir))
             if dir_base:
                  clean_dir = re.sub(r'[^\w.-]+', '_', dir_base).strip('_')
                  if clean_dir: base_name = clean_dir
        ts = datetime.datetime.now().strftime("%Y%m%d")
        suggested_name = f"{ts}_{base_name}_archive{default_ext}"
        suggested_path = os.path.join(os.path.expanduser("~"), suggested_name)
        if mirror_dir:
             parent = os.path.dirname(os.path.abspath(mirror_dir)) or os.path.expanduser("~")
             suggested_path = os.path.join(parent, suggested_name)
        if dialog:
            dialog.set_current_name(suggested_name)
            folder = os.path.dirname(suggested_path)
            if os.path.isdir(folder): dialog.set_current_folder(folder)
        else:
            current = target_entry.get_text().strip()
            if not current or os.path.basename(current).startswith(("website_archive.", "archive.")): target_entry.set_text(suggested_path)
    def _update_ui_state(self):
        if not self.mirror_radio or not self.stack or not self.execute_button: return
        is_mirror_mode = self.mirror_radio.get_active()
        if is_mirror_mode:
            self.stack.set_visible_child_name("mirror_section")
            self.execute_button.set_label("Виконати HTTrack")
            if self.archive_after_mirror_check and self.post_mirror_archive_hbox:
                self.post_mirror_archive_hbox.set_visible(self.archive_after_mirror_check.get_active())
        else:
            self.stack.set_visible_child_name("archive_section")
            self.execute_button.set_label("Архівувати")
            if self.post_mirror_archive_hbox: self.post_mirror_archive_hbox.set_visible(False)
    def _on_operation_toggled(self, radio_button):
        if radio_button.get_active():
            self._update_ui_state()
            is_mirror_mode = (radio_button == self.mirror_radio)
            if is_mirror_mode and self.archive_after_mirror_check and self.archive_after_mirror_check.get_active():
                self._suggest_post_mirror_archive_filename(getattr(self, 'mirror_output_dir_entry', Gtk.Entry()).get_text().strip(), getattr(self, 'url_entry', Gtk.Entry()).get_text().strip())
            elif not is_mirror_mode: self._suggest_archive_filename(getattr(self, 'dir_to_archive_entry', Gtk.Entry()).get_text().strip())
    def _on_archive_after_mirror_toggled(self, check_button):
        self._update_ui_state()
        if check_button.get_active(): self._suggest_post_mirror_archive_filename(getattr(self, 'mirror_output_dir_entry', Gtk.Entry()).get_text().strip(), getattr(self, 'url_entry', Gtk.Entry()).get_text().strip())
    def _on_mirror_input_changed(self, entry):
        if self.mirror_radio.get_active() and self.archive_after_mirror_check and self.archive_after_mirror_check.get_active():
             self._suggest_post_mirror_archive_filename(getattr(self, 'mirror_output_dir_entry', Gtk.Entry()).get_text().strip(), getattr(self, 'url_entry', Gtk.Entry()).get_text().strip())
    def _on_archive_input_changed(self, entry):
         if self.archive_radio.get_active(): self._suggest_archive_filename(entry.get_text().strip())
    def _on_execute_clicked(self, widget):
        if self.app._is_task_running: self.show_warning_dialog("Завдання вже виконується."); return
        try:
            if self.mirror_radio.get_active(): self._execute_mirror()
            elif self.archive_radio.get_active(): self._execute_archive()
        except (ValueError, RuntimeError, FileNotFoundError) as e: self.show_warning_dialog(str(e))
        except Exception as e: import traceback; traceback.print_exc(); self.show_warning_dialog(f"Неочікувана помилка HTTrack/Архів: {e}")
    def _execute_mirror(self):
        if not all([self.url_entry, self.mirror_output_dir_entry, self.archive_after_mirror_check, self.post_mirror_archive_entry]): raise RuntimeError("Внутрішня помилка: Віджети Mirror не ініціалізовані.")
        url = self.url_entry.get_text().strip(); mirror_dir = self.mirror_output_dir_entry.get_text().strip()
        archive_after = self.archive_after_mirror_check.get_active(); archive_path = self.post_mirror_archive_entry.get_text().strip() if archive_after else None
        self.url_handler.validate_httrack_url(url)
        if not mirror_dir: raise ValueError("Вкажіть директорію для збереження дзеркала.")
        if not os.path.isdir(mirror_dir):
             try: os.makedirs(mirror_dir, exist_ok=True)
             except OSError as e: raise ValueError(f"Не вдалося створити директорію '{mirror_dir}': {e}")
        if archive_after:
            if not archive_path: raise ValueError("Вкажіть шлях для файлу архіву.")
            arc_dir = os.path.dirname(archive_path)
            if arc_dir and not os.path.isdir(arc_dir):
                 try: os.makedirs(arc_dir, exist_ok=True)
                 except OSError as e: raise ValueError(f"Не вдалося створити директорію '{arc_dir}': {e}")
            try:
                if os.path.exists(mirror_dir) and os.path.exists(archive_path) and os.path.abspath(archive_path).startswith(os.path.abspath(mirror_dir) + os.sep):
                    self.show_warning_dialog("Попередження: Архів зберігається всередині директорії дзеркала.")
            except Exception as path_e: print(f"Warning checking archive path: {path_e}")
        self._start_task(run_httrack_web_threaded, args=(url, mirror_dir), kwargs={'archive_after_mirror': archive_after, 'post_mirror_archive_path': archive_path, 'mirror_output_dir': mirror_dir, 'site_url': url})
    def _execute_archive(self):
         if not self.dir_to_archive_entry or not self.archive_file_entry: raise RuntimeError("Внутрішня помилка: Віджети Archive не ініціалізовані.")
         source_dir = self.dir_to_archive_entry.get_text().strip(); archive_path = self.archive_file_entry.get_text().strip()
         if not source_dir: raise ValueError("Вкажіть директорію для архівування.")
         if not os.path.isdir(source_dir): raise ValueError(f"Директорія не знайдена: {source_dir}")
         if not archive_path: raise ValueError("Вкажіть шлях для файлу архіву.")
         arc_dir = os.path.dirname(archive_path)
         if arc_dir and not os.path.isdir(arc_dir):
             try: os.makedirs(arc_dir, exist_ok=True)
             except OSError as e: raise ValueError(f"Не вдалося створити директорію '{arc_dir}': {e}")
         try:
             if os.path.exists(source_dir) and os.path.exists(archive_path) and os.path.abspath(archive_path).startswith(os.path.abspath(source_dir) + os.sep):
                 raise ValueError("Не можна зберігати архів всередині директорії, що архівується.")
         except Exception as path_e: print(f"Warning checking archive path: {path_e}")
         self._start_task(archive_directory_threaded, args=(source_dir, archive_path), kwargs={})
class UploadPage(BasePage):
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        self.page_widget = None; self.host_entry = None; self.port_entry = None
        self.file_entry = None; self.execute_button = None
        self.default_host = app_window.host; self.default_port = app_window.port
    def build_ui(self):
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        self.page_widget.pack_start(Gtk.Label(label="<b><big>Завантаження на Сервер</big></b>", use_markup=True), False, False, 0)
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self.page_widget.pack_start(grid, False, False, 0)
        grid.attach(Gtk.Label(label="Хост сервера:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.host_entry = Gtk.Entry(text=self.default_host, hexpand=True)
        grid.attach(self.host_entry, 1, 0, 3, 1)
        grid.attach(Gtk.Label(label="Порт сервера:", halign=Gtk.Align.END), 0, 1, 1, 1)
        self.port_entry = Gtk.Entry(text=str(self.default_port), hexpand=True)
        grid.attach(self.port_entry, 1, 1, 3, 1)
        grid.attach(Gtk.Label(label="Файл для завантаження:", halign=Gtk.Align.END), 0, 2, 1, 1)
        self.file_entry = Gtk.Entry(hexpand=True)
        grid.attach(self.file_entry, 1, 2, 2, 1)
        btn_file = Gtk.Button(label="...")
        btn_file.connect("clicked", lambda w: self._select_file_dialog(self.file_entry, "Оберіть файл"))
        grid.attach(btn_file, 3, 2, 1, 1)
        self.execute_button = Gtk.Button(label="Завантажити")
        self.execute_button.connect("clicked", self._on_execute_clicked)
        self.page_widget.pack_start(self.execute_button, False, False, 5)
        self.page_widget.show_all()
        return self.page_widget
    def _on_execute_clicked(self, widget):
        if self.app._is_task_running: self.show_warning_dialog("Завдання вже виконується."); return
        try:
            if not all([self.host_entry, self.port_entry, self.file_entry]): raise RuntimeError("Внутрішня помилка: Віджети Upload не ініціалізовані.")
            host = self.host_entry.get_text().strip(); port_str = self.port_entry.get_text().strip(); file_path = self.file_entry.get_text().strip()
            if not host: raise ValueError("Вкажіть хост сервера.")
            if not port_str: raise ValueError("Вкажіть порт сервера.")
            try: port = int(port_str); assert 1 <= port <= 65535
            except: raise ValueError("Порт має бути числом від 1 до 65535.")
            if not file_path: raise ValueError("Оберіть файл для завантаження.")
            if not os.path.isfile(file_path): raise ValueError(f"Файл не знайдено: {file_path}")
            self._start_task(upload_file_to_server, args=(host, port, file_path), kwargs={})
        except (ValueError, RuntimeError, FileNotFoundError) as e: self.show_warning_dialog(str(e))
        except Exception as e: self.show_warning_dialog(f"Неочікувана помилка Upload: {e}")
class BookmarksPage(BasePage):
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        self.page_widget = None
        self.listbox = None
        self.url_entry = None
        self.name_entry = None
        self.bookmarks = [] # Список словників [{'name': '...', 'url': '...'}]
        self.bookmarks_file = os.path.join(GLib.get_user_config_dir(), "downys", "bookmarks.json")
    def build_ui(self):
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, border_width=10)
        self.page_widget.pack_start(Gtk.Label(label="<b><big>Закладки</big></b>", use_markup=True), False, False, 5)
        # --- List ---
        scrolled_window = Gtk.ScrolledWindow(shadow_type=Gtk.ShadowType.IN, hexpand=True, vexpand=True)
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-activated", self._on_bookmark_activated)
        scrolled_window.add(self.listbox)
        self.page_widget.pack_start(scrolled_window, True, True, 0)
        # --- Add/Remove Buttons ---
        hbox_buttons = Gtk.Box(spacing=6)
        btn_remove = Gtk.Button(label="Видалити Вибране")
        btn_remove.connect("clicked", self._on_remove_clicked)
        hbox_buttons.pack_end(btn_remove, False, False, 0)
        self.page_widget.pack_start(hbox_buttons, False, False, 5)
        # --- Add Form ---
        grid = Gtk.Grid(column_spacing=10, row_spacing=5)
        grid.attach(Gtk.Label(label="URL:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.url_entry = Gtk.Entry(hexpand=True)
        self.url_entry.connect("activate", self._on_add_clicked) # Allow adding with Enter
        grid.attach(self.url_entry, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="Назва:", halign=Gtk.Align.END), 0, 1, 1, 1)
        self.name_entry = Gtk.Entry(hexpand=True)
        self.name_entry.connect("activate", self._on_add_clicked)
        grid.attach(self.name_entry, 1, 1, 1, 1)
        btn_add = Gtk.Button(label="Додати Закладку")
        btn_add.connect("clicked", self._on_add_clicked)
        grid.attach(btn_add, 0, 2, 2, 1)
        self.page_widget.pack_start(grid, False, False, 5)
        self.load_bookmarks()
        self.populate_listbox()
        self.page_widget.show_all()
        return self.page_widget
    def load_bookmarks(self):
        self.bookmarks = []
        if os.path.exists(self.bookmarks_file):
            try:
                with open(self.bookmarks_file, 'r', encoding='utf-8') as f:
                    self.bookmarks = json.load(f)
                if not isinstance(self.bookmarks, list): self.bookmarks = []
            except (json.JSONDecodeError, OSError, TypeError) as e:
                print(f"Помилка завантаження закладок: {e}")
                self.bookmarks = []
    def save_bookmarks(self):
        try:
            os.makedirs(os.path.dirname(self.bookmarks_file), exist_ok=True)
            with open(self.bookmarks_file, 'w', encoding='utf-8') as f:
                json.dump(self.bookmarks, f, indent=2, ensure_ascii=False)
        except OSError as e:
            print(f"Помилка збереження закладок: {e}")
            self.show_warning_dialog(f"Не вдалося зберегти закладки:\n{e}")
    def populate_listbox(self):
        for child in self.listbox.get_children(): self.listbox.remove(child)
        for i, bm in enumerate(self.bookmarks):
            label_text = f"<b>{bm.get('name', 'Без назви')}</b>\n<small>{bm.get('url', 'Немає URL')}</small>"
            label = Gtk.Label(use_markup=True, xalign=0, wrap=True, ellipsize=Pango.EllipsizeMode.END)
            label.set_markup(label_text)
            row = Gtk.ListBoxRow()
            row.add(label)
            row.bookmark_index = i # Store index for later retrieval
            self.listbox.add(row)
        self.listbox.show_all()
    def _on_add_clicked(self, widget):
        url = self.url_entry.get_text().strip()
        name = self.name_entry.get_text().strip()
        if not url: self.show_warning_dialog("URL закладки не може бути порожнім."); return
        if not name: name = url # Use URL as name if name is empty
        # Check for duplicates (optional)
        # if any(b['url'] == url for b in self.bookmarks):
        #     self.show_warning_dialog("Закладка з таким URL вже існує."); return
        self.bookmarks.append({'name': name, 'url': url})
        self.save_bookmarks()
        self.populate_listbox()
        self.url_entry.set_text("")
        self.name_entry.set_text("")
    def _on_remove_clicked(self, widget):
        selected_row = self.listbox.get_selected_row()
        if selected_row and hasattr(selected_row, 'bookmark_index'):
            index_to_remove = selected_row.bookmark_index
            if 0 <= index_to_remove < len(self.bookmarks):
                del self.bookmarks[index_to_remove]
                self.save_bookmarks()
                self.populate_listbox() # Re-populate with correct indices
            else: print("Помилка: Некоректний індекс закладки.")
        else: self.show_warning_dialog("Будь ласка, виберіть закладку для видалення.")
    def _on_bookmark_activated(self, listbox, row):
        if hasattr(row, 'bookmark_index'):
            index = row.bookmark_index
            if 0 <= index < len(self.bookmarks):
                bookmark = self.bookmarks[index]
                url = bookmark.get('url')
                if url:
                    # Визначити, для якої сторінки ця закладка (проста евристика)
                    page_target = "youtube" # Default to YouTube
                    if "youtube.com" in url or "youtu.be" in url: page_target = "youtube"
                    elif url.startswith("http://") or url.startswith("https://"): page_target = "httrack" # Assume other http(s) are for httrack
                    self.app.go_to_page_with_url(page_target, url)
                else: self.show_warning_dialog("У цій закладці немає URL.")
            else: print("Помилка: Некоректний індекс закладки при активації.")
class AboutPage(BasePage):
    def build_ui(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        page.pack_start(Gtk.Label(label="<b><big>Про програму</big></b>", use_markup=True), False, False, 0)
        about_text = """<b>DownYS</b> - багатофункціональна програма для роботи з контентом.
<b>Можливості:</b>
 - Завантаження відео з YouTube (yt-dlp) з вибором формату та субтитрів
 - Конвертація відео/аудіо (FFmpeg)
 - Віддзеркалення веб-сайтів (HTTrack)
 - Архівування директорій (tar.gz, zip, ...)
 - Завантаження файлів на простий TCP сервер
 - Збереження URL у закладках
<b>Вимоги:</b> Python 3.x, PyGObject (GTK 3), yt-dlp, FFmpeg, HTTrack
<i>Переконайтеся, що FFmpeg та HTTrack встановлені та доступні у PATH.</i>"""
        label = Gtk.Label(label=about_text, use_markup=True, justify=Gtk.Justification.LEFT, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        page.pack_start(label, False, False, 5)
        page.show_all()
        self.page_widget = page
        return self.page_widget
class AppWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="DownYS", default_width=800, default_height=600)
        self.connect("destroy", Gtk.main_quit)
        self.host = "127.0.0.1"; self.port = 12345
        self._is_task_running = False; self._current_task_thread = None
        self.url_handler = URLHandler()
        header_bar = Gtk.HeaderBar(title="DownYS", show_close_button=True)
        self.set_titlebar(header_bar)
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(main_vbox)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack_sidebar = Gtk.StackSidebar(stack=self.stack)
        content_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        content_hbox.pack_start(self.stack_sidebar, False, False, 0)
        content_hbox.pack_start(self.stack, True, True, 0)
        main_vbox.pack_start(content_hbox, True, True, 0)
        self.pages = {}
        page_definitions = [
            ("bookmarks", "Закладки", BookmarksPage), # Додано Закладки першими
            ("youtube", "YouTube", YouTubePage),
            ("ffmpeg", "FFmpeg", FFmpegPage),
            ("httrack", "HTTrack/Архів", HTTrackPage),
            ("upload", "Завантаження", UploadPage),
            ("about", "Про програму", AboutPage),
        ]
        for name, title, page_class in page_definitions:
             page_instance = page_class(self, self.url_handler)
             page_widget = page_instance.build_ui()
             self.stack.add_titled(page_widget, name + "_page", title)
             self.pages[name] = page_instance
        status_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        main_vbox.pack_end(status_hbox, False, False, 0)
        self.status_label = Gtk.Label(label="Готово.", halign=Gtk.Align.START, ellipsize=Pango.EllipsizeMode.END, max_width_chars=80)
        status_hbox.pack_start(self.status_label, True, True, 0)
        self.progress_bar = Gtk.ProgressBar(show_text=True, text="")
        status_hbox.pack_end(self.progress_bar, False, False, 0)
        self.show_all()
    def go_to_page_with_url(self, page_name, url):
        page_widget_name = page_name + "_page"
        target_page = self.stack.get_child_by_name(page_widget_name)
        if target_page:
            self.stack.set_visible_child(target_page)
            page_instance = self.pages.get(page_name)
            if page_instance:
                url_entry = getattr(page_instance, 'url_entry', None) # Find the URL entry on the target page
                if url_entry and isinstance(url_entry, Gtk.Entry):
                     url_entry.set_text(url)
                     print(f"Перейшли на '{page_name}' та встановили URL: {url}")
                else: print(f"Помилка: Не знайдено поле URL на сторінці '{page_name}'.")
            else: print(f"Помилка: Не знайдено екземпляр сторінки '{page_name}'.")
        else: print(f"Помилка: Не знайдено сторінку з іменем '{page_widget_name}'.")
    def _start_task(self, task_func, args=(), kwargs=None):
        if self._is_task_running: self.show_warning_dialog("Завдання вже виконується."); return
        self._is_task_running = True
        GLib.idle_add(self._set_controls_sensitive, False); GLib.idle_add(self._update_progress, 0.0)
        GLib.idle_add(self._update_status, "Запуск завдання...")
        if kwargs is None: kwargs = {}
        original_kwargs = kwargs.copy()
        call_kwargs = {'status_callback': self._update_status}
        if task_func == download_youtube_video_with_progress: call_kwargs['progress_callback'] = self._update_progress
        elif task_func == run_ffmpeg_task: call_kwargs['progress_callback'] = self._update_progress
        elif task_func == upload_file_to_server: call_kwargs['update_progress_callback'] = self._update_progress
        if task_func == run_ffmpeg_task:
            if 'task_type' in original_kwargs: call_kwargs['task_type'] = original_kwargs['task_type']
            if 'task_options' in original_kwargs: call_kwargs['task_options'] = original_kwargs['task_options']
        # Передаємо решту аргументів з original_kwargs до download_youtube_video_with_progress
        elif task_func == download_youtube_video_with_progress:
             for key in ['format_selection', 'audio_format_override', 'download_subs', 'sub_langs', 'embed_subs']:
                 if key in original_kwargs: call_kwargs[key] = original_kwargs[key]
        def wrapper():
            try:
                task_func(*args, **call_kwargs)
                final_message = "Завдання успішно завершено."
                if task_func == run_httrack_web_threaded and original_kwargs.get('archive_after_mirror'):
                     mirror_dir = original_kwargs.get('mirror_output_dir'); archive_path = original_kwargs.get('post_mirror_archive_path')
                     site_url = original_kwargs.get('site_url')
                     if mirror_dir and archive_path:
                         if not os.path.isdir(mirror_dir): raise RuntimeError(f"Помилка архівації: директорія HTTrack '{mirror_dir}' не знайдена.")
                         GLib.idle_add(self._update_status, "HTTrack завершено. Запуск архівації...")
                         archive_directory_threaded(directory_to_archive=mirror_dir, archive_path=archive_path, status_callback=self._update_status, site_url=site_url)
                         final_message = "HTTrack та архівування завершено."
                     else: print("Warning: Missing args for post-HTTrack archiving."); final_message = "HTTrack завершено, помилка параметрів архівування."
                GLib.idle_add(self._on_task_complete, final_message)
            except Exception as e: import traceback; traceback.print_exc(); GLib.idle_add(self._on_task_error, str(e))
        self._current_task_thread = threading.Thread(target=wrapper, daemon=True); self._current_task_thread.start()
    def _on_task_complete(self, final_message="Завдання завершено."):
        self._is_task_running = False; GLib.idle_add(self._set_controls_sensitive, True)
        GLib.idle_add(self._update_progress, 1.0); GLib.idle_add(self._update_status, final_message)
        self._current_task_thread = None
    def _on_task_error(self, error_message):
        self._is_task_running = False; GLib.idle_add(self._set_controls_sensitive, True)
        GLib.idle_add(self._update_progress, 0.0); status_msg = f"Помилка: {error_message}"
        GLib.idle_add(self._update_status, status_msg)
        GLib.idle_add(self.show_warning_dialog, f"Під час виконання завдання сталася помилка:\n{error_message}")
        self._current_task_thread = None
    def _set_controls_sensitive(self, sensitive):
        for page_name, page_instance in self.pages.items():
            button = getattr(page_instance, 'execute_button', None) or getattr(page_instance, 'download_button', None)
            if button:
                 try: button.set_sensitive(sensitive)
                 except Exception as e: print(f"Warning: Sensitivity for button on page {page_name}: {e}")
        if hasattr(self.stack_sidebar, 'get_children'):
            try:
                 for child in self.stack_sidebar.get_children():
                      if isinstance(child, Gtk.StackSwitcher): child.set_sensitive(sensitive); break
            except Exception as e: print(f"Warning: sidebar sensitivity: {e}")
    def _update_progress(self, fraction):
        fraction = max(0.0, min(1.0, fraction)); self.progress_bar.set_fraction(fraction)
        self.progress_bar.set_text(f"{int(fraction*100)}%" if fraction > 0 or fraction == 1.0 else "")
    def _update_status(self, message): self.status_label.set_text(str(message)); print(f"STATUS: {message}")
    def show_warning_dialog(self, message):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, destroy_with_parent=True, message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK, text="Попередження")
        dialog.format_secondary_text(str(message)); dialog.run(); dialog.destroy()
    def _select_file_dialog(self, entry_widget, title, save_mode=False):
        if entry_widget is None or not hasattr(entry_widget, 'get_text'): print(f"Warning: _select_file_dialog invalid widget: {entry_widget}"); self.show_warning_dialog(f"Внутрішня помилка: Діалог для неіснуючого поля ({title})."); return
        action = Gtk.FileChooserAction.SAVE if save_mode else Gtk.FileChooserAction.OPEN
        dialog = Gtk.FileChooserDialog(title=title, parent=self, action=action, buttons=("_Скасувати", Gtk.ResponseType.CANCEL, ("_Зберегти" if save_mode else "_Відкрити"), Gtk.ResponseType.OK))
        current_path = entry_widget.get_text().strip(); current_page_name = self.stack.get_visible_child_name().replace("_page", "") if self.stack.get_visible_child_name() else None; page_instance = self.pages.get(current_page_name)
        if current_path:
             current_dir = os.path.dirname(current_path)
             if os.path.isdir(current_dir): dialog.set_current_folder(current_dir)
             elif os.path.isdir(current_path): dialog.set_current_folder(current_path)
             else: dialog.set_current_folder(os.path.expanduser("~"))
             if save_mode and not os.path.isdir(current_path): dialog.set_current_name(os.path.basename(current_path))
             elif not save_mode and os.path.isfile(current_path):
                  if os.path.isdir(current_dir): dialog.set_current_folder(current_dir)
                  dialog.set_filename(current_path)
        else:
            dialog.set_current_folder(os.path.expanduser("~"))
            if save_mode:
                suggested_name = None
                try:
                    if page_instance:
                         if current_page_name == "httrack":
                              if hasattr(page_instance, 'archive_radio') and page_instance.archive_radio.get_active() and hasattr(page_instance, '_suggest_archive_filename'): page_instance._suggest_archive_filename(getattr(page_instance, 'dir_to_archive_entry', Gtk.Entry()).get_text().strip(), dialog=dialog)
                              elif hasattr(page_instance, 'mirror_radio') and page_instance.mirror_radio.get_active() and hasattr(page_instance, 'archive_after_mirror_check') and page_instance.archive_after_mirror_check.get_active() and hasattr(page_instance, '_suggest_post_mirror_archive_filename'): page_instance._suggest_post_mirror_archive_filename(getattr(page_instance, 'mirror_output_dir_entry', Gtk.Entry()).get_text().strip(), getattr(page_instance, 'url_entry', Gtk.Entry()).get_text().strip(), dialog=dialog)
                         elif current_page_name == "ffmpeg" and hasattr(page_instance, 'task_combo'):
                              task_info = FFMPEG_TASKS.get(page_instance.task_combo.get_active_text()); ext = task_info.get("output_ext", ".out") if task_info else ".out"; suggested_name = f"output_converted{ext}"
                except Exception as e: print(f"Warning suggesting filename: {e}")
                if suggested_name and not dialog.get_filename(): dialog.set_current_name(suggested_name)
                elif not dialog.get_filename(): dialog.set_current_name("output_file")
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            selected_path = dialog.get_filename(); entry_widget.set_text(selected_path)
            if page_instance:
                 try:
                     if current_page_name == "ffmpeg" and hasattr(page_instance, '_update_output_suggestion') and entry_widget == getattr(page_instance, 'input_entry', None): page_instance._update_output_suggestion()
                     elif current_page_name == "httrack":
                          if entry_widget == getattr(page_instance, 'mirror_output_dir_entry', None) and hasattr(page_instance, '_on_mirror_input_changed'): page_instance._on_mirror_input_changed(entry_widget)
                          elif entry_widget == getattr(page_instance, 'dir_to_archive_entry', None) and hasattr(page_instance, '_on_archive_input_changed'): page_instance._on_archive_input_changed(entry_widget)
                 except Exception as e: print(f"Warning triggering page update after dialog: {e}")
        dialog.destroy()
    def _select_folder_dialog(self, entry_widget, title):
        if entry_widget is None or not hasattr(entry_widget, 'get_text'): print(f"Warning: _select_folder_dialog invalid widget: {entry_widget}"); self.show_warning_dialog(f"Внутрішня помилка: Діалог для неіснуючого поля ({title})."); return
        dialog = Gtk.FileChooserDialog(title=title, parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER, buttons=("_Скасувати", Gtk.ResponseType.CANCEL, "_Обрати", Gtk.ResponseType.OK))
        current_dir = entry_widget.get_text().strip()
        if current_dir and os.path.isdir(current_dir): dialog.set_current_folder(current_dir)
        else: dialog.set_current_folder(os.path.expanduser("~"))
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            selected_dir = dialog.get_filename(); entry_widget.set_text(selected_dir)
            current_page_name = self.stack.get_visible_child_name().replace("_page", "") if self.stack.get_visible_child_name() else None
            if current_page_name == "httrack":
                 page_instance = self.pages.get("httrack")
                 if page_instance:
                      try:
                          if entry_widget == getattr(page_instance, 'mirror_output_dir_entry', None) and hasattr(page_instance, '_on_mirror_input_changed'): page_instance._on_mirror_input_changed(entry_widget)
                          elif entry_widget == getattr(page_instance, 'dir_to_archive_entry', None) and hasattr(page_instance, '_on_archive_input_changed'): page_instance._on_archive_input_changed(entry_widget)
                      except Exception as e: print(f"Warning triggering page update after folder dialog: {e}")
        dialog.destroy()
if __name__ == "__main__":
    missing_deps = []
    try: subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except: missing_deps.append("FFmpeg")
    try: subprocess.run(['httrack', '--version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except: missing_deps.append("HTTrack")
    if missing_deps:
         dep_str = ", ".join(missing_deps); print(f"ПОПЕРЕДЖЕННЯ: Не знайдено: {dep_str}. Відповідні функції не працюватимуть.")
         win_temp = Gtk.Window(); dialog = Gtk.MessageDialog(transient_for=win_temp, modal=True, message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK, text="Залежності Відсутні")
         dialog.format_secondary_text(f"Не знайдено {dep_str}.\nВстановіть їх та додайте до PATH.\n\nВідповідні вкладки можуть працювати некоректно."); dialog.run(); dialog.destroy(); win_temp.destroy()
    app = AppWindow()
    Gtk.main()

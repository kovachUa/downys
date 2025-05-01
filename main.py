# -*- coding: utf-8 -*-
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

try:
    # Import task functions and page classes from script files
    from scripts.youtube import download_youtube_media, extract_youtube_info
    from scripts.upload_server import upload_file_to_server
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
# Dictionary defining available FFmpeg tasks, their types, expected output extensions,
# and any required parameters for the UI.
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
    """Handles URL parsing and validation, specifically for HTTrack needs."""
    def __init__(self):
        pass

    def validate_httrack_url(self, url_string):
        """Checks if a URL is valid for HTTrack (basic scheme and host check)."""
        if not url_string:
            raise ValueError("URL не може бути порожнім.")
        try:
            parsed_url = urlparse(url_string)
            allowed_schemes = ('http', 'https', 'ftp')
            if not parsed_url.scheme or parsed_url.scheme.lower() not in allowed_schemes:
                raise ValueError(f"Непідтримувана схема URL (очікується {', '.join(allowed_schemes)}).")
            if not parsed_url.netloc: # Checks for domain/IP address
                raise ValueError("Відсутнє ім'я хоста (домен) в URL.")
            return True
        except ValueError as e: # Catch parsing errors as well
             raise ValueError(f"Неприпустимий URL: {e}")
        except Exception as e: # Catch unexpected parsing issues
             raise ValueError(f"Не вдалося проаналізувати URL '{url_string}': {e}")

    def get_hostname_from_url(self, url_string, sanitize=True):
        """Extracts the hostname from a URL, optionally sanitizing it for filenames."""
        if not url_string:
            return None
        try:
            parsed_url = urlparse(url_string)
            hostname = parsed_url.hostname
            if hostname:
                # Optionally remove common "www." prefix
                if hostname.startswith("www."):
                     hostname = hostname[4:]
                if sanitize:
                    # Replace non-alphanumeric characters (except dot and hyphen) with underscores
                    hostname = re.sub(r'[^\w.-]+', '_', hostname).strip('_')
                    if not hostname: # Return None if sanitization results in empty string
                        return None
                return hostname
            return None # No hostname found in URL
        except Exception as e:
            print(f"Warning: Could not parse URL '{url_string}' for hostname: {e}")
            return None

# --- Base Class for Application Pages ---

class BasePage:
    """Base class for all pages (tabs) in the application."""
    def __init__(self, app_window, url_handler):
        self.app = app_window        # Reference to the main AppWindow instance
        self.url_handler = url_handler # Instance of URLHandler
        self.page_widget = None      # The main Gtk.Widget for this page

    def build_ui(self):
        """Builds the GTK widgets for the page. Must be implemented by subclasses."""
        raise NotImplementedError

    # --- Convenience methods to access AppWindow functions ---
    def _start_task(self, *args, **kwargs):
        """Starts a task via the main application window."""
        self.app._start_task(*args, **kwargs)

    def _select_file_dialog(self, *args, **kwargs):
        """Opens a file selection dialog via the main application window."""
        self.app._select_file_dialog(*args, **kwargs)

    def _select_folder_dialog(self, *args, **kwargs):
        """Opens a folder selection dialog via the main application window."""
        self.app._select_folder_dialog(*args, **kwargs)

    def show_warning_dialog(self, *args, **kwargs):
         """Shows a warning dialog via the main application window."""
         self.app.show_warning_dialog(*args, **kwargs)

    def get_page_widget(self):
         """Returns the main widget for this page."""
         # Check if the widget exists and is a valid Gtk.Widget
         if hasattr(self, 'page_widget') and isinstance(self.page_widget, Gtk.Widget):
             return self.page_widget
         elif self.page_widget is not None: # Fallback if type checking fails but exists
             return self.page_widget
         print(f"Warning: get_page_widget called on {type(self).__name__} but page_widget is not set or invalid.")
         return None

# --- Page Implementations ---

class YouTubePage(BasePage):
    """Page for downloading content from YouTube."""
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        # Initialize UI elements to None
        self.url_entry = None
        self.output_dir_entry = None
        self.download_button = None
        self.format_combo = None
        self.audio_format_label = None # Label for audio format combo
        self.audio_format_combo = None
        self.download_subs_check = None
        self.sub_langs_label = None # Label for subtitle languages entry
        self.sub_langs_entry = None
        self.embed_subs_check = None

    def build_ui(self):
        """Builds the YouTube download page UI."""
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        # Title
        self.page_widget.pack_start(Gtk.Label(label="<b><big>Завантаження YouTube</big></b>", use_markup=True), False, False, 0)

        # Input Grid
        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        self.page_widget.pack_start(grid, False, False, 0)

        # URL Input
        grid.attach(Gtk.Label(label="URL відео/списку:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.url_entry = Gtk.Entry(hexpand=True, placeholder_text="Вставте URL відео або плейлиста YouTube")
        grid.attach(self.url_entry, 1, 0, 3, 1)

        # Output Directory Input
        grid.attach(Gtk.Label(label="Дир. збереження:", halign=Gtk.Align.END), 0, 1, 1, 1)
        self.output_dir_entry = Gtk.Entry(hexpand=True)
        grid.attach(self.output_dir_entry, 1, 1, 2, 1)
        btn_out = Gtk.Button(label="...")
        btn_out.connect("clicked", lambda w: self._select_folder_dialog(self.output_dir_entry, "Оберіть директорію"))
        grid.attach(btn_out, 3, 1, 1, 1)

        # Format Selection ComboBox
        grid.attach(Gtk.Label(label="Формат/Якість:", halign=Gtk.Align.END), 0, 2, 1, 1)
        self.format_combo = Gtk.ComboBoxText()
        formats = {
            "best": "Найкраще Відео+Аудіо (WebM/MKV)",
            "best_mp4": "Найкраще Відео+Аудіо (MP4)",
            "audio_best": "Лише аудіо (Найкраще)",
            "audio_mp3": "Лише аудіо (MP3)",
            "audio_m4a": "Лише аудіо (M4A/AAC)"
            # "original": "Оригінальний формат (якщо єдиний файл)" # Often less useful
        }
        for key, value in formats.items():
            self.format_combo.append(key, value)
        self.format_combo.set_active_id("best") # Default selection
        self.format_combo.connect("changed", self._on_format_changed)
        grid.attach(self.format_combo, 1, 2, 3, 1)

        # Audio Format Override ComboBox (conditionally visible)
        self.audio_format_label = Gtk.Label(label="Аудіо кодек:", halign=Gtk.Align.END)
        self.audio_format_combo = Gtk.ComboBoxText()
        audio_formats = ['best', 'mp3', 'aac', 'm4a', 'opus', 'vorbis', 'wav'] # Common audio codecs/formats
        for fmt in audio_formats:
            self.audio_format_combo.append(fmt, fmt.upper())
        self.audio_format_combo.set_active_id("best") # Default selection
        grid.attach(self.audio_format_label, 0, 3, 1, 1)
        grid.attach(self.audio_format_combo, 1, 3, 3, 1)

        # Subtitle Options
        self.download_subs_check = Gtk.CheckButton(label="Завантажити субтитри")
        self.download_subs_check.connect("toggled", self._on_subs_toggled)
        grid.attach(self.download_subs_check, 0, 4, 2, 1)

        self.sub_langs_label = Gtk.Label(label="Мови суб. (через кому):", halign=Gtk.Align.END)
        self.sub_langs_entry = Gtk.Entry(text="uk,en") # Default languages
        grid.attach(self.sub_langs_label, 2, 4, 1, 1)
        grid.attach(self.sub_langs_entry, 3, 4, 1, 1)

        self.embed_subs_check = Gtk.CheckButton(label="Вбудувати субтитри (якщо можливо)") # Slightly more general label
        grid.attach(self.embed_subs_check, 0, 5, 2, 1)

        # Download Button
        self.download_button = Gtk.Button(label="Завантажити")
        self.download_button.connect("clicked", self._on_download_clicked)
        self.page_widget.pack_start(self.download_button, False, False, 5) # Add padding

        # Set initial state
        self._suggest_default_output_dir()
        self._update_options_visibility() # Set initial visibility of conditional controls

        self.page_widget.show_all()
        return self.page_widget

    def _suggest_default_output_dir(self):
        """Suggests a default download directory if the entry is empty."""
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads", "YouTube_DownYS")
        if self.output_dir_entry and not self.output_dir_entry.get_text():
            self.output_dir_entry.set_text(default_dir)

    def _update_options_visibility(self):
        """Shows/hides subtitle and audio format options based on selections."""
        # Ensure all widgets are created before proceeding
        if not all([hasattr(self, w) and getattr(self, w) for w in [
                    'format_combo', 'download_subs_check', 'audio_format_label',
                    'audio_format_combo', 'sub_langs_label', 'sub_langs_entry',
                    'embed_subs_check']]):
            return # Widgets not ready yet

        format_id = self.format_combo.get_active_id()
        is_audio = format_id is not None and format_id.startswith("audio_")
        subs_active = self.download_subs_check.get_active()

        # Show audio format combo only for audio-only selections
        self.audio_format_label.set_visible(is_audio)
        self.audio_format_combo.set_visible(is_audio)

        # Show subtitle language entry only if downloading subs
        self.sub_langs_label.set_visible(subs_active)
        self.sub_langs_entry.set_visible(subs_active)

        # Show embed option only if downloading subs AND it's not audio-only format
        self.embed_subs_check.set_visible(subs_active and not is_audio)

    def _on_format_changed(self, combo):
        """Handles changes in the main format selection."""
        self._update_options_visibility() # Update visibility first
        format_id = combo.get_active_id()
        # Auto-select corresponding audio format if specific audio type is chosen
        if hasattr(self, 'audio_format_combo') and self.audio_format_combo:
            if format_id == "audio_mp3":
                self.audio_format_combo.set_active_id("mp3")
            elif format_id == "audio_m4a":
                self.audio_format_combo.set_active_id("m4a") # Match common container/codec pair
            elif format_id is not None and format_id.startswith("audio_"):
                self.audio_format_combo.set_active_id("best") # Default for "audio_best"

    def _on_subs_toggled(self, check):
        """Handles toggling the 'Download Subtitles' checkbox."""
        self._update_options_visibility()

    def _on_download_clicked(self, widget):
        """Starts the YouTube download process when the button is clicked."""
        if self.app._is_task_running:
            self.show_warning_dialog("Завдання вже виконується.")
            return
        try:
            # Ensure all necessary widgets exist
            if not all([hasattr(self, w) and getattr(self, w) for w in [
                        'url_entry', 'output_dir_entry', 'format_combo', 'audio_format_combo',
                        'download_subs_check', 'sub_langs_entry', 'embed_subs_check']]):
                 raise RuntimeError("Внутрішня помилка: Віджети YouTube не ініціалізовані.")

            # Get values from UI elements
            url = self.url_entry.get_text().strip()
            output_dir = self.output_dir_entry.get_text().strip()
            format_selection = self.format_combo.get_active_id() or "best"
            audio_format_override = None
            if (self.format_combo.get_active_id() or "").startswith("audio_"):
                audio_format_override = self.audio_format_combo.get_active_id()

            download_subs = self.download_subs_check.get_active()
            sub_langs = self.sub_langs_entry.get_text().strip() if download_subs else None
            embed_subs = self.embed_subs_check.get_active() if download_subs else False

            # --- Input Validation ---
            if not url: raise ValueError("URL відео YouTube не може бути порожнім.")
            if not output_dir: raise ValueError("Будь ласка, оберіть директорію для збереження.")

            # Warn if downloading subs but languages are empty, use default
            if download_subs and not sub_langs:
                 self.show_warning_dialog("Вказано завантаження субтитрів, але не вказано мови. Будуть використані стандартні (uk,en).")
                 sub_langs = "uk,en" # Set default

            # Ensure output directory exists
            if not os.path.isdir(output_dir):
                try:
                    os.makedirs(output_dir, exist_ok=True)
                except OSError as e:
                    raise ValueError(f"Не вдалося створити директорію '{output_dir}': {e}")

            # --- Start Download Task ---
            # Call the correctly imported function
            self._start_task(
                download_youtube_media, # Use the function from youtube.py
                args=(url, output_dir), # Pass URL string (handled by function) and output dir
                kwargs={                  # Pass specific options as keyword arguments
                    'format_selection': format_selection,
                    'audio_format_override': audio_format_override,
                    'download_subs': download_subs,
                    'sub_langs': sub_langs,
                    'embed_subs': embed_subs,
                    # Callbacks (status_callback, progress_callback) are added automatically by _start_task
                }
            )
        except (ValueError, RuntimeError, FileNotFoundError) as e:
            # Show user-friendly errors
            self.show_warning_dialog(str(e))
        except Exception as e:
            # Show unexpected errors
            import traceback
            traceback.print_exc()
            self.show_warning_dialog(f"Неочікувана помилка YouTube: {e}")


class FFmpegPage(BasePage):
    """Page for performing FFmpeg media conversion tasks."""
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        # Initialize UI elements
        self.task_combo = None
        self.params_box = None      # Container for dynamic parameters
        self.param_entries = {}     # Dictionary to hold parameter entry widgets
        self.input_entry = None
        self.output_entry = None
        self.execute_button = None

    def build_ui(self):
        """Builds the FFmpeg conversion page UI."""
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        # Title
        self.page_widget.pack_start(Gtk.Label(label="<b><big>FFmpeg Конвертація</big></b>", use_markup=True), False, False, 0)

        # Input Grid
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self.page_widget.pack_start(grid, False, False, 0)

        # Task Selection ComboBox
        grid.attach(Gtk.Label(label="Завдання FFmpeg:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.task_combo = Gtk.ComboBoxText()
        for label in FFMPEG_TASKS.keys():
            self.task_combo.append_text(label)
        self.task_combo.set_active(0) # Select the first task by default
        self.task_combo.connect("changed", self._on_task_changed)
        grid.attach(self.task_combo, 1, 0, 3, 1)

        # Dynamic Parameter Area
        self.params_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        grid.attach(self.params_box, 0, 1, 4, 1) # Span across grid columns

        # Input File Selection
        grid.attach(Gtk.Label(label="Вхідний файл:", halign=Gtk.Align.END), 0, 2, 1, 1)
        self.input_entry = Gtk.Entry(hexpand=True)
        self.input_entry.connect("changed", self._update_output_suggestion) # Update output suggestion on change
        grid.attach(self.input_entry, 1, 2, 2, 1)
        btn_in = Gtk.Button(label="...")
        btn_in.connect("clicked", lambda w: self._select_file_dialog(self.input_entry, "Оберіть вхідний файл"))
        grid.attach(btn_in, 3, 2, 1, 1)

        # Output File Selection
        grid.attach(Gtk.Label(label="Вихідний файл:", halign=Gtk.Align.END), 0, 3, 1, 1)
        self.output_entry = Gtk.Entry(hexpand=True)
        grid.attach(self.output_entry, 1, 3, 2, 1)
        btn_out = Gtk.Button(label="...")
        btn_out.connect("clicked", lambda w: self._select_file_dialog(self.output_entry, "Оберіть вихідний файл", save_mode=True))
        grid.attach(btn_out, 3, 3, 1, 1)

        # Execute Button
        self.execute_button = Gtk.Button(label="Виконати")
        self.execute_button.connect("clicked", self._on_execute_clicked)
        self.page_widget.pack_start(self.execute_button, False, False, 5) # Add padding

        self.page_widget.show_all()
        GLib.idle_add(self._on_task_changed, self.task_combo) # Trigger initial parameter population and output suggestion
        return self.page_widget

    def _on_task_changed(self, combo):
        """Handles changes in the selected FFmpeg task."""
        selected_label = combo.get_active_text()
        if not selected_label: return
        task_info = FFMPEG_TASKS.get(selected_label)
        if not task_info: return

        # --- Clear existing parameters ---
        if hasattr(self, 'params_box') and self.params_box:
             # Use get_children() which is standard
             children = self.params_box.get_children()
             for widget in children:
                 self.params_box.remove(widget)
        self.param_entries = {} # Reset the dictionary holding entry widgets

        # --- Build new parameters based on task_info ---
        if hasattr(self, 'params_box') and self.params_box:
             for param_spec in task_info.get("params", []):
                 hbox = Gtk.Box(spacing=5) # Use HBox for label + entry
                 hbox.pack_start(Gtk.Label(label=f"{param_spec['label']}:"), False, False, 0)

                 if param_spec["type"] == "entry":
                     entry = Gtk.Entry(text=param_spec.get("default", ""))
                     entry.set_hexpand(True) # Allow entry to expand
                     hbox.pack_start(entry, True, True, 0)
                     # Store the entry widget for later retrieval
                     self.param_entries[param_spec["name"]] = entry
                 # Add other widget types (e.g., ComboBox, CheckButton) here if needed
                 # elif param_spec["type"] == "checkbox": ...

                 self.params_box.pack_start(hbox, False, False, 0)
             self.params_box.show_all() # Show the newly added parameter widgets

        # Update the suggested output filename based on the new task
        self._update_output_suggestion()

    def _update_output_suggestion(self, *args):
        """Suggests an output filename based on input file and selected task."""
        # Ensure widgets are initialized
        if not all([hasattr(self, w) and getattr(self, w) for w in [
                    'input_entry', 'output_entry', 'task_combo']]):
            return

        input_path = self.input_entry.get_text().strip()
        output_path = self.output_entry.get_text().strip()
        active_task_label = self.task_combo.get_active_text()

        if not active_task_label: return # No task selected
        task_info = FFMPEG_TASKS.get(active_task_label)
        # Determine the expected output extension for the selected task
        output_ext = task_info.get("output_ext", ".out") if task_info else ".out"

        update_needed = False
        suggested_path = ""

        # If there's a valid input file path:
        if input_path and os.path.isfile(input_path):
            input_dir = os.path.dirname(input_path) or "." # Get directory, default to current
            base, _ = os.path.splitext(os.path.basename(input_path)) # Get filename without extension
            # Suggest a name like "inputfile_converted.mp4" in the same directory
            suggested_path = os.path.join(input_dir, f"{base}_converted{output_ext}")

            # Update if output is empty OR if output seems like a previous suggestion/wrong extension
            if not output_path:
                update_needed = True
            else:
                 out_dir = os.path.dirname(output_path)
                 out_base, out_ext = os.path.splitext(os.path.basename(output_path))
                 # Check if output is in the same directory AND
                 # (name starts like suggested OR extension doesn't match current task)
                 if out_dir == input_dir and \
                    (out_base.startswith(f"{base}_converted") or out_ext.lower() != output_ext.lower()):
                     update_needed = True
        # If both input and output are empty:
        elif not input_path and not output_path:
            # Suggest a default name in the user's home directory
            suggested_path = os.path.join(os.path.expanduser("~"), f"output_converted{output_ext}")
            update_needed = True

        # If an update is needed, set the output entry text
        if update_needed and suggested_path:
            self.output_entry.set_text(suggested_path)

    def _on_execute_clicked(self, widget):
        """Starts the FFmpeg conversion task when the button is clicked."""
        if self.app._is_task_running:
            self.show_warning_dialog("Завдання вже виконується.")
            return
        try:
            # Ensure widgets exist
            if not all([hasattr(self, w) and getattr(self, w) for w in [
                        'task_combo', 'input_entry', 'output_entry']]):
                 raise RuntimeError("Внутрішня помилка: Віджети FFmpeg не ініціалізовані.")

            # Get selected task
            active_task_label = self.task_combo.get_active_text()
            if not active_task_label: raise ValueError("Будь ласка, оберіть завдання FFmpeg.")
            task_info = FFMPEG_TASKS.get(active_task_label)
            if not task_info: raise ValueError("Обрано невідоме завдання FFmpeg.")

            # --- Get Task Parameters ---
            task_type = task_info["type"]
            task_options = {}
            # Iterate through the parameter specifications for the selected task
            for spec in task_info.get("params", []):
                name = spec["name"]
                entry = self.param_entries.get(name) # Get the corresponding entry widget
                if entry:
                    value = entry.get_text().strip()
                    # Validate required parameters
                    if not value and spec.get("required"):
                        raise ValueError(f"Параметр '{spec['label']}' є обов'язковим.")
                    task_options[name] = value
                elif spec.get("required"):
                    # This indicates an internal inconsistency if a required param widget is missing
                    raise RuntimeError(f"Внутрішня помилка: віджет для обов'язкового параметра '{spec['label']}' не знайдено.")

            # --- Get Input/Output Paths ---
            input_path = self.input_entry.get_text().strip()
            output_path = self.output_entry.get_text().strip()

            # --- Input Validation ---
            if not input_path: raise ValueError("Оберіть вхідний файл.")
            if not os.path.isfile(input_path): raise ValueError(f"Вхідний файл не знайдено: {input_path}")
            if not output_path: raise ValueError("Вкажіть вихідний файл.")

            # Ensure output directory exists
            out_dir = os.path.dirname(output_path)
            if out_dir and not os.path.isdir(out_dir):
                try: os.makedirs(out_dir, exist_ok=True)
                except OSError as e: raise ValueError(f"Не вдалося створити директорію '{out_dir}': {e}")

            # Prevent overwriting input with output using the same filename
            if os.path.exists(input_path) and os.path.exists(output_path):
                try:
                     # Use os.path.samefile for robust check (handles symlinks etc.)
                     if os.path.samefile(input_path, output_path):
                         raise ValueError("Вхідний та вихідний файли не можуть бути однаковими.")
                except FileNotFoundError: pass # If one doesn't exist, comparison isn't needed
                except OSError as e_samefile: # Catch potential OS errors during samefile check
                    print(f"Помилка перевірки samefile: {e_samefile}") # Log warning, but proceed

            # --- Start FFmpeg Task ---
            self._start_task(run_ffmpeg_task,
                             args=(input_path, output_path),
                             kwargs={'task_type': task_type, 'task_options': task_options})
        except (ValueError, RuntimeError, FileNotFoundError) as e:
            self.show_warning_dialog(str(e))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.show_warning_dialog(f"Неочікувана помилка FFmpeg: {e}")


class HTTrackPage(BasePage):
    """Page for mirroring websites with HTTrack and archiving directories."""
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        # Operation selection
        self.mirror_radio = None
        self.archive_radio = None
        self.stack = None           # To switch between mirror/archive options
        self.execute_button = None
        # Mirror widgets
        self.url_entry = None
        self.mirror_output_dir_entry = None
        self.archive_after_mirror_check = None
        self.post_mirror_archive_hbox = None # Container for archive path
        self.post_mirror_archive_entry = None
        # Archive widgets
        self.dir_to_archive_entry = None
        self.archive_file_entry = None

    def build_ui(self):
        """Builds the HTTrack/Archive page UI."""
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        # Title
        self.page_widget.pack_start(Gtk.Label(label="<b><big>HTTrack та Архівування</big></b>", use_markup=True), False, False, 0)

        # Grid for layout
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self.page_widget.pack_start(grid, False, False, 0)

        # --- Operation selection (Radio buttons) ---
        grid.attach(Gtk.Label(label="Дія:", halign=Gtk.Align.END), 0, 0, 1, 1)
        hbox_op = Gtk.Box(spacing=10)
        grid.attach(hbox_op, 1, 0, 3, 1)
        # Mirror Radio Button
        self.mirror_radio = Gtk.RadioButton.new_with_label_from_widget(None, "Віддзеркалити / Оновити сайт")
        self.mirror_radio.set_active(True) # Default to mirror mode
        self.mirror_radio.connect("toggled", self._on_operation_toggled)
        hbox_op.pack_start(self.mirror_radio, False, False, 0)
        # Archive Radio Button
        self.archive_radio = Gtk.RadioButton.new_with_label_from_widget(self.mirror_radio, "Архівувати директорію")
        self.archive_radio.connect("toggled", self._on_operation_toggled)
        hbox_op.pack_start(self.archive_radio, False, False, 0)

        # --- Stack for switching between mirror/archive options ---
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        grid.attach(self.stack, 0, 1, 4, 1) # Span across grid columns

        # --- Build Mirror UI section ---
        mirror_vbox = self._build_mirror_ui()
        self.stack.add_titled(mirror_vbox, "mirror_section", "Mirror Options") # Add with a name

        # --- Build Archive UI section ---
        archive_vbox = self._build_archive_ui()
        self.stack.add_titled(archive_vbox, "archive_section", "Archive Options") # Add with a name

        # --- Execute Button ---
        self.execute_button = Gtk.Button(label="Виконати HTTrack") # Label updates dynamically
        self.execute_button.connect("clicked", self._on_execute_clicked)
        self.page_widget.pack_start(self.execute_button, False, False, 5) # Add padding

        # --- Initial Setup ---
        self._suggest_default_paths() # Suggest initial paths
        self.stack.set_visible_child_name("mirror_section") # Start with mirror view
        GLib.idle_add(self._update_ui_state) # Ensure initial UI state (button label, visibility) is correct
        self.page_widget.show_all()
        # Hide the initially invisible post-mirror archive hbox properly
        if self.post_mirror_archive_hbox:
            self.post_mirror_archive_hbox.set_visible(False)
        return self.page_widget

    def _build_mirror_ui(self):
        """Builds the widgets specific to the Mirror operation."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        # --- URL Entry ---
        grid1 = Gtk.Grid(column_spacing=10, row_spacing=5)
        vbox.pack_start(grid1, False, False, 0)
        grid1.attach(Gtk.Label(label="URL сайту:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.url_entry = Gtk.Entry(hexpand=True, placeholder_text="Введіть URL сайту для віддзеркалення")
        self.url_entry.connect("changed", self._on_mirror_input_changed) # Update suggestion on change
        grid1.attach(self.url_entry, 1, 0, 3, 1)

        # --- Mirror Output Directory ---
        grid2 = Gtk.Grid(column_spacing=10, row_spacing=5)
        vbox.pack_start(grid2, False, False, 0)
        grid2.attach(Gtk.Label(label="Дир. збереження:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.mirror_output_dir_entry = Gtk.Entry(hexpand=True)
        self.mirror_output_dir_entry.connect("changed", self._on_mirror_input_changed) # Update suggestion on change
        grid2.attach(self.mirror_output_dir_entry, 1, 0, 2, 1)
        btn1 = Gtk.Button(label="...")
        btn1.connect("clicked", lambda w: self._select_folder_dialog(self.mirror_output_dir_entry, "Оберіть директорію"))
        grid2.attach(btn1, 3, 0, 1, 1)

        # --- Archive After Mirror Option ---
        self.archive_after_mirror_check = Gtk.CheckButton(label="Архівувати результат віддзеркалення")
        self.archive_after_mirror_check.connect("toggled", self._on_archive_after_mirror_toggled)
        vbox.pack_start(self.archive_after_mirror_check, False, False, 0)

        # --- Post-Mirror Archive File Path (conditionally visible) ---
        # Use no_show_all=True so set_visible works correctly initially
        self.post_mirror_archive_hbox = Gtk.Box(spacing=10, no_show_all=True)
        vbox.pack_start(self.post_mirror_archive_hbox, False, False, 0)
        # Add label, entry, and button to the hbox
        lbl = Gtk.Label(label="Файл архіву:")
        self.post_mirror_archive_hbox.pack_start(lbl, False, False, 0)
        self.post_mirror_archive_entry = Gtk.Entry(hexpand=True)
        self.post_mirror_archive_hbox.pack_start(self.post_mirror_archive_entry, True, True, 0)
        btn2 = Gtk.Button(label="...")
        btn2.connect("clicked", lambda w: self._select_file_dialog(self.post_mirror_archive_entry, "Оберіть файл архіву", save_mode=True))
        self.post_mirror_archive_hbox.pack_start(btn2, False, False, 0)

        return vbox

    def _build_archive_ui(self):
        """Builds the widgets specific to the Archive operation."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        # --- Directory to Archive ---
        grid1 = Gtk.Grid(column_spacing=10, row_spacing=5)
        vbox.pack_start(grid1, False, False, 0)
        grid1.attach(Gtk.Label(label="Дир. для архів.:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.dir_to_archive_entry = Gtk.Entry(hexpand=True)
        self.dir_to_archive_entry.connect("changed", self._on_archive_input_changed) # Update suggestion on change
        grid1.attach(self.dir_to_archive_entry, 1, 0, 2, 1)
        btn1 = Gtk.Button(label="...")
        btn1.connect("clicked", lambda w: self._select_folder_dialog(self.dir_to_archive_entry, "Оберіть директорію"))
        grid1.attach(btn1, 3, 0, 1, 1)

        # --- Archive File Path ---
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
        """Suggests default paths for mirror output and archive source."""
        default_mirror_dir = os.path.join(os.path.expanduser("~"), "httrack_mirrors")

        # Suggest mirror output directory if empty
        if hasattr(self, 'mirror_output_dir_entry') and self.mirror_output_dir_entry and not self.mirror_output_dir_entry.get_text():
            self.mirror_output_dir_entry.set_text(default_mirror_dir)

        # Suggest source directory for archiving (defaults to mirror dir) if empty
        if hasattr(self, 'dir_to_archive_entry') and self.dir_to_archive_entry and not self.dir_to_archive_entry.get_text():
             self.dir_to_archive_entry.set_text(default_mirror_dir)
             # Also suggest archive filename based on this default dir (if in archive mode)
             if hasattr(self, 'archive_radio') and self.archive_radio and self.archive_radio.get_active():
                 self._suggest_archive_filename(default_mirror_dir)

    def _suggest_archive_filename(self, source_dir, dialog=None):
        """Suggests an archive filename based on the source directory.
           Can update either the entry widget or a FileChooserDialog.
        """
        # Ensure the target widget for the archive filename exists
        if not hasattr(self, 'archive_file_entry') or not self.archive_file_entry: return
        target_entry = self.archive_file_entry # This is for the dedicated Archive section
        default_ext = ".tar.gz" # Preferred archive format
        suggested_name = f"archive{default_ext}" # Generic default
        base_save_path = os.path.expanduser("~") # Default save location (home dir)

        # Try to generate a more specific name based on the source directory
        if source_dir and os.path.isdir(source_dir):
            # Try to save archive in the parent directory of the source
            parent = os.path.dirname(os.path.abspath(source_dir)) or base_save_path
            base_save_path = parent
            # Use the source directory's name as the base for the archive filename
            base = os.path.basename(os.path.normpath(source_dir)) or "archive"
            # Sanitize the base name for filesystem compatibility
            clean = re.sub(r'[^\w.-]+', '_', base).strip('_') or "archive"
            # Add timestamp for uniqueness
            ts = datetime.datetime.now().strftime("%Y%m%d")
            suggested_name = f"{ts}_{clean}{default_ext}"
        elif source_dir: # If source_dir is just text (not a valid dir), use it as base
            base = os.path.basename(os.path.normpath(source_dir))
            if base:
                 clean = re.sub(r'[^\w.-]+', '_', base).strip('_') or "archive"
                 ts = datetime.datetime.now().strftime("%Y%m%d")
                 suggested_name = f"{ts}_{clean}{default_ext}"

        # Construct the full suggested path
        suggested_path = os.path.join(base_save_path, suggested_name)

        # Update the FileChooserDialog or the entry widget
        if dialog: # If called from _select_file_dialog
            dialog.set_current_name(suggested_name)
            folder_to_set = os.path.dirname(suggested_path)
            # Set the dialog's current folder
            if os.path.isdir(folder_to_set):
                dialog.set_current_folder(folder_to_set)
            elif os.path.isdir(base_save_path): # Fallback
                dialog.set_current_folder(base_save_path)
        else: # If called directly (e.g., on input change)
            current = target_entry.get_text().strip()
            # Update the entry field only if it's empty or looks like a previous default
            if not current or os.path.basename(current).startswith("archive."):
                target_entry.set_text(suggested_path)

    def _suggest_post_mirror_archive_filename(self, mirror_dir, url, dialog=None):
        """Suggests an archive filename after mirroring, based on URL or mirror directory.
           Can update either the entry widget or a FileChooserDialog.
        """
        # Ensure the target widget for the post-mirror archive filename exists
        if not hasattr(self, 'post_mirror_archive_entry') or not self.post_mirror_archive_entry: return
        target_entry = self.post_mirror_archive_entry # This is for the Mirror section's option
        default_ext = ".tar.gz"
        base_name = "website" # Generic default base name

        # Try to get a name from the URL's hostname first
        hostname = self.url_handler.get_hostname_from_url(url)
        if hostname:
            base_name = hostname
        # Fallback to using the mirror directory's name if hostname fails
        elif mirror_dir and os.path.isdir(mirror_dir):
             dir_base = os.path.basename(os.path.normpath(mirror_dir))
             if dir_base:
                  # Sanitize the directory name
                  clean_dir = re.sub(r'[^\w.-]+', '_', dir_base).strip('_')
                  if clean_dir: base_name = clean_dir # Use cleaned dir name if valid

        # Add timestamp and construct suggested name
        ts = datetime.datetime.now().strftime("%Y%m%d")
        suggested_name = f"{ts}_{base_name}_archive{default_ext}"
        base_save_path = os.path.expanduser("~") # Default save location

        # Try to save the archive in the parent directory of the mirror
        if mirror_dir:
             try: # Use try-except for path operations
                 abs_mirror_dir = os.path.abspath(mirror_dir)
                 parent = os.path.dirname(abs_mirror_dir) or base_save_path
                 if os.path.isdir(parent): # Ensure parent exists
                    base_save_path = parent
             except Exception as e:
                 print(f"Warning getting parent dir for suggestion: {e}")


        # Construct the full suggested path
        suggested_path = os.path.join(base_save_path, suggested_name)

        # Update the FileChooserDialog or the entry widget
        if dialog: # If called from _select_file_dialog
            dialog.set_current_name(suggested_name)
            folder_to_set = os.path.dirname(suggested_path)
            # Set the dialog's current folder
            if os.path.isdir(folder_to_set):
                dialog.set_current_folder(folder_to_set)
            elif os.path.isdir(base_save_path): # Fallback
                 dialog.set_current_folder(base_save_path)
        else: # If called directly
            current = target_entry.get_text().strip()
            # Update the entry field only if it's empty or looks like a previous default
            if not current or os.path.basename(current).startswith(("website_archive.", "archive.")):
                target_entry.set_text(suggested_path)

    def _update_ui_state(self, *args):
        """Switches the Stack view, updates button label, and visibility based on radio selection."""
        # Ensure widgets are initialized
        if not all([hasattr(self, w) and getattr(self, w) for w in [
                    'mirror_radio', 'stack', 'execute_button',
                    'archive_after_mirror_check', 'post_mirror_archive_hbox']]):
            # print("Debug: _update_ui_state called before widgets are ready.")
            return

        is_mirror_mode = self.mirror_radio.get_active()

        if is_mirror_mode:
            self.stack.set_visible_child_name("mirror_section")
            self.execute_button.set_label("Виконати HTTrack")
            # Show/hide post-mirror archive controls based on the checkbox
            self.post_mirror_archive_hbox.set_visible(self.archive_after_mirror_check.get_active())
        else: # Archive mode
            self.stack.set_visible_child_name("archive_section")
            self.execute_button.set_label("Архівувати")
            # Ensure post-mirror controls are always hidden in archive mode
            self.post_mirror_archive_hbox.set_visible(False)

    def _on_operation_toggled(self, radio_button):
        """Handles radio button changes to update UI and suggest filenames."""
        # Act only when the toggled button becomes active
        if radio_button.get_active():
            self._update_ui_state() # Update visibility and button label first
            is_mirror_mode = (radio_button == self.mirror_radio)

            # Suggest filename if switching to a relevant mode/option
            if is_mirror_mode and self.archive_after_mirror_check.get_active():
                # Suggest post-mirror archive name if checkbox is already active
                url_entry = getattr(self, 'url_entry', None)
                mirror_dir_entry = getattr(self, 'mirror_output_dir_entry', None)
                url = url_entry.get_text().strip() if url_entry else ""
                mirror_dir = mirror_dir_entry.get_text().strip() if mirror_dir_entry else ""
                self._suggest_post_mirror_archive_filename(mirror_dir, url)
            elif not is_mirror_mode: # Switched to Archive mode
                 # Suggest regular archive name based on current source dir entry
                 dir_entry = getattr(self, 'dir_to_archive_entry', None)
                 source_dir = dir_entry.get_text().strip() if dir_entry else ""
                 self._suggest_archive_filename(source_dir)

    def _on_archive_after_mirror_toggled(self, check_button):
        """Handles the 'archive after mirror' checkbox toggle."""
        self._update_ui_state() # Updates visibility of the hbox
        if check_button.get_active():
             # Suggest filename when checkbox is activated
             url_entry = getattr(self, 'url_entry', None)
             mirror_dir_entry = getattr(self, 'mirror_output_dir_entry', None)
             url = url_entry.get_text().strip() if url_entry else ""
             mirror_dir = mirror_dir_entry.get_text().strip() if mirror_dir_entry else ""
             self._suggest_post_mirror_archive_filename(mirror_dir, url)

    def _on_mirror_input_changed(self, entry):
        """Suggests post-mirror archive name when URL or mirror dir changes (if enabled)."""
        # Check if in mirror mode and the archive checkbox is active
        if hasattr(self, 'mirror_radio') and self.mirror_radio and self.mirror_radio.get_active() and \
           hasattr(self, 'archive_after_mirror_check') and self.archive_after_mirror_check and self.archive_after_mirror_check.get_active():
             # Get current URL and mirror directory
             url_entry = getattr(self, 'url_entry', None)
             mirror_dir_entry = getattr(self, 'mirror_output_dir_entry', None)
             url = url_entry.get_text().strip() if url_entry else ""
             mirror_dir = mirror_dir_entry.get_text().strip() if mirror_dir_entry else ""
             # Trigger suggestion update
             self._suggest_post_mirror_archive_filename(mirror_dir, url)

    def _on_archive_input_changed(self, entry):
         """Suggests archive name when source directory changes (in archive mode)."""
         # Check if in archive mode
         if hasattr(self, 'archive_radio') and self.archive_radio and self.archive_radio.get_active():
             # Trigger suggestion update based on the new directory path
             self._suggest_archive_filename(entry.get_text().strip())

    def _on_execute_clicked(self, widget):
        """Determines the current mode (Mirror or Archive) and calls the appropriate execution method."""
        if self.app._is_task_running:
            self.show_warning_dialog("Завдання вже виконується.")
            return
        try:
            # Ensure radio buttons exist
            if not all([hasattr(self, w) and getattr(self, w) for w in ['mirror_radio', 'archive_radio']]):
                 raise RuntimeError("Внутрішня помилка: Радіокнопки HTTrack/Архів не ініціалізовані.")

            # Call the specific execution function based on the active radio button
            if self.mirror_radio.get_active():
                self._execute_mirror()
            elif self.archive_radio.get_active():
                self._execute_archive()
        except (ValueError, RuntimeError, FileNotFoundError) as e:
            self.show_warning_dialog(str(e))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.show_warning_dialog(f"Неочікувана помилка HTTrack/Архів: {e}")

    def _execute_mirror(self):
        """Validates mirror inputs and starts the HTTrack task."""
        # Ensure all required mirror widgets are present
        if not all([hasattr(self, attr) and getattr(self, attr) for attr in
                   ['url_entry', 'mirror_output_dir_entry', 'archive_after_mirror_check', 'post_mirror_archive_entry']]):
            raise RuntimeError("Внутрішня помилка: Віджети Mirror не ініціалізовані.")

        # Get values from UI
        url = self.url_entry.get_text().strip()
        mirror_dir = self.mirror_output_dir_entry.get_text().strip()
        archive_after = self.archive_after_mirror_check.get_active()
        archive_path = self.post_mirror_archive_entry.get_text().strip() if archive_after else None

        # --- Input Validation ---
        try:
            # Validate URL format for HTTrack
            self.url_handler.validate_httrack_url(url)
        except ValueError as e:
            self.show_warning_dialog(f"Неприпустимий URL: {e}")
            return # Stop if URL is invalid

        if not mirror_dir: raise ValueError("Вкажіть директорію для збереження дзеркала.")
        # Ensure mirror directory exists
        try:
            os.makedirs(mirror_dir, exist_ok=True)
        except OSError as e:
            raise ValueError(f"Не вдалося створити/перевірити директорію '{mirror_dir}': {e}")

        # Validate archive path if archiving is enabled
        if archive_after:
            if not archive_path: raise ValueError("Вкажіть шлях для файлу архіву.")
            # Ensure archive destination directory exists
            arc_dir = os.path.dirname(archive_path)
            if arc_dir:
                 try: os.makedirs(arc_dir, exist_ok=True)
                 except OSError as e: raise ValueError(f"Не вдалося створити директорію для архіву '{arc_dir}': {e}")

            # Basic check: warn if archive is being saved inside the mirror directory
            try:
                # Get absolute paths for reliable comparison
                abs_mirror_dir = os.path.abspath(mirror_dir)
                abs_archive_path = os.path.abspath(archive_path)
                # Check if archive path starts with mirror path + separator
                if abs_archive_path != abs_mirror_dir and abs_archive_path.startswith(abs_mirror_dir + os.sep):
                    # Show a non-blocking warning dialog for this case
                    self.show_warning_dialog("Попередження: Архів зберігається всередині директорії дзеркала. Це може призвести до рекурсії або неочікуваних результатів.")
            except Exception as path_e: # Catch potential errors during path normalization/check
                print(f"Warning checking archive path within mirror path: {path_e}")

        # --- Start HTTrack Task ---
        # Pass necessary args/kwargs for potential chaining (archiving) in _start_task
        self._start_task(run_httrack_web_threaded,
                         args=(url, mirror_dir),
                         kwargs={'archive_after_mirror': archive_after,
                                 'post_mirror_archive_path': archive_path,
                                 'mirror_output_dir': mirror_dir, # Needed for chaining check
                                 'site_url': url}) # Pass URL for context if archiving later

    def _execute_archive(self):
         """Validates archive inputs and starts the archiving task."""
         # Ensure required archive widgets are present
         if not all([hasattr(self, w) and getattr(self, w) for w in ['dir_to_archive_entry', 'archive_file_entry']]):
             raise RuntimeError("Внутрішня помилка: Віджети Archive не ініціалізовані.")

         # Get values from UI
         source_dir = self.dir_to_archive_entry.get_text().strip()
         archive_path = self.archive_file_entry.get_text().strip()

         # --- Input Validation ---
         if not source_dir: raise ValueError("Вкажіть директорію для архівування.")
         if not os.path.isdir(source_dir): raise ValueError(f"Директорія не знайдена: {source_dir}")
         if not archive_path: raise ValueError("Вкажіть шлях для файлу архіву.")

         # Ensure archive destination directory exists
         arc_dir = os.path.dirname(archive_path)
         if arc_dir:
             try: os.makedirs(arc_dir, exist_ok=True)
             except OSError as e: raise ValueError(f"Не вдалося створити директорію для архіву '{arc_dir}': {e}")

         # Prevent archiving a directory into itself (critical error)
         try:
             abs_source_dir = os.path.abspath(source_dir)
             abs_archive_path = os.path.abspath(archive_path)
             # Check if archive path starts with source path + separator
             if abs_archive_path != abs_source_dir and abs_archive_path.startswith(abs_source_dir + os.sep):
                 # This is an error condition, raise ValueError to stop execution
                 raise ValueError("Не можна зберігати архів всередині директорії, що архівується.")
         except ValueError as ve:
             self.show_warning_dialog(str(ve)) # Show the specific error
             return # Stop execution
         except Exception as path_e:
             print(f"Warning checking archive path within source path: {path_e}")

         # --- Start Archiving Task ---
         self._start_task(archive_directory_threaded, args=(source_dir, archive_path), kwargs={})


class UploadPage(BasePage):
    """Page for uploading files to a simple TCP server."""
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        # Initialize UI elements
        self.host_entry = None
        self.port_entry = None
        self.file_entry = None
        self.execute_button = None
        # Get default server settings from the main AppWindow instance
        self.default_host = app_window.host
        self.default_port = app_window.port

    def build_ui(self):
        """Builds the file upload page UI."""
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        # Title
        self.page_widget.pack_start(Gtk.Label(label="<b><big>Завантаження на Сервер</big></b>", use_markup=True), False, False, 0)

        # Input Grid
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self.page_widget.pack_start(grid, False, False, 0)

        # Host Entry
        grid.attach(Gtk.Label(label="Хост сервера:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.host_entry = Gtk.Entry(text=self.default_host, hexpand=True) # Use default host
        grid.attach(self.host_entry, 1, 0, 3, 1)

        # Port Entry
        grid.attach(Gtk.Label(label="Порт сервера:", halign=Gtk.Align.END), 0, 1, 1, 1)
        self.port_entry = Gtk.Entry(text=str(self.default_port), hexpand=True) # Use default port
        grid.attach(self.port_entry, 1, 1, 3, 1)

        # File Entry
        grid.attach(Gtk.Label(label="Файл для завантаження:", halign=Gtk.Align.END), 0, 2, 1, 1)
        self.file_entry = Gtk.Entry(hexpand=True, placeholder_text="Оберіть файл для надсилання")
        grid.attach(self.file_entry, 1, 2, 2, 1)
        btn_file = Gtk.Button(label="...")
        btn_file.connect("clicked", lambda w: self._select_file_dialog(self.file_entry, "Оберіть файл"))
        grid.attach(btn_file, 3, 2, 1, 1)

        # Execute Button
        self.execute_button = Gtk.Button(label="Завантажити")
        self.execute_button.connect("clicked", self._on_execute_clicked)
        self.page_widget.pack_start(self.execute_button, False, False, 5) # Add padding

        self.page_widget.show_all()
        return self.page_widget

    def _on_execute_clicked(self, widget):
        """Starts the file upload task when the button is clicked."""
        if self.app._is_task_running:
            self.show_warning_dialog("Завдання вже виконується.")
            return
        try:
            # Ensure widgets exist
            if not all([hasattr(self, w) and getattr(self, w) for w in ['host_entry', 'port_entry', 'file_entry']]):
                 raise RuntimeError("Внутрішня помилка: Віджети Upload не ініціалізовані.")

            # Get values from UI
            host = self.host_entry.get_text().strip()
            port_str = self.port_entry.get_text().strip()
            file_path = self.file_entry.get_text().strip()

            # --- Input Validation ---
            if not host: raise ValueError("Вкажіть хост сервера.")
            if not port_str: raise ValueError("Вкажіть порт сервера.")
            # Validate port number
            try:
                port = int(port_str)
                if not (1 <= port <= 65535): # Standard port range
                    raise ValueError("Порт має бути числом від 1 до 65535.")
            except ValueError: # Catches non-integer input and range errors
                raise ValueError(f"Некоректний порт: '{port_str}'. Введіть число від 1 до 65535.")

            if not file_path: raise ValueError("Оберіть файл для завантаження.")
            if not os.path.isfile(file_path): raise ValueError(f"Файл не знайдено: {file_path}")

            # --- Start Upload Task ---
            self._start_task(upload_file_to_server, args=(host, port, file_path), kwargs={})
        except (ValueError, RuntimeError, FileNotFoundError) as e:
            self.show_warning_dialog(str(e))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.show_warning_dialog(f"Неочікувана помилка Upload: {e}")


class AboutPage(BasePage):
    """Displays information about the application."""
    def build_ui(self):
        """Builds the About page UI."""
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        # Title
        self.page_widget.pack_start(Gtk.Label(label="<b><big>Про програму</big></b>", use_markup=True), False, False, 0)

        # About Text
        about_text = """<b>DownYS</b> - багатофункціональна програма для роботи з контентом.

<b>Можливості:</b>
 • Завантаження відео з YouTube (yt-dlp) з вибором формату та субтитрів
 • Конвертація відео/аудіо (FFmpeg)
 • Віддзеркалення веб-сайтів (HTTrack)
 • Архівування директорій (tar.gz)
 • Завантаження файлів на простий TCP сервер
 • Збереження URL у закладках (з можливістю вибору файлу)

<b>Вимоги:</b> Python 3.x, PyGObject (GTK 3), yt-dlp, FFmpeg, HTTrack

<i>Переконайтеся, що FFmpeg та HTTrack встановлені та доступні у системному PATH для коректної роботи відповідних функцій.</i>"""
        # Create a label with markup, justification, and wrapping
        label = Gtk.Label(label=about_text,
                          use_markup=True,
                          justify=Gtk.Justification.LEFT,
                          wrap=True,
                          wrap_mode=Pango.WrapMode.WORD_CHAR,
                          xalign=0.0) # Align text to the left
        label.set_selectable(True) # Allow user to select and copy text
        self.page_widget.pack_start(label, False, False, 5) # Add padding

        self.page_widget.show_all()
        return self.page_widget

# --- Main Application Window ---

class AppWindow(Gtk.Window):
    """The main application window."""
    def __init__(self):
        Gtk.Window.__init__(self, title="DownYS", default_width=800, default_height=600)
        self.connect("destroy", Gtk.main_quit) # Quit application when window is closed

        # Default server settings (can be overridden in UploadPage UI)
        self.host = "127.0.0.1"
        self.port = 12345

        # Task management state
        self._is_task_running = False
        self._current_task_thread = None

        # Utilities
        self.url_handler = URLHandler()

        # --- Main Window Structure ---
        # Header Bar
        header_bar = Gtk.HeaderBar(title="DownYS", show_close_button=True)
        self.set_titlebar(header_bar)

        # Main Vertical Box (holds content + status bar)
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0) # No spacing here
        self.add(main_vbox)

        # Content Area (Sidebar + Stack) - Horizontal Box
        content_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        main_vbox.pack_start(content_hbox, True, True, 0) # Content area expands

        # --- CORRECTED ORDER: Sidebar first, then Stack ---
        # Stack for Pages (create before sidebar as sidebar needs it)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        # Sidebar connected to the Stack
        self.stack_sidebar = Gtk.StackSidebar(stack=self.stack)
        # Add sidebar to the left, fixed width
        content_hbox.pack_start(self.stack_sidebar, False, False, 0) # <<< SIDEBAR ADDED FIRST

        # Add stack to the right, it expands to fill remaining space
        content_hbox.pack_start(self.stack, True, True, 0)          # <<< STACK ADDED SECOND


        # --- Initialize and Add Pages ---
        self.pages = {} # Dictionary to hold page instances {name: instance}
        page_definitions = [
            ("bookmarks", "Закладки", BookmarksPage),
            ("youtube", "YouTube", YouTubePage),
            ("ffmpeg", "FFmpeg", FFmpegPage),
            ("httrack", "HTTrack/Архів", HTTrackPage),
            ("upload", "Завантаження", UploadPage),
            ("about", "Про програму", AboutPage),
        ]

        for name, title, page_class in page_definitions:
             try:
                 page_instance = page_class(self, self.url_handler) # Create instance
                 page_widget = page_instance.build_ui() # Build its UI

                 if page_widget is None or not isinstance(page_widget, Gtk.Widget):
                     print(f"ПОМИЛКА: build_ui для сторінки '{name}' не повернув валідний віджет!")
                     page_widget = Gtk.Label(label=f"Помилка завантаження сторінки '{title}'")
                     page_widget.show() # Show the error label

                 # Add the page widget to the stack with a name and title
                 self.stack.add_titled(page_widget, name + "_page", title)
                 self.pages[name] = page_instance # Store the instance

             except Exception as build_e:
                 print(f"ПОМИЛКА при створенні сторінки '{name}': {build_e}")
                 import traceback
                 traceback.print_exc()
                 # Add an error placeholder page
                 error_widget = Gtk.Label(label=f"Помилка завантаження сторінки '{title}'\nДив. консоль.")
                 error_widget.show()
                 self.stack.add_titled(error_widget, name + "_page", f"{title} (Помилка)")
                 self.pages[name] = None # Mark page as failed


        # --- Status Bar Area ---
        status_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, border_width=5)
        # Use pack_end to place it at the bottom
        main_vbox.pack_end(status_hbox, False, False, 0)

        # --- MODIFIED STATUS LABEL (Simplified) ---
        # Status Label (simplified to avoid potential layout issues during init)
        self.status_label = Gtk.Label(label="Готово.",
                                      halign=Gtk.Align.START) # Keep left alignment
        status_hbox.pack_start(self.status_label, True, True, 0) # Make it expand

        # Progress Bar (fixed size)
        self.progress_bar = Gtk.ProgressBar(show_text=True, text="")
        status_hbox.pack_end(self.progress_bar, False, False, 0)

        # Show the main window and all its contents
        self.show_all()

        # Initially hide progress bar until a task starts
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text("")

    def go_to_page_with_url(self, page_name, url):
        """Switches to the specified page and populates the URL field if possible."""
        page_widget_name = page_name + "_page" # Construct stack child name
        target_page_widget = self.stack.get_child_by_name(page_widget_name)

        if target_page_widget:
            # Switch the visible page in the stack
            self.stack.set_visible_child(target_page_widget)

            # Find the corresponding page instance
            page_instance = self.pages.get(page_name)
            if page_instance:
                url_entry = None
                # Try to find a common URL entry widget name
                # Add other potential names if different pages use different conventions
                possible_url_fields = ['url_entry']
                for field_name in possible_url_fields:
                    if hasattr(page_instance, field_name) and isinstance(getattr(page_instance, field_name, None), Gtk.Entry):
                        url_entry = getattr(page_instance, field_name)
                        break # Found one

                # If a suitable entry widget was found, set its text
                if url_entry:
                     url_entry.set_text(url)
                     print(f"Перейшли на '{page_name}' та встановили URL: {url}")
                else:
                    print(f"Попередження: Не знайдено відповідне поле ('url_entry', etc.) на сторінці '{page_name}' для встановлення URL.")
            else:
                print(f"Помилка: Не знайдено екземпляр сторінки '{page_name}' (можливо, помилка ініціалізації).")
        else:
            print(f"Помилка: Не знайдено сторінку в стеку з іменем '{page_widget_name}'.")

    def _start_task(self, task_func, args=(), kwargs=None):
        """Wrapper to run a task function in a separate thread with UI updates."""
        if self._is_task_running:
            self.show_warning_dialog("Завдання вже виконується.")
            return

        self._is_task_running = True
        # --- Update UI for task start (using GLib.idle_add for thread safety) ---
        GLib.idle_add(self._set_controls_sensitive, False) # Disable execute button
        GLib.idle_add(self._update_progress, 0.0)        # Reset progress bar
        GLib.idle_add(self._update_status, "Запуск завдання...") # Set initial status

        if kwargs is None: kwargs = {}
        original_kwargs = kwargs.copy() # Keep original kwargs for post-task logic (e.g., httrack chaining)

        # --- Prepare arguments for the task function call ---
        # Add callbacks required by the task functions (status and optionally progress)
        call_kwargs = {'status_callback': self._update_status}

        # Add progress callback only if the task function is known to support it
        # Check function identity directly
        if task_func in [download_youtube_media, run_ffmpeg_task, upload_file_to_server]:
             # Use the correct keyword argument name expected by the specific task function
             # Check if the callback isn't already provided in kwargs to avoid overriding
             if task_func == upload_file_to_server and 'update_progress_callback' not in kwargs:
                 call_kwargs['update_progress_callback'] = self._update_progress
             elif task_func != upload_file_to_server and 'progress_callback' not in kwargs:
                 call_kwargs['progress_callback'] = self._update_progress
        # else: Tasks like httrack, archive, extract_info might not provide granular progress

        # --- Add original kwargs provided by the caller ---
        # Avoid overwriting the callbacks we just added.
        # Also skip specific kwargs used only for post-task logic (HTTrack chaining).
        for key, value in original_kwargs.items():
            if key not in ['status_callback', 'progress_callback', 'update_progress_callback']:
                 # Handle HTTrack chaining kwargs: they are used *after* the task, not passed *to* it.
                 if task_func == run_httrack_web_threaded and key in ['archive_after_mirror', 'post_mirror_archive_path', 'mirror_output_dir', 'site_url']:
                     pass # Don't pass these to run_httrack_web_threaded itself
                 else:
                     # Pass all other original keyword arguments to the task function
                     call_kwargs[key] = value

        # --- Define the thread target function ---
        def wrapper():
            """The function executed in the background thread."""
            try:
                # Execute the main task function with prepared arguments
                task_func(*args, **call_kwargs)
                final_message = "Завдання успішно завершено." # Default success message

                # --- Handle Post-Task Chaining (HTTrack -> Archive) ---
                # Check if the completed task was HTTrack AND archiving was requested
                if task_func == run_httrack_web_threaded and original_kwargs.get('archive_after_mirror'):
                     # Retrieve necessary info from the original kwargs
                     mirror_dir = original_kwargs.get('mirror_output_dir')
                     archive_path = original_kwargs.get('post_mirror_archive_path')
                     site_url = original_kwargs.get('site_url') # For context

                     # Validate if chaining is possible
                     if mirror_dir and archive_path:
                         # Check if mirror directory actually exists after HTTrack ran
                         if not os.path.isdir(mirror_dir):
                              # If directory is missing, raise an error to be caught below
                              raise RuntimeError(f"Помилка архівації: директорія HTTrack '{mirror_dir}' не знайдена після віддзеркалення.")

                         # Update status before starting the archive task
                         GLib.idle_add(self._update_status, "HTTrack завершено. Запуск архівації...")

                         # Execute the archive task (also needs status callback)
                         archive_directory_threaded(directory_to_archive=mirror_dir,
                                                   archive_path=archive_path,
                                                   status_callback=self._update_status, # Pass callback
                                                   site_url=site_url) # Pass context if needed by archiver
                         final_message = "HTTrack та архівування успішно завершено." # Update final message
                     else:
                         # This indicates a setup error before the task started
                         print("Warning: Не вистачає аргументів ('mirror_output_dir' or 'post_mirror_archive_path') для архівування після HTTrack.")
                         final_message = "HTTrack завершено, але архівування не виконано через помилку параметрів."

                # --- Signal Completion (via main thread) ---
                GLib.idle_add(self._on_task_complete, final_message)

            except Exception as e:
                 # --- Handle Errors (from task or chaining logic) ---
                 import traceback
                 traceback.print_exc() # Log full traceback to console
                 # Signal error via the main thread
                 GLib.idle_add(self._on_task_error, str(e)) # Pass error message

        # --- Start the Background Thread ---
        self._current_task_thread = threading.Thread(target=wrapper, daemon=True) # Daemon allows app exit even if thread hangs
        self._current_task_thread.start()

    def _on_task_complete(self, final_message="Завдання завершено."):
        """Callback executed in the main thread when the task finishes successfully."""
        self._is_task_running = False
        # --- Update UI for task completion ---
        GLib.idle_add(self._set_controls_sensitive, True) # Re-enable button
        GLib.idle_add(self._update_progress, 1.0)        # Ensure progress shows 100%
        GLib.idle_add(self._update_status, final_message) # Show final message
        self._current_task_thread = None # Clear thread reference

    def _on_task_error(self, error_message):
        """Callback executed in the main thread when the task fails."""
        self._is_task_running = False
        # --- Update UI for task error ---
        GLib.idle_add(self._set_controls_sensitive, True) # Re-enable button
        # Reset progress bar on error
        GLib.idle_add(self._update_progress, 0.0)
        # Show error message in status bar
        status_msg = f"Помилка: {error_message}"
        GLib.idle_add(self._update_status, status_msg)
        # Show a more prominent warning dialog
        GLib.idle_add(self.show_warning_dialog, f"Під час виконання завдання сталася помилка:\n{error_message}")
        self._current_task_thread = None # Clear thread reference

    def _set_controls_sensitive(self, sensitive):
        """Disables/Enables the primary action button of the currently visible page."""
        current_page_key = None # The key used in self.pages ('youtube', 'ffmpeg', etc.)
        visible_child_widget = self.stack.get_visible_child()

        if visible_child_widget:
            # Iterate through our stored pages to find which one matches the visible widget
            for page_key, page_instance in self.pages.items():
                # Ensure the page instance exists and has its widget
                if page_instance is None: continue # Skip pages that failed to initialize

                page_widget = None
                # Prefer using the getter method if available
                if hasattr(page_instance, 'get_page_widget') and callable(page_instance.get_page_widget):
                    try:
                        page_widget = page_instance.get_page_widget()
                    except Exception as getter_e:
                        print(f"Warning: Error calling get_page_widget for {page_key}: {getter_e}")
                # Fallback to direct attribute access
                elif hasattr(page_instance, 'page_widget'):
                     page_widget = page_instance.page_widget

                # Compare the retrieved widget with the visible one
                if page_widget == visible_child_widget:
                    current_page_key = page_key
                    break # Found the matching page key

        # If we found the matching page, update its button sensitivity
        if current_page_key:
            page_instance = self.pages.get(current_page_key)
            if page_instance: # Should exist if key was found
                 # Find the primary action button using common names
                 button = getattr(page_instance, 'execute_button', None) or \
                          getattr(page_instance, 'download_button', None)

                 # Check if the button exists and has the set_sensitive method
                 if button and hasattr(button, 'set_sensitive'):
                      try:
                          # Set the sensitivity
                          button.set_sensitive(sensitive)
                      except Exception as e:
                          # Log error if setting sensitivity fails
                          print(f"Warning: Could not set sensitivity for button on page {current_page_key}: {e}")
        # else:
            # This might happen briefly during transitions or if mapping fails (e.g., error placeholder)
            # print(f"Warning: Could not map visible widget to a known page key in _set_controls_sensitive.")

        # Keep sidebar navigable regardless of task status
        # self.stack_sidebar.set_sensitive(True) # Usually not needed, sidebar manages itself

    def _update_progress(self, fraction):
        """Updates the progress bar in the main thread. Safely handles values."""
        # --- THIS FUNCTION RUNS IN THE MAIN GTK THREAD via GLib.idle_add ---
        try:
            # Ensure fraction is a valid float between 0.0 and 1.0
            fraction = float(fraction)
            fraction = max(0.0, min(1.0, fraction)) # Clamp value
        except (ValueError, TypeError):
            fraction = 0.0 # Default to 0 if conversion fails

        self.progress_bar.set_fraction(fraction)
        # Show percentage text only when progress > 0 or at 100%
        self.progress_bar.set_text(f"{int(fraction*100)}%" if fraction > 0 or fraction == 1.0 else "")
        # --- REMOVED: Manual event loop pumping ---

    def _update_status(self, message):
        """Updates the status label in the main thread."""
        # --- THIS FUNCTION RUNS IN THE MAIN GTK THREAD via GLib.idle_add ---
        try:
            # Ensure message is a string
            message_str = str(message)
        except Exception as e:
            message_str = f"Помилка оновлення статусу: {e}"

        self.status_label.set_text(message_str)
        print(f"STATUS: {message_str}") # Also print to console for logging/debugging
        # --- REMOVED: Manual event loop pumping ---

    def show_warning_dialog(self, message):
        """Displays a modal warning dialog. Ensures it runs on the main GTK thread."""
        # Use GLib.idle_add to ensure dialog creation and running happens in the main thread
        def show_dialog_idle():
            try:
                dialog = Gtk.MessageDialog(transient_for=self, # Set parent window
                                           modal=True,           # Block interaction with parent
                                           destroy_with_parent=True, # Close dialog if parent closes
                                           message_type=Gtk.MessageType.WARNING,
                                           buttons=Gtk.ButtonsType.OK,
                                           text="Попередження") # Dialog title
                dialog.format_secondary_text(str(message)) # Dialog message content
                dialog.run()  # Show and wait for response
                dialog.destroy() # Clean up the dialog
            except Exception as dialog_e:
                 print(f"Error displaying warning dialog: {dialog_e}")
        GLib.idle_add(show_dialog_idle)

    def show_info_dialog(self, title, message):
        """Displays a modal information dialog. Ensures it runs on the main GTK thread."""
        # Use GLib.idle_add for thread safety
        def show_dialog_idle():
            try:
                dialog = Gtk.MessageDialog(transient_for=self,
                                           modal=True,
                                           destroy_with_parent=True,
                                           message_type=Gtk.MessageType.INFO,
                                           buttons=Gtk.ButtonsType.OK,
                                           text=title) # Dialog title
                dialog.format_secondary_text(str(message)) # Dialog message content
                dialog.run()
                dialog.destroy()
            except Exception as dialog_e:
                 print(f"Error displaying info dialog: {dialog_e}")
        GLib.idle_add(show_dialog_idle)

    def _select_file_dialog(self, entry_widget, title, save_mode=False):
        """Opens a file chooser dialog and updates the entry widget."""
        # Basic check for valid widget
        if entry_widget is None or not isinstance(entry_widget, Gtk.Entry):
            print(f"Warning: _select_file_dialog called with invalid widget: {entry_widget}")
            self.show_warning_dialog(f"Внутрішня помилка: Спроба викликати діалог файлу для невідповідного поля вводу (Заголовок: '{title}').")
            return

        # Determine dialog action and button label
        action = Gtk.FileChooserAction.SAVE if save_mode else Gtk.FileChooserAction.OPEN
        button_label = "_Зберегти" if save_mode else "_Відкрити"

        # Create the dialog
        dialog = Gtk.FileChooserDialog(title=title, parent=self, action=action)
        dialog.add_buttons("_Скасувати", Gtk.ResponseType.CANCEL, button_label, Gtk.ResponseType.OK)

        # Enable overwrite confirmation for save dialogs
        if save_mode:
            dialog.set_do_overwrite_confirmation(True)

        # --- Try to set current folder/filename based on entry widget ---
        current_path = entry_widget.get_text().strip()
        # Determine the currently active page for context-specific suggestions
        current_page_key = None
        visible_child_widget = self.stack.get_visible_child()
        if visible_child_widget:
             for page_key, page_instance in self.pages.items():
                if page_instance is None: continue
                page_widget = page_instance.get_page_widget() if hasattr(page_instance, 'get_page_widget') else getattr(page_instance, 'page_widget', None)
                if page_widget == visible_child_widget:
                    current_page_key = page_key
                    break
        page_instance = self.pages.get(current_page_key) if current_page_key else None

        try:
             # If the entry widget has a path:
             if current_path:
                 current_dir = os.path.dirname(current_path)
                 # Set current folder if the directory exists
                 if os.path.isdir(current_dir):
                     dialog.set_current_folder(current_dir)
                 # Or if the path itself is a directory
                 elif os.path.isdir(current_path):
                     dialog.set_current_folder(current_path)
                 else: # Default to home if path or dir doesn't exist
                     dialog.set_current_folder(os.path.expanduser("~"))

                 # Set filename suggestion in save mode or pre-select file in open mode
                 if save_mode and not os.path.isdir(current_path):
                     dialog.set_current_name(os.path.basename(current_path))
                 elif not save_mode and os.path.isfile(current_path):
                     dialog.set_filename(current_path) # Pre-select the file in Open mode

             # If the entry widget is empty:
             else:
                 # Default to the user's home directory
                 dialog.set_current_folder(os.path.expanduser("~"))
                 # --- Suggest filenames in SAVE mode based on context ---
                 if save_mode and page_instance and current_page_key != "bookmarks":
                     suggested_name_set = False
                     # HTTrack Page Context
                     if current_page_key == "httrack":
                         # Check if it's the 'archive file' entry in the Archive section
                         if hasattr(page_instance, 'archive_radio') and page_instance.archive_radio.get_active() and \
                            entry_widget == getattr(page_instance, 'archive_file_entry', None) and \
                            hasattr(page_instance, '_suggest_archive_filename'):
                              dir_entry = getattr(page_instance, 'dir_to_archive_entry', None)
                              src_dir = dir_entry.get_text().strip() if dir_entry else ""
                              page_instance._suggest_archive_filename(src_dir, dialog=dialog) # Pass dialog to method
                              suggested_name_set = True
                         # Check if it's the 'post mirror archive' entry in the Mirror section
                         elif hasattr(page_instance, 'mirror_radio') and page_instance.mirror_radio.get_active() and \
                              hasattr(page_instance, 'archive_after_mirror_check') and page_instance.archive_after_mirror_check.get_active() and \
                              entry_widget == getattr(page_instance, 'post_mirror_archive_entry', None) and \
                              hasattr(page_instance, '_suggest_post_mirror_archive_filename'):
                              url_entry = getattr(page_instance, 'url_entry', None)
                              mirror_dir_entry = getattr(page_instance, 'mirror_output_dir_entry', None)
                              url = url_entry.get_text().strip() if url_entry else ""
                              mirror_dir = mirror_dir_entry.get_text().strip() if mirror_dir_entry else ""
                              page_instance._suggest_post_mirror_archive_filename(mirror_dir, url, dialog=dialog) # Pass dialog
                              suggested_name_set = True
                     # FFmpeg Page Context
                     elif current_page_key == "ffmpeg":
                         # Check if it's the output file entry
                         if entry_widget == getattr(page_instance, 'output_entry', None) and \
                            hasattr(page_instance, 'task_combo'):
                              task_combo = getattr(page_instance, 'task_combo', None)
                              active_text = task_combo.get_active_text() if task_combo else None
                              task_info = FFMPEG_TASKS.get(active_text) if active_text else None
                              if task_info:
                                  ext = task_info.get("output_ext", ".out")
                                  dialog.set_current_name(f"output_converted{ext}") # Suggest name
                                  suggested_name_set = True
                     # Fallback default name if no context-specific suggestion worked
                     # Don't suggest for upload source file selection
                     if not suggested_name_set and current_page_key != 'upload':
                           dialog.set_current_name("output_file")
                 # Default save name if no context at all
                 elif save_mode:
                     dialog.set_current_name("output_file")

        except Exception as e:
            print(f"Warning setting up file dialog: {e}")
            # Ensure a default folder is set if errors occur during setup
            try:
                if not dialog.get_current_folder(): # Check if not already set
                    dialog.set_current_folder(os.path.expanduser("~"))
            except Exception: pass # Ignore error setting fallback folder

        # --- Run the dialog and handle response ---
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            selected_path = dialog.get_filename()
            entry_widget.set_text(selected_path) # Update the entry widget

            # --- Trigger updates on relevant pages after selection (if needed) ---
            # Check if the page instance and key are valid
            if page_instance and current_page_key != "bookmarks":
                 try:
                     # FFmpeg: Update output suggestion if input file changed
                     if current_page_key == "ffmpeg" and \
                        entry_widget == getattr(page_instance, 'input_entry', None) and \
                        hasattr(page_instance, '_update_output_suggestion'):
                          page_instance._update_output_suggestion()
                     # HTTrack: Update filename suggestions if relevant fields changed
                     elif current_page_key == "httrack":
                          # Mirror output dir changed -> update post-mirror suggestion
                          if entry_widget == getattr(page_instance, 'mirror_output_dir_entry', None) and \
                             hasattr(page_instance, '_on_mirror_input_changed'):
                               page_instance._on_mirror_input_changed(entry_widget)
                          # Archive source dir changed -> update archive suggestion
                          elif entry_widget == getattr(page_instance, 'dir_to_archive_entry', None) and \
                               hasattr(page_instance, '_on_archive_input_changed'):
                               page_instance._on_archive_input_changed(entry_widget)
                          # Archive file selected -> re-trigger suggestion based on dir (in case dir was empty before)
                          elif entry_widget == getattr(page_instance, 'archive_file_entry', None) and \
                               hasattr(page_instance, '_on_archive_input_changed'):
                               dir_entry = getattr(page_instance, 'dir_to_archive_entry', None)
                               if dir_entry: page_instance._on_archive_input_changed(dir_entry)
                          # Post-mirror archive file selected -> re-trigger based on url/dir
                          elif entry_widget == getattr(page_instance, 'post_mirror_archive_entry', None) and \
                               hasattr(page_instance, '_on_mirror_input_changed'):
                               mirror_dir_entry = getattr(page_instance, 'mirror_output_dir_entry', None)
                               if mirror_dir_entry: page_instance._on_mirror_input_changed(mirror_dir_entry)
                 except Exception as e:
                     # Log errors during these optional post-selection updates
                     print(f"Warning triggering page update after file dialog selection: {e}")

        # --- Clean up the dialog ---
        dialog.destroy()

    def _select_folder_dialog(self, entry_widget, title):
        """Opens a folder chooser dialog and updates the entry widget."""
        # Basic widget validation
        if entry_widget is None or not isinstance(entry_widget, Gtk.Entry):
            print(f"Warning: _select_folder_dialog called with invalid widget: {entry_widget}")
            self.show_warning_dialog(f"Внутрішня помилка: Спроба викликати діалог папки для невідповідного поля вводу (Заголовок: '{title}').")
            return

        # Create the folder chooser dialog
        dialog = Gtk.FileChooserDialog(title=title, parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons("_Скасувати", Gtk.ResponseType.CANCEL, "_Обрати", Gtk.ResponseType.OK)

        # --- Set current folder based on entry widget or home dir ---
        current_dir = entry_widget.get_text().strip()
        try:
            if current_dir and os.path.isdir(current_dir):
                dialog.set_current_folder(current_dir)
            else:
                dialog.set_current_folder(os.path.expanduser("~"))
        except Exception as e:
            print(f"Warning setting current folder for dialog: {e}")
            # Ensure a fallback folder is set if errors occur
            try:
                if not dialog.get_current_folder():
                    dialog.set_current_folder(os.path.expanduser("~"))
            except Exception: pass

        # --- Run the dialog and handle response ---
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            selected_dir = dialog.get_filename()
            entry_widget.set_text(selected_dir) # Update the entry widget

            # --- Trigger updates on HTTrack page if relevant directory changed ---
            # Determine current page
            current_page_key = None
            visible_child_widget = self.stack.get_visible_child()
            if visible_child_widget:
                 for page_key, page_instance in self.pages.items():
                    if page_instance is None: continue
                    page_widget = page_instance.get_page_widget() if hasattr(page_instance, 'get_page_widget') else getattr(page_instance, 'page_widget', None)
                    if page_widget == visible_child_widget:
                        current_page_key = page_key
                        break

            # If the current page is HTTrack, trigger suggestion updates
            if current_page_key == "httrack":
                 page_instance = self.pages.get("httrack")
                 if page_instance:
                      try:
                          # Mirror output dir changed -> update post-mirror suggestion
                          if entry_widget == getattr(page_instance, 'mirror_output_dir_entry', None) and \
                             hasattr(page_instance, '_on_mirror_input_changed'):
                               page_instance._on_mirror_input_changed(entry_widget)
                          # Archive source dir changed -> update archive filename suggestion
                          elif entry_widget == getattr(page_instance, 'dir_to_archive_entry', None) and \
                               hasattr(page_instance, '_on_archive_input_changed'):
                               page_instance._on_archive_input_changed(entry_widget)
                      except Exception as e:
                          print(f"Warning triggering page update after folder dialog selection: {e}")

        # --- Clean up the dialog ---
        dialog.destroy()

# --- Application Entry Point ---
if __name__ == "__main__":
    # Check for external command-line dependencies before launching the UI
    missing_deps = []
    print("Перевірка залежностей...")
    try:
        # Check for FFmpeg
        print(" - FFmpeg...", end="")
        subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(" OK")
    except (FileNotFoundError, subprocess.CalledProcessError, OSError) as e:
        print(f" НЕ ЗНАЙДЕНО ({e})")
        missing_deps.append("FFmpeg")

    try:
        # Check for HTTrack
        print(" - HTTrack...", end="")
        subprocess.run(['httrack', '--version'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(" OK")
    except (FileNotFoundError, subprocess.CalledProcessError, OSError) as e:
        print(f" НЕ ЗНАЙДЕНО ({e})")
        missing_deps.append("HTTrack")

    try:
        # Check for yt-dlp (preferred)
        print(" - yt-dlp...", end="")
        subprocess.run(['yt-dlp', '--version'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(" OK")
    except (FileNotFoundError, subprocess.CalledProcessError, OSError):
         # Fallback check for youtube-dl if yt-dlp not found
         print(" (yt-dlp не знайдено, перевірка youtube-dl...)")
         try:
             print("   - youtube-dl...", end="")
             subprocess.run(['youtube-dl', '--version'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
             print(" OK (знайдено youtube-dl, але рекомендується yt-dlp)")
         except (FileNotFoundError, subprocess.CalledProcessError, OSError) as e:
             print(f" НЕ ЗНАЙДЕНО ({e})")
             missing_deps.append("yt-dlp (або youtube-dl)")

    # Show warning dialog if any dependencies are missing
    if missing_deps:
         dep_str = ", ".join(missing_deps)
         warning_message = f"Не знайдено необхідні програми: {dep_str}.\n\nБудь ласка, встановіть їх та переконайтеся, що вони доступні у системному PATH.\n\nВідповідні функції програми можуть працювати некоректно або не працювати взагалі."
         # Print warning to console as well
         console_warning_message = warning_message.replace('.', ':', 1).replace('.\n\n', '.\n')
         print(f"\n!!! ПОПЕРЕДЖЕННЯ: {console_warning_message} !!!\n")

         # Show GTK dialog (requires a temporary window parent before main loop starts)
         # This needs to run *before* Gtk.main()
         try:
             win_temp = Gtk.Window() # Create temporary invisible window
             dialog = Gtk.MessageDialog(transient_for=win_temp, # Associate with temp window
                                        modal=True,
                                        message_type=Gtk.MessageType.WARNING,
                                        buttons=Gtk.ButtonsType.OK,
                                        text="Відсутні Залежності")
             dialog.format_secondary_text(warning_message)
             dialog.run()
             dialog.destroy()
             win_temp.destroy() # Clean up temporary window
         except Exception as dialog_e:
             print(f"Помилка показу діалогу попередження GTK: {dialog_e}")
             print("(Продовження запуску програми...)")


    # Create and run the main application window
    print("\nЗапуск DownYS...")
    try:
        app = AppWindow()
        Gtk.main() # Start the GTK main event loop
    except Exception as main_e:
        print(f"\n!!! Критична помилка при запуску або роботі програми: {main_e} !!!")
        import traceback
        traceback.print_exc()

    print("DownYS завершив роботу.")

import gi
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

from scripts.youtube import download_youtube_video_with_progress
from scripts.upload_server import upload_file_to_server
from scripts.httrack_tasks import run_httrack_web_threaded, archive_directory_threaded

FFMPEG_TASKS = {
    "Відео -> MP4 (Просто)": {
        "type": "convert_simple",
        "output_ext": ".mp4",
        "params": []
    },
    "Відео -> AVI": {
        "type": "convert_format",
        "output_ext": ".avi",
        "params": []
    },
    "Відео -> Аудіо (AAC)": {
        "type": "extract_audio_aac",
        "output_ext": ".aac",
        "params": []
    },
    "Відео -> Аудіо (MP3)": {
        "type": "extract_audio_mp3",
        "output_ext": ".mp3",
        "params": []
    },
    "Стиснути Відео (Бітрейт)": {
        "type": "compress_bitrate",
        "output_ext": ".mp4",
        "params": [{"name": "bitrate", "label": "Бітрейт (напр., 1M)", "type": "entry", "default": "1M", "required": True}]
    },
    "Змінити Роздільну здатність": {
        "type": "adjust_resolution",
        "output_ext": ".mp4",
        "params": [
            {"name": "width", "label": "Ширина", "type": "entry", "default": "1280", "required": True},
            {"name": "height", "label": "Висота", "type": "entry", "default": "720", "required": True}
        ]
    },
    # TODO: Додати інші завдання
}

def run_ffmpeg_task(input_path, output_path, task_type=None, task_options=None, progress_callback=None, status_callback=None):
    if status_callback:
        GLib.idle_add(status_callback, f"Запуск FFmpeg завдання '{task_type}'...")

    total_steps = 100
    for i in range(total_steps + 1):
        if status_callback:
            if i == 0:
                GLib.idle_add(status_callback, "Ініціалізація FFmpeg...")
            elif i == total_steps:
                 GLib.idle_add(status_callback, "Завершення FFmpeg...")
            elif i % 20 == 0:
                 GLib.idle_add(status_callback, f"Обробка {int(i/total_steps*100)}%...")

        if progress_callback:
            GLib.idle_add(progress_callback, i / total_steps)

        time.sleep(0.05)

    if status_callback:
        GLib.idle_add(status_callback, "FFmpeg завдання завершено.")


class AppWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="Multi-Tool App")
        self.set_default_size(800, 600)

        self.host = "127.0.0.1"
        self.port = 12345

        header_bar = Gtk.HeaderBar()
        header_bar.set_show_close_button(True)
        header_bar.props.title = "Multi-Tool"
        self.set_titlebar(header_bar)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(box)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(300)

        self.stack_sidebar = Gtk.StackSidebar()
        self.stack_sidebar.set_stack(self.stack)

        hbox_main = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hbox_main.set_homogeneous(False)
        hbox_main.pack_start(self.stack_sidebar, False, False, 0)
        hbox_main.pack_start(self.stack, True, True, 0)
        box.pack_start(hbox_main, True, True, 0)

        self._create_youtube_page()
        self._create_ffmpeg_page()
        self._create_httrack_page()
        self._create_upload_page()
        self._create_about_page()

        status_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.pack_end(status_hbox, False, False, 0)

        self.status_label = Gtk.Label(label="Готово.")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.set_line_wrap(True)
        self.status_label.set_max_width_chars(80)
        self.status_label.set_ellipsize(Pango.EllipsizeMode.END)
        status_hbox.pack_start(self.status_label, True, True, 0)

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text("")
        self.progress_bar.set_show_text(True)
        status_hbox.pack_end(self.progress_bar, False, False, 0)

        self._is_task_running = False
        self._current_task_thread = None

        self.ffmpeg_task_combo = None
        self.ffmpeg_params_box = None
        self.ffmpeg_param_entries = {}
        self.ffmpeg_input_entry = None
        self.ffmpeg_output_entry = None
        self.ffmpeg_execute_button = None

        self.youtube_url_entry = None
        self.youtube_output_dir_entry = None
        self.youtube_download_button = None

        self.httrack_mirror_radio = None
        self.httrack_archive_radio = None
        self.httrack_stack = None # Added Gtk.Stack for HTTrack content
        self.httrack_mirror_vbox = None # VBox to hold mirror fields
        self.httrack_archive_vbox = None # VBox to hold archive fields
        self.httrack_url_entry = None
        self.httrack_mirror_output_dir_entry = None
        self.httrack_archive_after_mirror_check = None
        self.httrack_post_mirror_archive_hbox = None
        self.httrack_post_mirror_archive_entry = None
        self.httrack_dir_to_archive_entry = None
        self.httrack_archive_file_entry = None
        self.httrack_execute_button = None

        self.upload_host_entry = None
        self.upload_port_entry = None
        self.upload_file_entry = None
        self.upload_execute_button = None

        self.connect("destroy", Gtk.main_quit)
        self.show_all()

    def _create_youtube_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_border_width(10)
        page.pack_start(Gtk.Label(label="<b><big>Завантаження YouTube</big></b>", use_markup=True), False, False, 0)

        youtube_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        page.pack_start(youtube_grid, False, False, 0)

        youtube_grid.attach(Gtk.Label(label="URL відео:"), 0, 0, 1, 1)
        self.youtube_url_entry = Gtk.Entry()
        self.youtube_url_entry.set_hexpand(True)
        youtube_grid.attach(self.youtube_url_entry, 1, 0, 3, 1)

        youtube_grid.attach(Gtk.Label(label="Директорія збереження:"), 0, 1, 1, 1)
        self.youtube_output_dir_entry = Gtk.Entry()
        self.youtube_output_dir_entry.set_hexpand(True)
        youtube_grid.attach(self.youtube_output_dir_entry, 1, 1, 2, 1)
        youtube_output_dir_button = Gtk.Button(label="...")
        youtube_output_dir_button.connect("clicked", lambda w: self._select_folder_dialog(self.youtube_output_dir_entry, "Оберіть директорію для збереження"))
        youtube_grid.attach(youtube_output_dir_button, 3, 1, 1, 1)

        self.youtube_download_button = Gtk.Button(label="Завантажити")
        self.youtube_download_button.connect("clicked", self._on_youtube_download_clicked)
        page.pack_start(self.youtube_download_button, False, False, 0)

        self._suggest_youtube_default_output_dir()

        page.show_all()
        self.stack.add_titled(page, "youtube_page", "YouTube")

    def _create_ffmpeg_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_border_width(10)
        page.pack_start(Gtk.Label(label="<b><big>FFmpeg Конвертація</big></b>", use_markup=True), False, False, 0)

        ffmpeg_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        page.pack_start(ffmpeg_grid, False, False, 0)

        ffmpeg_grid.attach(Gtk.Label(label="Завдання FFmpeg:"), 0, 0, 1, 1)
        self.ffmpeg_task_combo = Gtk.ComboBoxText()
        for label in FFMPEG_TASKS.keys():
            self.ffmpeg_task_combo.append_text(label)
        self.ffmpeg_task_combo.set_active(0)
        self.ffmpeg_task_combo.connect("changed", self._on_ffmpeg_task_changed)
        ffmpeg_grid.attach(self.ffmpeg_task_combo, 1, 0, 3, 1)

        self.ffmpeg_params_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        ffmpeg_grid.attach(self.ffmpeg_params_box, 0, 1, 4, 1)

        ffmpeg_grid.attach(Gtk.Label(label="Вхідний файл:"), 0, 2, 1, 1)
        self.ffmpeg_input_entry = Gtk.Entry()
        self.ffmpeg_input_entry.set_hexpand(True)
        self.ffmpeg_input_entry.connect("changed", self._update_ffmpeg_output_suggestion)
        ffmpeg_grid.attach(self.ffmpeg_input_entry, 1, 2, 2, 1)
        ffmpeg_input_button = Gtk.Button(label="...")
        ffmpeg_input_button.connect("clicked", lambda w: self._select_file_dialog(self.ffmpeg_input_entry, "Оберіть вхідний файл"))
        ffmpeg_grid.attach(ffmpeg_input_button, 3, 2, 1, 1)

        ffmpeg_grid.attach(Gtk.Label(label="Вихідний файл:"), 0, 3, 1, 1)
        self.ffmpeg_output_entry = Gtk.Entry()
        self.ffmpeg_output_entry.set_hexpand(True)
        ffmpeg_grid.attach(self.ffmpeg_output_entry, 1, 3, 2, 1)
        ffmpeg_output_button = Gtk.Button(label="...")
        ffmpeg_output_button.connect("clicked", lambda w: self._select_file_dialog(self.ffmpeg_output_entry, "Оберіть вихідний файл", save_mode=True))
        ffmpeg_grid.attach(ffmpeg_output_button, 3, 3, 1, 1)

        self.ffmpeg_execute_button = Gtk.Button(label="Виконати")
        self.ffmpeg_execute_button.connect("clicked", self._on_ffmpeg_execute_clicked)
        page.pack_start(self.ffmpeg_execute_button, False, False, 0)

        page.show_all()
        self._on_ffmpeg_task_changed(self.ffmpeg_task_combo)

        self.stack.add_titled(page, "ffmpeg_page", "FFmpeg")

    # ЗМІНЕНО: Використовуємо Gtk.Stack для вмісту HTTrack сторінки
    def _create_httrack_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_border_width(10)
        page.pack_start(Gtk.Label(label="<b><big>HTTrack та Архівування</big></b>", use_markup=True), False, False, 0)

        httrack_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        page.pack_start(httrack_grid, False, False, 0)

        # Operation Type Selection (Row 0)
        httrack_grid.attach(Gtk.Label(label="Дія:"), 0, 0, 1, 1)
        hbox_operation = Gtk.Box(spacing=10)
        httrack_grid.attach(hbox_operation, 1, 0, 3, 1)

        self.httrack_mirror_radio = Gtk.RadioButton.new_with_label_from_widget(None, "Віддзеркалити / Оновити сайт")
        self.httrack_mirror_radio.set_active(True)
        self.httrack_mirror_radio.connect("toggled", self._on_httrack_operation_toggled)
        hbox_operation.pack_start(self.httrack_mirror_radio, False, False, 0)

        self.httrack_archive_radio = Gtk.RadioButton.new_with_label_from_widget(self.httrack_mirror_radio, "Архівувати директорію")
        self.httrack_archive_radio.connect("toggled", self._on_httrack_operation_toggled)
        hbox_operation.pack_start(self.httrack_archive_radio, False, False, 0)

        # --- Gtk.Stack to hold Mirroring and Archiving interfaces ---
        self.httrack_stack = Gtk.Stack()
        self.httrack_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE) # Smooth transition
        self.httrack_stack.set_transition_duration(200)
        # Attach the stack to the grid, below the radio buttons
        httrack_grid.attach(self.httrack_stack, 0, 1, 4, 1) # Row 1, spans 4 columns, height 1 (stack manages internal height)


        # --- Mirroring Interface (Inside a VBox for packing) ---
        self.httrack_mirror_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.httrack_stack.add_titled(self.httrack_mirror_vbox, "mirror_section", "Mirror") # Add vbox to stack with a name

        # URL Entry
        mirror_url_grid = Gtk.Grid(column_spacing=10, row_spacing=5) # Use a grid inside vbox for label/entry alignment
        self.httrack_mirror_vbox.pack_start(mirror_url_grid, False, False, 0)
        mirror_url_grid.attach(Gtk.Label(label="URL сайту:"), 0, 0, 1, 1)
        self.httrack_url_entry = Gtk.Entry()
        self.httrack_url_entry.set_hexpand(True)
        self.httrack_url_entry.connect("changed", self._on_httrack_url_changed)
        mirror_url_grid.attach(self.httrack_url_entry, 1, 0, 3, 1) # Span 3 columns

        # Output Directory for Mirroring
        mirror_output_grid = Gtk.Grid(column_spacing=10, row_spacing=5) # Use a grid inside vbox for label/entry alignment
        self.httrack_mirror_vbox.pack_start(mirror_output_grid, False, False, 0)
        mirror_output_grid.attach(Gtk.Label(label="Директорія збереження:"), 0, 0, 1, 1)
        self.httrack_mirror_output_dir_entry = Gtk.Entry()
        self.httrack_mirror_output_dir_entry.set_hexpand(True)
        self.httrack_mirror_output_dir_entry.connect("changed", self._on_httrack_mirror_output_dir_changed)
        mirror_output_grid.attach(self.httrack_mirror_output_dir_entry, 1, 0, 2, 1) # Span 2 columns
        mirror_output_dir_button = Gtk.Button(label="...")
        mirror_output_dir_button.connect("clicked", lambda w: self._select_folder_dialog(self.httrack_mirror_output_dir_entry, "Оберіть директорію для збереження"))
        mirror_output_grid.attach(mirror_output_dir_button, 3, 0, 1, 1) # Button in column 3


        # Option: Archive after Mirroring (Directly in mirror_vbox)
        self.httrack_archive_after_mirror_check = Gtk.CheckButton(label="Архівувати результат віддзеркалення")
        self.httrack_archive_after_mirror_check.connect("toggled", self._on_httrack_archive_after_mirror_toggled)
        self.httrack_mirror_vbox.pack_start(self.httrack_archive_after_mirror_check, False, False, 0)

        # Archive File Path for post-mirror archiving (Inside mirror_vbox, controlled by checkbox)
        self.httrack_post_mirror_archive_hbox = Gtk.Box(spacing=10) # Use HBox for internal layout consistency
        self.httrack_mirror_vbox.pack_start(self.httrack_post_mirror_archive_hbox, False, False, 0)
        self.httrack_post_mirror_archive_hbox.set_visible(False) # Initially hidden


        post_mirror_archive_hbox_label = Gtk.Label(label="Файл архіву результату:") # Label inside HBox
        self.httrack_post_mirror_archive_hbox.pack_start(post_mirror_archive_hbox_label, False, False, 0)
        self.httrack_post_mirror_archive_entry = Gtk.Entry()
        self.httrack_post_mirror_archive_entry.set_hexpand(True)
        self.httrack_post_mirror_archive_hbox.pack_start(self.httrack_post_mirror_archive_entry, True, True, 0)
        post_mirror_archive_button = Gtk.Button(label="...")
        post_mirror_archive_button.connect("clicked", lambda w: self._select_file_dialog(self.httrack_post_mirror_archive_entry, "Оберіть файл архіву", save_mode=True))
        self.httrack_post_mirror_archive_hbox.pack_start(post_mirror_archive_button, False, False, 0)


        # --- Archiving Interface (Inside a VBox for packing) ---
        self.httrack_archive_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.httrack_stack.add_titled(self.httrack_archive_vbox, "archive_section", "Archive") # Add vbox to stack


        # Directory to Archive (Inside archive_vbox)
        dir_to_archive_grid = Gtk.Grid(column_spacing=10, row_spacing=5) # Use grid inside vbox
        self.httrack_archive_vbox.pack_start(dir_to_archive_grid, False, False, 0)
        dir_to_archive_grid.attach(Gtk.Label(label="Директорія для архівування:"), 0, 0, 1, 1)
        self.httrack_dir_to_archive_entry = Gtk.Entry()
        self.httrack_dir_to_archive_entry.set_hexpand(True)
        self.httrack_dir_to_archive_entry.connect("changed", self._on_httrack_dir_to_archive_changed)
        dir_to_archive_grid.attach(self.httrack_dir_to_archive_entry, 1, 0, 2, 1) # Span 2 columns
        dir_to_archive_button = Gtk.Button(label="...")
        dir_to_archive_button.connect("clicked", lambda w: self._select_folder_dialog(self.httrack_dir_to_archive_entry, "Оберіть директорію для архівування"))
        dir_to_archive_grid.attach(dir_to_archive_button, 3, 0, 1, 1) # Button in column 3


        # Archive File Path (Inside archive_vbox)
        archive_file_grid = Gtk.Grid(column_spacing=10, row_spacing=5) # Use grid inside vbox
        self.httrack_archive_vbox.pack_start(archive_file_grid, False, False, 0)
        archive_file_grid.attach(Gtk.Label(label="Файл архіву:"), 0, 0, 1, 1)
        self.httrack_archive_file_entry = Gtk.Entry()
        self.httrack_archive_file_entry.set_hexpand(True)
        archive_file_grid.attach(self.httrack_archive_file_entry, 1, 0, 2, 1) # Span 2 columns
        archive_file_button = Gtk.Button(label="...")
        archive_file_button.connect("clicked", lambda w: self._select_file_dialog(self.httrack_archive_file_entry, "Оберіть шлях для файлу архіву", save_mode=True))
        archive_file_grid.attach(archive_file_button, 3, 0, 1, 1) # Button in column 3


        # Execute Button for HTTrack task (Below the grid)
        self.httrack_execute_button = Gtk.Button(label="Виконати HTTrack")
        self.httrack_execute_button.connect("clicked", self._on_httrack_execute_clicked)
        page.pack_start(self.httrack_execute_button, False, False, 0)


        # Default path suggestions and initial state
        self._suggest_httrack_default_paths()
        # Manually set initial visible child of the stack and update button label
        self.httrack_stack.set_visible_child_name("mirror_section")
        if self.httrack_execute_button:
            self.httrack_execute_button.set_label("Виконати HTTrack")


        page.show_all()
        # Initial call to update visibility of post-mirror archive HBox based on checkbox
        self._on_httrack_archive_after_mirror_toggled(self.httrack_archive_after_mirror_check)


        self.stack.add_titled(page, "httrack_page", "HTTrack/Архів")


    def _create_upload_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_border_width(10)
        page.pack_start(Gtk.Label(label="<b><big>Завантаження на Сервер</big></b>", use_markup=True), False, False, 0)

        upload_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        page.pack_start(upload_grid, False, False, 0)

        upload_grid.attach(Gtk.Label(label="Хост сервера:"), 0, 0, 1, 1)
        self.upload_host_entry = Gtk.Entry()
        self.upload_host_entry.set_text(self.host)
        self.upload_host_entry.set_hexpand(True)
        upload_grid.attach(self.upload_host_entry, 1, 0, 3, 1)

        upload_grid.attach(Gtk.Label(label="Порт сервера:"), 0, 1, 1, 1)
        self.upload_port_entry = Gtk.Entry()
        self.upload_port_entry.set_text(str(self.port))
        self.upload_port_entry.set_hexpand(True)
        upload_grid.attach(self.upload_port_entry, 1, 1, 3, 1)

        upload_grid.attach(Gtk.Label(label="Файл для завантаження:"), 0, 2, 1, 1)
        self.upload_file_entry = Gtk.Entry()
        self.upload_file_entry.set_hexpand(True)
        upload_grid.attach(self.upload_file_entry, 1, 2, 2, 1)
        upload_file_button = Gtk.Button(label="...")
        upload_file_button.connect("clicked", lambda w: self._select_file_dialog(self.upload_file_entry, "Оберіть файл для завантаження"))
        upload_grid.attach(upload_file_button, 3, 2, 1, 1)

        self.upload_execute_button = Gtk.Button(label="Завантажити")
        self.upload_execute_button.connect("clicked", self._on_upload_execute_clicked)
        page.pack_start(self.upload_execute_button, False, False, 0)

        page.show_all()
        self.stack.add_titled(page, "upload_page", "Завантаження")

    def _create_about_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_border_width(10)
        page.pack_start(Gtk.Label(label="<b><big>Про програму</big></b>", use_markup=True), False, False, 0)
        page.pack_start(Gtk.Label(label="Це багатофункціональна програма для роботи з контентом."), False, False, 0)
        self.stack.add_titled(page, "about_page", "Про програму")

    def _select_file_dialog(self, entry_widget, title, save_mode=False):
        action = Gtk.FileChooserAction.SAVE if save_mode else Gtk.FileChooserAction.OPEN
        buttons = (
            "_Скасувати", Gtk.ResponseType.CANCEL,
            ("_Зберегти" if save_mode else "_Відкрити"), Gtk.ResponseType.OK
        )
        dialog = Gtk.FileChooserDialog(title, self, action, buttons)

        current_path = entry_widget.get_text().strip()
        if current_path:
            current_dir = os.path.dirname(current_path)
            if os.path.isdir(current_dir):
                 dialog.set_current_folder(current_dir)
            elif os.path.exists(current_dir):
                 dialog.set_current_folder(current_dir)
            elif os.path.isdir(current_path):
                 dialog.set_current_folder(current_path)
            else:
                 dialog.set_current_folder(os.path.expanduser("~"))

            if save_mode and not os.path.isdir(current_path):
                 suggested_name = os.path.basename(current_path)
                 if suggested_name:
                      dialog.set_current_name(suggested_name)

        else:
            dialog.set_current_folder(os.path.expanduser("~"))
            if save_mode:
                 if self.stack.get_visible_child_name() == "ffmpeg_page" and self.ffmpeg_task_combo:
                      selected_task_label = self.ffmpeg_task_combo.get_active_text()
                      task_info = FFMPEG_TASKS.get(selected_task_label)
                      output_ext = task_info.get("output_ext", ".mp4") if task_info else ".mp4"
                      dialog.set_current_name(f"output_converted{output_ext}")
                 elif self.stack.get_visible_child_name() == "httrack_page":
                      if self.httrack_archive_radio and self.httrack_archive_radio.get_active():
                           self._suggest_httrack_archive_filename(self.httrack_dir_to_archive_entry.get_text().strip() if self.httrack_dir_to_archive_entry else "", file_chooser_dialog=dialog)
                      elif self.httrack_mirror_radio and self.httrack_mirror_radio.get_active() and self.httrack_archive_after_mirror_check and self.httrack_archive_after_mirror_check.get_active():
                           mirror_dir = self.httrack_mirror_output_dir_entry.get_text().strip() if self.httrack_mirror_output_dir_entry else ""
                           url_text = self.httrack_url_entry.get_text().strip() if self.httrack_url_entry else ""
                           self._suggest_httrack_post_mirror_archive_filename(mirror_dir, file_chooser_dialog=dialog, url=url_text)
                      else:
                           dialog.set_current_name("archive.tar.gz")
                 else:
                      dialog.set_current_name("output_file")

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            entry_widget.set_text(dialog.get_filename())
            if self.stack.get_visible_child_name() == "ffmpeg_page" and entry_widget == self.ffmpeg_input_entry:
                 self._update_ffmpeg_output_suggestion()
            elif self.stack.get_visible_child_name() == "httrack_page":
                 if entry_widget == self.httrack_dir_to_archive_entry:
                      self._suggest_httrack_archive_filename(entry_widget.get_text().strip())

        dialog.destroy()

    def _select_folder_dialog(self, entry_widget, title):
        dialog = Gtk.FileChooserDialog(
            title, self,
            Gtk.FileChooserAction.SELECT_FOLDER,
            ("_Скасувати", Gtk.ResponseType.CANCEL,
             "_Обрати", Gtk.ResponseType.OK)
        )

        current_dir = entry_widget.get_text().strip()
        if current_dir and os.path.isdir(current_dir):
             dialog.set_current_folder(current_dir)
        else:
             dialog.set_current_folder(os.path.expanduser("~"))

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            selected_dir = dialog.get_filename()
            entry_widget.set_text(selected_dir)
            if self.stack.get_visible_child_name() == "httrack_page":
                 if entry_widget == self.httrack_mirror_output_dir_entry and self.httrack_archive_after_mirror_check and self.httrack_archive_after_mirror_check.get_active():
                      url_text = self.httrack_url_entry.get_text().strip() if self.httrack_url_entry else ""
                      self._suggest_httrack_post_mirror_archive_filename(selected_dir, url=url_text)
                 elif entry_widget == self.httrack_dir_to_archive_entry and self.httrack_archive_file_entry and not self.httrack_archive_file_entry.get_text().strip():
                      self._suggest_httrack_archive_filename(selected_dir)

        dialog.destroy()

    def _suggest_youtube_default_output_dir(self):
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads", "YouTube")
        if self.youtube_output_dir_entry:
            self.youtube_output_dir_entry.set_text(default_dir)

    def _on_youtube_download_clicked(self, widget):
        if self._is_task_running:
            self.show_warning_dialog("Завдання вже виконується. Будь ласка, дочекайтеся його завершення.")
            return

        try:
            url = self.youtube_url_entry.get_text().strip()
            output_dir = self.youtube_output_dir_entry.get_text().strip()

            if not url:
                raise ValueError("Будь ласка, введіть URL відео YouTube.")
            if not output_dir:
                raise ValueError("Будь ласка, оберіть директорію для збереження.")
            if not os.path.isdir(output_dir):
                parent_dir = os.path.dirname(output_dir)
                if parent_dir and parent_dir != '.' and not os.path.isdir(parent_dir):
                     try:
                          os.makedirs(output_dir, exist_ok=True)
                     except OSError as e:
                          raise ValueError(f"Не вдалося створити директорію для збереження: {e}")
                elif not os.path.isdir(output_dir):
                     raise ValueError(f"Директорія для збереження не існує: {output_dir}")

            self._start_task(
                download_youtube_video_with_progress,
                args=(url, output_dir),
            )

        except ValueError as e:
            self.show_warning_dialog(str(e))
        except Exception as e:
             self.show_warning_dialog(f"Неочікувана помилка при зборі параметрів YouTube: {e}")

    def _on_ffmpeg_task_changed(self, combo):
        selected_label = combo.get_active_text()
        if not selected_label:
            return
        task_info = FFMPEG_TASKS.get(selected_label)
        if not task_info:
             return
        for widget in self.ffmpeg_params_box.get_children():
            self.ffmpeg_params_box.remove(widget)
        self.ffmpeg_param_entries = {}
        for param_spec in task_info.get("params", []):
            hbox = Gtk.Box(spacing=5)
            hbox.pack_start(Gtk.Label(label=f"{param_spec['label']}:"), False, False, 0)
            if param_spec["type"] == "entry":
                entry = Gtk.Entry(text=param_spec.get("default", ""))
                entry.set_hexpand(True)
                hbox.pack_start(entry, True, True, 0)
                self.ffmpeg_param_entries[param_spec["name"]] = entry
            self.ffmpeg_params_box.pack_start(hbox, False, False, 0)
        self.ffmpeg_params_box.show_all()
        self._update_ffmpeg_output_suggestion()

    def _update_ffmpeg_output_suggestion(self, *args):
        input_path = self.ffmpeg_input_entry.get_text().strip()
        output_path = self.ffmpeg_output_entry.get_text().strip()
        selected_task_label = self.ffmpeg_task_combo.get_active_text()
        task_info = FFMPEG_TASKS.get(selected_task_label)
        if not task_info:
            return
        output_ext = task_info.get("output_ext", ".mp4")
        if input_path:
            input_dir = os.path.dirname(input_path)
            input_name_base, _ = os.path.splitext(os.path.basename(input_path))
            suggested_name = f"{input_name_base}_converted{output_ext}"
            suggested_path = os.path.join(input_dir, suggested_name)
            current_output_basename = os.path.basename(output_path)
            if not output_path or current_output_basename.startswith(f"{input_name_base}_converted"):
                 self.ffmpeg_output_entry.set_text(suggested_path)
            else:
                 base, old_ext = os.path.splitext(output_path)
                 if old_ext.lower() != output_ext.lower():
                      self.ffmpeg_output_entry.set_text(base + output_ext)
        else:
             default_output_name = f"output_converted{output_ext}"
             if not output_path:
                  self.ffmpeg_output_entry.set_text(os.path.join(os.path.expanduser("~"), default_output_name))

    def _on_ffmpeg_execute_clicked(self, widget):
        if self._is_task_running:
            self.show_warning_dialog("Завдання вже виконується. Будь ласка, дочекайтеся його завершення.")
            return
        try:
            selected_task_label = self.ffmpeg_task_combo.get_active_text()
            task_info = FFMPEG_TASKS.get(selected_label)
            if not selected_task_label or not task_info:
                 raise ValueError("Будь ласка, оберіть завдання FFmpeg.")
            task_type = task_info["type"]
            task_options = {}
            for param_spec in task_info.get("params", []):
                param_name = param_spec["name"]
                if param_name in self.ffmpeg_param_entries:
                    value = self.ffmpeg_param_entries[param_name].get_text().strip()
                    if not value and param_spec.get("required", False):
                         raise ValueError(f"Параметр '{param_spec['label']}' є обов'язковим і не може бути порожнім.")
                    task_options[param_name] = value
            input_path = self.ffmpeg_input_entry.get_text().strip()
            output_path = self.ffmpeg_output_entry.get_text().strip()
            if not input_path:
                 raise ValueError("Будь ласка, оберіть вхідний файл для конвертації.")
            if not os.path.exists(input_path) or not os.path.isfile(input_path):
                 raise ValueError(f"Вхідний шлях не є існуючим файлом: {input_path}")
            if not output_path:
                 raise ValueError("Будь ласка, вкажіть вихідний файл для конвертації.")
            output_parent_dir = os.path.dirname(output_path)
            if output_parent_dir and output_parent_dir != '.' and not os.path.isdir(output_parent_dir):
                 raise ValueError(f"Батьківська директорія для вихідного файлу не існує: {output_parent_dir}")
            try:
                input_abs = os.path.abspath(input_path)
                output_abs = os.path.abspath(output_path)
                if input_abs == output_abs:
                    raise ValueError("Вхідний та вихідний файли не можуть бути однаковими.")
            except Exception as e:
                 pass
            self._start_task(
                run_ffmpeg_task,
                args=(input_path, output_path),
                kwargs={'task_type': task_type, 'task_options': task_options}
            )
        except ValueError as e:
            self.show_warning_dialog(str(e))
        except Exception as e:
             self.show_warning_dialog(f"Неочікувана помилка при зборі параметрів FFmpeg: {e}")

    def _suggest_httrack_default_paths(self):
        default_dir = os.path.join(os.path.expanduser("~"), "httrack_downloads")
        if self.httrack_mirror_output_dir_entry:
            self.httrack_mirror_output_dir_entry.set_text(default_dir)
        if self.httrack_dir_to_archive_entry:
            self.httrack_dir_to_archive_entry.set_text(default_dir)
        if self.httrack_post_mirror_archive_entry and not self.httrack_post_mirror_archive_entry.get_text().strip():
             self._suggest_httrack_post_mirror_archive_filename(default_dir, url=self.httrack_url_entry.get_text().strip() if self.httrack_url_entry else "")
        if self.httrack_archive_file_entry and not self.httrack_archive_file_entry.get_text().strip():
             self._suggest_httrack_archive_filename(default_dir)

    # ЗМІНЕНО: Використовуємо httrack_stack.set_visible_child_name для перемикання розділів
    def _on_httrack_operation_toggled(self, radio_button):
        if radio_button.get_active():
            operation_type = "mirror" if radio_button == self.httrack_mirror_radio else "archive"

            if self.httrack_stack: # Ensure stack exists
                if operation_type == "mirror":
                    self.httrack_stack.set_visible_child_name("mirror_section")
                    # Explicitly update visibility of post-mirror archive HBox based on checkbox state
                    if self.httrack_archive_after_mirror_check:
                        self._on_httrack_archive_after_mirror_toggled(self.httrack_archive_after_mirror_check)
                else: # operation_type == "archive"
                    self.httrack_stack.set_visible_child_name("archive_section")
                    # Ensure post-mirror archive HBox is hidden when switching to archive mode
                    if self.httrack_post_mirror_archive_hbox:
                        self.httrack_post_mirror_archive_hbox.set_visible(False)


            # Update execute button label
            if self.httrack_execute_button:
                 self.httrack_execute_button.set_label("Архівувати" if operation_type == "archive" else "Виконати HTTrack")


    def _on_httrack_archive_after_mirror_toggled(self, check_button):
        if self.httrack_post_mirror_archive_hbox:
            self.httrack_post_mirror_archive_hbox.set_visible(check_button.get_active())
        if check_button.get_active() and self.httrack_post_mirror_archive_entry and not self.httrack_post_mirror_archive_entry.get_text().strip():
             mirror_dir = self.httrack_mirror_output_dir_entry.get_text().strip() if self.httrack_mirror_output_dir_entry else ""
             url_text = self.httrack_url_entry.get_text().strip() if self.httrack_url_entry else ""
             self._suggest_httrack_post_mirror_archive_filename(mirror_dir, url=url_text)

    def _on_httrack_url_changed(self, entry):
        if self.httrack_mirror_radio.get_active() and self.httrack_archive_after_mirror_check.get_active():
             mirror_dir = self.httrack_mirror_output_dir_entry.get_text().strip() if self.httrack_mirror_output_dir_entry else ""
             self._suggest_httrack_post_mirror_archive_filename(mirror_dir, url=entry.get_text().strip())

    def _on_httrack_mirror_output_dir_changed(self, entry):
        if self.httrack_archive_after_mirror_check.get_active():
             url_text = self.httrack_url_entry.get_text().strip() if self.httrack_url_entry else ""
             self._suggest_httrack_post_mirror_archive_filename(entry.get_text().strip(), url=url_text)

    def _on_httrack_dir_to_archive_changed(self, entry):
         self._suggest_httrack_archive_filename(entry.get_text().strip())

    def _suggest_httrack_archive_filename(self, directory_to_archive, file_chooser_dialog=None, default_ext=".tar.gz"):
        if not directory_to_archive:
             if file_chooser_dialog:
                  file_chooser_dialog.set_current_name("archive.tar.gz")
             elif self.httrack_archive_file_entry and not self.httrack_archive_file_entry.get_text().strip():
                  self.httrack_archive_file_entry.set_text(os.path.join(os.path.expanduser("~"), "archive.tar.gz"))
             return

        base_name = os.path.basename(directory_to_archive)
        if not base_name: base_name = "archive"
        clean_base_name = re.sub(r'[^\w.-]', '_', base_name)
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d")
        suggested_name = f"{timestamp}_{clean_base_name}{default_ext}"

        if file_chooser_dialog:
            file_chooser_dialog.set_current_name(suggested_name)
        elif self.httrack_archive_file_entry:
            current_archive_entry_text = self.httrack_archive_file_entry.get_text().strip()
            current_dir = os.path.dirname(current_archive_entry_text) or "."
            source_dir_parent = os.path.dirname(directory_to_archive) or "."
            if not current_archive_entry_text or os.path.abspath(current_dir) == os.path.abspath(source_dir_parent):
                 suggested_path = os.path.join(source_dir_parent, suggested_name)
                 self.httrack_archive_file_entry.set_text(suggested_path)

    def _suggest_httrack_post_mirror_archive_filename(self, mirror_output_dir, file_chooser_dialog=None, default_ext=".tar.gz", url=None):
        hostname = None
        if url:
            try:
                parsed_url = urlparse(url)
                if parsed_url.hostname:
                    hostname = parsed_url.hostname
                    if hostname.startswith("www."):
                         hostname = hostname[4:]
                    hostname = re.sub(r'[^\w.-]', '_', hostname)
            except Exception as e:
                pass

        base_name = "website"
        if hostname:
             base_name = hostname
        elif mirror_output_dir:
             dir_base_name = os.path.basename(mirror_output_dir)
             if dir_base_name:
                  base_name = re.sub(r'[^\w.-]', '_', dir_base_name)

        if not base_name: base_name = "archive"
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d")
        suggested_name = f"{timestamp}_{base_name}_archive{default_ext}"

        if file_chooser_dialog:
            file_chooser_dialog.set_current_name(suggested_name)
        elif self.httrack_post_mirror_archive_entry:
             current_entry_text = self.httrack_post_mirror_archive_entry.get_text().strip()
             current_dir = os.path.dirname(current_entry_text) or "."
             mirror_dir_parent = os.path.dirname(mirror_output_dir) or "."
             if not current_entry_text or os.path.abspath(current_dir) == os.path.abspath(mirror_dir_parent):
                  suggested_path = os.path.join(mirror_dir_parent, suggested_name)
                  self.httrack_post_mirror_archive_entry.set_text(suggested_path)

    def _on_httrack_execute_clicked(self, widget):
        if self._is_task_running:
            self.show_warning_dialog("Завдання вже виконується. Будь ласка, дочекайтеся його завершення.")
            return

        try:
            operation_type = "mirror" if self.httrack_mirror_radio.get_active() else "archive"
            params = { "operation_type": operation_type }

            if operation_type == "mirror":
                params["url"] = self.httrack_url_entry.get_text().strip()
                params["mirror_output_dir"] = self.httrack_mirror_output_dir_entry.get_text().strip()
                params["archive_after_mirror"] = self.httrack_archive_after_mirror_check.get_active()
                params["post_mirror_archive_path"] = self.httrack_post_mirror_archive_entry.get_text().strip() if params["archive_after_mirror"] else None

                if not params["url"]:
                    raise ValueError("Будь ласка, введіть URL сайту для віддзеркалення.")
                if not params["mirror_output_dir"]:
                     raise ValueError("Будь ласка, оберіть директорію для збереження.")
                parent_dir = os.path.dirname(params["mirror_output_dir"])
                if parent_dir and parent_dir != '.' and not os.path.isdir(parent_dir):
                     try:
                          os.makedirs(params["mirror_output_dir"], exist_ok=True)
                     except OSError as e:
                          raise ValueError(f"Не вдалося створити директорію для збереження: {e}")
                elif not os.path.isdir(parent_dir if parent_dir != '.' else '.'):
                     raise ValueError(f"Батьківська директорія для збереження не існує: {parent_dir}")

                if params["archive_after_mirror"]:
                     if not params["post_mirror_archive_path"]:
                          raise ValueError("Будь ласка, вкажіть шлях для файлу архіву результату.")
                     archive_parent_dir = os.path.dirname(params["post_mirror_archive_path"])
                     if archive_parent_dir and archive_parent_dir != '.' and not os.path.isdir(archive_parent_dir):
                          try:
                               os.makedirs(archive_parent_dir, exist_ok=True)
                          except OSError as e:
                               raise ValueError(f"Не вдалося створити батьківську директорію для файлу архіву: {e}")
                     elif not os.path.isdir(archive_parent_dir if archive_parent_dir != '.' else '.'):
                          raise ValueError(f"Батьківська директорія для файлу архіву не існує: {archive_parent_dir}")

                     if params["mirror_output_dir"] and params["post_mirror_archive_path"]:
                          try:
                              mirror_abs = os.path.abspath(params["mirror_output_dir"])
                              archive_abs = os.path.abspath(params["post_mirror_archive_path"])
                              if archive_abs.startswith(mirror_abs + os.sep):
                                  self.show_warning_dialog("Попередження: Файл архіву зберігається всередині директорії віддзеркалення. Це може спричинити проблеми під час архівації.")
                              elif os.path.dirname(archive_abs) == mirror_abs:
                                   self.show_warning_dialog("Попередження: Файл архіву зберігається безпосередньо у директорії віддзеркалення. Це може спричинити проблеми під час архівації.")
                          except Exception as e:
                              pass

                self._start_task(
                    run_httrack_web_threaded,
                    args=(params["url"], params["mirror_output_dir"]),
                    kwargs={'archive_after_mirror': params["archive_after_mirror"],
                            'post_mirror_archive_path': params["post_mirror_archive_path"],
                            'mirror_output_dir': params["mirror_output_dir"],
                            'site_url': params["url"]
                           }
                )

            elif operation_type == "archive":
                params["archive_source_dir"] = self.httrack_dir_to_archive_entry.get_text().strip()
                params["archive_path"] = self.httrack_archive_file_entry.get_text().strip()

                if not params["archive_source_dir"]:
                     raise ValueError("Будь ласка, оберіть директорію для архівування.")
                if not os.path.isdir(params["archive_source_dir"]):
                     raise ValueError(f"Директорія для архівування не існує: {params['archive_source_dir']}")

                if not params["archive_path"]:
                     raise ValueError("Будь ласка, вкажіть шлях для збереження архіву.")
                archive_parent_dir = os.path.dirname(params["archive_path"])
                if archive_parent_dir and archive_parent_dir != '.' and not os.path.isdir(archive_parent_dir):
                     try:
                          os.makedirs(archive_parent_dir, exist_ok=True)
                     except OSError as e:
                          raise ValueError(f"Не вдалося створити батьківську директорію для файлу архіву: {e}")
                elif not os.path.isdir(archive_parent_dir if archive_parent_dir != '.' else '.'):
                     raise ValueError(f"Батьківська директорія для файлу архіву не існує: {archive_parent_dir}")

                self._start_task(
                    archive_directory_threaded,
                    args=(params["archive_source_dir"], params["archive_path"]),
                    kwargs={'site_url': None,
                            'site_subdir_name': None
                           }
                )

        except ValueError as e:
            self.show_warning_dialog(str(e))
        except Exception as e:
             self.show_warning_dialog(f"Неочікувана помилка при зборі параметрів HTTrack/архівування: {e}")

    def _on_upload_execute_clicked(self, widget):
        if self._is_task_running:
            self.show_warning_dialog("Завдання вже виконується. Будь ласка, дочекайтеся його завершення.")
            return

        try:
            host = self.upload_host_entry.get_text().strip()
            port_str = self.upload_port_entry.get_text().strip()
            file_path = self.upload_file_entry.get_text().strip()

            if not host:
                raise ValueError("Будь ласка, вкажіть хост сервера.")
            if not port_str:
                raise ValueError("Будь ласка, вкажіть порт сервера.")
            try:
                port = int(port_str)
                if not (1 <= port <= 65535):
                    raise ValueError("Порт має бути числом від 1 до 65535.")
            except ValueError:
                raise ValueError("Порт має бути числовим значенням.")

            if not file_path:
                raise ValueError("Будь ласка, оберіть файл для завантаження.")
            if not os.path.isfile(file_path):
                raise ValueError(f"Файл для завантаження не існує: {file_path}")

            self._start_task(
                upload_file_to_server,
                args=(file_path,),
                kwargs={'host': host, 'port': port}
            )

        except ValueError as e:
            self.show_warning_dialog(str(e))
        except Exception as e:
             self.show_warning_dialog(f"Неочікувана помилка при зборі параметрів завантаження: {e}")

    def _set_controls_sensitive(self, sensitive):
        if hasattr(self.stack, 'get_children'):
            for page in self.stack.get_children():
                 page_execute_buttons = [
                     self.ffmpeg_execute_button,
                     self.youtube_download_button,
                     self.httrack_execute_button,
                     self.upload_execute_button,
                 ]
                 for btn in page_execute_buttons:
                      if btn is not None:
                           btn.set_sensitive(sensitive)

        if hasattr(self.stack_sidebar, 'get_children'):
            for sidebar_child in self.stack_sidebar.get_children():
                 if isinstance(sidebar_child, Gtk.StackSwitcher):
                      if hasattr(sidebar_child, 'get_children'):
                          for switcher_button in sidebar_child.get_children():
                               if hasattr(switcher_button, 'set_sensitive'):
                                    switcher_button.set_sensitive(sensitive)

    def _update_progress(self, fraction):
        self.progress_bar.set_fraction(fraction)
        self.progress_bar.set_text(f"{int(fraction*100)}%") if fraction > 0 or fraction == 1.0 else self.progress_bar.set_text("")

    def _update_status(self, message):
        self.status_label.set_text(message)

    def _on_task_complete(self):
        self._is_task_running = False
        GLib.idle_add(self._set_controls_sensitive, True)
        GLib.idle_add(self._update_progress, 1.0)
        GLib.idle_add(self._update_status, "Завдання завершено.")

    def _on_task_error(self, error_message):
        self._is_task_running = False
        GLib.idle_add(self._set_controls_sensitive, True)
        GLib.idle_add(self._update_progress, 0.0)
        GLib.idle_add(self._update_status, f"Помилка: {error_message}")
        GLib.idle_add(self.show_warning_dialog, f"Під час виконання завдання сталася помилка:\n{error_message}")

    def _start_task(self, task_func, args=(), kwargs=None):
        if self._is_task_running:
            self.show_warning_dialog("Завдання вже виконується. Будь ласка, дочекайтеся його завершення.")
            return

        self._is_task_running = True
        GLib.idle_add(self._set_controls_sensitive, False)
        GLib.idle_add(self._update_progress, 0.0)
        GLib.idle_add(self._update_status, "Запуск завдання...")

        if kwargs is None:
             kwargs = {}

        task_kwargs = kwargs.copy()
        task_kwargs['status_callback'] = self._update_status
        tasks_with_progress = [download_youtube_video_with_progress, run_ffmpeg_task, upload_file_to_server]
        if task_func in tasks_with_progress:
             if task_func == upload_file_to_server:
                 task_kwargs['update_progress_callback'] = self._update_progress
             else:
                 task_kwargs['progress_callback'] = self._update_progress

        def wrapper():
            try:
                task_func(*args, **task_kwargs)

                if task_func == run_httrack_web_threaded and kwargs.get('archive_after_mirror'):
                     mirror_output_dir = kwargs.get('mirror_output_dir')
                     post_mirror_archive_path = kwargs.get('post_mirror_archive_path')
                     site_url = kwargs.get('site_url')

                     if mirror_output_dir and post_mirror_archive_path:
                         GLib.idle_add(self._update_status, "HTTrack завершено. Запуск архівації результату...")
                         try:
                             archive_directory_threaded(
                                 mirror_output_dir,
                                 post_mirror_archive_path,
                                 status_callback=self._update_status,
                                 site_url=site_url
                             )
                         except Exception as archive_e:
                              GLib.idle_add(self._on_task_error, f"Помилка під час архівації результату HTTrack: {archive_e}")
                              return

                GLib.idle_add(self._on_task_complete)

            except Exception as e:
                import traceback
                traceback.print_exc()
                GLib.idle_add(self._on_task_error, str(e))

        thread = threading.Thread(target=wrapper)
        thread.start()
        self._current_task_thread = thread

    def show_warning_dialog(self, message):
        dialog = Gtk.MessageDialog(
            parent=self,
            modal=True,
            destroy_with_parent=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK,
            text=message
        )
        dialog.run()
        dialog.destroy()

if __name__ == "__main__":
    win = AppWindow()
    Gtk.main()

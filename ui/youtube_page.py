# scripts/ui/youtube_page.py

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango
import os
import sys
import subprocess

from  ui.base_page import BasePage
from scripts.youtube import download_youtube_media

class YouTubePage(BasePage):
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        self.url_entry = None
        self.base_output_dir_entry = None
        self.download_button = None
        self.mode_default_radio = None
        self.mode_music_radio = None
        self.mode_playlist_flat_radio = None
        self.mode_single_flat_radio = None
        self.format_combo = None
        self.audio_format_label = None
        self.audio_format_combo = None
        self.download_subs_check = None
        self.sub_langs_label = None
        self.sub_langs_entry = None
        self.embed_subs_check = None
        self.file_list_store = None
        self.file_tree_view = None

    def build_ui(self):
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        self.page_widget.pack_start(Gtk.Label(label="<b><big>Завантаження YouTube</big></b>", use_markup=True), False, False, 0)
        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        self.page_widget.pack_start(grid, False, False, 0)

        grid.attach(Gtk.Label(label="URL відео/списку:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.url_entry = Gtk.Entry(hexpand=True, placeholder_text="Вставте URL відео або плейлиста YouTube")
        grid.attach(self.url_entry, 1, 0, 3, 1)

        grid.attach(Gtk.Label(label="Головна папка:", halign=Gtk.Align.END), 0, 1, 1, 1)
        self.base_output_dir_entry = Gtk.Entry(hexpand=True)
        self.base_output_dir_entry.connect("changed", self._populate_file_browser) 
        grid.attach(self.base_output_dir_entry, 1, 1, 2, 1)
        btn_out = Gtk.Button(label="...")
        btn_out.connect("clicked", lambda w: self._select_folder_dialog(self.base_output_dir_entry, "Оберіть головну директорію"))
        grid.attach(btn_out, 3, 1, 1, 1)
        
        mode_grid = Gtk.Grid(column_spacing=10, row_spacing=5)
        grid.attach(mode_grid, 0, 2, 4, 1)
        mode_grid.attach(Gtk.Label(label="Режим:", halign=Gtk.Align.END), 0, 0, 1, 1)
        
        self.mode_default_radio = Gtk.RadioButton.new_with_label(None, "Стандартний (за каналами)")
        self.mode_music_radio = Gtk.RadioButton.new_with_label_from_widget(self.mode_default_radio, "Музика (лише аудіо)")
        mode_grid.attach(self.mode_default_radio, 1, 0, 1, 1)
        mode_grid.attach(self.mode_music_radio, 2, 0, 1, 1)

        self.mode_playlist_flat_radio = Gtk.RadioButton.new_with_label_from_widget(self.mode_default_radio, "Масово в одну теку (плейлист)")
        self.mode_single_flat_radio = Gtk.RadioButton.new_with_label_from_widget(self.mode_default_radio, "Одне відео (в одну теку)")
        mode_grid.attach(self.mode_playlist_flat_radio, 1, 1, 1, 1)
        mode_grid.attach(self.mode_single_flat_radio, 2, 1, 1, 1)
        
        for radio in [self.mode_default_radio, self.mode_music_radio, self.mode_playlist_flat_radio, self.mode_single_flat_radio]:
            radio.connect("toggled", self._on_download_mode_changed)
        
        grid.attach(Gtk.Label(label="Формат/Якість:", halign=Gtk.Align.END), 0, 3, 1, 1)
        self.format_combo = Gtk.ComboBoxText()
        formats = {"best": "Найкраще Відео+Аудіо (WebM/MKV)", "best_mp4": "Найкраще Відео+Аудіо (MP4)", "audio_best": "Лише аудіо (Найкраще)", "audio_mp3": "Лише аудіо (MP3)", "audio_m4a": "Лише аудіо (M4A/AAC)"}
        for key, value in formats.items(): self.format_combo.append(key, value)
        self.format_combo.set_active_id("best_mp4") 
        self.format_combo.connect("changed", self._on_format_changed)
        grid.attach(self.format_combo, 1, 3, 3, 1)

        grid.attach(Gtk.Label(label="Аудіо кодек:", halign=Gtk.Align.END), 0, 4, 1, 1)
        self.audio_format_combo = Gtk.ComboBoxText()
        audio_formats = ['best', 'mp3', 'aac', 'm4a', 'opus', 'vorbis', 'wav']
        for fmt in audio_formats: self.audio_format_combo.append(fmt, fmt.upper())
        self.audio_format_combo.set_active_id("best")
        grid.attach(self.audio_format_combo, 1, 4, 3, 1)
        
        self.download_subs_check = Gtk.CheckButton(label="Завантажити субтитри")
        self.download_subs_check.connect("toggled", self._on_subs_toggled)
        grid.attach(self.download_subs_check, 0, 5, 2, 1)
        self.sub_langs_label = Gtk.Label(label="Мови суб. (через кому):", halign=Gtk.Align.END)
        self.sub_langs_entry = Gtk.Entry(text="uk,en")
        grid.attach(self.sub_langs_label, 2, 5, 1, 1)
        grid.attach(self.sub_langs_entry, 3, 5, 1, 1)
        self.embed_subs_check = Gtk.CheckButton(label="Вбудувати субтитри (якщо можливо)")
        grid.attach(self.embed_subs_check, 0, 6, 2, 1)
        
        self.download_button = Gtk.Button(label="Завантажити")
        self.download_button.connect("clicked", self._on_download_clicked)
        self.page_widget.pack_start(self.download_button, False, False, 10)
        
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL, margin_top=10, margin_bottom=5)
        self.page_widget.pack_start(sep, False, False, 0)
        browser_label = Gtk.Label(label="<b>Перегляд головної папки:</b>", use_markup=True, xalign=0.0, margin_bottom=5)
        self.page_widget.pack_start(browser_label, False, False, 0)
        self.file_list_store = Gtk.ListStore(str, str, str, str)
        self.file_tree_view = Gtk.TreeView(model=self.file_list_store)
        self.file_tree_view.connect("row-activated", self._on_file_tree_view_row_activated)
        render_text = Gtk.CellRendererText()
        for i, title in enumerate(["Ім'я файлу/Папки", "Тип", "Розмір"]):
            col = Gtk.TreeViewColumn(title, render_text, text=i); col.set_sort_column_id(i)
            self.file_tree_view.append_column(col)
        scrolled_window_files = Gtk.ScrolledWindow(shadow_type=Gtk.ShadowType.IN, hexpand=True, vexpand=True, min_content_height=150)
        scrolled_window_files.add(self.file_tree_view)
        self.page_widget.pack_start(scrolled_window_files, True, True, 0)
        browser_buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin_top=5)
        self.page_widget.pack_start(browser_buttons_box, False, False, 0)
        btn_refresh_files = Gtk.Button(label="Оновити список"); btn_refresh_files.connect("clicked", self._populate_file_browser)
        browser_buttons_box.pack_start(btn_refresh_files, False, False, 0)
        btn_open_selected_file = Gtk.Button(label="Відкрити вибране"); btn_open_selected_file.connect("clicked", self._on_open_selected_file_clicked)
        browser_buttons_box.pack_start(btn_open_selected_file, False, False, 0)
        btn_open_output_dir_fs = Gtk.Button(label="Відкрити головну папку"); btn_open_output_dir_fs.connect("clicked", self._on_open_output_dir_fs_clicked)
        browser_buttons_box.pack_start(btn_open_output_dir_fs, False, False, 0)
        self._suggest_default_output_dir()
        self._update_options_visibility() 
        GLib.idle_add(self._populate_file_browser)
        
        return self.page_widget

    def _on_file_tree_view_row_activated(self, treeview, path, column):
        model, iter_ = treeview.get_model(), treeview.get_model().get_iter(path)
        if iter_:
            file_path = model.get_value(iter_, 3)
            if file_path: self._open_path_externally(file_path)

    def _on_open_selected_file_clicked(self, widget):
        model, iter_ = self.file_tree_view.get_selection().get_selected()
        if iter_:
            file_path = model.get_value(iter_, 3)
            if file_path: self._open_path_externally(file_path)
        else:
            self.show_warning_dialog("Будь ласка, виберіть файл або папку у списку.")

    def _on_open_output_dir_fs_clicked(self, widget):
        dir_path = self.base_output_dir_entry.get_text().strip()
        if dir_path and os.path.isdir(dir_path):
            self._open_path_externally(dir_path)
        else:
            self.show_warning_dialog("Вкажіть головну директорію збереження.")

    def _on_download_mode_changed(self, widget):
        if not widget.get_active(): return
        if not hasattr(self, 'format_combo') or not self.format_combo: return
        is_music_mode = self.mode_music_radio.get_active()
        self.format_combo.set_sensitive(not is_music_mode)
        if is_music_mode:
            self.format_combo.set_active_id("audio_mp3")
        else:
            if self.format_combo.get_active_id().startswith("audio_"):
                 self.format_combo.set_active_id("best_mp4")
        self._update_options_visibility()

    def _on_format_changed(self, combo):
        self._update_options_visibility()
        if (combo.get_active_id() or "").startswith("audio_"):
            self.audio_format_combo.set_active_id(combo.get_active_id().split('_')[-1])

    def _on_subs_toggled(self, check):
        self._update_options_visibility()

    def _suggest_default_output_dir(self):
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads", "YouTube_DownYS")
        if self.base_output_dir_entry and not self.base_output_dir_entry.get_text():
            self.base_output_dir_entry.set_text(default_dir)

    def _update_options_visibility(self):
        if not all([hasattr(self, w) and getattr(self, w) for w in ['format_combo', 'download_subs_check', 'audio_format_label', 'audio_format_combo', 'sub_langs_label', 'sub_langs_entry', 'embed_subs_check']]): return 
        format_id = self.format_combo.get_active_id() or ""
        is_audio = format_id.startswith("audio_")
        subs_active = self.download_subs_check.get_active()
        for w, v in [(self.audio_format_label, is_audio), (self.audio_format_combo, is_audio), (self.sub_langs_label, subs_active), (self.sub_langs_entry, subs_active), (self.embed_subs_check, subs_active and not is_audio)]:
            w.set_visible(v)

    def _populate_file_browser(self, widget=None):
        if not self.file_list_store or not self.base_output_dir_entry: return
        self.file_list_store.clear()
        directory_path = self.base_output_dir_entry.get_text().strip()
        if not directory_path or not os.path.isdir(directory_path):
            self.file_list_store.append([f"'{os.path.basename(directory_path) if directory_path else 'Папка не вказана'}'", "Директорія не знайдена", "", ""])
            return
        try:
            items = sorted(os.listdir(directory_path))
            if not items:
                self.file_list_store.append(["(Папка порожня)", "", "", ""])
            else:
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

    def _on_download_clicked(self, widget):
        if self.app._is_task_running:
            self.show_warning_dialog("Завдання вже виконується.")
            return
        try:
            url = self.url_entry.get_text().strip()
            base_dir = self.base_output_dir_entry.get_text().strip()

            if not url: raise ValueError("URL не може бути порожнім.")
            if not base_dir: raise ValueError("Оберіть головну папку для збереження.")
            
            is_playlist = self.url_handler.is_youtube_playlist(url)
            is_channel = "/@" in url or "/channel/" in url
            
            download_mode = 'default'
            if self.mode_music_radio.get_active():
                download_mode = 'music'
            elif self.mode_playlist_flat_radio.get_active():
                if not is_playlist and not is_channel:
                    self.show_warning_dialog("Режим 'Масово в одну теку' призначений для плейлистів або каналів.")
                    return
                download_mode = 'flat_playlist'
            elif self.mode_single_flat_radio.get_active():
                if is_playlist or is_channel:
                    self.show_warning_dialog("Режим 'Одне відео' не призначений для плейлистів або каналів. Буде завантажено лише відео з URL, а не весь список.")
                download_mode = 'single_flat'
            
            final_output_dir = base_dir
            if download_mode in ['music', 'flat_playlist', 'single_flat']:
                subdir = 'Music' if download_mode == 'music' else 'Videos'
                final_output_dir = os.path.join(base_dir, subdir)
            
            os.makedirs(final_output_dir, exist_ok=True)
            
            self._start_task(
                download_youtube_media,
                args=(url, final_output_dir),
                kwargs={
                    'download_mode': download_mode,
                    'format_selection': self.format_combo.get_active_id() or "best_mp4",
                    'audio_format_override': self.audio_format_combo.get_active_id(),
                    'download_subs': self.download_subs_check.get_active(),
                    'sub_langs': self.sub_langs_entry.get_text().strip(),
                    'embed_subs': self.embed_subs_check.get_active()
                },
                success_callback=self._populate_file_browser
            )

        except (ValueError, RuntimeError, FileNotFoundError) as e: 
            self.show_warning_dialog(str(e))
        except Exception as e: 
            import traceback; traceback.print_exc()
            self.show_warning_dialog(f"Неочікувана помилка: {e}")

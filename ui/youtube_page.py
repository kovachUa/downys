import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango
import os
import sys
import subprocess
import logging

from ui.base_page import BasePage
from scripts.youtube import download_youtube_media, get_youtube_info

_ = lambda s: s
logger = logging.getLogger(__name__)

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
        self.download_subs_check = None
        self.sub_langs_entry = None
        self.embed_subs_check = None
        self.file_list_store = None
        self.file_tree_view = None

        self.video_quality_combo = None
        self.audio_quality_combo = None
        self.playlist_start_spin = None
        self.playlist_end_spin = None
        self.concurrent_fragments_spin = None
        self.skip_downloaded_check = None
        self.time_start_entry = None
        self.time_end_entry = None
        self.clean_filename_check = None
        self.ignore_errors_check = None

    def build_ui(self):
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        self.page_widget.pack_start(Gtk.Label(label=f"<b><big>{_('Завантаження YouTube')}</big></b>", use_markup=True), False, False, 0)
        
        main_grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        self.page_widget.pack_start(main_grid, False, False, 0)

        main_grid.attach(Gtk.Label(label=_("URL відео/списку:"), halign=Gtk.Align.END), 0, 0, 1, 1)
        self.url_entry = Gtk.Entry(hexpand=True, placeholder_text=_("Вставте URL відео або плейлиста YouTube"))
        main_grid.attach(self.url_entry, 1, 0, 3, 1)

        main_grid.attach(Gtk.Label(label=_("Головна папка:"), halign=Gtk.Align.END), 0, 1, 1, 1)
        self.base_output_dir_entry = Gtk.Entry(hexpand=True)
        self.base_output_dir_entry.connect("changed", lambda w: self.app.settings.set('youtube_output_dir', w.get_text().strip())) 
        self.base_output_dir_entry.connect("focus-out-event", self._populate_file_browser)
        main_grid.attach(self.base_output_dir_entry, 1, 1, 2, 1)
        btn_out = Gtk.Button(label="..."); btn_out.connect("clicked", lambda w: self._select_folder_dialog(self.base_output_dir_entry, _("Оберіть головну директорію")))
        main_grid.attach(btn_out, 3, 1, 1, 1)
        
        mode_grid = Gtk.Grid(column_spacing=10, row_spacing=5)
        main_grid.attach(mode_grid, 0, 2, 4, 1)
        mode_grid.attach(Gtk.Label(label=_("Режим:"), halign=Gtk.Align.END), 0, 0, 1, 1)
        
        self.mode_default_radio = Gtk.RadioButton.new_with_label(None, _("Стандартний (за каналами)"))
        self.mode_music_radio = Gtk.RadioButton.new_with_label_from_widget(self.mode_default_radio, _("Музика (лише аудіо)"))
        mode_grid.attach(self.mode_default_radio, 1, 0, 1, 1)
        mode_grid.attach(self.mode_music_radio, 2, 0, 1, 1)

        self.mode_playlist_flat_radio = Gtk.RadioButton.new_with_label_from_widget(self.mode_default_radio, _("Масово в одну теку (плейлист)"))
        self.mode_single_flat_radio = Gtk.RadioButton.new_with_label_from_widget(self.mode_default_radio, _("Одне відео (в одну теку)"))
        mode_grid.attach(self.mode_playlist_flat_radio, 1, 1, 1, 1)
        mode_grid.attach(self.mode_single_flat_radio, 2, 1, 1, 1)
        
        main_grid.attach(Gtk.Label(label=_("Формат відео:"), halign=Gtk.Align.END), 0, 3, 1, 1)
        self.format_combo = Gtk.ComboBoxText()
        formats = {"best": _("Найкраще (WebM/MKV)"), "best_mp4": _("Найкраще (MP4)")}
        for key, value in formats.items(): self.format_combo.append(key, value)
        self.format_combo.set_active_id("best_mp4") 
        main_grid.attach(self.format_combo, 1, 3, 3, 1)

        self._build_advanced_options(main_grid)

        self.download_button = Gtk.Button(label=_("Завантажити"))
        self.download_button.connect("clicked", self._on_download_clicked)
        self.page_widget.pack_start(self.download_button, False, False, 10)
        
        self._build_file_browser()
        
        self._suggest_default_output_dir()
        GLib.idle_add(self._populate_file_browser)
        
        return self.page_widget

    def _build_advanced_options(self, parent_grid):
        adv_grid = Gtk.Grid(column_spacing=10, row_spacing=8, margin_top=10)
        parent_grid.attach(adv_grid, 0, 4, 4, 1)

        adv_grid.attach(Gtk.Label(label=_("Макс. якість відео:"), halign=Gtk.Align.END), 0, 0, 1, 1)
        self.video_quality_combo = Gtk.ComboBoxText()
        qualities = {"best": "Найкраща", "4320": "4320p", "2160": "2160p (4K)", "1440": "1440p (2K)", "1080": "1080p", "720": "720p", "480": "480p"}
        for key, val in qualities.items(): self.video_quality_combo.append(key, val)
        self.video_quality_combo.set_active_id("best")
        adv_grid.attach(self.video_quality_combo, 1, 0, 1, 1)

        adv_grid.attach(Gtk.Label(label=_("Якість аудіо:"), halign=Gtk.Align.END), 2, 0, 1, 1)
        self.audio_quality_combo = Gtk.ComboBoxText()
        audio_qualities = {"0": "Найкраща (0)", "3": "Добра (3)", "5": "Середня (5)", "7": "Нормальна (7)", "9": "Найгірша (9)"}
        for key, val in audio_qualities.items(): self.audio_quality_combo.append(key, val)
        self.audio_quality_combo.set_active_id("5")
        adv_grid.attach(self.audio_quality_combo, 3, 0, 1, 1)

        adv_grid.attach(Gtk.Label(label=_("Діапазон плейлиста:"), halign=Gtk.Align.END), 0, 1, 1, 1)
        playlist_box = Gtk.Box(spacing=5)
        self.playlist_start_spin = Gtk.SpinButton.new_with_range(0, 10000, 1); self.playlist_start_spin.set_value(0)
        self.playlist_end_spin = Gtk.SpinButton.new_with_range(0, 10000, 1); self.playlist_end_spin.set_value(0)
        playlist_box.pack_start(self.playlist_start_spin, True, True, 0)
        playlist_box.pack_start(Gtk.Label(label="–"), False, False, 0)
        playlist_box.pack_start(self.playlist_end_spin, True, True, 0)
        adv_grid.attach(playlist_box, 1, 1, 1, 1)

        adv_grid.attach(Gtk.Label(label=_("Часовий відрізок:"), halign=Gtk.Align.END), 2, 1, 1, 1)
        time_box = Gtk.Box(spacing=5)
        self.time_start_entry = Gtk.Entry(placeholder_text="hh:mm:ss")
        self.time_end_entry = Gtk.Entry(placeholder_text="hh:mm:ss")
        time_box.pack_start(self.time_start_entry, True, True, 0)
        time_box.pack_start(Gtk.Label(label="–"), False, False, 0)
        time_box.pack_start(self.time_end_entry, True, True, 0)
        adv_grid.attach(time_box, 3, 1, 1, 1)

        self.skip_downloaded_check = Gtk.CheckButton(label=_("Пропускати вже завантажені (веде .archive файл)"))
        adv_grid.attach(self.skip_downloaded_check, 0, 2, 2, 1)

        self.clean_filename_check = Gtk.CheckButton(label=_("Спрощені імена файлів (без назви каналу)"))
        adv_grid.attach(self.clean_filename_check, 2, 2, 2, 1)

        adv_grid.attach(Gtk.Label(label=_("Паралельних фрагментів:"), halign=Gtk.Align.END), 0, 3, 1, 1)
        self.concurrent_fragments_spin = Gtk.SpinButton.new_with_range(1, 16, 1)
        self.concurrent_fragments_spin.set_value(4)
        adv_grid.attach(self.concurrent_fragments_spin, 1, 3, 1, 1)
        
        self.ignore_errors_check = Gtk.CheckButton(label=_("Ігнорувати помилки в плейлистах"))
        self.ignore_errors_check.set_active(True)
        adv_grid.attach(self.ignore_errors_check, 2, 3, 2, 1)
        
        subs_box = Gtk.Box(spacing=6, margin_top=5)
        self.download_subs_check = Gtk.CheckButton(label=_("Завантажити субтитри (мови):"))
        self.sub_langs_entry = Gtk.Entry(text="uk,en")
        self.embed_subs_check = Gtk.CheckButton(label=_("Вбудувати субтитри"))
        subs_box.pack_start(self.download_subs_check, False, False, 0)
        subs_box.pack_start(self.sub_langs_entry, True, True, 0)
        subs_box.pack_start(self.embed_subs_check, False, False, 0)
        adv_grid.attach(subs_box, 0, 4, 4, 1)
        
    def _build_file_browser(self):
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL, margin_top=10, margin_bottom=5)
        self.page_widget.pack_start(sep, False, False, 0)
        browser_label = Gtk.Label(label=f"<b>{_('Перегляд головної папки:')}</b>", use_markup=True, xalign=0.0, margin_bottom=5)
        self.page_widget.pack_start(browser_label, False, False, 0)
        self.file_list_store = Gtk.ListStore(str, str, str, str)
        self.file_tree_view = Gtk.TreeView(model=self.file_list_store)
        self.file_tree_view.connect("row-activated", self._on_file_tree_view_row_activated)
        render_text = Gtk.CellRendererText()
        for i, title in enumerate([_("Ім'я файлу/Папки"), _("Тип"), _("Розмір")]):
            col = Gtk.TreeViewColumn(title, render_text, text=i); col.set_sort_column_id(i)
            self.file_tree_view.append_column(col)
        scrolled_window_files = Gtk.ScrolledWindow(shadow_type=Gtk.ShadowType.IN, hexpand=True, vexpand=True, min_content_height=150)
        scrolled_window_files.add(self.file_tree_view)
        self.page_widget.pack_start(scrolled_window_files, True, True, 0)
        browser_buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin_top=5)
        self.page_widget.pack_start(browser_buttons_box, False, False, 0)
        btn_refresh_files = Gtk.Button(label=_("Оновити список")); btn_refresh_files.connect("clicked", self._populate_file_browser)
        browser_buttons_box.pack_start(btn_refresh_files, False, False, 0)
        btn_open_selected_file = Gtk.Button(label=_("Відкрити вибране")); btn_open_selected_file.connect("clicked", self._on_open_selected_file_clicked)
        browser_buttons_box.pack_start(btn_open_selected_file, False, False, 0)
        btn_open_output_dir_fs = Gtk.Button(label=_("Відкрити головну папку")); btn_open_output_dir_fs.connect("clicked", self._on_open_output_dir_fs_clicked)
        browser_buttons_box.pack_start(btn_open_output_dir_fs, False, False, 0)

    def _on_download_clicked(self, widget):
        if self.app.active_tasks:
            self.show_warning_dialog(_("Завдання вже виконується."))
            return
        try:
            url = self.url_entry.get_text().strip()
            base_dir = self.base_output_dir_entry.get_text().strip()

            if not url: raise ValueError(_("URL не може бути порожнім."))
            if not base_dir: raise ValueError(_("Оберіть головну папку для збереження."))
            
            info = get_youtube_info(url)
            if not info: raise RuntimeError(_("Не вдалося отримати інформацію про URL."))
            
            url_type = info.get('_type', 'video')
            is_playlist_like = url_type in ['playlist', 'multi_video']

            download_mode = 'default'
            if self.mode_music_radio.get_active():
                download_mode = 'music'
            elif self.mode_playlist_flat_radio.get_active():
                if not is_playlist_like:
                    self.show_warning_dialog(_("Режим 'Масово в одну теку' призначений для плейлистів або каналів."))
                    return
                download_mode = 'flat_playlist'
            elif self.mode_single_flat_radio.get_active():
                if is_playlist_like:
                    self.show_warning_dialog(_("Режим 'Одне відео' не призначений для плейлистів або каналів."))
                download_mode = 'single_flat'
            
            final_output_dir = base_dir
            if download_mode in ['music', 'flat_playlist', 'single_flat']:
                subdir = 'Music' if download_mode == 'music' else 'Videos'
                final_output_dir = os.path.join(base_dir, subdir)
            
            os.makedirs(final_output_dir, exist_ok=True)
            
            task_kwargs = {
                'url': url,
                'output_dir': final_output_dir,
                'download_mode': download_mode,
                'format_selection': self.format_combo.get_active_id() or "best_mp4",
                'max_resolution': self.video_quality_combo.get_active_id(),
                'audio_quality': int(self.audio_quality_combo.get_active_id() or 5),
                'playlist_start': self.playlist_start_spin.get_value_as_int(),
                'playlist_end': self.playlist_end_spin.get_value_as_int(),
                'concurrent_fragments': self.concurrent_fragments_spin.get_value_as_int(),
                'skip_downloaded': self.skip_downloaded_check.get_active(),
                'time_start': self.time_start_entry.get_text().strip(),
                'time_end': self.time_end_entry.get_text().strip(),
                'clean_filename': self.clean_filename_check.get_active(),
                'ignore_errors': self.ignore_errors_check.get_active(),
                'download_subs': self.download_subs_check.get_active(),
                'sub_langs': self.sub_langs_entry.get_text().strip(),
                'embed_subs': self.embed_subs_check.get_active()
            }
            task_name = f"YouTube: {info.get('title', url)}"

            self.app.start_task(
                download_youtube_media,
                task_name,
                kwargs=task_kwargs,
                success_callback=self._populate_file_browser
            )

        except (ValueError, RuntimeError, FileNotFoundError) as e: 
            self.show_warning_dialog(str(e))
        except Exception as e: 
            self.app.show_detailed_error_dialog(_("Неочікувана помилка"), str(e))
            
    def _suggest_default_output_dir(self):
        saved_path = self.app.settings.get('youtube_output_dir')
        if saved_path and os.path.isdir(saved_path):
            self.base_output_dir_entry.set_text(saved_path)
            return
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads", "YouTube_DownYS")
        self.base_output_dir_entry.set_text(default_dir)
        if not self.app.settings.get('youtube_output_dir'):
            self.app.settings.set('youtube_output_dir', default_dir)

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
            self.show_warning_dialog(_("Будь ласка, виберіть файл або папку у списку."))

    def _on_open_output_dir_fs_clicked(self, widget):
        dir_path = self.base_output_dir_entry.get_text().strip()
        if dir_path and os.path.isdir(dir_path):
            self._open_path_externally(dir_path)
        else:
            self.show_warning_dialog(_("Вкажіть головну директорію збереження."))
            
    def _populate_file_browser(self, widget=None, event=None):
        if not self.file_list_store or not self.base_output_dir_entry: return
        self.file_list_store.clear()
        directory_path = self.base_output_dir_entry.get_text().strip()
        if not directory_path or not os.path.isdir(directory_path):
            base_name = os.path.basename(directory_path) if directory_path else _("Папка не вказана")
            self.file_list_store.append([f"'{base_name}'", _("Директорія не знайдена"), "", ""])
            return
        try:
            items = sorted(os.listdir(directory_path), key=lambda s: s.lower())
            if not items:
                self.file_list_store.append([_("(Папка порожня)"), "", "", ""])
            else:
                for item_name in items:
                    full_path = os.path.join(directory_path, item_name)
                    try:
                        if os.path.isdir(full_path): item_type, size_str = _("Папка"), ""
                        elif os.path.isfile(full_path): item_type, size_str = _("Файл"), self._format_size(os.path.getsize(full_path))
                        else: item_type, size_str = _("Інше"), ""
                        self.file_list_store.append([item_name, item_type, size_str, full_path])
                    except OSError:
                         self.file_list_store.append([item_name, _("Недоступно"), "", full_path])
        except OSError as e:
            self.file_list_store.append([f"{_('Помилка доступу до')} '{os.path.basename(directory_path)}'", str(e), "", directory_path])

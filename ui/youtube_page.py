import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango
import os
import sys
import subprocess
import logging
import threading

from ui.base_page import BasePage
from scripts.youtube import download_youtube_media, get_youtube_info, stop_download

_ = lambda s: s
logger = logging.getLogger(__name__)

class YouTubePage(BasePage):
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        self.url_entry, self.base_output_dir_entry, self.download_button = None, None, None
        self.stop_button = None
        self.info_revealer, self.info_spinner, self.info_grid = None, None, None
        self.info_title_label, self.info_uploader_label, self.info_duration_label = None, None, None
        
        # --- НОВІ ПОЛЯ ДЛЯ ІНФОРМАЦІЇ ---
        self.info_detail_labels = [] # Список для керування видимістю
        self.info_resolution_label, self.info_fps_label, self.info_bitrate_label = None, None, None
        self.info_codecs_label, self.info_size_label = None, None
        # --- КІНЕЦЬ НОВИХ ПОЛІВ ---
        
        self.video_info = None
        self.mode_default_radio, self.mode_music_radio, self.mode_playlist_flat_radio, self.mode_single_flat_radio = None, None, None, None
        self.format_combo, self.download_subs_check, self.sub_langs_entry, self.embed_subs_check = None, None, None, None
        self.file_list_store, self.file_tree_view = None, None
        self.video_quality_combo, self.audio_quality_combo, self.playlist_start_spin, self.playlist_end_spin = None, None, None, None
        self.concurrent_fragments_spin, self.skip_downloaded_check, self.time_start_entry, self.time_end_entry = None, None, None, None
        self.clean_filename_check, self.ignore_errors_check = None, None
        self.avoid_av1_check, self.prefer_h264_check, self.force_mp4_check, self.max_bitrate_spin = None, None, None, None

        self.url_change_timeout = None  # таймер дебаунсу

    def build_ui(self):
        # --- Весь вміст сторінки всередині ScrolledWindow ---
        page_scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        page_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)  # Горизонтальний скрол не потрібен

        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        page_scroller.add(self.page_widget)
        # --- КІНЕЦЬ ЗМІНИ ---

        self.page_widget.pack_start(Gtk.Label(label=f"<b><big>{_('Завантаження YouTube')}</big></b>", use_markup=True), False, False, 0)

        main_grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        self.page_widget.pack_start(main_grid, False, False, 0)

        # Поле URL
        main_grid.attach(Gtk.Label(label=_("URL відео/списку:"), halign=Gtk.Align.END), 0, 0, 1, 1)
        self.url_entry = Gtk.Entry(hexpand=True, placeholder_text=_("Вставте URL і натисніть Enter для аналізу"))
        # Автоматичний аналіз: по Enter, втраті фокуса і при зміні з дебаунсом
        self.url_entry.connect("activate", self._on_url_changed)
        self.url_entry.connect("focus-out-event", self._on_url_changed)
        self.url_entry.connect("changed", self._on_url_text_changed)
        main_grid.attach(self.url_entry, 1, 0, 3, 1)

        # Базова папка
        main_grid.attach(Gtk.Label(label=_("Головна папка:"), halign=Gtk.Align.END), 0, 1, 1, 1)
        self.base_output_dir_entry = Gtk.Entry(hexpand=True)
        self.base_output_dir_entry.connect("changed", lambda w: self.app.settings.set('youtube_output_dir', w.get_text().strip()))
        self.base_output_dir_entry.connect("focus-out-event", self._populate_file_browser)
        main_grid.attach(self.base_output_dir_entry, 1, 1, 2, 1)
        btn_out = Gtk.Button(label="...")
        btn_out.connect("clicked", lambda w: self._select_folder_dialog(self.base_output_dir_entry, _("Оберіть головну директорію")))
        main_grid.attach(btn_out, 3, 1, 1, 1)

        self._build_info_panel(main_grid)

        # Режими
        mode_grid = Gtk.Grid(column_spacing=10, row_spacing=5)
        main_grid.attach(mode_grid, 0, 3, 4, 1)
        mode_grid.attach(Gtk.Label(label=_("Режим:"), halign=Gtk.Align.END), 0, 0, 1, 1)
        self.mode_default_radio = Gtk.RadioButton.new_with_label(None, _("Стандартний (за каналами)"))
        self.mode_music_radio = Gtk.RadioButton.new_with_label_from_widget(self.mode_default_radio, _("Музика (лише аудіо)"))
        mode_grid.attach(self.mode_default_radio, 1, 0, 1, 1)
        mode_grid.attach(self.mode_music_radio, 2, 0, 1, 1)
        self.mode_playlist_flat_radio = Gtk.RadioButton.new_with_label_from_widget(self.mode_default_radio, _("Масово в одну теку (плейлист)"))
        self.mode_single_flat_radio = Gtk.RadioButton.new_with_label_from_widget(self.mode_default_radio, _("Одне відео (в одну теку)"))
        mode_grid.attach(self.mode_playlist_flat_radio, 1, 1, 1, 1)
        mode_grid.attach(self.mode_single_flat_radio, 2, 1, 1, 1)

        # Формат
        main_grid.attach(Gtk.Label(label=_("Базовий формат:"), halign=Gtk.Align.END), 0, 4, 1, 1)
        self.format_combo = Gtk.ComboBoxText()
        formats = {"best": _("Найкраще (WebM/MKV)"), "best_mp4": _("Найкраще сумісне (MP4)")}
        for key, value in formats.items():
            self.format_combo.append(key, value)
        self.format_combo.set_active_id("best_mp4")
        main_grid.attach(self.format_combo, 1, 4, 3, 1)

        self._build_advanced_options(main_grid)

        # Кнопки Завантажити/Стоп
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, margin_top=6)
        self.download_button = Gtk.Button(label=_("Завантажити"))
        self.download_button.connect("clicked", self._on_download_clicked)
        btn_box.pack_start(self.download_button, False, False, 0)

        self.stop_button = Gtk.Button(label=_("Стоп"))
        self.stop_button.connect("clicked", self._on_stop_clicked)
        btn_box.pack_start(self.stop_button, False, False, 0)

        self.page_widget.pack_start(btn_box, False, False, 0)

        self._build_file_browser()
        self._suggest_default_output_dir()
        GLib.idle_add(self._populate_file_browser)

        return page_scroller  # Повертаємо ScrolledWindow замість Gtk.Box

    def _build_advanced_options(self, parent_grid):
        expander = Gtk.Expander(label=_("Додаткові опції"), margin_top=10)
        parent_grid.attach(expander, 0, 5, 4, 1)

        adv_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=5)
        expander.add(adv_vbox)

        quality_frame = Gtk.Frame(label=_("Розширені налаштування якості"))
        adv_vbox.pack_start(quality_frame, False, False, 0)

        quality_grid = Gtk.Grid(column_spacing=10, row_spacing=8, border_width=5)
        quality_frame.add(quality_grid)

        self.avoid_av1_check = Gtk.CheckButton(label=_("Уникати AV1 кодек (рекомендовано)"))
        self.avoid_av1_check.set_active(True)
        self.avoid_av1_check.set_tooltip_text(_("Новий кодек, який може мати проблеми з відтворенням на деяких пристроях"))
        quality_grid.attach(self.avoid_av1_check, 0, 0, 2, 1)

        self.prefer_h264_check = Gtk.CheckButton(label=_("Надавати перевагу H264"))
        self.prefer_h264_check.set_active(True)
        self.prefer_h264_check.set_tooltip_text(_("Найбільш сумісний відеокодек для більшості пристроїв та програм"))
        quality_grid.attach(self.prefer_h264_check, 0, 1, 2, 1)

        self.force_mp4_check = Gtk.CheckButton(label=_("Примусово конвертувати в MP4"))
        self.force_mp4_check.set_active(False)
        self.force_mp4_check.set_tooltip_text(_("Гарантує MP4 контейнер, але може сповільнити завантаження, якщо потрібна конвертація"))
        quality_grid.attach(self.force_mp4_check, 0, 2, 2, 1)

        quality_grid.attach(Gtk.Label(label=_("Макс. бітрейт (кбіт/с):"), halign=Gtk.Align.END), 0, 3, 1, 1)
        self.max_bitrate_spin = Gtk.SpinButton.new_with_range(0, 50000, 500)
        self.max_bitrate_spin.set_value(0)
        self.max_bitrate_spin.set_tooltip_text(_("Обмежує максимальний бітрейт відео. 0 = без обмежень"))
        quality_grid.attach(self.max_bitrate_spin, 1, 3, 1, 1)

        adv_grid = Gtk.Grid(column_spacing=10, row_spacing=8, margin_top=10)
        adv_vbox.pack_start(adv_grid, False, False, 0)

        adv_grid.attach(Gtk.Label(label=_("Макс. роздільна здатність:"), halign=Gtk.Align.END), 0, 0, 1, 1)
        self.video_quality_combo = Gtk.ComboBoxText()
        qualities = {"best": "Найкраща", "4320": "4320p", "2160": "2160p (4K)", "1440": "1440p (2K)", "1080": "1080p", "720": "720p", "480": "480p"}
        for key, val in qualities.items():
            self.video_quality_combo.append(key, val)
        self.video_quality_combo.set_active_id("best")
        adv_grid.attach(self.video_quality_combo, 1, 0, 1, 1)

        adv_grid.attach(Gtk.Label(label=_("Якість аудіо (MP3):"), halign=Gtk.Align.END), 2, 0, 1, 1)
        self.audio_quality_combo = Gtk.ComboBoxText()
        audio_qualities = {"0": "Найкраща (0)", "3": "Добра (3)", "5": "Середня (5)", "7": "Нормальна (7)", "9": "Найгірша (9)"}
        for key, val in audio_qualities.items():
            self.audio_quality_combo.append(key, val)
        self.audio_quality_combo.set_active_id("5")
        adv_grid.attach(self.audio_quality_combo, 3, 0, 1, 1)

        adv_grid.attach(Gtk.Label(label=_("Діапазон плейлиста:"), halign=Gtk.Align.END), 0, 1, 1, 1)
        playlist_box = Gtk.Box(spacing=5)
        self.playlist_start_spin = Gtk.SpinButton.new_with_range(0, 10000, 1)
        self.playlist_end_spin = Gtk.SpinButton.new_with_range(0, 10000, 1)
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

        self.skip_downloaded_check = Gtk.CheckButton(label=_("Пропускати вже завантажені"))
        adv_grid.attach(self.skip_downloaded_check, 0, 2, 2, 1)

        self.clean_filename_check = Gtk.CheckButton(label=_("Спрощені імена файлів"))
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

    def _on_stop_clicked(self, widget):
        # Зупинити активне завдання, якщо є
        if self.app.active_tasks:
            stop_download()
        else:
            self.show_warning_dialog(_("Немає активного завдання для зупинки."))

    def _on_url_text_changed(self, widget):
        # Дебаунс автозапуску аналізу URL
        if self.url_change_timeout:
            GLib.source_remove(self.url_change_timeout)
            self.url_change_timeout = None
        # Запускаємо перевірку через 800 мс після останньої зміни
        self.url_change_timeout = GLib.timeout_add(800, self._trigger_url_fetch)

    def _trigger_url_fetch(self):
        self.url_change_timeout = None
        self._on_url_changed(self.url_entry)
        return False

    def _on_download_clicked(self, widget):
        if self.app.active_tasks:
            self.show_warning_dialog(_("Завдання вже виконується."))
            return
        try:
            url, base_dir = self.url_entry.get_text().strip(), self.base_output_dir_entry.get_text().strip()
            if not url:
                raise ValueError(_("URL не може бути порожнім."))
            if not base_dir:
                raise ValueError(_("Оберіть головну папку для збереження."))
            if not self.video_info:
                self.show_warning_dialog(_("Спочатку проаналізуйте URL, натиснувши Enter у полі вводу."))
                return

            info = self.video_info
            is_playlist_like = info.get('_type', 'video') in ['playlist', 'multi_video']

            download_mode = 'default'
            if self.mode_music_radio.get_active():
                download_mode = 'music'
            elif self.mode_playlist_flat_radio.get_active():
                if not is_playlist_like:
                    self.show_warning_dialog(_("Режим 'Масово в одну теку' призначений для плейлистів."))
                    return
                download_mode = 'flat_playlist'
            elif self.mode_single_flat_radio.get_active():
                if is_playlist_like:
                    self.show_warning_dialog(_("Режим 'Одне відео' не призначений для плейлистів."))
                download_mode = 'single_flat'

            final_output_dir = os.path.join(base_dir, 'Music' if download_mode == 'music' else 'Videos') if download_mode != 'default' else base_dir
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
                'embed_subs': self.embed_subs_check.get_active(),
                'force_mp4': self.force_mp4_check.get_active(),
                'avoid_av1': self.avoid_av1_check.get_active(),
                'prefer_h264': self.prefer_h264_check.get_active(),
                'max_bitrate': self.max_bitrate_spin.get_value_as_int()
            }
            task_name = f"YouTube: {info.get('title', url)}"
            self.app.start_task(download_youtube_media, task_name, kwargs=task_kwargs, success_callback=self._populate_file_browser)
        except (ValueError, RuntimeError) as e:
            self.show_warning_dialog(str(e))
        except Exception as e:
            self.app.show_detailed_error_dialog(_("Неочікувана помилка"), str(e))

    def _build_info_panel(self, parent_grid):
        self.info_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN, transition_duration=250)
        self.info_revealer.set_reveal_child(False)
        parent_grid.attach(self.info_revealer, 0, 2, 4, 1)

        info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, margin_top=10, margin_bottom=5)
        self.info_revealer.add(info_box)

        self.info_spinner = Gtk.Spinner()
        info_box.pack_start(self.info_spinner, False, False, 0)

        frame = Gtk.Frame(label=_("Інформація про відео/плейлист"))
        info_box.pack_start(frame, True, True, 0)

        self.info_grid = Gtk.Grid(column_spacing=10, row_spacing=5, border_width=5)
        frame.add(self.info_grid)

        # --- ОСНОВНА ІНФОРМАЦІЯ ---
        self.info_grid.attach(Gtk.Label(label="<b>Назва:</b>", use_markup=True, xalign=1), 0, 0, 1, 1)
        self.info_title_label = Gtk.Label(label="...", xalign=0, wrap=True, ellipsize=Pango.EllipsizeMode.END)
        self.info_grid.attach(self.info_title_label, 1, 0, 1, 1)

        self.info_grid.attach(Gtk.Label(label="<b>Канал:</b>", use_markup=True, xalign=1), 0, 1, 1, 1)
        self.info_uploader_label = Gtk.Label(label="...", xalign=0)
        self.info_grid.attach(self.info_uploader_label, 1, 1, 1, 1)

        self.info_grid.attach(Gtk.Label(label="<b>Тривалість:</b>", use_markup=True, xalign=1), 0, 2, 1, 1)
        self.info_duration_label = Gtk.Label(label="...", xalign=0)
        self.info_grid.attach(self.info_duration_label, 1, 2, 1, 1)
        
        # --- РОЗДІЛЮВАЧ І ДЕТАЛЬНА ІНФОРМАЦІЯ ---
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL, margin_top=5, margin_bottom=5)
        self.info_grid.attach(separator, 0, 3, 2, 1)

        # Допоміжна функція для додавання рядків з детальною інформацією
        def add_detail_row(grid, row_idx, label_text):
            title_label = Gtk.Label(label=f"<b>{label_text}:</b>", use_markup=True, xalign=1)
            value_label = Gtk.Label(label="...", xalign=0, wrap=True, ellipsize=Pango.EllipsizeMode.END)
            grid.attach(title_label, 0, row_idx, 1, 1)
            grid.attach(value_label, 1, row_idx, 1, 1)
            # Додаємо всі створені віджети до списку для керування видимістю
            self.info_detail_labels.extend([title_label, value_label])
            return value_label

        self.info_resolution_label = add_detail_row(self.info_grid, 4, "Формат")
        self.info_codecs_label = add_detail_row(self.info_grid, 5, "Кодеки")
        self.info_bitrate_label = add_detail_row(self.info_grid, 6, "Бітрейт")
        self.info_size_label = add_detail_row(self.info_grid, 7, "Розмір (орієнт.)")

    def _on_url_changed(self, widget, event=None):
        url = self.url_entry.get_text().strip()
        if not url or (self.video_info and self.video_info.get('webpage_url') == url):
            return
        self.video_info = None
        self.info_revealer.set_reveal_child(True)
        self.info_grid.set_no_show_all(True)
        self.info_grid.hide()
        self.info_spinner.start()
        self.download_button.set_sensitive(False)
        threading.Thread(target=self._fetch_info_thread, args=(url,), daemon=True).start()

    def _fetch_info_thread(self, url):
        try:
            # Запитуємо повну інформацію, не 'flat'
            info = get_youtube_info(url)
        except Exception as e:
            logger.error(f"Info fetch error: {e}")
            info = None
        GLib.idle_add(self._update_info_ui, info)

    def _format_duration(self, seconds):
        if not seconds:
            return "N/A"
        h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

    def _update_info_ui(self, info):
        self.info_spinner.stop()
        self.download_button.set_sensitive(True)

        # Спершу ховаємо всі детальні поля
        for label in self.info_detail_labels:
            label.set_visible(False)

        if info:
            self.video_info = info
            is_playlist = info.get('_type', 'video') in ['playlist', 'multi_video']
            
            # --- Основна інформація ---
            self.info_title_label.set_text(info.get('title', '...'))
            if is_playlist:
                self.info_uploader_label.set_text(f"{info.get('uploader', '...')} ({info.get('playlist_count')} відео)")
                self.info_duration_label.set_text("Плейлист")
            else:
                self.info_uploader_label.set_text(info.get('uploader', '...'))
                self.info_duration_label.set_text(self._format_duration(info.get('duration')))

                # --- Детальна інформація (тільки для окремих відео) ---
                chosen_format = info # yt-dlp надає найкращий формат на верхньому рівні
                
                # Роздільна здатність, FPS та розширення
                res_parts = []
                if chosen_format.get('width') and chosen_format.get('height'):
                    res_parts.append(f"{chosen_format['width']}x{chosen_format['height']}")
                if chosen_format.get('fps'):
                    res_parts.append(f"{chosen_format['fps']}fps")
                if chosen_format.get('ext'):
                    res_parts.append(f"(.{chosen_format['ext']})")
                self.info_resolution_label.set_text(' '.join(res_parts) or "N/A")

                # Кодеки
                vcodec = chosen_format.get('vcodec', 'none').split('.')[0]
                acodec = chosen_format.get('acodec', 'none').split('.')[0]
                self.info_codecs_label.set_text(f"Відео: {vcodec}, Аудіо: {acodec}")

                # Бітрейт
                bitrate = chosen_format.get('tbr')
                self.info_bitrate_label.set_text(f"{bitrate:.0f} кбіт/с" if bitrate else "N/A")

                # Розмір файлу
                filesize = chosen_format.get('filesize') or chosen_format.get('filesize_approx')
                self.info_size_label.set_text(self._format_size(filesize) if filesize else "N/A")

                # Показуємо всі детальні поля
                for label in self.info_detail_labels:
                    label.set_visible(True)
        else:
            self.info_title_label.set_text("Не вдалося отримати інформацію про URL.")
            self.info_uploader_label.set_text("...")
            self.info_duration_label.set_text("...")

        self.info_grid.set_no_show_all(False)
        self.info_grid.show_all()
        # Додатково показати/сховати розділювач
        separator = self.info_detail_labels[0].get_parent().get_children()[6] # Не дуже надійно, але працює для цієї структури
        separator.set_visible(any(lbl.get_visible() for lbl in self.info_detail_labels))

        return False

    def _build_file_browser(self):
        self.page_widget.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL, margin_top=10, margin_bottom=5), False, False, 0)
        self.page_widget.pack_start(Gtk.Label(label=f"<b>{_('Перегляд головної папки:')}</b>", use_markup=True, xalign=0.0, margin_bottom=5), False, False, 0)

        self.file_list_store = Gtk.ListStore(str, str, str, str)
        self.file_tree_view = Gtk.TreeView(model=self.file_list_store)
        self.file_tree_view.connect("row-activated", self._on_file_tree_view_row_activated)

        for i, title in enumerate([_("Ім'я файлу/Папки"), _("Тип"), _("Розмір")]):
            self.file_tree_view.append_column(Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i))

        scrolled_window_files = Gtk.ScrolledWindow(shadow_type=Gtk.ShadowType.IN, hexpand=True, vexpand=True, min_content_height=150)
        scrolled_window_files.add(self.file_tree_view)
        self.page_widget.pack_start(scrolled_window_files, True, True, 0)

        browser_buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin_top=5)
        self.page_widget.pack_start(browser_buttons_box, False, False, 0)

        btn_refresh_files = Gtk.Button(label=_("Оновити список"))
        btn_refresh_files.connect("clicked", self._populate_file_browser)
        browser_buttons_box.pack_start(btn_refresh_files, False, False, 0)

        btn_open_selected_file = Gtk.Button(label=_("Відкрити вибране"))
        btn_open_selected_file.connect("clicked", self._on_open_selected_file_clicked)
        browser_buttons_box.pack_start(btn_open_selected_file, False, False, 0)

        btn_open_output_dir_fs = Gtk.Button(label=_("Відкрити головну папку"))
        btn_open_output_dir_fs.connect("clicked", self._on_open_output_dir_fs_clicked)
        browser_buttons_box.pack_start(btn_open_output_dir_fs, False, False, 0)

    def _suggest_default_output_dir(self):
        saved_path = self.app.settings.get('youtube_output_dir')
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads", "YouTube_DownYS")
        self.base_output_dir_entry.set_text(saved_path if saved_path and os.path.isdir(saved_path) else default_dir)

    def _on_file_tree_view_row_activated(self, treeview, path, column):
        model, iter_ = treeview.get_model(), treeview.get_model().get_iter(path)
        if iter_:
            self._open_path_externally(model.get_value(iter_, 3))

    def _on_open_selected_file_clicked(self, widget):
        model, iter_ = self.file_tree_view.get_selection().get_selected()
        if iter_:
            self._open_path_externally(model.get_value(iter_, 3))
        else:
            self.show_warning_dialog(_("Будь ласка, виберіть файл або папку у списку."))

    def _on_open_output_dir_fs_clicked(self, widget):
        dir_path = self.base_output_dir_entry.get_text().strip()
        if dir_path and os.path.isdir(dir_path):
            self._open_path_externally(dir_path)
        else:
            self.show_warning_dialog(_("Вкажіть головну директорію збереження."))

    def _populate_file_browser(self, widget=None, event=None):
        if not self.file_list_store:
            return
        self.file_list_store.clear()
        directory_path = self.base_output_dir_entry.get_text().strip()
        if not directory_path or not os.path.isdir(directory_path):
            self.file_list_store.append([f"'{os.path.basename(directory_path)}'", _("Директорія не знайдена"), "", ""])
            return
        try:
            items = sorted(os.listdir(directory_path), key=str.lower)
            if not items:
                self.file_list_store.append([_("(Папка порожня)"), "", "", ""])
            else:
                for item_name in items:
                    full_path = os.path.join(directory_path, item_name)
                    try:
                        is_dir = os.path.isdir(full_path)
                        item_type = _("Папка") if is_dir else _("Файл")
                        size_str = "" if is_dir else self._format_size(os.path.getsize(full_path))
                        self.file_list_store.append([item_name, item_type, size_str, full_path])
                    except OSError:
                        self.file_list_store.append([item_name, _("Недоступно"), "", full_path])
        except OSError as e:
            self.file_list_store.append([f"{_('Помилка доступу')} '{os.path.basename(directory_path)}'", str(e), "", directory_path])

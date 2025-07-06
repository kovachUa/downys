import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import os
import re
import datetime

from ui.base_page import BasePage
from scripts.httrack_tasks import run_httrack_web_threaded, archive_directory_threaded

_ = lambda s: s

class HTTrackPage(BasePage):
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        self.mirror_radio, self.archive_radio = None, None
        self.stack, self.execute_button = None, None
        self.url_entry, self.mirror_output_dir_entry = None, None
        self.archive_after_mirror_check = None
        self.post_mirror_archive_hbox, self.post_mirror_archive_entry = None, None
        self.dir_to_archive_entry, self.archive_file_entry = None, None
        self.depth_spin, self.rate_spin, self.sockets_spin = None, None, None

    def build_ui(self):
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        self.page_widget.pack_start(Gtk.Label(label=f"<b><big>{_('HTTrack та Архівування')}</big></b>", use_markup=True), False, False, 0)
        
        main_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self.page_widget.pack_start(main_grid, False, False, 0)
        
        main_grid.attach(Gtk.Label(label=_("Дія:"), halign=Gtk.Align.END), 0, 0, 1, 1)
        hbox_op = Gtk.Box(spacing=10); main_grid.attach(hbox_op, 1, 0, 3, 1)
        
        self.mirror_radio = Gtk.RadioButton.new_with_label(None, _("Віддзеркалити / Оновити сайт"))
        self.mirror_radio.set_active(True)
        self.mirror_radio.connect("toggled", self._on_operation_toggled)
        hbox_op.pack_start(self.mirror_radio, False, False, 0)
        
        self.archive_radio = Gtk.RadioButton.new_with_label_from_widget(self.mirror_radio, _("Архівувати директорію"))
        self.archive_radio.connect("toggled", self._on_operation_toggled)
        hbox_op.pack_start(self.archive_radio, False, False, 0)
        
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        main_grid.attach(self.stack, 0, 1, 4, 1) 
        
        self.stack.add_titled(self._build_mirror_ui(), "mirror_section", "Mirror Options") 
        self.stack.add_titled(self._build_archive_ui(), "archive_section", "Archive Options") 
        
        self.execute_button = Gtk.Button(label=_("Виконати HTTrack")) 
        self.execute_button.connect("clicked", self._on_execute_clicked)
        self.page_widget.pack_start(self.execute_button, False, False, 5) 
        
        self._suggest_default_paths() 
        self.stack.set_visible_child_name("mirror_section") 
        GLib.idle_add(self._update_ui_state) 
        if self.post_mirror_archive_hbox: self.post_mirror_archive_hbox.set_visible(False)
        
        return self.page_widget

    def _build_mirror_ui(self):
        grid = Gtk.Grid(column_spacing=10, row_spacing=8)

        # Row 0: URL
        grid.attach(Gtk.Label(label=_("URL сайту:"), halign=Gtk.Align.END), 0, 0, 1, 1)
        self.url_entry = Gtk.Entry(hexpand=True, placeholder_text=_("Введіть URL сайту"))
        self.url_entry.connect("changed", self._on_mirror_input_changed) 
        grid.attach(self.url_entry, 1, 0, 3, 1)
        
        # Row 1: Output Directory
        grid.attach(Gtk.Label(label=_("Дир. збереження:"), halign=Gtk.Align.END), 0, 1, 1, 1)
        self.mirror_output_dir_entry = Gtk.Entry(hexpand=True)
        self.mirror_output_dir_entry.connect("changed", self._on_mirror_input_changed) 
        grid.attach(self.mirror_output_dir_entry, 1, 1, 2, 1)
        btn1 = Gtk.Button(label="..."); btn1.connect("clicked", lambda w: self._select_folder_dialog(self.mirror_output_dir_entry, _("Оберіть директорію")))
        grid.attach(btn1, 3, 1, 1, 1)
        
        # Row 2: Options
        options_grid = Gtk.Grid(column_spacing=10, row_spacing=5)
        grid.attach(options_grid, 0, 2, 4, 1)
        options_grid.attach(Gtk.Label(label=_("Глибина:"), halign=Gtk.Align.END), 0, 0, 1, 1)
        self.depth_spin = Gtk.SpinButton.new_with_range(0, 100, 1); self.depth_spin.set_value(3)
        options_grid.attach(self.depth_spin, 1, 0, 1, 1)
        options_grid.attach(Gtk.Label(label=_("Швидкість (B/s):"), halign=Gtk.Align.END), 2, 0, 1, 1)
        self.rate_spin = Gtk.SpinButton.new_with_range(0, 1000000, 1000); self.rate_spin.set_value(50000)
        options_grid.attach(self.rate_spin, 3, 0, 1, 1)
        options_grid.attach(Gtk.Label(label=_("Сокети:"), halign=Gtk.Align.END), 4, 0, 1, 1)
        self.sockets_spin = Gtk.SpinButton.new_with_range(1, 20, 1); self.sockets_spin.set_value(2)
        options_grid.attach(self.sockets_spin, 5, 0, 1, 1)

        # Row 3: Archive after mirror
        self.archive_after_mirror_check = Gtk.CheckButton(label=_("Архівувати результат"))
        self.archive_after_mirror_check.connect("toggled", self._on_archive_after_mirror_toggled)
        grid.attach(self.archive_after_mirror_check, 0, 3, 4, 1)
        
        # Row 4: Post mirror archive path
        self.post_mirror_archive_hbox = Gtk.Box(spacing=10, no_show_all=True)
        grid.attach(self.post_mirror_archive_hbox, 0, 4, 4, 1)
        self.post_mirror_archive_hbox.pack_start(Gtk.Label(label=_("Файл архіву:")), False, False, 0)
        self.post_mirror_archive_entry = Gtk.Entry(hexpand=True)
        self.post_mirror_archive_hbox.pack_start(self.post_mirror_archive_entry, True, True, 0)
        btn2 = Gtk.Button(label="..."); btn2.connect("clicked", lambda w: self._select_file_dialog(self.post_mirror_archive_entry, _("Оберіть файл архіву"), save_mode=True))
        self.post_mirror_archive_hbox.pack_start(btn2, False, False, 0)
        return grid

    def _build_archive_ui(self):
        grid = Gtk.Grid(column_spacing=10, row_spacing=8)

        # Row 0: Directory to archive
        grid.attach(Gtk.Label(label=_("Дир. для архів.:"), halign=Gtk.Align.END), 0, 0, 1, 1)
        self.dir_to_archive_entry = Gtk.Entry(hexpand=True)
        self.dir_to_archive_entry.connect("changed", self._on_archive_input_changed) 
        grid.attach(self.dir_to_archive_entry, 1, 0, 2, 1)
        btn1 = Gtk.Button(label="..."); btn1.connect("clicked", lambda w: self._select_folder_dialog(self.dir_to_archive_entry, _("Оберіть директорію")))
        grid.attach(btn1, 3, 0, 1, 1)
        
        # Row 1: Archive file path
        grid.attach(Gtk.Label(label=_("Файл архіву:"), halign=Gtk.Align.END), 0, 1, 1, 1)
        self.archive_file_entry = Gtk.Entry(hexpand=True)
        grid.attach(self.archive_file_entry, 1, 1, 2, 1)
        btn2 = Gtk.Button(label="..."); btn2.connect("clicked", lambda w: self._select_file_dialog(self.archive_file_entry, _("Оберіть шлях для архіву"), save_mode=True))
        grid.attach(btn2, 3, 1, 1, 1)
        return grid

    def _suggest_default_paths(self):
        default_mirror_dir = os.path.join(os.path.expanduser("~"), "httrack_mirrors")
        if self.mirror_output_dir_entry and not self.mirror_output_dir_entry.get_text():
            self.mirror_output_dir_entry.set_text(default_mirror_dir)
        if self.dir_to_archive_entry and not self.dir_to_archive_entry.get_text():
             self.dir_to_archive_entry.set_text(default_mirror_dir)
             if self.archive_radio and self.archive_radio.get_active():
                 self._suggest_archive_filename(default_mirror_dir)

    def _suggest_archive_filename(self, source_dir):
        if not self.archive_file_entry: return
        base_save_path = os.path.expanduser("~")
        if source_dir and os.path.isdir(source_dir):
            base_save_path = os.path.dirname(os.path.abspath(source_dir)) or base_save_path
        elif source_dir and os.path.isdir(os.path.dirname(source_dir)):
            base_save_path = os.path.dirname(source_dir)
        
        base_name_str = "archive"
        if source_dir:
             base_name_str = re.sub(r'[^\w.-]+', '_', os.path.basename(os.path.normpath(source_dir)) or "archive").strip('_') or "archive"
        
        suggested_name = f"{datetime.datetime.now().strftime('%Y%m%d')}_{base_name_str}.tar.gz"
        suggested_path = os.path.join(base_save_path, suggested_name)
        self.archive_file_entry.set_text(suggested_path)

    def _suggest_post_mirror_archive_filename(self, mirror_dir, url):
        if not self.post_mirror_archive_entry: return
        base_save_path = os.path.expanduser("~")
        if mirror_dir and os.path.isdir(os.path.dirname(os.path.abspath(mirror_dir))):
             base_save_path = os.path.dirname(os.path.abspath(mirror_dir))
        
        base_name = "website"
        hostname = self.url_handler.get_hostname_from_url(url)
        if hostname: base_name = hostname
        
        suggested_name = f"{datetime.datetime.now().strftime('%Y%m%d')}_{base_name}_archive.tar.gz"
        self.post_mirror_archive_entry.set_text(os.path.join(base_save_path, suggested_name))

    def _update_ui_state(self, *args):
        is_mirror_mode = self.mirror_radio.get_active()
        self.stack.set_visible_child_name("mirror_section" if is_mirror_mode else "archive_section")
        self.execute_button.set_label(_("Виконати HTTrack") if is_mirror_mode else _("Архівувати"))
        self.post_mirror_archive_hbox.set_visible(is_mirror_mode and self.archive_after_mirror_check.get_active())

    def _on_operation_toggled(self, radio_button):
        if radio_button.get_active(): self._update_ui_state()

    def _on_archive_after_mirror_toggled(self, check_button):
        self._update_ui_state()
        if check_button.get_active():
             self._suggest_post_mirror_archive_filename(self.mirror_output_dir_entry.get_text(), self.url_entry.get_text())

    def _on_mirror_input_changed(self, entry):
        if self.mirror_radio.get_active() and self.archive_after_mirror_check.get_active():
             self._suggest_post_mirror_archive_filename(self.mirror_output_dir_entry.get_text(), self.url_entry.get_text())

    def _on_archive_input_changed(self, entry):
         if self.archive_radio.get_active():
             self._suggest_archive_filename(entry.get_text().strip())

    def _on_execute_clicked(self, widget):
        if self.app.active_tasks:
            self.show_warning_dialog(_("Завдання вже виконується."))
            return
        try:
            if self.mirror_radio.get_active(): self._execute_mirror()
            else: self._execute_archive()
        except (ValueError, RuntimeError, FileNotFoundError) as e:
            self.show_warning_dialog(str(e))
        except Exception as e:
            self.app.show_detailed_error_dialog(_("Неочікувана помилка"), str(e))

    def _execute_mirror(self):
        url = self.url_entry.get_text().strip()
        mirror_dir = self.mirror_output_dir_entry.get_text().strip()
        archive_after = self.archive_after_mirror_check.get_active()
        archive_path = self.post_mirror_archive_entry.get_text().strip() if archive_after else None
        
        self.url_handler.validate_httrack_url(url)
        if not mirror_dir: raise ValueError(_("Вкажіть директорію для дзеркала."))
        os.makedirs(mirror_dir, exist_ok=True)
        
        if archive_after and not archive_path: raise ValueError(_("Вкажіть шлях для архіву."))
        
        httrack_opts = {
            'max_depth': self.depth_spin.get_value_as_int(),
            'max_rate': self.rate_spin.get_value_as_int(),
            'sockets': self.sockets_spin.get_value_as_int(),
            'archive_after_mirror': archive_after,
            'post_mirror_archive_path': archive_path,
        }
        
        task_name = f"HTTrack: {self.url_handler.get_hostname_from_url(url) or url}"
        self.app.start_task(run_httrack_web_threaded, task_name, args=(url, mirror_dir), kwargs=httrack_opts)

    def _execute_archive(self):
         source_dir = self.dir_to_archive_entry.get_text().strip()
         archive_path = self.archive_file_entry.get_text().strip()
         if not source_dir or not os.path.isdir(source_dir): raise ValueError(_(f"Директорія не знайдена: {source_dir}"))
         if not archive_path: raise ValueError(_("Вкажіть шлях для архіву."))
         if os.path.abspath(archive_path).startswith(os.path.abspath(source_dir)):
             raise ValueError(_("Не можна зберігати архів всередині директорії, що архівується."))

         task_name = f"Archive: {os.path.basename(source_dir)}"
         self.app.start_task(archive_directory_threaded, task_name, args=(source_dir, archive_path))

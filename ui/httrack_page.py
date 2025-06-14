# scripts/ui/httrack_page.py

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import os
import re
import datetime

from ui.base_page import BasePage
from scripts.httrack_tasks import run_httrack_web_threaded, archive_directory_threaded

class HTTrackPage(BasePage):
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        self.mirror_radio, self.archive_radio = None, None
        self.stack, self.execute_button = None, None
        self.url_entry, self.mirror_output_dir_entry = None, None
        self.archive_after_mirror_check = None
        self.post_mirror_archive_hbox, self.post_mirror_archive_entry = None, None
        self.dir_to_archive_entry, self.archive_file_entry = None, None

    def build_ui(self):
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        self.page_widget.pack_start(Gtk.Label(label="<b><big>HTTrack та Архівування</big></b>", use_markup=True), False, False, 0)
        
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self.page_widget.pack_start(grid, False, False, 0)
        
        grid.attach(Gtk.Label(label="Дія:", halign=Gtk.Align.END), 0, 0, 1, 1)
        hbox_op = Gtk.Box(spacing=10); grid.attach(hbox_op, 1, 0, 3, 1)
        
        self.mirror_radio = Gtk.RadioButton.new_with_label(None, "Віддзеркалити / Оновити сайт")
        self.mirror_radio.set_active(True)
        self.mirror_radio.connect("toggled", self._on_operation_toggled)
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
        if self.mirror_output_dir_entry and not self.mirror_output_dir_entry.get_text():
            self.mirror_output_dir_entry.set_text(default_mirror_dir)
        if self.dir_to_archive_entry and not self.dir_to_archive_entry.get_text():
             self.dir_to_archive_entry.set_text(default_mirror_dir)
             if self.archive_radio and self.archive_radio.get_active():
                 self._suggest_archive_filename(default_mirror_dir)

    def _suggest_archive_filename(self, source_dir):
        if not self.archive_file_entry: return
        base_save_path = os.path.expanduser("~")
        base = "archive"
        if source_dir and os.path.isdir(source_dir):
            base_save_path = os.path.dirname(os.path.abspath(source_dir)) or base_save_path
            base = re.sub(r'[^\w.-]+', '_', os.path.basename(os.path.normpath(source_dir)) or "archive").strip('_') or "archive"
        suggested_name = f"{datetime.datetime.now().strftime('%Y%m%d')}_{base}.tar.gz"
        suggested_path = os.path.join(base_save_path, suggested_name)
        self.archive_file_entry.set_text(suggested_path)

    def _suggest_post_mirror_archive_filename(self, mirror_dir, url):
        if not self.post_mirror_archive_entry: return
        base_save_path = os.path.expanduser("~")
        base_name = "website"
        hostname = self.url_handler.get_hostname_from_url(url)
        if hostname: base_name = hostname
        suggested_name = f"{datetime.datetime.now().strftime('%Y%m%d')}_{base_name}_archive.tar.gz"
        if mirror_dir and os.path.isdir(mirror_dir):
             base_save_path = os.path.dirname(os.path.abspath(mirror_dir)) or base_save_path
        self.post_mirror_archive_entry.set_text(os.path.join(base_save_path, suggested_name))

    def _update_ui_state(self, *args):
        is_mirror_mode = self.mirror_radio.get_active()
        self.stack.set_visible_child_name("mirror_section" if is_mirror_mode else "archive_section")
        self.execute_button.set_label("Виконати HTTrack" if is_mirror_mode else "Архівувати")
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
        if self.app._is_task_running:
            self.show_warning_dialog("Завдання вже виконується.")
            return
        try:
            if self.mirror_radio.get_active(): self._execute_mirror()
            else: self._execute_archive()
        except (ValueError, RuntimeError, FileNotFoundError) as e:
            self.show_warning_dialog(str(e))
        except Exception as e:
            import traceback; traceback.print_exc()
            self.show_warning_dialog(f"Неочікувана помилка: {e}")

    def _execute_mirror(self):
        url, mirror_dir = self.url_entry.get_text().strip(), self.mirror_output_dir_entry.get_text().strip()
        archive_after = self.archive_after_mirror_check.get_active()
        archive_path = self.post_mirror_archive_entry.get_text().strip() if archive_after else None
        
        self.url_handler.validate_httrack_url(url) # Can raise ValueError
        if not mirror_dir: raise ValueError("Вкажіть директорію для дзеркала.")
        os.makedirs(mirror_dir, exist_ok=True)
        
        if archive_after and not archive_path: raise ValueError("Вкажіть шлях для архіву.")
        
        self._start_task(run_httrack_web_threaded, args=(url, mirror_dir), kwargs={'archive_after_mirror': archive_after, 'post_mirror_archive_path': archive_path, 'mirror_output_dir': mirror_dir, 'site_url': url})

    def _execute_archive(self):
         source_dir, archive_path = self.dir_to_archive_entry.get_text().strip(), self.archive_file_entry.get_text().strip()
         if not source_dir or not os.path.isdir(source_dir): raise ValueError(f"Директорія не знайдена: {source_dir}")
         if not archive_path: raise ValueError("Вкажіть шлях для архіву.")
         if os.path.abspath(archive_path).startswith(os.path.abspath(source_dir)):
             raise ValueError("Не можна зберігати архів всередині директорії, що архівується.")
         self._start_task(archive_directory_threaded, args=(source_dir, archive_path), kwargs={})

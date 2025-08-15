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
        self.mirror_create_radio, self.mirror_update_radio, self.archive_radio = None, None, None
        self.stack, self.execute_button = None, None
        self.url_entry, self.mirror_output_dir_entry = None, None
        self.archive_after_mirror_check = None
        self.post_mirror_archive_hbox, self.post_mirror_archive_entry = None, None
        self.dir_to_archive_entry, self.archive_file_entry = None, None
        self.depth_spin, self.rate_spin, self.sockets_spin = None, None, None
        self.follow_robots_check = None
        # --- НОВЕ: Віджет для списку сайтів ---
        self.site_listbox = None

    def build_ui(self):
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        self.page_widget.pack_start(Gtk.Label(label=f"<b><big>{_('HTTrack та Архівування')}</big></b>", use_markup=True), False, False, 0)
        
        main_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self.page_widget.pack_start(main_grid, False, False, 0)
        
        main_grid.attach(Gtk.Label(label=_("Дія:"), halign=Gtk.Align.END), 0, 0, 1, 1)
        hbox_op = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        main_grid.attach(hbox_op, 1, 0, 3, 1)
        
        self.mirror_create_radio = Gtk.RadioButton.new_with_label(None, _("Віддзеркалити (створити нове)"))
        self.mirror_create_radio.set_active(True)
        self.mirror_create_radio.connect("toggled", self._on_operation_toggled)
        hbox_op.pack_start(self.mirror_create_radio, False, False, 0)
        
        self.mirror_update_radio = Gtk.RadioButton.new_with_label_from_widget(self.mirror_create_radio, _("Оновити існуюче дзеркало"))
        self.mirror_update_radio.connect("toggled", self._on_operation_toggled)
        hbox_op.pack_start(self.mirror_update_radio, False, False, 0)

        self.archive_radio = Gtk.RadioButton.new_with_label_from_widget(self.mirror_create_radio, _("Архівувати будь-яку директорію"))
        self.archive_radio.connect("toggled", self._on_operation_toggled)
        hbox_op.pack_start(self.archive_radio, False, False, 0)
        
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        main_grid.attach(self.stack, 0, 1, 4, 1) 
        
        self.stack.add_titled(self._build_mirror_ui(), "mirror_section", "Mirror Options") 
        self.stack.add_titled(self._build_archive_ui(), "archive_section", "Archive Options") 
        
        self.execute_button = Gtk.Button(label=_("Виконати")) 
        self.execute_button.connect("clicked", self._on_execute_clicked)
        self.page_widget.pack_start(self.execute_button, False, False, 5) 
        
        self._suggest_default_paths() 
        GLib.idle_add(self._update_ui_state)
        GLib.idle_add(self._populate_site_list)
        
        return self.page_widget

    def _build_mirror_ui(self):
        mirror_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        mirror_vbox.pack_start(grid, False, False, 0)

        grid.attach(Gtk.Label(label=_("URL сайту:"), halign=Gtk.Align.END), 0, 0, 1, 1)
        self.url_entry = Gtk.Entry(hexpand=True, placeholder_text=_("Введіть URL сайту для створення або оновлення"))
        self.url_entry.connect("changed", self._on_mirror_input_changed) 
        grid.attach(self.url_entry, 1, 0, 3, 1)
        
        grid.attach(Gtk.Label(label=_("Головна директорія:"), halign=Gtk.Align.END), 0, 1, 1, 1)
        self.mirror_output_dir_entry = Gtk.Entry(hexpand=True)
        self.mirror_output_dir_entry.connect("changed", lambda w: self.app.settings.set('httrack_mirror_dir', w.get_text().strip()))
        self.mirror_output_dir_entry.connect("changed", self._on_mirror_input_changed)
        # --- НОВЕ: Оновлюємо список сайтів, коли змінюється директорія ---
        self.mirror_output_dir_entry.connect("focus-out-event", lambda w, e: self._populate_site_list())
        grid.attach(self.mirror_output_dir_entry, 1, 1, 2, 1)
        btn1 = Gtk.Button(label="..."); btn1.connect("clicked", lambda w: self._select_folder_dialog(self.mirror_output_dir_entry, _("Оберіть головну директорію")))
        grid.attach(btn1, 3, 1, 1, 1)
        
        options_grid = Gtk.Grid(column_spacing=10, row_spacing=5, margin_top=5)
        grid.attach(options_grid, 0, 2, 4, 1)
        options_grid.attach(Gtk.Label(label=_("Глибина:"), halign=Gtk.Align.END), 0, 0, 1, 1)
        self.depth_spin = Gtk.SpinButton.new_with_range(0, 100, 1); self.depth_spin.set_value(3)
        options_grid.attach(self.depth_spin, 1, 0, 1, 1)
        options_grid.attach(Gtk.Label(label=_("Швидкість (B/s):"), halign=Gtk.Align.END), 2, 0, 1, 1)
        self.rate_spin = Gtk.SpinButton.new_with_range(0, 1000000, 1000); self.rate_spin.set_value(0)
        self.rate_spin.set_tooltip_text("0 = без обмежень")
        options_grid.attach(self.rate_spin, 3, 0, 1, 1)
        options_grid.attach(Gtk.Label(label=_("Сокети:"), halign=Gtk.Align.END), 4, 0, 1, 1)
        self.sockets_spin = Gtk.SpinButton.new_with_range(1, 20, 1); self.sockets_spin.set_value(4)
        options_grid.attach(self.sockets_spin, 5, 0, 1, 1)

        checks_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, margin_top=5)
        grid.attach(checks_box, 0, 3, 4, 1)
        self.follow_robots_check = Gtk.CheckButton(label=_("Дотримуватися правил robots.txt"))
        self.follow_robots_check.set_active(True)
        checks_box.pack_start(self.follow_robots_check, False, False, 0)
        
        self.archive_after_mirror_check = Gtk.CheckButton(label=_("Архівувати результат після завершення"))
        self.archive_after_mirror_check.connect("toggled", self._on_archive_after_mirror_toggled)
        checks_box.pack_start(self.archive_after_mirror_check, False, False, 0)
        
        self.post_mirror_archive_hbox = Gtk.Box(spacing=10, no_show_all=True, margin_left=20)
        grid.attach(self.post_mirror_archive_hbox, 0, 4, 4, 1)
        self.post_mirror_archive_hbox.pack_start(Gtk.Label(label=_("Файл архіву:")), False, False, 0)
        self.post_mirror_archive_entry = Gtk.Entry(hexpand=True)
        self.post_mirror_archive_hbox.pack_start(self.post_mirror_archive_entry, True, True, 0)
        btn2 = Gtk.Button(label="..."); btn2.connect("clicked", lambda w: self._select_file_dialog(self.post_mirror_archive_entry, _("Оберіть файл архіву"), save_mode=True))
        self.post_mirror_archive_hbox.pack_start(btn2, False, False, 0)

        # --- НОВИЙ БЛОК: Список завантажених сайтів ---
        mirror_vbox.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL, margin_top=15, margin_bottom=5), False, False, 0)
        mirror_vbox.pack_start(Gtk.Label(label=f"<b>{_('Завантажені сайти в головній директорії:')}</b>", use_markup=True, xalign=0), False, False, 0)
        
        scrolled_sites = Gtk.ScrolledWindow(shadow_type=Gtk.ShadowType.IN, min_content_height=120)
        self.site_listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        scrolled_sites.add(self.site_listbox)
        mirror_vbox.pack_start(scrolled_sites, True, True, 5)
        
        site_buttons_box = Gtk.Box(spacing=6)
        btn_refresh = Gtk.Button(label=_("Оновити список"))
        btn_refresh.connect("clicked", lambda w: self._populate_site_list())
        site_buttons_box.pack_start(btn_refresh, False, False, 0)
        
        btn_archive_selected = Gtk.Button(label=_("Архівувати вибраний сайт"))
        btn_archive_selected.connect("clicked", self._on_archive_selected_clicked)
        site_buttons_box.pack_start(btn_archive_selected, False, False, 0)
        mirror_vbox.pack_start(site_buttons_box, False, False, 0)
        # --- КІНЕЦЬ НОВОГО БЛОКУ ---

        return mirror_vbox

    def _build_archive_ui(self):
        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        grid.attach(Gtk.Label(label=_("Дир. для архів.:"), halign=Gtk.Align.END), 0, 0, 1, 1)
        self.dir_to_archive_entry = Gtk.Entry(hexpand=True)
        self.dir_to_archive_entry.connect("changed", lambda w: self.app.settings.set('httrack_archive_dir', w.get_text().strip()))
        self.dir_to_archive_entry.connect("changed", self._on_archive_input_changed)
        grid.attach(self.dir_to_archive_entry, 1, 0, 2, 1)
        btn1 = Gtk.Button(label="..."); btn1.connect("clicked", lambda w: self._select_folder_dialog(self.dir_to_archive_entry, _("Оберіть директорію")))
        grid.attach(btn1, 3, 0, 1, 1)
        grid.attach(Gtk.Label(label=_("Файл архіву:"), halign=Gtk.Align.END), 0, 1, 1, 1)
        self.archive_file_entry = Gtk.Entry(hexpand=True)
        grid.attach(self.archive_file_entry, 1, 1, 2, 1)
        btn2 = Gtk.Button(label="..."); btn2.connect("clicked", lambda w: self._select_file_dialog(self.archive_file_entry, _("Оберіть шлях для архіву"), save_mode=True))
        grid.attach(btn2, 3, 1, 1, 1)
        return grid

    def _populate_site_list(self):
        """Сканує головну директорію і заповнює список сайтів."""
        if not self.site_listbox: return
        
        for child in self.site_listbox.get_children(): self.site_listbox.remove(child)
        
        base_dir = self.mirror_output_dir_entry.get_text().strip()
        if not base_dir or not os.path.isdir(base_dir):
            row = Gtk.ListBoxRow(); row.add(Gtk.Label(label=_("<i>Головна директорія не вказана або не існує</i>"), use_markup=True))
            row.set_selectable(False); self.site_listbox.add(row)
            self.site_listbox.show_all(); return
        
        found_sites = []
        try:
            for item_name in os.listdir(base_dir):
                full_path = os.path.join(base_dir, item_name)
                if os.path.isdir(full_path):
                    found_sites.append((item_name, full_path))
        except OSError as e:
            row = Gtk.ListBoxRow(); row.add(Gtk.Label(label=_("<i>Помилка доступу до директорії</i>"), use_markup=True))
            row.set_selectable(False); self.site_listbox.add(row)
            self.site_listbox.show_all(); return
        
        if not found_sites:
            row = Gtk.ListBoxRow(); row.add(Gtk.Label(label=_("<i>Не знайдено завантажених сайтів</i>"), use_markup=True))
            row.set_selectable(False); self.site_listbox.add(row)
        else:
            for name, path in sorted(found_sites):
                row = Gtk.ListBoxRow()
                row.add(Gtk.Label(label=name, xalign=0))
                row.site_path = path # Зберігаємо повний шлях
                self.site_listbox.add(row)
                
        self.site_listbox.show_all()

    def _on_archive_selected_clicked(self, widget):
        """Обробник для кнопки 'Архівувати вибраний сайт'."""
        selected_row = self.site_listbox.get_selected_row()
        if not selected_row or not hasattr(selected_row, 'site_path'):
            self.show_warning_dialog(_("Будь ласка, виберіть сайт зі списку для архівування."))
            return
            
        source_dir = selected_row.site_path
        base_name = os.path.basename(source_dir)
        suggested_name = f"{datetime.datetime.now().strftime('%Y%m%d')}_{base_name}.tar.gz"
        
        dialog = Gtk.FileChooserDialog(
            title=_("Зберегти архів як..."), transient_for=self.app, action=Gtk.FileChooserAction.SAVE
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        dialog.set_current_folder(os.path.dirname(source_dir))
        dialog.set_current_name(suggested_name)
        dialog.set_do_overwrite_confirmation(True)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            archive_path = dialog.get_filename()
            dialog.destroy()
            
            if os.path.abspath(archive_path).startswith(os.path.abspath(source_dir)):
                 self.show_warning_dialog(_("Не можна зберігати архів всередині директорії, що архівується."))
                 return
            
            task_name = f"Archive: {base_name}"
            self.app.start_task(archive_directory_threaded, task_name, args=(source_dir, archive_path))
        else:
            dialog.destroy()
    
    # ... (решта методів класу залишається майже без змін, лише додається success_callback)
    
    def _suggest_default_paths(self):
        if self.mirror_output_dir_entry:
            saved_path = self.app.settings.get('httrack_mirror_dir')
            if saved_path and os.path.isdir(os.path.dirname(saved_path)): self.mirror_output_dir_entry.set_text(saved_path)
            elif not self.mirror_output_dir_entry.get_text(): self.mirror_output_dir_entry.set_text(os.path.join(os.path.expanduser("~"), "httrack_mirrors"))
        if self.dir_to_archive_entry:
            saved_path = self.app.settings.get('httrack_archive_dir')
            if saved_path and os.path.isdir(saved_path): self.dir_to_archive_entry.set_text(saved_path)
            elif not self.dir_to_archive_entry.get_text(): self.dir_to_archive_entry.set_text(self.mirror_output_dir_entry.get_text())
            if self.archive_radio and self.archive_radio.get_active(): self._suggest_archive_filename(self.dir_to_archive_entry.get_text())

    def _suggest_archive_filename(self, source_dir):
        if not self.archive_file_entry: return
        base_save_path = os.path.dirname(source_dir) if source_dir and os.path.isdir(source_dir) else os.path.expanduser("~")
        base_name_str = os.path.basename(os.path.normpath(source_dir)) if source_dir else "archive"
        suggested_name = f"{datetime.datetime.now().strftime('%Y%m%d')}_{base_name_str}.tar.gz"
        self.archive_file_entry.set_text(os.path.join(base_save_path, suggested_name))

    def _suggest_post_mirror_archive_filename(self, mirror_dir, url):
        if not self.post_mirror_archive_entry: return
        base_save_path = os.path.abspath(mirror_dir)
        hostname = self.url_handler.get_hostname_from_url(url) or "website"
        suggested_name = f"{datetime.datetime.now().strftime('%Y%m%d')}_{hostname}_archive.tar.gz"
        self.post_mirror_archive_entry.set_text(os.path.join(base_save_path, suggested_name))

    def _update_ui_state(self, *args):
        is_mirror_mode = self.mirror_create_radio.get_active() or self.mirror_update_radio.get_active()
        self.stack.set_visible_child_name("mirror_section" if is_mirror_mode else "archive_section")
        if self.mirror_create_radio.get_active(): self.execute_button.set_label(_("Віддзеркалити"))
        elif self.mirror_update_radio.get_active(): self.execute_button.set_label(_("Оновити"))
        else: self.execute_button.set_label(_("Архівувати"))
        self.post_mirror_archive_hbox.set_visible(is_mirror_mode and self.archive_after_mirror_check.get_active())
        self.archive_after_mirror_check.set_sensitive(self.mirror_create_radio.get_active())
        if self.mirror_update_radio.get_active(): self.archive_after_mirror_check.set_active(False)

    def _on_operation_toggled(self, radio_button):
        if radio_button.get_active(): self._suggest_default_paths(); self._update_ui_state()

    def _on_archive_after_mirror_toggled(self, check_button):
        self._update_ui_state()
        if check_button.get_active(): self._suggest_post_mirror_archive_filename(self.mirror_output_dir_entry.get_text(), self.url_entry.get_text())

    def _on_mirror_input_changed(self, entry):
        is_mirror_mode = self.mirror_create_radio.get_active() or self.mirror_update_radio.get_active()
        if is_mirror_mode and self.archive_after_mirror_check.get_active(): self._suggest_post_mirror_archive_filename(self.mirror_output_dir_entry.get_text(), self.url_entry.get_text())

    def _on_archive_input_changed(self, entry):
         if self.archive_radio.get_active(): self._suggest_archive_filename(entry.get_text().strip())

    def _on_execute_clicked(self, widget):
        if self.app.active_tasks: self.show_warning_dialog(_("Завдання вже виконується.")); return
        try:
            if self.mirror_create_radio.get_active() or self.mirror_update_radio.get_active(): self._execute_mirror()
            else: self._execute_archive()
        except (ValueError, RuntimeError, FileNotFoundError) as e: self.show_warning_dialog(str(e))
        except Exception as e: self.app.show_detailed_error_dialog(_("Неочікувана помилка"), str(e))

    def _execute_mirror(self):
        url, mirror_dir = self.url_entry.get_text().strip(), self.mirror_output_dir_entry.get_text().strip()
        archive_after, archive_path = self.archive_after_mirror_check.get_active(), self.post_mirror_archive_entry.get_text().strip() if self.archive_after_mirror_check.get_active() else None
        self.url_handler.validate_httrack_url(url)
        if not mirror_dir: raise ValueError(_("Вкажіть головну директорію для дзеркала."))
        os.makedirs(mirror_dir, exist_ok=True)
        if archive_after and not archive_path: raise ValueError(_("Вкажіть шлях для архіву."))
        
        mirror_mode = 'update' if self.mirror_update_radio.get_active() else 'create'
        if mirror_mode == 'update' and not os.path.isdir(os.path.join(mirror_dir, self.url_handler.get_hostname_from_url(url))):
             raise ValueError(_("Для оновлення, директорія проекту дзеркала вже повинна існувати."))

        httrack_opts = {
            'mirror_mode': mirror_mode, 'max_depth': self.depth_spin.get_value_as_int(),
            'max_rate': self.rate_spin.get_value_as_int(), 'sockets': self.sockets_spin.get_value_as_int(),
            'archive_after_mirror': archive_after, 'post_mirror_archive_path': archive_path,
            'follow_robots': self.follow_robots_check.get_active(),
        }
        
        task_name = f"HTTrack ({mirror_mode}): {self.url_handler.get_hostname_from_url(url) or url}"
        self.app.start_task(
            run_httrack_web_threaded, task_name, args=(url, mirror_dir), kwargs=httrack_opts,
            success_callback=self._populate_site_list # <-- Оновлюємо список після завершення
        )

    def _execute_archive(self):
         source_dir, archive_path = self.dir_to_archive_entry.get_text().strip(), self.archive_file_entry.get_text().strip()
         if not source_dir or not os.path.isdir(source_dir): raise ValueError(_(f"Директорія не знайдена: {source_dir}"))
         if not archive_path: raise ValueError(_("Вкажіть шлях для архіву."))
         if os.path.abspath(archive_path).startswith(os.path.abspath(source_dir)):
             raise ValueError(_("Не можна зберігати архів всередині директорії, що архівується."))
         task_name = f"Archive: {os.path.basename(source_dir)}"
         self.app.start_task(archive_directory_threaded, task_name, args=(source_dir, archive_path))

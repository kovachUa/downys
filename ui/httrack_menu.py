import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import os
import datetime
from urllib.parse import urlparse
import re


class HTTrackMenu(Gtk.Dialog):
    def __init__(self, parent, initial_url=""):
        super().__init__(title="Налаштування HTTrack / Архівування", parent=parent,
                         modal=True, destroy_with_parent=True)

        self.add_button("_Скасувати", Gtk.ResponseType.CANCEL)
        self.add_button("_Виконати", Gtk.ResponseType.OK)

        self.set_default_size(500, 350)
        self.set_border_width(10)

        box = self.get_content_area()
        box.set_spacing(10)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        box.add(grid)

        # Operation Type Selection
        grid.attach(Gtk.Label(label="Дія:"), 0, 0, 1, 1)
        hbox_operation = Gtk.Box(spacing=10)
        grid.attach(hbox_operation, 1, 0, 3, 1)

        self.mirror_radio = Gtk.RadioButton.new_with_label_from_widget(None, "Віддзеркалити / Оновити сайт")
        self.mirror_radio.set_active(True)
        self.mirror_radio.connect("toggled", self.on_operation_toggled)
        hbox_operation.pack_start(self.mirror_radio, False, False, 0)

        self.archive_radio = Gtk.RadioButton.new_with_label_from_widget(self.mirror_radio, "Архівувати директорію")
        self.archive_radio.connect("toggled", self.on_operation_toggled)
        hbox_operation.pack_start(self.archive_radio, False, False, 0)

        # Fields for Mirroring (URL, Output Dir, Archive after Mirror)
        self.mirror_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        grid.attach(self.mirror_box, 0, 1, 4, 4)

        # Single URL Entry (завжди видиме в mirror_box)
        url_hbox = Gtk.Box(spacing=10)
        self.mirror_box.pack_start(url_hbox, False, False, 0)
        url_hbox.pack_start(Gtk.Label(label="URL сайту:"), False, False, 0)
        self.url_entry = Gtk.Entry(text=initial_url)
        self.url_entry.set_hexpand(True)
        self.url_entry.connect("changed", self.on_url_changed)
        url_hbox.pack_start(self.url_entry, True, True, 0)

        # Output Directory for Mirroring
        output_dir_hbox = Gtk.Box(spacing=10)
        self.mirror_box.pack_start(output_dir_hbox, False, False, 0)
        output_dir_hbox.pack_start(Gtk.Label(label="Директорія збереження:"), False, False, 0)
        self.output_dir_entry = Gtk.Entry()
        self.output_dir_entry.set_hexpand(True)
        self.output_dir_entry.connect("changed", self.on_output_dir_changed)
        output_dir_hbox.pack_start(self.output_dir_entry, True, True, 0)
        output_dir_button = Gtk.Button(label="...")
        output_dir_button.connect("clicked", self.on_output_dir_clicked)
        output_dir_hbox.pack_start(output_dir_button, False, False, 0)

        # Option: Archive after Mirroring
        self.archive_after_mirror_check = Gtk.CheckButton(label="Архівувати результат віддзеркалення")
        self.archive_after_mirror_check.connect("toggled", self.on_archive_after_mirror_toggled)
        self.mirror_box.pack_start(self.archive_after_mirror_check, False, False, 0)

        # Archive File Path for post-mirror archiving
        self.post_mirror_archive_hbox = Gtk.Box(spacing=10)
        self.post_mirror_archive_hbox.set_visible(False)
        self.mirror_box.pack_start(self.post_mirror_archive_hbox, False, False, 0)

        self.post_mirror_archive_hbox.pack_start(Gtk.Label(label="Файл архіву результату:"), False, False, 0)
        self.post_mirror_archive_entry = Gtk.Entry()
        self.post_mirror_archive_entry.set_hexpand(True)
        self.post_mirror_archive_hbox.pack_start(self.post_mirror_archive_entry, True, True, 0)
        post_mirror_archive_button = Gtk.Button(label="...")
        post_mirror_archive_button.connect("clicked", self.on_post_mirror_archive_file_clicked)
        self.post_mirror_archive_hbox.pack_start(post_mirror_archive_button, False, False, 0)


        # Fields for Archiving (original logic)
        self.archive_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.archive_box.set_visible(False)
        grid.attach(self.archive_box, 0, 1, 4, 4)

        # Directory to Archive (всередині archive_box)
        dir_to_archive_hbox = Gtk.Box(spacing=10)
        self.archive_box.pack_start(dir_to_archive_hbox, False, False, 0)
        dir_to_archive_hbox.pack_start(Gtk.Label(label="Директорія для архівування:"), False, False, 0)
        self.dir_to_archive_entry = Gtk.Entry()
        self.dir_to_archive_entry.set_hexpand(True)
        self.dir_to_archive_entry.connect("changed", self.on_dir_to_archive_changed)
        dir_to_archive_hbox.pack_start(self.dir_to_archive_entry, True, True, 0)
        dir_to_archive_button = Gtk.Button(label="...")
        dir_to_archive_button.connect("clicked", self.on_dir_to_archive_clicked)
        dir_to_archive_hbox.pack_start(dir_to_archive_button, False, False, 0)


        # Archive File Path (всередині archive_box)
        archive_file_hbox = Gtk.Box(spacing=10)
        self.archive_box.pack_start(archive_file_hbox, False, False, 0)
        archive_file_hbox.pack_start(Gtk.Label(label="Файл архіву:"), False, False, 0)
        self.archive_file_entry = Gtk.Entry()
        self.archive_file_entry.set_hexpand(True)
        archive_file_hbox.pack_start(self.archive_file_entry, True, True, 0)
        archive_file_button = Gtk.Button(label="...")
        archive_file_button.connect("clicked", self.on_archive_file_clicked)
        archive_file_hbox.pack_start(archive_file_button, False, False, 0)


        self._suggest_default_output_dir()

        box.show_all()
        self.on_operation_toggled(self.mirror_radio)


    def _suggest_default_output_dir(self):
        default_dir = os.path.join(os.path.expanduser("~"), "httrack_downloads")
        self.output_dir_entry.set_text(default_dir)
        self.dir_to_archive_entry.set_text(default_dir)
        self._suggest_post_mirror_archive_filename(self.output_dir_entry.get_text().strip(), url=self.url_entry.get_text().strip())


    def on_operation_toggled(self, radio_button):
        if radio_button.get_active():
            operation_type = "mirror" if radio_button == self.mirror_radio else "archive"
            self.mirror_box.set_visible(operation_type == "mirror")
            self.archive_box.set_visible(operation_type == "archive")

            self.archive_after_mirror_check.set_visible(operation_type == "mirror")

            if operation_type == "mirror":
                self.on_archive_after_mirror_toggled(self.archive_after_mirror_check)

            execute_button = self.get_widget_for_response(Gtk.ResponseType.OK)
            if execute_button:
                execute_button.set_label("Архівувати" if operation_type == "archive" else "Виконати HTTrack")


    def on_batch_toggled(self, check_button):
        pass


    def on_archive_after_mirror_toggled(self, check_button):
        self.post_mirror_archive_hbox.set_visible(check_button.get_active())
        if check_button.get_active() and not self.post_mirror_archive_entry.get_text().strip():
             self._suggest_post_mirror_archive_filename(self.output_dir_entry.get_text().strip(), url=self.url_entry.get_text().strip())


    def on_url_changed(self, entry):
        if self.mirror_radio.get_active() and self.archive_after_mirror_check.get_active():
             self._suggest_post_mirror_archive_filename(self.output_dir_entry.get_text().strip(), url=entry.get_text().strip())


    def on_output_dir_changed(self, entry):
        if self.archive_after_mirror_check.get_active():
             self._suggest_post_mirror_archive_filename(entry.get_text().strip(), url=self.url_entry.get_text().strip())


    def on_dir_to_archive_changed(self, entry):
         self._suggest_archive_filename(entry.get_text().strip())


    def on_output_dir_clicked(self, widget):
        dialog = Gtk.FileChooserDialog("Оберіть директорію для збереження", self,
                                       Gtk.FileChooserAction.SELECT_FOLDER,
                                       ("_Скасувати", Gtk.ResponseType.CANCEL,
                                        "_Обрати", Gtk.ResponseType.OK))

        current_dir = self.output_dir_entry.get_text().strip()
        if current_dir and os.path.isdir(current_dir):
             dialog.set_current_folder(current_dir)
        else:
             dialog.set_current_folder(os.path.expanduser("~"))


        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            selected_dir = dialog.get_filename()
            self.output_dir_entry.set_text(selected_dir)
            if self.archive_after_mirror_check.get_active():
                 self._suggest_post_mirror_archive_filename(selected_dir, url=self.url_entry.get_text().strip())

        dialog.destroy()

    def on_list_file_clicked(self, widget):
        pass


    def on_dir_to_archive_clicked(self, widget):
        dialog = Gtk.FileChooserDialog("Оберіть директорію для архівування", self,
                                       Gtk.FileChooserAction.SELECT_FOLDER,
                                       ("_Скасувати", Gtk.ResponseType.CANCEL,
                                        "_Обрати", Gtk.ResponseType.OK))

        current_dir = self.dir_to_archive_entry.get_text().strip()
        if current_dir and os.path.isdir(current_dir):
             dialog.set_current_folder(current_dir)
        else:
             httrack_dir = self.output_dir_entry.get_text().strip()
             if httrack_dir and os.path.isdir(httrack_dir):
                  dialog.set_current_folder(httrack_dir)
             else:
                  dialog.set_current_folder(os.path.expanduser("~"))


        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            selected_dir = dialog.get_filename()
            self.dir_to_archive_entry.set_text(selected_dir)
            if not self.archive_file_entry.get_text().strip():
                 self._suggest_archive_filename(selected_dir)

        dialog.destroy()


    def on_archive_file_clicked(self, widget):
        dialog = Gtk.FileChooserDialog("Оберіть місце для збереження архіву", self,
                                       Gtk.FileChooserAction.SAVE,
                                       ("_Скасувати", Gtk.ResponseType.CANCEL,
                                        "_Зберегти", Gtk.ResponseType.OK))

        current_archive_dir = os.path.dirname(self.archive_file_entry.get_text().strip())
        if current_archive_dir and os.path.isdir(current_archive_dir):
             dialog.set_current_folder(current_archive_dir)
        else:
             archive_source_dir = self.dir_to_archive_entry.get_text().strip()
             if archive_source_dir and os.path.isdir(archive_source_dir):
                  dialog.set_current_folder(archive_source_dir)
             else:
                  dialog.set_current_folder(os.path.expanduser("~"))

        dir_to_archive = self.dir_to_archive_entry.get_text().strip()
        if dir_to_archive:
             self._suggest_archive_filename(dir_to_archive, dialog)
        else:
             dialog.set_current_name("archive.tar.gz")

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.archive_file_entry.set_text(dialog.get_filename())

        dialog.destroy()

    def on_post_mirror_archive_file_clicked(self, widget):
        dialog = Gtk.FileChooserDialog("Оберіть місце для збереження архіву (після віддзеркалення)", self,
                                       Gtk.FileChooserAction.SAVE,
                                       ("_Скасувати", Gtk.ResponseType.CANCEL,
                                        "_Зберегти", Gtk.ResponseType.OK))

        current_archive_dir = os.path.dirname(self.post_mirror_archive_entry.get_text().strip())
        if current_archive_dir and os.path.isdir(current_archive_dir):
             dialog.set_current_folder(current_archive_dir)
        else:
             mirror_output_dir = self.output_dir_entry.get_text().strip()
             if mirror_output_dir and os.path.isdir(os.path.dirname(mirror_output_dir) or "."):
                  dialog.set_current_folder(os.path.dirname(mirror_output_dir) or ".")
             else:
                  dialog.set_current_folder(os.path.expanduser("~"))


        mirror_output_dir = self.output_dir_entry.get_text().strip()
        url = self.url_entry.get_text().strip()
        self._suggest_post_mirror_archive_filename(mirror_output_dir, dialog, url=url)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.post_mirror_archive_entry.set_text(dialog.get_filename())

        dialog.destroy()


    def _suggest_archive_filename(self, directory_to_archive, file_chooser_dialog=None, default_ext=".tar.gz"):
        if not directory_to_archive:
             return

        base_name = os.path.basename(directory_to_archive)
        if not base_name: base_name = "archive"

        clean_base_name = re.sub(r'[^\w.-]', '_', base_name)

        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d")

        suggested_name = f"{timestamp}_{clean_base_name}{default_ext}"


        if file_chooser_dialog:
            file_chooser_dialog.set_current_name(suggested_name)
        else:
            current_archive_entry_text = self.archive_file_entry.get_text().strip()
            if not current_archive_entry_text:
                 suggested_path = os.path.join(os.path.dirname(directory_to_archive) or os.path.expanduser("~"), suggested_name)
                 self.archive_file_entry.set_text(suggested_path)
            elif os.path.dirname(self.archive_file_entry.get_text().strip()) != (os.path.dirname(directory_to_archive) or "."):
                current_filename = os.path.basename(self.archive_file_entry.get_text().strip())
                suggested_path = os.path.join(os.path.dirname(directory_to_archive) or os.path.expanduser("~"), current_filename)
                self.archive_file_entry.set_text(suggested_path)


    def _suggest_post_mirror_archive_filename(self, mirror_output_dir, file_chooser_dialog=None, default_ext=".tar.gz", url=None):
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
                pass # Не логуємо тут, бо це в UI логіці

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
        else:
            current_entry_text = self.post_mirror_archive_entry.get_text().strip()
            if not current_entry_text:
                 suggested_path = os.path.join(os.path.dirname(mirror_output_dir) or os.path.expanduser("~"), suggested_name)
                 self.post_mirror_archive_entry.set_text(suggested_path)
            elif os.path.dirname(self.post_mirror_archive_entry.get_text().strip()) != (os.path.dirname(mirror_output_dir) or "."):
                current_filename = os.path.basename(self.post_mirror_archive_entry.get_text().strip())
                suggested_path = os.path.join(os.path.dirname(mirror_output_dir) or os.path.expanduser("~"), current_filename)
                self.post_mirror_archive_entry.set_text(suggested_path)


    def get_params(self):
        operation_type = "mirror" if self.mirror_radio.get_active() else "archive"

        params = {
            "operation_type": operation_type,
            "url": None,
            "is_batch": False,
            "list_file": None,
            "mirror_output_dir": None,
            "archive_source_dir": None,
            "archive_path": None,
            "archive_after_mirror": False,
            "post_mirror_archive_path": None,
        }

        if operation_type == "mirror":
            params["is_batch"] = False # Масове завантаження прибрано з UI
            params["mirror_output_dir"] = self.output_dir_entry.get_text().strip()
            params["archive_after_mirror"] = self.archive_after_mirror_check.get_active()

            # Завжди одиночний URL в цьому режимі
            params["url"] = self.url_entry.get_text().strip()
            if not params["url"]:
                raise ValueError("Будь ласка, введіть URL сайту для віддзеркалення.")

            if not params["mirror_output_dir"]:
                 raise ValueError("Будь ласка, оберіть директорію для збереження.")
            parent_dir = os.path.dirname(params["mirror_output_dir"])
            if parent_dir and parent_dir != '.' and not os.path.isdir(parent_dir):
                 raise ValueError(f"Батьківська директорія для збереження не існує: {parent_dir}")

            if params["archive_after_mirror"]:
                 params["post_mirror_archive_path"] = self.post_mirror_archive_entry.get_text().strip()
                 if not params["post_mirror_archive_path"]:
                      raise ValueError("Будь ласка, вкажіть шлях для файлу архіву результату.")
                 archive_parent_dir = os.path.dirname(params["post_mirror_archive_path"])
                 if archive_parent_dir and archive_parent_dir != '.' and not os.path.isdir(archive_parent_dir):
                      raise ValueError(f"Батьківська директорія для файлу архіву (після віддзеркалення) не існує: {archive_parent_dir}")
                 try:
                     mirror_abs = os.path.abspath(params["mirror_output_dir"])
                     archive_parent_abs = os.path.abspath(os.path.dirname(params["post_mirror_archive_path"]))
                     if mirror_abs == archive_parent_abs:
                         pass # Попередження вже в логіці

                 except Exception as e:
                     pass # Попередження вже в логіці


        elif operation_type == "archive":
            params["archive_source_dir"] = self.dir_to_archive_entry.get_text().strip()
            params["archive_path"] = self.archive_file_entry.get_text().strip()

            if not params["archive_source_dir"]:
                 raise ValueError("Будь ласка, оберіть директорію для архівування.")
            if not os.path.isdir(params["archive_source_dir"]):
                 raise ValueError(f"Директорія для архівування не існує: {params['archive_source_dir']}")

            if not params["archive_path"]:
                 raise ValueError("Будь ласка, вкажіть шлях для збереження архіву.")
            archive_parent_dir = os.path.dirname(params["archive_path"])
            if archive_parent_dir and archive_parent_dir != '.' and not os.path.isdir(archive_parent_dir):
                 raise ValueError(f"Батьківська директорія для файлу архіву не існує: {archive_parent_dir}")


        return params

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import os

# Список доступних FFmpeg завдань та їх параметрів
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


class FFmpegMenu(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title="FFmpeg Налаштування та Конвертація", parent=parent,
                         modal=True, destroy_with_parent=True)

        self.add_button("_Скасувати", Gtk.ResponseType.CANCEL)
        self.add_button("_Виконати", Gtk.ResponseType.OK)

        self.set_default_size(500, 350) # Зменшено висоту, бо немає масової опції
        self.set_border_width(10)

        box = self.get_content_area()
        box.set_spacing(10)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        box.add(grid)

        # FFmpeg Task Selection
        grid.attach(Gtk.Label(label="Завдання FFmpeg:"), 0, 0, 1, 1)
        self.task_combo = Gtk.ComboBoxText()
        for label in FFMPEG_TASKS.keys():
            self.task_combo.append_text(label)
        self.task_combo.set_active(0)
        self.task_combo.connect("changed", self.on_task_changed)
        grid.attach(self.task_combo, 1, 0, 3, 1)

        # Fields for Parameters (завжди одиночні в оновленому меню)
        self.params_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        grid.attach(self.params_box, 0, 1, 4, 1) # Рядок 1

        # Input File (завжди файл в оновленому меню)
        self.input_label = Gtk.Label(label="Вхідний файл:")
        grid.attach(self.input_label, 0, 2, 1, 1) # Рядок 2
        self.input_path_entry = Gtk.Entry()
        self.input_path_entry.set_hexpand(True)
        grid.attach(self.input_path_entry, 1, 2, 2, 1)
        self.input_path_button = Gtk.Button(label="...")
        self.input_path_button.connect("clicked", self._on_select_file) # Підключаємо обробник вибору файла
        grid.attach(self.input_path_button, 3, 2, 1, 1)


        # Output File (завжди файл в оновленому меню)
        self.output_label = Gtk.Label(label="Вихідний файл:")
        grid.attach(self.output_label, 0, 3, 1, 1) # Рядок 3
        self.output_path_entry = Gtk.Entry()
        self.output_path_entry.set_hexpand(True)
        grid.attach(self.output_path_entry, 1, 3, 2, 1)
        self.output_path_button = Gtk.Button(label="...")
        self.output_path_button.connect("clicked", lambda w: self._on_select_file(self.output_path_entry, "Оберіть вихідний файл", save_mode=True)) # Підключаємо обробник вибору файла (режим збереження)
        grid.attach(self.output_path_button, 3, 3, 1, 1)


        # Show all elements and initialize
        box.show_all()
        self.on_task_changed(self.task_combo)


    def on_task_changed(self, combo):
        selected_label = combo.get_active_text()
        if not selected_label:
            return

        task_info = FFMPEG_TASKS.get(selected_label)
        if not task_info:
             return

        for widget in self.params_box.get_children():
            self.params_box.remove(widget)

        self.param_entries = {}

        for param_spec in task_info["params"]:
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


    def on_batch_toggled(self, check_button):
        pass


    # Обробник кліку кнопки вибору вхідного шляху (завжди файл)
    def on_input_path_button_clicked(self, widget):
        self._on_select_file(self.input_path_entry, "Оберіть вхідний файл")


    # Обробник кліку кнопки вибору вихідного шляху (завжди файл, режим збереження)
    def on_output_path_button_clicked(self, widget):
        self._on_select_file(self.output_path_entry, "Оберіть вихідний файл", save_mode=True)


    # Допоміжні функції для вибору файла/папки (універсальні, приймають entry_widget)
    # Видалили аргумент 'widget', оскільки він не використовувався
    def _on_select_file(self, entry_widget, title, save_mode=False):
        action = Gtk.FileChooserAction.SAVE if save_mode else Gtk.FileChooserAction.OPEN
        dialog = Gtk.FileChooserDialog(title, self, action,
                                       ("_Скасувати", Gtk.ResponseType.CANCEL,
                                        "_Зберегти" if save_mode else "_Відкрити", Gtk.ResponseType.OK))

        current_path = entry_widget.get_text().strip()
        if current_path:
            if os.path.isdir(current_path):
                 dialog.set_current_folder(current_path)
            elif os.path.exists(os.path.dirname(current_path)):
                 dialog.set_current_folder(os.path.dirname(current_path))
                 if save_mode:
                      dialog.set_current_name(os.path.basename(current_path))
            else:
                 dialog.set_current_folder(os.path.expanduser("~"))
                 if save_mode:
                      suggested_name = os.path.basename(current_path)
                      if suggested_name: dialog.set_current_name(suggested_name)
        else:
            dialog.set_current_folder(os.path.expanduser("~"))
            if save_mode:
                 selected_task_label = self.task_combo.get_active_text()
                 task_info = FFMPEG_TASKS.get(selected_task_label)
                 output_ext = task_info.get("output_ext", ".mp4") if task_info else ".mp4"
                 dialog.set_current_name(f"output_converted{output_ext}")

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            entry_widget.set_text(dialog.get_filename())

        dialog.destroy()

    def _on_select_folder(self, entry_widget, title):
        pass # Ця функція більше не використовується в FFmpegMenu


    def _update_output_suggestion(self):
        # is_batch завжди False
        input_path = self.input_path_entry.get_text().strip()
        output_path = self.output_path_entry.get_text().strip()
        selected_task_label = self.task_combo.get_active_text()
        task_info = FFMPEG_TASKS.get(selected_task_label)

        if not task_info:
            return

        output_ext = task_info.get("output_ext", ".mp4")

        # Завжди одиночний режим
        if input_path:
            input_dir = os.path.dirname(input_path)
            input_name_base, _ = os.path.splitext(os.path.basename(input_path))
            suggested_name = f"{input_name_base}_converted{output_ext}"
            suggested_path = os.path.join(input_dir, suggested_name)

            current_output_basename = os.path.basename(output_path)
            if not output_path or current_output_basename.startswith(f"{input_name_base}_converted"):
                 self.output_path_entry.set_text(suggested_path)
            else:
                 base, old_ext = os.path.splitext(output_path)
                 if old_ext != output_ext:
                      self.output_path_entry.set_text(base + output_ext)
        else:
             default_output_name = f"output_converted{output_ext}"
             if not output_path:
                  self.output_path_entry.set_text(os.path.join(os.path.expanduser("~"), default_output_name))


    def get_params(self):
        # is_batch завжди False
        selected_task_label = self.task_combo.get_active_text()
        task_info = FFMPEG_TASKS.get(selected_task_label)

        if not selected_task_label or not task_info:
             raise ValueError("Будь ласка, оберіть завдання FFmpeg.")

        task_type = task_info["type"]

        task_options = {}
        for param_spec in task_info.get("params", []):
            param_name = param_spec["name"]
            if param_name in self.param_entries:
                value = self.param_entries[param_name].get_text().strip()
                if not value and param_spec.get("required", False):
                     raise ValueError(f"Параметр '{param_spec['label']}' є обов'язковим і не може бути порожнім.")
                task_options[param_name] = value

        input_path = self.input_path_entry.get_text().strip()
        output_path = self.output_path_entry.get_text().strip()

        # Завжди одиночний режим
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


        return {
            "task_type": task_type,
            "task_options": task_options,
            "is_batch": False, # Завжди False
            "input_path": input_path,
            "output_path": output_path,
        }

# Блок if __name__ == "__main__": видалено

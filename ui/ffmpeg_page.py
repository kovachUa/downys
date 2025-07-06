import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import os

from ui.base_page import BasePage
from scripts.ffmpeg_tasks import run_ffmpeg_task

_ = lambda s: s

FFMPEG_TASKS = {
    "Відео -> MP4 (H264/AAC)": {"type": "convert_simple", "output_ext": ".mp4", "params": []},
    "Відео -> AVI (MPEG4/MP3)": {"type": "convert_format", "output_ext": ".avi", "params": []},
    "Відео -> Аудіо (AAC)": {"type": "extract_audio_aac", "output_ext": ".aac", "params": []},
    "Відео -> Аудіо (MP3)": {"type": "extract_audio_mp3", "output_ext": ".mp3", "params": []},
    "Стиснути Відео (Бітрейт)": {"type": "compress_bitrate", "output_ext": ".mp4", "params": [{"name": "bitrate", "label": "Відео Бітрейт (напр., 1M)", "type": "entry", "default": "1M", "required": True}]},
    "Змінити Роздільну здатність": {"type": "adjust_resolution", "output_ext": ".mp4", "params": [{"name": "width", "label": "Ширина", "type": "entry", "default": "1280", "required": True},{"name": "height", "label": "Висота", "type": "entry", "default": "720", "required": True}]}
}

class FFmpegPage(BasePage):
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        self.convert_radio = None
        self.merge_radio = None
        self.stack = None
        self.task_combo = None
        self.params_box = None
        self.param_entries = {}
        self.input_entry = None
        self.output_entry = None
        self.execute_button = None

    def build_ui(self):
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        self.page_widget.pack_start(Gtk.Label(label=f"<b><big>{_('FFmpeg Інструменти')}</big></b>", use_markup=True), False, False, 0)

        main_grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        self.page_widget.pack_start(main_grid, False, False, 0)

        main_grid.attach(Gtk.Label(label=_("Дія:"), halign=Gtk.Align.END), 0, 0, 1, 1)
        hbox_op = Gtk.Box(spacing=10)
        main_grid.attach(hbox_op, 1, 0, 3, 1)

        self.convert_radio = Gtk.RadioButton.new_with_label(None, _("Конвертувати / Змінити файл"))
        self.convert_radio.set_active(True)
        self.convert_radio.connect("toggled", self._on_operation_toggled)
        hbox_op.pack_start(self.convert_radio, False, False, 0)

        self.merge_radio = Gtk.RadioButton.new_with_label_from_widget(self.convert_radio, _("Об'єднати файли"))
        self.merge_radio.set_sensitive(False)
        self.merge_radio.connect("toggled", self._on_operation_toggled)
        hbox_op.pack_start(self.merge_radio, False, False, 0)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        main_grid.attach(self.stack, 0, 1, 4, 1)

        self.stack.add_titled(self._build_convert_ui(), "convert_section", "Convert Options")

        self.execute_button = Gtk.Button(label=_("Виконати"))
        self.execute_button.connect("clicked", self._on_execute_clicked)
        self.page_widget.pack_start(self.execute_button, False, False, 10)

        self.stack.set_visible_child_name("convert_section")
        GLib.idle_add(self._on_task_changed, self.task_combo)

        return self.page_widget

    def _build_convert_ui(self):
        grid = Gtk.Grid(column_spacing=10, row_spacing=8)

        grid.attach(Gtk.Label(label=_("Вхідний файл:"), halign=Gtk.Align.END), 0, 0, 1, 1)
        self.input_entry = Gtk.Entry(hexpand=True)
        self.input_entry.connect("changed", self._update_output_suggestion)
        grid.attach(self.input_entry, 1, 0, 2, 1)
        btn_in = Gtk.Button(label="..."); btn_in.connect("clicked", lambda w: self._select_file_dialog(self.input_entry, _("Оберіть вхідний файл")))
        grid.attach(btn_in, 3, 0, 1, 1)

        grid.attach(Gtk.Label(label=_("Вихідний файл:"), halign=Gtk.Align.END), 0, 1, 1, 1)
        self.output_entry = Gtk.Entry(hexpand=True)
        grid.attach(self.output_entry, 1, 1, 2, 1)
        btn_out = Gtk.Button(label="..."); btn_out.connect("clicked", lambda w: self._select_file_dialog(self.output_entry, _("Оберіть вихідний файл"), save_mode=True))
        grid.attach(btn_out, 3, 1, 1, 1)

        grid.attach(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL, margin_top=5, margin_bottom=5), 0, 2, 4, 1)

        grid.attach(Gtk.Label(label=_("Завдання:"), halign=Gtk.Align.END), 0, 3, 1, 1)
        self.task_combo = Gtk.ComboBoxText()
        for label in FFMPEG_TASKS.keys():
            self.task_combo.append_text(label)
        self.task_combo.set_active(0)
        self.task_combo.connect("changed", self._on_task_changed)
        grid.attach(self.task_combo, 1, 3, 3, 1)

        self.params_box = Gtk.Grid(column_spacing=10, row_spacing=8)
        grid.attach(self.params_box, 0, 4, 4, 1)

        return grid

    def _on_operation_toggled(self, radio_button):
        if not radio_button.get_active():
            return

        if self.convert_radio.get_active():
            self.stack.set_visible_child_name("convert_section")
            self.execute_button.set_label(_("Виконати конвертацію"))
        elif self.merge_radio.get_active():
            self.stack.set_visible_child_name("merge_section")
            self.execute_button.set_label(_("Об'єднати файли"))

    def _on_task_changed(self, combo):
        selected_label = combo.get_active_text()
        if not selected_label or not self.params_box: return
        task_info = FFMPEG_TASKS.get(selected_label)
        if not task_info: return

        for widget in self.params_box.get_children():
            self.params_box.remove(widget)

        self.param_entries = {}
        params = task_info.get("params", [])

        row, col = 0, 0
        for param_spec in params:
            if col >= 4:
                col = 0
                row += 1

            label_widget = Gtk.Label(label=f"{param_spec['label']}:", halign=Gtk.Align.END)
            self.params_box.attach(label_widget, col, row, 1, 1)
            col += 1

            if param_spec["type"] == "entry":
                entry = Gtk.Entry(text=param_spec.get("default", ""))
                self.params_box.attach(entry, col, row, 1, 1)
                self.param_entries[param_spec["name"]] = entry

            col += 1

        self.params_box.show_all()
        self._update_output_suggestion()

    def _update_output_suggestion(self, *args):
        if not all([self.input_entry, self.output_entry, self.task_combo]): return

        input_path = self.input_entry.get_text().strip()
        active_task_label = self.task_combo.get_active_text()
        if not active_task_label: return

        task_info = FFMPEG_TASKS.get(active_task_label, {})
        output_ext = task_info.get("output_ext", ".out")

        if input_path and os.path.isfile(input_path):
            input_dir, base = os.path.dirname(input_path), os.path.splitext(os.path.basename(input_path))[0]
            suggested_path = os.path.join(input_dir, f"{base}_converted{output_ext}")
            self.output_entry.set_text(suggested_path)

    def _on_execute_clicked(self, widget):
        try:
            if self.convert_radio.get_active():
                self._execute_convert_task()
            else:
                self.app.show_warning_dialog("Ця функція ще не реалізована.")

        except (ValueError, RuntimeError, FileNotFoundError) as e:
            self.app.show_warning_dialog(str(e))
        except Exception as e:
            self.app.show_detailed_error_dialog(_("Неочікувана помилка FFmpeg"), str(e))

    def _execute_convert_task(self):
        active_task_label = self.task_combo.get_active_text()
        if not active_task_label: raise ValueError(_("Оберіть завдання FFmpeg."))

        task_info = FFMPEG_TASKS.get(active_task_label)
        if not task_info: raise ValueError(_("Обрано невідоме завдання FFmpeg."))

        task_options = {spec["name"]: self.param_entries[spec["name"]].get_text().strip() for spec in task_info.get("params", [])}

        input_path = self.input_entry.get_text().strip()
        output_path = self.output_entry.get_text().strip()

        if not input_path: raise ValueError(_("Оберіть вхідний файл."))
        if not os.path.isfile(input_path): raise ValueError(_(f"Вхідний файл не знайдено: {input_path}"))
        if not output_path: raise ValueError(_("Вкажіть вихідний файл."))

        out_dir = os.path.dirname(output_path)
        if out_dir and not os.path.isdir(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        if os.path.abspath(input_path) == os.path.abspath(output_path):
            raise ValueError(_("Вхідний та вихідний файли не можуть бути однаковими."))

        task_name = f"FFmpeg: {os.path.basename(input_path)}"
        all_kwargs = {'task_type': task_info["type"], 'task_options': task_options}

        self.app.start_task(run_ffmpeg_task, task_name, args=(input_path, output_path), kwargs=all_kwargs)

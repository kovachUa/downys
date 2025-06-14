# scripts/ui/ffmpeg_page.py

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from ui.base_page import BasePage
from scripts.ffmpeg_tasks import run_ffmpeg_task # Імпорт з іншого модуля

# Визначення завдань FFmpeg. Вони специфічні для цієї сторінки.
FFMPEG_TASKS = {
    "Відео -> MP4 (Просто)": {"type": "convert_simple","output_ext": ".mp4","params": []},
    "Відео -> AVI": {"type": "convert_format","output_ext": ".avi","params": []},
    "Відео -> Аудіо (AAC)": {"type": "extract_audio_aac","output_ext": ".aac","params": []},
    "Відео -> Аудіо (MP3)": {"type": "extract_audio_mp3","output_ext": ".mp3","params": []},
    "Стиснути Відео (Бітрейт)": {"type": "compress_bitrate","output_ext": ".mp4","params": [{"name": "bitrate", "label": "Відео Бітрейт (напр., 1M)", "type": "entry", "default": "1M", "required": True}]},
    "Змінити Роздільну здатність": {"type": "adjust_resolution","output_ext": ".mp4","params": [{"name": "width", "label": "Ширина", "type": "entry", "default": "1280", "required": True},{"name": "height", "label": "Висота", "type": "entry", "default": "720", "required": True}]}
}


class FFmpegPage(BasePage):
    def __init__(self, app_window, url_handler):
        super().__init__(app_window, url_handler)
        self.task_combo = None
        self.params_box = None      
        self.param_entries = {}     
        self.input_entry = None
        self.output_entry = None
        self.execute_button = None

    def build_ui(self):
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, border_width=10)
        self.page_widget.pack_start(Gtk.Label(label="<b><big>FFmpeg Конвертація</big></b>", use_markup=True), False, False, 0)
        
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        self.page_widget.pack_start(grid, False, False, 0)

        grid.attach(Gtk.Label(label="Завдання FFmpeg:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.task_combo = Gtk.ComboBoxText()
        for label in FFMPEG_TASKS.keys():
            self.task_combo.append_text(label)
        self.task_combo.set_active(0) 
        self.task_combo.connect("changed", self._on_task_changed)
        grid.attach(self.task_combo, 1, 0, 3, 1)
        
        self.params_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        grid.attach(self.params_box, 0, 1, 4, 1) 
        
        grid.attach(Gtk.Label(label="Вхідний файл:", halign=Gtk.Align.END), 0, 2, 1, 1)
        self.input_entry = Gtk.Entry(hexpand=True)
        self.input_entry.connect("changed", self._update_output_suggestion) 
        grid.attach(self.input_entry, 1, 2, 2, 1)
        btn_in = Gtk.Button(label="...")
        btn_in.connect("clicked", lambda w: self._select_file_dialog(self.input_entry, "Оберіть вхідний файл"))
        grid.attach(btn_in, 3, 2, 1, 1)
        
        grid.attach(Gtk.Label(label="Вихідний файл:", halign=Gtk.Align.END), 0, 3, 1, 1)
        self.output_entry = Gtk.Entry(hexpand=True)
        grid.attach(self.output_entry, 1, 3, 2, 1)
        btn_out = Gtk.Button(label="...")
        btn_out.connect("clicked", lambda w: self._select_file_dialog(self.output_entry, "Оберіть вихідний файл", save_mode=True))
        grid.attach(btn_out, 3, 3, 1, 1)
        
        self.execute_button = Gtk.Button(label="Виконати")
        self.execute_button.connect("clicked", self._on_execute_clicked)
        self.page_widget.pack_start(self.execute_button, False, False, 5) 
        
        GLib.idle_add(self._on_task_changed, self.task_combo) 
        
        return self.page_widget

    def _on_task_changed(self, combo):
        selected_label = combo.get_active_text()
        if not selected_label: return
        task_info = FFMPEG_TASKS.get(selected_label)
        if not task_info: return

        if hasattr(self, 'params_box') and self.params_box:
             for widget in self.params_box.get_children():
                 self.params_box.remove(widget)
        
        self.param_entries = {} 
        if hasattr(self, 'params_box') and self.params_box:
             for param_spec in task_info.get("params", []):
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

    def _update_output_suggestion(self, *args):
        import os
        if not all([hasattr(self, w) and getattr(self, w) for w in ['input_entry', 'output_entry', 'task_combo']]): return
        
        input_path = self.input_entry.get_text().strip()
        output_path = self.output_entry.get_text().strip()
        active_task_label = self.task_combo.get_active_text()
        
        if not active_task_label: return 
        task_info = FFMPEG_TASKS.get(active_task_label)
        output_ext = task_info.get("output_ext", ".out") if task_info else ".out"
        
        update_needed = False
        suggested_path = ""
        
        if input_path and os.path.isfile(input_path):
            input_dir, base = os.path.dirname(input_path) or ".", os.path.splitext(os.path.basename(input_path))[0]
            suggested_path = os.path.join(input_dir, f"{base}_converted{output_ext}")
            if not output_path or os.path.dirname(output_path) == input_dir:
                update_needed = True
        elif not input_path and not output_path:
            suggested_path = os.path.join(os.path.expanduser("~"), f"output_converted{output_ext}")
            update_needed = True
            
        if update_needed and suggested_path:
            self.output_entry.set_text(suggested_path)

    def _on_execute_clicked(self, widget):
        import os
        if self.app._is_task_running:
            self.show_warning_dialog("Завдання вже виконується.")
            return
        try:
            active_task_label = self.task_combo.get_active_text()
            if not active_task_label: raise ValueError("Оберіть завдання FFmpeg.")
            
            task_info = FFMPEG_TASKS.get(active_task_label)
            if not task_info: raise ValueError("Обрано невідоме завдання FFmpeg.")
            
            task_type = task_info["type"]
            task_options = {}
            for spec in task_info.get("params", []):
                name = spec["name"]
                entry = self.param_entries.get(name)
                if entry:
                    value = entry.get_text().strip()
                    if not value and spec.get("required"):
                        raise ValueError(f"Параметр '{spec['label']}' є обов'язковим.")
                    task_options[name] = value
            
            input_path = self.input_entry.get_text().strip()
            output_path = self.output_entry.get_text().strip()
            
            if not input_path: raise ValueError("Оберіть вхідний файл.")
            if not os.path.isfile(input_path): raise ValueError(f"Вхідний файл не знайдено: {input_path}")
            if not output_path: raise ValueError("Вкажіть вихідний файл.")
            
            out_dir = os.path.dirname(output_path)
            if out_dir and not os.path.isdir(out_dir):
                os.makedirs(out_dir, exist_ok=True)
            
            if os.path.abspath(input_path) == os.path.abspath(output_path):
                raise ValueError("Вхідний та вихідний файли не можуть бути однаковими.")
            
            self._start_task(run_ffmpeg_task, args=(input_path, output_path), kwargs={'task_type': task_type, 'task_options': task_options})
        
        except (ValueError, RuntimeError, FileNotFoundError) as e:
            self.show_warning_dialog(str(e))
        except Exception as e:
            import traceback; traceback.print_exc()
            self.show_warning_dialog(f"Неочікувана помилка FFmpeg: {e}")

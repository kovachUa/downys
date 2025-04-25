import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango
import os
import json

class BookmarksPage:

    def __init__(self, app_window, url_handler):
        self.app = app_window 
        self.url_handler = url_handler 
        self.page_widget = None
        self.listbox = None
        self.url_entry = None
        self.name_entry = None
        self.bookmarks = []
        self.bookmarks_file = None 
        self.path_label = None 
        self._path_checked = False 
        print("DEBUG: BookmarksPage initialized (path will be requested on action).")

    def _prompt_for_path(self):
        """Показує діалог вибору/створення файлу закладок."""
        dialog = Gtk.FileChooserDialog(
            title="Виберіть або створіть файл для закладок (.json)",
            parent=self.app, 
            action=Gtk.FileChooserAction.SAVE
        )
        dialog.add_buttons(
            "_Скасувати", Gtk.ResponseType.CANCEL,
            "_Обрати", Gtk.ResponseType.OK
        )
        dialog.set_do_overwrite_confirmation(False)

        filter_json = Gtk.FileFilter()
        filter_json.set_name("JSON файли")
        filter_json.add_mime_type("application/json")
        filter_json.add_pattern("*.json")
        dialog.add_filter(filter_json)
        filter_any = Gtk.FileFilter()
        filter_any.set_name("Всі файли")
        filter_any.add_pattern("*")
        dialog.add_filter(filter_any)

        default_dir = os.path.join(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS) or GLib.get_home_dir(), "DownYS_Bookmarks")
        default_name = "bookmarks.json"
        try:
            os.makedirs(default_dir, exist_ok=True)
            if os.path.isdir(default_dir):
                 dialog.set_current_folder(default_dir)
            else:
                 dialog.set_current_folder(os.path.expanduser("~"))
        except Exception as e:
             print(f"Warning setting default folder in prompt: {e}")
             dialog.set_current_folder(os.path.expanduser("~"))
        dialog.set_current_name(default_name)

        response = dialog.run()
        chosen_path = None
        if response == Gtk.ResponseType.OK:
            chosen_path = dialog.get_filename()
            if chosen_path and not chosen_path.lower().endswith(".json"):
                chosen_path += ".json"
        dialog.destroy()
        return chosen_path

    def _update_path_label(self):
        """Оновлює текст мітки шляху."""
        if not self.path_label:
            return
        if self.bookmarks_file:
            try:
                 path_markup = f"<small>Файл закладок: {GLib.markup_escape_text(self.bookmarks_file)}</small>"
                 self.path_label.set_markup(path_markup)
                 self.path_label.set_tooltip_text(self.bookmarks_file)
            except Exception as e:
                 print(f"Error updating path label: {e}")
                 self.path_label.set_text("Помилка відображення шляху")
        else:
             self.path_label.set_markup("<small>Файл закладок: <i>Не обрано</i></small>")
             self.path_label.set_tooltip_text("Натисніть 'Додати' або 'Видалити', щоб обрати файл")

    def _ensure_bookmarks_path(self):
        """Перевіряє, чи встановлено шлях, і запитує користувача, якщо ні."""
        if self.bookmarks_file and os.path.exists(os.path.dirname(self.bookmarks_file)):
            self._path_checked = True
            return True

        if self._path_checked:
             if not self.bookmarks_file:
                  self.app.show_warning_dialog("Неможливо виконати дію: файл закладок не обрано.")
             else:
                  self.app.show_warning_dialog(f"Неможливо виконати дію: папка для файлу закладок недоступна:\n{os.path.dirname(self.bookmarks_file)}")
             return False

        print("DEBUG: Bookmarks file path is not set or invalid. Prompting user.")
        chosen_path = self._prompt_for_path()
        self._path_checked = True

        if chosen_path:
            try:
                os.makedirs(os.path.dirname(chosen_path), exist_ok=True)
                self.bookmarks_file = chosen_path
                print(f"DEBUG: User selected bookmarks file: {self.bookmarks_file}")
                self._update_path_label()
                self.load_bookmarks()
                self.populate_listbox()
                return True
            except OSError as e:
                 print(f"ERROR: Could not create directory for chosen path '{chosen_path}': {e}")
                 self.app.show_warning_dialog(f"Не вдалося створити папку для файлу:\n{os.path.dirname(chosen_path)}\n\nПомилка: {e}")
                 self.bookmarks_file = None
                 self._update_path_label()
                 return False
        else:
            print("DEBUG: User cancelled bookmarks file selection.")
            self.bookmarks_file = None
            self._update_path_label()
            self.app.show_warning_dialog("Файл закладок не обрано. Збереження та завантаження неможливе.")
            return False

    def build_ui(self):
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, border_width=10)
        self.page_widget.pack_start(Gtk.Label(label="<b><big>Закладки</big></b>", use_markup=True), False, False, 5)

        scrolled_window = Gtk.ScrolledWindow(shadow_type=Gtk.ShadowType.IN, hexpand=True, vexpand=True)
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-activated", self._on_bookmark_activated)
        scrolled_window.add(self.listbox)
        self.page_widget.pack_start(scrolled_window, True, True, 0)

        hbox_buttons = Gtk.Box(spacing=6)
        btn_remove = Gtk.Button(label="Видалити Вибране")
        btn_remove.connect("clicked", self._on_remove_clicked)
        hbox_buttons.pack_end(btn_remove, False, False, 0)
        self.page_widget.pack_start(hbox_buttons, False, False, 5)

        grid = Gtk.Grid(column_spacing=10, row_spacing=5)
        grid.attach(Gtk.Label(label="URL:", halign=Gtk.Align.END), 0, 0, 1, 1)
        self.url_entry = Gtk.Entry(hexpand=True)
        self.url_entry.connect("activate", self._on_add_clicked)
        grid.attach(self.url_entry, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="Назва:", halign=Gtk.Align.END), 0, 1, 1, 1)
        self.name_entry = Gtk.Entry(hexpand=True)
        self.name_entry.connect("activate", self._on_add_clicked)
        grid.attach(self.name_entry, 1, 1, 1, 1)
        btn_add = Gtk.Button(label="Додати Закладку")
        btn_add.connect("clicked", self._on_add_clicked)
        grid.attach(btn_add, 0, 2, 2, 1)
        self.page_widget.pack_start(grid, False, False, 5)

        self.path_label = Gtk.Label(xalign=0.0, selectable=True)
        self.path_label.set_line_wrap(True)
        self.path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.path_label.set_margin_top(10)
        self._update_path_label()
        self.page_widget.pack_start(self.path_label, False, False, 0)

        self.populate_listbox()
        self.page_widget.show_all()

        return self.page_widget

    def load_bookmarks(self):
        if not self.bookmarks_file:
            print("DEBUG: load_bookmarks called but path is not set.")
            self.bookmarks = []
            return

        if not os.path.exists(self.bookmarks_file):
            print(f"DEBUG: Bookmarks file '{self.bookmarks_file}' not found. Starting with empty list.")
            self.bookmarks = []
            return

        print(f"DEBUG: Loading bookmarks from: {self.bookmarks_file}")
        self.bookmarks = []
        try:
            with open(self.bookmarks_file, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            if isinstance(loaded_data, list):
                self.bookmarks = [bm for bm in loaded_data if isinstance(bm, dict) and 'url' in bm]
                print(f"DEBUG: Loaded and validated bookmarks: {len(self.bookmarks)} items")
            else:
                print(f"Warning: Bookmarks file content is not a list: {type(loaded_data)}. Resetting.")
                self.bookmarks = []
                self.app.show_warning_dialog(f"Файл закладок має невірний формат (очікується список):\n{self.bookmarks_file}")

        except (json.JSONDecodeError, OSError, TypeError) as e:
            print(f"Помилка завантаження або валідації закладок з '{self.bookmarks_file}': {e}")
            self.bookmarks = []
            self.app.show_warning_dialog(f"Не вдалося завантажити закладки з файлу:\n{self.bookmarks_file}\n\nПомилка: {e}\n\nСписок буде порожнім.")
        except Exception as e:
            print(f"Неочікувана помилка при завантаженні закладок: {e}")
            self.bookmarks = []
            self.app.show_warning_dialog(f"Неочікувана помилка при завантаженні закладок:\n{e}")


    def save_bookmarks(self):
        if not self._ensure_bookmarks_path():
             return

        if not self.bookmarks_file:
             print("CRITICAL ERROR: save_bookmarks called but self.bookmarks_file is still None after check!")
             self.app.show_warning_dialog("Критична помилка: Неможливо зберегти закладки (шлях не встановлено).")
             return

        print(f"DEBUG: Saving {len(self.bookmarks)} bookmarks to {self.bookmarks_file}")
        try:
            os.makedirs(os.path.dirname(self.bookmarks_file), exist_ok=True)
            with open(self.bookmarks_file, 'w', encoding='utf-8') as f:
                json.dump(self.bookmarks, f, indent=2, ensure_ascii=False)
            print(f"DEBUG: Save successful.")
        except OSError as e:
            print(f"Помилка збереження закладок у файл '{self.bookmarks_file}': {e}")
            self.app.show_warning_dialog(f"Не вдалося зберегти закладки:\n{e}")
        except Exception as e:
             print(f"Неочікувана помилка при збереженні закладок: {e}")
             self.app.show_warning_dialog(f"Неочікувана помилка при збереженні закладок:\n{e}")

    def populate_listbox(self):
        print(f"DEBUG: Populating listbox. Have {len(self.bookmarks)} bookmarks.")
        if not hasattr(self, 'listbox') or not self.listbox:
             print("Warning: populate_listbox called before listbox is created.")
             return
        for child in self.listbox.get_children():
            self.listbox.remove(child)

        if not self.bookmarks:
             print("DEBUG: No bookmarks to display.")
             # Можна додати мітку "Немає закладок"
             # placeholder_row = Gtk.ListBoxRow()
             # placeholder_label = Gtk.Label(label="<i>Немає збережених закладок</i>", use_markup=True, margin=10, halign=Gtk.Align.CENTER)
             # placeholder_row.add(placeholder_label)
             # placeholder_row.set_selectable(False)
             # self.listbox.add(placeholder_row)
             self.listbox.show_all()
             return

        display_list = []
        for i, bm in enumerate(self.bookmarks):
            if not isinstance(bm, dict):
                print(f"WARNING: Skipping invalid bookmark item at index {i}: {bm}")
                continue
            sort_key = bm.get('name', '').lower()
            display_list.append((sort_key, i, bm))

        try:
            display_list.sort(key=lambda item: item[0])
        except Exception as e:
            print(f"ERROR: Failed to sort bookmarks for display: {e}")
            pass

        for sort_key, original_index, bm_data in display_list:
            name = bm_data.get('name', 'Без назви')
            url = bm_data.get('url', 'Немає URL')
            label_text = f"<b>{name}</b>\n<small>{url}</small>"
            try:
                label = Gtk.Label(xalign=0, wrap=True, ellipsize=Pango.EllipsizeMode.END)
                label.set_markup(label_text)
                row = Gtk.ListBoxRow()
                row.add(label)
                row.bookmark_index = original_index
                self.listbox.add(row)
            except Exception as e:
                print(f"ERROR: Failed to create or add row for bookmark (Index: {original_index}, Data: {bm_data}): {e}")

        self.listbox.show_all()
        print(f"DEBUG: Listbox population finished. Added {len(self.listbox.get_children())} rows.")

    def _on_add_clicked(self, widget):
        if not self._ensure_bookmarks_path():
            return

        url = self.url_entry.get_text().strip()
        name = self.name_entry.get_text().strip()
        if not url:
            self.app.show_warning_dialog("URL закладки не може бути порожнім.")
            return
        if not name: name = url
        if any(isinstance(b, dict) and b.get('url') == url for b in self.bookmarks):
             print(f"DEBUG: Bookmark with URL '{url}' already exists.")
        new_bookmark = {'name': name, 'url': url}
        print(f"DEBUG: Adding bookmark: {new_bookmark}")
        self.bookmarks.append(new_bookmark)
        self.save_bookmarks()
        self.populate_listbox()
        if hasattr(self, 'url_entry') and self.url_entry: self.url_entry.set_text("")
        if hasattr(self, 'name_entry') and self.name_entry: self.name_entry.set_text("")


    def _on_remove_clicked(self, widget):
        if not self._ensure_bookmarks_path():
            return

        selected_row = self.listbox.get_selected_row()
        if selected_row and hasattr(selected_row, 'bookmark_index'):
            index_to_remove = selected_row.bookmark_index
            print(f"DEBUG: Attempting to remove bookmark at original index: {index_to_remove}")
            if 0 <= index_to_remove < len(self.bookmarks):
                removed_item = self.bookmarks.pop(index_to_remove)
                print(f"DEBUG: Removed bookmark: {removed_item}")
                self.save_bookmarks()
                self.populate_listbox()
            else:
                print(f"ERROR: Invalid bookmark index {index_to_remove} for removal. Current bookmark count: {len(self.bookmarks)}")
                self.app.show_warning_dialog("Помилка: Не вдалося видалити закладку (некоректний індекс).")
                self.populate_listbox()
        else:
             if self.bookmarks_file:
                self.app.show_warning_dialog("Будь ласка, виберіть закладку для видалення.")

    def _on_bookmark_activated(self, listbox, row):
        if not self.bookmarks:
             print("DEBUG: Bookmark activated, but list is empty.")
             return

        if hasattr(row, 'bookmark_index'):
            index = row.bookmark_index
            print(f"DEBUG: Bookmark activated at original index: {index}")
            if 0 <= index < len(self.bookmarks):
                bookmark = self.bookmarks[index]
                if not isinstance(bookmark, dict):
                    print(f"ERROR: Activated bookmark at index {index} is not a dictionary: {bookmark}")
                    self.app.show_warning_dialog("Помилка: Обрана закладка має некоректний формат.")
                    return

                url = bookmark.get('url')
                print(f"DEBUG: Activating URL: {url}")
                if url:
                    page_target = "youtube"
                    if "youtube.com" in url or "youtu.be" in url: page_target = "youtube"
                    elif url.startswith("http://") or url.startswith("https://"): page_target = "httrack"
                    else: print(f"DEBUG: Unknown URL type for activation: {url}. Defaulting to YouTube page.")
                    self.app.go_to_page_with_url(page_target, url)
                else: self.app.show_warning_dialog("У цій закладці немає URL.")
            else:
                print(f"ERROR: Invalid bookmark index {index} upon activation. Current bookmark count: {len(self.bookmarks)}")
                self.app.show_warning_dialog("Помилка: Не вдалося активувати закладку (некоректний індекс).")

    def get_page_widget(self):
         return self.page_widget

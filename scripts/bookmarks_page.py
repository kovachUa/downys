# --- START OF FILE bookmarks_page.py ---

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
        self.path_label = None


        try:
            docs_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS)
            if not docs_dir: 
                 docs_dir = GLib.get_home_dir()
            self.default_bookmarks_dir = os.path.join(docs_dir, "DownYS_Bookmarks")
        except Exception: 
             self.default_bookmarks_dir = os.path.join(GLib.get_home_dir(), "DownYS_Bookmarks")

        self.bookmarks_file = os.path.join(self.default_bookmarks_dir, "bookmarks.json")
        print(f"DEBUG: Bookmarks will be loaded/saved to: {self.bookmarks_file}")

        self._initialize_bookmarks() # Завантажуємо закладки при старті

    def _initialize_bookmarks(self):
        """Створює директорію (якщо потрібно) та завантажує закладки."""
        try:
            os.makedirs(self.default_bookmarks_dir, exist_ok=True)
            print(f"DEBUG: Ensured bookmarks directory exists: {self.default_bookmarks_dir}")
            self.load_bookmarks()
        except OSError as e:
            print(f"ERROR: Could not create or access bookmarks directory '{self.default_bookmarks_dir}': {e}")
            self.app.show_warning_dialog(
                f"Не вдалося створити або отримати доступ до папки закладок:\n{self.default_bookmarks_dir}\n\nПомилка: {e}\n\nЗбереження/завантаження може не працювати."
            )
            self.bookmarks = [] 
        except Exception as e:
             print(f"ERROR: Unexpected error during bookmark initialization: {e}")
             self.app.show_warning_dialog(f"Неочікувана помилка ініціалізації закладок:\n{e}")
             self.bookmarks = []


    def _update_path_label(self):
        """Оновлює текст мітки шляху, показуючи стандартний шлях."""
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
             self.path_label.set_markup("<small>Файл закладок: <i>Не вдалося визначити</i></small>")
             self.path_label.set_tooltip_text("Помилка визначення шляху до файлу закладок")


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
            print("ERROR: load_bookmarks called but bookmarks_file is not set!")
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
        if not self.bookmarks_file:
             print("ERROR: Cannot save bookmarks, file path is not set.")
             self.app.show_warning_dialog("Помилка: Неможливо зберегти закладки (шлях не встановлено).")
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

        # Очищення старого списку
        for child in self.listbox.get_children():
            self.listbox.remove(child)

        if not self.bookmarks: # Якщо список порожній або став None через помилку
             print("DEBUG: No bookmarks to display.")
             # Можна додати мітку "Немає закладок" якщо бажано
             placeholder_row = Gtk.ListBoxRow()
             placeholder_label = Gtk.Label(label="<i>Немає збережених закладок</i>", use_markup=True, margin=10, halign=Gtk.Align.CENTER)
             placeholder_row.add(placeholder_label)
             placeholder_row.set_selectable(False) 
             self.listbox.add(placeholder_row)
             self.listbox.show_all()
             return

        display_list = []
        for i, bm in enumerate(self.bookmarks):
            if not isinstance(bm, dict): 
                print(f"WARNING: Skipping invalid bookmark item at index {i}: {bm}")
                continue
            sort_key_name = bm.get('name', '').lower()
            sort_key_url = bm.get('url', '').lower()
            display_list.append(((sort_key_name, sort_key_url), i, bm))

        try:
            display_list.sort(key=lambda item: item[0]) 
        except Exception as e:
            print(f"ERROR: Failed to sort bookmarks for display: {e}")
            display_list = [(None, i, bm) for i, bm in enumerate(self.bookmarks) if isinstance(bm, dict)]
            pass

        for sort_key, original_index, bm_data in display_list:
            name = bm_data.get('name', 'Без назви')
            url = bm_data.get('url', 'Немає URL')
            label_text = f"<b>{GLib.markup_escape_text(name)}</b>\n<small>{GLib.markup_escape_text(url)}</small>"
            try:
                label = Gtk.Label(xalign=0, wrap=True, ellipsize=Pango.EllipsizeMode.END)
                label.set_markup(label_text)
                row = Gtk.ListBoxRow()
                row.add(label)
                row.bookmark_index = original_index
                self.listbox.add(row)
            except Exception as e:
                print(f"ERROR: Failed to create or add row for bookmark (Index: {original_index}, Data: {bm_data}): {e}")
                try:
                    fallback_text = f"{name}\n{url}"
                    label = Gtk.Label(fallback_text, xalign=0, wrap=True, ellipsize=Pango.EllipsizeMode.END)
                    row = Gtk.ListBoxRow()
                    row.add(label)
                    row.bookmark_index = original_index
                    self.listbox.add(row)
                except Exception as fallback_e:
                    print(f"ERROR: Failed to create fallback row: {fallback_e}")


        self.listbox.show_all()
        print(f"DEBUG: Listbox population finished. Added {len(self.listbox.get_children())} rows (excluding placeholder if used).")


    def _on_add_clicked(self, widget):
        url = self.url_entry.get_text().strip()
        name = self.name_entry.get_text().strip()

        if not url:
            self.app.show_warning_dialog("URL закладки не може бути порожнім.")
            return

        if not (url.startswith("http://") or url.startswith("https://") or "youtube.com" in url or "youtu.be" in url):
             print(f"Warning: Adding bookmark with potentially non-standard URL scheme: {url}")


        if not name:
            try:
                 hostname = self.url_handler.get_hostname_from_url(url, sanitize=False)
                 name = hostname if hostname else url # Використовуємо хост або весь URL
            except Exception:
                 name = url 

        is_duplicate = False
        for i, bm in enumerate(self.bookmarks):
            if isinstance(bm, dict) and bm.get('url') == url:
                print(f"DEBUG: Bookmark with URL '{url}' already exists at index {i}.")
                is_duplicate = True
                self.app.show_info_dialog("Інформація", f"Закладка з URL:\n{url}\nвже існує.")
                break 

        if not is_duplicate:
            new_bookmark = {'name': name, 'url': url}
            print(f"DEBUG: Adding bookmark: {new_bookmark}")
            self.bookmarks.append(new_bookmark)
            self.save_bookmarks()
            self.populate_listbox() 

            if hasattr(self, 'url_entry') and self.url_entry: self.url_entry.set_text("")
            if hasattr(self, 'name_entry') and self.name_entry: self.name_entry.set_text("")


    def _on_remove_clicked(self, widget):
        selected_row = self.listbox.get_selected_row()

        if not selected_row:
             self.app.show_warning_dialog("Будь ласка, виберіть закладку для видалення.")
             return

        if not hasattr(selected_row, 'bookmark_index'):
             print("DEBUG: Tried to remove the placeholder row or an invalid row.")
             return

        index_to_remove = selected_row.bookmark_index
        print(f"DEBUG: Attempting to remove bookmark at original index: {index_to_remove}")

        if 0 <= index_to_remove < len(self.bookmarks):
            removed_item = self.bookmarks.pop(index_to_remove)
            print(f"DEBUG: Removed bookmark: {removed_item}")
            self.save_bookmarks() # Зберігаємо зміни
            self.populate_listbox() # Оновлюємо UI
        else:
            print(f"ERROR: Invalid bookmark index {index_to_remove} for removal. Current bookmark count: {len(self.bookmarks)}")
            self.app.show_warning_dialog("Помилка: Не вдалося видалити закладку (некоректний індекс). Спробуйте оновити список.")
            self.populate_listbox()


    def _on_bookmark_activated(self, listbox, row):
        if not hasattr(row, 'bookmark_index'):
             print("DEBUG: Activated the placeholder row or an invalid row.")
             return

        index = row.bookmark_index
        print(f"DEBUG: Bookmark activated at original index: {index}")

        # Валідація індексу та типу даних
        if 0 <= index < len(self.bookmarks) and isinstance(self.bookmarks[index], dict):
            bookmark = self.bookmarks[index]
            url = bookmark.get('url')
            print(f"DEBUG: Activating URL: {url}")

            if url:
                page_target = None
                try:
                    lower_url = url.lower()
                    if "youtube.com" in lower_url or "youtu.be" in lower_url:
                        page_target = "youtube"
                    elif lower_url.startswith("http://") or lower_url.startswith("https://") or lower_url.startswith("ftp://"):
                         is_youtube = False
                         try:
                              parsed = self.url_handler.urlparse(url)
                              if parsed.hostname and ('youtube.com' in parsed.hostname or 'youtu.be' in parsed.hostname):
                                   is_youtube = True
                         except Exception: pass 
                         if not is_youtube:
                              page_target = "httrack"

                    if not page_target and (lower_url.startswith("http://") or lower_url.startswith("https://")):
                        page_target = "httrack"
                        print(f"DEBUG: URL '{url}' doesn't look like YouTube, trying HTTrack page.")
                    elif not page_target:
                         print(f"DEBUG: Unknown URL type for activation: {url}. Cannot determine target page.")
                         self.app.show_warning_dialog(f"Не вдалося визначити тип посилання для URL:\n{url}\n\nВідкрийте його вручну на відповідній вкладці.")

                except Exception as e:
                     print(f"ERROR determining page target for url '{url}': {e}")
                     self.app.show_warning_dialog(f"Помилка визначення типу посилання:\n{e}")

                if page_target:
                    self.app.go_to_page_with_url(page_target, url)

            else:
                self.app.show_warning_dialog("У цій закладці немає URL.")
        else:
            print(f"ERROR: Invalid bookmark index ({index}) or data type upon activation. Current bookmark count: {len(self.bookmarks)}")
            self.app.show_warning_dialog("Помилка: Не вдалося активувати закладку (некоректний індекс або формат даних).")
            self.populate_listbox()


    def get_page_widget(self):
         return self.page_widget


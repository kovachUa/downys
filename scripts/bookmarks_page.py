import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango
import os
import json
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

BOOKMARK_CATEGORIES = {
    "youtube": "YouTube",
    "httrack": "HTTrack / Веб-сайт",
    "other": "Інше"
}

class BookmarksPage:
    def __init__(self, app_window, url_handler):
        self.app = app_window
        self.url_handler = url_handler
        self.page_widget = None
        
        # --- НОВЕ: Замість одного списку - словник зі списками та стек ---
        self.stack = None
        self.listboxes = {} # {'youtube': Gtk.ListBox, 'httrack': Gtk.ListBox, ...}

        self.url_entry = None
        self.name_entry = None
        self.category_combo = None
        self.desc_view = None 
        self.desc_buffer = None
        
        self.save_button = None
        self.cancel_edit_button = None
        self.editing_bookmark_index = None

        self.bookmarks = []
        self.path_label = None

        try:
            docs_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS)
            docs_dir = docs_dir or GLib.get_home_dir()
            self.default_bookmarks_dir = os.path.join(docs_dir, "DownYS_Bookmarks")
        except Exception: 
             self.default_bookmarks_dir = os.path.join(GLib.get_home_dir(), "DownYS_Bookmarks")

        self.bookmarks_file = os.path.join(self.default_bookmarks_dir, "bookmarks.json")
        self._initialize_bookmarks()

    def _initialize_bookmarks(self):
        try:
            os.makedirs(self.default_bookmarks_dir, exist_ok=True)
            self.load_bookmarks()
        except Exception as e:
            logger.exception(f"Unexpected error during bookmark initialization: {e}")
            self.bookmarks = []

    def build_ui(self):
        self.page_widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, border_width=10)
        self.page_widget.pack_start(Gtk.Label(label="<b><big>Закладки</big></b>", use_markup=True), False, False, 5)

        # --- НОВЕ: Створення Gtk.Stack та перемикача ---
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        stack_switcher = Gtk.StackSwitcher(stack=self.stack, halign=Gtk.Align.CENTER)
        self.page_widget.pack_start(stack_switcher, False, False, 0)
        
        for key, name in BOOKMARK_CATEGORIES.items():
            scrolled_window = Gtk.ScrolledWindow(shadow_type=Gtk.ShadowType.IN, hexpand=True, vexpand=True)
            listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
            listbox.connect("row-activated", self._on_bookmark_activated)
            
            self.listboxes[key] = listbox # Зберігаємо віджет списку
            scrolled_window.add(listbox)
            self.stack.add_titled(scrolled_window, key, name)

        self.page_widget.pack_start(self.stack, True, True, 5)
        # --- КІНЕЦЬ НОВОГО БЛОКУ ---

        hbox_buttons = Gtk.Box(spacing=6)
        btn_edit = Gtk.Button(label="Редагувати Вибране")
        btn_edit.connect("clicked", self._on_edit_clicked)
        hbox_buttons.pack_start(btn_edit, False, False, 0)
        btn_remove = Gtk.Button(label="Видалити Вибране")
        btn_remove.connect("clicked", self._on_remove_clicked)
        hbox_buttons.pack_start(btn_remove, False, False, 0)
        self.page_widget.pack_start(hbox_buttons, False, False, 5)

        # ... (Код форми для додавання/редагування залишається без змін)
        grid = Gtk.Grid(column_spacing=10, row_spacing=5)
        grid.attach(Gtk.Label(label="URL:", halign=Gtk.Align.END), 0, 0, 1, 1); self.url_entry = Gtk.Entry(hexpand=True); grid.attach(self.url_entry, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="Назва:", halign=Gtk.Align.END), 0, 1, 1, 1); self.name_entry = Gtk.Entry(hexpand=True); grid.attach(self.name_entry, 1, 1, 1, 1)
        grid.attach(Gtk.Label(label="Категорія:", halign=Gtk.Align.END), 0, 2, 1, 1); self.category_combo = Gtk.ComboBoxText(); grid.attach(self.category_combo, 1, 2, 1, 1)
        for key, value in BOOKMARK_CATEGORIES.items(): self.category_combo.append(key, value)
        grid.attach(Gtk.Label(label="Опис:", halign=Gtk.Align.START), 0, 3, 1, 1)
        scrolled_desc = Gtk.ScrolledWindow(shadow_type=Gtk.ShadowType.IN, min_content_height=60)
        self.desc_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR); self.desc_buffer = self.desc_view.get_buffer()
        self.desc_buffer.connect("changed", self._on_desc_buffer_changed)
        scrolled_desc.add(self.desc_view); grid.attach(scrolled_desc, 1, 3, 1, 1)
        self.save_button = Gtk.Button(); self.save_button.connect("clicked", self._on_save_clicked)
        self.cancel_edit_button = Gtk.Button(label="Скасувати Редагування"); self.cancel_edit_button.connect("clicked", self._on_cancel_edit_clicked)
        self.cancel_edit_button.set_no_show_all(True)
        hbox_form_buttons = Gtk.Box(spacing=6)
        hbox_form_buttons.pack_start(self.save_button, True, True, 0); hbox_form_buttons.pack_start(self.cancel_edit_button, True, True, 0)
        grid.attach(hbox_form_buttons, 0, 4, 2, 1)
        self.page_widget.pack_start(grid, False, False, 5)

        self.path_label = Gtk.Label(xalign=0.0, selectable=True, ellipsize=Pango.EllipsizeMode.MIDDLE, margin_top=10)
        self.path_label.set_line_wrap(True)
        self._update_path_label()
        self.page_widget.pack_start(self.path_label, False, False, 0)
        
        self._set_add_mode()
        self.populate_listbox()
        self.page_widget.show_all()
        return self.page_widget
        
    def _set_add_mode(self):
        self.editing_bookmark_index = None
        self.url_entry.set_text(""); self.name_entry.set_text(""); self.desc_buffer.set_text("", -1)
        self.category_combo.set_active_id("httrack")
        self.save_button.set_label("Додати Закладку"); self.cancel_edit_button.hide()

    def _set_edit_mode(self, bookmark, index):
        self.editing_bookmark_index = index
        self.url_entry.set_text(bookmark.get('url', '')); self.name_entry.set_text(bookmark.get('name', ''))
        self.desc_buffer.set_text(bookmark.get('description', ''), -1)
        self.category_combo.set_active_id(bookmark.get('category', 'other'))
        self.save_button.set_label("Зберегти Зміни"); self.cancel_edit_button.show()
    
    def _get_current_listbox(self):
        """Допоміжна функція для отримання активного на даний момент списку."""
        visible_child_name = self.stack.get_visible_child_name()
        return self.listboxes.get(visible_child_name)

    def load_bookmarks(self):
        # ... (код завантаження та міграції залишається без змін) ...
        if not os.path.exists(self.bookmarks_file): self.bookmarks = []; return
        try:
            with open(self.bookmarks_file, 'r', encoding='utf-8') as f: data = json.load(f)
            self.bookmarks = []
            for bm in data:
                if not isinstance(bm, dict) or 'url' not in bm: continue
                if 'description' not in bm: bm['description'] = ''
                if 'category' not in bm:
                    bm['category'] = 'youtube' if any(s in bm['url'].lower() for s in ["youtube.com", "youtu.be"]) else 'httrack'
                self.bookmarks.append(bm)
        except (json.JSONDecodeError, OSError) as e: self.bookmarks = []; logger.error(f"Error loading bookmarks: {e}")

    def save_bookmarks(self):
        # ... (код збереження залишається без змін) ...
        try:
            os.makedirs(os.path.dirname(self.bookmarks_file), exist_ok=True)
            with open(self.bookmarks_file, 'w', encoding='utf-8') as f: json.dump(self.bookmarks, f, indent=2, ensure_ascii=False)
        except OSError as e: logger.error(f"Error saving bookmarks: {e}")

    def populate_listbox(self):
        # --- ПЕРЕПИСАНО: Заповнення окремих списків для кожної вкладки ---
        for listbox in self.listboxes.values():
            for child in listbox.get_children(): listbox.remove(child)

        grouped = defaultdict(list)
        for i, bm in enumerate(self.bookmarks):
            grouped[bm.get('category', 'other')].append((i, bm))
        
        for cat_key, listbox in self.listboxes.items():
            if cat_key in grouped:
                sorted_group = sorted(grouped[cat_key], key=lambda item: item[1].get('name', '').lower())
                for idx, data in sorted_group:
                    name, url, desc = data.get('name'), data.get('url'), data.get('description')
                    markup = f"<b>{GLib.markup_escape_text(name)}</b>\n<small>{GLib.markup_escape_text(url)}</small>"
                    if desc: markup += f"\n<i><small>{GLib.markup_escape_text(desc)}</small></i>"
                    
                    label = Gtk.Label(xalign=0, wrap=True); label.set_markup(markup)
                    row = Gtk.ListBoxRow(); row.add(label)
                    row.bookmark_index = idx
                    listbox.add(row)
            else: # Якщо в категорії немає закладок
                row = Gtk.ListBoxRow()
                row.add(Gtk.Label(label="<i>Немає закладок у цій категорії</i>", use_markup=True, margin=10))
                row.set_selectable(False)
                listbox.add(row)
            listbox.show_all()

    def _on_save_clicked(self, widget):
        # ... (код збереження залишається майже без змін) ...
        url = self.url_entry.get_text().strip()
        if not url: self.app.show_warning_dialog("URL не може бути порожнім."); return
        name = self.name_entry.get_text().strip() or self.url_handler.get_hostname_from_url(url, sanitize=False) or url
        category, description = self.category_combo.get_active_id(), self.desc_buffer.get_text(self.desc_buffer.get_start_iter(), self.desc_buffer.get_end_iter(), False).strip()

        if self.editing_bookmark_index is not None:
            self.bookmarks[self.editing_bookmark_index] = {'name': name, 'url': url, 'category': category, 'description': description}
        else:
            if any(bm.get('url') == url for bm in self.bookmarks): self.app.show_info_dialog("Інформація", f"Закладка з URL:\n{url}\nвже існує."); return
            self.bookmarks.append({'name': name, 'url': url, 'category': category, 'description': description})

        self.save_bookmarks()
        self.populate_listbox()
        self._set_add_mode()

    def _on_edit_clicked(self, widget):
        # --- ЗМІНЕНО: Використання активного списку ---
        active_listbox = self._get_current_listbox()
        if not active_listbox: return
        
        selected_row = active_listbox.get_selected_row()
        if not selected_row or not hasattr(selected_row, 'bookmark_index'): self.app.show_warning_dialog("Будь ласка, виберіть закладку для редагування."); return
        
        index = selected_row.bookmark_index
        if 0 <= index < len(self.bookmarks): self._set_edit_mode(self.bookmarks[index], index)
    
    def _on_remove_clicked(self, widget):
        # --- ЗМІНЕНО: Використання активного списку ---
        active_listbox = self._get_current_listbox()
        if not active_listbox: return
        
        selected_row = active_listbox.get_selected_row()
        if not selected_row or not hasattr(selected_row, 'bookmark_index'): self.app.show_warning_dialog("Будь ласка, виберіть закладку для видалення."); return
        
        index_to_remove = selected_row.bookmark_index
        if 0 <= index_to_remove < len(self.bookmarks):
            self.bookmarks.pop(index_to_remove)
            self.save_bookmarks(); self.populate_listbox(); self._set_add_mode()
        else: logger.error(f"Invalid bookmark index {index_to_remove} for removal.")
    
    # Інші методи залишаються без змін, оскільки вони не залежать від конкретного віджета списку
    def _on_cancel_edit_clicked(self, widget): self._set_add_mode()
    def _on_bookmark_activated(self, listbox, row):
        if not hasattr(row, 'bookmark_index'): return
        index = row.bookmark_index
        if 0 <= index < len(self.bookmarks):
            bookmark = self.bookmarks[index]
            url, category = bookmark.get('url'), bookmark.get('category')
            if not url: return
            page_target = category if category in ["youtube", "httrack"] else None
            if page_target: self.app.go_to_page_with_url(page_target, url)
            else: self.app.show_info_dialog("Інформація", f"Це закладка загального призначення.\nURL: {url}")
    def get_page_widget(self): return self.page_widget
    def _update_path_label(self):
        if not self.path_label: return
        self.path_label.set_markup(f"<small>Файл закладок: {GLib.markup_escape_text(self.bookmarks_file)}</small>")
        self.path_label.set_tooltip_text(self.bookmarks_file)
    def _on_desc_buffer_changed(self, buffer):
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        if len(text) > 200: GLib.idle_add(self._trim_description, buffer)
    def _trim_description(self, buffer):
        end_iter = buffer.get_iter_at_offset(200); buffer.delete(end_iter, buffer.get_end_iter())

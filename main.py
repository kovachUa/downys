# main.py

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import os
import sys
import threading
import subprocess
from urllib.parse import urlparse, parse_qs

# --- Імпорт сторінок з нової директорії UI ---
from  ui.youtube_page import YouTubePage
from  ui.ffmpeg_page import FFmpegPage
from  ui.httrack_page import HTTrackPage
from  ui.about_page import AboutPage
from  scripts.bookmarks_page import BookmarksPage

# --- Імпорт функцій-виконавців ---
from scripts.youtube import download_youtube_media
from scripts.ffmpeg_tasks import run_ffmpeg_task
from scripts.httrack_tasks import run_httrack_web_threaded, archive_directory_threaded

class URLHandler:
    def is_youtube_playlist(self, url_string: str) -> bool:
        try:
            parsed_url = urlparse(url_string)
            if 'youtube.com' in (parsed_url.hostname or ""):
                query_params = parse_qs(parsed_url.query)
                return 'list' in query_params
        except Exception:
            return False
        return False

    def validate_httrack_url(self, url_string):
        if not url_string:
            raise ValueError("URL не може бути порожнім.")
        try:
            parsed_url = urlparse(url_string)
            allowed_schemes = ('http', 'https', 'ftp')
            if not parsed_url.scheme or parsed_url.scheme.lower() not in allowed_schemes:
                raise ValueError(f"Непідтримувана схема URL (очікується {', '.join(allowed_schemes)}).")
            if not parsed_url.netloc: 
                raise ValueError("Відсутнє ім'я хоста (домен) в URL.")
            return True
        except ValueError as e: 
             raise ValueError(f"Неприпустимий URL: {e}")
        except Exception as e: 
             raise ValueError(f"Не вдалося проаналізувати URL '{url_string}': {e}")

    def get_hostname_from_url(self, url_string, sanitize=True):
        if not url_string: return None
        try:
            parsed_url = urlparse(url_string)
            hostname = parsed_url.hostname
            if hostname:
                if hostname.startswith("www."): hostname = hostname[4:]
                if sanitize:
                    hostname = re.sub(r'[^\w.-]+', '_', hostname).strip('_')
                    if not hostname: return None
                return hostname
            return None 
        except Exception as e:
            print(f"Warning: Could not parse URL '{url_string}' for hostname: {e}")
            return None

class AppWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="DownYS", default_width=800, default_height=750)
        self.connect("destroy", Gtk.main_quit)
        
        self._is_task_running = False
        self._current_task_thread = None
        self.url_handler = URLHandler()

        header_bar = Gtk.HeaderBar(title="DownYS", show_close_button=True)
        self.set_titlebar(header_bar)

        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(main_vbox)

        content_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        main_vbox.pack_start(content_hbox, True, True, 0)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack_sidebar = Gtk.StackSidebar(stack=self.stack)
        content_hbox.pack_start(self.stack_sidebar, False, False, 0)
        content_hbox.pack_start(self.stack, True, True, 0)

        self.pages = {}
        page_defs = [
            ("bookmarks", "Закладки", BookmarksPage),
            ("youtube", "YouTube", YouTubePage),
            ("ffmpeg", "FFmpeg", FFmpegPage),
            ("httrack", "HTTrack/Архів", HTTrackPage),
            ("about", "Про програму", AboutPage)
        ]

        for name, title, p_class in page_defs:
            try:
                p_instance = p_class(self, self.url_handler)
                p_widget = p_instance.build_ui()
                if not isinstance(p_widget, Gtk.Widget):
                    p_widget = Gtk.Label(label=f"Помилка завантаження '{title}'")
                self.stack.add_titled(p_widget, name + "_page", title)
                self.pages[name] = p_instance
            except Exception as e:
                import traceback
                print(f"ПОМИЛКА створення сторінки '{name}': {e}")
                traceback.print_exc()
                error_label = Gtk.Label(label=f"Помилка завантаження сторінки '{title}'\nДивіться деталі в консолі.")
                self.stack.add_titled(error_label, name + "_page", f"{title} (Помилка)")
                self.pages[name] = None
        
        status_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, border_width=5)
        main_vbox.pack_end(status_hbox, False, False, 0)
        self.status_label = Gtk.Label(label="Готово.", halign=Gtk.Align.START)
        status_hbox.pack_start(self.status_label, True, True, 0)
        self.progress_bar = Gtk.ProgressBar(show_text=True, text="")
        status_hbox.pack_end(self.progress_bar, False, False, 0)

        self.show_all()

    def get_page_instance(self, page_name): return self.pages.get(page_name)

    def go_to_page_with_url(self, page_name, url):
        target_widget = self.stack.get_child_by_name(page_name + "_page")
        if target_widget:
            self.stack.set_visible_child(target_widget)
            page_instance = self.pages.get(page_name)
            if page_instance and hasattr(page_instance, 'url_entry'):
                url_entry = getattr(page_instance, 'url_entry', None)
                if isinstance(url_entry, Gtk.Entry):
                    url_entry.set_text(url)

    def _start_task_with_callbacks(self, task_func, args=(), kwargs=None, success_callback=None):
        if self._is_task_running: 
            self.show_warning_dialog("Завдання вже виконується.")
            return

        self._is_task_running = True
        GLib.idle_add(self._set_controls_sensitive, False)
        GLib.idle_add(self._update_progress, 0.0)
        GLib.idle_add(self._update_status, f"Запуск: {task_func.__name__}...")

        call_kwargs = kwargs.copy() if kwargs else {}
        chain_kwargs = kwargs.copy() if kwargs else {} 

        if 'status_callback' not in call_kwargs: call_kwargs['status_callback'] = self._update_status
        if 'progress_callback' not in call_kwargs and task_func in [download_youtube_media, run_ffmpeg_task]:
            call_kwargs['progress_callback'] = self._update_progress
        
        if task_func == run_httrack_web_threaded:
            for key in ['archive_after_mirror', 'post_mirror_archive_path', 'mirror_output_dir', 'site_url']:
                if key in call_kwargs: del call_kwargs[key] 

        def wrapper():
            try:
                task_func(*args, **call_kwargs) 
                final_message = "Завдання успішно завершено."
                if task_func == run_httrack_web_threaded and chain_kwargs.get('archive_after_mirror'):
                    m_dir, a_path, s_url = chain_kwargs.get('mirror_output_dir'), chain_kwargs.get('post_mirror_archive_path'), chain_kwargs.get('site_url')
                    if m_dir and a_path:
                        GLib.idle_add(self._update_status, "HTTrack завершено. Архівування...")
                        archive_directory_threaded(directory_to_archive=m_dir, archive_path=a_path, status_callback=self._update_status, site_url=s_url)
                        final_message = "HTTrack та архівування успішно завершено."
                
                if success_callback and callable(success_callback): 
                    GLib.idle_add(success_callback)
                GLib.idle_add(self._on_task_complete, final_message)
            except Exception as e: 
                import traceback; traceback.print_exc()
                GLib.idle_add(self._on_task_error, str(e))
        self._current_task_thread = threading.Thread(target=wrapper, daemon=True)
        self._current_task_thread.start()

    def _on_task_complete(self, final_message="Завдання завершено."):
        self._is_task_running = False
        GLib.idle_add(self._set_controls_sensitive, True)
        GLib.idle_add(self._update_progress, 1.0)
        GLib.idle_add(self._update_status, final_message)

    def _on_task_error(self, error_message):
        self._is_task_running = False
        GLib.idle_add(self._set_controls_sensitive, True)
        GLib.idle_add(self._update_progress, 0.0)
        GLib.idle_add(self._update_status, f"Помилка: {error_message}")
        self.show_warning_dialog(f"Помилка завдання:\n{error_message}")

    def _set_controls_sensitive(self, sensitive):
        visible_child = self.stack.get_visible_child()
        for page in self.pages.values():
            if page and hasattr(page, 'get_page_widget') and page.get_page_widget() == visible_child:
                button = getattr(page, 'execute_button', None) or getattr(page, 'download_button', None)
                if button: button.set_sensitive(sensitive)
                break

    def _update_progress(self, fraction):
        fraction = max(0.0, min(1.0, float(fraction)))
        self.progress_bar.set_fraction(fraction)
        self.progress_bar.set_text(f"{int(fraction*100)}%" if fraction > 0 or fraction == 1.0 else "")

    def _update_status(self, message):
        self.status_label.set_text(str(message))
        print(f"STATUS: {message}") 

    def show_warning_dialog(self, message):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK, text="Попередження") 
        dialog.format_secondary_text(str(message)); dialog.run(); dialog.destroy()

    def show_info_dialog(self, title, message):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK, text=title) 
        dialog.format_secondary_text(str(message)); dialog.run(); dialog.destroy()

    def _select_file_dialog(self, entry_widget, title, save_mode=False):
        # Код діалогу вибору файлу залишається тут
        pass

    def _select_folder_dialog(self, entry_widget, title):
        # Код діалогу вибору папки залишається тут
        pass

if __name__ == "__main__":
    missing_deps = []
    print("Перевірка залежностей...")
    for dep_name, cmd_args in [("FFmpeg", ['ffmpeg', '-version']), ("HTTrack", ['httrack', '--version']), ("yt-dlp", ['yt-dlp', '--version'])]:
        print(f" - {dep_name}...", end="")
        try:
            subprocess.run(cmd_args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(" OK")
        except (FileNotFoundError, subprocess.CalledProcessError, OSError):
            print(f" НЕ ЗНАЙДЕНО")
            missing_deps.append(dep_name)
    if missing_deps:
         msg = f"Не знайдено: {', '.join(missing_deps)}.\nВстановіть їх та додайте до PATH."
         print(f"\n!!! ПОПЕРЕДЖЕННЯ: {msg} !!!\n")
         try:
             win_temp = Gtk.Window()
             dialog = Gtk.MessageDialog(transient_for=win_temp, modal=True, message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK, text="Відсутні Залежності")
             dialog.format_secondary_text(msg); dialog.run(); dialog.destroy(); win_temp.destroy()
         except Exception as e:
             print(f"Помилка діалогу попередження: {e}\n(Продовження...)")
    
    print("\nЗапуск DownYS...")
    try:
        app = AppWindow()
        Gtk.main() 
    except Exception as e:
        print(f"\n!!! Критична помилка: {e} !!!")
        import traceback
        traceback.print_exc()
    print("DownYS завершив роботу.")

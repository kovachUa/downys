import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango
import os
import sys
import threading
import multiprocessing
import uuid
from queue import Empty
import subprocess
import shutil
from urllib.parse import urlparse, parse_qs
import re
import logging
import gettext

from settings_manager import SettingsManager
from ui.youtube_page import YouTubePage
from ui.ffmpeg_page import FFmpegPage
from ui.httrack_page import HTTrackPage
from ui.about_page import AboutPage
from scripts.bookmarks_page import BookmarksPage
from scripts.youtube import download_youtube_media, get_youtube_info
from scripts.ffmpeg_tasks import run_ffmpeg_task
from scripts.httrack_tasks import run_httrack_web_threaded, archive_directory_threaded

try:
    gettext.install("downys", os.path.join(os.path.dirname(__file__), "locale"))
except FileNotFoundError:
    _ = lambda s: s

logger = logging.getLogger(__name__)

TASK_DEPENDENCIES = {
    run_ffmpeg_task: ("FFmpeg", "ffmpeg"),
    run_httrack_web_threaded: ("HTTrack", "httrack"),
    archive_directory_threaded: ("tar", "tar"),
    download_youtube_media: ("yt-dlp", "yt-dlp"),
}

class URLHandler:
    def validate_httrack_url(self, url_string):
        logger.debug(f"Validating HTTrack URL: {url_string}")
        if not url_string:
            raise ValueError(_("URL не може бути порожнім."))
        try:
            parsed_url = urlparse(url_string)
            allowed_schemes = ('http', 'https', 'ftp')
            if not parsed_url.scheme or parsed_url.scheme.lower() not in allowed_schemes:
                raise ValueError(_(f"Непідтримувана схема URL (очікується {', '.join(allowed_schemes)})."))
            if not parsed_url.netloc:
                raise ValueError(_("Відсутнє ім'я хоста (домен) в URL."))
            logger.debug(f"URL '{url_string}' is valid for HTTrack.")
            return True
        except ValueError as e:
             logger.warning(f"Invalid URL '{url_string}': {e}")
             raise ValueError(_(f"Неприпустимий URL: {e}"))
        except Exception as e:
             logger.error(f"Failed to parse URL '{url_string}': {e}")
             raise ValueError(_(f"Не вдалося проаналізувати URL '{url_string}': {e}"))

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
            logging.warning(_(f"Не вдалося проаналізувати URL '{url_string}' для отримання хоста: {e}"))
            return None

class AppWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="DownYS", default_width=850, default_height=800)
        self.connect("destroy", self._on_destroy)

        self.settings = SettingsManager()
        self.active_tasks = {}
        self._queue_checker_id = None
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
            ("bookmarks", _("Закладки"), BookmarksPage),
            ("youtube", "YouTube", YouTubePage),
            ("ffmpeg", "FFmpeg", FFmpegPage),
            ("httrack", _("HTTrack/Архів"), HTTrackPage),
            ("about", _("Про програму"), AboutPage)
        ]

        for name, title, p_class in page_defs:
            try:
                p_instance = p_class(self, self.url_handler)
                p_widget = p_instance.build_ui()
                if not isinstance(p_widget, Gtk.Widget):
                    p_widget = Gtk.Label(label=_(f"Помилка завантаження '{title}'"))
                self.stack.add_titled(p_widget, name + "_page", title)
                self.pages[name] = p_instance
            except Exception as e:
                logging.exception(_(f"ПОМИЛКА створення сторінки '{name}': {e}"))
                error_label = Gtk.Label(label=_(f"Помилка завантаження сторінки '{title}'\nДивіться деталі в консолі."))
                self.stack.add_titled(error_label, name + "_page", f"{title} ({_('Помилка')})")
                self.pages[name] = None
        
        self._build_task_management_ui(main_vbox)

        status_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, border_width=5)
        main_vbox.pack_end(status_hbox, False, False, 0)
        self.status_label = Gtk.Label(label=_("Готово."), halign=Gtk.Align.START, ellipsize=Pango.EllipsizeMode.END)
        status_hbox.pack_start(self.status_label, True, True, 0)
        self.progress_bar = Gtk.ProgressBar(show_text=True, text="")
        status_hbox.pack_end(self.progress_bar, False, False, 0)

        self.show_all()

    def _build_task_management_ui(self, parent_box):
        self.task_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN, transition_duration=250)
        parent_box.pack_end(self.task_revealer, False, False, 0)
        
        task_frame = Gtk.Frame(label=_("Активні завдання"), margin=5)
        self.task_revealer.add(task_frame)
        
        scrolled_window = Gtk.ScrolledWindow(shadow_type=Gtk.ShadowType.IN, min_content_height=100)
        task_frame.add(scrolled_window)
        
        self.task_listbox = Gtk.ListBox()
        scrolled_window.add(self.task_listbox)

    def _add_task_to_ui(self, task_id, task_name):
        row = Gtk.ListBoxRow()
        row.task_id = task_id
        
        hbox = Gtk.Box(spacing=10, margin=5)
        row.add(hbox)
        
        label = Gtk.Label(label=task_name, xalign=0, ellipsize=Pango.EllipsizeMode.END)
        hbox.pack_start(label, True, True, 0)
        
        cancel_button = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.BUTTON)
        cancel_button.set_tooltip_text(_("Скасувати завдання"))
        cancel_button.connect("clicked", self._on_cancel_task_clicked, task_id)
        hbox.pack_end(cancel_button, False, False, 0)
        
        self.task_listbox.add(row)
        row.show_all()
        self.task_revealer.set_reveal_child(True)

    def _remove_task_from_ui(self, task_id):
        for row in self.task_listbox.get_children():
            if hasattr(row, 'task_id') and row.task_id == task_id:
                self.task_listbox.remove(row)
                break
        if len(self.active_tasks) == 0:
            self.task_revealer.set_reveal_child(False)

    def _on_cancel_task_clicked(self, widget, task_id):
        task_info = self.active_tasks.get(task_id)
        if task_info and task_info.get('process'):
            logger.info(f"Cancelling task {task_id}...")
            task_info['process'].terminate()
            
    def _check_dependency(self, name, command):
        if not shutil.which(command):
            logger.error(f"Dependency '{name}' not found using command '{command}'.")
            self.show_warning_dialog(f"{_('Відсутня залежність')}: {name}.\n{_('Встановіть її та додайте до системного PATH.')}")
            return False
        logger.debug(f"Dependency '{name}' found.")
        return True

    def start_task(self, task_func, task_name, args=(), kwargs=None, success_callback=None):
        if not kwargs: kwargs = {}

        dependency_info = TASK_DEPENDENCIES.get(task_func)
        if dependency_info:
            dep_name, dep_cmd = dependency_info
            if not self._check_dependency(dep_name, dep_cmd):
                return

        task_id = str(uuid.uuid4())
        comm_queue = multiprocessing.Queue()
        
        process = multiprocessing.Process(target=task_func, args=(*args, kwargs, comm_queue), daemon=True)
        
        self.active_tasks[task_id] = {
            'process': process,
            'name': task_name,
            'queue': comm_queue,
            'success_callback': success_callback
        }
        
        process.start()
        self._add_task_to_ui(task_id, task_name)
        
        if not self._queue_checker_id:
            self._queue_checker_id = GLib.timeout_add(150, self._check_queues)

    def _check_queues(self):
        if not self.active_tasks:
            self._queue_checker_id = None
            return False

        for task_id, task_info in list(self.active_tasks.items()):
            if not task_info['process'].is_alive():
                logger.warning(f"Process for task {task_id} ('{task_info['name']}') is no longer alive. Cleaning up.")
                try:
                    message = task_info['queue'].get_nowait()
                    self._handle_queue_message(task_id, message)
                except Empty:
                    if task_info['process'].exitcode is not None and task_info['process'].exitcode != 0:
                        self._on_task_error(task_id, _(f"Завдання завершилося несподівано з кодом виходу: {task_info['process'].exitcode}"))
                    else:
                        self._remove_task(task_id)

                continue

            try:
                while True:
                    message = task_info['queue'].get_nowait()
                    self._handle_queue_message(task_id, message)
            except Empty:
                pass
        
        return True

    def _handle_queue_message(self, task_id, message):
        msg_type = message.get("type")
        value = message.get("value")

        if msg_type == "status":
            self._update_status(value)
        elif msg_type == "progress":
            self._update_progress(value)
        elif msg_type == "done":
            self._on_task_complete(task_id, value)
        elif msg_type == "error":
            self._on_task_error(task_id, value)

    def _remove_task(self, task_id):
        if task_id in self.active_tasks:
            task_info = self.active_tasks.pop(task_id)
            task_info['queue'].close()
        self._remove_task_from_ui(task_id)
    
    def _on_task_complete(self, task_id, final_message):
        task_info = self.active_tasks.get(task_id, {})
        
        self._update_status(final_message)
        self._update_progress(0)
        
        if task_info.get('success_callback'):
            try:
                task_info['success_callback']()
            except Exception as e:
                logger.error(f"Error in success_callback for task {task_id}: {e}")
        
        self._remove_task(task_id)

    def _on_task_error(self, task_id, error_message):
        task_info = self.active_tasks.get(task_id, {})
        task_name = task_info.get('name', _('невідоме завдання'))
        
        self.show_detailed_error_dialog(_(f"Помилка виконання завдання: {task_name}"), str(error_message))
        self._update_status(_(f"Помилка: {task_name}"))
        self._update_progress(0)
        
        self._remove_task(task_id)

    def _on_destroy(self, *args):
        for task_id, task_info in self.active_tasks.items():
            if task_info.get('process') and task_info['process'].is_alive():
                logger.info(f"Terminating active task {task_id} on exit.")
                task_info['process'].terminate()
        Gtk.main_quit()
    
    def analyze_and_go_to_page(self, url):
        self._update_status(_("Аналіз URL..."))
        
        def analysis_thread():
            page_target = "httrack"
            try:
                info = get_youtube_info(url)
                if info and info.get('_type') in ('video', 'playlist', 'multi_video'):
                    page_target = "youtube"
            except Exception as e:
                logger.warning(f"URL analysis failed for '{url}', defaulting to httrack. Error: {e}")
            
            GLib.idle_add(self.go_to_page_with_url, page_target, url)
            GLib.idle_add(self._update_status, _("Готово."))

        thread = threading.Thread(target=analysis_thread, daemon=True)
        thread.start()

    def go_to_page_with_url(self, page_name, url):
        target_widget = self.stack.get_child_by_name(page_name + "_page")
        if target_widget:
            self.stack.set_visible_child(target_widget)
            page_instance = self.pages.get(page_name)
            if page_instance and hasattr(page_instance, 'url_entry'):
                url_entry = getattr(page_instance, 'url_entry', None)
                if isinstance(url_entry, Gtk.Entry):
                    url_entry.set_text(url)

    def _update_progress(self, fraction):
        fraction = max(0.0, min(1.0, float(fraction)))
        self.progress_bar.set_fraction(fraction)
        self.progress_bar.set_text(f"{int(fraction*100)}%" if fraction > 0 or fraction == 1.0 else "")

    def _update_status(self, message):
        self.status_label.set_text(str(message))
        logging.info(f"STATUS: {message}")

    def show_warning_dialog(self, message):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK, text=_("Попередження"))
        dialog.format_secondary_text(str(message)); dialog.run(); dialog.destroy()

    def show_info_dialog(self, title, message):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK, text=title)
        dialog.format_secondary_text(str(message)); dialog.run(); dialog.destroy()

    def show_detailed_error_dialog(self, title, message):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.CLOSE, text=title)
        dialog.set_default_size(600, 400)
        scrolled_window = Gtk.ScrolledWindow(shadow_type=Gtk.ShadowType.IN, hexpand=True, vexpand=True)
        text_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, editable=False, cursor_visible=False)
        text_buffer = text_view.get_buffer()
        text_buffer.set_text(str(message))
        scrolled_window.add(text_view)
        dialog.get_content_area().pack_end(scrolled_window, True, True, 0)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def _select_file_dialog(self, entry_widget, title, save_mode=False):
        action = Gtk.FileChooserAction.SAVE if save_mode else Gtk.FileChooserAction.OPEN
        dialog = Gtk.FileChooserDialog(title=title, transient_for=self, action=action)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE if save_mode else Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        if save_mode:
            dialog.set_do_overwrite_confirmation(True)
            current_path = entry_widget.get_text()
            if current_path:
                if os.path.isdir(current_path):
                    dialog.set_current_folder(current_path)
                elif os.path.isdir(os.path.dirname(current_path)):
                    dialog.set_current_folder(os.path.dirname(current_path))
                    dialog.set_current_name(os.path.basename(current_path))

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            entry_widget.set_text(dialog.get_filename())
        dialog.destroy()

    def _select_folder_dialog(self, entry_widget, title):
        dialog = Gtk.FileChooserDialog(title=title, transient_for=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        
        current_path = entry_widget.get_text()
        if current_path and os.path.isdir(current_path):
            dialog.set_current_folder(current_path)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            entry_widget.set_text(dialog.get_filename())
        dialog.destroy()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    app_name = "DownYS"
    if os.name == 'nt':
        log_dir = os.path.join(os.environ['APPDATA'], app_name, 'logs')
    else:
        log_dir = os.path.join(os.path.expanduser('~'), '.config', app_name, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, "app.log")

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s', handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(log_file_path, encoding='utf-8')])

    logging.info(_("\nЗапуск DownYS..."))
    try:
        app = AppWindow()
        Gtk.main()
    except Exception as e:
        logging.exception(_(f"\n!!! Критична помилка: {e} !!!"))
    logging.info(_("DownYS завершив роботу."))

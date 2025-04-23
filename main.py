import gi
import os
import json # Keep if needed elsewhere, not used in provided snippets
import subprocess # Keep if needed elsewhere, not used in provided snippets
import re # Keep if needed elsewhere, not used in provided snippets
import shutil # Keep if needed elsewhere, not used in provided snippets
import threading
from urllib.parse import urlparse # Keep if needed elsewhere, not used in provided snippets
import time # Added for dummy task

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango

# Assume these scripts and menus exist
from scripts.youtube import download_youtube_video_with_progress
from scripts.upload_server import upload_file_to_server
from ui.ffmpeg_menu import FFmpegMenu, FFMPEG_TASKS
from ui.httrack_menu import HTTrackMenu
from ui.youtube_menu import YouTubeMenu
from scripts.httrack_tasks import run_httrack_web_threaded, archive_directory_threaded

# --- Dummy FFmpeg Task (Replace with actual implementation) ---
def run_ffmpeg_task(input_path, output_path, task_type=None, task_options=None, progress_callback=None, status_callback=None):
    # Ensure callbacks are called via GLib.idle_add as this runs in a separate thread
    if status_callback:
        GLib.idle_add(status_callback, f"Запуск FFmpeg завдання '{task_type}'...")
    print(f"Dummy FFmpeg Task: {task_type}, Input: {input_path}, Output: {output_path}, Options: {task_options}")

    # Simulate work and progress
    total_steps = 100
    for i in range(total_steps + 1):
        # Ensure all UI-updating calls go through GLib.idle_add
        if status_callback:
            if i == 0:
                GLib.idle_add(status_callback, "Ініціалізація FFmpeg...")
            elif i == total_steps:
                 GLib.idle_add(status_callback, "Завершення FFmpeg...")
            elif i % 20 == 0:
                 GLib.idle_add(status_callback, f"Обробка {i}%...")

        if progress_callback:
            GLib.idle_add(progress_callback, i / total_steps)

        time.sleep(0.05) # Simulate work

    if status_callback:
        GLib.idle_add(status_callback, "FFmpeg завдання завершено.")


class AppWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="Multi-Tool App")
        self.set_default_size(800, 600)

        self.host = "127.0.0.1" # Placeholder host
        self.port = 12345       # Placeholder port

        # --- UI Elements ---
        header_bar = Gtk.HeaderBar()
        header_bar.set_show_close_button(True)
        header_bar.props.title = "Multi-Tool"
        self.set_titlebar(header_bar)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(box)

        # Store stack and stack_sidebar as instance attributes
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(300)

        self.stack_sidebar = Gtk.StackSidebar()
        self.stack_sidebar.set_stack(self.stack)

        hbox_main = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hbox_main.set_homogeneous(False)
        hbox_main.pack_start(self.stack_sidebar, False, False, 0) # Use self.stack_sidebar
        hbox_main.pack_start(self.stack, True, True, 0) # Use self.stack
        box.pack_start(hbox_main, True, True, 0)

        # --- Pages ---
        self._create_youtube_page()
        self._create_ffmpeg_page()
        self._create_httrack_page()
        self._create_upload_page()
        self._create_about_page() # Placeholder About page

        # --- Status and Progress Bar ---
        status_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.pack_end(status_hbox, False, False, 0)

        self.status_label = Gtk.Label(label="Готово.")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.set_line_wrap(True)
        self.status_label.set_max_width_chars(80) # Limit width to prevent excessive wrapping
        self.status_label.set_ellipsize(Pango.EllipsizeMode.END) # Add ellipsis if text is too long
        status_hbox.pack_start(self.status_label, True, True, 0)

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text("")
        self.progress_bar.set_show_text(True)
        status_hbox.pack_end(self.progress_bar, False, False, 0) # Use pack_end for right alignment

        # --- Task Management ---
        self._is_task_running = False
        self._current_task_thread = None

        # Show window
        self.connect("destroy", Gtk.main_quit)
        self.show_all()

    # --- Page Creation Methods ---
    def _create_youtube_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_border_width(10)
        # Use Pango markup for bold and large text
        page.pack_start(Gtk.Label(label="<b><big>Завантаження YouTube</big></b>", use_markup=True), False, False, 0)
        button = Gtk.Button(label="Налаштувати та завантажити")
        button.connect("clicked", self.on_youtube_clicked)
        page.pack_start(button, False, False, 0)
        self.stack.add_titled(page, "youtube_page", "YouTube")

    def _create_ffmpeg_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_border_width(10)
        # Use Pango markup for bold and large text
        page.pack_start(Gtk.Label(label="<b><big>FFmpeg Конвертація</big></b>", use_markup=True), False, False, 0)
        button = Gtk.Button(label="Налаштувати та виконати")
        button.connect("clicked", self.on_ffmpeg_clicked)
        page.pack_start(button, False, False, 0)
        self.stack.add_titled(page, "ffmpeg_page", "FFmpeg")

    def _create_httrack_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_border_width(10)
        # Use Pango markup for bold and large text
        page.pack_start(Gtk.Label(label="<b><big>HTTrack та Архівування</big></b>", use_markup=True), False, False, 0)
        button = Gtk.Button(label="Налаштувати та виконати")
        button.connect("clicked", self.on_httrack_clicked)
        page.pack_start(button, False, False, 0)
        self.stack.add_titled(page, "httrack_page", "HTTrack/Архів")

    def _create_upload_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_border_width(10)
        # Use Pango markup for bold and large text
        page.pack_start(Gtk.Label(label="<b><big>Завантаження на Сервер</big></b>", use_markup=True), False, False, 0)
        button = Gtk.Button(label="Обрати файл та завантажити")
        button.connect("clicked", self.on_upload_clicked)
        page.pack_start(button, False, False, 0)
        self.stack.add_titled(page, "upload_page", "Завантаження")

    def _create_about_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_border_width(10)
        # Use Pango markup for bold and large text
        page.pack_start(Gtk.Label(label="<b><big>Про програму</big></b>", use_markup=True), False, False, 0)
        page.pack_start(Gtk.Label(label="Це багатофункціональна програма для роботи з контентом."), False, False, 0)
        # Add more info here
        self.stack.add_titled(page, "about_page", "Про програму")


    # --- Dialog Callbacks ---
    def on_youtube_clicked(self, widget):
        dialog = YouTubeMenu(self)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            try:
                url, output_dir = dialog.get_params()
                # Pass the task function and its arguments/kwargs to _start_task
                self._start_task(
                    download_youtube_video_with_progress,
                    args=(url, output_dir),
                    # Callbacks are added by _start_task's internal logic based on task_func type
                )
            except ValueError as e:
                self.show_warning_dialog(str(e))
            except Exception as e:
                self.show_warning_dialog(f"Неочікувана помилка при отриманні параметрів: {e}")

        dialog.destroy()

    def on_ffmpeg_clicked(self, widget):
        dialog = FFmpegMenu(self)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            try:
                params = dialog.get_params()
                # Pass the task function and its arguments/kwargs to _start_task
                self._start_task(
                    run_ffmpeg_task, # Use the dummy or actual FFmpeg task function
                    args=(params['input_path'], params['output_path']),
                    kwargs={'task_type': params['task_type'], 'task_options': params['task_options']}
                    # Callbacks are added by _start_task's internal logic based on task_func type
                )
            except ValueError as e:
                self.show_warning_dialog(str(e))
            except Exception as e:
                self.show_warning_dialog(f"Неочікувана помилка при отриманні параметрів: {e}")

        dialog.destroy()

    def on_httrack_clicked(self, widget):
        dialog = HTTrackMenu(self)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            try:
                params = dialog.get_params()
                operation_type = params["operation_type"]

                if operation_type == "mirror":
                    url = params["url"]
                    mirror_output_dir = params["mirror_output_dir"]
                    archive_after_mirror = params["archive_after_mirror"]
                    post_mirror_archive_path = params["post_mirror_archive_path"]

                    # The main task is HTTrack mirroring
                    # Pass archiving parameters for the wrapper to use later
                    self._start_task(
                        run_httrack_web_threaded,
                        args=(url, mirror_output_dir),
                        kwargs={'archive_after_mirror': archive_after_mirror,
                                'post_mirror_archive_path': post_mirror_archive_path,
                                'mirror_output_dir': mirror_output_dir, # Need this again for archiving
                                'site_url': url # Pass url for archive function to potentially find subdir
                               }
                        # status_callback is added by _start_task's internal logic
                    )

                elif operation_type == "archive":
                    archive_source_dir = params["archive_source_dir"]
                    archive_path = params["archive_path"]
                    # Direct archive task
                    self._start_task(
                        archive_directory_threaded,
                        args=(archive_source_dir, archive_path),
                        kwargs={'site_url': None, # No URL source in this mode
                                'site_subdir_name': None # No explicit subdir in this mode
                               }
                        # status_callback is added by _start_task's internal logic
                    )

            except ValueError as e:
                self.show_warning_dialog(str(e))
            except Exception as e:
                 self.show_warning_dialog(f"Неочікувана помилка при отриманні параметрів: {e}")


        dialog.destroy()

    def on_upload_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(
            "Оберіть файл для завантаження", self,
            Gtk.FileChooserAction.OPEN,
            ("_Скасувати", Gtk.ResponseType.CANCEL,
             "_Відкрити", Gtk.ResponseType.OK)
        )

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            file_path = dialog.get_filename()
            dialog.destroy()

            if not file_path or not os.path.isfile(file_path):
                 self.show_warning_dialog("Будь ласка, оберіть існуючий файл.")
                 return

            try:
                # Pass the task function and its arguments/kwargs to _start_task
                self._start_task(
                    upload_file_to_server,
                    args=(file_path,),
                    kwargs={'host': self.host, 'port': self.port}
                    # update_progress_callback is added by _start_task's internal logic
                )
            except Exception as e:
                 # Should be caught by _start_task wrapper, but safety first
                 self.show_warning_dialog(f"Неочікувана помилка перед запуском завантаження: {e}")

        else:
            dialog.destroy()

    # --- Task Execution and Callbacks ---

    def _set_controls_sensitive(self, sensitive):
        # This method is called from the main thread
        # Disable buttons on stack pages (iterate through stack children)
        for page in self.stack.get_children(): # Use self.stack
             # Iterate through potential containers within the page
             # For simplicity, let's just find buttons directly under the page container
             # A recursive function would be needed for deeply nested buttons
             if hasattr(page, 'get_children'):
                 for child in page.get_children():
                     if isinstance(child, Gtk.Button):
                          child.set_sensitive(sensitive)


        # Disable buttons within the StackSidebar / StackSwitcher
        # Accessing the StackSwitcher directly is still slightly fragile
        # but more reliable than iterating arbitrary sidebar children.
        # StackSwitcher is often a direct child of the StackSidebar.
        if hasattr(self.stack_sidebar, 'get_children'):
            for sidebar_child in self.stack_sidebar.get_children(): # Use self.stack_sidebar
                 if isinstance(sidebar_child, Gtk.StackSwitcher):
                      # Found the switcher, now iterate its children (the buttons)
                      if hasattr(sidebar_child, 'get_children'):
                          for switcher_button in sidebar_child.get_children():
                              # Check if the child of StackSwitcher is a button-like element
                               if hasattr(switcher_button, 'set_sensitive'):
                                    switcher_button.set_sensitive(sensitive)

        # Note: Disabling controls in open dialogs (_on_youtube_clicked etc.) requires managing
        # the dialog instances themselves or using a global input grab (less ideal).
        # For this scope, disabling main window controls is sufficient.


    def _update_progress(self, fraction):
        # This method is called from the task thread via GLib.idle_add (or directly by task if it does the wrapping)
        self.progress_bar.set_fraction(fraction)
        # Only show percentage text if progress is non-zero or complete
        self.progress_bar.set_text(f"{int(fraction*100)}%") if fraction > 0 or fraction == 1.0 else self.progress_bar.set_text("")


    def _update_status(self, message):
        # This method is called from the task thread via GLib.idle_add (or directly by task if it does the wrapping)
        self.status_label.set_text(message)

    def _on_task_complete(self):
        # This method is called from the task thread via GLib.idle_add
        self._is_task_running = False
        GLib.idle_add(self._set_controls_sensitive, True) # Ensure sensitivity is updated on main thread
        GLib.idle_add(self._update_progress, 1.0) # Ensure progress is full on success on main thread
        GLib.idle_add(self._update_status, "Завдання завершено.") # Update status on main thread
        print("Task Completed.") # Log to console as well

    def _on_task_error(self, error_message):
        # This method is called from the task thread via GLib.idle_add
        self._is_task_running = False
        GLib.idle_add(self._set_controls_sensitive, True) # Ensure sensitivity is updated on main thread
        # Keep progress bar at last state or reset? Let's reset for clarity on failure
        GLib.idle_add(self._update_progress, 0.0) # Reset progress on main thread
        GLib.idle_add(self._update_status, f"Помилка: {error_message}") # Update status on main thread
        print(f"Task Error: {error_message}") # Log to console as well
        # Show dialog on main thread
        GLib.idle_add(self.show_warning_dialog, f"Під час виконання завдання сталася помилка:\n{error_message}")


    def _start_task(self, task_func, args=(), kwargs=None):
        if self._is_task_running:
            self.show_warning_dialog("Завдання вже виконується. Будь ласка, дочекайтеся його завершення.")
            return

        self._is_task_running = True
        # Update UI on the main thread
        GLib.idle_add(self._set_controls_sensitive, False)
        GLib.idle_add(self._update_progress, 0.0)
        GLib.idle_add(self._update_status, "Запуск завдання...")


        if kwargs is None:
             kwargs = {}

        # Prepare kwargs to pass to the task function, including callbacks
        # Task functions are expected to wrap their callback calls with GLib.idle_add.
        task_kwargs = kwargs.copy()

        # Pass the methods as callbacks.
        task_kwargs['status_callback'] = self._update_status
        # Determine which tasks get a progress callback
        tasks_with_progress = [download_youtube_video_with_progress, run_ffmpeg_task, upload_file_to_server]
        if task_func in tasks_with_progress:
             # upload_file_to_server expects 'update_progress_callback' name
             if task_func == upload_file_to_server:
                 task_kwargs['update_progress_callback'] = self._update_progress
             else: # youtube, ffmpeg
                 task_kwargs['progress_callback'] = self._update_progress
        # HTTrack tasks do not have a clear progress indication, only status updates


        def wrapper():
            try:
                # Execute the primary task
                print(f"Starting thread for: {task_func.__name__}")
                # Note: Pass *args and **task_kwargs to the task function
                task_func(*args, **task_kwargs)
                print(f"Primary task finished: {task_func.__name__}")

                # --- Handle Sequential Tasks (e.g., Archive after HTTrack Mirror) ---
                # This sequence logic is specific to the HTTrack mirror task
                if task_func == run_httrack_web_threaded and kwargs.get('archive_after_mirror'):
                     mirror_output_dir = kwargs.get('mirror_output_dir') # Use kwargs directly from the initial call
                     post_mirror_archive_path = kwargs.get('post_mirror_archive_path')
                     site_url = kwargs.get('site_url')

                     if mirror_output_dir and post_mirror_archive_path:
                         # Update status on the main thread before starting the next step
                         GLib.idle_add(self._update_status, "HTTrack завершено. Запуск архівації результату...")
                         print("Starting post-mirror archive...")
                         try:
                             # Call archive_directory_threaded. It expects status_callback and optional site_url/subdir.
                             # It must also wrap its status_callback calls with GLib.idle_add.
                             archive_directory_threaded(
                                 mirror_output_dir,
                                 post_mirror_archive_path,
                                 status_callback=self._update_status, # Pass status callback
                                 site_url=site_url # Pass original URL to help find subdir
                             )
                             print("Post-mirror archive finished.")
                         except Exception as archive_e:
                              # If archive fails, report archive error, but the main task (HTTrack) finished.
                              # We report this as an error for the overall operation sequence.
                              GLib.idle_add(self._on_task_error, f"Помилка під час архівації результату HTTrack: {archive_e}")
                              return # Stop here on archive error

                # If we reached here, the primary task (and optional sequence) succeeded
                GLib.idle_add(self._on_task_complete)

            except Exception as e:
                import traceback
                traceback.print_exc() # Print detailed traceback to console
                GLib.idle_add(self._on_task_error, str(e))

        thread = threading.Thread(target=wrapper)
        # thread.daemon = True # Keeping the application alive until tasks finish is safer for debugging
        thread.start()
        self._current_task_thread = thread


    # --- Utility Methods ---
    def show_warning_dialog(self, message):
        # This method should only be called from the main thread
        # Using modern keyword arguments for Gtk.MessageDialog
        dialog = Gtk.MessageDialog(
            parent=self,
            modal=True,
            destroy_with_parent=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK,
            text=message # Using the recommended 'text' keyword
        )
        dialog.run()
        dialog.destroy()


# --- Main Execution ---
if __name__ == "__main__":
    win = AppWindow()
    Gtk.main()

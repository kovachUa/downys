import gi
import subprocess
from pymediainfo import MediaInfo
from gi.repository import Gtk

gi.require_version("Gtk", "3.0")

class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Downys")

        # Головний контейнер
        vbox = Gtk.VBox(spacing=10)
        self.add(vbox)

        # Кнопка для обробки метаданих
        self.metadata_video_button = Gtk.Button(label="Process Video Metadata")
        self.metadata_video_button.connect("clicked", self.on_metadata_video_clicked)
        vbox.pack_start(self.metadata_video_button, False, False, 0)

        # Інші кнопки
        self.httrack_button = Gtk.Button(label="HTTrack")
        vbox.pack_start(self.httrack_button, False, False, 0)

        self.youtube_button = Gtk.Button(label="YouTube Download")
        vbox.pack_start(self.youtube_button, False, False, 0)

    def on_metadata_video_clicked(self, widget):
        self.open_file_chooser('video')

    def open_file_chooser(self, file_type):
        dialog = Gtk.FileChooserDialog(f"Choose a {file_type.capitalize()} File", self, Gtk.FileChooserAction.OPEN,
                                       ("Cancel", Gtk.ResponseType.CANCEL, "Open", Gtk.ResponseType.OK))

        # Фільтрація файлів за типом
        if file_type == 'video':
            filter = Gtk.FileFilter()
            filter.set_name("Video Files")
            filter.add_mime_type("video/*")
            dialog.add_filter(filter)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            file_path = dialog.get_filename()
            self.show_metadata_edit_dialog(file_path)

        dialog.destroy()

    def show_metadata_edit_dialog(self, file_path):
        # Отримуємо метадані за допомогою pymediainfo
        media_info = MediaInfo.parse(file_path)
        video_info = media_info.tracks[0]  # Отримаємо перший відеотрек
        resolution = f"{video_info.width}x{video_info.height}"
        duration = video_info.duration / 1000  # Перетворюємо на секунди

        # Створюємо діалог для редагування
        dialog = Gtk.Dialog("Edit Metadata", self, Gtk.DialogFlags.MODAL,
                            ("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK))

        content_area = dialog.get_content_area()

        # Додаємо поля для редагування
        resolution_label = Gtk.Label(label="Resolution (e.g. 1920x1080):")
        duration_label = Gtk.Label(label="Duration (seconds):")

        resolution_entry = Gtk.Entry(text=resolution)
        duration_entry = Gtk.Entry(text=f"{duration:.2f}")

        content_area.add(resolution_label)
        content_area.add(resolution_entry)
        content_area.add(duration_label)
        content_area.add(duration_entry)

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            # Отримуємо значення з полів вводу
            new_resolution = resolution_entry.get_text()
            new_duration = duration_entry.get_text()

            # Зберігаємо нові метадані (за допомогою ffmpeg або іншого інструмента)
            self.update_video_metadata(file_path, new_resolution, new_duration)

        dialog.destroy()

    def update_video_metadata(self, file_path, new_resolution, new_duration):
        # Функція для оновлення метаданих відеофайлу за допомогою ffmpeg

        # Розбір нового значення роздільної здатності
        width, height = new_resolution.split('x')

        # Викликаємо ffmpeg для зміни метаданих
        output_file = "output_" + file_path.split("/")[-1]
        command = [
            "ffmpeg", "-i", file_path, "-s", f"{width}x{height}",
            "-t", new_duration, "-map_metadata", "0", "-c:v", "libx264", "-c:a", "aac",
            "-strict", "experimental", output_file
        ]
        subprocess.run(command, check=True)
        print(f"Updated video metadata saved to: {output_file}")

# Запуск програми
win = MainWindow()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()

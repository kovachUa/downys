import gi
from gi.repository import Gtk

gi.require_version("Gtk", "3.0")

class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Downys")

        # Головний контейнер
        vbox = Gtk.VBox(spacing=10)
        self.add(vbox)

        # Кнопка для обробки метаданих
        self.metadata_video_button = Gtk.Button(label="Обробити метадані відео")
        self.metadata_video_button.connect("clicked", self.on_metadata_video_clicked)
        vbox.pack_start(self.metadata_video_button, False, False, 0)

        # Кнопка для програвання медіа
        self.play_media_button = Gtk.Button(label="Програти медіа")
        self.play_media_button.connect("clicked", self.on_play_media_clicked)
        vbox.pack_start(self.play_media_button, False, False, 0)

        # Інші кнопки
        self.httrack_button = Gtk.Button(label="HTTrack")
        vbox.pack_start(self.httrack_button, False, False, 0)

        self.youtube_button = Gtk.Button(label="Завантажити з YouTube")
        vbox.pack_start(self.youtube_button, False, False, 0)

        self.media_file = None  # Змінна для зберігання шляху до медіа файлу

    def on_metadata_video_clicked(self, widget):
        self.open_file_chooser('video')

    def on_play_media_clicked(self, widget):
        if not self.media_file:
            self.show_warning_dialog("Будь ласка, виберіть медіа файл для програвання.")
            return
        self.play_media(self.media_file)

    def open_file_chooser(self, file_type):
        dialog = Gtk.FileChooserDialog(f"Виберіть {file_type.capitalize()} файл", self, Gtk.FileChooserAction.OPEN,
                                       ("Скасувати", Gtk.ResponseType.CANCEL, "Відкрити", Gtk.ResponseType.OK))

        # Фільтрація файлів за типом
        if file_type == 'video':
            filter = Gtk.FileFilter()
            filter.set_name("Відеофайли")
            filter.add_mime_type("video/*")
            dialog.add_filter(filter)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.media_file = dialog.get_filename()
            self.show_metadata_edit_dialog(self.media_file)  # Відкриваємо діалог для редагування метаданих

        dialog.destroy()

    def show_metadata_edit_dialog(self, file_path):
        # Створюємо діалог для редагування метаданих
        dialog = Gtk.Dialog("Редагувати метадані", self, Gtk.DialogFlags.MODAL,
                            ("Скасувати", Gtk.ResponseType.CANCEL, "Зберегти", Gtk.ResponseType.OK))

        content_area = dialog.get_content_area()

        # Додаємо поля для редагування
        resolution_label = Gtk.Label(label="Роздільна здатність (наприклад 1920x1080):")
        duration_label = Gtk.Label(label="Тривалість (секунди):")

        resolution_entry = Gtk.Entry()
        duration_entry = Gtk.Entry()

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
        # Викликаємо ffmpeg для зміни метаданих (фіктивна команда для демонстрації)
        print(f"Оновлені метадані для {file_path}: роздільна здатність - {new_resolution}, тривалість - {new_duration} секунд.")
        
    def play_media(self, file_path):
        # Створення плеєра для медіа
        print(f"Програвання медіа: {file_path}")

    def show_warning_dialog(self, message):
        # Оновлений діалог попередження
        dialog = Gtk.MessageDialog(
            self,
            Gtk.DialogFlags.MODAL,
            Gtk.MessageType.WARNING,
            Gtk.ButtonsType.OK,
            text=message
        )
        dialog.run()
        dialog.destroy()

# Запуск програми
win = MainWindow()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()

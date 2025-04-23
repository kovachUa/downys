import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import os

class YouTubeMenu(Gtk.Dialog):
    def __init__(self, parent, initial_url=""):
        """
        Діалог для налаштувань завантаження YouTube відео.

        Args:
            parent (Gtk.Window): Батьківське вікно.
            initial_url (str, optional): Початковий URL для поля вводу. За замовчуванням "".
        """
        super().__init__(title="Налаштування завантаження YouTube", transient_for=parent,
                         modal=True, destroy_with_parent=True)

        self.add_button("_Скасувати", Gtk.ResponseType.CANCEL)
        self.add_button("_Завантажити", Gtk.ResponseType.OK)

        self.set_default_size(450, 200)
        self.set_border_width(10)

        box = self.get_content_area()
        box.set_spacing(10)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        box.add(grid)

        # URL Entry
        grid.attach(Gtk.Label(label="URL відео:"), 0, 0, 1, 1)
        self.url_entry = Gtk.Entry()
        self.url_entry.set_text(initial_url)
        self.url_entry.set_hexpand(True)
        grid.attach(self.url_entry, 1, 0, 3, 1)

        # Output Directory
        grid.attach(Gtk.Label(label="Директорія збереження:"), 0, 1, 1, 1)
        self.output_dir_entry = Gtk.Entry()
        self.output_dir_entry.set_hexpand(True)
        grid.attach(self.output_dir_entry, 1, 1, 2, 1)
        output_dir_button = Gtk.Button(label="...")
        output_dir_button.connect("clicked", self.on_output_dir_clicked)
        grid.attach(output_dir_button, 3, 1, 1, 1)

        # Default output directory suggestion
        self._suggest_default_output_dir()

        self.show_all()

    def _suggest_default_output_dir(self):
        """Пропонує директорію за замовчуванням для збереження YouTube відео."""
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads", "YouTube")
        self.output_dir_entry.set_text(default_dir)

    def on_output_dir_clicked(self, widget):
        """Відкриває діалог вибору директорії для збереження."""
        dialog = Gtk.FileChooserDialog(
            title="Оберіть директорію для збереження", 
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            buttons=(
                "_Скасувати", Gtk.ResponseType.CANCEL,
                "_Обрати", Gtk.ResponseType.OK
            )
        )

        current_dir = self.output_dir_entry.get_text().strip()
        if current_dir and os.path.isdir(current_dir):
            dialog.set_current_folder(current_dir)
        else:
            self._suggest_default_output_dir()
            dialog.set_current_folder(self.output_dir_entry.get_text().strip())

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.output_dir_entry.set_text(dialog.get_filename())

        dialog.destroy()

    def get_params(self):
        """
        Повертає параметри завантаження YouTube відео.
        Викликається після того, як діалог закрився з Gtk.ResponseType.OK.
        """
        url = self.url_entry.get_text().strip()
        output_dir = self.output_dir_entry.get_text().strip()

        # Валідація
        if not url:
            raise ValueError("Будь ласка, введіть URL відео YouTube.")
        if not output_dir:
            raise ValueError("Будь ласка, оберіть директорію для збереження.")
        if not os.path.isdir(output_dir):
            parent_dir = os.path.dirname(output_dir)
            if parent_dir and parent_dir != '.' and not os.path.isdir(parent_dir):
                raise ValueError(f"Батьківська директорія для збереження не існує: {parent_dir}")

        return url, output_dir

import gi
import os
import ffmpeg
from gi.repository import Gtk

class FFmpegMenu(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title="FFmpeg Settings", transient_for=parent, flags=0)

        self.set_default_size(400, 300)

        # Layout
        box = self.get_content_area()
        grid = Gtk.Grid(column_spacing=10, row_spacing=10, margin=10)
        box.add(grid)

        # Input file selector
        self.input_file_label = Gtk.Label(label="Input File:")
        grid.attach(self.input_file_label, 0, 0, 1, 1)

        self.input_file_button = Gtk.Button(label="Choose File")
        self.input_file_button.connect("clicked", self.on_input_file_clicked)
        grid.attach(self.input_file_button, 1, 0, 1, 1)

        self.input_file_path_label = Gtk.Label(label="No input file selected")
        grid.attach(self.input_file_path_label, 0, 1, 2, 1)

        # Output folder selector
        self.output_folder_label = Gtk.Label(label="Output Folder:")
        grid.attach(self.output_folder_label, 0, 2, 1, 1)

        self.output_folder_button = Gtk.Button(label="Choose Folder")
        self.output_folder_button.connect("clicked", self.on_output_folder_clicked)
        grid.attach(self.output_folder_button, 1, 2, 1, 1)

        self.output_folder_path_label = Gtk.Label(label="No output folder selected")
        grid.attach(self.output_folder_path_label, 0, 3, 2, 1)

        # Format selector
        self.format_label = Gtk.Label(label="Format:")
        grid.attach(self.format_label, 0, 4, 1, 1)

        self.format_combo = Gtk.ComboBoxText()
        self.format_combo.append_text("mp4")
        self.format_combo.append_text("mp3")
        self.format_combo.append_text("avi")
        self.format_combo.set_active(1)  # Default to mp3
        grid.attach(self.format_combo, 1, 4, 1, 1)

        # Convert button
        self.convert_button = Gtk.Button(label="Convert")
        self.convert_button.connect("clicked", self.on_convert_clicked)
        grid.attach(self.convert_button, 0, 5, 2, 1)

        # Cancel button
        self.cancel_button = Gtk.Button(label="Cancel")
        self.cancel_button.connect("clicked", self.on_cancel_clicked)
        grid.attach(self.cancel_button, 0, 6, 2, 1)

        self.show_all()

        # Initialize variables
        self.input_file = None
        self.output_folder = None

    def on_input_file_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Choose Input File", parent=self, action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.input_file = dialog.get_filename()
            self.input_file_path_label.set_text(self.input_file)
        dialog.destroy()

    def on_output_folder_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Choose Output Folder", parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.output_folder = dialog.get_filename()
            self.output_folder_path_label.set_text(self.output_folder)
        dialog.destroy()

    def on_convert_clicked(self, widget):
        if not self.input_file:
            self.show_warning("Please select an input file.")
            return

        if not self.output_folder:
            self.show_warning("Please select an output folder.")
            return

        input_file = self.input_file
        output_format = self.format_combo.get_active_text()
        output_file_name = f"{os.path.splitext(os.path.basename(input_file))[0]}.{output_format}"
        output_file = os.path.join(self.output_folder, output_file_name)

        try:
            # Perform conversion using ffmpeg-python
            ffmpeg.input(input_file).output(output_file).run(overwrite_output=True)
            self.show_info(f"File successfully converted to: {output_file}")
        except ffmpeg.Error as e:
            self.show_warning(f"Error during conversion: {e}")

    def on_cancel_clicked(self, widget):
        self.destroy()

    def show_warning(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK,
            text="Warning",
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def show_info(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Information",
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

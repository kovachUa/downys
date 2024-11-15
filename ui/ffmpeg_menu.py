import gi
import subprocess
from gi.repository import Gtk

gi.require_version('Gtk', '3.0')

class FFmpegMenu(Gtk.Window):
    def __init__(self, parent_window):
        super().__init__(title="FFmpeg Settings")
        self.set_default_size(300, 300)  # Зменшено ширину вікна
        self.set_resizable(False)

        self.parent_window = parent_window
        self.set_modal(True)

        # Layout
        grid = Gtk.Grid(column_spacing=10, row_spacing=10, margin=10)
        self.add(grid)

        # Video Input File chooser
        self.input_file_label = Gtk.Label(label="Input File:")
        grid.attach(self.input_file_label, 0, 0, 1, 1)

        self.input_file_button = Gtk.Button(label="Choose File")
        self.input_file_button.connect("clicked", self.on_choose_input_file_clicked)
        grid.attach(self.input_file_button, 1, 0, 2, 1)

        # Label to show selected input file path
        self.input_file_path_label = Gtk.Label(label="No input file selected")
        grid.attach(self.input_file_path_label, 0, 1, 3, 1)

        # Output File chooser
        self.output_file_label = Gtk.Label(label="Output File:")
        grid.attach(self.output_file_label, 0, 2, 1, 1)

        self.output_file_button = Gtk.Button(label="Choose Save Location")
        self.output_file_button.connect("clicked", self.on_choose_output_file_clicked)
        grid.attach(self.output_file_button, 1, 2, 2, 1)

        # Label to show selected output file path
        self.output_file_path_label = Gtk.Label(label="No output file selected")
        grid.attach(self.output_file_path_label, 0, 3, 3, 1)

        # Format Selection ComboBox
        self.format_label = Gtk.Label(label="Format:")
        grid.attach(self.format_label, 0, 4, 1, 1)

        self.format_combo = Gtk.ComboBoxText()
        self.format_combo.append_text("mp4")
        self.format_combo.append_text("mp3")
        self.format_combo.append_text("avi")
        self.format_combo.append_text("mov")
        self.format_combo.append_text("wav")
        self.format_combo.append_text("flv")
        self.format_combo.append_text("mkv")
        self.format_combo.set_active(0)
        grid.attach(self.format_combo, 1, 4, 2, 1)

        # Audio Sample Rate (-ar) Entry
        self.sample_rate_label = Gtk.Label(label="Audio Sample Rate (-ar):")
        grid.attach(self.sample_rate_label, 0, 5, 1, 1)

        self.sample_rate_entry = Gtk.Entry()
        self.sample_rate_entry.set_placeholder_text("e.g., 44100")
        grid.attach(self.sample_rate_entry, 1, 5, 2, 1)

        # Audio Quality (-aq) Entry
        self.audio_quality_label = Gtk.Label(label="Audio Quality (-aq):")
        grid.attach(self.audio_quality_label, 0, 6, 1, 1)

        self.audio_quality_entry = Gtk.Entry()
        self.audio_quality_entry.set_placeholder_text("e.g., 2")
        grid.attach(self.audio_quality_entry, 1, 6, 2, 1)

        # Audio Channels (-ac) Entry
        self.audio_channels_label = Gtk.Label(label="Audio Channels (-ac):")
        grid.attach(self.audio_channels_label, 0, 7, 1, 1)

        self.audio_channels_entry = Gtk.Entry()
        self.audio_channels_entry.set_placeholder_text("e.g., 2")
        grid.attach(self.audio_channels_entry, 1, 7, 2, 1)

        # Convert button
        self.convert_button = Gtk.Button(label="Convert")
        self.convert_button.connect("clicked", self.on_convert_button_clicked)
        grid.attach(self.convert_button, 0, 8, 3, 1)

        # Cancel button
        self.cancel_button = Gtk.Button(label="Cancel")
        self.cancel_button.connect("clicked", self.on_cancel_button_clicked)
        grid.attach(self.cancel_button, 0, 9, 3, 1)

        # Initialize file paths
        self.input_file = None
        self.output_file = None

    def on_choose_input_file_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Choose Input File",
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
            buttons=("Cancel", Gtk.ResponseType.CANCEL, "Open", Gtk.ResponseType.OK)
        )
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.input_file = dialog.get_filename()
            self.input_file_path_label.set_text(f"Selected input: {self.input_file}")
        dialog.destroy()

    def on_choose_output_file_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Choose Output File",
            parent=self,
            action=Gtk.FileChooserAction.SAVE,
            buttons=("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        )
        dialog.set_current_name("output.mp4")
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.output_file = dialog.get_filename()
            selected_format = self.format_combo.get_active_text()
            if selected_format:
                self.output_file = self.output_file.rsplit(".", 1)[0] + f".{selected_format}"
            self.output_file_path_label.set_text(f"Save to: {self.output_file}")
        dialog.destroy()

    def on_convert_button_clicked(self, widget):
        if not self.input_file or not self.output_file:
            self.show_warning_dialog("Please select both input and output files.")
            return

        # Retrieve FFmpeg options
        sample_rate = self.sample_rate_entry.get_text()
        audio_quality = self.audio_quality_entry.get_text()
        audio_channels = self.audio_channels_entry.get_text()

        # Construct FFmpeg command with selected options
        command = f"ffmpeg -i \"{self.input_file}\""
        if sample_rate:
            command += f" -ar {sample_rate}"
        if audio_quality:
            command += f" -aq {audio_quality}"
        if audio_channels:
            command += f" -ac {audio_channels}"
        command += f" \"{self.output_file}\""

        print(f"Running command: {command}")
        try:
            subprocess.run(command, shell=True, check=True)
            self.show_info_dialog("Conversion completed successfully!")
        except subprocess.CalledProcessError as e:
            self.show_warning_dialog(f"Error during conversion: {e}")

        self.close()

    def on_cancel_button_clicked(self, widget):
        self.close()

    def show_warning_dialog(self, message):
        dialog = Gtk.MessageDialog(
            self, 0, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK, message
        )
        dialog.run()
        dialog.destroy()

    def show_info_dialog(self, message):
        dialog = Gtk.MessageDialog(
            self, 0, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, message
        )
        dialog.run()
        dialog.destroy()

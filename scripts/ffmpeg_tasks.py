import subprocess
import shlex
import os
import time
from gi.repository import GLib 

def log_message(message, level="INFO"):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp} FFMPEG LOG ({level}): {message}") # Використовуємо print для простоти

def run_ffmpeg_task(input_path, output_path, task_type=None, task_options=None, progress_callback=None, status_callback=None):
    """Виконує реальне завдання FFmpeg за допомогою subprocess."""
    task_label = task_type or "Невідоме завдання"
    if status_callback:
        GLib.idle_add(status_callback, f"Запуск FFmpeg завдання '{task_label}'...")

    try:
        subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log_message("FFmpeg знайдено.")
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
         error_msg = f"FFmpeg не знайдено або не працює: {e}"
         log_message(error_msg, level="ERROR")
         if status_callback:
             GLib.idle_add(status_callback, f"Помилка: {error_msg}")
         raise RuntimeError(error_msg) # Викидаємо помилку, щоб її спіймав головний потік

    if not os.path.isfile(input_path):
        error_msg = f"Вхідний файл FFmpeg не знайдено: {input_path}"
        log_message(error_msg, level="ERROR")
        if status_callback: GLib.idle_add(status_callback, f"Помилка: {error_msg}")
        raise FileNotFoundError(error_msg)

    command = ['ffmpeg', '-hide_banner', '-i', input_path]
    try:
        options = task_options or {}

        if task_type == "convert_simple":
            command.extend(['-c:v', 'libx264', '-c:a', 'aac', '-y'])
        elif task_type == "convert_format" and output_path.lower().endswith(".avi"):
             command.extend(['-c:v', 'mpeg4', '-qscale:v', '4', '-c:a', 'libmp3lame', '-qscale:a', '4', '-y'])
        elif task_type == "extract_audio_aac":
            command.extend(['-vn', '-c:a', 'aac', '-y'])
        elif task_type == "extract_audio_mp3":
            bitrate = options.get('audio_bitrate', '192k')
            command.extend(['-vn', '-c:a', 'libmp3lame', '-ab', str(bitrate), '-y'])
        elif task_type == "compress_bitrate":
            bitrate = options.get('bitrate')
            if not bitrate: raise ValueError("Бітрейт ('bitrate') не вказано для стиснення.")
            # Припускаємо, що стискаємо відео, аудіо - стандартно
            command.extend(['-c:v', 'libx264', '-b:v', str(bitrate), '-preset', 'medium', '-c:a', 'aac', '-b:a', '128k', '-y'])
        elif task_type == "adjust_resolution":
            width = options.get('width')
            height = options.get('height')
            if not width or not height: raise ValueError("Ширина ('width') або висота ('height') не вказані.")
            command.extend(['-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease', '-c:v', 'libx264', '-preset', 'medium', '-c:a', 'aac', '-y'])
        else:
            raise ValueError(f"Невідомий або нереалізований тип завдання FFmpeg: {task_type}")

        command.append(output_path)

    except Exception as e:
         error_msg = f"Помилка формування команди FFmpeg: {e}"
         log_message(error_msg, level="ERROR")
         if status_callback: GLib.idle_add(status_callback, f"Помилка параметрів: {e}")
         raise ValueError(error_msg)

    command_str = shlex.join(command)
    log_message(f"Executing FFmpeg command: {command_str}")
    if status_callback: GLib.idle_add(status_callback, "Обробка FFmpeg...")
    if progress_callback: GLib.idle_add(progress_callback, 0.05) # Початковий невеликий прогрес

    try:

        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, universal_newlines=True)

        stdout, stderr = process.communicate() 
        return_code = process.poll()           

        if return_code != 0:
            log_message(f"FFmpeg failed with code {return_code}", level="ERROR")
            error_details = "\n".join(stderr.splitlines()[-15:]) # Останні 15 рядків
            log_message(f"FFmpeg stderr (last 15 lines):\n{error_details}", level="ERROR")
            raise subprocess.CalledProcessError(return_code, command, output=stdout, stderr=stderr)

        # Успішне завершення
        log_message(f"FFmpeg completed successfully for {output_path}")
        if status_callback: GLib.idle_add(status_callback, "FFmpeg завдання виконано.")
        if progress_callback: GLib.idle_add(progress_callback, 1.0) # 100% прогрес

    except FileNotFoundError:
         # Хоча перевірка була вище, ця помилка може виникнути при Popen
         error_msg = "Помилка запуску FFmpeg: Команду не знайдено."
         log_message(error_msg, level="CRITICAL")
         if status_callback: GLib.idle_add(status_callback, error_msg)
         raise RuntimeError(error_msg)
    except subprocess.CalledProcessError as e:
         # Помилка виконання команди
         error_output = e.stderr or "Немає виводу помилки"
         last_lines = "\n".join(error_output.splitlines()[-10:])
         error_msg = f"Помилка виконання FFmpeg (код {e.returncode}):\n...\n{last_lines}"
         log_message(error_msg, level="ERROR")
         if status_callback: GLib.idle_add(status_callback, f"Помилка FFmpeg (код {e.returncode})")
         # Перевикидаємо як RuntimeError для обробки в головному потоці
         raise RuntimeError(error_msg)
    except Exception as e:
         # Інші неочікувані помилки під час виконання
         import traceback
         error_msg = f"Неочікувана помилка під час виконання FFmpeg: {e}\n{traceback.format_exc()}"
         log_message(error_msg, level="CRITICAL")
         if status_callback: GLib.idle_add(status_callback, f"Неочікувана помилка FFmpeg: {e}")
         raise RuntimeError(f"Неочікувана помилка під час виконання FFmpeg: {e}")

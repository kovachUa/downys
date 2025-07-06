import subprocess
import shlex
import os
import re
import logging

logger = logging.getLogger(__name__)

def get_media_duration(file_path):
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError) as e:
        logger.warning(f"Could not get duration for {file_path}: {e}")
        return 0

def run_ffmpeg_task(input_path, output_path, kwargs, comm_queue):
    task_type = kwargs.get('task_type')
    task_options = kwargs.get('task_options', {})

    def send_status(message):
        comm_queue.put({"type": "status", "value": message})

    def send_progress(fraction):
        comm_queue.put({"type": "progress", "value": fraction})

    def send_done(message):
        comm_queue.put({"type": "done", "value": message})

    def send_error(message):
        comm_queue.put({"type": "error", "value": message})

    try:
        send_status(f"Запуск FFmpeg: {task_type}...")
        
        if not os.path.isfile(input_path):
            raise FileNotFoundError(f"Вхідний файл не знайдено: {input_path}")
        
        duration_sec = get_media_duration(input_path)

        command = ['ffmpeg', '-hide_banner', '-i', input_path]
        
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
            command.extend(['-c:v', 'libx264', '-b:v', str(bitrate), '-preset', 'medium', '-c:a', 'aac', '-b:a', '128k', '-y'])
        elif task_type == "adjust_resolution":
            width = options.get('width')
            height = options.get('height')
            if not width or not height: raise ValueError("Ширина ('width') або висота ('height') не вказані.")
            command.extend(['-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease', '-c:v', 'libx264', '-preset', 'medium', '-c:a', 'aac', '-y'])
        else:
            raise ValueError(f"Невідомий тип завдання FFmpeg: {task_type}")

        command.extend(['-progress', 'pipe:1', '-nostats'])
        command.append(output_path)
        
        logger.info(f"Executing FFmpeg command: {' '.join(command)}")
        send_status("Обробка FFmpeg...")
        send_progress(0.05)

        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                   text=True, encoding='utf-8', errors='replace', bufsize=1)
        
        progress_pattern = re.compile(r"out_time_ms=(\d+)")
        
        for line in iter(process.stdout.readline, ''):
            if duration_sec > 0:
                match = progress_pattern.search(line)
                if match:
                    current_ms = int(match.group(1))
                    progress = min(1.0, (current_ms / 1000000) / duration_sec)
                    send_progress(progress)
        
        stderr_output = process.stderr.read()
        process.wait()
        
        if process.returncode != 0:
            error_msg = f"Помилка виконання FFmpeg (код {process.returncode}):\n{stderr_output}"
            raise RuntimeError(error_msg)

        send_progress(1.0)
        send_done("FFmpeg завдання виконано.")

    except Exception as e:
        import traceback
        error_msg = f"Неочікувана помилка під час виконання FFmpeg: {e}\n{traceback.format_exc()}"
        logger.critical(error_msg)
        send_error(error_msg)

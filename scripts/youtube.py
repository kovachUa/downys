import yt_dlp
import os
import sys
import time
from gi.repository import GLib # Import GLib

_last_downloaded_file_path = None
_spinner = ['|', '/', '-', '\\']
_spinner_index = 0

def log_message(message, level="INFO"):
    sys.stderr.write(f"YT-DLP LOG ({level}): {message}\n")
    sys.stderr.flush()

# Corrected progress_hook to simplify postprocessing progress and remove last_fraction logic
def progress_hook(d, progress_callback, status_callback): # Removed state parameter
    global _spinner_index

    # Ensure calls to callbacks are wrapped in GLib.idle_add as this hook runs in the YT-DLP thread
    if d['status'] == 'downloading':
        total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
        downloaded_bytes = d.get('downloaded_bytes', 0)

        fraction = 0.0
        if total_bytes and total_bytes > 0:
            fraction = min(1.0, max(0.0, downloaded_bytes / total_bytes))

        if progress_callback:
            GLib.idle_add(progress_callback, fraction)


        text = d.get('_speed_str', '...') + ' ETA ' + d.get('_eta_str', '...')
        if status_callback:
             spinner_char = _spinner[_spinner_index % len(_spinner)]
             _spinner_index += 1
             GLib.idle_add(status_callback, f"{spinner_char} Завантаження: {text}")


    elif d['status'] == 'extracting':
        log_message("Executing post-processor: extracting...")
        if status_callback:
             GLib.idle_add(status_callback, "Витягування метаданих...")
        # Set progress to a point indicating download is done, postprocessing started
        if progress_callback:
             GLib.idle_add(progress_callback, 0.90)


    elif d['status'] == 'merging':
        log_message("Executing post-processor: merging...")
        if status_callback:
             GLib.idle_add(status_callback, "Злиття відео та аудіо...")
        # Set progress to a point indicating merging is in progress
        if progress_callback:
             GLib.idle_add(progress_callback, 0.98)


    elif d['status'] == 'finished':
        _last_downloaded_file_path = d.get('filename')
        if _last_downloaded_file_path:
            log_message(f"Download finished: {_last_downloaded_file_path}")
        else:
             log_message("Download finished, but filename not in hook dict.", level="WARNING")

        if progress_callback:
            GLib.idle_add(progress_callback, 1.0) # Final progress


    elif d['status'] == 'error':
        error_message = d.get('error', 'Невідома помимилка yt-dlp')
        log_message(f"Error in hook: {error_message}", level="ERROR")
        # Error handling is primarily done by the try...except block in main.py wrapper


# Added progress_callback and status_callback parameters
def download_youtube_video_with_progress(video_url, output_dir, progress_callback=None, status_callback=None):
    global _last_downloaded_file_path
    _last_downloaded_file_path = None

    log_message(f"Attempting to download: {video_url} to {output_dir}")
    os.makedirs(output_dir, exist_ok=True)

    # Pass the callbacks to the hook function.
    # The hook itself will now use GLib.idle_add.
    # No need for state object here anymore.
    hook = lambda d: progress_hook(d, progress_callback, status_callback)


    ydl_opts = {
        # Request formats prioritizing MP4 video and AAC audio,
        # then any best video+audio pair, then overall best.
        # This is a robust format string.
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=aac]/bestvideo+bestaudio/best',
        'outtmpl': f'{output_dir}/%(uploader)s/%(title)s.%(ext)s',
        'postprocessors': [
            # Ensure the final container is MP4. This will trigger FFmpeg if necessary.
            # This is often sufficient for merging best video/audio if they are incompatible containers.
            {'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'},
            # No need for separate FFmpegExtractAudio or FFmpegMerger with args here.
            # FFmpegVideoConvertor often handles the audio conversion/passthrough needed for the preferred video format.
        ],
        'progress_hooks': [hook], # Use our wrapper hook
        'quiet': True, # Suppress standard yt-dlp output
        'logtostderr': True, # Direct logs to stderr (useful for debugging)
        'verbose': False, # Keep verbose False unless debugging
        'no_warnings': False, # Set to False temporarily to see yt-dlp warnings if issue persists
        'retries': 5,
        'fragment_retries': 5,
        'ignoreerrors': False, # Do not ignore errors, let them raise exceptions
        'sleep_interval': 0.02,
        'max_sleep_interval': 0.05,
        # Consider adding 'ffmpeg_location': '/path/to/ffmpeg' if ffmpeg is not in PATH
        # Add a user agent to potentially avoid some blocking issues
        'useragent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }

    # If status_callback is available, send an initial status update
    if status_callback:
         GLib.idle_add(status_callback, f"Підготовка до завантаження: {video_url}...")

    video_url_to_process = video_url # Use the provided URL


    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            log_message(f"Starting yt-dlp process for: {video_url_to_process}")
            # extract_info with download=True triggers the download and postprocessing hooks
            info_dict = ydl.extract_info(video_url_to_process, download=True)
            log_message("yt-dlp extract_info with download=True finished.")

        # The final path should be obtainable from the info_dict after postprocessing.
        # The 'finished' hook's filename might be the path *before* postprocessing,
        # depending on yt-dlp version and options. Using prepare_filename on info_dict is safer *after* the call.
        final_path = None
        if info_dict:
            try:
                 # prepare_filename should give the path based on outtmpl *after* postprocessors
                 # assuming postprocessors don't move the file to a completely different directory
                 # or rename it in a way not reflected by outtmpl and the info_dict metadata.
                 filepath_from_info = ydl.prepare_filename(info_dict)
                 if os.path.exists(filepath_from_info):
                      log_message(f"Found file using prepare_filename: {filepath_from_info}", level="INFO")
                      final_path = filepath_from_info
                 else:
                      log_message(f"prepare_filename path does not exist: {filepath_from_info}.", level="ERROR")

            except Exception as info_e:
                 log_message(f"Error using prepare_filename: {info_e}.", level="ERROR")

        # As a last resort, check the path set by the 'finished' hook if info_dict failed
        if not final_path and _last_downloaded_file_path and os.path.exists(_last_downloaded_file_path):
             log_message(f"Using path from hook as fallback: {_last_downloaded_file_path}", level="WARNING")
             final_path = _last_downloaded_file_path
        elif not final_path:
             log_message("Neither prepare_filename nor hook provided a valid path.", level="ERROR")


        if not final_path or not os.path.exists(final_path):
             # If we still don't have a path, raise an error
             raise RuntimeError("Не вдалося отримати шлях до завантаженого файлу після завершення yt-dlp.")

        log_message(f"Returning downloaded file path: {final_path}")
        return final_path

    except yt_dlp.utils.DownloadError as e:
        log_message(f"yt-dlp DownloadError: {e}", level="ERROR")
        # Re-raise with a consistent user-friendly message
        raise RuntimeError(f"Помилка завантаження YouTube: {e}")
    except Exception as e:
        log_message(f"Unexpected error during yt-dlp operation: {e}", level="ERROR")
        # Re-raise with a consistent user-friendly message
        raise RuntimeError(f"Неочікувана помилка yt-dlp: {e}")

import yt_dlp
import os
import sys
import time
import re
import pprint 
from gi.repository import GLib

_last_downloaded_file_path = None
_spinner = ['|', '/', '-', '\\']
_spinner_index = 0

def log_message(message, level="INFO"):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    sys.stderr.write(f"{timestamp} YT-DLP LOG ({level}): {message}\n")
    sys.stderr.flush()

def progress_hook(d, progress_callback, status_callback):
    global _spinner_index

    if d['status'] == 'downloading':
        total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
        downloaded_bytes = d.get('downloaded_bytes', 0)
        fraction = 0.0
        if total_bytes and total_bytes > 0: fraction = min(1.0, max(0.0, downloaded_bytes / total_bytes))
        if progress_callback: GLib.idle_add(progress_callback, fraction)

        filename = d.get('filename', 'файл')
        short_filename = os.path.basename(filename)
        short_filename = re.sub(r'\.f\d+$', '', short_filename)
        if short_filename.endswith('.part'): short_filename = short_filename[:-5]
        speed_str = d.get('_speed_str', '...').strip()
        eta_str = d.get('_eta_str', '...').strip()
        percent_str = d.get('_percent_str', f'{int(fraction*100)}%').strip()
        status_msg = f"Завантаження ({percent_str}): {short_filename} [{speed_str} ETA {eta_str}]"

        if status_callback:
             spinner_char = _spinner[_spinner_index % len(_spinner)]
             _spinner_index += 1
             GLib.idle_add(status_callback, f"{spinner_char} {status_msg}")

    elif d['status'] == 'error':
        error_message = d.get('error', 'Невідома помилка yt-dlp')
        log_message(f"Error in hook: {error_message}", level="ERROR")

    elif d['status'] == 'finished':
        filename = d.get('filename')
        if filename:
             # Не перезаписуємо _last_downloaded_file_path, якщо це тимчасовий файл
             if not filename.endswith(('.part', '.ytdl', '.temp')):
                 log_message(f"Finished downloading final/merged file: {filename}")
                 _last_downloaded_file_path = filename
             else:
                 log_message(f"Finished downloading fragment/temporary file: {filename}")
             if status_callback: GLib.idle_add(status_callback, f"Завершено етап: {os.path.basename(filename)}")
        else:
             log_message("Download part finished, filename not in hook dict.", level="WARNING")

    elif '_type' in d and d['_type'] == 'post_process':
         postprocessor_name = d.get('postprocessor')
         stage = d.get('status', 'running')
         status_msg = f"Пост-обробка ({postprocessor_name}): {stage}"
         if stage == 'started' or stage == 'running':
              if progress_callback: GLib.idle_add(progress_callback, 0.95)
         log_message(f"Postprocessor {postprocessor_name}: {stage}")
         if status_callback: GLib.idle_add(status_callback, status_msg)


def download_youtube_video_with_progress(video_url, output_dir, progress_callback=None, status_callback=None):
    global _last_downloaded_file_path
    _last_downloaded_file_path = None # Reset before download

    log_message(f"Attempting to download: {video_url} to {output_dir}")
    os.makedirs(output_dir, exist_ok=True)

    hook = lambda d: progress_hook(d, progress_callback, status_callback)

    cookies_file_path = os.path.join(os.path.expanduser("~"), "youtube_cookies.txt")
    cookies_found = os.path.exists(cookies_file_path)
    if cookies_found:
        log_message(f"Using cookies file: {cookies_file_path}")
    else:
        log_message(f"Cookies file not found at: {cookies_file_path}. Download might fail for restricted videos.")

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': f'{output_dir}/%(title)s [%(id)s].%(ext)s',
        'retries': 5, 'fragment_retries': 5, 'ignoreerrors': False,
        'progress_hooks': [hook], 'quiet': True, 'logtostderr': True, 'verbose': False, 'no_warnings': False,
        'sleep_interval': 2, 'max_sleep_interval': 5,
        'useragent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36',
        'merge_output_format': 'mkv',
    }
    if cookies_found:
        ydl_opts['cookiefile'] = cookies_file_path
        ydl_opts['extractor-args'] = 'youtube:player_client=default,-web_creator'
        log_message("Applying extractor-args 'youtube:player_client=default,-web_creator' due to cookies presence.")

    if status_callback:
         GLib.idle_add(status_callback, f"Підготовка до завантаження: {video_url}...")

    final_path = None
    info_dict = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            log_message(f"Starting yt-dlp process for: {video_url} with options: { {k: v for k, v in ydl_opts.items() if k != 'progress_hooks'} }")
            info_dict = ydl.extract_info(video_url, download=True) # download=True is crucial
            log_message("yt-dlp extract_info with download=True finished.")

            if info_dict:
                log_message(f"Info dict received. Keys: {list(info_dict.keys())}")
                log_msg_info = {
                    'id': info_dict.get('id'), 'title': info_dict.get('title'),
                    'filepath': info_dict.get('filepath'), # Often set after download/merge
                    '_filename': info_dict.get('_filename'), # Sometimes contains final path
                    'filename': info_dict.get('filename'), # Can be set by some extractors
                    'requested_downloads': info_dict.get('requested_downloads'),
                    'ext': info_dict.get('ext'), 'format': info_dict.get('format')
                }
                log_message(f"Relevant info dict fields:\n{pprint.pformat(log_msg_info)}")

                if info_dict.get('filepath') and os.path.exists(info_dict['filepath']):
                    final_path = info_dict['filepath']
                    log_message(f"Priority 1: Final path from info_dict['filepath']: {final_path}")

                if not final_path and info_dict.get('_filename') and os.path.exists(info_dict['_filename']):
                     final_path = info_dict['_filename']
                     log_message(f"Priority 2: Final path from info_dict['_filename']: {final_path}")

                if not final_path and info_dict.get('filename') and os.path.exists(info_dict['filename']):
                     final_path = info_dict['filename']
                     log_message(f"Priority 3: Final path from info_dict['filename']: {final_path}")

                if not final_path:
                     log_message(f"Checking last path from 'finished' hook: {_last_downloaded_file_path}")
                     if _last_downloaded_file_path and os.path.exists(_last_downloaded_file_path) and \
                        not _last_downloaded_file_path.endswith(('.part', '.ytdl', '.temp')):
                           final_path = _last_downloaded_file_path
                           log_message(f"Priority 4: Using non-temporary path from 'finished' hook: {final_path}")
                     elif _last_downloaded_file_path:
                         log_message(f"Path from hook '{_last_downloaded_file_path}' does not exist or is temporary.", level="WARNING")

                if not final_path:
                    log_message("Attempting prepare_filename...")
                    try:
                         prepared_path = ydl.prepare_filename(info_dict)
                         log_message(f"prepare_filename result: {prepared_path}")
                         if os.path.exists(prepared_path):
                              final_path = prepared_path
                              log_message(f"Priority 5: Final path confirmed using prepare_filename: {final_path}")
                         else:
                              log_message(f"Path from prepare_filename does not exist: {prepared_path}", level="WARNING")
                    except Exception as e:
                         log_message(f"Error using prepare_filename: {e}", level="ERROR")

                if not final_path:
                     log_message("Final path still not determined. Searching directory by ID...", level="WARNING")
                     video_id = info_dict.get('id')
                     found_file = None
                     if video_id:
                          try:
                              log_message(f"Searching for files containing '{video_id}' in '{output_dir}'")
                              dir_list = os.listdir(output_dir)
                              log_message(f"Directory contents: {dir_list}")
                              for f in dir_list:
                                  if video_id in f and not f.endswith(('.part', '.ytdl', '.temp', '.mkv.frag', '.mp4.frag')): # Додано .frag
                                       potential_path = os.path.join(output_dir, f)
                                       if os.path.isfile(potential_path):
                                            found_file = potential_path
                                            log_message(f"Priority 6: Found potential file by searching ID: {found_file}")
                                            break
                                       else: found_file = None
                          except Exception as search_e:
                              log_message(f"Error searching directory for file: {search_e}", level="ERROR")
                     if found_file: final_path = found_file
                     else: log_message("Could not find file by searching ID.", level="ERROR")

           
            if not final_path:
                 log_message("FATAL: Could not determine final path by any method.", level="CRITICAL")
                 last_hook_path = _last_downloaded_file_path or "None"
                 info_keys = list(info_dict.keys()) if info_dict else "None"
                 raise RuntimeError(f"Не вдалося отримати шлях до завантаженого файлу після завершення yt-dlp. Last hook path: {last_hook_path}. Info dict keys: {info_keys}")

            
            if not os.path.exists(final_path):
                  log_message(f"FATAL: Determined path '{final_path}' does not exist!", level="CRITICAL")
                  raise RuntimeError(f"Визначений шлях '{final_path}' не вказує на існуючий файл після завантаження.")


        log_message(f"Download process complete. Returning path: {final_path}")
        if progress_callback: GLib.idle_add(progress_callback, 1.0)
        if status_callback: GLib.idle_add(status_callback, f"Завантаження завершено: {os.path.basename(final_path)}")
        return final_path

    except yt_dlp.utils.DownloadError as e:
        log_message(f"yt-dlp DownloadError: {e}", level="ERROR")
        error_details = str(e)
        if error_details.startswith("ERROR: "): error_details = error_details[len("ERROR: "):]
        # Додаємо URL до повідомлення про помилку
        raise RuntimeError(f"Помилка завантаження YouTube ({video_url}): {error_details}")
    except Exception as e:
        import traceback
        log_message(f"Unexpected error during yt-dlp operation: {traceback.format_exc()}", level="CRITICAL")
        raise RuntimeError(f"Неочікувана помилка yt-dlp: {e}")

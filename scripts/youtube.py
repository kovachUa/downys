# scripts/youtube.py

import yt_dlp
import os
import re
import time
import traceback
from typing import Optional, Callable, Dict, Any, List, Union

# Функція для очищення ANSI кодів та пробілів
def clean_string(s: str) -> str:
    if not isinstance(s, str):
        return ""
    # Видалення ANSI escape кодів кольору
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    cleaned = ansi_escape.sub('', s)
    # Заміна множинних пробілів на один та видалення пробілів на початку/кінці
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

# Helper to create default YDL options (avoid repetition)
def _get_default_ydl_opts() -> Dict[str, Any]:
    return {
        'nocheckcertificate': True,
        'ignoreerrors': True, # Continue processing playlist items on error
        'quiet': True,        # Suppress yt-dlp's direct stdout/stderr output
        'verbose': False,
        'no_warnings': True,
        'continuedl': True,   # Enables resuming (report_resuming_byte)
        # 'restrictfilenames': True, # Optional: Limit characters in filenames
    }

# NEW FUNCTION: Extract information without downloading
def extract_youtube_info(
    url: str,
    extra_opts: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Отримує метадані про відео або плейлист за вказаною URL-адресою, не завантажуючи файл.
    Corresponds to the concept of yt-dlp's extract_info(url, download=False).

    Args:
        url: URL відео або плейлиста YouTube.
        extra_opts: Додаткові параметри для yt-dlp.

    Returns:
        Словник з інформацією про відео/плейлист або None у разі помилки.
    """
    ydl_opts = _get_default_ydl_opts()
    # We specifically want info extraction, not download
    ydl_opts['extract_flat'] = 'in_playlist' # Get basic info for playlist entries quickly
    ydl_opts['skip_download'] = True

    if extra_opts:
        ydl_opts.update(extra_opts)

    print(f"Вилучення інформації для: {url}")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Use extract_info directly with download=False implied by skip_download
            info_dict = ydl.extract_info(url, download=False)
            return info_dict
    except yt_dlp.utils.DownloadError as e:
        error_message = clean_string(str(e))
        match = re.search(r'ERROR: (.*?)(?:;|$)', error_message, re.IGNORECASE)
        if match: error_message = match.group(1).strip()
        print(f"Помилка вилучення інформації yt-dlp: {error_message}")
        return None
    except Exception as e:
        print(f"Неочікувана помилка під час вилучення інформації: {e}")
        traceback.print_exc()
        return None


# MODIFIED FUNCTION: Renamed and accepts list/single URL
def download_youtube_media(
    urls: Union[str, List[str]], # Changed to accept list or single string
    output_dir: str,
    format_selection: str = "best",
    audio_format_override: Optional[str] = None,
    download_subs: bool = False,
    sub_langs: Optional[str] = None,
    embed_subs: bool = False,
    status_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[float], None]] = None
):
    """
    Завантажує відео/аудіо або плейлисти з YouTube з наданого URL або списку URL.
    Corresponds to the high-level concept of yt-dlp's download(url_list).
    Reporting is handled via callbacks based on internal yt-dlp reports.

    Args:
        urls: Один URL або список URL відео/плейлистів YouTube.
        output_dir: Базова директорія для збереження файлів.
        format_selection: Вибір формату ('best', 'best_mp4', 'original', 'audio_best', 'audio_mp3', 'audio_m4a').
        audio_format_override: Перевизначення аудіо кодека для аудіо форматів.
        download_subs: Чи завантажувати субтитри.
        sub_langs: Бажані мови субтитрів (рядок через кому).
        embed_subs: Чи вбудовувати субтитри у відеофайл.
        status_callback: Функція для оновлення статусу (отримує звіти типу report_*).
        progress_callback: Функція для оновлення прогресу (отримує звіти типу report_download_progress).
    """

    def _safe_callback(callback: Optional[Callable], *args: Any, **kwargs: Any):
        if callback and callable(callback):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                print(f"Помилка під час виклику callback {callback.__name__}: {e}")

    _start_time = time.time()
    _last_reported_progress = -1.0

    # progress_hook remains the central place for reporting
    def progress_hook(d: Dict[str, Any]):
        nonlocal _start_time, _last_reported_progress
        status = d.get('status')
        progress_fraction = -1.0

        # --- Downloading status --- (Handles report_download_progress)
        if status == 'downloading':
            total_bytes_estimate = d.get('total_bytes_estimate')
            total_bytes = d.get('total_bytes')
            downloaded_bytes = d.get('downloaded_bytes')
            speed_str = clean_string(d.get('_speed_str', 'N/A'))
            eta_str = clean_string(d.get('_eta_str', 'N/A'))
            percent_str = clean_string(d.get('_percent_str', '0.0%')).replace('%', '')

            try:
                progress_fraction = float(percent_str) / 100.0
            except ValueError:
                 # Fallback calculation if percentage string is invalid
                 if total_bytes and downloaded_bytes is not None and total_bytes > 0:
                      progress_fraction = max(0.0, min(1.0, downloaded_bytes / total_bytes))
                 elif total_bytes_estimate and downloaded_bytes is not None and total_bytes_estimate > 0:
                     progress_fraction = max(0.0, min(1.0, downloaded_bytes / total_bytes_estimate))

            if progress_fraction >= 0 and abs(progress_fraction - _last_reported_progress) > 0.001:
                 _safe_callback(progress_callback, progress_fraction)
                 _last_reported_progress = progress_fraction

            info = d.get('info_dict') # Info from internal extract_info
            display_filename = info.get('title', None) if info else None
            if not display_filename:
                # filename from internal prepare_filename logic
                display_filename = os.path.basename(d.get('filename', 'Невідомий файл'))

            # Report overall progress (Corresponds to report_progress)
            status_msg = f"Завантаження '{display_filename}': {percent_str}% ({speed_str}, ETA: {eta_str})"
            _safe_callback(status_callback, status_msg)
            # Note: Resuming reports (report_resuming_byte etc.) handled internally by yt-dlp

        # --- Error status --- (Corresponds to report_retry failure)
        elif status == 'error':
            filename = os.path.basename(d.get('filename', 'Невідомий файл'))
            error_msg = f"Помилка завантаження '{filename}'" # Simplified message
            _safe_callback(status_callback, error_msg)
            _last_reported_progress = 0.0
            _safe_callback(progress_callback, 0.0)
            # Full error is caught in the main try/except block

        # --- Finished status --- (Handles report_destination, report_file_already_downloaded)
        elif status == 'finished':
            info = d.get('info_dict')
            display_filename = info.get('title', None) if info else None
            final_filename = d.get('filename', 'Невідомий файл') # The actual destination
            if not display_filename:
                display_filename = os.path.basename(final_filename)

            elapsed = d.get('elapsed', time.time() - _start_time)
            total_bytes = d.get('total_bytes') or d.get('downloaded_bytes')
            size_str = f"{total_bytes / (1024 * 1024):.2f} MB" if total_bytes else "N/A"

            # Report completion and destination file name
            finish_msg = f"Завершено '{display_filename}' ({size_str}) за {elapsed:.2f} сек."
            _safe_callback(status_callback, finish_msg)

            if _last_reported_progress < 1.0:
                _safe_callback(progress_callback, 1.0)
            _last_reported_progress = 1.0
            _start_time = time.time() # Reset timer for next file in list/playlist

        # --- Postprocessing status --- (Part of internal process_info)
        elif d.get('_type') == 'postprocessor' and status == 'started':
             processor = d.get('postprocessor')
             info = d.get('info_dict')
             display_filename = info.get('title', 'файл') if info else 'файл'
             status_msg = f"Обробка '{display_filename}' ({processor})..."
             _safe_callback(status_callback, status_msg)
             current_progress = max(1.0, _last_reported_progress) if _last_reported_progress >= 0 else 1.0
             _safe_callback(progress_callback, current_progress)
             _last_reported_progress = 1.0


    # ---- Setup yt-dlp options ----
    ydl_opts = _get_default_ydl_opts() # Start with defaults
    ydl_opts['progress_hooks'] = [progress_hook]
    # Filename template (Drives internal prepare_filename)
    ydl_opts['outtmpl'] = os.path.join(output_dir, '%(uploader)s', '%(title)s.%(ext)s')

    # --- Format Selection ---
    is_audio_only = format_selection.startswith('audio_')
    format_code = ''
    pp_opts: List[Dict[str, Any]] = []
    # Clear potentially conflicting old options
    if 'merge_output_format' in ydl_opts: del ydl_opts['merge_output_format']
    if 'extract_audio' in ydl_opts: del ydl_opts['extract_audio']
    if 'postprocessors' in ydl_opts: del ydl_opts['postprocessors']
    if 'audioformat' in ydl_opts: del ydl_opts['audioformat']

    if format_selection == 'best':
        format_code = 'bestvideo+bestaudio/best'
    elif format_selection == 'best_mp4':
        format_code = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        ydl_opts['merge_output_format'] = 'mp4'
    elif format_selection == 'original':
        format_code = 'best[vcodec!=none][acodec!=none]/best'
    elif is_audio_only:
        format_code = 'bestaudio/best'
        target_audio_codec = None
        if format_selection == 'audio_mp3': target_audio_codec = 'mp3'
        elif format_selection == 'audio_m4a': target_audio_codec = 'aac'
        if audio_format_override and audio_format_override != 'best':
            target_audio_codec = audio_format_override

        if target_audio_codec and target_audio_codec != 'best':
            pp_opts.append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': target_audio_codec,
                'preferredquality': '192',
            })
            ydl_opts['audioformat'] = target_audio_codec # Inform yt-dlp about the target
            ydl_opts['extract_audio'] = True # Ensure extraction happens

    ydl_opts['format'] = format_code
    if pp_opts:
        ydl_opts['postprocessors'] = pp_opts

    # --- Subtitle Handling ---
    # ... (subtitle logic remains the same) ...
    sub_langs_list = []
    ydl_opts['writesubtitles'] = False
    ydl_opts['writeautomaticsub'] = False
    ydl_opts['embedsubtitles'] = False
    if 'subtitleslangs' in ydl_opts: del ydl_opts['subtitleslangs']

    if download_subs:
        ydl_opts['writesubtitles'] = True
        ydl_opts['writeautomaticsub'] = True
        if sub_langs:
            sub_langs_list = [lang.strip() for lang in sub_langs.split(',') if lang.strip()]
        if not sub_langs_list:
             sub_langs_list = ['uk', 'en']
        ydl_opts['subtitleslangs'] = sub_langs_list

        if embed_subs and not is_audio_only:
            ydl_opts['embedsubtitles'] = True
            # Prefer MKV for embedding if not explicitly MP4
            # if ydl_opts.get('merge_output_format') != 'mp4':
            #    ydl_opts['merge_output_format'] = 'mkv' # Auto handled usually

    # --- Execute Download ---
    url_list = []
    if isinstance(urls, str):
        url_list = [urls]
        _safe_callback(status_callback, f"Запуск завантаження для: {urls}")
    elif isinstance(urls, list):
        url_list = urls
        _safe_callback(status_callback, f"Запуск завантаження для {len(urls)} URL...")
    else:
        _safe_callback(status_callback, "Помилка: Неправильний тип URL (очікується рядок або список).")
        _safe_callback(progress_callback, 0.0)
        return # Stop if URLs are invalid type

    if not url_list:
        _safe_callback(status_callback, "Помилка: Список URL порожній.")
        _safe_callback(progress_callback, 0.0)
        return

    _safe_callback(progress_callback, 0.0)
    _last_reported_progress = 0.0

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Pass the list of URLs to the download method
            ydl.download(url_list)

        _safe_callback(status_callback, "Усі завдання в черзі завершено.")
        if _last_reported_progress < 1.0:
             _safe_callback(progress_callback, 1.0)

    except yt_dlp.utils.DownloadError as e:
        # Handle final download errors (after retries etc.)
        error_message = clean_string(str(e))
        match = re.search(r'ERROR: (.*?)(?:;|$)', error_message, re.IGNORECASE)
        if match: error_message = match.group(1).strip()

        error_msg_log = f"Помилка завантаження yt-dlp: {error_message}"
        print(error_msg_log)
        _safe_callback(status_callback, error_msg_log)
        if _last_reported_progress >= 0:
            _safe_callback(progress_callback, _last_reported_progress)
        else:
            _safe_callback(progress_callback, 0.0)
    except Exception as e:
        # Handle other unexpected errors
        error_message = f"Неочікувана помилка під час завантаження: {e}"
        print(error_message)
        traceback.print_exc()
        _safe_callback(status_callback, error_message)
        if _last_reported_progress >= 0:
            _safe_callback(progress_callback, _last_reported_progress)
        else:
            _safe_callback(progress_callback, 0.0)



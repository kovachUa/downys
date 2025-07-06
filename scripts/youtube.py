import yt_dlp
import os
import re
import time
import logging
from typing import Optional, Callable, Dict, Any, List, Union
from yt_dlp.utils import download_range_func

logger = logging.getLogger(__name__)

def _get_default_ydl_opts() -> Dict[str, Any]:
    return {
        'nocheckcertificate': True,
        'quiet': True,
        'verbose': False,
        'no_warnings': True,
        'continuedl': True,
    }

def get_youtube_info(url: str, extra_opts: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    ydl_opts = _get_default_ydl_opts()
    ydl_opts['extract_flat'] = 'in_playlist'
    ydl_opts['skip_download'] = True
    if extra_opts:
        ydl_opts.update(extra_opts)
    
    logger.info(f"Вилучення інформації для URL: {url}")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error(f"Помилка вилучення інформації yt-dlp для '{url}': {e}", exc_info=True)
        return None

def download_youtube_media(kwargs, comm_queue):
    url = kwargs.get('url')
    output_dir = kwargs.get('output_dir')
    download_mode = kwargs.get('download_mode', 'default')
    format_selection = kwargs.get('format_selection', "best_mp4")
    max_resolution = kwargs.get('max_resolution')
    audio_quality = kwargs.get('audio_quality', 5)
    playlist_start = kwargs.get('playlist_start', 0)
    playlist_end = kwargs.get('playlist_end', 0)
    concurrent_fragments = kwargs.get('concurrent_fragments', 4)
    skip_downloaded = kwargs.get('skip_downloaded', False)
    time_start = kwargs.get('time_start')
    time_end = kwargs.get('time_end')
    clean_filename = kwargs.get('clean_filename', False)
    ignore_errors = kwargs.get('ignore_errors', True)
    download_subs = kwargs.get('download_subs', False)
    sub_langs = kwargs.get('sub_langs')
    embed_subs = kwargs.get('embed_subs', False)

    def send_status(message):
        comm_queue.put({"type": "status", "value": message})
    def send_progress(fraction):
        comm_queue.put({"type": "progress", "value": fraction})
    def send_done(message):
        comm_queue.put({"type": "done", "value": message})
    def send_error(message):
        comm_queue.put({"type": "error", "value": message})

    _last_reported_progress = -1.0

    def progress_hook(d: Dict[str, Any]):
        nonlocal _last_reported_progress
        status = d.get('status')
        if status == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes')
            if total and downloaded is not None:
                fraction = min(1.0, downloaded / total)
                if abs(fraction - _last_reported_progress) > 0.005:
                    send_progress(fraction)
                    _last_reported_progress = fraction
            
            filename = d.get('filename') or "..."
            title = os.path.basename(filename)
            percent_str = d.get('_percent_str', '')
            speed_str = d.get('_speed_str', '')
            eta_str = d.get('_eta_str', '')
            send_status(f"Завантаження '{title}': {percent_str} ({speed_str}, ETA: {eta_str})")

        elif status == 'finished':
            send_progress(1.0)
            send_status(f"Завершено: {os.path.basename(d.get('filename', ''))}")
        elif status == 'error':
            send_status("Помилка завантаження...")

    try:
        ydl_opts = _get_default_ydl_opts()
        ydl_opts['ignoreerrors'] = ignore_errors
        ydl_opts['progress_hooks'] = [progress_hook]

        if download_mode == 'default':
            ydl_opts['outtmpl'] = os.path.join(output_dir, '%(channel,uploader)s', '%(title)s.%(ext)s')
        else: # music, flat_playlist, single_flat all go into one folder
             ydl_opts['outtmpl'] = os.path.join(output_dir, '%(title)s.%(ext)s')
        
        is_audio_only = download_mode == 'music'
        if is_audio_only:
            ydl_opts['format'] = f'bestaudio/best'
            ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': str(audio_quality)}]
        else:
            res_filter = ""
            if max_resolution and max_resolution != "best":
                res_filter = f"[height<={max_resolution}]"
            
            if format_selection == 'best_mp4':
                ydl_opts['format'] = f'bestvideo{res_filter}[ext=mp4]+bestaudio[ext=m4a]/best{res_filter}[ext=mp4]/best{res_filter}'
                ydl_opts['merge_output_format'] = 'mp4'
            else: # best webm/mkv
                ydl_opts['format'] = f'bestvideo{res_filter}+bestaudio/best{res_filter}'
                
        if download_mode == 'single_flat':
            ydl_opts['noplaylist'] = True

        if playlist_start > 0: ydl_opts['playliststart'] = playlist_start
        if playlist_end > 0: ydl_opts['playlistend'] = playlist_end

        if concurrent_fragments > 1: ydl_opts['concurrent_fragment_downloads'] = concurrent_fragments

        if skip_downloaded:
            archive_file = os.path.join(output_dir, '.yt-dlp-archive.txt')
            ydl_opts['download_archive'] = archive_file
        
        if time_start or time_end:
            ydl_opts['download_ranges'] = download_range_func(None, [(time_start or "00:00:00", time_end)])

        if download_subs and not is_audio_only:
            ydl_opts['writesubtitles'] = True
            ydl_opts['writeautomaticsub'] = True
            ydl_opts['subtitleslangs'] = [lang.strip() for lang in (sub_langs or 'uk,en').split(',')]
            if embed_subs:
                ydl_opts['embedsubtitles'] = True

        logger.info(f"Запуск yt-dlp з параметрами: {ydl_opts}")
        send_status(f"Запуск yt-dlp для {url}...")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            download_list = [url] if isinstance(url, str) else url
            ydl.download(download_list)
        
        send_done("Завантаження YouTube завершено.")

    except Exception as e:
        import traceback
        error_msg = f"Критична помилка yt-dlp: {e}\n{traceback.format_exc()}"
        logger.critical(error_msg)
        send_error(error_msg)

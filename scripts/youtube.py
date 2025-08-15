import yt_dlp
import os
import logging
from typing import Optional, Dict, Any
from yt_dlp.utils import download_range_func

logger = logging.getLogger(__name__)

stop_requested = False  # Флаг для зупинки завантаження


def stop_download():
    """Викликається для зупинки активного завантаження."""
    global stop_requested
    stop_requested = True
    logger.info("Зупинка завантаження запрошена користувачем.")


def log_available_formats(info):
    if not info or 'formats' not in info:
        return
    formats = info.get('formats', [])
    logger.debug("========== Доступні формати ==========")
    for f in formats:
        if f.get('vcodec') == 'none':
            continue
        logger.debug(
            f"ID: {f.get('format_id', 'N/A'):<10} | "
            f"Ext: {f.get('ext', 'N/A'):<8} | "
            f"Res: {f.get('height')}p | "
            f"VCodec: {f.get('vcodec', 'N/A'):<15} | "
            f"ACodec: {f.get('acodec', 'none'):<10} | "
            f"TBR: {f.get('tbr')} kbps"
        )
    logger.debug("======================================")


def _get_default_ydl_opts() -> Dict[str, Any]:
    return {
        'nocheckcertificate': True,
        'quiet': False,   # показуємо хід роботи
        'verbose': True,  # детальніше логування
        'no_warnings': False,
        'continuedl': True
    }


def get_youtube_info(url: str, extra_opts: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    ydl_opts = _get_default_ydl_opts()
    ydl_opts.update({'extract_flat': 'in_playlist', 'skip_download': True})
    if extra_opts:
        ydl_opts.update(extra_opts)

    logger.info(f"Вилучення інформації для URL: {url}")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if logger.isEnabledFor(logging.DEBUG) and info and info.get('_type') != 'playlist':
                full_info_opts = ydl_opts.copy()
                full_info_opts['extract_flat'] = False
                with yt_dlp.YoutubeDL(full_info_opts) as ydl_full:
                    log_available_formats(ydl_full.extract_info(url, download=False))
            return info
    except Exception as e:
        logger.error(f"Помилка вилучення інформації yt-dlp: {e}", exc_info=False)
        return None


def download_youtube_media(kwargs, comm_queue):
    global stop_requested
    stop_requested = False

    url, output_dir = kwargs.get('url'), kwargs.get('output_dir')
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
    force_mp4 = kwargs.get('force_mp4', False)
    avoid_av1 = kwargs.get('avoid_av1', True)
    prefer_h264 = kwargs.get('prefer_h264', True)
    max_bitrate = kwargs.get('max_bitrate')

    def send_status(message): comm_queue.put({"type": "status", "value": message})
    def send_progress(fraction): comm_queue.put({"type": "progress", "value": fraction})
    def send_done(message): comm_queue.put({"type": "done", "value": message})
    def send_error(message): comm_queue.put({"type": "error", "value": message})

    _last_reported_progress = -1.0

    def progress_hook(d: Dict[str, Any]):
        global stop_requested
        if stop_requested:
            raise yt_dlp.utils.DownloadError("Завантаження зупинено користувачем.")
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            if total:
                fraction = min(1.0, d.get('downloaded_bytes', 0) / total)
                if abs(fraction - _last_reported_progress) > 0.005:
                    send_progress(fraction)
            send_status(f"Завантаження: {d.get('_percent_str', '')} ({d.get('_speed_str', '')})")
        elif d['status'] == 'finished':
            send_progress(1.0)
            send_status(f"Завершено: {os.path.basename(d.get('filename', ''))}")

    try:
        ydl_opts = _get_default_ydl_opts()
        ydl_opts.update({'ignoreerrors': ignore_errors, 'progress_hooks': [progress_hook]})

        # Формування шляхів збереження
        if download_mode == 'default':
            ydl_opts['outtmpl'] = os.path.join(output_dir, '%(channel,uploader)s', '%(title)s.%(ext)s')
        elif download_mode == 'flat_playlist':
            ydl_opts['outtmpl'] = os.path.join(output_dir, '%(title)s.%(ext)s')
            ydl_opts['noplaylist'] = False
        elif download_mode == 'single_flat':
            ydl_opts['outtmpl'] = os.path.join(output_dir, '%(title)s.%(ext)s')
            ydl_opts['noplaylist'] = True
        elif download_mode == 'music':
            ydl_opts['outtmpl'] = os.path.join(output_dir, '%(title)s.%(ext)s')

        is_audio_only = download_mode == 'music'

        # Формат завантаження
        if is_audio_only:
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [
                {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': str(audio_quality)}
            ]
        else:
            format_filters = []
            if max_resolution and max_resolution != "best":
                format_filters.append(f"height<={max_resolution}")
            if avoid_av1:
                format_filters.append("vcodec!~='^av01'")
            if prefer_h264:
                format_filters.append("vcodec^='avc1'")
            if max_bitrate and max_bitrate > 0:
                format_filters.append(f"tbr<={max_bitrate}")

            format_filter_str = ''.join(f'[{f}]' for f in format_filters)
            base_format = f"bestvideo{format_filter_str}+bestaudio/best{format_filter_str}/best"

            if format_selection == 'best_mp4' or force_mp4:
                ydl_opts['format'] = f"{base_format}[ext=mp4]/best"
                ydl_opts['merge_output_format'] = 'mp4'
            else:
                ydl_opts['format'] = base_format

            if force_mp4:
                ydl_opts.setdefault('postprocessors', []).append(
                    {'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}
                )

        if playlist_start > 0:
            ydl_opts['playliststart'] = playlist_start
        if playlist_end > 0:
            ydl_opts['playlistend'] = playlist_end
        if concurrent_fragments > 1:
            ydl_opts['concurrent_fragment_downloads'] = concurrent_fragments
        if skip_downloaded:
            ydl_opts['download_archive'] = os.path.join(output_dir, '.yt-dlp-archive.txt')
        if time_start or time_end:
            ydl_opts['download_ranges'] = download_range_func(None, [(time_start or "00:00:00", time_end)])
        if download_subs and not is_audio_only:
            ydl_opts.update({
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': [lang.strip() for lang in (sub_langs or 'uk,en').split(',')]
            })
            if embed_subs:
                ydl_opts['embedsubtitles'] = True

        logger.info(f"Запуск yt-dlp з параметрами: {ydl_opts}")
        send_status(f"Запуск yt-dlp для {url}...")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        send_done("Завантаження YouTube завершено.")
    except Exception as e:
        import traceback
        error_msg = f"Критична помилка yt-dlp: {e}\n{traceback.format_exc()}"
        logger.critical(error_msg)
        send_error(error_msg)

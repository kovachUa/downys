# scripts/youtube.py

import yt_dlp
import os
import re
import time
import traceback
from typing import Optional, Callable, Dict, Any, List, Union
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

def clean_string(s: str) -> str:
    if not isinstance(s, str): return ""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    cleaned = ansi_escape.sub('', s)
    return re.sub(r'\s+', ' ', cleaned).strip()

def _get_default_ydl_opts() -> Dict[str, Any]:
    return {
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'quiet': True,
        'verbose': False,
        'no_warnings': True,
        'continuedl': True,
    }

def extract_youtube_info(url: str, extra_opts: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    ydl_opts = _get_default_ydl_opts()
    ydl_opts['extract_flat'] = 'in_playlist'
    ydl_opts['skip_download'] = True
    if extra_opts: ydl_opts.update(extra_opts)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"Помилка вилучення інформації yt-dlp: {e}")
        return None

def download_youtube_media(
    urls: Union[str, List[str]],
    output_dir: str,
    download_mode: str = 'default',
    format_selection: str = "best",
    audio_format_override: Optional[str] = None,
    download_subs: bool = False,
    sub_langs: Optional[str] = None,
    embed_subs: bool = False,
    status_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[float], None]] = None
):
    def _safe_callback(callback: Optional[Callable], *args: Any, **kwargs: Any):
        if callback and callable(callback):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                print(f"Помилка під час виклику callback {callback.__name__}: {e}")

    _start_time = time.time()
    _last_reported_progress = -1.0

    def progress_hook(d: Dict[str, Any]):
        nonlocal _start_time, _last_reported_progress
        status = d.get('status')
        if status == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes')
            if total and downloaded is not None:
                fraction = min(1.0, downloaded / total)
                if abs(fraction - _last_reported_progress) > 0.001:
                    _safe_callback(progress_callback, fraction); _last_reported_progress = fraction
            title = d.get('info_dict', {}).get('title', '...')
            _safe_callback(status_callback, f"Завантаження '{title[:50]}...': {d.get('_percent_str', '')}")
        elif status == 'finished':
            _safe_callback(progress_callback, 1.0)
            _safe_callback(status_callback, f"Завершено: {os.path.basename(d.get('filename', ''))}")
        elif status == 'error':
            _safe_callback(status_callback, "Помилка завантаження...")

    ydl_opts = _get_default_ydl_opts()
    ydl_opts['progress_hooks'] = [progress_hook]

    # --- ФІНАЛЬНА ВИПРАВЛЕНА ЛОГІКА ---

    # 1. Встановлюємо опцію 'noplaylist' залежно від режиму.
    #    Це єдиний надійний спосіб контролювати поведінку.
    if download_mode == 'single_flat':
        # Примусово завантажувати ТІЛЬКИ ОДНЕ відео, ігноруючи будь-які
        # плейлисти або списки відео на каналі.
        ydl_opts['noplaylist'] = True
    else:
        # Для всіх інших режимів (default, music, flat_playlist) ми ДОЗВОЛЯЄМО
        # завантажувати плейлисти/канали, якщо вони є в URL.
        ydl_opts['noplaylist'] = False

    # 2. Встановлюємо шаблон шляху збереження.
    if download_mode in ['music', 'flat_playlist', 'single_flat']:
        # Всі ці режими вимагають пласкої структури в цільовій папці.
        ydl_opts['outtmpl'] = os.path.join(output_dir, '%(title)s.%(ext)s')
    else:  # 'default'
        # Стандартний режим створює підпапки за назвою каналу.
        ydl_opts['outtmpl'] = os.path.join(output_dir, '%(uploader)s', '%(title)s.%(ext)s')

    # --- КІНЕЦЬ ФІНАЛЬНОЇ ЛОГІКИ ---


    # 3. Обробка формату (залишається без змін).
    local_format_selection = format_selection
    if download_mode == 'music' and not format_selection.startswith('audio_'):
        local_format_selection = 'audio_mp3'

    is_audio_only = local_format_selection.startswith('audio_')
    
    if local_format_selection == 'best': ydl_opts['format'] = 'bestvideo+bestaudio/best'
    elif local_format_selection == 'best_mp4':
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        ydl_opts['merge_output_format'] = 'mp4'
    elif is_audio_only:
        ydl_opts['format'] = 'bestaudio/best'
        target_codec = audio_format_override
        if not target_codec or target_codec == 'best':
            if local_format_selection == 'audio_mp3': target_codec = 'mp3'
            elif local_format_selection == 'audio_m4a': target_codec = 'aac'
        if target_codec and target_codec != 'best':
            ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': target_codec}]
    
    if download_subs and not is_audio_only:
        ydl_opts['writesubtitles'] = True
        ydl_opts['writeautomaticsub'] = True
        ydl_opts['subtitleslangs'] = [lang.strip() for lang in (sub_langs or 'uk,en').split(',')]
        if embed_subs: ydl_opts['embedsubtitles'] = True

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            download_list = [urls] if isinstance(urls, str) else urls
            ydl.download(download_list)
    except Exception as e:
        _safe_callback(status_callback, f"Помилка yt-dlp: {e}")
        raise e

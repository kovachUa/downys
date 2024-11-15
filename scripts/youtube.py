import yt_dlp
import os
import sys

# Визначення директорії для збереження
output_dir = './downloads'  # Можна змінити на будь-яку іншу директорію

def download_youtube_video(video_url):
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',  # Завантажити найкраще відео та аудіо, якщо можливо
        'outtmpl': f'{output_dir}/%(uploader)s/%(title)s.%(ext)s',  # Шаблон імені файлу
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',  # Перетворення в mp4 (якщо потрібно)
        }],
        'merge_output_format': 'mp4',  # Якщо відео та аудіо завантажуються окремо, їх злиття в один mp4 файл
        'sleep_interval': 0.02,
        'max_sleep_interval': 0.05
    }

    os.makedirs(output_dir, exist_ok=True)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info_dict = ydl.extract_info(video_url, download=True)
            uploader = info_dict.get('uploader', 'Unknown_Channel')
            uploader_dir = os.path.join(output_dir, uploader)
            os.makedirs(uploader_dir, exist_ok=True)
        except yt_dlp.utils.DownloadError as e:
            print(f"Error downloading video: {e}")
            sys.exit(1)

    return uploader

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Введіть URL каналу або відео.")
        sys.exit(1)

    video_url = sys.argv[1]

    # Додати ytsearch, якщо не URL
    if not (video_url.startswith('http://') or video_url.startswith('https://')):
        video_url = f"ytsearch:{video_url}"

    downloader = download_youtube_video(video_url)

    print(f"Відео збережено локально в директорії {output_dir}/{downloader}.")

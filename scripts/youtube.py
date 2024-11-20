import os
import yt_dlp
import json
import re

# Function to sanitize the filename
def sanitize_filename(filename):
    return re.sub(r'[^\w\-_\. ]', '_', filename)

# Load configuration from file
def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

# Main function to download YouTube video
def download_youtube_video(video_url):
    config = load_config()  # Load config from file

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',  # Best quality video and audio
        'outtmpl': f"{config['output_dir']}/%(uploader)s/%(title)s.%(ext)s",  # Output template
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',  # Convert to mp4 if needed
        }],
        'merge_output_format': 'mp4',  # Merge the video and audio into MP4
        'sleep_interval': config["sleep_interval"],  # Configured sleep interval between downloads
        'max_sleep_interval': config["max_sleep_interval"],  # Max sleep interval
        'noplaylist': True,  # Disable playlist downloads, only download the specific video
        'prefer_free_formats': False,  # Prefer paid formats if available (e.g., higher quality)
    }

    os.makedirs(config["output_dir"], exist_ok=True)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info_dict = ydl.extract_info(video_url, download=True)
            uploader = info_dict.get('uploader', 'Unknown_Channel')
            title = info_dict.get('title', 'Unknown_Title')

            # Ensure the uploader directory is created
            uploader_dir = os.path.join(config["output_dir"], uploader)
            os.makedirs(uploader_dir, exist_ok=True)

            # Filename for the downloaded file
            filename = f"{title}.mp4"
            sanitized_filename = sanitize_filename(filename)

            # Get the correct file path where the video is saved
            downloaded_filename = os.path.join(uploader_dir, sanitized_filename)

            # Debugging: Print paths to verify
            print(f"Завантаження відео: {downloaded_filename}")
            print(f"Файл успішно збережено в {downloaded_filename}")

        except yt_dlp.utils.DownloadError as e:
            print(f"Помилка при завантаженні відео: {e}")

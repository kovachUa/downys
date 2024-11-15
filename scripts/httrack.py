import ffmpeg
import os

# Define input and output paths
base_dir = "project_directory"
input_dir = os.path.join(base_dir, "input")
output_dir = os.path.join(base_dir, "output")
input_file = os.path.join(input_dir, "input_file.mp4")

# Define output directories for each task
output_paths = {
    "converted_video": os.path.join(output_dir, "converted_video", "output_converted.avi"),
    "extracted_audio": os.path.join(output_dir, "extracted_audio", "output_audio.mp3"),
    "compressed_video": os.path.join(output_dir, "compressed_video", "output_compressed.mp4"),
    "adjusted_resolution": os.path.join(output_dir, "adjusted_resolution", "output_adjusted.mp4"),
    "images_to_video": os.path.join(output_dir, "images_to_video", "output_images_video.mp4"),
    "resized_images": os.path.join(output_dir, "resized_images", "output_resized.jpg"),
    "extracted_frames": os.path.join(output_dir, "extracted_frames", "output_frame_%03d.jpg"),
    "subtitles_added": os.path.join(output_dir, "subtitles_added", "output_subtitled.mp4"),
    "rotated_cropped_video": os.path.join(output_dir, "rotated_cropped_video", "output_rotated_cropped.mp4"),
    "merged_video": os.path.join(output_dir, "merged_video", "output_merged.mp4"),
    "stream_extracted": os.path.join(output_dir, "stream_extracted", "output_stream.mp4"),
    "quality_filter": os.path.join(output_dir, "quality_filter", "output_filtered.mp4"),
    "gif_creation": os.path.join(output_dir, "gif_creation", "output.gif"),
    "audio_video_creation": os.path.join(output_dir, "audio_video_creation", "output_audio_video.mp4"),
    "metadata_usage": os.path.join(output_dir, "metadata_usage", "output_metadata.mp4"),
}

# Ensure output directories exist
for path in output_paths.values():
    os.makedirs(os.path.dirname(path), exist_ok=True)

# Functions for each task
def convert_video_format():
    ffmpeg.input(input_file).output(output_paths["converted_video"]).run()

def extract_audio():
    ffmpeg.input(input_file).output(output_paths["extracted_audio"], **{'q:a': 0, 'map': 'a'}).run()

def compress_video(bitrate="1M"):
    ffmpeg.input(input_file).output(output_paths["compressed_video"], **{'b:v': bitrate}).run()

def adjust_resolution(width, height):
    ffmpeg.input(input_file).filter('scale', width, height).output(output_paths["adjusted_resolution"]).run()

def images_to_video(image_pattern, framerate="1"):
    ffmpeg.input(image_pattern, framerate=framerate).output(output_paths["images_to_video"], vcodec='libx264').run()

def resize_image(width, height):
    ffmpeg.input(input_file).filter('scale', width, height).output(output_paths["resized_images"]).run()

def extract_frames(framerate="1"):
    ffmpeg.input(input_file).filter('fps', framerate).output(output_paths["extracted_frames"]).run()

def add_subtitles(subtitle_file):
    ffmpeg.input(input_file).filter('subtitles', subtitle_file).output(output_paths["subtitles_added"]).run()

def rotate_and_crop_video(rotation="transpose=1", crop="crop=640:360:0:0"):
    ffmpeg.input(input_file).filter_complex(f"{rotation},{crop}").output(output_paths["rotated_cropped_video"]).run()

def merge_videos(input_files):
    ffmpeg.input(input_files[0]).input(input_files[1]).output(output_paths["merged_video"]).run()

def extract_from_stream(stream_url):
    ffmpeg.input(stream_url).output(output_paths["stream_extracted"]).run()

def apply_quality_filter():
    ffmpeg.input(input_file).filter('hqdn3d').output(output_paths["quality_filter"]).run()

def create_gif(start_time, duration):
    ffmpeg.input(input_file, ss=start_time, t=duration).output(output_paths["gif_creation"], vf='fps=10,scale=320:-1:flags=lanczos').run()

def create_audio_video(audio_file):
    ffmpeg.input(audio_file).output(output_paths["audio_video_creation"], vcodec='libx264', acodec='aac').run()

def use_metadata():
    ffmpeg.input(input_file).output(output_paths["metadata_usage"], metadata="title=My Video").run()


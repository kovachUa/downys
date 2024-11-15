import subprocess

def convert_video(input_file, output_file):
    try:
        command = [
            'ffmpeg', 
            '-i', input_file,  # Input file
            '-vcodec', 'libx264',  # Video codec
            '-acodec', 'aac',  # Audio codec
            output_file  # Output file
        ]
        subprocess.run(command, check=True)
        print(f"Video converted successfully: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error converting video: {e}")

def convert_audio(input_file, output_file):
    try:
        command = [
            'ffmpeg', 
            '-i', input_file,  # Input file
            '-vn',  # No video
            '-acodec', 'aac',  # Audio codec
            output_file  # Output file
        ]
        subprocess.run(command, check=True)
        print(f"Audio converted successfully: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error converting audio: {e}")
 

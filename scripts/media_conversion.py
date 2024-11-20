import av

def convert_video(input_file, output_file):
    try:
        # Open input file
        input_container = av.open(input_file)
        output_container = av.open(output_file, mode='w')

        # Add a video stream (H.264 codec)
        video_stream = output_container.add_stream(codec_name='h264')
        
        # Add an audio stream (AAC codec)
        audio_stream = output_container.add_stream(codec_name='aac')

        for frame in input_container.decode(video=0):
            frame.pts = None  # Reset timestamps for re-encoding
            packet = video_stream.encode(frame)
            if packet:
                output_container.mux(packet)

        # Encode audio frames
        for frame in input_container.decode(audio=0):
            frame.pts = None  # Reset timestamps for re-encoding
            packet = audio_stream.encode(frame)
            if packet:
                output_container.mux(packet)

        # Finalize encoding
        video_stream.encode(None)  # Flush video encoder
        audio_stream.encode(None)  # Flush audio encoder

        output_container.close()
        print(f"Video converted successfully: {output_file}")
    except Exception as e:
        print(f"Error converting video: {e}")


def convert_audio(input_file, output_file):
    try:
        # Open input file
        input_container = av.open(input_file)
        output_container = av.open(output_file, mode='w')

        # Add an audio stream (AAC codec)
        audio_stream = output_container.add_stream(codec_name='aac')

        for frame in input_container.decode(audio=0):
            frame.pts = None  # Reset timestamps for re-encoding
            packet = audio_stream.encode(frame)
            if packet:
                output_container.mux(packet)

        # Finalize encoding
        audio_stream.encode(None)  # Flush audio encoder

        output_container.close()
        print(f"Audio converted successfully: {output_file}")
    except Exception as e:
        print(f"Error converting audio: {e}")

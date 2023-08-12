import os
import subprocess

from pipeline.audio_masking.BaseAudioMasker import BaseAudioMasker
from moviepy.editor import VideoFileClip
from config import (
    VIDEOS_BASE_PATH,
    RESULT_BASE_PATH,
)


class RVCAudioMasker(BaseAudioMasker):
    # Extracts the audio track from a video and write it to an mp3 file
    def __init__(self, params: dict):
        self.params = params

    def mask(self, video_id: str):
        input_path = os.path.join(VIDEOS_BASE_PATH, video_id + ".mp4")
        input_mp3_path = os.path.join(VIDEOS_BASE_PATH, video_id + "_tmp.mp3")
        output_path = os.path.join(RESULT_BASE_PATH, video_id + ".mp3")

        video = VideoFileClip(input_path)
        audio = video.audio
        audio.write_audiofile(input_mp3_path)

        f0_up_key = 0  # transpose value
        model = "/Retrieval-based-Voice-Conversion-WebUI/weights/arianagrandev2.pth"
        file_index = "/Retrieval-based-Voice-Conversion-WebUI/weights/added_IVF1033_Flat_nprobe_1_v2.index"
        device = "cpu"
        f0_method = "crepe"

        args = [
            "python3",
            "/Retrieval-based-Voice-Conversion-WebUI/infer_cli.py",
            str(f0_up_key),
            f"/app/{input_mp3_path}",
            f"/app/{output_path}",
            model,
            file_index,
            device,
            f0_method,
        ]

        res = subprocess.run(
            args,
            capture_output=True,
            cwd="/Retrieval-based-Voice-Conversion-WebUI",
        )

        return output_path

import sys
import time

from communication.backend_client import BackendClient
from communication.video_manager import VideoManager
from masking.media_pipe_pose_masker import MediaPipePoseMasker

class WorkerProcess:
    _backend_client: BackendClient
    _video_manager: VideoManager

    def __init__(self, backend_client: BackendClient, video_manager: VideoManager):
        self._backend_client = backend_client
        self._video_manager = video_manager

    def run(self):
        while True:
            print("Attempting to fetch next job.")
            sys.stdout.flush()

            job = self._fetch_job()

            if job is None:
                time.sleep(10)
                continue

            print("Found job with id " + job["id"], flush=True)
            self._process_job(job)

    def _fetch_job(self):
        try:
            return self._backend_client.fetch_next_job()
        except Exception as e:
            print("Error while fetching job, retrying.", flush=True)
            print(e, flush=True)
            return None

    def _process_job(self, job):
        try:
            # @todo fetch video
            self._video_manager.load_original_video(job["video_id"])

            # @todo add support for different job types
            self._run_media_pipe_pose_masker(job)

            self._backend_client.mark_job_as_finished(job["id"])
            print("Finished processing job with id " + job["id"], flush=True)
        except Exception as e:
            print("Error while processing job, marking as failed.", flush=True)
            print(e, flush=True)
            self._backend_client.mark_job_as_failed(job["id"])

    def _run_media_pipe_pose_masker(self, job):
        media_pipe_pose_masker = MediaPipePoseMasker()

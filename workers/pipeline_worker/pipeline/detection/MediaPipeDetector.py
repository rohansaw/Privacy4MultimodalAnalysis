from typing import List
import os
import cv2
import mediapipe as mp
import numpy as np

from pipeline_worker.pipeline.detection.BaseDetector import BaseDetector
from pipeline_worker.pipeline.PipelineTypes import PartToDetect

standard_model_path = os.path.join("models", "pose_landmarker_heavy.task")


class MediaPipeDetector(BaseDetector):
    def __init__(self, parts_to_detect: List[PartToDetect]):
        super().__init__(parts_to_detect)
        self.reorder_parts_to_detect()
        self.silhouette_methods = {
            "body": self.detect_body_silhouette,
            "background": self.detect_background_silhouette,
        }
        self.model_path = standard_model_path
        self.init_mp_model()

    def reorder_parts_to_detect(self) -> List[PartToDetect]:
        background_part = self.get_part_to_detect("background")
        if background_part:
            index = self.parts_to_detect.index(background_part)
            self.parts_to_detect.pop(index)
            self.parts_to_detect.append(background_part)

    def init_mp_model(self):
        BaseOptions = mp.tasks.BaseOptions
        PoseLandmarker = mp.tasks.vision.PoseLandmarker
        PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
        VisionRunningMode = mp.tasks.vision.RunningMode

        # @ToDo currently only working for body
        detection_params = None
        body_part = self.get_part_to_detect("body")
        background_part = self.get_part_to_detect("background")
        if body_part:
            detection_params = body_part["detection_params"]
        elif background_part:
            try:
                detection_params = background_part["detection_params"]
            except:
                raise Exception("Detection Parameters for background not specified")
        else:
            raise Exception(
                "MediaPipe detector only supports body and background detection."
            )

        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=self.model_path),
            running_mode=VisionRunningMode.VIDEO,
            output_segmentation_masks=True,
            num_poses=detection_params["numPoses"],
            min_pose_detection_confidence=detection_params["confidence"],
        )

        self.model = PoseLandmarker.create_from_options(options)

    def detect_body_silhouette(
        self, frame: np.ndarray, timestamp_ms: int
    ) -> np.ndarray:
        # Returns the segmentation mask for the body [black / white]
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)

        results = self.model.detect_for_video(mp_image, timestamp_ms)

        output_image = np.zeros((mp_image.height, mp_image.width, mp_image.channels))
        if results.segmentation_masks:
            for segmentation_mask in results.segmentation_masks:
                mask = segmentation_mask.numpy_view()
                seg_mask = np.repeat(mask[:, :, np.newaxis], 3, axis=2)

                output_image[seg_mask > 0.3] = 1
                interpolation_mask = (seg_mask > 0.1) & (seg_mask <= 0.3)
                interpolation_factor = (seg_mask - 0.1) / (0.3 - 0.1)
                output_image[interpolation_mask] = (
                    1
                    - (1 - interpolation_factor[interpolation_mask])
                    * output_image[interpolation_mask]
                    + interpolation_factor[interpolation_mask] * 0
                )
        return output_image

    def detect_background_silhouette(
        self, frame: np.ndarray, timestamp_ms: int
    ) -> np.ndarray:
        # Returns the segmentation mask for the background [black / white]
        # The background is defined as everything that is not body
        person_silhouette_result = next(
            (
                result
                for result in self.current_results
                if result["part_name"] == "body"
            ),
            None,
        )
        if person_silhouette_result:
            mask = person_silhouette_result["mask"]
        else:
            mask = self.detect_body_silhouette(frame, timestamp_ms)
        mask_inverted = 1 - mask
        return mask_inverted  # the opposite of the body mask is the background

    def detect_boundingbox(self, frame, part_name: str):
        raise NotImplementedError(
            "Bounding Box detection is not specified for MediaPipe Detector"
        )

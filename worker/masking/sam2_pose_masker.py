import cv2
import numpy as np
import mediapipe
import supervision as sv
import os
import shutil

from typing import Callable
from communication.sam2_client import Sam2Client
from communication.openpose_client import OpenposeClient
from masking.smoothing import smooth_pose
from masking.mask_renderer import MaskRenderer
from masking.pose_renderer import PoseRenderer
from masking.media_pipe_landmarker import MediaPipeLandmarker


DEBUG = True
SMOOTHING = True


class Sam2PoseMasker:
    _sam2_client: Sam2Client
    _openpose_client: OpenposeClient
    _input_path: str
    _output_path: str
    _progress_callback: Callable[[int], None]
    _media_pipe_landmarker: MediaPipeLandmarker

    def __init__(
            self,
            sam2_client: Sam2Client,
            openpose_client: OpenposeClient,
            input_path: str,
            output_path: str,
            progress_callback: Callable[[int], None]
    ):
        self._sam2_client = sam2_client
        self._openpose_client = openpose_client
        self._input_path = input_path
        self._output_path = output_path
        self._progress_callback = progress_callback
        self._media_pipe_landmarker = MediaPipeLandmarker()

    def mask(self, video_masking_data: dict):
        content = self._read_video_content()
        masks = self._sam2_client.segment_video(video_masking_data['posePrompts'], content)
        del content

        video_capture, frame_width, frame_height, sample_rate = self._open_video()
        total_frames = int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT))

        bounding_boxes = self._calculate_full_object_bounding_boxes(masks)
        estimation_input_bounding_boxes = self._calculate_estimation_input_bounding_boxes(bounding_boxes, frame_width, frame_height)

        subvideo_output_dir = '/app/subvideos'
        sub_video_paths = self._create_sub_videos(video_capture, estimation_input_bounding_boxes, masks, subvideo_output_dir)
        video_capture.release()

        pose_data_dict = self._compute_pose_data(video_masking_data, sub_video_paths, total_frames)
        self._streamline_pose_data(video_masking_data, pose_data_dict, estimation_input_bounding_boxes, total_frames, sample_rate)

        shutil.rmtree(subvideo_output_dir)

        video_capture, frame_width, frame_height, sample_rate = self._open_video()
        video_writer = self._initialize_video_writer(frame_width, frame_height, sample_rate)

        mask_renderer = MaskRenderer('transparent_fill', {'level': 3, 'object_borders': True})

        pose_renderers = {
            obj_id: PoseRenderer(video_masking_data['overlayStrategies'][obj_id - 1])
            for obj_id in pose_data_dict.keys()
        }

        idx = 0
        while video_capture.isOpened():
            ret, frame = video_capture.read()

            if not ret:
                break

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            output_frame = frame.copy()
            self._render_all_masks_on_image(output_frame, mask_renderer, idx, masks)

            if DEBUG:
                self._render_bounding_boxes(output_frame, bounding_boxes, idx, (255, 255, 255))
                self._render_bounding_boxes(output_frame, estimation_input_bounding_boxes, idx, (0, 255, 0))

            for obj_id, poses in pose_data_dict.items():
                if poses[idx] is not None:
                    current_pose = poses[idx]
                    pose_renderers[obj_id].render_keypoint_overlay(output_frame, current_pose)

            output_frame = cv2.cvtColor(output_frame, cv2.COLOR_RGB2BGR)
            video_writer.write(output_frame)
            idx += 1

        video_capture.release()
        video_writer.release()

    def _open_video(self):
        video_capture = cv2.VideoCapture(self._input_path)
        frame_width = video_capture.get(cv2.CAP_PROP_FRAME_WIDTH)
        frame_height = video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
        sample_rate = video_capture.get(cv2.CAP_PROP_FPS)

        return video_capture, frame_width, frame_height, sample_rate

    def _initialize_video_writer(self, frame_width, frame_height, sample_rate):
        return cv2.VideoWriter(
            self._output_path,
            cv2.VideoWriter_fourcc(*'mp4v'),
            fps=sample_rate,
            frameSize=(int(frame_width), int(frame_height))
        )

    def _read_video_content(self):
        with open(self._input_path, "rb") as file:
            return file.read()

    def _select_bounding_box(self, bbox_dict, idx):
        bbox = None
        for frame_idx in sorted(bbox_dict.keys()):
            if frame_idx <= idx:
                bbox = bbox_dict[frame_idx]
            else:
                break
        return bbox

    def _prepare_estimation_input_frame(self, frame, mask, bbox):
        crop_alpha = 1.0

        # Crop the frame using the bounding box
        cropped_frame = frame[bbox[1]:bbox[3], bbox[0]:bbox[2]]
        cropped_frame = cropped_frame.astype(np.uint8)
        cropped_frame_height, cropped_frame_width, _ = cropped_frame.shape

        # Crop the mask using the bounding box
        cropped_mask = mask[bbox[1]:bbox[3], bbox[0]:bbox[2]]

        # Create reverse mask
        reverse_mask = ~cropped_mask
        reverse_mask_8bit = (reverse_mask * 255).astype(np.uint8)

        # Find contours and draw them on the reverse mask
        cropped_contours, _ = cv2.findContours(cropped_mask.astype(np.uint8), cv2.RETR_EXTERNAL,
                                               cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(reverse_mask_8bit, cropped_contours, -1, 0, round(cropped_frame_width / 100))

        # Create a boolean mask
        reverse_mask_bool = reverse_mask_8bit > 0

        # Apply the overlay using crop_alpha
        overlay = np.zeros_like(cropped_frame)
        cropped_frame[reverse_mask_bool] = (crop_alpha * overlay[reverse_mask_bool] + (1 - crop_alpha) * cropped_frame[reverse_mask_bool]).astype(np.uint8)

        return cropped_frame

    def _calculate_full_object_bounding_boxes(self, masks, iou_threshold=0.25):
        bounding_boxes = {}
        active_bboxes = {}

        for idx in range(len(masks)):
            # Iterate over all objects in the frame
            for object_id in range(1, len(masks[idx]) + 1):
                mask = masks[idx][object_id][0]
                current_bbox = self._calculate_bounding_box_from_mask(mask)
                if current_bbox is None:
                    continue

                start_point = current_bbox[0], current_bbox[1]
                end_point = current_bbox[2], current_bbox[3]

                if object_id not in active_bboxes:
                    # Initialize the first bounding box for the object
                    active_bboxes[object_id] = current_bbox
                    bounding_boxes[object_id] = {idx: current_bbox}
                else:
                    # Calculate IoU between the current frame's bbox and the active bbox
                    iou = self._calculate_iou(active_bboxes[object_id], current_bbox)

                    if iou < iou_threshold:
                        # If IoU is below the threshold, create a new bounding box entry
                        bounding_boxes[object_id][idx] = current_bbox
                        active_bboxes[object_id] = current_bbox
                    else:
                        # Update the active bounding box
                        active_bboxes[object_id][0] = min(active_bboxes[object_id][0], start_point[0])
                        active_bboxes[object_id][1] = min(active_bboxes[object_id][1], start_point[1])
                        active_bboxes[object_id][2] = max(active_bboxes[object_id][2], end_point[0])
                        active_bboxes[object_id][3] = max(active_bboxes[object_id][3], end_point[1])

        return bounding_boxes

    def _calculate_bounding_box_from_mask(self, segmentation_mask):
        # Find the coordinates of the non-zero values in the mask
        y_indices, x_indices = np.where(segmentation_mask > 0)

        if len(y_indices) == 0 or len(x_indices) == 0:
            # No object detected in the mask
            return None

        # Calculate the bounding box coordinates
        x_min = np.min(x_indices)
        x_max = np.max(x_indices)
        y_min = np.min(y_indices)
        y_max = np.max(y_indices)

        return [x_min, y_min, x_max, y_max]

    def _calculate_iou(self, bbox1, bbox2):
        # Calculate intersection
        x_left = max(bbox1[0], bbox2[0])
        y_top = max(bbox1[1], bbox2[1])
        x_right = min(bbox1[2], bbox2[2])
        y_bottom = min(bbox1[3], bbox2[3])

        if x_right < x_left or y_bottom < y_top:
            return 0.0

        intersection_area = (x_right - x_left) * (y_bottom - y_top)

        # Calculate union
        bbox1_area = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        bbox2_area = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
        union_area = bbox1_area + bbox2_area - intersection_area

        iou = intersection_area / union_area
        return iou

    def _create_sub_videos(self, video_capture, estimation_input_bounding_boxes, masks, subvideo_output_dir):
        sub_video_paths = []

        fps = video_capture.get(cv2.CAP_PROP_FPS)
        total_frames = int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT))

        # Iterate through each object in estimation_input_bounding_boxes
        for obj_id, bbox_dict in estimation_input_bounding_boxes.items():
            sorted_frames = sorted(bbox_dict.keys())

            for i, start_frame in enumerate(sorted_frames):
                bbox = bbox_dict[start_frame]  # bbox in (xmin, ymin, xmax, ymax) format
                width = bbox[2] - bbox[0]
                height = bbox[3] - bbox[1]

                # Determine the end frame for this sub-video
                if i < len(sorted_frames) - 1:
                    end_frame = sorted_frames[i + 1] - 1
                else:
                    end_frame = total_frames - 1

                # Define the output video filename
                os.makedirs(subvideo_output_dir, exist_ok=True)

                output_filename = f"{subvideo_output_dir}/object_{obj_id}_frame_{start_frame}.mp4"
                sub_video_paths.append(output_filename)

                out = cv2.VideoWriter(output_filename, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))

                # Seek to the start_frame
                video_capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

                for frame_num in range(start_frame, end_frame + 1):
                    ret, frame = video_capture.read()
                    if not ret:
                        break

                    mask = masks[frame_num][obj_id][0]
                    cropped_frame = self._prepare_estimation_input_frame(frame, mask, bbox)

                    # Write the cropped frame to the output video
                    out.write(cropped_frame)

                # Release the writer for this sub-video
                out.release()

        # Release the video capture object
        video_capture.release()
        return sub_video_paths

    def _render_bounding_boxes(self, output_frame, bounding_boxes, current_frame_idx, color):
        for object_id, bboxes in bounding_boxes.items():
            # Find the most recent bounding box for the current frame
            relevant_bbox = self._select_bounding_box(bboxes, current_frame_idx)

            if relevant_bbox is not None:
                start_point = (relevant_bbox[0], relevant_bbox[1])
                end_point = (relevant_bbox[2], relevant_bbox[3])
                cv2.rectangle(output_frame, start_point, end_point, color, 2)

    def _calculate_estimation_input_bounding_boxes(self, bounding_boxes, frame_width, frame_height):
        estimation_input_bounding_boxes = {}

        for object_id, bboxes in bounding_boxes.items():
            estimation_input_bounding_boxes[object_id] = {}

            for frame_idx, bbox in bboxes.items():
                # Apply fine-tuning to each bounding box for the object
                fine_tuned_bbox = self._fine_tune_bounding_box(bbox, frame_width, frame_height)
                estimation_input_bounding_boxes[object_id][frame_idx] = fine_tuned_bbox

        return estimation_input_bounding_boxes

    def _fine_tune_bounding_box(self, bbox, frame_width, frame_height):
        x_min, y_min, x_max, y_max = bbox
        width = x_max - x_min
        height = y_max - y_min

        # Add margin (up to 10% of width or height)
        margin_width = int(0.1 * width)
        margin_height = int(0.1 * height)

        x_min = max(0, x_min - margin_width)
        y_min = max(0, y_min - margin_height)
        x_max = min(frame_width, x_max + margin_width)
        y_max = min(frame_height, y_max + margin_height)

        # Calculate new width and height
        width = x_max - x_min
        height = y_max - y_min

        # Make the bounding box square
        if width > height:
            diff = width - height
            y_min = max(0, y_min - diff // 2)
            y_max = min(frame_height, y_max + (diff - diff // 2))
        else:
            diff = height - width
            x_min = max(0, x_min - diff // 2)
            x_max = min(frame_width, x_max + (diff - diff // 2))

        return [np.int64(x_min), np.int64(y_min), np.int64(x_max), np.int64(y_max)]

    def _render_all_masks_on_image(self, image, mask_renderer, frame_idx, masks):
        for object_id in range(1, len(masks[frame_idx]) + 1):
            mask = masks[frame_idx][object_id][0]
            mask_renderer.apply_to_image(image, mask, object_id)

    def _compute_pose_data(self, video_masking_data, sub_video_paths, frame_count):
        pose_data_dict = {}

        for sub_video_path in sub_video_paths:
            if os.path.exists(sub_video_path):
                obj_id, start_frame, content = self._read_sub_video(sub_video_path)

                if video_masking_data['overlayStrategies'][obj_id - 1] == 'mp_pose':
                    self._compute_mp_pose_data(sub_video_path, obj_id, pose_data_dict, frame_count, start_frame)
                elif video_masking_data['overlayStrategies'][obj_id - 1] == 'mp_face':
                    self._compute_mp_face_data(sub_video_path, obj_id, pose_data_dict, frame_count, start_frame)
                elif video_masking_data['overlayStrategies'][obj_id - 1] == 'mp_hand':
                    self._compute_mp_hand_data(sub_video_path, obj_id, pose_data_dict, frame_count, start_frame)
                elif video_masking_data['overlayStrategies'][obj_id - 1] == 'openpose':
                    self._compute_openpose_pose_data(content, obj_id, pose_data_dict, frame_count, start_frame)
                elif video_masking_data['overlayStrategies'][obj_id - 1] == 'none':
                    pass # Nothing to be done if there is no pose overlay strategy
                else:
                    raise Exception(f'Unknown overlay strategy, got {video_masking_data["overlayStrategies"][obj_id - 1]}')

        return pose_data_dict

    def _compute_openpose_pose_data(self, content, obj_id, pose_data_dict, frame_count, start_frame):
        # Trigger the pose estimation on the sub-video
        pose_data = self._openpose_client.estimate_pose_on_video(content)

        # Ensure the list for this obj_id exists in pose_data_dict
        if obj_id not in pose_data_dict:
            pose_data_dict[obj_id] = [None] * frame_count  # Initialize with None

        # Insert the extracted poses into the appropriate place in the list
        for i, pose in enumerate(pose_data):
            pose_data_dict[obj_id][start_frame + i] = pose

    def _compute_mp_pose_data(self, sub_video_path, obj_id, pose_data_dict, frame_count, start_frame):
        landmarker = self._media_pipe_landmarker.configure_pose_landmarker()
        video_capture = cv2.VideoCapture(sub_video_path)

        if obj_id not in pose_data_dict:
            pose_data_dict[obj_id] = [None] * frame_count

        i = 0
        while video_capture.isOpened():
            ret, frame = video_capture.read()

            if not ret:
                break

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_timestamp_ms = video_capture.get(cv2.CAP_PROP_POS_MSEC)

            mp_image = mediapipe.Image(image_format=mediapipe.ImageFormat.SRGB, data=frame)
            pose_landmarker_result = landmarker.detect_for_video(mp_image, int(frame_timestamp_ms))

            if len(pose_landmarker_result.pose_landmarks) > 0:
                pose = pose_landmarker_result.pose_landmarks[0]
                pose_data_dict[obj_id][start_frame + i] = pose

            i += 1

        video_capture.release()

    def _compute_mp_face_data(self, sub_video_path, obj_id, pose_data_dict, frame_count, start_frame):
        landmarker = self._media_pipe_landmarker.configure_face_landmarker()
        video_capture = cv2.VideoCapture(sub_video_path)

        if obj_id not in pose_data_dict:
            pose_data_dict[obj_id] = [None] * frame_count

        i = 0
        while video_capture.isOpened():
            ret, frame = video_capture.read()

            if not ret:
                break

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_timestamp_ms = video_capture.get(cv2.CAP_PROP_POS_MSEC)

            mp_image = mediapipe.Image(image_format=mediapipe.ImageFormat.SRGB, data=frame)
            face_landmarker_result = landmarker.detect_for_video(mp_image, int(frame_timestamp_ms))

            if len(face_landmarker_result.face_landmarks) > 0:
                face = face_landmarker_result.face_landmarks[0]
                pose_data_dict[obj_id][start_frame + i] = face

            i += 1

        video_capture.release()

    def _compute_mp_hand_data(self, sub_video_path, obj_id, pose_data_dict, frame_count, start_frame):
        landmarker = self._media_pipe_landmarker.configure_hand_landmarker()
        video_capture = cv2.VideoCapture(sub_video_path)

        if obj_id not in pose_data_dict:
            pose_data_dict[obj_id] = [None] * frame_count

        i = 0
        while video_capture.isOpened():
            ret, frame = video_capture.read()

            if not ret:
                break

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_timestamp_ms = video_capture.get(cv2.CAP_PROP_POS_MSEC)

            mp_image = mediapipe.Image(image_format=mediapipe.ImageFormat.SRGB, data=frame)
            hand_landmarker_result = landmarker.detect_for_video(mp_image, int(frame_timestamp_ms))

            if len(hand_landmarker_result.hand_landmarks) > 0:
                hand = hand_landmarker_result.hand_landmarks[0]
                pose_data_dict[obj_id][start_frame + i] = hand

            i += 1

        video_capture.release()

    def _read_sub_video(self, sub_video_path):
        basename = os.path.basename(sub_video_path)
        parts = basename.split('_')
        obj_id = int(parts[1])
        start_frame = int(parts[3].split('.')[0])

        # Read the sub-video content
        with open(sub_video_path, 'rb') as video_file:
            content = video_file.read()
            return obj_id, start_frame, content

    def _streamline_pose_data(self, video_masking_data, pose_data_dict, estimation_input_bounding_boxes, frame_count, sample_rate):
        confidence_threshold = 0.05

        for obj_id, pose_data in pose_data_dict.items():
            overlay_strategy = video_masking_data['overlayStrategies'][obj_id - 1]

            if overlay_strategy == 'openpose':
                for idx in range(frame_count):
                    relevant_start_frame = max(frame for frame in estimation_input_bounding_boxes[obj_id].keys() if frame <= idx)

                    bbox = estimation_input_bounding_boxes[obj_id][relevant_start_frame]
                    xmin, ymin, xmax, ymax = bbox

                    current_pose = pose_data[idx]

                    if current_pose is None or current_pose['pose_keypoints'] is None:
                        pose_data_dict[obj_id][idx] = None
                        continue

                    adjusted_pose = {
                        'pose_keypoints': [],
                        'face_keypoints': [],
                        'left_hand_keypoints': [],
                        'right_hand_keypoints': []
                    }

                    for keypoint in current_pose['pose_keypoints']:
                        if keypoint is not None and (keypoint[0] > 0 or keypoint[1] > 0) and keypoint[2] > confidence_threshold:
                            # Translate the keypoint back to the original frame coordinates
                            adjusted_keypoint = (keypoint[0] + xmin, keypoint[1] + ymin)
                            adjusted_pose['pose_keypoints'].append(adjusted_keypoint)
                        else:
                            adjusted_pose['pose_keypoints'].append(None)

                    if current_pose['face_keypoints'] is not None:
                        for keypoint in current_pose['face_keypoints']:
                            if keypoint is not None and (keypoint[0] > 0 or keypoint[1] > 0) and keypoint[2] > confidence_threshold:
                                # Translate the keypoint back to the original frame coordinates
                                adjusted_keypoint = (keypoint[0] + xmin, keypoint[1] + ymin)
                                adjusted_pose['face_keypoints'].append(adjusted_keypoint)
                            else:
                                adjusted_pose['face_keypoints'].append(None)

                    if current_pose['left_hand_keypoints'] is not None:
                        for keypoint in current_pose['left_hand_keypoints']:
                            if keypoint is not None and (keypoint[0] > 0 or keypoint[1] > 0) and keypoint[2] > confidence_threshold:
                                # Translate the keypoint back to the original frame coordinates
                                adjusted_keypoint = (keypoint[0] + xmin, keypoint[1] + ymin)
                                adjusted_pose['left_hand_keypoints'].append(adjusted_keypoint)
                            else:
                                adjusted_pose['left_hand_keypoints'].append(None)

                    if current_pose['right_hand_keypoints'] is not None:
                        for keypoint in current_pose['right_hand_keypoints']:
                            if keypoint is not None and (keypoint[0] > 0 or keypoint[1] > 0) and keypoint[2] > confidence_threshold:
                                # Translate the keypoint back to the original frame coordinates
                                adjusted_keypoint = (keypoint[0] + xmin, keypoint[1] + ymin)
                                adjusted_pose['right_hand_keypoints'].append(adjusted_keypoint)
                            else:
                                adjusted_pose['right_hand_keypoints'].append(None)

                    pose_data_dict[obj_id][idx] = adjusted_pose
            elif overlay_strategy == 'mp_pose':
                for idx in range(frame_count):
                    relevant_start_frame = max(frame for frame in estimation_input_bounding_boxes[obj_id].keys() if frame <= idx)

                    bbox = estimation_input_bounding_boxes[obj_id][relevant_start_frame]
                    xmin, ymin, xmax, ymax = bbox

                    current_pose = pose_data[idx]

                    if current_pose is None:
                        pose_data_dict[obj_id][idx] = None
                        continue

                    adjusted_pose = []
                    for keypoint in current_pose:
                        if keypoint is not None and (keypoint.x > 0 or keypoint.y > 0) and keypoint.visibility > confidence_threshold:
                            # Translate the keypoint back to the original frame coordinates
                            adjusted_keypoint = (keypoint.x * (xmax - xmin) + xmin, keypoint.y * (ymax - ymin) + ymin)
                            adjusted_pose.append(adjusted_keypoint)
                        else:
                            adjusted_pose.append(None)

                    pose_data_dict[obj_id][idx] = adjusted_pose
            elif overlay_strategy == 'mp_face':
                for idx in range(frame_count):
                    relevant_start_frame = max(frame for frame in estimation_input_bounding_boxes[obj_id].keys() if frame <= idx)

                    bbox = estimation_input_bounding_boxes[obj_id][relevant_start_frame]
                    xmin, ymin, xmax, ymax = bbox

                    current_face = pose_data[idx]

                    adjusted_face = []
                    for keypoint in current_face:
                        if keypoint is not None and (keypoint.x > 0 or keypoint.y > 0):
                            # Translate the keypoint back to the original frame coordinates
                            adjusted_keypoint = (keypoint.x * (xmax - xmin) + xmin, keypoint.y * (ymax - ymin) + ymin)
                            adjusted_face.append(adjusted_keypoint)
                        else:
                            adjusted_face.append(None)

                    pose_data_dict[obj_id][idx] = adjusted_face
            elif overlay_strategy == 'mp_hand':
                for idx in range(frame_count):
                    relevant_start_frame = max(frame for frame in estimation_input_bounding_boxes[obj_id].keys() if frame <= idx)

                    bbox = estimation_input_bounding_boxes[obj_id][relevant_start_frame]
                    xmin, ymin, xmax, ymax = bbox

                    current_hand = pose_data[idx]

                    if current_hand is None:
                        continue

                    adjusted_hand = []
                    for keypoint in current_hand:
                        if keypoint is not None and (keypoint.x > 0 or keypoint.y > 0):
                            # Translate the keypoint back to the original frame coordinates
                            adjusted_keypoint = (keypoint.x * (xmax - xmin) + xmin, keypoint.y * (ymax - ymin) + ymin)
                            adjusted_hand.append(adjusted_keypoint)
                        else:
                            adjusted_hand.append(None)

                    pose_data_dict[obj_id][idx] = adjusted_hand

            if SMOOTHING and (overlay_strategy == 'openpose' or overlay_strategy == 'mp_pose'):
                if overlay_strategy == 'mp_pose':
                    pose_data_dict[obj_id] = smooth_pose(
                        pose_data_dict[obj_id],
                        sample_rate,
                        10 if overlay_strategy == 'openpose' else 15
                    )
                elif overlay_strategy == 'openpose':
                    pass
                    """
                    pose_data_dict[obj_id]['body_keypoints'] = smooth_pose(
                        pose_data_dict[obj_id]['body_keypoints'],
                        sample_rate,
                        10
                    )
                    
                    pose_data_dict[obj_id]['face_keypoints'] = smooth_pose(
                        pose_data_dict[obj_id]['face_keypoints'],
                        sample_rate,
                        12
                    )
                    """


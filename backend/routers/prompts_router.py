import cv2
import os
import requests
import json
import numpy as np

from fastapi import APIRouter, Request, Depends, Response
from auth.jwt_bearer import JWTBearer
from ultralytics import YOLO
from config import VIDEOS_BASE_PATH
from pydantic import BaseModel


router = APIRouter(
    prefix="/prompts",
)

model = YOLO('./models/yolov8m-pose.pt')


@router.get("/{video_id}/pose")
def fetch_pose_prompts(video_id: str, token_payload: dict = Depends(JWTBearer())):
    user_id = token_payload["sub"]
    # @todo must be users video

    video_path = os.path.join(VIDEOS_BASE_PATH, video_id + ".mp4")
    capture = cv2.VideoCapture(video_path)
    success, frame = capture.read()
    capture.release()

    results = model.predict(
        source=frame,
        device='cpu',
    )

    poses = results[0].keypoints.xy.cpu().numpy().astype(int)
    confs = results[0].keypoints.conf.cpu().numpy()

    poses = np.array([[point if conf > 0.8 else (0, 0)
                                for point, conf in zip(keypoints, confidences)]
                               for keypoints, confidences in zip(poses, confs)])

    # Remove empty poses (where all points are (0, 0))
    poses = np.array([pose for pose in poses if not np.all(pose == (0, 0))])

    pose_prompts = [extract_pose_points(pose) for pose in poses]

    return {'pose_prompts': pose_prompts}


class Sam2Params(BaseModel):
    pose_prompts: list[list[list[int]]]


@router.post("/{video_id}/sam2")
def test(sam2_params: Sam2Params, video_id: str, token_payload: dict = Depends(JWTBearer())):
    user_id = token_payload["sub"]
    # @todo must be users video

    video_path = os.path.join(VIDEOS_BASE_PATH, video_id + ".mp4")
    capture = cv2.VideoCapture(video_path)
    success, frame = capture.read()
    capture.release()

    if not success:
        # Handle error if the frame couldn't be read
        return {"error": "Could not read video frame"}

    _, buffer = cv2.imencode('.jpg', frame)
    image_data = buffer.tobytes()

    # Prepare the files and data for the multipart request
    files = {
        'image': ('frame.jpg', image_data, 'image/jpeg'),
    }

    data = {
        'pose_prompts': json.dumps(sam2_params.pose_prompts),
    }

    print(data)

    # Send the image along with the JSON data in a multipart request
    response = requests.post(
        'http://sam2:8000/sam2/segment-image',
        files=files,
        data=data,
    )

    return Response(content=response.content, media_type="image/jpeg")


def is_valid(point):
    return point[0] >= 1 and point[1] >= 1


def average_points(points):
    valid_points = [point for point in points if is_valid(point)]
    if valid_points:
        avg_x = round(sum(point[0] for point in valid_points) / len(valid_points))
        avg_y = round(sum(point[1] for point in valid_points) / len(valid_points))
        return [avg_x, avg_y]
    else:
        return [0, 0]


def extract_pose_points(pose):
    #return [point.tolist() + [1] for point in pose]

    points_0_to_4 = [pose[j] for j in range(5)]
    merged_head_point = average_points(points_0_to_4)

    points_5_and_6 = [pose[j] for j in range(5, 7)]
    merged_upper_body_point = average_points(points_5_and_6)

    points_11_and_12 = [pose[j] for j in range(11, 13)]
    merged_lower_body_point = average_points(points_11_and_12)

    new_pose = []

    if is_valid(merged_head_point):
        new_pose.append(merged_head_point + [1])
    if is_valid(merged_upper_body_point):
        new_pose.append(merged_upper_body_point + [1])
    if is_valid(merged_lower_body_point):
        new_pose.append(merged_lower_body_point + [1])

    # Check if we have less than 2 points and add points from indices 7-10 and 13-end if valid
    for j in list(range(7, 11)) + list(range(13, len(pose))):
        if len(new_pose) >= 2:
            break
        if is_valid(pose[j]):
            new_pose.append(pose[j].tolist() + [1])

    return new_pose

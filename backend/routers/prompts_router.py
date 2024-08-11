import cv2
import os
import requests
import json

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
    pose_prompts = [extract_pose_points(pose) for pose in poses]
    print(pose_prompts)

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
    # Collect valid points from indices 0 to 4
    points_0_to_4 = [pose[j] for j in range(5)]
    avg_point_0_to_4 = average_points(points_0_to_4)

    # Collect valid points from indices 5 and 6
    points_5_and_6 = [pose[j] for j in range(5, 7)]
    avg_point_5_and_6 = average_points(points_5_and_6)

    # Collect valid points from indices 11 and 12
    points_11_and_12 = [pose[j] for j in range(11, 13)]
    avg_point_11_and_12 = average_points(points_11_and_12)

    # Create a new list of points
    new_pose = []

    # Add the averaged points to the new list if they are valid
    if is_valid(avg_point_0_to_4):
        new_pose.append(avg_point_0_to_4 + [1])
    if is_valid(avg_point_5_and_6):
        new_pose.append(avg_point_5_and_6 + [1])
    if is_valid(avg_point_11_and_12):
        new_pose.append(avg_point_11_and_12 + [1])

    # Add other points (indices 7 to 10 and 13 to end) if they are valid
    for j in range(7, 11):
        if is_valid(pose[j]):
            new_pose.append(pose[j].tolist() + [1])
    for j in range(13, len(pose)):
        if is_valid(pose[j]):
            new_pose.append(pose[j].tolist() + [1])

    return new_pose

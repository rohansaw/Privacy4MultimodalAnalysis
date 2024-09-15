import React, {useEffect, useRef, useState} from "react";
import {useParams} from "react-router";
import {Box, Button, Divider, IconButton, InputLabel, MenuItem, Select, TextField} from "@mui/material";
import {useDispatch, useSelector} from "react-redux";
import Selector from "../state/selector";
import Api from "../api";
import Config from "../config";
import KeycloakAuth from "../keycloakAuth";
import DraggablePoint from "../components/videosMakingEditor/DraggablePoint";
import Command from "../state/actions/command";
import {v4 as uuidv4} from "uuid";
import HighlightOffIcon from '@mui/icons-material/HighlightOff';
import ShieldLogoIcon from "../components/common/ShieldLogoIcon";

const VideoMaskingEditorPage = () => {
    const dispatch = useDispatch();
    const videoList = useSelector(Selector.Video.videoList);
    const { videoId } = useParams<{ videoId: string }>();

    const imgRef = useRef<HTMLImageElement>(null);
    const [currentFrame, setCurrentFrame] = useState<number>(0);
    const [posePrompts, setPosePrompts] = useState<[number, number, number][][]>([]);
    const [overlayStrategies, setOverlayStrategories] = useState<string[]>([]);
    const [bounds, setBounds] = useState({ left: 0, top: 0, right: 0, bottom: 0 });
    const [dragStartPosition, setDragStartPosition] = useState({ x: 0, y: 0 });
    const [segmentationImageUrl, setSegmentationImageUrl] = useState<string | null>(null);
    const [videoPosePrompts, setVideoPosePrompts] = useState<Record<string, [number, number, number][][]>>({});

    useEffect(() => {
        if (!videoId) {
            return;
        }

        Api.fetchPosePrompt(videoId, currentFrame).then(posePrompts => {
            setPosePrompts(posePrompts);
            setOverlayStrategories(posePrompts.map((_: any) => 'mp_pose'));
        });
    }, [videoId]);

    useEffect(() => {
        if (imgRef.current) {
            imgRef.current.onload = () => {
                const imgWidth = imgRef.current!.offsetWidth;
                const imgHeight = imgRef.current!.offsetHeight;
                setBounds({
                    left: 0,
                    top: 0,
                    right: imgWidth,
                    bottom: imgHeight,
                });
            };
        }
    }, [imgRef.current]);

    const handleDragStart = (e: any, data: any) => {
        setDragStartPosition({ x: data.x, y: data.y });
    };

    const handleDragStop = (poseIndex: number, pointIndex: number, e: any, data: any) => {
        const deltaX = Math.abs(data.x - dragStartPosition.x);
        const deltaY = Math.abs(data.y - dragStartPosition.y);
        const threshold = 1;

        if (deltaX < threshold && deltaY < threshold) {
            const newPoints = [...posePrompts];
            newPoints[poseIndex] = [...newPoints[poseIndex]];
            newPoints[poseIndex][pointIndex] = [
                newPoints[poseIndex][pointIndex][0],
                newPoints[poseIndex][pointIndex][1],
                newPoints[poseIndex][pointIndex][2] ? 0 : 1
            ];
            setPosePrompts(newPoints);
        } else {
            const newPoints = [...posePrompts];
            newPoints[poseIndex] = [...newPoints[poseIndex]];
            newPoints[poseIndex][pointIndex] = [
                Math.round(data.x), 
                Math.round(data.y), 
                posePrompts[poseIndex][pointIndex][2],
            ];
            setPosePrompts(newPoints);
        }
    };

    const handleRightClickPoint = (e: React.MouseEvent, poseIndex: number, pointIndex: number) => {
        e.preventDefault();
        e.stopPropagation();
        const newPoints = [...posePrompts];
        newPoints[poseIndex] = newPoints[poseIndex].filter((_, index) => index !== pointIndex);

        if (newPoints[poseIndex].length === 0) {
            newPoints.splice(poseIndex, 1);
        }

        setPosePrompts(newPoints);
    };

    const handleRightClickImage = (e: React.MouseEvent) => {
        e.preventDefault();
        if (imgRef.current) {
            const rect = imgRef.current.getBoundingClientRect();
            const x = Math.round(e.clientX - rect.left);
            const y = Math.round(e.clientY - rect.top);

            let closestPoseIndex = 0;
            let minDistance = Infinity;

            posePrompts.forEach((pose, poseIndex) => {
                pose.forEach(point => {
                    const distance = Math.sqrt(Math.pow(point[0] - x, 2) + Math.pow(point[1] - y, 2));
                    if (distance < minDistance) {
                        minDistance = distance;
                        closestPoseIndex = poseIndex;
                    }
                });
            });

            const newPoints = [...posePrompts];
            newPoints[closestPoseIndex] = [...newPoints[closestPoseIndex], [x, y, 1]];
            setPosePrompts(newPoints);
        }
    };

    const addNewTarget = () => {
        setPosePrompts([
            ...posePrompts,
            [[100, 100, 1]],
        ]);
        setOverlayStrategories([...overlayStrategies, 'none'])
    };

    const removeTarget = (targetIndex: number) => {
        const newPosePrompts = [...posePrompts];
        newPosePrompts.splice(targetIndex, 1);
        setPosePrompts(newPosePrompts);
    };

    const addPrompt = () => {
        setVideoPosePrompts({
            [currentFrame]: posePrompts,
        });
    };

    if (!videoId && videoList.length > 0) {
        return null;
    }

    const maskVideo = () => {
        dispatch(Command.Video.maskVideo({
            id: uuidv4(),
            type: 'sam2_masking',
            videoIds: [videoId!],
            resultVideoId: uuidv4(),
            runData: {
                videoMasking: {
                    posePrompts: {
                        [currentFrame]: posePrompts,
                    },
                    overlayStrategies,
                } as any,
                voiceMasking: {
                    strategy: 'remove',
                },
            },
        }));
    };

    const segmentPrompt = () => {
        Api.fetchPosePromptSegmentation(videoId!, currentFrame, posePrompts).then((segmentationImage) => {
            // Create a Blob from the binary data
            const blob = new Blob([segmentationImage], { type: 'image/jpeg' }); // Adjust the MIME type if needed
            // Create a URL for the Blob
            const imageUrl = URL.createObjectURL(blob);
            // Set the image URL in state
            setSegmentationImageUrl(imageUrl);
        });
    };

    const updateOverlayStrategy = (newValue: string, index: number) => {
        const newOverlayStrategies = [...overlayStrategies];
        newOverlayStrategies[index] = newValue;
        setOverlayStrategories(newOverlayStrategies);
    };

    return (
        <Box component="div" sx={{ display: 'flex' }}>
            <Box component='div' sx={{ width: 320 }}>
                <Button onClick={maskVideo} variant={'contained'} color={'secondary'} startIcon={<ShieldLogoIcon />}>Mask</Button>
                <Button onClick={segmentPrompt} variant={'contained'} color={'primary'} sx={{ marginLeft: 1, marginRight: 1 }}>Test</Button>

                <Divider sx={{ marginTop: 2 }} />

                {posePrompts.map((_, index) => (
                    <Box component='div' sx={{ marginTop: 1 }}>
                        <div>
                            Target {index + 1}
                            <IconButton><HighlightOffIcon onClick={() => removeTarget(index)} /></IconButton>
                        </div>

                        <InputLabel id="demo-simple-select-label">Overlay Strategy</InputLabel>
                        <Select 
                            labelId="demo-simple-select-label" 
                            label={`Overlay Strategy ${index + 1}`} 
                            value={overlayStrategies[index] || ''}
                            onChange={e => updateOverlayStrategy(e.target.value as string, index)}
                            size='small'
                        >
                            <MenuItem value={'none'}>No Overlay</MenuItem>
                            <MenuItem value={'mp_pose'}>MediaPipe Pose</MenuItem>
                            <MenuItem value={'mp_face'}>MediaPipe Face</MenuItem>
                            <MenuItem value={'mp_hand'}>MediaPipe Hands</MenuItem>
                            <MenuItem value={'openpose'}>Openpose</MenuItem>
                            <MenuItem value={'openpose_body25b'}>Openpose (BODY_25B)</MenuItem>
                            <MenuItem value={'openpose_face'}>Openpose + Face</MenuItem>
                            <MenuItem value={'openpose_body_135'}>Openpose (BODY_135)</MenuItem>
                        </Select>
                    </Box>
                ))}

                <Box component='div' sx={{ marginTop: 3}}>
                    <Button variant={'contained'} onClick={addNewTarget}>Add Target</Button>
                </Box>

                <Divider sx={{ marginTop: 2 }} />

                <Box component='div' sx={{ marginTop: 2}}>
                    <Button variant={'contained'} onClick={addPrompt}>Add Prompt</Button>
                </Box>

                {Object.entries(videoPosePrompts).map(([frameIndex, framePosePrompts]) => (
                    <Box component='div'>
                        <strong>Frame {frameIndex}:</strong><br />
                        {JSON.stringify(framePosePrompts)}
                    </Box>
                ))}
            </Box>
            <Box 
                component="div" 
                style={{position: 'relative', display: 'inline-block'}}
                onContextMenu={handleRightClickImage}
            >
                {videoId && (
                    <img
                        ref={imgRef}
                        src={segmentationImageUrl || `${Config.api.baseUrl}/videos/${videoId}/frames/${currentFrame}?token=${KeycloakAuth.getToken()}`}
                        alt="Video Frame"
                        style={{display: 'block'}}
                    />
                )}
                {posePrompts.map((pose, poseIndex) => (
                    pose.map((point, pointIndex) => (
                        <DraggablePoint
                            key={`${poseIndex}-${pointIndex}`}
                            position={{x: point[0], y: point[1]}}
                            onStart={handleDragStart}
                            onStop={(e, data) => handleDragStop(poseIndex, pointIndex, e, data)}
                            onContextMenu={(e) => handleRightClickPoint(e, poseIndex, pointIndex)}
                            bounds={bounds}
                            isActive={!!point[2]}
                            pointLabel={`(${Math.round(point[0])}, ${Math.round(point[1])})`}
                            promptNumber={poseIndex + 1}
                        />
                    ))
                ))}
            </Box>
        </Box>
    );
};

export default VideoMaskingEditorPage;

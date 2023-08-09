import { HidingMethods, MaskingMethods } from "../state/types/RunParamRendering";
import { blackoutFormSchemaBG, blackoutFormSchemaSubjectBBox, blackoutFormSchemaSubjectSilhouette, blackoutFormSchemaSubjectUI, blurFormSchemaBG, blurFormSchemaSubjectBBox, blurFormSchemaSubjectSilhouette, blurFormSchemaSubjectUI, bodyMeshFormSchema, faceMeshFormSchema, skeletonFormSchema } from "./formSchemas";

export const maskingMethods: MaskingMethods = {
    none: {
        name: "None",
        description: "Does not mask the subject in the video"
    },
    skeleton: {
        name: "Skeleton",
        description: "Displays a basic skeleton containing landmarks for the head, torso, arms and legs",
        parameterSchema: skeletonFormSchema,
        defaultValues: {
            maskingModel: "mediapipe",
            numPoses: 1,
            confidence: 0.5,
            timeseries: false
        }
    },
    faceMesh: {
        name: "Face Mesh",
        description: "Displays a detailed facemesh containing 478 Landmarks",
        parameterSchema: faceMeshFormSchema,
        defaultValues: {
            maskingModel: "mediapipe",
            numPoses: 1,
            confidence: 0.5,
            timeseries: false
        }
    },
    faceMeshSkeleton: {
        name: "Skeleton & Face Mesh",
        description: "Displays a skeleton with a detailed facemesh containing 478 Landmarks",
        parameterSchema: faceMeshFormSchema,
        defaultValues: {
            maskingModel: "mediapipe",
            numPoses: 1,
            confidence: 0.5,
            timeseries: false
        }
    }
}

export const hidingMethods: HidingMethods = {
    face: {
        none: {
            name: "None",
            description: "Does not hide the subject in the video"
        },
        blurBBox: {
            name: "Blur Boundingbox",
            description: "Gaussian Blurring",
            parameterSchema: blurFormSchemaSubjectBBox,
            uiSchema: blurFormSchemaSubjectUI,
            defaultValues: {
                subjectDetection: "boundingbox",
                detectionModel: "yolo",
                detectionParams: {
                    numPoses: 1,
                    confidence: 0.5
                },
                hidingParams: {
                    kernelSize: 23,
                    extraPixels: 0
                }
            }
        },
        blackoutBBox: {
            name: "Blackout BoundingBox",
            description: "Hiding the subject with the selected color",
            parameterSchema: blackoutFormSchemaSubjectBBox,
            uiSchema: blackoutFormSchemaSubjectUI,
            defaultValues: {
                subjectDetection: "boundingbox",
                detectionModel: "yolo",
                detectionParams: {
                    numPoses: 1,
                    confidence: 0.5
                },
                hidingParams: {
                    color: 0,
                    extraPixels: 0
                }
            }
        }
    },
    body: {
        none: {
            name: "None",
            description: "Does not hide the subject in the video"
        },
        blurBBox: {
            name: "Blur BoundingBox",
            description: "Gaussian Blurring",
            parameterSchema: blurFormSchemaSubjectBBox,
            uiSchema: blurFormSchemaSubjectUI,
            defaultValues: {
                subjectDetection: "silhouette",
                detectionModel: "mediapipe",
                detectionParams: {
                    numPoses: 1,
                    confidence: 0.5
                },
                hidingParams: {
                    kernelSize: 23,
                    extraPixels: 0
                }
            }
        },
        blurSilhouette: {
            name: "Blur Silhouette",
            description: "Gaussian Blurring",
            parameterSchema: blurFormSchemaSubjectSilhouette,
            uiSchema: blurFormSchemaSubjectUI,
            defaultValues: {
                subjectDetection: "boundingbox",
                detectionModel: "yolo",
                detectionParams: {
                    numPoses: 1,
                    confidence: 0.5
                },
                hidingParams: {
                    kernelSize: 23,
                    extraPixels: 0
                }
            }
        },
        blackoutBBox: {
            name: "Blackout Bounding Box",
            description: "Hiding the subject with the selected color",
            parameterSchema: blackoutFormSchemaSubjectBBox,
            uiSchema: blackoutFormSchemaSubjectUI,
            defaultValues: {
                subjectDetection: "silhouette",
                detectionModel: "mediapipe",
                detectionParams: {
                    numPoses: 1,
                    confidence: 0.5
                },
                hidingParams: {
                    color: 0,
                    extraPixels: 0
                }

            }
        },
        blackoutSilhouette: {
            name: "Blackout Silhouette",
            description: "Hiding the subject with the selected color",
            parameterSchema: blackoutFormSchemaSubjectSilhouette,
            uiSchema: blackoutFormSchemaSubjectUI,
            defaultValues: {
                subjectDetection: "silhouette",
                detectionModel: "mediapipe",
                detectionParams: {
                    numPoses: 1,
                    confidence: 0.5
                },
                hidingParams: {
                    color: 0,
                    extraPixels: 0
                }

            }
        },
    },
    "background": {
        none: {
            name: "None",
            description: "Does not hide the background of the video"
        },
        blur: {
            name: "Blur",
            description: "Gaussian Blurring",
            parameterSchema: blurFormSchemaBG,
            defaultValues: {
                subjectDetection: "silhouette",
                detectionModel: "mediapipe",
                detectionParams: {
                    numPoses: 1,
                    confidence: 0.5
                },
                hidingParams: {
                    kernelSize: 23,
                }
            }
        },
        blackout: {
            name: "Blackout",
            description: "Hiding the subject with the selected color",
            parameterSchema: blackoutFormSchemaBG,
            defaultValues: {
                subjectDetection: "silhouette",
                detectionModel: "mediapipe",
                detectionParams: {
                    numPoses: 1,
                    confidence: 0.5
                },
                hidingParams: {
                    color: 0,
                }
            }
        },
    }
}

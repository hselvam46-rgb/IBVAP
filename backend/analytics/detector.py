"""
YOLOv8 Detection Engine for Border Surveillance.
Detects and classifies Persons, Vehicles, and Fauna in real-time.
Includes both real YOLOv8 model inference and procedural video generator support.
"""

import numpy as np
from typing import List, Dict, Any, Optional
import cv2

# Threat classification mapping
THREAT_CLASSES = {"person"}
VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle", "bicycle"}
FAUNA_CLASSES = {"dog", "cow", "sheep", "horse", "bird", "cat"}


class Detection:
    def __init__(self, bbox: List[float], class_name: str, confidence: float, class_id: int = 0):
        # bbox is [x1, y1, x2, y2] normalized 0.0 to 1.0
        self.bbox = bbox
        self.class_name = class_name
        self.confidence = confidence
        self.class_id = class_id
        self.is_threat = class_name in THREAT_CLASSES
        self.is_vehicle = class_name in VEHICLE_CLASSES
        self.is_fauna = class_name in FAUNA_CLASSES

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bbox": [round(c, 4) for c in self.bbox],
            "class_name": self.class_name,
            "confidence": round(self.confidence, 3),
            "is_threat": self.is_threat,
            "is_vehicle": self.is_vehicle,
            "is_fauna": self.is_fauna
        }


class YOLOv8Detector:
    def __init__(self, model_name: str = "yolov8n.pt", conf_thresh: float = 0.45):
        self.conf_thresh = conf_thresh
        self.model = None
        self.model_loaded = False
        self._init_model(model_name)

    def _init_model(self, model_name: str):
        try:
            from ultralytics import YOLO
            self.model = YOLO(model_name)
            self.model_loaded = True
        except Exception:
            # Fallback will activate if weights are downloading or ultralytics is unavailable
            self.model = None
            self.model_loaded = False

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run inference on a BGR or RGB video frame.
        Returns a list of Detection objects with normalized bounding boxes.
        """
        h, w = frame.shape[:2]
        detections: List[Detection] = []

        if self.model_loaded and self.model is not None:
            try:
                results = self.model.predict(
                    source=frame,
                    conf=self.conf_thresh,
                    verbose=False,
                    device="cpu"
                )
                for r in results:
                    boxes = r.boxes
                    for box in boxes:
                        cls_id = int(box.cls[0].item())
                        cls_name = r.names.get(cls_id, "unknown")
                        conf = float(box.conf[0].item())
                        xyxy = box.xyxy[0].tolist()

                        # Normalize coordinates [0.0 - 1.0]
                        norm_bbox = [
                            max(0.0, min(1.0, xyxy[0] / w)),
                            max(0.0, min(1.0, xyxy[1] / h)),
                            max(0.0, min(1.0, xyxy[2] / w)),
                            max(0.0, min(1.0, xyxy[3] / h)),
                        ]
                        detections.append(Detection(
                            bbox=norm_bbox,
                            class_name=cls_name,
                            confidence=conf,
                            class_id=cls_id
                        ))
                return detections
            except Exception:
                pass

        # If model is not loaded or frame is procedural, return empty or caller uses procedural annotations
        return detections

"""
Thermal & Low-Light Night Surveillance Engine.
Enhances night CCTV feeds and applies tactical thermal colormaps (Ironbow, White-Hot, Black-Hot).
"""

import cv2
import numpy as np


class ThermalEngine:
    def __init__(self):
        self.clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(8, 8))

    def apply_thermal_processing(self, frame: np.ndarray, mode: str = "THERMAL_IRONBOW") -> np.ndarray:
        """
        Transform a video frame using tactical thermal IR shaders and dynamic range enhancement.
        mode: OPTICAL, THERMAL_IRONBOW, THERMAL_WHITEHOT, THERMAL_BLACKHOT
        """
        if mode == "OPTICAL":
            return frame

        # Convert to single channel grayscale
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        # Apply CLAHE dynamic range expansion
        enhanced_gray = self.clahe.apply(gray)

        if mode == "THERMAL_WHITEHOT":
            # Warm objects bright, cool background dark
            return cv2.cvtColor(enhanced_gray, cv2.COLOR_GRAY2BGR)

        elif mode == "THERMAL_BLACKHOT":
            # Inverted: warm objects dark, cool background bright
            inverted = cv2.bitwise_not(enhanced_gray)
            return cv2.cvtColor(inverted, cv2.COLOR_GRAY2BGR)

        elif mode == "THERMAL_IRONBOW":
            # Tactical Ironbow: OpenCV COLORMAP_INFERNO or COLORMAP_JET
            colored = cv2.applyColorMap(enhanced_gray, cv2.COLORMAP_INFERNO)
            return colored

        return frame

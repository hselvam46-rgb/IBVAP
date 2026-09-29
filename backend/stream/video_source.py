"""
Border CCTV, Thermal, Webcam & Mobile Phone Stream Manager.
Supports:
1. Live Laptop / Desktop Integrated Webcam (cv2.VideoCapture(0))
2. Mobile Phone Camera via Wi-Fi (IP Webcam / DroidCam / RTSP stream)
3. Eastern Frontier // Indo-Bangladesh Border (IBB) Sector Outposts:
   - CAM-01-IBB-PETRAPOLE: Zero Line Perimeter (South Bengal)
   - CAM-02-IBB-ICHAMATI: Riverine Ambush (Hasnabad/Taki Ichamati River Gap - Thermal Ironbow)
   - CAM-03-IBB-ICP-ANPR: ICP Integrated Checkpost Petrapole (ANPR Lane)
   - CAM-04-IBB-DAWKI: Smart Border Fence (Dawki River Gorge, Meghalaya - Night IR)
"""

import threading
import time
import cv2
import numpy as np
import math
from typing import Dict, Any, Tuple, List, Optional
from backend.analytics.detector import Detection, YOLOv8Detector


class HardwareCameraManager:
    """
    Thread-safe singleton camera manager.
    Coordinates physical laptop webcam and remote mobile camera feeds.
    Guarantees only one capture handle is active, avoiding DirectShow / MSMF hardware locks.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance.cap = None
                cls._instance.current_mode = "SECTOR"
                cls._instance.current_url = ""
                cls._instance.is_connecting = False
                cls._instance.error_msg = ""
                cls._instance.real_detector = None
                cls._instance.worker_lock = threading.Lock()
            return cls._instance

    def set_source(self, mode: str, mobile_url: str = ""):
        with self.worker_lock:
            if self.current_mode == mode and self.current_url == mobile_url and self.cap is not None and self.cap.isOpened():
                return

            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None

            self.current_mode = mode
            self.current_url = mobile_url
            self.error_msg = ""

            if mode in ("WEBCAM", "LAPTOP_WEBCAM"):
                self.is_connecting = True
                t = threading.Thread(target=self._connect_webcam, daemon=True)
                t.start()
            elif mode in ("MOBILE_CAM", "MOBILE"):
                self.is_connecting = True
                t = threading.Thread(target=self._connect_mobile, args=(mobile_url,), daemon=True)
                t.start()
            else:
                self.is_connecting = False

    def _connect_webcam(self):
        try:
            cap = None
            # Try default CAP_ANY first, then fallback safely
            for api_pref in [cv2.CAP_ANY, cv2.CAP_MSMF]:
                try:
                    c = cv2.VideoCapture(0, api_pref)
                    if c.isOpened():
                        cap = c
                        break
                    else:
                        c.release()
                except Exception:
                    continue

            if cap and cap.isOpened():
                with self.worker_lock:
                    self.cap = cap
                    self.is_connecting = False
                    self.error_msg = ""
                    if self.real_detector is None:
                        self.real_detector = YOLOv8Detector()
            else:
                with self.worker_lock:
                    self.cap = None
                    self.is_connecting = False
                    self.error_msg = "Webcam device 0 not responding or blocked by privacy setting"
        except BaseException as e:
            with self.worker_lock:
                self.cap = None
                self.is_connecting = False
                self.error_msg = str(e)

    def _connect_mobile(self, url: str):
        try:
            cap = cv2.VideoCapture(url)
            if cap.isOpened():
                with self.worker_lock:
                    self.cap = cap
                    self.is_connecting = False
                    self.error_msg = ""
                    if self.real_detector is None:
                        self.real_detector = YOLOv8Detector()
            else:
                with self.worker_lock:
                    self.cap = None
                    self.is_connecting = False
                    self.error_msg = f"Cannot reach stream at {url}"
        except Exception as e:
            with self.worker_lock:
                self.cap = None
                self.is_connecting = False
                self.error_msg = str(e)

    def read_frame(self, width: int, height: int):
        with self.worker_lock:
            if self.cap is not None and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    frame = cv2.resize(frame, (width, height))
                    detections = []
                    if self.real_detector is not None:
                        detections = self.real_detector.detect(frame)
                    return frame, detections, True, self.is_connecting, self.error_msg
            return None, [], False, self.is_connecting, self.error_msg


hardware_camera = HardwareCameraManager()


class SimulatedTarget:
    def __init__(
        self,
        class_name: str,
        start_pos: Tuple[float, float],
        velocity: Tuple[float, float],
        width: float,
        height: float,
        seed_hint: Optional[str] = None,
        plate_hint: Optional[str] = None,
        loiters_at: Optional[Tuple[float, float]] = None,
        loiter_duration: float = 0.0
    ):
        self.class_name = class_name
        self.x = start_pos[0]
        self.y = start_pos[1]
        self.vx = velocity[0]
        self.vy = velocity[1]
        self.width = width
        self.height = height
        self.seed_hint = seed_hint
        self.plate_hint = plate_hint
        self.loiters_at = loiters_at
        self.loiter_duration = loiter_duration
        self.loiter_timer = 0.0
        self.is_loitering = False

    def update(self, dt: float):
        if self.loiters_at and not self.is_loitering:
            dist = math.hypot(self.x - self.loiters_at[0], self.y - self.loiters_at[1])
            if dist < 0.05:
                self.is_loitering = True

        if self.is_loitering:
            self.loiter_timer += dt
            self.x += (np.random.rand() - 0.5) * 0.001
            self.y += (np.random.rand() - 0.5) * 0.001
            if self.loiter_timer >= self.loiter_duration:
                self.is_loitering = False
                self.loiters_at = None
        else:
            self.x += self.vx * dt
            self.y += self.vy * dt

        # Wrap around screen bounds
        if self.x > 1.1:
            self.x = -0.1
        elif self.x < -0.1:
            self.x = 1.1
        if self.y > 1.1:
            self.y = -0.1
        elif self.y < -0.1:
            self.y = 1.1

    def get_bbox(self) -> List[float]:
        x1 = max(0.0, self.x - self.width / 2.0)
        y1 = max(0.0, self.y - self.height / 2.0)
        x2 = min(1.0, self.x + self.width / 2.0)
        y2 = min(1.0, self.y + self.height / 2.0)
        return [x1, y1, x2, y2]


class BorderVideoSource:
    def __init__(self, camera_id: str, width: int = 640, height: int = 360):
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.frame_count = 0
        self.last_time = time.time()
        self.targets: List[SimulatedTarget] = []

        self.source_mode = "SECTOR"  # "SECTOR", "WEBCAM", "MOBILE_CAM"
        self.mobile_url: str = ""

        self._init_scene()

    def set_input_mode(self, mode: str, mobile_url: str = ""):
        """Switch video source between SECTOR, WEBCAM, and MOBILE_CAM non-blockingly."""
        self.source_mode = mode
        self.mobile_url = mobile_url
        hardware_camera.set_source(mode, mobile_url)

    def _init_scene(self):
        """Initialize scenario targets per Indo-Bangladesh Border camera post."""
        if self.camera_id in ("CAM-01-IBB-PETRAPOLE", "CAM-01-ZERO-LINE"):
            # Scenario: Inbound movement across Petrapole Zero Line
            self.targets = [
                SimulatedTarget(
                    class_name="person",
                    start_pos=(0.30, 0.25),
                    velocity=(0.008, 0.035),  # Inbound towards bottom
                    width=0.08,
                    height=0.22,
                    seed_hint="synthetic_test_profile_01",  # Synthetic calibration profile 01
                    loiters_at=(0.45, 0.55),
                    loiter_duration=95.0  # Will trigger 90s loitering alert
                ),
                SimulatedTarget(
                    class_name="dog",
                    start_pos=(0.80, 0.70),
                    velocity=(-0.015, -0.005),
                    width=0.07,
                    height=0.08
                )
            ]
        elif self.camera_id in ("CAM-02-IBB-ICHAMATI", "CAM-02-RIVERINE-THERMAL"):
            # Scenario: Night riverine crossing in Ichamati river
            self.targets = [
                SimulatedTarget(
                    class_name="person",
                    start_pos=(0.20, 0.30),
                    velocity=(0.022, 0.025),
                    width=0.07,
                    height=0.18,
                    seed_hint="synthetic_test_profile_02"  # Synthetic reference profile 02
                )
            ]
        elif self.camera_id in ("CAM-03-IBB-ICP-ANPR", "CAM-03-CHECKPOST-ANPR"):
            # Scenario: Petrapole ICP cargo checkpost lane
            self.targets = [
                SimulatedTarget(
                    class_name="car",
                    start_pos=(-0.10, 0.65),
                    velocity=(0.06, 0.0),
                    width=0.32,
                    height=0.28,
                    plate_hint="WB02TEST9912"  # Synthetic test hotlist plate
                ),
                SimulatedTarget(
                    class_name="truck",
                    start_pos=(1.2, 0.55),
                    velocity=(-0.04, 0.0),
                    width=0.40,
                    height=0.35,
                    plate_hint="DL01AB1234"  # Clean standard plate
                )
            ]
        else:  # CAM-04-IBB-DAWKI
            self.targets = [
                SimulatedTarget(
                    class_name="cow",
                    start_pos=(0.60, 0.40),
                    velocity=(0.004, 0.002),
                    width=0.14,
                    height=0.12
                ),
                SimulatedTarget(
                    class_name="person",
                    start_pos=(0.20, 0.50),
                    velocity=(0.002, 0.001),
                    width=0.07,
                    height=0.20,
                    loiters_at=(0.25, 0.52),
                    loiter_duration=120.0
                )
            ]

    def read_frame(self) -> Tuple[np.ndarray, List[Detection], List[SimulatedTarget]]:
        now = time.time()
        dt = min(0.1, max(0.01, now - self.last_time))
        self.last_time = now
        self.frame_count += 1

        # ==============================================================================
        # 1. REAL WEBCAM OR MOBILE PHONE CAMERA CAPTURE
        # ==============================================================================
        if self.source_mode in ("WEBCAM", "MOBILE_CAM"):
            real_frame, detections, success, is_connecting, err_msg = hardware_camera.read_frame(self.width, self.height)
            if success and real_frame is not None:
                # Check for physical privacy shutter / Lenovo Vantage Privacy Mode
                mean_val = float(np.mean(real_frame))
                std_val = float(np.std(real_frame))
                if self.source_mode == "WEBCAM" and mean_val < 30.0 and std_val < 3.0:
                    # Physical shutter is closed! Display helpful tactical HUD warning directly on the frame
                    overlay = real_frame.copy()
                    cv2.rectangle(overlay, (15, 15), (self.width - 15, self.height - 15), (10, 15, 25), -1)
                    cv2.addWeighted(overlay, 0.70, real_frame, 0.30, 0, real_frame)
                    cv2.rectangle(real_frame, (15, 15), (self.width - 15, self.height - 15), (0, 160, 255), 2)
                    cv2.putText(real_frame, "[CAMERA PRIVACY ACTIVE / SHUTTER CLOSED]", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 220, 255), 2)
                    cv2.putText(real_frame, "Webcam is connected, but the lens is blocked or muted:", (30, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (220, 220, 220), 1)
                    cv2.putText(real_frame, "1. Open the physical slider switch above your laptop screen", (30, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 180), 1)
                    cv2.putText(real_frame, "2. In Lenovo Vantage, turn OFF 'Camera Privacy Mode'", (30, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 180), 1)
                    cv2.putText(real_frame, "3. Press Fn + Camera Privacy key (F8 / F9 / F10)", (30, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 180), 1)
                    cv2.putText(real_frame, "4. Check Windows Settings -> Privacy & Security -> Camera", (30, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 180), 1)
                else:
                    # Normal real-time frame with tactical watermark
                    src_label = "LIVE LAPTOP WEBCAM [DEV-0]" if self.source_mode == "WEBCAM" else f"MOBILE CAM: {self.mobile_url}"
                    cv2.rectangle(real_frame, (10, 10), (320, 32), (8, 12, 20), -1)
                    cv2.rectangle(real_frame, (10, 10), (320, 32), (0, 212, 255), 1)
                    cv2.putText(real_frame, f"LIVE FEED: {src_label}", (16, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 212, 255), 1)

                return real_frame, detections, []

            # Standby screen when connecting or if an error occurred
            standby = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            standby[:] = [15, 20, 30]
            header = "CONNECTING TO INTEGRATED WEBCAM..." if self.source_mode == "WEBCAM" else "CONNECTING TO MOBILE PHONE CAMERA..."
            sub = "Initializing Hardware Device 0..." if self.source_mode == "WEBCAM" else f"Target URL: {self.mobile_url}"
            hint = "Ensure webcam is enabled in OS settings" if self.source_mode == "WEBCAM" else "Ensure IP Webcam / DroidCam is active on mobile Wi-Fi"

            if err_msg:
                cv2.putText(standby, f"FEED OFFLINE: {err_msg}", (30, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 100, 255), 1)
            else:
                cv2.putText(standby, header, (30, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 212, 255), 2)
            cv2.putText(standby, sub, (30, 175), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (160, 180, 200), 1)
            cv2.putText(standby, hint, (30, 205), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 229, 163), 1)
            return standby, [], []

        # ==============================================================================
        # 2. INDO-BANGLADESH SECTOR SIMULATION FEED
        # ==============================================================================
        frame = self._render_background()

        detections: List[Detection] = []
        for target in self.targets:
            target.update(dt)
            bbox = target.get_bbox()
            self._render_target(frame, target, bbox)

            conf = 0.88 + 0.10 * np.sin(self.frame_count * 0.1)
            detections.append(Detection(
                bbox=bbox,
                class_name=target.class_name,
                confidence=float(conf)
            ))

        return frame, detections, self.targets

    def _render_background(self) -> np.ndarray:
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        if self.camera_id in ("CAM-01-IBB-PETRAPOLE", "CAM-01-ZERO-LINE"):
            # South Bengal Petrapole Border - Lush tropical vegetation & smart fence
            frame[:int(self.height * 0.35), :] = [170, 160, 140]  # Humid eastern sky
            frame[int(self.height * 0.35):, :] = [45, 100, 50]    # Green foliage / delta terrain
            # Draw barbed wire border fence
            fy = int(self.height * 0.48)
            cv2.line(frame, (0, fy), (self.width, fy), (50, 50, 50), 3)
            cv2.line(frame, (0, fy + 25), (self.width, fy + 25), (60, 60, 60), 2)
            for x in range(0, self.width, 40):
                cv2.line(frame, (x, fy - 25), (x, fy + 45), (40, 40, 40), 4)

        elif self.camera_id in ("CAM-02-IBB-ICHAMATI", "CAM-02-RIVERINE-THERMAL"):
            # Night riverine terrain (Ichamati River gap between India & Bangladesh)
            frame[:int(self.height * 0.3), :] = [20, 15, 10]
            frame[int(self.height * 0.3):int(self.height * 0.7), :] = [55, 45, 30]  # River water
            frame[int(self.height * 0.7):, :] = [30, 40, 25]  # Mud river bank

        elif self.camera_id in ("CAM-03-IBB-ICP-ANPR", "CAM-03-CHECKPOST-ANPR"):
            # Petrapole Integrated Checkpost (ICP) Cargo Lane
            frame[:, :] = [55, 55, 55]  # Asphalt road
            for y in range(0, self.height, 60):
                cv2.line(frame, (int(self.width * 0.5), y), (int(self.width * 0.5), y + 35), (200, 200, 200), 4)
            cv2.rectangle(frame, (0, int(self.height * 0.88)), (self.width, self.height), (20, 180, 220), -1)

        else:  # CAM-04-IBB-DAWKI
            # Dawki river gorge / Umngot river border rocky terrain
            frame[:, :] = [35, 40, 45]
            cv2.line(frame, (0, int(self.height * 0.6)), (self.width, int(self.height * 0.6)), (20, 25, 30), 6)

        return frame

    def _render_target(self, frame: np.ndarray, target: SimulatedTarget, bbox: List[float]):
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = int(bbox[0] * w), int(bbox[1] * h), int(bbox[2] * w), int(bbox[3] * h)

        if target.class_name == "person":
            color = (40, 70, 180) if "ICHAMATI" not in self.camera_id and "THERMAL" not in self.camera_id else (240, 220, 180)
            head_radius = max(4, int((y2 - y1) * 0.16))
            head_cx = (x1 + x2) // 2
            head_cy = y1 + head_radius
            cv2.circle(frame, (head_cx, head_cy), head_radius, color, -1)
            cv2.rectangle(frame, (x1 + 4, head_cy + head_radius), (x2 - 4, y2), color, -1)

        elif target.class_name in ("car", "truck"):
            color = (180, 80, 40) if target.class_name == "car" else (70, 100, 110)
            cv2.rectangle(frame, (x1, y1 + int((y2 - y1) * 0.2)), (x2, y2), color, -1)
            cv2.rectangle(frame, (x1 + int((x2 - x1) * 0.2), y1), (x2 - int((x2 - x1) * 0.2), y1 + int((y2 - y1) * 0.4)), (210, 210, 210), -1)
            if target.plate_hint:
                pw = max(30, int((x2 - x1) * 0.45))
                ph = max(12, int((y2 - y1) * 0.16))
                px1 = (x1 + x2) // 2 - pw // 2
                py1 = y2 - ph - 6
                cv2.rectangle(frame, (px1, py1), (px1 + pw, py1 + ph), (240, 240, 240), -1)
                cv2.rectangle(frame, (px1, py1), (px1 + pw, py1 + ph), (10, 10, 10), 1)
                cv2.putText(frame, target.plate_hint, (px1 + 2, py1 + ph - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (10, 10, 10), 1)

        elif target.class_name in ("dog", "cow"):
            color = (60, 110, 140) if target.class_name == "dog" else (120, 120, 120)
            ax_w = max(1, abs(x2 - x1) // 2)
            ax_h = max(1, abs(y2 - y1) // 2)
            cv2.ellipse(frame, ((x1 + x2) // 2, (y1 + y2) // 2), (ax_w, ax_h), 0, 0, 360, color, -1)

"""
Platform Configuration for IBVAP Edge Node.
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
SNAPSHOT_DIR = os.path.join(DATA_DIR, "snapshots")
EVIDENCE_DIR = os.path.join(DATA_DIR, "evidence")
WATCHLIST_DIR = os.path.join(BASE_DIR, "frontend", "assets", "watchlist")

os.makedirs(SNAPSHOT_DIR, exist_ok=True)
os.makedirs(EVIDENCE_DIR, exist_ok=True)
os.makedirs(WATCHLIST_DIR, exist_ok=True)

# Sector Isolation & Access Partitioning (Principle of Least Privilege)
CURRENT_NODE_SECTOR = "INDO_BANGLADESH_BORDER"
CURRENT_SECTOR_NAME = "Eastern Frontier // Indo-Bangladesh Border (IBB Sector)"
SECTOR_CODE = "IBB_EASTERN"

# Live Video Ingestion Modes
ACTIVE_INPUT_MODE = "IBB_SECTOR"  # "IBB_SECTOR", "WEBCAM", "MOBILE_CAM"
WEBCAM_INDEX = 0
MOBILE_CAM_URL = "http://192.168.1.5:8080/video"  # Default mobile IP webcam URL

# Performance & Analytics Defaults
DETECTION_CONFIDENCE_THRESHOLD = 0.50
FALSE_ALARM_MIN_BBOX_AREA = 0.002  # Minimum relative frame area (filters small rodents/birds)
LOITERING_DEFAULT_THRESHOLD_SECONDS = 90.0  # Standardized 90s border intrusion dwell default
FACE_SIMILARITY_MATCH_THRESHOLD = 0.72  # Cosine similarity threshold for ArcFace 512-d
ANPR_MIN_CONFIDENCE = 0.65

# Biometric & Data Minimisation Rules
DATA_RETENTION_HOURS = 72  # 72-hour rolling purge for unflagged video / frames
STORE_UNMATCHED_PROBES = False  # Dropped immediately from memory per data minimisation mandate

# Edge Store-and-Forward Defaults
HQ_SYNC_URL = "http://127.0.0.1:8000/api/hq/sync"  # Local/remote HQ sync endpoint
HEARTBEAT_INTERVAL_SECONDS = 5.0
DEFAULT_LINK_ONLINE = True

# Security
SECRET_KEY = "IBVAP_SECURE_EDGE_TOKEN_KEY_DEFENSE_OPS"
SESSION_EXPIRE_HOURS = 12

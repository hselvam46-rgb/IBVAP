"""
Circular Frame Buffer & 1-Click Forensic Evidence Exporter.
Maintains a rolling in-memory buffer of recent frames and generates
cryptographically-hashed evidence packages for court and audit review.
"""

import os
import time
import cv2
import hashlib
import json
import numpy as np
from collections import deque
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from backend.core.config import EVIDENCE_DIR, SNAPSHOT_DIR


class CircularFrameBuffer:
    def __init__(self, camera_id: str, max_frames: int = 150):
        self.camera_id = camera_id
        self.max_frames = max_frames
        self.buffer = deque(maxlen=max_frames)

    def add_frame(self, frame: np.ndarray, timestamp: float):
        self.buffer.append((frame.copy(), timestamp))

    def save_snapshot(self, alert_id: str) -> str:
        """Save latest frame as a snapshot."""
        if not self.buffer:
            # Create a blank fallback frame
            blank = np.zeros((360, 640, 3), dtype=np.uint8)
            fname = f"snap_{alert_id}.jpg"
            fpath = os.path.join(SNAPSHOT_DIR, fname)
            cv2.imwrite(fpath, blank)
            return fpath

        frame, ts = self.buffer[-1]
        fname = f"snap_{alert_id}.jpg"
        fpath = os.path.join(SNAPSHOT_DIR, fname)
        cv2.imwrite(fpath, frame)
        return fpath

    def export_evidence_package(
        self,
        alert_id: str,
        operator_id: str,
        notes: str = ""
    ) -> Dict[str, Any]:
        """
        Package the circular buffer into an evidentiary video clip + manifest with SHA-256 integrity hash.
        """
        if not self.buffer:
            return {"error": "Frame buffer is empty"}

        frames_to_save = list(self.buffer)
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        clip_name = f"evidence_{alert_id}_{timestamp_str}.mp4"
        clip_path = os.path.join(EVIDENCE_DIR, clip_name)

        h, w = frames_to_save[0][0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(clip_path, fourcc, 20.0, (w, h))

        for frame, _ in frames_to_save:
            writer.write(frame)
        writer.release()

        # Compute SHA-256 hash of the generated evidence video
        sha256_hash = hashlib.sha256()
        with open(clip_path, "rb") as f:
            while chunk := f.read(8192):
                sha256_hash.update(chunk)
        file_hash = sha256_hash.hexdigest()

        # Write forensic manifest
        manifest = {
            "evidence_id": f"EVID-{alert_id}",
            "alert_id": alert_id,
            "camera_id": self.camera_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operator_id": operator_id,
            "frame_count": len(frames_to_save),
            "video_file": clip_name,
            "file_size_bytes": os.path.getsize(clip_path),
            "sha256_digest": file_hash,
            "notes": notes,
            "chain_of_custody": "SEALED_ON_PREMISE_EDGE"
        }

        manifest_name = f"evidence_{alert_id}_{timestamp_str}_manifest.json"
        manifest_path = os.path.join(EVIDENCE_DIR, manifest_name)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        return {
            "status": "SUCCESS",
            "clip_path": clip_path,
            "clip_filename": clip_name,
            "manifest_path": manifest_path,
            "sha256_digest": file_hash,
            "frame_count": len(frames_to_save)
        }

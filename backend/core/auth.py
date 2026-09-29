"""
Operator Authentication and Role-Based Access Control for IBVAP.
Roles:
- OPERATOR: Live monitoring, alert acknowledgment, note submission.
- DUTY_OFFICER: Escalation to BSF HQ/QRF, zone management, false alarm dismissal.
- ADMIN: System configuration, watchlist updates, audit trail verification.
"""

import hmac
import hashlib
import time
import json
import base64
from typing import Optional, Dict
from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from backend.core.config import SECRET_KEY, SESSION_EXPIRE_HOURS
from backend.database.models import User
from backend.database.db import get_db, hash_password


ROLE_HIERARCHY = {
    "OPERATOR": 1,
    "DUTY_OFFICER": 2,
    "ADMIN": 3
}


def create_session_token(user: User) -> str:
    """Create a signed session token containing user ID, role, and expiry."""
    payload = {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "badge_number": user.badge_number,
        "exp": int(time.time()) + (SESSION_EXPIRE_HOURS * 3600)
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    signature = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_session_token(token: str) -> Optional[Dict]:
    """Verify session token integrity and expiration."""
    if not token or "." not in token:
        return None
    try:
        payload_b64, signature = token.split(".", 1)
        expected_sig = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode()).decode())
        if time.time() > payload.get("exp", 0):
            return None
        return payload
    except Exception:
        return None


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> User:
    """FastAPI dependency for authenticating incoming API calls."""
    if not authorization:
        # Check if query parameter or fallback for local dev
        raise HTTPException(status_code=401, detail="Authentication session required")

    token = authorization.replace("Bearer ", "").strip()
    session_data = verify_session_token(token)
    if not session_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")

    user = db.query(User).filter(User.id == session_data["user_id"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="User account not found")
    return user


def require_role(min_role: str):
    """Decorator / dependency factory for minimum role enforcement."""
    def role_checker(user: User = Depends(get_current_user)) -> User:
        user_level = ROLE_HIERARCHY.get(user.role, 0)
        required_level = ROLE_HIERARCHY.get(min_role, 999)
        if user_level < required_level:
            raise HTTPException(
                status_code=403,
                detail=f"Forbidden: Action requires at least {min_role} clearance (your role: {user.role})"
            )
        return user
    return role_checker

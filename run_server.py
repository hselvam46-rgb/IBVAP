"""
IBVAP Platform Runner.
Starts the unified FastAPI edge server on port 8000.
"""

import uvicorn
import os
import sys

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print("=" * 65)
    print("  IBVAP: Intelligent Border Vigilance & Analytics Platform")
    print(f"  Tactical C4I Operator Console -> http://0.0.0.0:{port}")
    print("=" * 65)
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)


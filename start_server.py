"""
start_server.py — Starts the IBVAP Alarm Manager API + Dashboard

Usage:
    python start_server.py
    Then open: http://localhost:8000/ui
"""
import sys
import subprocess

try:
    import multipart
except ImportError:
    print("Auto-installing python-multipart into your environment...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-multipart"])

import shutil
import uvicorn
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Ensure dashboard frontend is built if dist is missing
_root = Path(__file__).resolve().parent
_dist = _root / "website" / "dashboard" / "dist"
_dashboard = _root / "website" / "dashboard"

if not (_dist / "index.html").exists() and (_dashboard / "package.json").exists():
    npm_bin = shutil.which("npm")
    if npm_bin:
        print("React dashboard build missing. Building frontend...")
        try:
            if not (_dashboard / "node_modules").exists():
                subprocess.check_call([npm_bin, "install"], cwd=str(_dashboard))
            subprocess.check_call([npm_bin, "run", "build"], cwd=str(_dashboard))
            print("React dashboard built successfully.")
        except Exception as err:
            print(f"Warning: Failed to build React dashboard ({err}). Fallback UI will be used.")

from alarm_manager.src.api import app as api_app

if __name__ == "__main__":
    print("=" * 55)
    print("  IBVAP Alarm Manager Server")
    print("  API Docs:  http://localhost:8000/docs")
    print("  Dashboard: http://localhost:8000/ui")
    print("=" * 55)
    uvicorn.run(
        api_app,
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="warning",
    )

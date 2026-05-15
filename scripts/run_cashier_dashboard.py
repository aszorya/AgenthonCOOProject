"""Start cashier Streamlit dashboard. Run from coopilot/: python scripts/run_cashier_dashboard.py"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
app = ROOT / "dashboard" / "cashier_app.py"

if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(
            [sys.executable, "-m", "streamlit", "run", str(app), "--server.headless", "true"],
            cwd=str(ROOT),
        )
    )

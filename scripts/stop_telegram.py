"""Stop all local COOPilot Telegram bot processes."""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    if sys.platform != "win32":
        print("Run: pkill -f run_telegram.py")
        return 0

    ps = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
            "Where-Object { $_.CommandLine -match 'run_telegram' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }",
        ],
        capture_output=True,
        text=True,
    )
    killed = [x.strip() for x in ps.stdout.splitlines() if x.strip()]
    if killed:
        print("Stopped PIDs:", ", ".join(killed))
    else:
        print("No run_telegram.py process found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Use --headless for the CLI subset, or run the real window acceptance."""
import argparse
import os
import subprocess
import sys

from vel_env import ROOT, tool_environment

parser = argparse.ArgumentParser()
parser.add_argument("--headless", action="store_true")
args = parser.parse_args()
command = [sys.executable, ROOT / "tests/gui/test_gui_h1.py"]
if args.headless:
    command.extend(["Registry", "Lifecycle"])
elif not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
    parser.error("WSLg display unavailable. Use --headless for CLI-only verification.")
raise SystemExit(subprocess.run(command, cwd=ROOT, env=tool_environment(), timeout=210).returncode)

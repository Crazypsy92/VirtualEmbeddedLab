#!/usr/bin/env python3
"""Verify the pinned Zephyr dependencies, or fetch the exact local archives."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

from vel_env import ROOT, nonroot, tool, zephyr_base, zephyr_environment


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    nonroot()
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true", help="download only pinned source archives")
    options = parser.parse_args()
    base = zephyr_base()
    workspace = base.parent
    workspace.mkdir(parents=True, exist_ok=True)
    meta = json.loads((ROOT / "zephyr/versions.json").read_text())
    destinations = {"zephyr": base, **{
        name: workspace / "modules/hal" / name for name in ("cmsis", "cmsis_6")
    }}
    env = zephyr_environment("cross-compile")
    for name, entry in meta["sources"].items():
        destination = destinations[name]
        archive = workspace / entry["archive"]
        if options.install and not destination.exists():
            with tempfile.TemporaryDirectory(dir=workspace) as temporary:
                if not archive.exists():
                    partial = Path(temporary) / entry["archive"]
                    subprocess.run(["curl", "-fsSL", "--max-time", "180", entry["url"],
                                    "-o", partial], check=True, timeout=185)
                    if sha256(partial) != entry["sha256"]:
                        raise SystemExit(f"Archive checksum mismatch for {name}")
                    partial.rename(archive)
                if sha256(archive) != entry["sha256"]:
                    raise SystemExit(f"Archive checksum mismatch for {name}")
                with tarfile.open(archive) as stream:
                    stream.extractall(temporary, filter="data")
                destination.parent.mkdir(parents=True, exist_ok=True)
                (Path(temporary) / entry["archive_root"]).rename(destination)
        if not destination.is_dir():
            raise SystemExit(f"Missing {name}: {destination}. Re-run with --install.")
        if (destination / ".git").exists():
            revision = subprocess.check_output(["git", "-C", destination, "rev-parse", "HEAD"],
                                               text=True, timeout=10).strip()
            if revision != entry["commit"]:
                raise SystemExit(f"Unexpected revision for {name}: {revision}")
        elif not archive.is_file() or sha256(archive) != entry["sha256"]:
            raise SystemExit(f"Cannot verify pinned {name}. Need its Git checkout or original archive.")
        print(f"{name}: {entry['commit']}")
    if options.install and not (workspace / ".west").exists():
        subprocess.run([sys.executable, "-m", "west", "init", "-l", base],
                       env=env, cwd=workspace, check=True, timeout=30)
    for name in ("dtc", "arm-none-eabi-gcc", "qemu-system-arm"):
        subprocess.run([tool(name), "--version"], env=env, check=True, timeout=15,
                       stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, "-m", "west", "--version"], env=env, check=True, timeout=15)
    print("STAGE4_EXTERNAL_ENVIRONMENT_VERIFIED")


if __name__ == "__main__":
    main()

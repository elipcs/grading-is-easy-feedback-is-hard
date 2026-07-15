#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_step(script_relative_path: str, experiment: str, extra_args: list[str] | None = None):
    command = [
        sys.executable,
        str(PROJECT_ROOT / script_relative_path),
        "--experiment",
        experiment,
    ]
    if extra_args:
        command.extend(extra_args)
    print(" ".join(command))
    subprocess.run(command, check=True)

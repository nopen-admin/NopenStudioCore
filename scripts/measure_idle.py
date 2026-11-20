#!/usr/bin/env python3
"""Measure the inactive Buddy runner using Linux /proc and isolated state."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

CLI = Path(__file__).resolve().parents[1] / "nopen"
DRIVERS = re.compile(r"lib(?:cuda|opencl|vulkan|egl|glx|d3d)|_dri\.so", re.IGNORECASE)


def sample(pid):
    proc = Path("/proc") / str(pid)
    fields = (proc / "stat").read_text().rpartition(")")[2].split()
    cpu_ticks = int(fields[11]) + int(fields[12])
    status = (proc / "status").read_text()
    rss = int(re.search(r"^VmRSS:\s+(\d+)", status, re.MULTILINE).group(1))
    driver_mapped = bool(DRIVERS.search((proc / "maps").read_text()))
    descriptors = [os.readlink(path) for path in (proc / "fd").iterdir()]
    gpu_device = any(path.startswith(("/dev/dri/", "/dev/nvidia", "/dev/kfd")) for path in descriptors)
    socket_open = any(path.startswith("socket:") for path in descriptors)
    return cpu_ticks, rss, driver_mapped, gpu_device, socket_open


def measure(seconds, check_interval, state):
    env = dict(os.environ, XDG_STATE_HOME=state)
    command = lambda *args: subprocess.run([CLI, *args], env=env, check=True, capture_output=True,
                                            text=True, timeout=10)
    command("init", "--decline")
    runner = subprocess.Popen([CLI, "run", "--check-interval", str(check_interval)], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 5
        while json.loads(command("status").stdout)["mode"] != "READY":
            if runner.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("Runner did not become READY.")
            time.sleep(0.05)
        started = time.monotonic()
        first = sample(runner.pid)
        time.sleep(seconds)
        last = sample(runner.pid)
        elapsed = time.monotonic() - started
        ticks = last[0] - first[0]
        return {
            "seconds": round(elapsed, 3),
            "check_interval_seconds": check_interval,
            "cpu_ticks": ticks,
            "clock_ticks_per_second": os.sysconf("SC_CLK_TCK"),
            "cpu_percent_one_core": round(100 * ticks / os.sysconf("SC_CLK_TCK") / elapsed, 3),
            "rss_kib_at_start_end": [first[1], last[1]],
            "gpu_driver_mapping_sampled": first[2] or last[2],
            "gpu_device_fd_sampled": first[3] or last[3],
            "socket_fd_sampled": first[4] or last[4],
            "observer": json.loads(command("observe", "status").stdout),
        }
    finally:
        try:
            command("stop")
            runner.wait(timeout=5)
        finally:
            if runner.poll() is None:
                runner.kill()
                runner.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=35)
    parser.add_argument("--check-interval", type=int, default=30)
    args = parser.parse_args()
    if args.seconds < 1 or not 1 <= args.check_interval <= 3600:
        parser.error("--seconds must be positive and --check-interval must be 1–3600")
    with tempfile.TemporaryDirectory() as state:
        print(json.dumps(measure(args.seconds, args.check_interval, state), indent=2))


if __name__ == "__main__":
    main()

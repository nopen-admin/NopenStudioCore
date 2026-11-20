"""Measure new process startup, fixture checkpoint latency and 30s idle on Linux."""

import argparse
import json
import math
import os
from pathlib import Path
import re
import select
import statistics
import subprocess
import tempfile
import time

DRIVER = re.compile(r"lib(?:cuda|opencl|vulkan|egl|glx)|_dri\.so", re.IGNORECASE)


def sample(process):
    proc = Path("/proc") / str(process.pid)
    stat = (proc / "stat").read_text().rpartition(")")[2].split()
    rss = int(re.search(r"^VmRSS:\s+(\d+)", (proc / "status").read_text(), re.MULTILINE)[1])
    paths = [os.readlink(fd) for fd in (proc / "fd").iterdir()]
    return {
        "ticks": int(stat[11]) + int(stat[12]),
        "rss_kib": rss,
        "socket": any(path.startswith("socket:") for path in paths),
        "gpu_device": any(path.startswith(("/dev/dri/", "/dev/nvidia", "/dev/kfd")) for path in paths),
        "gpu_mapping": bool(DRIVER.search((proc / "maps").read_text())),
    }


def latency(command, env, root, count, args, state):
    samples = []
    for index in range(count):
        started = time.perf_counter_ns()
        result = subprocess.run([*command, "--state", root / f"{args[0]}-{index}", *args],
                                env=env, check=True, capture_output=True, text=True, timeout=15)
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
        assert json.loads(result.stdout)["state"] == state
    return {"median_ms": round(statistics.median(samples), 3),
            "p95_ms": round(sorted(samples)[math.ceil(0.95 * count) - 1], 3)}


def measure(command, root, count, seconds):
    env = dict(os.environ)
    env.pop("DOTNET_EnableDiagnostics", None)
    if Path(command[0]).name == "dotnet":
        env["DOTNET_EnableDiagnostics"] = "0"
    start = latency(command, env, root, count, ["status"], "IDLE")
    work = latency(command, env, root, count, ["demo", "benchmark", "--approve"], "DONE")
    with subprocess.Popen([*command, "--state", root / "idle", "run"], env=env,
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as process:
        try:
            assert select.select([process.stdout], [], [], 5)[0], "Console readiness timed out."
            assert json.loads(process.stdout.readline())["state"] == "IDLE"
            time.sleep(0.2)
            begun = time.monotonic()
            first = sample(process)
            time.sleep(seconds)
            last = sample(process)
            elapsed = time.monotonic() - begun
            ticks = last["ticks"] - first["ticks"]
            assert process.communicate("çık\n", timeout=5)[0] == ""
            assert process.returncode == 0
        finally:
            if process.poll() is None:
                process.kill()
    return {
        "process_invocations_per_case": count, "cold_process_status": start, "fixture_commit_and_exit": work,
        "idle_seconds": round(elapsed, 3), "idle_cpu_ticks": ticks,
        "clock_ticks_per_sec": os.sysconf("SC_CLK_TCK"),
        "rss_kib_samples": [first["rss_kib"], last["rss_kib"]],
        "socket_fd_sampled": first["socket"] or last["socket"],
        "gpu_device_fd_sampled": first["gpu_device"] or last["gpu_device"],
        "gpu_mapping_sampled": first["gpu_mapping"] or last["gpu_mapping"],
        "application_file_bytes": Path(command[-1]).stat().st_size,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--idle-seconds", type=int, default=30)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    options = parser.parse_args()
    command = options.command[1:] if options.command[:1] == ["--"] else options.command
    if options.samples < 30 or options.idle_seconds < 30 or not command:
        parser.error("Provide a CLI command, at least 30 samples and at least 30 idle seconds.")
    with tempfile.TemporaryDirectory() as directory:
        print(json.dumps(measure(command, Path(directory), options.samples, options.idle_seconds), indent=2))

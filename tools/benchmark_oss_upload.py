"""Compare GitHub Runner upload throughput to regular and accelerated OSS endpoints.

Only multipart parts are uploaded. Every upload is aborted; no Object is completed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from oss_mirror import Oss


PART_SIZE = 16 * 1024 * 1024
PART_COUNT = 4
ENDPOINTS = (
    ("accelerated", "https://oss-accelerate.aliyuncs.com"),
    ("direct", "https://oss-cn-beijing.aliyuncs.com"),
    ("accelerated-repeat", "https://oss-accelerate.aliyuncs.com"),
)


def parse_upload_id(output: str) -> str:
    def find(value: object) -> str | None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower().replace("_", "") == "uploadid" and isinstance(child, str):
                    return child
                found = find(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = find(child)
                if found:
                    return found
        return None

    try:
        upload_id = find(json.loads(output))
    except ValueError:
        upload_id = None
    if not upload_id:
        match = re.search(r"\bUploadId\b['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9-]{8,128})", output, re.I)
        upload_id = match.group(1) if match else None
    if not upload_id or not re.fullmatch(r"[A-Za-z0-9-]{8,128}", upload_id):
        raise RuntimeError("OSS did not return a usable multipart upload ID")
    return upload_id


def upload_part(
    oss: Oss, endpoint: str, key: str, upload_id: str, number: int, part: Path,
    credentials: dict[str, str],
) -> float:
    started = time.monotonic()
    result = subprocess.run(
        [
            "ossutil", "api", "upload-part", "--bucket", oss.bucket, "--key", key,
            "--upload-id", upload_id, "--part-number", str(number),
            "--body", f"file://{part}", "--region", oss.region,
            "--endpoint", endpoint,
        ],
        capture_output=True, text=True, check=False, timeout=1200, env=credentials,
    )
    if result.returncode:
        details = re.findall(
            r"(?:Http Status Code|Error Code)\s*:\s*[A-Za-z0-9-]+",
            result.stdout + result.stderr,
        )
        raise RuntimeError(f"part {number} failed via {endpoint}: {', '.join(details) or 'ossutil error'}")
    return time.monotonic() - started


def benchmark(oss: Oss, label: str, endpoint: str, part: Path) -> float:
    key = f"releases/_diagnostics/upload-{os.environ['GITHUB_RUN_ID']}-{label}-{uuid.uuid4().hex}"
    oss.endpoint = endpoint
    response = oss.command(
        "api", "initiate-multipart-upload", "--bucket", oss.bucket,
        "--key", key, "--output-format", "json", capture=True,
    )
    upload_id = parse_upload_id(response.stdout)
    try:
        credentials = oss.env.copy()
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=PART_COUNT) as pool:
            futures = [
                pool.submit(upload_part, oss, endpoint, key, upload_id, number, part, credentials)
                for number in range(1, PART_COUNT + 1)
            ]
            durations = [future.result() for future in futures]
        elapsed = time.monotonic() - started
        rate = PART_COUNT * PART_SIZE / 1048576 / elapsed
        print(
            f"{label}: {PART_COUNT * PART_SIZE // 1048576} MiB in {elapsed:.2f}s "
            f"= {rate:.3f} MiB/s; part durations: "
            + ", ".join(f"{duration:.2f}s" for duration in durations),
            flush=True,
        )
        return rate
    finally:
        try:
            oss.command(
                "api", "abort-multipart-upload", "--bucket", oss.bucket,
                "--key", key, "--upload-id", upload_id, capture=True,
            )
            print(f"Aborted multipart upload for {label}", flush=True)
        except Exception:
            print(f"ABORT FAILED: key={key} upload_id={upload_id}", flush=True)
            raise


def main() -> None:
    if not os.environ.get("GITHUB_RUN_ID"):
        raise RuntimeError("This benchmark must run in GitHub Actions")
    oss = Oss()
    with tempfile.TemporaryDirectory(prefix="aeloon-oss-benchmark-") as directory:
        part = Path(directory) / "part.bin"
        part.write_bytes(os.urandom(PART_SIZE))
        results = {label: benchmark(oss, label, endpoint, part) for label, endpoint in ENDPOINTS}
    accelerated = (results["accelerated"] + results["accelerated-repeat"]) / 2
    print(f"Accelerated/direct throughput ratio: {accelerated / results['direct']:.2f}x", flush=True)


if __name__ == "__main__":
    main()

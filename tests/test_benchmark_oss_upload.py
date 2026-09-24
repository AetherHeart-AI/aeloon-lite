"""The upload benchmark must remove multipart parts even when a transfer fails."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import benchmark_oss_upload


class FakeOss:
    bucket = "aeloon-lite"
    region = "cn-beijing"
    env = {}

    def __init__(self):
        self.commands = []

    def command(self, *args, **kwargs):
        self.commands.append(args)
        return type("Result", (), {"stdout": json.dumps({"UploadId": "1234567890AB"})})()


class BenchmarkTests(unittest.TestCase):
    def test_upload_id_is_read_from_nested_json(self):
        self.assertEqual(
            benchmark_oss_upload.parse_upload_id('{"Result":{"UploadId":"1234567890AB"}}'),
            "1234567890AB",
        )

    def test_failed_upload_aborts_parts(self):
        oss = FakeOss()
        with tempfile.TemporaryDirectory() as directory:
            part = Path(directory) / "part.bin"
            part.write_bytes(b"example")
            with patch.dict(os.environ, {"GITHUB_RUN_ID": "123"}), patch.object(
                benchmark_oss_upload, "upload_part", side_effect=RuntimeError("transfer failed")
            ):
                with self.assertRaisesRegex(RuntimeError, "transfer failed"):
                    benchmark_oss_upload.benchmark(
                        oss, "direct", "https://oss-cn-beijing.aliyuncs.com", part,
                    )
        self.assertEqual(oss.commands[0][1], "initiate-multipart-upload")
        self.assertEqual(oss.commands[-1][1], "abort-multipart-upload")


if __name__ == "__main__":
    unittest.main()

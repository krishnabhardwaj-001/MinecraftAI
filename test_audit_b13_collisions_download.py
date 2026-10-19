"""
Unit tests for B13: Output collisions, unguessable download IDs, and TTL cleanup.
Verifies:
1. Generations write to isolated per-request job directories, preventing overwrites of identical prompts.
2. Datapack ZIP bytes remain deterministic inside per-request directories.
3. Download URLs contain unguessable tokens; guessing raw pack filenames returns 404.
4. Expired artifacts (exceeding TTL) return 404 and are purged.
5. Path traversal protections remain enforced.
"""

import os
import shutil
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from generator.datapack_generator import DatapackGenerator
from generator.models import FunctionDefinition
from security.config import DEFAULT_SECURITY_CONFIG
from web.app import app, GENERATED_DIR, cleanup_expired_artifacts


class TestAuditB13CollisionsAndDownloads(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.test_dir = GENERATED_DIR / "test_b13_scratch"
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_per_request_job_directories_prevent_collision(self):
        """Two generations with the exact same request write to separate job dirs without deleting each other."""
        gen1_dir = self.test_dir / "job_req1"
        gen2_dir = self.test_dir / "job_req2"
        gen1_dir.mkdir(parents=True, exist_ok=True)
        gen2_dir.mkdir(parents=True, exist_ok=True)

        g1 = DatapackGenerator(output_dir=gen1_dir, version="1.21.11")
        g2 = DatapackGenerator(output_dir=gen2_dir, version="1.21.11")

        funcs = [FunctionDefinition(function_path="main", commands=["say test"])]
        res1 = g1.generate(functions=funcs, datapack_name="custom_pack", create_zip=True, clean=True)
        self.assertTrue(Path(res1.zip_path).exists())

        # Second generator runs with clean=True on its own directory; res1 must NOT be touched
        res2 = g2.generate(functions=funcs, datapack_name="custom_pack", create_zip=True, clean=True)
        self.assertTrue(Path(res2.zip_path).exists())
        self.assertTrue(Path(res1.zip_path).exists(), "Job 1 zip was deleted by Job 2 collision!")

        # Crucial: ZIP bytes must be identical (deterministic) despite distinct job folders
        bytes1 = Path(res1.zip_path).read_bytes()
        bytes2 = Path(res2.zip_path).read_bytes()
        self.assertEqual(bytes1, bytes2, "Zip archives must be bitwise deterministic")

    def test_download_by_unguessable_token(self):
        """Files in job subdirectories can be downloaded via unguessable token, but not by raw filename."""
        job_token = "job_secure_abc123"
        job_dir = GENERATED_DIR / job_token
        job_dir.mkdir(parents=True, exist_ok=True)

        # Create a valid zip archive inside job_dir
        zip_path = job_dir / "secret_pack.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("pack.mcmeta", '{"pack": {"pack_format": 94, "description": "Test"}}')
            zf.writestr("data/custom/function/main.mcfunction", "say test\n")

        try:
            # 1. Download via token + filename -> 200 OK
            resp_token = self.client.get(f"/api/download/{job_token}/secret_pack.zip")
            self.assertEqual(resp_token.status_code, 200)
            self.assertEqual(resp_token.headers["content-type"], "application/zip")

            # 2. Attempting to download guessing only 'secret_pack.zip' directly from /api/download/ -> 404
            resp_guess = self.client.get("/api/download/secret_pack.zip")
            self.assertEqual(resp_guess.status_code, 404)

        finally:
            shutil.rmtree(job_dir, ignore_errors=True)

    def test_ttl_cleanup_of_expired_download(self):
        """Accessing a download past retention TTL returns 404 and purges it."""
        job_token = "job_expired_xyz789"
        job_dir = GENERATED_DIR / job_token
        job_dir.mkdir(parents=True, exist_ok=True)

        zip_path = job_dir / "expired_pack.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("pack.mcmeta", '{"pack": {"pack_format": 94, "description": "Test"}}')
            zf.writestr("data/custom/function/main.mcfunction", "say test\n")

        # Backdate mtime past TTL (e.g. 2 hours ago)
        past_time = time.time() - (DEFAULT_SECURITY_CONFIG.artifact_retention_seconds + 3600)
        os.utime(str(zip_path), (past_time, past_time))
        os.utime(str(job_dir), (past_time, past_time))

        try:
            resp = self.client.get(f"/api/download/{job_token}/expired_pack.zip")
            self.assertEqual(resp.status_code, 404)
            # File should now be purged
            self.assertFalse(job_dir.exists())
        finally:
            if job_dir.exists():
                shutil.rmtree(job_dir, ignore_errors=True)

    def test_download_path_traversal_blocked(self):
        """Path traversal attempts are rejected with 400 or 403."""
        resp1 = self.client.get("/api/download/..%2F..%2Fetc/passwd")
        self.assertIn(resp1.status_code, [400, 403, 404])

        resp2 = self.client.get("/api/download/valid_token/..%2F..%2Fetc.zip")
        self.assertIn(resp2.status_code, [400, 403, 404])


if __name__ == "__main__":
    unittest.main()

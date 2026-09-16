import shutil
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from web.app import app

client = TestClient(app)


class TestMinecraftAIWeb(unittest.TestCase):
    """
    Step 9 Automated Test Suite for the MinecraftAI Web Interface.
    Verifies web endpoints, HTML rendering, API contracts, and download security.
    """

    @classmethod
    def tearDownClass(cls):
        # Clean up any generated test archives
        gen_dir = Path("generated")
        if gen_dir.exists():
            for item in gen_dir.iterdir():
                if item.name.startswith("make_every_creeper_drop_diamonds"):
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    elif item.is_file():
                        item.unlink(missing_ok=True)

    def test_1_home_page_renders(self):
        """
        Verify that GET / returns HTTP 200 and serves valid HTML with required element IDs.
        """
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        html = response.text

        # Verify key UI components and IDs
        self.assertIn('id="generatorForm"', html)
        self.assertIn('id="requestInput"', html)
        self.assertIn('id="submitBtn"', html)
        self.assertIn('id="pipelineFlow"', html)
        self.assertIn('id="downloadBtn"', html)
        self.assertIn('id="clarificationCard"', html)
        self.assertIn('id="successCard"', html)
        self.assertIn("1.21.11", html)

    def test_2_health_endpoint(self):
        """
        Verify that GET /api/health returns valid operational status.
        """
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("minecraft_version"), "1.21.11")
        self.assertEqual(data.get("data_pack_version"), "94.1")

    def test_3_generate_empty_request_rejected(self):
        """
        Verify that POST /api/generate rejects empty string requests with HTTP 400.
        """
        response = client.post("/api/generate", json={"request": "   "})
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("cannot be empty", data.get("detail", ""))

    def test_4_generate_ambiguous_request_clarification(self):
        """
        Verify that POST /api/generate with an ambiguous prompt returns needs_clarification.
        """
        response = client.post("/api/generate", json={"request": "Make the zombie stronger."})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "needs_clarification")
        self.assertFalse(data.get("is_success"))
        self.assertTrue(bool(data.get("clarification")))

    def test_5_generate_valid_request_and_download(self):
        """
        Verify end-to-end execution through the web API and ZIP download.
        """
        # 1. Generate
        response = client.post(
            "/api/generate",
            json={"request": "Make every creeper drop diamonds."}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "success")
        self.assertTrue(data.get("is_success"))
        self.assertIsNotNone(data.get("download_url"))
        self.assertIsNotNone(data.get("zip_filename"))

        zip_filename = data["zip_filename"]
        download_url = data["download_url"]

        # 2. Download generated ZIP
        dl_response = client.get(download_url)
        self.assertEqual(dl_response.status_code, 200)
        self.assertEqual(dl_response.headers.get("content-type"), "application/zip")
        self.assertGreater(len(dl_response.content), 100)

    def test_6_download_security_path_traversal(self):
        """
        Verify that the download endpoint rejects path traversal attacks.
        """
        # Non-.zip extension
        res1 = client.get("/api/download/pack.mcmeta")
        self.assertEqual(res1.status_code, 400)

        # Path traversal with relative dots (FastAPI routing normalizes or regex blocks)
        res2 = client.get("/api/download/..%2F..%2Fsecret.zip")
        self.assertIn(res2.status_code, [400, 403, 404])

        # Non-existent zip
        res3 = client.get("/api/download/definitely_not_a_real_datapack_xyz_123.zip")
        self.assertEqual(res3.status_code, 404)


if __name__ == "__main__":
    unittest.main()

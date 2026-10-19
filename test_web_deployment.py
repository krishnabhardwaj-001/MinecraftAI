"""
test_web_deployment.py - Production Web Deployment & Zero-Setup Client Tests.

Verifies:
1. True zero-setup experience: client sends prompt without any credentials or client-side models.
2. Server-side AI provider isolation: client never receives provider secrets or credentials.
3. Production path concealment: server filesystem paths are never returned in responses.
4. Production failure hardening: returns safe generic 503 without leaking stack traces or hostnames.
5. Job endpoints: POST /api/jobs and GET /api/jobs/{job_id} / GET /api/generate/{job_id}.
6. Byte-level ZIP delivery: pack.mcmeta at root, data/ directory, no leaked artifacts.
7. Automatic artifact cleanup: removes expired files after retention threshold.
"""

import io
import json
import os
import shutil
import time
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from web.app import (
    app,
    cleanup_expired_artifacts,
    DEFAULT_JOB_MANAGER,
)
from security.config import DEFAULT_SECURITY_CONFIG
from security.rate_limit import DEFAULT_RATE_LIMITER


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limiter_and_artifacts():
    DEFAULT_RATE_LIMITER.reset()
    yield
    DEFAULT_RATE_LIMITER.reset()


class TestProductionZeroSetupExperience:
    """Verifies that an end-user client requires zero local setup, zero models, and zero credentials."""

    def test_client_generates_without_any_credentials(self, client):
        """Client submits standard JSON request without auth headers or local models."""
        response = client.post(
            "/api/generate",
            json={
                "request": "When it starts raining, give every player one diamond.",
                "minecraft_version": "1.21.11"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["is_success"] is True
        assert data["download_url"] is not None

        # Confirm no credentials leaked in API payload
        response_str = json.dumps(data)
        assert "OLLAMA_API_KEY" not in response_str
        assert "Authorization" not in response_str
        assert "Bearer" not in response_str
        assert "sk-" not in response_str

    def test_zip_delivery_structure_root(self, client):
        """Verifies downloaded ZIP has pack.mcmeta and data/ directly at root, not inside subfolders."""
        response = client.post(
            "/api/generate",
            json={
                "request": "Make every creeper drop diamonds.",
                "minecraft_version": "1.21.11"
            }
        )
        assert response.status_code == 200
        data = response.json()
        download_url = data["download_url"]

        dl_resp = client.get(download_url)
        assert dl_resp.status_code == 200
        assert dl_resp.headers["content-type"] == "application/zip"

        with zipfile.ZipFile(io.BytesIO(dl_resp.content)) as zf:
            names = zf.namelist()
            # Root verification
            assert "pack.mcmeta" in names
            assert any(n.startswith("data/") for n in names)
            assert not any(n.startswith("generated/") for n in names)
            assert not any(n.startswith("output/") for n in names)

            # Valid pack.mcmeta content
            mcmeta = json.loads(zf.read("pack.mcmeta").decode("utf-8"))
            assert "pack" in mcmeta
            assert mcmeta["pack"]["pack_format"] == 94


class TestProductionSecurityAndConcealment:
    """Verifies path concealment and error sanitization under production mode."""

    def test_production_mode_conceals_server_paths(self, client):
        """In production mode, datapack_path and zip_path must be None."""
        mock_res = MagicMock(
            status="ready",
            is_success=True,
            minecraft_version="1.21.11",
            original_request="Make every skeleton drop iron ingots.",
            final_datapack_path="D:\\Projects\\MinecraftAI\\generated\\make_every_skeleton_drop_iron_ingots",
            final_zip_path="D:\\Projects\\MinecraftAI\\generated\\make_every_skeleton_drop_iron_ingots.zip",
            datapack_name="make_every_skeleton_drop_iron_ingots",
            errors=[],
            stages={"1": "done", "2": "done", "3": "done", "4": "done", "5": "done", "6": "done", "7": "done", "8": "done"},
            clarification=None,
            clarification_requirements=[],
            execution_summary="Generated",
            generation=MagicMock(files_generated=["pack.mcmeta"]),
            context=MagicMock(commands_retrieved=[], entities_retrieved=[], items_retrieved=[]),
            validation=MagicMock(is_valid=True, total_errors=0, total_warnings=0, errors=[], warnings=[], checks_performed=[]),
            repair=None,
            plan={"summary": "Drop iron ingots"},
            error_code=None,
            failed_stage=None,
            diagnostic=None
        )
        with patch.object(DEFAULT_SECURITY_CONFIG, "is_development_mode", False):
            with patch("web.app.run_minecraft_pipeline", return_value=mock_res), \
                 patch("web.app.validate_zip_archive"):
                response = client.post(
                    "/api/generate",
                    json={
                        "request": "Make every skeleton drop iron ingots.",
                        "minecraft_version": "1.21.11"
                    }
                )
                assert response.status_code == 200
                data = response.json()
                assert data["datapack_path"] is None
                assert data["zip_path"] is None
                assert data["download_url"] is not None

    def test_production_mode_provider_failure_sanitization(self, client):
        """When AI provider fails in production, return safe 503 without stack traces."""
        with patch.object(DEFAULT_SECURITY_CONFIG, "is_development_mode", False):
            with patch("web.app.run_minecraft_pipeline", side_effect=ConnectionRefusedError("Connection refused to 10.0.0.5:11434")):
                response = client.post(
                    "/api/generate",
                    json={"request": "Make me 10 times faster"}
                )
                assert response.status_code == 503
                detail = response.json().get("detail", "")
                assert "Generation is temporarily unavailable. Please try again in a moment." in detail
                # Ensure internal host or stack trace is not disclosed
                assert "10.0.0.5" not in detail
                assert "Traceback" not in detail
                assert "ConnectionRefusedError" not in detail

    def test_health_check_reports_healthy_without_secrets(self, client):
        """Health check returns ready status and provider without leaking credentials."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["health"] == "healthy"
        assert "provider" in data
        # Zero secret exposure
        health_str = json.dumps(data)
        assert "key" not in health_str.lower() or "data_pack_version" in health_str
        assert "password" not in health_str.lower()
        assert "token" not in health_str.lower()


class TestJobModelEndpoints:
    """Verifies asynchronous job creation and polling."""

    def test_create_and_poll_job(self, client):
        """Submit job via POST /api/jobs and poll GET /api/jobs/{id}."""
        from unittest.mock import MagicMock
        mock_res = MagicMock()
        mock_res.status = "success"
        mock_res.is_success = True
        mock_res.final_zip_path = None
        mock_res.context = None
        mock_res.validation = None
        mock_res.repair = None
        mock_res.generation = None
        mock_res.errors = []
        mock_res.clarification = None
        mock_res.clarification_requirements = []
        mock_res.execution_summary = "OK"
        mock_res.minecraft_version = "1.21.11"
        mock_res.original_request = "Make spiders drop iron ingots."
        mock_res.plan = None

        with patch("web.app.run_minecraft_pipeline", return_value=mock_res):
            resp = client.post(
                "/api/jobs",
                json={
                    "request": "Make spiders drop iron ingots.",
                    "minecraft_version": "1.21.11"
                }
            )
            assert resp.status_code == 200
            job_data = resp.json()
            job_id = job_data["job_id"]
            assert job_id.startswith("job_")
            assert job_data["status"] in ("queued", "running")

            # Poll job status
            poll_resp = client.get(f"/api/jobs/{job_id}")
            assert poll_resp.status_code == 200
            status_data = poll_resp.json()
            assert status_data["job_id"] == job_id
            assert "status" in status_data
            assert "progress_stage" in status_data

            # Alias route GET /api/generate/{job_id}
            alias_resp = client.get(f"/api/generate/{job_id}")
            assert alias_resp.status_code == 200
            assert alias_resp.json()["job_id"] == job_id

    def test_nonexistent_job_returns_404(self, client):
        """Polling an unknown job ID returns HTTP 404."""
        resp = client.get("/api/jobs/job_nonexistent_12345")
        assert resp.status_code == 404


class TestArtifactCleanupRetention:
    """Verifies automatic disk storage retention and cleanup."""

    def test_cleanup_expired_artifacts(self, tmp_path):
        """Creates dummy fresh and expired artifacts; verifies expired are purged."""
        test_dir = tmp_path / "test_generated"
        test_dir.mkdir()

        fresh_file = test_dir / "fresh_pack.zip"
        fresh_file.write_text("fresh content", encoding="utf-8")

        expired_file = test_dir / "old_pack.zip"
        expired_file.write_text("old content", encoding="utf-8")

        # Set modification time of expired file to 2 hours ago
        past_time = time.time() - 7200
        os.utime(str(expired_file), (past_time, past_time))

        # Run cleanup with 3600s TTL (1 hour)
        purged = cleanup_expired_artifacts(base_dir=test_dir, max_age_seconds=3600)
        assert purged == 1
        assert fresh_file.exists()
        assert not expired_file.exists()

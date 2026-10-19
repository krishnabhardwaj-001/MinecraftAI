"""
End-to-End Website & Web API Integration Tests.
Verifies all public routes, legal documents, security headers, input rejection,
clarification loop, multi-version support (1.21.11 and 1.21.1),
and byte-level archive structure of downloaded datapacks.
"""

import io
import json
import shutil
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from web.app import app


@pytest.fixture(scope="module")
def web_client():
    """Test client for FastAPI app."""
    return TestClient(app)


class TestWebEndpoints:
    """Tests for public HTTP routes, legal pages, and API diagnostics."""

    def test_home_page_rendering(self, web_client):
        resp = web_client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        html = resp.text

        # Verify branding, disclaimer, selector, and legal links
        assert "MinecraftAI" in html
        assert "not affiliated with, endorsed by, or sponsored by Mojang" in html
        assert 'id="minecraftVersionSelect"' in html
        assert 'href="/privacy"' in html
        assert 'href="/terms"' in html
        assert 'href="/security"' in html

    def test_legal_pages_rendered(self, web_client):
        for route, title in [
            ("/privacy", "Privacy Policy"),
            ("/terms", "Terms of Service"),
            ("/security", "Security Policy")
        ]:
            resp = web_client.get(route)
            assert resp.status_code == 200
            assert "text/html" in resp.headers.get("content-type", "")
            assert title in resp.text
            assert "Mojang" in resp.text or "Security" in resp.text

    def test_legal_api_endpoint(self, web_client):
        resp = web_client.get("/api/legal/privacy_policy")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("document") == "privacy_policy"
        assert "Privacy Policy" in data.get("content", "")

        # Test non-existent legal doc
        resp_404 = web_client.get("/api/legal/nonexistent_document")
        assert resp_404.status_code == 404

    def test_health_endpoint_diagnostics(self, web_client):
        resp = web_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ok"
        assert data.get("health") == "healthy"
        assert "1.21.11" in data.get("supported_versions", [])
        assert "1.21.1" in data.get("supported_versions", [])
        assert data.get("generator") == "ready"
        assert data.get("validator") == "ready"
        assert data.get("security") == "enforced"

    def test_versions_endpoint(self, web_client):
        resp = web_client.get("/api/versions")
        assert resp.status_code == 200
        data = resp.json()
        versions = data.get("supported_versions", [])
        assert "1.21.11" in versions
        assert "1.21.1" in versions
        assert data.get("default_version") == "1.21.11"

    def test_security_headers_enforced(self, web_client):
        resp = web_client.get("/")
        assert "Content-Security-Policy" in resp.headers
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


class TestWebInputValidation:
    """Tests for edge cases and security rejection at the web boundary."""

    def test_empty_request_rejected(self, web_client):
        resp = web_client.post("/api/generate", json={"request": "   "})
        assert resp.status_code == 400
        assert "cannot be empty" in resp.json().get("detail", "")

    def test_oversized_request_rejected(self, web_client):
        resp = web_client.post("/api/generate", json={"request": "a" * 2500})
        assert resp.status_code == 400
        detail = resp.json().get("detail", "").lower()
        assert "maximum" in detail and "length" in detail

    def test_null_byte_request_rejected(self, web_client):
        resp = web_client.post("/api/generate", json={"request": "give diamond\x00kill"})
        assert resp.status_code == 400
        assert "Null bytes" in resp.json().get("detail", "")

    def test_unsupported_version_rejected(self, web_client):
        resp = web_client.post("/api/generate", json={
            "request": "Give me a sword",
            "minecraft_version": "1.12.2"
        })
        assert resp.status_code == 400
        assert "Unsupported Minecraft version" in resp.json().get("detail", "")

    def test_download_traversal_rejected(self, web_client):
        resp = web_client.get("/api/download/..%2F..%2Fsecret.zip")
        assert resp.status_code in (400, 403, 404)

    def test_download_non_zip_rejected(self, web_client):
        resp = web_client.get("/api/download/pack.mcmeta")
        assert resp.status_code == 400


@pytest.mark.live
class TestWebEndToEndPipeline:
    """
    Mandatory real end-to-end tests through the web interface and generator.
    Covers simple functions, rain triggers, interaction menus,
    dual versions (1.21.11 and 1.21.1), and clarification loops.
    """

    @pytest.fixture(autouse=True)
    def cleanup_and_reset(self):
        from security.rate_limit import DEFAULT_RATE_LIMITER
        DEFAULT_RATE_LIMITER.reset()
        yield
        DEFAULT_RATE_LIMITER.reset()
        gen_dir = Path("generated")
        if gen_dir.exists():
            for p in gen_dir.iterdir():
                if any(k in p.name for k in ("say_hello", "whenever_it_rains", "make_a_clickable", "give_all_players", "speed")):
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                    elif p.is_file():
                        p.unlink(missing_ok=True)

    def test_e2e_1_simple_function_1_21_11(self, web_client):
        """Test simple function generation on Minecraft 1.21.11."""
        resp = web_client.post("/api/generate", json={
            "request": "Give all players regeneration effect for 30 seconds.",
            "minecraft_version": "1.21.11"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["is_success"] is True
        assert data["minecraft_version"] == "1.21.11"
        assert data["download_url"] is not None

        # Download and verify archive
        dl_resp = web_client.get(data["download_url"])
        assert dl_resp.status_code == 200
        assert dl_resp.headers["content-type"] == "application/zip"

        with zipfile.ZipFile(io.BytesIO(dl_resp.content)) as zf:
            names = zf.namelist()
            assert "pack.mcmeta" in names
            assert any(n.startswith("data/") for n in names)
            mcmeta = json.loads(zf.read("pack.mcmeta").decode("utf-8"))
            assert mcmeta["pack"]["pack_format"] == 94

    def test_e2e_2_rain_diamond_1_21_11(self, web_client):
        """Test rain-triggered diamond reward on Minecraft 1.21.11."""
        resp = web_client.post("/api/generate", json={
            "request": "When it starts raining, give every player one diamond.",
            "minecraft_version": "1.21.11"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["is_success"] is True

        dl_resp = web_client.get(data["download_url"])
        assert dl_resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(dl_resp.content)) as zf:
            assert "pack.mcmeta" in zf.namelist()
            assert any("tick" in n or "rain" in n for n in zf.namelist())

    def test_e2e_3_recipe_mechanism_1_21_11(self, web_client):
        """Test recipe mechanism generation on Minecraft 1.21.11."""
        resp = web_client.post("/api/generate", json={
            "request": "Make rotten flesh smelt into leather.",
            "minecraft_version": "1.21.11"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["is_success"] is True

        dl_resp = web_client.get(data["download_url"])
        assert dl_resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(dl_resp.content)) as zf:
            names = zf.namelist()
            assert "pack.mcmeta" in names
            # Recipe file should exist under recipe/ directory
            assert any("recipe" in n for n in names)

    def test_e2e_4_version_1_21_1_support(self, web_client):
        """Test version 1.21.1 targeting (pack_format 48)."""
        resp = web_client.post("/api/generate", json={
            "request": "Make every creeper drop 1 diamond.",
            "minecraft_version": "1.21.1"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["minecraft_version"] == "1.21.1"

        dl_resp = web_client.get(data["download_url"])
        assert dl_resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(dl_resp.content)) as zf:
            mcmeta = json.loads(zf.read("pack.mcmeta").decode("utf-8"))
            # 1.21.1 uses pack_format 48
            assert mcmeta["pack"]["pack_format"] == 48

    def test_e2e_5_clarification_loop(self, web_client):
        """Test clarification request and subsequent resolution."""
        # 1. Submit ambiguous request
        ambig_resp = web_client.post("/api/generate", json={
            "request": "Make me faster."
        })
        assert ambig_resp.status_code == 200
        ambig_data = ambig_resp.json()
        assert ambig_data["status"] == "needs_clarification"
        assert ambig_data["is_success"] is False
        assert len(ambig_data.get("clarification", "")) > 0

        # 2. Submit resolution with clarification answer
        resolved_resp = web_client.post("/api/generate", json={
            "request": "Make me faster.",
            "clarification_answer": "10 times faster",
            "previous_request": "Make me faster.",
            "minecraft_version": "1.21.11"
        })
        assert resolved_resp.status_code == 200
        resolved_data = resolved_resp.json()
        assert resolved_data["status"] == "success"
        assert resolved_data["is_success"] is True
        assert resolved_data["download_url"] is not None

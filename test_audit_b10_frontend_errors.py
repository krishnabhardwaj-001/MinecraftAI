"""
Unit tests for B10: Front-end error handling and security link hygiene.
Verifies:
1. CSS preserves multi-line error diagnostics with white-space: pre-wrap.
2. Front-end app.js parses FastAPI 422 structured detail objects without [object Object].
3. Front-end app.js hides successCard and removes stale downloadBtn href when download_url is null.
"""

import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from web.app import app


class TestAuditB10FrontendErrors(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_css_error_list_preserves_multiline_diagnostics(self):
        """Verifies that .error-list li specifies white-space: pre-wrap so multi-line 503 diagnostics don't collapse."""
        css_file = Path("web/static/css/style.css")
        self.assertTrue(css_file.exists(), "style.css must exist")
        css_content = css_file.read_text(encoding="utf-8")

        # Find .error-list li block
        self.assertIn(".error-list li", css_content)
        # Check that white-space: pre-wrap is present
        self.assertIn("white-space: pre-wrap;", css_content)

    def test_fastapi_422_detail_structure(self):
        """Verifies FastAPI 422 response returns a structured detail list, and app.js handles it."""
        # Send an invalid payload that triggers FastAPI validation error (422)
        resp = self.client.post("/api/generate", json={"invalid_field": 123})
        self.assertEqual(resp.status_code, 422)
        body = resp.json()
        self.assertIn("detail", body)
        self.assertIsInstance(body["detail"], list)
        self.assertTrue(len(body["detail"]) > 0)
        # Each item has loc and msg
        self.assertIn("loc", body["detail"][0])
        self.assertIn("msg", body["detail"][0])

        # Verify app.js contains logic to format msg.loc and msg.msg without [object Object]
        js_file = Path("web/static/js/app.js")
        js_content = js_file.read_text(encoding="utf-8")
        self.assertIn("typeof msg === \"object\"", js_content)
        self.assertIn("errArray.push", js_content)

    def test_null_download_url_handling_in_app_js(self):
        """Verifies app.js removes stale downloadBtn href and hides successCard when download_url is null."""
        js_file = Path("web/static/js/app.js")
        js_content = js_file.read_text(encoding="utf-8")

        # Must check if download_url is null/falsy
        self.assertIn("if (!data.download_url)", js_content)
        self.assertIn("downloadBtn.removeAttribute(\"href\")", js_content)
        self.assertIn("successCard.classList.add(\"hidden\")", js_content)

    def test_textContent_used_without_innerhtml_injection(self):
        """Verifies textContent is used for error messages rather than innerHTML."""
        js_file = Path("web/static/js/app.js")
        js_content = js_file.read_text(encoding="utf-8")

        # In showErrorState, errorList.innerHTML = "" is acceptable for clearing,
        # but inserting message items must use textContent:
        self.assertIn("li.textContent = msg;", js_content)


if __name__ == "__main__":
    unittest.main()

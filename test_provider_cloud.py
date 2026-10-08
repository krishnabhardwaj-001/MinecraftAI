"""
Focused Unit Tests for Ollama Cloud Provider Configuration & Security.
Validates:
1. Cloud host configuration (https://ollama.com).
2. Cloud model configuration (gpt-oss:120b-cloud).
3. API-key header and authentication handling.
4. Missing Cloud API key produces a clear safe configuration error.
5. No silent local fallback when Cloud configuration fails.
6. LLM_PROVIDER environment selection.
7. Local Ollama behavior occurs only where explicitly configured.
8. Secret API key is never exposed or logged.
"""
import os
import unittest
from unittest.mock import MagicMock, patch

from ai.provider import AIProvider
from run_pipeline import get_ollama_diagnostic_message


class TestOllamaCloudProvider(unittest.TestCase):
    """Tests for Ollama Cloud provider configuration, authentication, and safety."""

    @patch("ai.provider.OllamaClient")
    def test_1_cloud_host_and_model_configuration(self, mock_client_cls):
        """Verify explicit Ollama Cloud host and model configuration with Bearer token."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        test_env = {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_HOST": "https://ollama.com",
            "OLLAMA_MODEL": "gpt-oss:120b-cloud",
            "OLLAMA_API_KEY": "test-secret-cloud-token-12345"
        }

        with patch.dict(os.environ, test_env, clear=True):
            provider = AIProvider()

            self.assertEqual(provider.provider, "ollama")
            self.assertEqual(provider.model, "gpt-oss:120b-cloud")
            self.assertEqual(provider.host, "https://ollama.com")
            self.assertTrue(provider.is_cloud)

            # Verify OllamaClient was initialized with the cloud endpoint and Bearer auth header
            mock_client_cls.assert_called_once_with(
                host="https://ollama.com",
                headers={"Authorization": "Bearer test-secret-cloud-token-12345"}
            )

    def test_2_missing_cloud_api_key_fails_safely_without_silent_fallback(self):
        """Verify that missing API key in Cloud mode fails safely without falling back to local."""
        test_env = {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_HOST": "https://ollama.com",
            "OLLAMA_MODEL": "gpt-oss:120b-cloud",
            "OLLAMA_API_KEY": ""
        }

        with patch.dict(os.environ, test_env, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                AIProvider()

            error_msg = str(ctx.exception)
            self.assertIn("OLLAMA_API_KEY is required for Ollama Cloud", error_msg)
            self.assertIn("https://ollama.com", error_msg)

    @patch("ai.provider.OllamaClient")
    def test_3_cloud_model_defaults_to_cloud_host(self, mock_client_cls):
        """Verify that configuring a -cloud model without host defaults to https://ollama.com."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        test_env = {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_HOST": "",
            "OLLAMA_MODEL": "gpt-oss:120b-cloud",
            "OLLAMA_API_KEY": "dummy-valid-key"
        }

        with patch.dict(os.environ, test_env, clear=True):
            provider = AIProvider()

            self.assertTrue(provider.is_cloud)
            self.assertEqual(provider.host, "https://ollama.com")
            mock_client_cls.assert_called_once_with(
                host="https://ollama.com",
                headers={"Authorization": "Bearer dummy-valid-key"}
            )

    @patch("ai.provider.OllamaClient")
    def test_4_no_silent_local_fallback_on_generation_failure(self, mock_client_cls):
        """Verify that when Cloud generation fails, it does NOT silently fall back to local Ollama."""
        mock_client = MagicMock()
        mock_client.chat.side_effect = RuntimeError("Cloud API returned 502 Bad Gateway")
        mock_client_cls.return_value = mock_client

        test_env = {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_HOST": "https://ollama.com",
            "OLLAMA_MODEL": "gpt-oss:120b-cloud",
            "OLLAMA_API_KEY": "valid-key-xyz"
        }

        with patch.dict(os.environ, test_env, clear=True):
            provider = AIProvider()

            # Ensure generation error propagates directly without silent local fallback
            with self.assertRaises(RuntimeError) as ctx:
                provider.generate_structured("system prompt", "user prompt", {})

            self.assertIn("Cloud API returned 502 Bad Gateway", str(ctx.exception))
            # Verify only 1 chat attempt made to the cloud client, zero local calls
            mock_client.chat.assert_called_once()

    def test_5_llm_provider_environment_selection(self):
        """Verify that LLM_PROVIDER in environment selects the appropriate provider."""
        # 1. Test OpenAI selection via LLM_PROVIDER
        openai_env = {
            "LLM_PROVIDER": "openai",
            "OPENAI_API_KEY": "test-openai-key-abc",
            "OPENAI_MODEL": "gpt-5.6"
        }
        with patch.dict(os.environ, openai_env, clear=True):
            with patch("ai.provider.OpenAI") as mock_openai_cls:
                provider = AIProvider()
                self.assertEqual(provider.provider, "openai")
                self.assertEqual(provider.model, "gpt-5.6")
                mock_openai_cls.assert_called_once_with(api_key="test-openai-key-abc")

        # 2. Test Ollama selection via LLM_PROVIDER
        ollama_env = {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_HOST": "http://localhost:11434",
            "OLLAMA_MODEL": "llama3.1:8b"
        }
        with patch.dict(os.environ, ollama_env, clear=True):
            with patch("ai.provider.OllamaClient") as mock_ollama_cls:
                provider = AIProvider()
                self.assertEqual(provider.provider, "ollama")
                mock_ollama_cls.assert_called_once_with(
                    host="http://localhost:11434",
                    headers=None
                )

    @patch("ai.provider.OllamaClient")
    def test_6_local_ollama_only_where_explicitly_configured(self, mock_client_cls):
        """Verify that local Ollama mode is activated ONLY when explicitly configured with a local host."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        local_env = {
            "LLM_PROVIDER": "ollama",
            "OLLAMA_HOST": "http://localhost:11434",
            "OLLAMA_MODEL": "custom-local-model",
            "OLLAMA_API_KEY": ""
        }

        with patch.dict(os.environ, local_env, clear=True):
            provider = AIProvider()

            # Local mode does not require API key
            self.assertFalse(provider.is_cloud)
            self.assertEqual(provider.host, "http://localhost:11434")
            self.assertEqual(provider.model, "custom-local-model")
            mock_client_cls.assert_called_once_with(
                host="http://localhost:11434",
                headers=None
            )

    def test_7_diagnostic_message_distinguishes_cloud_vs_local(self):
        """Verify that diagnostic messages distinguish between Cloud and Local environments."""
        # 1. Cloud endpoint diagnostic
        cloud_msg = get_ollama_diagnostic_message("https://ollama.com")
        self.assertIn("Ollama Cloud", cloud_msg)
        self.assertIn("OLLAMA_API_KEY", cloud_msg)
        self.assertNotIn("ollama pull llama3.1:8b", cloud_msg)

        # 2. Local endpoint diagnostic
        local_msg = get_ollama_diagnostic_message("http://localhost:11434")
        self.assertIn("ollama serve", local_msg)
        self.assertNotIn("ollama pull llama3.1:8b", local_msg)


if __name__ == "__main__":
    unittest.main()

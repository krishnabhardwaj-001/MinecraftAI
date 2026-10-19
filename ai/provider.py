import os
import json
from typing import Any, Dict, Optional, Tuple

# Load .env before any SDK client is imported or initialized
from dotenv import load_dotenv
load_dotenv()

from ollama import Client as OllamaClient
from openai import OpenAI
from pydantic import BaseModel


def is_ollama_unreachable_error(exc: Optional[BaseException]) -> bool:
    """
    Determines whether an exception indicates that the Ollama service
    is offline, unreachable, not running, failed to connect, or returned
    an Ollama provider error (such as sign-in required or missing model).
    """
    if exc is None:
        return False

    exc_name = type(exc).__name__
    if exc_name in (
        "ConnectError",
        "ConnectTimeout",
        "ConnectionRefusedError",
        "RequestError",
        "ReadTimeout",
        "ResponseError",
    ):
        return True

    try:
        import httpx
        if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
            return True
    except ImportError:
        pass

    try:
        import ollama
        if hasattr(ollama, "RequestError") and isinstance(exc, ollama.RequestError):
            return True
        if hasattr(ollama, "ResponseError") and isinstance(exc, ollama.ResponseError):
            return True
    except ImportError:
        pass

    if isinstance(exc, (ConnectionRefusedError, ConnectionError)):
        return True

    msg = str(exc).lower()
    connection_indicators = [
        "connection refused",
        "connecterror",
        "failed to connect",
        "11434",
        "winerror 10061",
        "all connection attempts failed",
        "target machine actively refused",
        "is ollama running",
        "no such host",
    ]
    if any(ind in msg for ind in connection_indicators):
        return True

    ollama_indicators = [
        "ollama signin",
        "sign in to ollama",
        "ollama unauthorized",
        "ollama error",
        "ollama cloud",
        "ollama_api_key is required",
    ]
    if any(ind in msg for ind in ollama_indicators):
        return True

    if "ollama" in msg and any(k in msg for k in ("unauthorized", "model not found", "quota", "allowance", "signin", "sign in")):
        return True

    if getattr(exc, "__cause__", None) and is_ollama_unreachable_error(exc.__cause__):
        return True
    if getattr(exc, "__context__", None) and is_ollama_unreachable_error(exc.__context__):
        return True

    return False


def get_ollama_diagnostic_message(
    endpoint: Optional[str] = None,
    exc: Optional[BaseException] = None
) -> str:
    """
    Returns an actionable diagnostic message explaining that Ollama is unreachable,
    displaying the endpoint, explaining how to start Ollama or sign in to Ollama Cloud,
    and noting external provider alternatives.
    """
    raw_endpoint = endpoint or os.getenv("OLLAMA_HOST")
    resolved_endpoint = raw_endpoint or "http://localhost:11434"
    is_cloud = (
        raw_endpoint is not None
        and (raw_endpoint.startswith("https://") or "ollama.com" in raw_endpoint.lower())
    )

    err_str = str(exc).lower() if exc else ""
    status_code = getattr(exc, "status_code", None)

    # 1. Authentication / Sign-in required
    if status_code in (401, 403) or any(k in err_str for k in ("unauthorized", "sign in", "signin", "authenticate", "ollama_api_key is required")):
        if is_cloud:
            return (
                f"The AI provider (Ollama Cloud) authentication failed at {resolved_endpoint}.\n\n"
                "To resolve this issue:\n"
                "  1. Ensure your OLLAMA_API_KEY environment variable is configured with a valid key.\n"
                "  2. Verify your network connection to Ollama Cloud (https://ollama.com).\n"
                "  3. Alternatively, configure local Ollama for development by setting OLLAMA_HOST=http://localhost:11434."
            )
        return (
            f"Ollama Cloud authentication required at {resolved_endpoint}.\n\n"
            "To resolve this issue:\n"
            "  1. Sign in with your Ollama account in your terminal:\n"
            "       ollama signin\n"
            "  2. Follow the prompt to complete sign-in in your browser.\n"
            "  3. Once signed in, restart the server or retry your request.\n\n"
            "Note: You do not need to paste an API key into MinecraftAI."
        )

    # 2. Cloud model not found / not pulled
    if status_code == 404 or "not found" in err_str:
        target_model = os.getenv("OLLAMA_MODEL", "gpt-oss:120b-cloud")
        return (
            f"Cloud model '{target_model}' not found in your Ollama library at {resolved_endpoint}.\n\n"
            "To resolve this issue:\n"
            f"  1. Register the cloud model pointer by running:\n"
            f"       ollama pull {target_model}\n"
            "     (This only downloads a lightweight ~384-byte cloud manifest; no model weights are stored locally.)\n"
            "  2. Ensure you are signed in:\n"
            "       ollama signin\n"
            "  3. Retry your request."
        )

    # 3. Cloud quota / usage limit exceeded
    if status_code == 429 or any(k in err_str for k in ("rate limit", "quota", "allowance", "exceeded")):
        return (
            f"Ollama Cloud usage limit or rate limit exceeded at {resolved_endpoint}.\n\n"
            "To resolve this issue:\n"
            "  1. Check your account status and usage allowance at https://ollama.com.\n"
            "  2. Please wait before submitting additional generation requests."
        )

    if is_cloud:
        return (
            f"The AI provider (Ollama Cloud) is unreachable or authentication failed at {resolved_endpoint}.\n\n"
            "To resolve this issue:\n"
            "  1. Verify your network connection to Ollama Cloud (https://ollama.com).\n"
            "  2. Ensure your OLLAMA_API_KEY environment variable is configured with a valid key.\n"
            "  3. Check that your configured model (OLLAMA_MODEL) is available in your Ollama Cloud account.\n"
            "  4. Alternatively, configure local Ollama for development by setting OLLAMA_HOST=http://localhost:11434."
        )

    return (
        f"The AI provider (Ollama) is unreachable or not running at {resolved_endpoint}.\n\n"
        "To resolve this issue:\n"
        "  1. Ensure Ollama is installed (https://ollama.com).\n"
        "  2. Start the Ollama service by running:\n"
        "       ollama serve\n"
        "     or launch the Ollama desktop application.\n"
        "  3. Ensure you are signed in to Ollama Cloud ('ollama signin') and the model is registered ('ollama pull gpt-oss:120b-cloud').\n"
        "  4. Alternatively, configure an external AI provider if supported "
        "(such as setting the OPENAI_API_KEY environment variable for OpenAI, "
        "or setting OLLAMA_HOST=https://ollama.com and OLLAMA_API_KEY for Ollama Cloud)."
    )


def classify_provider_error(exc: Optional[BaseException]) -> Tuple[Optional[str], Optional[str]]:
    """
    Classifies an exception into a standard error code ('provider_unreachable', 'provider_auth', etc.)
    and returns a user-actionable diagnostic message.
    """
    if exc is None:
        return None, None

    msg = str(exc).lower()

    # Check for authentication / authorization issues first
    auth_indicators = [
        "ollama_api_key is required",
        "unauthorized",
        "401",
        "bad api key",
        "invalid api key",
        "authentication",
        "api key is required",
        "bearer",
    ]
    if any(ind in msg for ind in auth_indicators) or type(exc).__name__ in ("AuthenticationError",):
        diag = get_ollama_diagnostic_message(exc=exc)
        return "provider_auth", diag

    # Check for unreachable / connection issues
    if is_ollama_unreachable_error(exc):
        diag = get_ollama_diagnostic_message(exc=exc)
        return "provider_unreachable", diag

    # Check for OpenAI connection errors
    if type(exc).__name__ in ("APIConnectionError", "ConnectError"):
        return "provider_unreachable", "AI provider service is unreachable. Please verify your connection."

    return None, None


class AIProvider:
    """
    Common interface for cloud and local AI models.
    Supports Ollama Cloud (default production target), Local Ollama (development),
    and OpenAI.
    """

    DEFAULT_CLOUD_HOST = "https://ollama.com"
    DEFAULT_CLOUD_MODEL = "gpt-oss:120b-cloud"
    DEFAULT_LOCAL_HOST = "http://127.0.0.1:11434"

    def __init__(self, provider: Optional[str] = None):
        # Respect LLM_PROVIDER from environment if not explicitly passed
        env_provider = os.getenv("LLM_PROVIDER")
        chosen_provider = provider or env_provider or "ollama"
        self.provider = chosen_provider.lower()

        if self.provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")

            if not api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY is not set."
                )

            self.client = OpenAI(api_key=api_key)

            self.model = os.getenv(
                "OPENAI_MODEL",
                "gpt-4o"
            )

        elif self.provider == "ollama":
            self.host = os.getenv("OLLAMA_HOST")
            self.model = os.getenv(
                "OLLAMA_MODEL",
                self.DEFAULT_CLOUD_MODEL
            )
            self.api_key = os.getenv("OLLAMA_API_KEY")

            # Determine whether Cloud model or direct remote cloud endpoint is targeted
            self.is_cloud_model = self._is_cloud_model(self.model)
            is_direct_remote = self._is_direct_cloud_endpoint(self.host)

            if is_direct_remote:
                # Direct connection to remote https:// endpoint (bypassing local Ollama daemon)
                target_host = self.host
                if not self.api_key:
                    raise RuntimeError(
                        f"OLLAMA_API_KEY is required for Ollama Cloud (endpoint: {target_host}). "
                        "Please set OLLAMA_API_KEY in your environment or .env file."
                    )
                headers = {"Authorization": f"Bearer {self.api_key}"}
                self.client = OllamaClient(host=target_host, headers=headers)
                self.host = target_host
                self.is_cloud = True
            elif self.api_key and not self.host:
                # API key provided without host -> default to direct cloud host https://ollama.com
                target_host = self.DEFAULT_CLOUD_HOST
                headers = {"Authorization": f"Bearer {self.api_key}"}
                self.client = OllamaClient(host=target_host, headers=headers)
                self.host = target_host
                self.is_cloud = True
            else:
                # Local Ollama daemon mode (supports both cloud models via 'ollama signin' and local models)
                # No API key required! Local Ollama daemon handles authentication with Ollama Cloud.
                target_host = self.host if self.host else self.DEFAULT_LOCAL_HOST
                headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None
                self.client = OllamaClient(host=target_host, headers=headers)
                self.host = target_host
                self.is_cloud = self.is_cloud_model or self._is_cloud_target(self.host, self.model)

        else:
            raise ValueError(
                "Provider must be 'openai' or 'ollama'."
            )

    @classmethod
    def _is_cloud_model(cls, model: Optional[str]) -> bool:
        """Determines whether the specified model is an Ollama Cloud hosted model."""
        if not model:
            return False
        m = model.strip().lower()
        return m.endswith("-cloud") or m == cls.DEFAULT_CLOUD_MODEL

    @classmethod
    def _is_direct_cloud_endpoint(cls, host: Optional[str]) -> bool:
        """Determines whether the host is an explicit remote HTTPS Ollama Cloud endpoint."""
        if not host:
            return False
        h = host.strip().lower()
        return h.startswith("https://") or "ollama.com" in h

    @classmethod
    def _is_cloud_target(cls, host: Optional[str], model: Optional[str]) -> bool:
        """
        Determines whether Ollama Cloud is targeted (either direct or via local sign-in proxy).
        """
        if cls._is_direct_cloud_endpoint(host):
            return True

        if cls._is_cloud_model(model):
            return True

        return False

    def generate_structured(
        self,
        system_prompt,
        user_prompt,
        schema
    ):
        """
        Ask the selected AI provider to return structured JSON.
        """

        if self.provider == "ollama":
            return self._generate_ollama(
                system_prompt,
                user_prompt,
                schema
            )

        return self._generate_openai(
            system_prompt,
            user_prompt,
            schema
        )

    def _generate_ollama(
        self,
        system_prompt,
        user_prompt,
        schema
    ):
        response = self.client.chat(
            model=self.model,

            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],

            format=schema,

            options={
                "temperature": 0,
                "num_predict": 4096,
                "num_ctx": 8192
            }
        )

        content = response.message.content
        if not content or not content.strip():
            raise ValueError(f"AI provider '{self.provider}' returned empty response.")

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            import re
            match = re.search(r"(\{.*\})", content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except Exception:
                    pass
            raise ValueError(f"AI provider '{self.provider}' returned invalid JSON: {content[:200]}") from e

    def _generate_openai(
        self,
        system_prompt,
        user_prompt,
        schema
    ):
        if hasattr(self.client, "responses"):
            response = self.client.responses.create(
                model=self.model,
                instructions=system_prompt,
                input=user_prompt,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "minecraft_request",
                        "strict": False,
                        "schema": schema
                    }
                }
            )
            raw_text = getattr(response, "output_text", None)
            if raw_text is None and hasattr(response, "output"):
                raw_text = str(response.output)
            return json.loads(raw_text)
        else:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "minecraft_request",
                        "strict": False,
                        "schema": schema
                    }
                }
            )
            return json.loads(response.choices[0].message.content)

    def close(self):
        """Cleanly close underlying HTTP client connections."""
        if hasattr(self, "client") and hasattr(self.client, "close"):
            try:
                self.client.close()
            except Exception:
                pass

    def __del__(self):
        self.close()

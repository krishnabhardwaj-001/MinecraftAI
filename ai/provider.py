import os
import json
from typing import Any, Dict, Optional

# Load .env before any SDK client is imported or initialized
from dotenv import load_dotenv
load_dotenv()

from ollama import Client as OllamaClient
from openai import OpenAI
from pydantic import BaseModel


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
                "gpt-5.6"
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
        response = self.client.responses.create(
            model=self.model,

            instructions=system_prompt,

            input=user_prompt,

            text={
                "format": {
                    "type": "json_schema",
                    "name": "minecraft_request",
                    "strict": True,
                    "schema": schema
                }
            }
        )

        return json.loads(response.output_text)

    def close(self):
        """Cleanly close underlying HTTP client connections."""
        if hasattr(self, "client") and hasattr(self.client, "close"):
            try:
                self.client.close()
            except Exception:
                pass

    def __del__(self):
        self.close()

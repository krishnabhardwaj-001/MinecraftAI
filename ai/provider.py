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

            # Determine whether Cloud configuration is targeted
            self.is_cloud = self._is_cloud_target(self.host, self.model)

            if self.is_cloud:
                target_host = self.host or self.DEFAULT_CLOUD_HOST
                if not self.api_key:
                    raise RuntimeError(
                        f"OLLAMA_API_KEY is required for Ollama Cloud (endpoint: {target_host}). "
                        "Please set OLLAMA_API_KEY in your environment or .env file."
                    )
                # Send the API key using Ollama client's supported authentication header
                headers = {"Authorization": f"Bearer {self.api_key}"}
                self.client = OllamaClient(host=target_host, headers=headers)
                self.host = target_host
            else:
                # Explicit local Ollama development configuration
                target_host = self.host
                headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None
                self.client = OllamaClient(host=target_host, headers=headers)

        else:
            raise ValueError(
                "Provider must be 'openai' or 'ollama'."
            )

    @classmethod
    def _is_cloud_target(cls, host: Optional[str], model: Optional[str]) -> bool:
        """
        Determines whether Ollama Cloud is targeted.
        Cloud is targeted if:
        1. An explicit cloud host is configured (e.g. 'https://ollama.com' or https:// URL), OR
        2. A cloud model is configured (ending in '-cloud') without an explicit local host, OR
        3. No host is configured (in which case production defaults to Ollama Cloud).
        """
        if host:
            h = host.strip().lower()
            if h.startswith("https://") or "ollama.com" in h:
                return True
            # Explicit local host specified (e.g. http://localhost:11434, http://127.0.0.1:11434)
            return False

        if model and model.strip().lower().endswith("-cloud"):
            return True

        # Default production target is Cloud
        return True

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

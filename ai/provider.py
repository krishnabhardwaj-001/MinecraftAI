import os
import json

from dotenv import load_dotenv
from pydantic import BaseModel
from ollama import chat as ollama_chat
from openai import OpenAI

load_dotenv()


class AIProvider:
    """
    Common interface for cloud and local AI models.
    """

    def __init__(self, provider="ollama"):
        self.provider = provider.lower()

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
            self.model = os.getenv(
                "OLLAMA_MODEL",
                "llama3.1:8b"
            )

        else:
            raise ValueError(
                "Provider must be 'openai' or 'ollama'."
            )

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
        response = ollama_chat(
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
                "num_predict": 2048,
                "num_ctx": 4096
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
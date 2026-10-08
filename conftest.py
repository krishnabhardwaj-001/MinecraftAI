"""
Pytest configuration and test environment initialization.
Ensures automated test suites run without making unauthenticated or real Cloud API requests.
"""
import os

# If running automated tests and no Cloud API key is set, configure the local test daemon
# so that integration tests execute against the local test environment.
if not os.getenv("OLLAMA_API_KEY"):
    os.environ.setdefault("OLLAMA_HOST", "http://localhost:11434")

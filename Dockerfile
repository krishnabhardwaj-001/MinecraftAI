# ==============================================================================
# MinecraftAI Production Container
# Multi-stage/lean Python 3.11 image with non-root security context
# ==============================================================================

FROM python:3.11-slim AS base

# Install curl for container health check
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Create dedicated non-root application user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

WORKDIR /app

# Install Python build dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy package definitions first for optimal layer caching
COPY pyproject.toml ./

# Install project and production dependencies
RUN pip install --no-cache-dir \
    pydantic>=2.0.0 \
    python-dotenv>=1.0.0 \
    ollama>=0.2.0 \
    openai>=1.0.0 \
    fastapi>=0.100.0 \
    uvicorn>=0.20.0 \
    jinja2>=3.1.0 \
    httpx>=0.24.0

# Copy application source code
COPY . /app

# Ensure non-root ownership of workspace and output directories
RUN mkdir -p /app/generated /app/scratch && \
    chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose FastAPI application port
EXPOSE 8000

# Set environment defaults
ENV PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    ENVIRONMENT=production \
    OLLAMA_HOST=https://ollama.com \
    OLLAMA_MODEL=gpt-oss:120b-cloud

# Container Healthcheck verifying /api/health
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Launch production web server
CMD ["python", "run_web.py"]

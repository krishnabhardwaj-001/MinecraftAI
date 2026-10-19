# ==============================================================================
# MinecraftAI Production Container
# Multi-stage Python 3.11 image with non-root security context
# ==============================================================================

# Stage 1: Build stage for installing wheels and dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install production dependencies via pyproject.toml
COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install .

# Stage 2: Final runtime container
FROM python:3.11-slim AS runner

ARG INSTALL_JRE=false

# Install curl for container health check and optional JRE 21 for headless server tests
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    if [ "$INSTALL_JRE" = "true" ]; then \
        apt-get install -y --no-install-recommends openjdk-21-jre-headless; \
    fi && \
    rm -rf /var/lib/apt/lists/*

# Copy installed dependencies from builder stage
COPY --from=builder /install /usr/local

# Create dedicated non-root application user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

WORKDIR /app

# Copy application source code (filtered by .dockerignore)
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

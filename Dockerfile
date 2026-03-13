# ==============================================================================
# memosaur Backend Dockerfile
# ==============================================================================
#
# Multi-Stage Build für kleineres Image
# Unterstützt: amd64, arm64 (Raspberry Pi)
#
# Build: docker build -t memosaur-backend .
# Run:   docker run -p 8000:8000 -v $(pwd)/data:/app/data memosaur-backend
#
# ==============================================================================

# --- Stage 1: Builder ---------------------------------------------------------
FROM python:3.11-slim as builder

# System Dependencies (Build-Tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Python Dependencies installieren (gecacht)
# Nutze requirements-docker.txt (ohne CUDA/PyTorch - spart 700+ MB!)
WORKDIR /app
ENV PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu
COPY requirements-docker.txt ./requirements.txt
RUN pip install --no-cache-dir --user -r requirements.txt

# --- Stage 2: Runtime ---------------------------------------------------------
FROM python:3.11-slim

# Labels (Metadata)
LABEL maintainer="memosaur@example.com"
LABEL description="Privacy-First Personal Memory System"
LABEL version="2.0.0"

# System Dependencies (Runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-Root User erstellen (Security Best Practice)
# Debian slim hat kein useradd, nutze adduser
RUN addgroup --gid 1000 memosaur && \
    adduser --uid 1000 --gid 1000 --disabled-password --gecos "" memosaur && \
    mkdir -p /app/data && \
    chown -R memosaur:memosaur /app

# Python Packages aus Builder kopieren
COPY --from=builder /root/.local /home/memosaur/.local

# Application Code kopieren
WORKDIR /app
COPY --chown=memosaur:memosaur backend/ ./backend/
COPY --chown=memosaur:memosaur config.yaml.example ./config.yaml
COPY --chown=memosaur:memosaur frontend/ ./frontend/

# User wechseln
USER memosaur

# PATH für .local/bin (pip --user)
ENV PATH=/home/memosaur/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Port
EXPOSE 8000

# Startup Command
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# syntax=docker/dockerfile:1.7
# Lightweight model downloader for the init container: distroless Python, no shell, non-root user.

FROM python:3.11-slim-bookworm AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
COPY downloader/requirements.txt /tmp/requirements.txt
RUN pip install --no-deps --only-binary :all: --target /opt/deps -r /tmp/requirements.txt \
    && PYTHONPATH=/opt/deps python -c "import huggingface_hub"

FROM gcr.io/distroless/python3-debian12:nonroot
COPY --from=builder /opt/deps /opt/deps
COPY scripts/download_model.py /app/download_model.py
ENV PYTHONPATH=/opt/deps PYTHONUNBUFFERED=1 HF_HUB_DISABLE_TELEMETRY=1
USER 65532:65532
ENTRYPOINT ["python3", "/app/download_model.py"]

# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.12-slim-bookworm

FROM ${PYTHON_IMAGE} AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --no-deps --only-binary :all: -r /tmp/requirements.txt \
    && /opt/venv/bin/pip check

FROM ${PYTHON_IMAGE}
RUN apt-get update \
    && apt-get install -y --no-install-recommends libtcmalloc-minimal4 libnuma1 g++ \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 vllm \
    && useradd --uid 10001 --gid vllm --create-home --home-dir /home/vllm --shell /usr/sbin/nologin vllm

COPY --from=builder /opt/venv /opt/venv
COPY --chmod=0755 scripts/entrypoint.sh /opt/app/scripts/entrypoint.sh
COPY config/ /opt/app/config/
COPY src/ /opt/app/src/

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/opt/app/src \
    PYTHONUNBUFFERED=1 \
    HOME=/home/vllm \
    XDG_CACHE_HOME=/home/vllm/.cache \
    HF_HOME=/home/vllm/.cache/huggingface \
    VLLM_CACHE_ROOT=/home/vllm/.cache/vllm \
    VLLM_CONFIG_ROOT=/home/vllm/.cache/vllm-config \
    TRITON_CACHE_DIR=/home/vllm/.cache/triton \
    NUMBA_CACHE_DIR=/tmp/numba \
    TORCHINDUCTOR_CACHE_DIR=/tmp/torchinductor \
    LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libtcmalloc_minimal.so.4:/opt/venv/lib/libiomp5.so \
    VLLM_TARGET_DEVICE=cpu \
    VLLM_NO_USAGE_STATS=1 \
    DO_NOT_TRACK=1

USER 10001:10001
WORKDIR /home/vllm
EXPOSE 8000
ENTRYPOINT ["/opt/app/scripts/entrypoint.sh"]

#!/usr/bin/env bash
set -euo pipefail

: "${MODEL_ID:?MODEL_ID is not set}"
MODEL_DIR="${MODEL_CACHE_DIR:-/models}/${MODEL_ID//\//--}"
if [[ ! -f "${MODEL_DIR}/.download-complete.json" ]]; then
    echo "Model ${MODEL_ID} is not in ${MODEL_DIR}. The model-downloader init container must run first." >&2
    exit 1
fi

# Under a CPU limit the cgroup quota, not the cpuset, defines usable cores; derive OpenMP threads from it.
if [[ "${VLLM_CPU_OMP_THREADS_BIND:-auto}" == "nobind" && -z "${OMP_NUM_THREADS:-}" ]]; then
    read -r quota period < /sys/fs/cgroup/cpu.max 2>/dev/null || quota=max
    cpus=$([[ "${quota}" == "max" ]] && nproc || echo $(( quota / period )))
    export OMP_NUM_THREADS=$(( cpus - ${VLLM_CPU_NUM_OF_RESERVED_CPU:-1} > 0 ? cpus - ${VLLM_CPU_NUM_OF_RESERVED_CPU:-1} : 1 ))
fi

# Privacy settings are fixed here so that ConfigMap values cannot override them.
export VLLM_CONFIGURE_LOGGING=1
export VLLM_LOGGING_CONFIG_PATH=/opt/app/config/logging.json
unset VLLM_DEBUG_LOG_API_SERVER_RESPONSE
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

exec vllm serve "${MODEL_DIR}" \
    --config "${VLLM_CONFIG_FILE:-/etc/vllm/config.yaml}" \
    --host 0.0.0.0 \
    --port 8000 \
    --disable-uvicorn-access-log \
    --middleware vllm_privacy.middleware.BearerAuthMiddleware \
    --middleware vllm_privacy.middleware.AccessLogMiddleware \
    "$@"

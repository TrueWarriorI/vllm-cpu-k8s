"""Downloads model weights from Hugging Face into the model cache volume once.

On later pod starts the marker file is found and the script exits without touching the network.
"""

import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ALLOW_PATTERNS = ["*.json", "*.safetensors", "*.txt", "*.model", "*.jinja", "*.tiktoken"]
MARKER = ".download-complete.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger("download_model")


def model_dir(cache_root: Path, model_id: str) -> Path:
    return cache_root / model_id.replace("/", "--")


def is_complete(target: Path, model_id: str, revision: str) -> bool:
    marker = target / MARKER
    if not marker.is_file():
        return False
    meta = json.loads(marker.read_text())
    return meta.get("model_id") == model_id and revision in (meta.get("revision"), meta.get("commit"))


def main() -> int:
    model_id = os.environ["MODEL_ID"]
    revision = os.environ.get("MODEL_REVISION", "main")
    target = model_dir(Path(os.environ.get("MODEL_CACHE_DIR", "/models")), model_id)

    if is_complete(target, model_id, revision):
        log.info("Model %s@%s found in %s, skipping download", model_id, revision, target)
        return 0

    from huggingface_hub import HfApi, snapshot_download

    token = os.environ.get("HF_TOKEN") or None
    commit = HfApi(token=token).model_info(model_id, revision=revision).sha
    log.info("Downloading %s@%s (commit %s) to %s", model_id, revision, commit, target)
    snapshot_download(model_id, revision=commit, local_dir=target, allow_patterns=ALLOW_PATTERNS, token=token)

    marker = {"model_id": model_id, "revision": revision, "commit": commit, "at": datetime.now(UTC).isoformat()}
    tmp = target / f"{MARKER}.tmp"
    tmp.write_text(json.dumps(marker))
    tmp.replace(target / MARKER)
    log.info("Download complete: %s", target)
    return 0


if __name__ == "__main__":
    sys.exit(main())

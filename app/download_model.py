import json
import os
from pathlib import Path

from huggingface_hub import snapshot_download


def download_model():
    model = os.environ["MODEL_ID"]
    revision = os.environ["MODEL_REVISION"]
    target = Path("/cache/model")
    marker = target / ".complete.json"
    expected = {"model": model, "revision": revision}

    # Проверка выполняется ДО вызова HF: при рестарте сеть не нужна.
    if marker.exists():
        if json.loads(marker.read_text()) != expected:
            raise RuntimeError("Model changed: use a new PVC")
        print("Model cache ready", flush=True)
        return

    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=model,
        revision=revision,
        local_dir=str(target),
        token=os.environ.get("HF_TOKEN") or False,
        allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.jinja"],
    )
    temporary = target / ".complete.tmp"
    temporary.write_text(json.dumps(expected))
    temporary.replace(marker)
    print("Model downloaded", flush=True)


if __name__ == "__main__":
    download_model()

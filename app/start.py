import os
from pathlib import Path


if __name__ == "__main__":
    if not Path("/cache/model/.complete.json").exists():
        raise RuntimeError("Model cache missing: run the download initContainer")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.execvp("vllm", ["vllm", "serve", "--config", "/config/serve.yaml"])

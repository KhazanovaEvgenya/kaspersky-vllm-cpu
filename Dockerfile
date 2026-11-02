FROM python:3.12.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 libnuma1 libtcmalloc-minimal4 ffmpeg libsm6 libxext6 libgl1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home app
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --no-deps --only-binary=:all: \
    --extra-index-url https://wheels.vllm.ai/0.27.0/cpu \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt && python -m pip check
# CPU sampler PyTorch компилирует C++ ядра даже с enforce-eager.
RUN apt-get update && apt-get install -y --no-install-recommends g++ \
    && rm -rf /var/lib/apt/lists/*
COPY app/ /app/
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/cache/huggingface \
    VLLM_TARGET_DEVICE=cpu \
    CUDA_VISIBLE_DEVICES="" \
    VLLM_LOGGING_CONFIG_PATH=/app/logging.json \
    LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libtcmalloc_minimal.so.4
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["python", "/app/start.py"]

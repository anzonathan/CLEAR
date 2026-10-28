# CLEAR field detection service
# CUDA runtime image: PyTorch is preinstalled, so Ultralytics does not pull CPU torch.
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=4 \
    MKL_NUM_THREADS=4 \
    CLEAR_DATA_DIR=/data \
    CLEAR_YOLO_WEIGHTS=/app/models/yolov8n.pt

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.deploy.txt /app/requirements.deploy.txt
RUN pip install --no-cache-dir -r /app/requirements.deploy.txt

COPY . /app

# Bake COCO weights into the image so a restart does not need internet.
RUN mkdir -p /app/models \
    && cd /app/models \
    && python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" \
    && test -f /app/models/yolov8n.pt

RUN mkdir -p /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=6s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

# One worker is required: active camera + frame state is in-process.
CMD ["uvicorn", "App.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]

FROM python:3.11-slim

# PyBullet のコンパイルに必要なビルドツール + オフスクリーンレンダリング用ライブラリ
RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ \
    gcc \
    make \
    libgl1 \
    libglib2.0-0 \
    libosmesa6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p output/dataset/logs output/dataset/docs output/viz

CMD ["python", "scripts/run_dataset.py"]

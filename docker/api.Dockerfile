FROM python:3.10-slim

WORKDIR /app

# Cài đặt các gói phát triển PostgreSQL cần thiết
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy các tập tin nguồn
COPY ./src /app/src

# Thiết lập môi trường
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Khởi chạy API
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

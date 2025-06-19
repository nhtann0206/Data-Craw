FROM python:3.10-slim

WORKDIR /app

# Cài đặt các gói phát triển và thư viện cần thiết
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt dependencies cơ bản trước
COPY requirements.txt .
# Fix installation order for compatibility
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir numpy pandas scikit-learn && \
    pip install --no-cache-dir "torch==2.0.1" "torchvision==0.15.2" && \
    pip install --no-cache-dir "tensorflow==2.15.0" "keras<3.0.0" && \
    pip install --no-cache-dir -r requirements.txt

# Copy mã nguồn
COPY ./src /app/src

# Tạo thư mục lưu trữ phân tích
RUN mkdir -p /app/volume/analyses
RUN chmod -R 777 /app/volume

# Set environment variable to avoid watching problematic modules
ENV STREAMLIT_WATCHDOG_MODULES="torch,tensorflow"

# Tạo file config cho Streamlit
RUN mkdir -p /root/.streamlit
RUN echo '\
[server]\n\
runOnSave = true\n\
\n\
[browser]\n\
gatherUsageStats = false\n\
\n\
[theme]\n\
base = "light"\n\
' > /root/.streamlit/config.toml

# Thiết lập môi trường
ENV PYTHONPATH=/app
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_FILE_WATCHER_TYPE=watchdog

# Khởi chạy Streamlit
CMD ["streamlit", "run", "src/ui/app.py", "--server.port=8501", "--server.address=0.0.0.0"]

# 📊 Data Platform

> **Mục tiêu**: Một nền tảng thu thập, lưu trữ, phân tích và trực quan hoá dữ liệu chứng khoán với tích hợp AI.

---

## 📋 Mục lục
1. [Tổng quan](#tổng-quan)
2. [Tính năng chính](#tính-năng-chính)
3. [Kiến trúc hệ thống](#kiến-trúc-hệ-thống)
4. [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
5. [Cài đặt và Chạy](#cài-đặt-và-chạy)
6. [Cách sử dụng](#cách-sử-dụng)
7. [Quản lý log](#quản-lý-log)
8. [Khắc phục sự cố](#khắc-phục-sự-cố)

---

## Tổng quan
Nền tảng dữ liệu hiện đại hỗ trợ toàn bộ vòng đời của dữ liệu chứng khoán: thu thập từ nhiều nguồn, lưu trữ hiệu quả, xử lý tự động, phân tích chuyên sâu và trực quan hoá thân thiện với người dùng.

Với sự kết hợp giữa các công nghệ tiên tiến như Docker, Airflow, PostgreSQL, Streamlit và tích hợp AI, hệ thống giúp người dùng nhanh chóng tiếp cận thông tin thị trường chứng khoán và đưa ra quyết định dựa trên dữ liệu.

## 🚀 Tính năng chính
- 📥 Tự động thu thập dữ liệu chứng khoán từ Yahoo Finance
- 💾 Lưu trữ hiệu quả trong MinIO (Data Lake) và PostgreSQL
- ⏱ Lập lịch và điều phối các tác vụ với Apache Airflow
- 📊 Dashboard trực quan với Streamlit cho phép phân tích đa góc nhìn
- 🤖 Chatbot AI tích hợp phân tích chứng khoán chuyên nghiệp
- 🔄 Hệ thống quản lý log tập trung
- 🌐 API để tích hợp với các hệ thống khác

## 🏗 Kiến trúc hệ thống

| Tầng             | Thành phần           | Công nghệ sử dụng       |
|------------------|----------------------|-------------------------|
| Ingestion        | API, Crawling        | HTTP, Requests, FastAPI |
| Data Lake        | Lưu trữ raw/clean    | MinIO (S3-compatible)   |
| Data Warehouse   | Lưu trữ dữ liệu sạch | PostgreSQL              |
| Processing       | Xử lý batch/stream   | Python, Pandas          |
| Serving/API      | Truy xuất qua REST   | FastAPI                 |
| Orchestration    | Điều phối công việc  | Apache Airflow          |
| Visualization    |  UI                  | Streamlit               |

## 🧰 Yêu cầu hệ thống
- Hệ điều hành: Ubuntu/Linux, macOS, Windows với WSL2
- Docker + Docker Compose (phiên bản 1.29.0 trở lên)
- Python 3.10+
- Ít nhất 8GB RAM và 20GB dung lượng đĩa trống
- Kết nối internet (để tải thư viện và lấy dữ liệu)

## ⚙️ Cài đặt và Chạy

### 1. Cài đặt ban đầu

```bash
# Clone repository
git clone https://github.com/nhtann0206/Data-Craw
cd DataPlatform-main

# Tạo môi trường ảo và activate
python3 -m venv venv
source venv/bin/activate  # Trên Windows: venv\Scripts\activate

# Tải các thư viện cần thiết
pip install -r requirements.txt

# Cung cấp quyền thực thi cho script quản lý
chmod +x manage.sh
```

### 2. Chuẩn bị cấu trúc thư mục

```bash
# Tạo cấu trúc thư mục cần thiết
./manage.sh setup
```

### 3. Khởi động hệ thống

```bash
# Xây dựng và khởi động các container
docker compose up -d

# Đợi các dịch vụ khởi động hoàn tất (khoảng 30-60 giây)
echo "Đang đợi các dịch vụ khởi động..."
sleep 60
```

### 4. Cài đặt thư viện cần thiết trong containers

```bash
# Cài đặt thư viện Yahoo Finance trong container Airflow
./manage.sh install

# Kiểm tra trạng thái hệ thống
./manage.sh check
```

### 5. Thiết lập kết nối cho Airflow

```bash
# Tự động thiết lập kết nối giữa Airflow và các dịch vụ khác
./manage.sh fix
```

### 6. Kích hoạt và chạy pipeline thu thập dữ liệu

```bash
# Kích hoạt DAG
docker exec -it airflow-webserver airflow dags unpause stock_data_pipeline

# Kích hoạt DAG để chạy ngay
docker exec -it airflow-webserver airflow dags trigger stock_data_pipeline
```

### 7. Truy cập các dịch vụ

Sau khi hoàn tất các bước trên, bạn có thể truy cập các dịch vụ sau:

- **Streamlit UI**: http://localhost:8501
- **Airflow Webserver**: http://localhost:8080 (user/pass: airflowadmin/airflowadmin)
- **MinIO Console**: http://localhost:9001 (user/pass: minioadmin/minioadmin)
- **FastAPI Docs**: http://localhost:8000/docs

## 🚦 Cách sử dụng

### 1. Thu thập dữ liệu chứng khoán

Dữ liệu sẽ được thu thập tự động qua DAG `stock_data_pipeline` trong Airflow. Để kiểm tra tiến trình:

1. Truy cập Airflow UI tại http://localhost:8080
2. Đăng nhập với tài khoản mặc định (airflowadmin/airflowadmin)
3. Tìm DAG `stock_data_pipeline` trong danh sách
4. Nhấp vào DAG để xem chi tiết và theo dõi tiến trình

Để kích hoạt thu thập dữ liệu thủ công:

```bash
docker exec -it airflow-webserver airflow dags trigger stock_data_pipeline
```

### 2. Xem dữ liệu đã thu thập

Kiểm tra dữ liệu thông qua lệnh:

```bash
# Kiểm tra dữ liệu bằng script check_data.py
docker exec -it fastapi python -m src.utils.check_data
```

Hoặc truy cập và xem dữ liệu trong MinIO:

1. Mở MinIO Console tại http://localhost:9001
2. Đăng nhập với thông tin (minioadmin/minioadmin)
3. Duyệt qua bucket `stock-data` để xem các file đã lưu trữ

### 3. Sử dụng giao diện Web Streamlit

Giao diện Streamlit cho phép:
- Xem biểu đồ giá cổ phiếu các công ty
- Chọn khung thời gian hiển thị (1h, 1d, 1w, 1m)
- Tương tác với AI chatbot để phân tích dữ liệu
- Xem lịch sử phân tích đã được thực hiện

Truy cập vào URL: http://localhost:8501

### 4. Sử dụng Chatbot phân tích chứng khoán

1. Mở giao diện Streamlit
2. Chuyển đến tab "Chat with StockGPT"
3. Đặt câu hỏi về dữ liệu chứng khoán như:
   - "Phân tích xu hướng của AAPL trong tuần qua"
   - "So sánh hiệu suất của GOOG và MSFT"
   - "Dự đoán xu hướng của TSLA trong thời gian tới"

### 5. Kiểm tra API

Các API có sẵn để truy xuất dữ liệu chứng khoán:
- Xem tài liệu API tại http://localhost:8000/docs
- Thử nghiệm các endpoint trực tiếp từ tài liệu

## 🛠️ Quản lý log

### Xem log của các container

```bash
# Xem log của container Airflow
docker logs airflow-webserver

# Xem log của container FastAPI
docker logs fastapi

# Xem log của container Streamlit
docker logs streamlit
```

### Xem log của hệ thống

```bash
# Xem log của toàn bộ hệ thống
docker-compose logs
```

## 🛠️ Khắc phục sự cố

### Vấn đề kết nối giữa các container

Nếu các container không thể kết nối với nhau:

```bash
# Chạy script sửa lỗi mạng và kết nối
./fix_network.sh
```

### DAG Airflow không hiển thị hoặc không hoạt động

```bash
# Kiểm tra logs của Airflow Scheduler
docker logs airflow-scheduler

# Chạy script sửa lỗi DAG
docker cp src/dags/fix_dag_visibility.py airflow-scheduler:/opt/airflow/dags/
docker exec -it airflow-scheduler python /opt/airflow/dags/fix_dag_visibility.py
```

### Sửa lỗi chung trong hệ thống

```bash
# Chạy script sửa lỗi tổng thể
./fix_all.sh
```

### Lỗi hiển thị Streamlit UI

```bash
# Khởi động lại container Streamlit
docker restart streamlit

# Kiểm tra logs
docker logs streamlit
```

## 📦 Thành phần chi tiết

### 1. MinIO (Data Lake)
- Lưu trữ dữ liệu thô (raw) và dữ liệu đã xử lý (clean)
- Truy cập qua cổng 9000 (API) và 9001 (console UI)
- Có thể thao tác bằng boto3 như Amazon S3

### 2. PostgreSQL (Data Warehouse)
- Lưu dữ liệu dạng bảng sau xử lý
- Cổng mặc định: 5432 (ảnh xạ ra 5433)
- Database: `postgres`, Table: `stock_data` và `stock_data_v2`

### 3. Apache Airflow (ETL & Orchestration)
- Giao diện web: http://localhost:8080
- Các DAG chính:
  - `stock_data_pipeline`: Thu thập dữ liệu chứng khoán

### 4. FastAPI (Data API)
- Documentation: http://localhost:8000/docs
- Endpoint chính:
  - `/stock/data/{symbol}`: Lấy dữ liệu cho mã chứng khoán
  - `/stock/status`: Kiểm tra trạng thái dữ liệu
  - `/stock/symbols`: Danh sách các mã chứng khoán có sẵn

### 5. Streamlit (Dashboard UI)
- Giao diện: http://localhost:8501
- Các tính năng:
  - Dashboard hiển thị biểu đồ giá
  - Chatbot phân tích chứng khoán
  - Lịch sử phân tích

### Lệnh Quản lý Hữu ích

```bash
# Xem trạng thái container
docker ps

# Xem logs của container
docker logs [tên-container]

# Khởi động lại container
docker restart [tên-container]

# Vào terminal của container
docker exec -it [tên-container] bash

# Kiểm tra dữ liệu PostgreSQL
docker exec -it postgres psql -U postgresadmin -d postgres -c "SELECT COUNT(*) FROM stock_data;"

# Kiểm tra bucket MinIO
docker exec -it minio mc ls local/stock-data/

# Dừng toàn bộ hệ thống
docker compose down

# Khởi động lại toàn bộ hệ thống với tối ưu hiệu năng
docker compose -f docker-compose.yml -f performance.yml up -d
```


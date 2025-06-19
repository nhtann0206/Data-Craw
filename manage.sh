#!/bin/bash

# Colors for better readability
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to display help
show_help() {
    echo -e "${GREEN}=== Data Platform Management Script ===${NC}"
    echo "Usage: ./manage.sh [command]"
    echo ""
    echo "Commands:"
    echo "  setup        - Set up directory structure and initial configuration"
    echo "  install      - Install required packages in containers"
    echo "  check        - Check system status and data availability"
    echo "  fix          - Fix common issues with services"
    echo "  cleanup      - Clean up temporary files and caches"
    echo "  cleanup-all  - Clean up temporary files and remove unused components"
    echo "  logs         - Set up log management system"
    echo "  logs-cleanup - Clean up old logs (>30 days)"
    echo "  help         - Show this help message"
    echo ""
    echo "Example: ./manage.sh setup"
}

setup() {
    echo -e "${GREEN}=== Setting up directory structure ===${NC}"
    
    # Create only essential data directories (no logs)
    echo "Creating data directories..."
    mkdir -p data/{postgres,minio}
    
    # Set permissions
    chmod -R 777 data
    
    # Setup logs in the separate log_management structure
    echo "Setting up centralized log management..."
    setup_logs
    
    # Create symlinks if needed for backward compatibility
    ln -sf log_management/analyses data/analyses 2>/dev/null || echo "Note: Could not create analyses symlink"
    
    echo "✅ Cấu trúc thư mục đã được chuẩn hóa!"
    echo "Cấu trúc thư mục logs:"
    find log_management -type d | sort
}

install_packages() {
    echo -e "${GREEN}=== Installing required packages ===${NC}"
    
    echo "Installing yfinance in Airflow containers..."
    
    # Tạo file requirements tạm thời
    echo "yfinance>=0.2.31" > airflow-requirements.txt

    # Cài đặt packages theo cách được khuyến nghị cho Airflow
    echo "Installing packages in airflow-scheduler..."
    docker cp airflow-requirements.txt airflow-scheduler:/opt/airflow/requirements.txt
    
    # Sử dụng đúng cách để cài đặt packages trong Airflow
    docker exec -it airflow-scheduler bash -c "pip install -r /opt/airflow/requirements.txt"

    echo "Installing packages in airflow-webserver..."
    docker cp airflow-requirements.txt airflow-webserver:/opt/airflow/requirements.txt
    docker exec -it airflow-webserver bash -c "pip install -r /opt/airflow/requirements.txt"

    # Xóa file requirements tạm thời
    rm airflow-requirements.txt

    echo -e "${YELLOW}Verifying installation...${NC}"
    # Sửa lỗi indentation trong Python code
    docker exec -it airflow-scheduler python -c "
try:
    import yfinance
    print(f'yfinance version: {yfinance.__version__}')
    print('✅ Thư viện yfinance đã được cài đặt thành công!')
except ImportError:
    print('❌ Lỗi: Thư viện yfinance chưa được cài đặt!')
"

    echo -e "${GREEN}=== Package installation completed ===${NC}"
}

check_status() {
    echo -e "${GREEN}=== CHECKING DATA PLATFORM STATUS ===${NC}"

    # Check container status
    echo -e "${YELLOW}Container Status:${NC}"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

    # Check if data has been crawled
    echo -e "\n${YELLOW}Checking Crawled Data:${NC}"
    docker exec -it fastapi python -m src.utils.check_data

    # Check Airflow DAG status
    echo -e "\n${YELLOW}Checking Airflow DAG Status:${NC}"
    docker exec -it airflow-webserver airflow dags list-runs -d stock_data_pipeline 2>/dev/null || echo -e "${RED}No DAG runs found. DAG may not be active.${NC}"

    echo -e "\n${GREEN}=== Check completed ===${NC}"
    echo -e "Access your services at:"
    echo "  - Airflow: http://localhost:8080"
    echo "  - Streamlit: http://localhost:8501"
    echo "  - MinIO Console: http://localhost:9001"
    echo "  - FastAPI Documentation: http://localhost:8000/docs"
}

fix_services() {
    echo -e "${GREEN}=== Fixing Common Issues ===${NC}"
    
    echo -e "${YELLOW}1. Checking Airflow DAGs directory...${NC}"
    docker exec -it airflow-scheduler ls -la /opt/airflow/dags
    
    echo -e "${YELLOW}2. Fixing DAG file permissions...${NC}"
    find ./src/dags -type f -name "*.py" -exec chmod 644 {} \;
    
    echo -e "${YELLOW}3. Installing required packages in containers...${NC}"
    docker exec -u 0 -it airflow-scheduler pip install yfinance -q
    
    echo -e "${YELLOW}4. Validating DAG parsing...${NC}"
    docker exec -it airflow-scheduler python -c "
    import sys
    sys.path.insert(0, '/opt/airflow')
    sys.path.insert(0, '/opt/airflow/src')
    try:
        from airflow.models.dag import DAG
        print('Airflow DAG module can be imported')
        
        import os
        dags_folder = '/opt/airflow/dags'
        print(f'DAGs folder contents: {os.listdir(dags_folder)}')
        
        sys.path.insert(0, dags_folder)
        import stock_data_pipeline
        print('✅ Successfully imported stock_data_pipeline')
    except Exception as e:
        print(f'❌ Error importing DAG: {str(e)}')
    "
    
    echo -e "${YELLOW}5. Creating MinIO bucket if needed...${NC}"
    docker exec -it minio mc alias set local http://localhost:9000 minioadmin minioadmin
    docker exec -it minio mc mb local/stock-data 2>/dev/null || echo "Bucket already exists"
    
    echo -e "${YELLOW}6. Restarting services...${NC}"
    docker restart airflow-scheduler airflow-webserver streamlit
    
    echo -e "${GREEN}=== Fix completed ===${NC}"
    echo "Please wait a minute and then run './manage.sh check' to verify if issues are resolved."
}

cleanup_temp() {
    echo -e "${GREEN}=== Cleaning up temporary files ===${NC}"
    
    # Xóa file cache Python
    find . -type d -name "__pycache__" -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete
    find . -type f -name "*.pyo" -delete
    find . -type f -name "*.pyd" -delete
    find . -type f -name ".coverage" -delete
    find . -type d -name ".pytest_cache" -exec rm -rf {} +
    find . -type d -name ".ipynb_checkpoints" -exec rm -rf {} +

    # Xóa các thư mục ẩn khác
    find . -type d -name ".DS_Store" -delete
    
    echo -e "${GREEN}✅ Cleanup completed!${NC}"
}

cleanup_all() {
    echo -e "${GREEN}=== Removing Unnecessary Files ===${NC}"
    
    # Confirm before deletion
    read -p "This will remove unused files and components. Continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]
    then
        echo "Operation cancelled"
        return
    fi
    
    # Remove CoinGecko related files (cryptocurrency, not stocks)
    echo "Removing cryptocurrency files..."
    rm -f src/dags/coingecko_minio_ingest_dag.py
    rm -f src/ingestion/coingecko_ingestor.py

    # Remove unused processing modules
    echo "Removing unused processing modules..."
    rm -f src/processing/transform.py
    rm -f src/processing/Dockerfile
    rmdir src/processing 2>/dev/null || echo "Processing directory contains other files, not removed"

    # Consolidate fix scripts
    echo "Removing redundant scripts..."
    rm -f fix_airflow.sh
    rm -f fix_streamlit.sh
    rm -f run_check.sh
    rm -f cleanup_unused.sh
    rm -f install_yfinance.sh
    
    # Also perform regular cleanup
    cleanup_temp
    
    echo -e "${GREEN}=== Cleanup Complete ===${NC}"
    echo "Files removed. Please verify that the platform still works correctly."
}

# Add new function for log management
setup_logs() {
    echo -e "${GREEN}=== Setting up log management ===${NC}"
    
    # Create log directories - include all data that should be logged/tracked
    mkdir -p log_management/{airflow,fastapi,streamlit,postgres,minio,system,crawlers,ml,api,analyses,stock_data,dag_runs}
    
    # Create placeholder files in each directory
    for dir in log_management/{airflow,fastapi,streamlit,postgres,minio,system,crawlers,ml,api,analyses,stock_data,dag_runs}; do
        touch "$dir/.gitkeep"
    done
    
    echo -e "${GREEN}✅ Log management setup completed!${NC}"
    
    # Show log structure
    find log_management -type d | sort
}

# Add log cleanup function
cleanup_logs() {
    echo -e "${GREEN}=== Cleaning up old logs ===${NC}"
    
    # Ask for confirmation
    read -p "This will remove logs older than 30 days. Continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]
    then
        echo "Operation cancelled"
        return
    fi
    
    # Find and remove old log files
    find log_management -type f -name "*.log" -mtime +30 -exec rm {} \;
    
    echo -e "${GREEN}✅ Log cleanup completed!${NC}"
}

# Main script logic
case "$1" in
    setup)
        setup
        ;;
    install)
        install_packages
        ;;
    check)
        check_status
        ;;
    fix)
        fix_services
        ;;
    cleanup)
        cleanup_temp
        ;;
    cleanup-all)
        cleanup_all
        ;;
    logs)
        setup_logs
        ;;
    logs-cleanup)
        cleanup_logs
        ;;
    help|--help|-h)
        show_help
        echo -e "\nLog Management Commands:"
        echo "  logs         - Set up log management system"
        echo "  logs-cleanup - Clean up old logs (>30 days)"
        ;;
    *)
        echo -e "${RED}Error: Unknown command '$1'${NC}"
        show_help
        exit 1
        ;;
esac

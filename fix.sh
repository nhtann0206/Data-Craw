#!/bin/bash

# Colors for better readability
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to display help information
show_help() {
    echo -e "${GREEN}===== Data Platform Fix Script =====${NC}"
    echo "Usage: ./fix.sh [command]"
    echo ""
    echo "Commands:"
    echo "  all            - Run all fixes sequentially"
    echo "  db             - Fix database connection issues"
    echo "  network        - Fix network connection between containers"
    echo "  dag            - Fix DAG timeout and visibility issues"
    echo "  packages       - Fix Python package installation issues"
    echo "  containers     - Check and fix container status"
    echo "  transfer       - Transfer data from MinIO to PostgreSQL"
    echo "  help           - Show this help message"
    echo ""
    echo "Example: ./fix.sh db"
}

# Function to fix database issues
fix_database() {
    echo -e "${GREEN}===== FIXING DATABASE ISSUES =====${NC}"
    
    # Get environment variables
    source .env 2>/dev/null || echo "No .env file found, using default values"
    
    DB_NAME=${AIRFLOW_DB:-"airflowdb"}
    DB_USER=${POSTGRES_USER:-"postgresadmin"}
    DB_PASSWORD=${POSTGRES_PASSWORD:-"postgresadmin"}
    EXISTING_DB=${POSTGRES_DB:-"postgres"}
    
    echo -e "${YELLOW}1. Checking PostgreSQL container...${NC}"
    if ! docker ps | grep -q "postgres"; then
        echo -e "${RED}PostgreSQL container not running. Starting...${NC}"
        docker-compose up -d postgres
        sleep 10
    fi
    
    echo -e "${YELLOW}2. Creating Airflow database '${DB_NAME}'...${NC}"
    docker exec postgres psql -U ${DB_USER} -d ${EXISTING_DB} -c "CREATE DATABASE ${DB_NAME};" || echo "Database may already exist"
    
    echo -e "${YELLOW}3. Verifying database creation...${NC}"
    docker exec postgres psql -U ${DB_USER} -d ${EXISTING_DB} -c "SELECT datname FROM pg_database WHERE datname='${DB_NAME}';"
    
    echo -e "${YELLOW}4. Updating Airflow configuration...${NC}"
    docker exec airflow-webserver bash -c "sed -i 's/postgres\/postgres/postgres\/${DB_NAME}/g' /opt/airflow/airflow.cfg"
    docker exec airflow-scheduler bash -c "sed -i 's/postgres\/postgres/postgres\/${DB_NAME}/g' /opt/airflow/airflow.cfg"
    
    echo -e "${YELLOW}5. Restarting Airflow services...${NC}"
    docker restart airflow-webserver airflow-scheduler
    
    echo -e "${GREEN}Waiting for services to restart (15 seconds)...${NC}"
    sleep 15
    
    echo -e "${YELLOW}6. Testing database connection...${NC}"
    docker exec airflow-webserver airflow db check
    
    echo -e "${GREEN}Database fix completed.${NC}"
}

# Function to fix network connection issues
fix_network() {
    echo -e "${GREEN}===== FIXING NETWORK CONNECTION ISSUES =====${NC}"
    
    echo -e "${YELLOW}1. Getting container IPs...${NC}"
    NETWORK=$(docker network ls | grep dataplatform | awk '{print $2}')
    echo "Using network: $NETWORK"
    
    # Show container IPs for debugging
    echo "Container network details:"
    docker inspect -f '{{.Name}} - {{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $(docker ps -q)
    
    echo -e "${YELLOW}2. Creating hosts file with IPs...${NC}"
    TEMP_HOSTS_FILE=$(mktemp)
    echo "# Container hosts" > $TEMP_HOSTS_FILE
    
    for container in postgres minio airflow-scheduler airflow-webserver fastapi streamlit; do
        if docker ps -q -f name=$container >/dev/null; then
            IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $container)
            if [ -n "$IP" ]; then
                echo "$IP $container" >> $TEMP_HOSTS_FILE
                echo "Added mapping: $IP → $container"
            fi
        fi
    done
    
    echo -e "${YELLOW}3. Updating container hosts files...${NC}"
    for container in airflow-scheduler airflow-webserver; do
        if docker ps -q -f name=$container >/dev/null; then
            docker cp $TEMP_HOSTS_FILE $container:/tmp/hosts_append
            docker exec $container bash -c "cat /tmp/hosts_append >> /etc/hosts"
        fi
    done
    
    rm $TEMP_HOSTS_FILE
    
    echo -e "${YELLOW}4. Setting up Airflow connections...${NC}"
    POSTGRES_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' postgres)
    MINIO_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' minio)
    
    # Update connections
    docker exec airflow-webserver airflow connections delete postgres_default 2>/dev/null || echo "No postgres connection to delete"
    docker exec airflow-webserver airflow connections delete minio_conn 2>/dev/null || echo "No minio connection to delete"
    
    docker exec airflow-webserver airflow connections add postgres_default \
        --conn-type postgres \
        --conn-host "$POSTGRES_IP" \
        --conn-port 5432 \
        --conn-schema postgres \
        --conn-login postgresadmin \
        --conn-password postgresadmin
        
    docker exec airflow-webserver airflow connections add minio_conn \
        --conn-type aws \
        --conn-host "$MINIO_IP" \
        --conn-port 9000 \
        --conn-login minioadmin \
        --conn-password minioadmin \
        --conn-extra '{"endpoint_url": "http://'$MINIO_IP':9000", "region_name": "us-east-1"}'
    
    echo -e "${GREEN}Network fix completed.${NC}"
}

# Function to fix DAG timeout and visibility issues
fix_dags() {
    echo -e "${GREEN}===== FIXING DAG ISSUES =====${NC}"
    
    echo -e "${YELLOW}1. Setting DAG processing timeout...${NC}"
    docker exec airflow-webserver bash -c "sed -i 's/dag_file_processor_timeout = [0-9]*/dag_file_processor_timeout = 300/' /opt/airflow/airflow.cfg"
    docker exec airflow-scheduler bash -c "sed -i 's/dag_file_processor_timeout = [0-9]*/dag_file_processor_timeout = 300/' /opt/airflow/airflow.cfg"
    
    echo -e "${YELLOW}2. Optimizing scheduler settings...${NC}"
    docker exec airflow-scheduler bash -c "sed -i 's/max_threads = [0-9]*/max_threads = 2/' /opt/airflow/airflow.cfg"
    docker exec airflow-scheduler bash -c "sed -i 's/parsing_processes = [0-9]*/parsing_processes = 1/' /opt/airflow/airflow.cfg"
    docker exec airflow-scheduler bash -c "sed -i 's/parallelism = [0-9]*/parallelism = 4/' /opt/airflow/airflow.cfg"
    
    echo -e "${YELLOW}3. Creating .airflowignore...${NC}"
    echo "# Ignore problematic modules
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
" > .airflowignore
    docker cp .airflowignore airflow-scheduler:/opt/airflow/dags/.airflowignore
    docker cp .airflowignore airflow-webserver:/opt/airflow/dags/.airflowignore
    rm .airflowignore
    
    echo -e "${YELLOW}4. Running DAG visibility fix script...${NC}"
    docker cp src/dags/fix_dag_visibility.py airflow-scheduler:/opt/airflow/dags/fix_dag_visibility.py
    docker exec airflow-scheduler python "/opt/airflow/dags/fix_dag_visibility.py"
    
    echo -e "${YELLOW}5. Restarting Airflow...${NC}"
    docker restart airflow-scheduler airflow-webserver
    sleep 15
    
    echo -e "${YELLOW}6. Testing DAG loading...${NC}"
    docker exec airflow-scheduler python -c "
from airflow.models.dagbag import DagBag
import time
start = time.time()
dagbag = DagBag(include_examples=False)
end = time.time()
if dagbag.import_errors:
    print('DAG import errors:')
    for file, err in dagbag.import_errors.items():
        print(f'  File: {file}, Error: {err}')
else:
    print(f'✅ All DAGs loaded successfully in {end-start:.2f} seconds')
    print(f'Found {len(dagbag.dags)} DAGs')
    for dag_id in dagbag.dags:
        print(f'  - {dag_id}')
"
    
    echo -e "${GREEN}DAG fix completed.${NC}"
}

# Function to fix package installation issues
fix_packages() {
    echo -e "${GREEN}===== FIXING PACKAGE INSTALLATION ISSUES =====${NC}"
    
    echo -e "${YELLOW}1. Creating requirements file...${NC}"
    cat > requirements_fix.txt << EOF
yfinance>=0.2.31
curl_cffi>=1.0.0
eventlet>=0.33.0
boto3>=1.26.0
EOF
    
    echo -e "${YELLOW}2. Installing packages in Airflow...${NC}"
    for container in airflow-scheduler airflow-webserver; do
        echo "Installing packages in $container..."
        docker cp requirements_fix.txt $container:/opt/airflow/requirements_fix.txt
        docker exec $container python -m pip install --user -r /opt/airflow/requirements_fix.txt
    done
    
    rm requirements_fix.txt
    
    echo -e "${YELLOW}3. Verifying installations...${NC}"
    docker exec airflow-webserver python -c "
import sys
print(f'Python version: {sys.version}')
try:
    import yfinance
    print(f'✅ yfinance version: {yfinance.__version__}')
except ImportError as e:
    print(f'❌ yfinance not installed: {e}')
"
    
    echo -e "${GREEN}Package fix completed.${NC}"
}

# Function to check and fix container status
fix_containers() {
    echo -e "${GREEN}===== FIXING CONTAINER ISSUES =====${NC}"
    
    echo -e "${YELLOW}1. Checking container status...${NC}"
    for container in postgres minio airflow-scheduler airflow-webserver fastapi streamlit; do
        if ! docker ps | grep -q $container; then
            echo -e "${RED}$container is not running. Starting...${NC}"
            docker start $container || docker-compose up -d $container
            sleep 5
        else
            echo -e "${GREEN}✓ $container is running${NC}"
        fi
    done
    
    echo -e "${YELLOW}2. Checking container health...${NC}"
    for container in postgres minio airflow-scheduler airflow-webserver fastapi streamlit; do
        if docker ps | grep -q $container; then
            status=$(docker inspect --format='{{.State.Status}}' $container)
            echo "$container status: $status"
        fi
    done
    
    echo -e "${GREEN}Container fix completed.${NC}"
}

# Function to transfer data from MinIO to PostgreSQL
transfer_data() {
    echo -e "${GREEN}===== TRANSFERRING DATA FROM MINIO TO POSTGRESQL =====${NC}"
    
    echo -e "${YELLOW}Running data transfer script in FastAPI container...${NC}"
    docker exec fastapi python -m src.utils.fix_data_transfer
    
    echo -e "${GREEN}Data transfer completed.${NC}"
}

# Main script logic
case "$1" in
    all)
        fix_containers
        fix_database
        fix_network
        fix_packages
        fix_dags
        transfer_data
        echo -e "${GREEN}All fixes have been applied.${NC}"
        ;;
    db)
        fix_database
        ;;
    network)
        fix_network
        ;;
    dag)
        fix_dags
        ;;
    packages)
        fix_packages
        ;;
    containers)
        fix_containers
        ;;
    transfer)
        transfer_data
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}Error: Unknown command '$1'${NC}"
        show_help
        exit 1
        ;;
esac

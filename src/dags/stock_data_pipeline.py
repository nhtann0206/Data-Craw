from datetime import datetime, timedelta
import pandas as pd
import os
import io
import logging
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from airflow.hooks.base import BaseHook
import boto3
import psycopg2
import psycopg2.extras as extras
import sys

# Add src to path
sys.path.insert(0, '/opt/airflow/src')
from crawlers.stock_crawler import StockCrawler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Log to console
        logging.FileHandler('/opt/airflow/logs/stock_pipeline.log'),  # Sử dụng thư mục logs có sẵn của airflow
    ]
)
logger = logging.getLogger(__name__)

# Default settings
DEFAULT_ARGS = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': days_ago(1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Stocks to crawl - major tech and finance companies
STOCK_SYMBOLS = ['AAPL', 'MSFT', 'GOOG', 'AMZN', 'META', 'TSLA', 'JPM', 'BAC', 'V', 'MA']

# Khung thời gian cần thu thập
TIMEFRAMES = {
    'hourly': {'timeframe': '1h', 'period': '60d'},
    'daily': {'timeframe': '1d', 'period': '1y'},
    'weekly': {'timeframe': '1wk', 'period': '5y'},
    'monthly': {'timeframe': '1mo', 'period': '10y'}
}

# Create DAG
dag = DAG(
    'stock_data_pipeline',
    default_args=DEFAULT_ARGS,
    description='Pipeline to crawl and process stock market data',
    schedule_interval=timedelta(hours=1),
    catchup=False,
    tags=['stock', 'data'],
)

def get_minio_connection():
    """Get MinIO connection from Airflow connections"""
    try:
        minio_conn = BaseHook.get_connection('minio_conn')
        s3_client = boto3.client(
            's3',
            endpoint_url=f'http://{minio_conn.host}:{minio_conn.port}',
            aws_access_key_id=minio_conn.login,
            aws_secret_access_key=minio_conn.password,
            region_name='us-east-1',  # Can be any region for MinIO
        )
        logger.info(f"Successfully connected to MinIO at {minio_conn.host}:{minio_conn.port}")
        return s3_client
    except Exception as e:
        logger.error(f"Failed to connect to MinIO: {str(e)}")
        # Fallback to environment variables
        try:
            s3_client = boto3.client(
                's3',
                endpoint_url='http://minio:9000',
                aws_access_key_id=os.environ.get('MINIO_ROOT_USER', 'minioadmin'),
                aws_secret_access_key=os.environ.get('MINIO_ROOT_PASSWORD', 'minioadmin'),
                region_name='us-east-1',
            )
            logger.info("Connected to MinIO using environment variables")
            return s3_client
        except Exception as e2:
            logger.error(f"Failed to connect to MinIO using environment variables: {str(e2)}")
            raise

def get_postgres_connection():
    """Get Postgres connection from Airflow connections"""
    try:
        pg_conn = BaseHook.get_connection('postgres_default')
        conn = psycopg2.connect(
            host=pg_conn.host,
            port=pg_conn.port,
            dbname=pg_conn.schema,
            user=pg_conn.login,
            password=pg_conn.password,
        )
        logger.info(f"Successfully connected to PostgreSQL at {pg_conn.host}:{pg_conn.port}/{pg_conn.schema}")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {str(e)}")
        # Fallback to environment variables
        try:
            conn = psycopg2.connect(
                host=os.environ.get('POSTGRES_HOST', 'postgres'),
                port=os.environ.get('POSTGRES_PORT', '5432'),
                dbname=os.environ.get('POSTGRES_DB', 'postgres'),
                user=os.environ.get('POSTGRES_USER', 'postgresadmin'),
                password=os.environ.get('POSTGRES_PASSWORD', 'postgresadmin'),
            )
            logger.info("Connected to PostgreSQL using environment variables")
            return conn
        except Exception as e2:
            logger.error(f"Failed to connect to PostgreSQL using environment variables: {str(e2)}")
            raise

# Thêm logging để dễ theo dõi tiến trình
def crawl_stock_data(symbol, timeframe_key='daily', **kwargs):
    """Crawl stock data and save to MinIO"""
    try:
        logger.info(f"Starting to crawl data for {symbol} with timeframe {timeframe_key}")
        
        # Lấy thông số khung thời gian
        timeframe_config = TIMEFRAMES.get(timeframe_key, TIMEFRAMES['daily'])
        timeframe = timeframe_config['timeframe']
        period = timeframe_config['period']
        
        # Khởi tạo crawler
        api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
        crawler = StockCrawler(api_key=api_key, data_source="yahoo") 
        
        # Lấy dữ liệu theo khung thời gian
        df = crawler.get_historical_data(symbol, timeframe=timeframe, period=period)
        
        if df.empty:
            logger.warning(f"No data fetched for {symbol} with timeframe {timeframe_key}")
            return None
            
        logger.info(f"Successfully fetched {len(df)} rows for {symbol} with timeframe {timeframe_key}")
        logger.info(f"Sample data: {df.head(1).to_dict('records')}")
        
        # Create execution timestamp
        execution_date = kwargs['execution_date'].strftime('%Y-%m-%d_%H-%M-%S')
        
        # Save to MinIO
        s3_client = get_minio_connection()
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        
        # Create bucket if not exists
        bucket_name = 'stock-data'
        try:
            s3_client.head_bucket(Bucket=bucket_name)
        except:
            s3_client.create_bucket(Bucket=bucket_name)
        
        # Save file to MinIO with timeframe info in the path
        object_key = f'{symbol}/{timeframe_key}/{execution_date}.csv'
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=csv_buffer.getvalue()
        )
        
        logger.info(f"Successfully saved {symbol} {timeframe_key} data to MinIO at {object_key}")
        
        return {
            'symbol': symbol,
            'timeframe': timeframe_key,
            'file_path': f's3://{bucket_name}/{object_key}',
            'row_count': len(df),
            'execution_date': execution_date
        }
        
    except Exception as e:
        logger.error(f"Error in crawling {symbol} with timeframe {timeframe_key}: {str(e)}")
        raise

def insert_to_postgres(symbol, timeframe_key='daily', **kwargs):
    """Insert stock data to Postgres"""
    try:
        ti = kwargs['ti']
        # Lấy kết quả từ task crawling tương ứng
        task_id = f'crawl_{symbol}_{timeframe_key}'
        crawl_result = ti.xcom_pull(task_ids=task_id)
        
        if not crawl_result:
            logger.warning(f"No crawl result found for {symbol} with timeframe {timeframe_key}")
            return
        
        logger.info(f"Processing crawl result for {symbol} with timeframe {timeframe_key}: {crawl_result}")
        
        # Get data from MinIO
        s3_client = get_minio_connection()
        bucket_name = 'stock-data'
        object_key = crawl_result['file_path'].replace(f's3://{bucket_name}/', '')
        
        logger.info(f"Retrieving data from MinIO at {bucket_name}/{object_key}")
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        df = pd.read_csv(io.BytesIO(response['Body'].read()))
        logger.info(f"Retrieved {len(df)} rows from MinIO for {symbol} with timeframe {timeframe_key}")
        
        # Connect to Postgres
        conn = get_postgres_connection()
        cursor = conn.cursor()
        
        # Create or update upgraded table with timeframe support
        create_table_query = """
        CREATE TABLE IF NOT EXISTS stock_data_v2 (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10),
            timestamp TIMESTAMP,
            timeframe VARCHAR(10),  -- new field for timeframe
            open FLOAT,
            high FLOAT,
            low FLOAT,
            close FLOAT,
            volume FLOAT,
            sma_20 FLOAT,           -- technical indicators
            sma_50 FLOAT,
            sma_200 FLOAT,
            daily_return FLOAT,
            volatility_10d FLOAT,
            volume_change FLOAT,
            rs_50 FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, timestamp, timeframe)
        );
        
        CREATE INDEX IF NOT EXISTS idx_stock_v2_symbol_ts_tf ON stock_data_v2(symbol, timestamp, timeframe);
        CREATE INDEX IF NOT EXISTS idx_stock_v2_timeframe ON stock_data_v2(timeframe);
        """
        cursor.execute(create_table_query)
        logger.info(f"Created/verified stock_data_v2 table")
        
        # Prepare data for insertion, including any technical indicators
        columns = [col for col in df.columns if col in [
            'symbol', 'timestamp', 'timeframe', 'open', 'high', 'low', 'close', 'volume',
            'sma_20', 'sma_50', 'sma_200', 'daily_return', 'volatility_10d', 'volume_change', 'rs_50'
        ]]
        
        # Construct dynamic tuple based on available columns
        tuples = []
        for _, row in df.iterrows():
            values = [row[col] if col in row and pd.notna(row[col]) else None for col in columns]
            tuples.append(tuple(values))
        
        # Generate column placeholder and query dynamically
        column_str = ', '.join(columns)
        placeholder_str = ', '.join(['%s'] * len(columns))
        update_str = ', '.join([f"{col} = EXCLUDED.{col}" for col in columns if col not in ['symbol', 'timestamp', 'timeframe']])
        
        # Batch insert with conflict handling
        try:
            insert_query = f"""
            INSERT INTO stock_data_v2 ({column_str})
            VALUES ({placeholder_str})
            ON CONFLICT (symbol, timestamp, timeframe) 
            DO UPDATE SET
                {update_str};
            """
            extras.execute_values(cursor, insert_query, tuples)
            conn.commit()
            logger.info(f"Successfully inserted {len(tuples)} rows for {symbol} ({timeframe_key}) into Postgres")
            
            # Check how many rows were actually inserted
            cursor.execute(f"SELECT COUNT(*) FROM stock_data_v2 WHERE symbol = '{symbol}' AND timeframe = '{timeframe_key}'")
            row_count = cursor.fetchone()[0]
            logger.info(f"Total rows for {symbol} with timeframe {timeframe_key} in database: {row_count}")
            
        except Exception as e:
            logger.error(f"Error in database insertion for {symbol} ({timeframe_key}): {str(e)}")
            conn.rollback()
            
        cursor.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error in inserting data for {symbol} with timeframe {timeframe_key}: {str(e)}")
        raise

# Create tasks for each stock symbol and timeframe
for symbol in STOCK_SYMBOLS:
    for timeframe_key in TIMEFRAMES.keys():
        # Create crawl task for this symbol and timeframe
        crawl_task = PythonOperator(
            task_id=f'crawl_{symbol}_{timeframe_key}',
            python_callable=crawl_stock_data,
            op_kwargs={'symbol': symbol, 'timeframe_key': timeframe_key},
            dag=dag,
        )
        
        # Create DB insert task
        db_task = PythonOperator(
            task_id=f'insert_to_db_{symbol}_{timeframe_key}',
            python_callable=insert_to_postgres,
            op_kwargs={'symbol': symbol, 'timeframe_key': timeframe_key},
            dag=dag,
        )
        
        # Set task dependencies
        crawl_task >> db_task

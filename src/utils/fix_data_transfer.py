import os
import boto3
import pandas as pd
import io
import psycopg2
from psycopg2.extras import execute_batch
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_minio_connection():
    """Connect to MinIO"""
    s3_client = boto3.client(
        's3',
        endpoint_url=f'http://{os.environ.get("MINIO_HOST", "minio")}:{os.environ.get("MINIO_PORT", "9000")}',
        aws_access_key_id=os.environ.get('MINIO_ROOT_USER', 'minioadmin'),
        aws_secret_access_key=os.environ.get('MINIO_ROOT_PASSWORD', 'minioadmin'),
    )
    return s3_client

def get_pg_connection():
    """Connect to PostgreSQL"""
    conn = psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ.get("POSTGRES_DB", "postgres"),
        user=os.environ.get("POSTGRES_USER", "postgresadmin"),
        password=os.environ.get("POSTGRES_PASSWORD", "postgresadmin")
    )
    return conn

def list_minio_files(s3_client, bucket='stock-data'):
    """List all files in MinIO bucket"""
    objects = []
    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket)
        
        for page in pages:
            if 'Contents' in page:
                objects.extend(page['Contents'])
        
        return objects
    except Exception as e:
        logger.error(f"Error listing MinIO objects: {e}")
        return []

def load_and_insert_data():
    """Load data from MinIO and insert into PostgreSQL"""
    s3_client = get_minio_connection()
    pg_conn = get_pg_connection()
    cursor = pg_conn.cursor()
    
    # First, make sure the stock_data table exists
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS stock_data (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10),
        timestamp TIMESTAMP,
        open FLOAT,
        high FLOAT,
        low FLOAT,
        close FLOAT,
        volume FLOAT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, timestamp)
    );
    """
    cursor.execute(create_table_sql)
    
    # Create index if not exists
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_stock_symbol_timestamp 
    ON stock_data(symbol, timestamp);
    """)
    
    # Also create the v2 table since the DAG might be using it
    create_v2_table_sql = """
    CREATE TABLE IF NOT EXISTS stock_data_v2 (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10),
        timestamp TIMESTAMP,
        timeframe VARCHAR(10),
        open FLOAT,
        high FLOAT,
        low FLOAT,
        close FLOAT,
        volume FLOAT,
        sma_20 FLOAT,
        sma_50 FLOAT,
        sma_200 FLOAT,
        daily_return FLOAT,
        volatility_10d FLOAT,
        volume_change FLOAT,
        rs_50 FLOAT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, timestamp, timeframe)
    );
    """
    cursor.execute(create_v2_table_sql)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_stock_v2_symbol_ts_tf 
    ON stock_data_v2(symbol, timestamp, timeframe);
    """)
    
    # Get list of files
    files = list_minio_files(s3_client)
    logger.info(f"Found {len(files)} files in MinIO")
    
    # Process files
    for i, file_obj in enumerate(files):
        try:
            key = file_obj['Key']
            # Only process CSV files
            if not key.endswith('.csv'):
                continue
                
            # Parse symbol and timeframe from path
            parts = key.split('/')
            if len(parts) < 2:
                continue
                
            symbol = parts[0]
            timeframe = parts[1] if len(parts) > 1 else 'daily'
            
            logger.info(f"Processing file {i+1}/{len(files)}: {key}")
            
            # Get file from MinIO
            response = s3_client.get_object(Bucket='stock-data', Key=key)
            df = pd.read_csv(io.BytesIO(response['Body'].read()))
            
            if df.empty:
                logger.warning(f"Empty data file: {key}")
                continue
            
            # Make sure timestamp is in the right format
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Make sure symbol column exists
            if 'symbol' not in df.columns:
                df['symbol'] = symbol
            
            # Make sure timeframe column exists
            if 'timeframe' not in df.columns:
                df['timeframe'] = timeframe
            
            # Prepare data for stock_data table
            data_tuples = []
            for _, row in df.iterrows():
                data_tuples.append((
                    row['symbol'],
                    row['timestamp'],
                    float(row['open']) if 'open' in row and pd.notna(row['open']) else None,
                    float(row['high']) if 'high' in row and pd.notna(row['high']) else None,
                    float(row['low']) if 'low' in row and pd.notna(row['low']) else None,
                    float(row['close']) if 'close' in row and pd.notna(row['close']) else None,
                    float(row['volume']) if 'volume' in row and pd.notna(row['volume']) else None
                ))
            
            # Insert into stock_data
            if data_tuples:
                insert_sql = """
                INSERT INTO stock_data (symbol, timestamp, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, timestamp) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume;
                """
                execute_batch(cursor, insert_sql, data_tuples)
                
                # Also insert into stock_data_v2
                data_tuples_v2 = []
                for _, row in df.iterrows():
                    # Add extra fields for v2 table
                    data_tuples_v2.append((
                        row['symbol'],
                        row['timestamp'],
                        timeframe,
                        float(row['open']) if 'open' in row and pd.notna(row['open']) else None,
                        float(row['high']) if 'high' in row and pd.notna(row['high']) else None,
                        float(row['low']) if 'low' in row and pd.notna(row['low']) else None,
                        float(row['close']) if 'close' in row and pd.notna(row['close']) else None,
                        float(row['volume']) if 'volume' in row and pd.notna(row['volume']) else None
                    ))
                
                insert_v2_sql = """
                INSERT INTO stock_data_v2 (symbol, timestamp, timeframe, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, timestamp, timeframe) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume;
                """
                execute_batch(cursor, insert_v2_sql, data_tuples_v2)
                
            # Commit every 10 files to avoid long transactions
            if i % 10 == 0:
                pg_conn.commit()
                
            logger.info(f"Inserted {len(data_tuples)} rows for {symbol} ({timeframe})")
            
        except Exception as e:
            logger.error(f"Error processing file {file_obj.get('Key', 'unknown')}: {e}")
            pg_conn.rollback()  # Rollback on error
    
    # Final commit
    pg_conn.commit()
    
    # Check counts
    cursor.execute("SELECT COUNT(*) FROM stock_data")
    count = cursor.fetchone()[0]
    logger.info(f"Total rows in stock_data table: {count}")
    
    cursor.execute("SELECT COUNT(*) FROM stock_data_v2")
    count = cursor.fetchone()[0]
    logger.info(f"Total rows in stock_data_v2 table: {count}")
    
    cursor.close()
    pg_conn.close()
    logger.info("Data transfer completed successfully!")

if __name__ == "__main__":
    load_and_insert_data()

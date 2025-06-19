import os
import sys
import psycopg2
import boto3
from datetime import datetime

def check_postgres():
    """Check PostgreSQL database for stock data"""
    try:
        print("Checking PostgreSQL connection...")
        conn = psycopg2.connect(
            host=os.environ.get("POSTGRES_HOST", "postgres"),
            port=os.environ.get("POSTGRES_PORT", "5432"),
            dbname=os.environ.get("POSTGRES_DB", "postgres"),
            user=os.environ.get("POSTGRES_USER", "postgresadmin"),
            password=os.environ.get("POSTGRES_PASSWORD", "postgresadmin")
        )
        
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema='public'
        """)
        tables = cursor.fetchall()
        print(f"Found tables: {[t[0] for t in tables]}")
        
        # Check stock data
        try:
            cursor.execute("SELECT COUNT(*) FROM stock_data")
            count = cursor.fetchone()[0]
            print(f"Stock data count: {count}")
            
            if count > 0:
                cursor.execute("""
                    SELECT symbol, COUNT(*) as cnt
                    FROM stock_data
                    GROUP BY symbol
                    ORDER BY cnt DESC
                """)
                symbol_counts = cursor.fetchall()
                print("Data by symbol:")
                for symbol, cnt in symbol_counts:
                    print(f"  - {symbol}: {cnt} records")
                
                # Check time range of data
                cursor.execute("""
                    SELECT 
                        symbol, 
                        MIN(timestamp) as earliest, 
                        MAX(timestamp) as latest,
                        MAX(timestamp) - MIN(timestamp) as time_range
                    FROM stock_data
                    GROUP BY symbol
                    ORDER BY symbol
                """)
                time_ranges = cursor.fetchall()
                print("\nTime range of data:")
                for row in time_ranges:
                    print(f"  {row[0]}: {row[1]} to {row[2]} (span: {row[3]})")
                
                # Sample data
                cursor.execute("""
                    SELECT symbol, timestamp, open, high, low, close, volume
                    FROM stock_data
                    ORDER BY timestamp DESC
                    LIMIT 3
                """)
                sample = cursor.fetchall()
                print("\nSample data (newest entries):")
                for row in sample:
                    print(f"  {row[0]} at {row[1]}: Open=${row[2]:.2f}, Close=${row[5]:.2f}, Volume={int(row[6])}")
        except Exception as e:
            print(f"Error checking stock_data: {str(e)}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {str(e)}")

def check_minio():
    """Check MinIO for stock data"""
    try:
        print("\nChecking MinIO connection...")
        s3_client = boto3.client(
            's3',
            endpoint_url=f'http://{os.environ.get("MINIO_HOST", "minio")}:{os.environ.get("MINIO_PORT", "9000")}',
            aws_access_key_id=os.environ.get('MINIO_ROOT_USER', 'minioadmin'),
            aws_secret_access_key=os.environ.get('MINIO_ROOT_PASSWORD', 'minioadmin'),
        )
        
        # List buckets
        buckets = s3_client.list_buckets()
        print(f"Found buckets: {[b['Name'] for b in buckets['Buckets']]}")
        
        # Check stock-data bucket
        try:
            response = s3_client.list_objects(Bucket='stock-data')
            if 'Contents' in response:
                print(f"Found {len(response['Contents'])} objects in stock-data bucket")
                
                # Group by symbol
                symbols = {}
                for obj in response['Contents']:
                    key = obj['Key']
                    parts = key.split('/')
                    if len(parts) > 1:
                        symbol = parts[0]
                        if symbol not in symbols:
                            symbols[symbol] = []
                        symbols[symbol].append(obj)
                
                # Print summary by symbol
                for symbol, objs in symbols.items():
                    print(f"  - {symbol}: {len(objs)} files, {sum(o['Size'] for o in objs)} bytes total")
                    # Show the most recent file
                    latest = sorted(objs, key=lambda x: x['LastModified'], reverse=True)[0]
                    print(f"    Latest: {latest['Key']} ({latest['LastModified']})")
            else:
                print("No objects found in stock-data bucket")
        except Exception as e:
            print(f"Error listing objects in stock-data bucket: {str(e)}")
        
    except Exception as e:
        print(f"Error connecting to MinIO: {str(e)}")

def check_logs():
    """Check log files"""
    print("\nChecking log files...")
    log_files = [
        "log_management/storage/minio.log",
        "log_management/system/dags.log",
        "log_management/airflow/stock_data_pipeline.log"
    ]
    
    # Check if log_management directory exists
    if not os.path.exists("log_management"):
        print("Log management directory not found. Run './manage.sh logs' to set it up.")
        return
    
    for log_file in log_files:
        if os.path.exists(log_file):
            size = os.path.getsize(log_file)
            print(f"{log_file}: {size} bytes")
            
            # Show last few lines if file has content
            if size > 0:
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    print(f"  Last 3 lines:")
                    for line in lines[-3:]:
                        print(f"    {line.strip()}")
        else:
            print(f"{log_file}: Not found")
    
    # Show total log sizes by component
    print("\nLog sizes by component:")
    for component in os.listdir("log_management"):
        component_dir = os.path.join("log_management", component)
        if os.path.isdir(component_dir):
            total_size = sum(os.path.getsize(os.path.join(component_dir, f)) 
                          for f in os.listdir(component_dir) 
                          if os.path.isfile(os.path.join(component_dir, f)))
            print(f"  {component}: {total_size} bytes")

if __name__ == "__main__":
    print(f"=== Data Check Report ({datetime.now()}) ===")
    check_postgres()
    check_minio()
    check_logs()
    print(f"=== Check completed at {datetime.now()} ===")

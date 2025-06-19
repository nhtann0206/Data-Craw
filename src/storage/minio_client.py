import boto3
from botocore.exceptions import ClientError
import json
import os
import io
import pandas as pd

from src.utils.logger import Logger
from src.config.settings import AppConfig

logger = Logger(name="minio",
                log_file="logs/storage.log").get_logger()

class MinIOClient():
    def __init__(self, host, port, access_key, secret_key):
        endpoint = f"http://{host}:{port}"
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.client = None

    def connect(self):
        """
            Function connecting to MinIO
        """
        try:
            self.client = boto3.client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )
            logger.info("Success connecting to MinIO.")
        except ClientError as e:
            logger.error(f"Error connecting to MinIO: {e}.")
            print(f"Error connecting to MinIO: {e}")

    def check_bucket_exists(self, bucket: str) -> bool:
        """
            Function check bucket exists
            
            Args:
                bucket (str): name of the bucket to check
            Returns:
                out (bool): True if bucket exists, False otherwise
        """
        try:
            self.client.head_bucket(Bucket=bucket)
            logger.info(f"Bucket {bucket} already exists ")
            return True
        except ClientError as e:
            logger.warning(f"Bucket {bucket} does not exist")
            print(f"Bucket {bucket} does not exist")
            return False

    def get_object(self, bucket: str, key: str):
        """
            Function get object from bucket
            
            Args:
                bucket (str): name bucket
                key (str): name object
            Returns:
                out (object): data object
        """
        try:
            response = self.client.get_object(Bucket=bucket, Key=key)
            data = response['Body'].read()
            logger.info(f"Object {key} retrieved from bucket {bucket}")
            return data
        except ClientError as e:
            logger.error(f"Error retrieving object {key} from bucket {bucket}: {e}")

    def create_bucket(self, bucket: str):
        """
            Function create bucket

            Args:
                bucket (str): name bucket need create
            Returns:
                None
        """
        try:
            self.client.create_bucket(Bucket=bucket)
            logger.info(f"Bucket {bucket} created")
        except:
            logger.error(f"Error creating bucket {bucket}")

    def insert(self, bucket: str, key: str, data):
        """
            Function insert data to bucket
            
            Args:
                bucket (str): name bucket
                key (str): name object
                data (str): data object
            Returns:
                None
        """
        if self.check_bucket_exists(bucket):
            try:
                fileobj = self.transform_to_fileobj(data)
                self.client.upload_fileobj(fileobj, bucket, key)
                logger.info(f"Object {key} uploaded to bucket {bucket}")
            except ClientError as e:
                logger.error(f"Error uploading object {key} to bucket {bucket}: {e}")
        else:
            self.create_bucket(bucket)
            self.insert(bucket, key, data)

    def transform_to_fileobj(self, data):
        """
            Function transform data to object
            
            Args:
                data (str): data need transform
            Returns:
                out (object): data object
        """
        if hasattr(data, "read"):
            return data
        
        if isinstance(data, bytes):
            return io.BytesIO(data)
        
        if isinstance(data, str):
            return io.BytesIO(data.encode("utf-8"))
        
        if isinstance(data, (dict, list)):
            json_str = json.dumps(data)
            return io.BytesIO(json_str.encode("utf-8"))
        
        if isinstance(data, pd.DataFrame):
            buf = io.BytesIO()
            data.to_csv(buf, index=False)
            buf.seek(0)
            return buf
    
    def get_list_objects(self, bucket: str, prefix: str = ""):
        """
            Function get list objects in bucket
            
            Args:
                bucket (str): name bucket
                prefix (str): prefix of object
            Returns:
                out (list): list objects in bucket
        """
        try:
            paginator = self.client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix)
            objects = []
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects.append(obj['Key'])
            logger.info(f"Listed {len(objects)} objects in bucket {bucket} with prefix {prefix}")
            return objects
        except ClientError as e:
            logger.error(f"Error listing objects in bucket {bucket}: {e}")
        
if __name__ == "__main__":
    from src.config.settings import AppConfig
    from src.ingestion.coingecko_ingestor import CoinGeckoIngestor
    from datetime import datetime
    config = AppConfig()
    s3 = MinIOClient(host=config.minio_host,
                     port=config.minio_port,
                     access_key=config.minio_access_key,
                     secret_key=config.minio_secret_key)
    s3.connect()
    data = "Hello, World!"
    s3.insert("data-raw", "input/test.txt", data)
    s3.insert("data-raw", "input/test.json", {"key": "value"})
    objects = s3.get_list_objects("data-raw", "input/")
    ingestor = CoinGeckoIngestor(coin_id='bitcoin', vs_currency='usd')
    price_data = ingestor.get_price()
    now = datetime.now()
    date = now.strftime("%Y-%m-%d")
    time = now.strftime("%H-%M-%S")
    s3.insert("coingecko-data", f"BITCOIN/{date}/{time}.json", price_data)
    print(objects)

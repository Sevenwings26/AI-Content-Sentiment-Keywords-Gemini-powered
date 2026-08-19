# app/connectors/s3_connector.py
import uuid
import boto3
from typing import Generator, Dict, Any, Optional
from app.connectors.base import BaseConnector, RawDocument

class S3Connector(BaseConnector):
    """
    Connector for streaming objects from AWS S3 buckets.
    """
    def __init__(self, connection_config: Dict[str, Any]):
        self.bucket_name = connection_config.get("bucket_name")
        self.prefix = connection_config.get("prefix", "")
        
        aws_access_key = connection_config.get("aws_access_key_id")
        aws_secret_key = connection_config.get("aws_secret_access_key")
        region = connection_config.get("region_name", "us-east-1")
        
        if aws_access_key and aws_secret_key:
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                region_name=region
            )
        else:
            self.s3_client = boto3.client("s3", region_name=region)

    def fetch_documents(self) -> Generator[RawDocument, None, None]:
        paginator = self.s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=self.prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                
                response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
                content_bytes = response["Body"].read()
                filename = key.split("/")[-1]
                mime_type = response.get("ContentType", "application/octet-stream")

                doc_id = str(uuid.uuid4())
                yield RawDocument(
                    doc_id=doc_id,
                    source_type="s3",
                    filename=filename,
                    content_bytes=content_bytes,
                    mime_type=mime_type,
                    metadata={
                        "s3_bucket": self.bucket_name,
                        "s3_key": key,
                        "last_modified": obj["LastModified"].isoformat()
                    }
                )

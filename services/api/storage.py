import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from packages.reconciliation.contracts import digest
from .config import settings


class EvidenceStore:
    def __init__(self):
        self.root = Path(settings.evidence_path)
        self.client = None
        if settings.storage_backend == "s3":
            self.client = boto3.client("s3", endpoint_url=settings.s3_endpoint or None, region_name=settings.s3_region)
        else:
            self.root.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes) -> str:
        key = digest(data)
        if self.client:
            options = {"Bucket": settings.s3_bucket, "Key": key, "Body": data,
                       "IfNoneMatch": "*", "Metadata": {"sha256": key}}
            if settings.s3_object_lock:
                options.update(ObjectLockMode="COMPLIANCE", ObjectLockRetainUntilDate=
                               datetime.now(timezone.utc) + timedelta(days=settings.s3_retention_days))
            try:
                self.client.put_object(**options)
            except ClientError as error:
                if error.response["Error"]["Code"] != "PreconditionFailed":
                    raise
        else:
            try:
                with (self.root / key).open("xb") as stream:
                    stream.write(data)
            except FileExistsError:
                pass
        if self.get(key) != data:
            raise ValueError("Evidence storage integrity failure")
        return key

    def get(self, key: str) -> bytes:
        if not re.fullmatch("[a-f0-9]{64}", key):
            raise ValueError("Invalid evidence identifier")
        if self.client:
            data = self.client.get_object(Bucket=settings.s3_bucket, Key=key)["Body"].read()
        else:
            data = (self.root / key).read_bytes()
        if digest(data) != key:
            raise ValueError("Evidence hash mismatch")
        return data

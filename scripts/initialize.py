import time

from alembic import command
from alembic.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError
from services.api.config import settings
from services.api.storage import EvidenceStore


def initialize():
    settings.check()
    command.upgrade(Config("alembic.ini"), "head")
    if settings.storage_backend == "s3":
        store = EvidenceStore()
        for attempt in range(20):
            try:
                store.client.head_bucket(Bucket=settings.s3_bucket)
                break
            except ClientError as error:
                if settings.app_mode != "demo" or error.response["Error"]["Code"] not in {"404", "NoSuchBucket"}:
                    raise
                store.client.create_bucket(Bucket=settings.s3_bucket, ObjectLockEnabledForBucket=True)
                break
            except EndpointConnectionError:
                if attempt == 19:
                    raise
                time.sleep(2)
    if settings.app_mode == "demo":
        from .seed import seed
        seed()


if __name__ == "__main__":
    initialize()

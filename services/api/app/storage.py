import os
from .config import DATA_DIR, STORAGE

def client():
    import boto3
    return boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT"), aws_access_key_id=os.getenv("S3_ACCESS_KEY"), aws_secret_access_key=os.getenv("S3_SECRET_KEY"))
def bucket(): return os.getenv("S3_BUCKET", "memoryvault")
def local_path(key):
    root = (DATA_DIR / "objects").resolve()
    path = (root / key).resolve()
    if not path.is_relative_to(root): raise ValueError("Invalid object key")
    return path
def put(key, data):
    if STORAGE == "s3": client().put_object(Bucket=bucket(), Key=key, Body=data, ContentType="application/octet-stream")
    else:
        path = local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
def get(key):
    if STORAGE == "s3": return client().get_object(Bucket=bucket(), Key=key)["Body"].read()
    return local_path(key).read_bytes()
def delete(key):
    if not key: return
    preview_path(key).unlink(missing_ok=True)
    if STORAGE == "s3": client().delete_object(Bucket=bucket(), Key=key)
    else: local_path(key).unlink(missing_ok=True)


def preview_path(key):
    root = (DATA_DIR / "previews").resolve()
    path = (root / (key + ".pdf")).resolve()
    if not path.is_relative_to(root): raise ValueError("Invalid preview key")
    return path

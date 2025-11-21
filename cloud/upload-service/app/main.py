from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import os
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI"}


def _get_env(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


_S3_ENDPOINT_URL = _get_env("S3_ENDPOINT_URL", "http://minio:9000")
_S3_BUCKET = _get_env("S3_BUCKET", "data")

_s3 = boto3.client(
    "s3",
    endpoint_url=_S3_ENDPOINT_URL,
    aws_access_key_id=_get_env("AWS_ACCESS_KEY_ID", "minioadmin"),
    aws_secret_access_key=_get_env("AWS_SECRET_ACCESS_KEY", "mySuperSecret"),
)


def _ensure_bucket_once(bucket: str):
    try:
        _s3.head_bucket(Bucket=bucket)
    except ClientError:
        try:
            _s3.create_bucket(Bucket=bucket)
        except ClientError as e:
            raise HTTPException(status_code=500, detail=f"Failed to create bucket {bucket}: {str(e)}")


_ensure_bucket_once(_S3_BUCKET)


def _parse_time_parts(time_str: str):
    if "p" in time_str:
        time_str = time_str.replace("p", ".")
    if "." in time_str:
        return datetime.strptime(time_str, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=timezone.utc)
    else:
        return datetime.strptime(time_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)

def _to_object_key(filename: str):
    split = filename.split("_")

    base = "_".join(split[:-2])
    start_dt = _parse_time_parts(split[-2])
    key_prefix = base + "/" + start_dt.strftime("%Y/%m/%d/")

    new_filename = "_".join(split[-2:])

    object_key = key_prefix + new_filename
    return object_key

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    # Read file into memory or stream; we'll stream via upload_fileobj
    try:
        object_key = _to_object_key(file.filename)
        print(f"object_key: {object_key}", flush=True)
        _s3.upload_fileobj(file.file, _S3_BUCKET, object_key)
        return JSONResponse({"status": "ok", "bucket": _S3_BUCKET, "key": object_key})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

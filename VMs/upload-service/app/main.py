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


def _parse_name_parts(filename: str):
    """Extract prefix and start timestamp from filenames like
    {prefix}_{YYYYMMDDTHHMMSS}p{MS}Z.ext or {prefix}_audio_... formats.
    Returns (prefix, dt_utc, name_root) where name_root is the baseline
    timestamp string without extension.
    """
    print(f"filename: {filename}", flush=True)
    base = os.path.basename(filename)
    print(f"base: {base}", flush=True)
    name, _ext = os.path.splitext(base)
    parts = name.split("_")
    print(f"parts: {parts}", flush=True)
    if len(parts) < 2:
        return None, None, None
    # prefix could include multiple underscores except the last time part
    # Assume time-like string at the end contains 'T' and possibly 'p'
    time_part = parts[-1]
    prefix = "_".join(parts[:-1])
    # Allow optional trailing 'Z' in original name root
    raw = time_part
    # Strip trailing 'Z' (Zulu) if present; Postman/uploads may include it in the base name
    if raw.endswith("Z"):
        raw = raw[:-1]
    # Convert pMS to .MS
    raw = raw.replace("p", ".")
    try:
        dt = datetime.strptime(raw, "%Y%m%dT%H%M%S.%f").replace(tzinfo=timezone.utc)
        # reconstruct canonical name root used for object key filename
        name_root = dt.strftime("%Y%m%dT%H%M%S") + "p" + str(dt.microsecond // 1000).zfill(3) + "Z"
        return prefix, dt, name_root
    except Exception:
        # try whole-second format (no milliseconds)
        try:
            dt = datetime.strptime(raw, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
            name_root = dt.strftime("%Y%m%dT%H%M%S") + "p000Z"
            return prefix, dt, name_root
        except Exception:
            return None, None, None


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    # Read file into memory or stream; we'll stream via upload_fileobj
    try:
        prefix, dt_utc, name_root = _parse_name_parts(file.filename)
        if prefix is None or dt_utc is None:
            raise HTTPException(status_code=400, detail="Filename must include timestamp suffix '..._YYYYMMDDTHHMMSSpMSZ.ext'")

        # Build key: {prefix}/YYYY/MM/DD/HH/MM/{name_root}
        key_prefix = f"{prefix}/" + dt_utc.strftime("%Y/%m/%d/%H/%M/")
        object_key = key_prefix + name_root

        # Stream to S3
        _s3.upload_fileobj(file.file, _S3_BUCKET, object_key)
        return JSONResponse({"status": "ok", "bucket": _S3_BUCKET, "key": object_key})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

import os
import socket
import uuid
from datetime import datetime, timezone

import boto3
from flask import Flask, abort, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

REGION = os.environ.get("AWS_REGION", "us-east-1")
TABLE_NAME = os.environ["TABLE_NAME"]
BUCKET = os.environ["BUCKET_NAME"]

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)
s3 = boto3.client("s3", region_name=REGION)


@app.route("/")
def index():
    items = table.scan().get("Items", [])
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return render_template("index.html", items=items, host=socket.gethostname())


@app.route("/add", methods=["POST"])
def add():
    title = request.form.get("title", "").strip()
    if not title:
        abort(400, "Название обязательно")

    try:
        cooking_time = int(request.form.get("cooking_time", ""))
        if cooking_time < 1:
            raise ValueError
    except ValueError:
        abort(400, "Укажите корректное время приготовления")

    item = {
        "id": str(uuid.uuid4()),
        "title": title,
        "description": request.form.get("description", "").strip(),
        "cooking_time": cooking_time,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    f = request.files.get("file")
    if f and f.filename:
        safe_name = secure_filename(f.filename) or "file"
        key = f"uploads/{item['id']}/{safe_name}"
        s3.upload_fileobj(
            f, BUCKET, key,
            ExtraArgs={"ContentType": f.content_type or "application/octet-stream"},
        )
        item["file_key"] = key
        item["file_name"] = f.filename

    table.put_item(Item=item)
    return redirect(url_for("index"))


@app.route("/file/<item_id>")
def get_file(item_id):
    item = table.get_item(Key={"id": item_id}).get("Item")
    if not item or "file_key" not in item:
        abort(404)

    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": item["file_key"]},
        ExpiresIn=300,
    )
    return redirect(url)


@app.route("/health")
def health():
    return {"status": "ok"}

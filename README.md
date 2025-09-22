Wasabi Uploader (Flask + Boto3) — README

A tiny Flask web app that uploads files from your computer to Wasabi (S3-compatible) storage and returns a 1-hour presigned download link. Designed to be beginner-friendly, Windows-friendly, and easy to drop into any Python project.

Features

Drag-and-drop + click-to-upload UI

Presigned URL (expires in 1 hour by default)

Clear startup diagnostics (endpoint, region, masked key; auth probe)

Bucket preflight + tiny diagnostic PutObject for clearer errors

Safe defaults for Wasabi (S3 path-style requests, v4 signing)

Loads config from .env (no secrets in code)

Prerequisites

Python 3.10+

A Wasabi account with an Access Key and Secret Key

A Wasabi bucket already created (note its exact name and region)

Region-specific endpoint in the form: https://s3.<region>.wasabisys.com
(e.g., Singapore ap-southeast-1 → https://s3.ap-southeast-1.wasabisys.com)

What’s in this project

app.py — the Flask app (reads config from .env)

requirements.txt — dependencies

.env.example — environment template (copy to .env and fill)

(Recommended) .gitignore — ignore .env, virtualenv, __pycache__/

Environment variables (put these in .env)

WASABI_ACCESS_KEY — your Wasabi Access Key ID

WASABI_SECRET_KEY — your Wasabi Secret Access Key

WASABI_REGION — bucket region (e.g., ap-southeast-1)

WASABI_ENDPOINT — region endpoint (e.g., https://s3.ap-southeast-1.wasabisys.com)

WASABI_BUCKET — exact bucket name (all lowercase, no spaces/underscores)

Tips
• Copy values carefully (watch O vs 0, I vs l vs 1).
• Endpoint must match the bucket’s region.
• Never commit .env. If secrets leak, rotate your keys in Wasabi.

Local setup & run

Create and activate a virtual environment.

Install dependencies from requirements.txt.

Copy .env.example to .env and fill the five variables.

Run the app.

Open http://127.0.0.1:5050, upload a file, copy the presigned URL.

If the UI doesn’t change after you edit HTML/CSS, stop the server and restart it, then hard refresh the page (Ctrl+Shift+R) or use an incognito tab.

How it works

On startup, the app:

Loads .env

Clears any ambient AWS_* variables (prevents wrong-creds surprises)

Builds a dedicated boto3 session + S3 client with path-style addressing

Prints endpoint/region/masked key and probes list_buckets() (auth check)

On upload:

Checks the target bucket (HEAD bucket) to catch region/permission/name issues

Does a tiny diagnostic PutObject (plain text) for a precise error if needed

Uploads your file to uploads/<uuid>_<filename>

Generates a presigned GET URL (default 1 hour) and shows it in the UI

Common errors & fixes
Error shown	Meaning	What to check / fix
Startup error: Missing env vars: …	.env not complete	Fill all five variables; restart the app
InvalidAccessKeyId	Keys not recognized by Wasabi	Rotate keys in Wasabi and paste cleanly into .env; verify the masked key printed at startup matches what you expect
NoSuchBucket	Name or region mismatch	Exact bucket spelling; bucket must exist in the region you set; endpoint must match region
AccessDenied	Permissions issue	Use keys from the bucket’s account, or grant at least s3:ListBucket and s3:PutObject to that bucket
AuthorizationHeaderMalformed or HTTP 301	Region mismatch	Set WASABI_REGION to the bucket’s region and use https://s3.<region>.wasabisys.com

UI uploads twice on refresh?
Implement POST→Redirect→GET (PRG) or content-hash dedupe if needed. (Ask and we’ll share a PRG variant.)

Production notes

Use a production WSGI/ASGI server behind a reverse proxy (e.g., gunicorn/uvicorn + Nginx)

Add request size limits and multipart uploads for very large files

Consider PRG flow and/or content-hash dedupe to avoid duplicate writes

Keep presigned link expiry short; prefer private buckets

Add structured logging and error monitoring

Maintenance

Keep boto3, botocore, Flask, and python-dotenv updated together

Rotate access keys periodically

Review bucket policies and access logs

FAQ

Q: Do I need AWS CLI or AWS accounts?
A: No—Wasabi is S3-compatible, and this app uses Boto3 directly with your Wasabi keys.

Q: Can I change the presigned URL expiry?
A: Yes—adjust the expiry seconds when generating the presigned URL.

Q: How do I upload huge files?
A: Switch to multipart uploads and a streamed hash; add progress UI as needed.
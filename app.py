# app.py — Wasabi single-file uploader (forced session, path-style, deep debug)
# 1) pip install boto3 flask
# 2) Fill CONFIG section (use freshly rotated keys)
# 3) python app.py → http://127.0.0.1:5050

import os
import uuid
from flask import Flask, request, render_template_string
from werkzeug.utils import secure_filename
import boto3
from boto3.session import Session
from botocore.client import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv


load_dotenv()

# 2) Helper to read & trim env vars
def _env(name: str, required: bool = True, default: str | None = None) -> str | None:
    v = os.getenv(name, default)
    if v is None:
        return None
    v = v.strip()
    return v if v else None  # empty -> None
# ==== CONFIG — FILL THESE EXACTLY (rotate your keys first) ===================
WASABI_ACCESS_KEY = _env("WASABI_ACCESS_KEY")
WASABI_SECRET_KEY = _env("WASABI_SECRET_KEY")
WASABI_REGION     = _env("WASABI_REGION")
WASABI_ENDPOINT   = _env("WASABI_ENDPOINT")
WASABI_BUCKET     = _env("WASABI_BUCKET") 
# ============================================================================

# Remove any ambient AWS configuration that could override ours
for k in [
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "AWS_PROFILE", "AWS_DEFAULT_REGION", "AWS_REGION",
    "AWS_SHARED_CREDENTIALS_FILE", "AWS_CONFIG_FILE"
]:
    os.environ.pop(k, None)

def _mask(k: str) -> str:
    return f"{k[:4]}..{k[-4:]}" if k and len(k) > 8 else (k or "")

# Build a dedicated session so nothing else leaks in
session: Session = boto3.session.Session(
    aws_access_key_id=WASABI_ACCESS_KEY.strip(),
    aws_secret_access_key=WASABI_SECRET_KEY.strip(),
    region_name=WASABI_REGION.strip(),
)
s3 = session.client(
    "s3",
    endpoint_url=WASABI_ENDPOINT.strip(),
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)

# --- Startup auth doctor (run once) ---
print("DEBUG endpoint host:", getattr(s3, "_endpoint", None).host, flush=True)
print("DEBUG region:", WASABI_REGION, flush=True)
print("DEBUG access key:", _mask(WASABI_ACCESS_KEY), "len:", len(WASABI_ACCESS_KEY), flush=True)
print("DEBUG secret len:", len(WASABI_SECRET_KEY), flush=True)

def _err_text(e: ClientError) -> str:
    try:
        code = e.response.get("Error", {}).get("Code")
        msg = e.response.get("Error", {}).get("Message")
        return f"{code}: {msg}"
    except Exception:
        return str(e)

def auth_ok() -> tuple[bool, str | None]:
    try:
        s3.list_buckets()
        print("DEBUG AUTH: OK (keys recognized by Wasabi)", flush=True)
        return True, None
    except ClientError as e:
        msg = _err_text(e)
        print("DEBUG AUTH: FAILED ->", msg, flush=True)
        return False, msg

def preflight_bucket() -> str | None:
    try:
        s3.head_bucket(Bucket=WASABI_BUCKET)
        print("DEBUG head_bucket OK for", WASABI_BUCKET, flush=True)
        return None
    except ClientError as e:
        err = _err_text(e)
        print("DEBUG head_bucket error:", err, flush=True)
        if "NoSuchBucket" in err or "404" in err:
            return ("Bucket not found. Check spelling and region. "
                    f"(bucket={WASABI_BUCKET!r}, region={WASABI_REGION}, endpoint={WASABI_ENDPOINT})")
        if "AccessDenied" in err or "403" in err:
            return ("Access denied to bucket. Keys must belong to same Wasabi account and have s3:ListBucket & s3:PutObject.")
        if "AuthorizationHeaderMalformed" in err or "301" in err:
            return ("Region mismatch. Set WASABI_REGION to the bucket's region and use endpoint https://s3.<region>.wasabisys.com")
        return err

# One-time diagnostic put (tiny object) to prove PutObject works
def diag_put() -> str | None:
    test_key = f"diag/{uuid.uuid4()}.txt"
    try:
        s3.put_object(Bucket=WASABI_BUCKET, Key=test_key, Body=b"diag", ContentType="text/plain")
        print("DEBUG diag_put OK ->", test_key, flush=True)
        return None
    except ClientError as e:
        err = _err_text(e)
        print("DEBUG diag_put error:", err, flush=True)
        return err

# Run startup checks
_auth_ok, _auth_err = auth_ok()

app = Flask(__name__)

HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Wasabi Uploader (no-dup) ✨</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root{
      --bg1:#0f172a; --bg2:#111827; --card:#111827cc;
      --border:#2e3442; --text:#e5e7eb; --muted:#94a3b8;
      --brand:#22d3ee; --brand2:#a78bfa; --ok:#10b98120; --err:#ef444420;
    }
    *{box-sizing:border-box} html,body{height:100%}
    body{
      margin:0; color:var(--text); font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
      background: radial-gradient(1200px 900px at 20% 10%, #1f2937 0, transparent 60%),
                  radial-gradient(1000px 700px at 80% 0%, #0ea5e9 0, transparent 35%),
                  linear-gradient(160deg, var(--bg1), var(--bg2));
      display:flex; align-items:center; justify-content:center; padding:24px;
    }
    .wrap{width:100%; max-width:760px}
    .card{background:var(--card); backdrop-filter: blur(10px);
      border:1px solid var(--border); border-radius:18px; padding:24px; box-shadow:0 20px 60px #0007;}
    h1{margin:0 0 12px; display:flex; align-items:center; gap:12px; font-size:24px}
    .badge{display:inline-block; border:1px solid var(--border); border-radius:999px;
      padding:6px 10px; font-size:12px; color:var(--muted); background:#0b1220cc;}
    .badges{display:flex; gap:8px; flex-wrap:wrap; margin:8px 0 18px}
    .badges code{color:var(--text)}

    /* --- Dropzone (robust + modern) --- */
    .dz{
      position:relative;
      display:flex; align-items:center; justify-content:center; flex-direction:column; gap:8px;
      min-height:200px; padding:28px;
      border:2px dashed #3b4253; border-radius:16px;
      background:linear-gradient(180deg,#0b1220aa,#0b1220cc);
      box-shadow:inset 0 0 0 1px rgba(255,255,255,.03), 0 12px 30px rgba(0,0,0,.35);
      text-align:center; cursor:pointer;
      transition:border-color .15s ease, box-shadow .15s ease, background .15s ease, transform .06s ease;
    }
    .dz:hover{ border-color:#64748b; background:#0b1220ee; }
    .dz.is-drag{ border-color:#22d3ee; box-shadow:0 0 0 4px rgba(34,211,238,.25), 0 12px 30px rgba(0,0,0,.4); }
    .dz:focus-within{ outline:none; border-color:#a78bfa; box-shadow:0 0 0 4px rgba(167,139,250,.25), 0 12px 30px rgba(0,0,0,.4); }

    .dz .icon{
      width:48px; height:48px; opacity:.9; margin-bottom:6px;
      background: conic-gradient(from 210deg, var(--brand), var(--brand2));
      -webkit-mask: url('data:image/svg+xml;utf8,\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="white">\
<path d="M7 18a4 4 0 0 1 0-8 5 5 0 0 1 9.58-1.657A4.5 4.5 0 0 1 19.5 18H17M12 13v8m0-8-3 3m3-3 3 3"/></svg>') no-repeat center/contain;
              mask: url('data:image/svg+xml;utf8,\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="white">\
<path d="M7 18a4 4 0 0 1 0-8 5 5 0 0 1 9.58-1.657A4.5 4.5 0 0 1 19.5 18H17M12 13v8m0-8-3 3m3-3 3 3"/></svg>') no-repeat center/contain;
    }
    .dz h3{margin:0 0 4px; font-size:18px}
    .dz p{margin:0; color:#94a3b8; font-size:13px}
    .dz .fileinfo{margin-top:8px; font-size:13px; color:#cbd5e1}
    /* Make all inner elements ignore clicks so the whole area triggers the label */
    .dz *{pointer-events:none}

    .fileinfo{margin:10px 0 0; font-size:13px; color:#cbd5e1}
    .actions{display:flex; gap:10px; align-items:center; margin-top:16px}
    .btn{border:none; border-radius:12px; padding:10px 16px; font-weight:600; cursor:pointer;
      color:#0b1220; background: linear-gradient(135deg, var(--brand), var(--brand2));
      transition: transform .06s ease, box-shadow .2s ease; box-shadow:0 10px 30px #0005;}
    .btn[disabled]{opacity:.6; cursor:not-allowed; box-shadow:none}
    .btn:active{transform:translateY(1px)}
    .note{color:var(--muted); font-size:12px}
    .ok,.err{border-radius:12px; padding:12px 14px; margin-top:16px}
    .ok{background:var(--ok); border:1px solid #065f46}
    .err{background:var(--err); border:1px solid #7f1d1d}
    .link{word-break:break-all; margin-top:8px}
    input[type=file]{display:none}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Wasabi Uploader</h1>

      <div class="badges">
        <span class="badge"><b>Endpoint:</b> <code>{{ endpoint }}</code></span>
        <span class="badge"><b>Region:</b> <code>{{ region }}</code></span>
        <span class="badge"><b>Bucket:</b> <code>{{ bucket }}</code></span>
      </div>

      {% if startup_error %}
        <div class="err"><b>Startup error:</b> {{ startup_error }}</div>
      {% endif %}

      <form id="uploadForm" method="POST" enctype="multipart/form-data" action="{{ url_for('index') }}">
        <label id="dropzone" class="dz" for="fileInput">
          <span class="icon"></span>
          <h3>Choose a file</h3>
          <p class="note">or drag & drop here (link is presigned for 1 hour)</p>
          <div id="fileInfo" class="fileinfo"></div>
        </label>
        <input id="fileInput" type="file" name="file" required />
        <div class="actions">
          <button id="submitBtn" class="btn" type="submit" disabled>Upload</button>
        </div>
      </form>

      {% if url %}
        <div class="ok">
          <div><b>Done!</b> Temporary URL (1 hour):</div>
          <div class="link"><a href="{{ url }}" target="_blank">{{ url }}</a></div>
        </div>
      {% endif %}

      {% if error %}
        <div class="err"><b>Error:</b> {{ error }}</div>
      {% endif %}
    </div>
  </div>

  <script>
    (function(){
      const dz     = document.getElementById('dropzone');
      const input  = document.getElementById('fileInput');
      const info   = document.getElementById('fileInfo');
      const submit = document.getElementById('submitBtn');

      function prettySize(bytes){
        const u=['B','KB','MB','GB','TB']; let i=0, n=Number(bytes||0);
        while(n>=1024 && i<u.length-1){ n/=1024; i++; }
        return (n<10? n.toFixed(2): n.toFixed(1))+' '+u[i];
      }
      function showFileInfo(f){
        if(!f){ info.textContent=''; if(submit) submit.disabled=true; return; }
        info.textContent = f.name + ' • ' + prettySize(f.size) + ' • ' + (f.type || 'application/octet-stream');
        if(submit) submit.disabled=false;
      }

      // Drag & drop highlight
      ['dragenter','dragover'].forEach(ev=>{
        dz.addEventListener(ev, e=>{ e.preventDefault(); e.stopPropagation(); dz.classList.add('is-drag'); });
      });
      ['dragleave','drop'].forEach(ev=>{
        dz.addEventListener(ev, e=>{ e.preventDefault(); e.stopPropagation(); dz.classList.remove('is-drag'); });
      });
      dz.addEventListener('drop', e=>{
        const files = e.dataTransfer && e.dataTransfer.files;
        if(files && files[0]){ input.files = files; showFileInfo(files[0]); }
      });

      // File chosen via dialog
      input.addEventListener('change', ()=>{ showFileInfo(input.files && input.files[0]); });

      // Submitting state
      document.getElementById('uploadForm').addEventListener('submit', ()=>{
        if(submit){ submit.disabled=true; submit.textContent='Uploading…'; }
      });
    })();
  </script>
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def index():
    # If auth failed at startup, show that immediately
    if not _auth_ok:
        return render_template_string(
            HTML, url=None, error=None, startup_error=_auth_err,
            endpoint=getattr(s3, "_endpoint", None).host, region=WASABI_REGION, bucket=WASABI_BUCKET
        )

    url = None
    error = None

    if request.method == "POST":
        # Bucket reachable?
        pre = preflight_bucket()
        if pre:
            return render_template_string(
                HTML, url=None, error=f"Bucket check failed: {pre}", startup_error=None,
                endpoint=getattr(s3, "_endpoint", None).host, region=WASABI_REGION, bucket=WASABI_BUCKET
            )

        # Can we put a tiny object?
        d = diag_put()
        if d:
            return render_template_string(
                HTML, url=None, error=f"Diagnostic PutObject failed: {d}", startup_error=None,
                endpoint=getattr(s3, "_endpoint", None).host, region=WASABI_REGION, bucket=WASABI_BUCKET
            )

        # Real upload
        f = request.files.get("file")
        if not f:
            error = "No file selected."
        else:
            fname = secure_filename(f.filename)
            if not fname:
                error = "Invalid filename."
            else:
                key = f"uploads/{uuid.uuid4()}_{fname}"
                try:
                    f.stream.seek(0)
                    data = f.stream.read()
                    s3.put_object(
                        Bucket=WASABI_BUCKET,
                        Key=key,
                        Body=data,
                        ContentType=f.mimetype or "application/octet-stream",
                    )
                    url = s3.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": WASABI_BUCKET, "Key": key},
                        ExpiresIn=3600,
                    )
                except ClientError as e:
                    error = _err_text(e)

    return render_template_string(
        HTML,
        url=url,
        error=error,
        startup_error=None,
        endpoint=getattr(s3, "_endpoint", None).host if getattr(s3, "_endpoint", None) else WASABI_ENDPOINT,
        region=WASABI_REGION,
        bucket=WASABI_BUCKET,
    )

if __name__ == "__main__":
    # Windows: avoid port conflicts & double-binding
    app.run(host="127.0.0.1", port=5050, debug=True, use_reloader=False)

"""
Astro GO Backend Server v2
- Device pairing code flow with QR
- Token capture (user paste URL after login)
- Token refresh support
- Content API proxy for Roku channel

Usage:
    source venv/bin/activate
    python server.py
"""

import json
import uuid
import time
import io
import base64
import re
import logging
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import flask
import qrcode
import requests

# ============================================================
# Configuration
# ============================================================

HOST = "0.0.0.0"
PORT = 5050

ASTRO_OAUTH_AUTHORIZE = "https://auth.astro.com.my/oauth2/auth"
ASTRO_OAUTH_TOKEN = "https://auth.astro.com.my/oauth2/token"
ASTRO_CLIENT_ID = "com.android/example"
ASTRO_CSDS = "https://csds-astro.astro.com.my"
ASTRO_SG_HOST = "sg-sg-sg.astro.com.my"

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
log = logging.getLogger("astro-backend")

app = flask.Flask(__name__)

# In-memory device store: {device_code: {status, token, ...}}
devices = {}


# ============================================================
# Template Creation
# ============================================================

def create_default_templates(templates_dir):
    """Create default HTML templates on first run."""
    login_html = templates_dir / "login.html"
    if not login_html.exists():
        login_html.write_text('''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Astro GO - Link Your TV</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0A1628 0%, #1A3A6E 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .card { background: white; border-radius: 16px; padding: 40px; width: 100%; max-width: 440px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
        .logo { text-align: center; margin-bottom: 25px; }
        .logo h1 { color: #1A3A6E; font-size: 24px; }
        .logo .play-icon {
            width: 60px; height: 60px; background: #FFD700; border-radius: 50%;
            display: inline-flex; align-items: center; justify-content: center; margin-bottom: 10px;
        }
        .logo .play-icon::after {
            content: ""; display: block; width: 0; height: 0;
            border-style: solid; border-width: 12px 0 12px 20px;
            border-color: transparent transparent transparent #0A1628; margin-left: 4px;
        }
        .step { display: flex; gap: 12px; margin-bottom: 16px; align-items: flex-start; }
        .step-num {
            background: #FFD700; color: #0A1628; width: 28px; height: 28px;
            border-radius: 50%; display: flex; align-items: center; justify-content: center;
            font-weight: bold; font-size: 14px; flex-shrink: 0; margin-top: 2px;
        }
        .step-content { flex: 1; }
        .step-content h3 { font-size: 15px; color: #333; margin-bottom: 4px; }
        .step-content p { font-size: 13px; color: #888; line-height: 1.4; }
        .code-badge {
            text-align: center; margin: 20px 0;
            background: #f5f5f5; border-radius: 12px; padding: 16px;
        }
        .code-badge .label { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 1px; }
        .code-badge .code { font-size: 32px; font-weight: bold; color: #1A3A6E; letter-spacing: 6px; font-family: monospace; margin-top: 4px; }
        .form-group { margin-bottom: 16px; }
        label { display: block; margin-bottom: 6px; color: #666; font-size: 14px; font-weight: 500; }
        input, textarea {
            width: 100%; padding: 14px 16px; border: 2px solid #e0e0e0;
            border-radius: 10px; font-size: 14px; font-family: monospace;
            transition: border-color 0.2s; resize: vertical;
        }
        input:focus, textarea:focus { outline: none; border-color: #FFD700; }
        textarea { min-height: 80px; word-break: break-all; }
        button {
            width: 100%; padding: 14px; background: #FFD700; color: #0A1628;
            border: none; border-radius: 10px; font-size: 16px; font-weight: 600;
            cursor: pointer; transition: background 0.2s;
        }
        button:hover { background: #E6C200; }
        button:disabled { background: #ccc; cursor: not-allowed; }
        .hint { text-align: center; margin-top: 20px; color: #999; font-size: 13px; line-height: 1.5; }
        .hint a { color: #1A3A6E; font-weight: 600; }
        .trouble { margin-top: 16px; padding: 12px; background: #fff3cd; border-radius: 8px; font-size: 13px; color: #856404; display: none; }
        .trouble.show { display: block; }
        .trouble strong { display: block; margin-bottom: 4px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="logo"><div class="play-icon"></div><h1>Astro GO</h1></div>

        <div class="code-badge">
            <div class="label">Your TV Code</div>
            <div class="code">{{ code }}</div>
        </div>

        <div class="step">
            <div class="step-num">1</div>
            <div class="step-content">
                <h3>Login to Astro</h3>
                <p>Open a new tab and go to <strong>auth.astro.com.my</strong>. Sign in with your Astro ID.</p>
            </div>
        </div>

        <div class="step">
            <div class="step-num">2</div>
            <div class="step-content">
                <h3>Copy the URL</h3>
                <p>After login, the browser will try to open an app. <strong>Copy the full URL</strong> from the address bar (it starts with <code>pastro://</code> or contains <code>#access_token=</code>).</p>
            </div>
        </div>

        <div class="step">
            <div class="step-num">3</div>
            <div class="step-content">
                <h3>Paste below</h3>
                <p>Paste the full URL here and click Link Device.</p>
            </div>
        </div>

        <form id="tokenForm" action="/login/submit" method="POST">
            <input type="hidden" name="code" value="{{ code }}">
            <div class="form-group">
                <label for="pasted_url">Paste URL here:</label>
                <textarea id="pasted_url" name="pasted_url" placeholder="pastro://com.astro.astro/authn/#access_token=xxx..." required></textarea>
            </div>
            <button id="submitBtn" type="submit">🔗 Link Device</button>
        </form>

        <div id="helpBox" class="trouble">
            <strong>⚡ Can't find the URL?</strong>
            After logging in at auth.astro.com.my, the page will try to redirect to <code>pastro://...</code>. Your browser might show a popup or error. That's normal! Just copy the URL from the address bar — it contains <code>#access_token=</code>.
        </div>

        <div class="hint">
            Having trouble? <a href="#" onclick="document.getElementById('helpBox').classList.toggle('show'); return false;">Show help</a>
            <br><br>
            <small>Don't have Astro GO? <a href="https://astrogo.astro.com.my/" target="_blank">Sign up here</a></small>
        </div>
    </div>

    <script>
        document.getElementById('tokenForm').addEventListener('submit', function(e) {
            var btn = document.getElementById('submitBtn');
            btn.disabled = true;
            btn.textContent = '⏳ Linking...';
        });
    </script>
</body>
</html>''')

    success_html = templates_dir / "login_success.html"
    if not success_html.exists():
        success_html.write_text('''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Astro GO - Success</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0A1628 0%, #1A3A6E 100%);
            min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px;
        }
        .card { background: white; border-radius: 16px; padding: 40px; width: 100%; max-width: 400px; text-align: center; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
        .checkmark { width: 80px; height: 80px; background: #27ae60; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; margin-bottom: 20px; }
        .checkmark::after { content: "\\u2713"; color: white; font-size: 40px; font-weight: bold; }
        h1 { color: #1A3A6E; margin-bottom: 10px; }
        p { color: #666; margin-bottom: 5px; line-height: 1.5; }
        .hint { color: #999; font-size: 13px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="checkmark"></div>
        <h1>Login Successful!</h1>
        <p>Your Roku channel will now connect.</p>
        <p>You can close this page.</p>
        <div class="hint">Return to your TV to start browsing</div>
    </div>
</body>
</html>''')

    error_html = templates_dir / "login_error.html"
    if not error_html.exists():
        error_html.write_text('''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Astro GO - Error</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0A1628 0%, #1A3A6E 100%);
            min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px;
        }
        .card { background: white; border-radius: 16px; padding: 40px; width: 100%; max-width: 400px; text-align: center; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
        .xmark { width: 80px; height: 80px; background: #e74c3c; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; margin-bottom: 20px; }
        .xmark::after { content: "\\u2717"; color: white; font-size: 40px; font-weight: bold; }
        h1 { color: #e74c3c; margin-bottom: 10px; }
        p { color: #666; margin-bottom: 5px; line-height: 1.5; }
        .error-msg { color: #e74c3c; margin-top: 15px; font-size: 14px; background: #fef2f2; padding: 12px; border-radius: 8px; word-break: break-all; }
        .btn { display: inline-block; margin-top: 20px; padding: 12px 30px; background: #FFD700; color: #0A1628; text-decoration: none; border-radius: 10px; font-weight: 600; }
    </style>
</head>
<body>
    <div class="card">
        <div class="xmark"></div>
        <h1>Link Failed</h1>
        <p>Could not find a valid token in the URL.</p>
        <div class="error-msg">{{ error }}</div>
        <a href="/login?code={{ code }}" class="btn">Try Again</a>
    </div>
</body>
</html>''')
        log.info("Default templates created")


# ============================================================
# Helper Functions
# ============================================================

def generate_device_code():
    return uuid.uuid4().hex[:8].upper()


def create_qr_code_base64(url):
    img = qrcode.make(url, box_size=8)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def parse_token_from_url(url):
    """Extract access_token (and optionally refresh_token) from a URL
    containing fragment like #access_token=xxx&refresh_token=yyy"""
    if not url:
        return None, None, "No URL provided"

    # Try fragment first (#)
    fragment = ""
    if "#" in url:
        fragment = url.split("#", 1)[1]
    # Also try query string
    elif "access_token=" in url:
        fragment = url.split("?", 1)[1] if "?" in url else url

    if not fragment:
        return None, None, "No URL fragment found (#access_token=...). Make sure to copy the full URL after login."

    params = {}
    for pair in fragment.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            params[k.strip()] = v.strip()

    access_token = params.get("access_token")
    if not access_token:
        return None, None, "No access_token found in the URL. Please copy the full URL after login."

    refresh_token = params.get("refresh_token")
    return access_token, refresh_token, None


def refresh_access_token(refresh_token):
    """Try to refresh an access token using Astro's token endpoint."""
    try:
        resp = requests.post(
            ASTRO_OAUTH_TOKEN,
            data={
                "grant_type": "refresh_token",
                "client_id": ASTRO_CLIENT_ID,
                "refresh_token": refresh_token,
            },
            timeout=15,
            headers={"User-Agent": "AstroGoBackend/2.0"},
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("access_token"), data.get("refresh_token") or refresh_token, None
        else:
            return None, refresh_token, f"Refresh failed: {resp.status_code}"
    except Exception as e:
        return None, refresh_token, str(e)


# ============================================================
# Device Auth API
# ============================================================

@app.route("/api/device/start")
def device_start():
    """Generate a new device code and return QR data."""
    code = generate_device_code()
    # Check if we're behind a proxy (Render, etc.)
    host = flask.request.host
    scheme = flask.request.scheme

    # Render passes the original host and uses https
    login_url = f"{scheme}://{host}/login?code={code}"

    devices[code] = {
        "status": "pending",
        "created_at": time.time(),
        "access_token": None,
        "refresh_token": None,
        "email": None,
        "error": None,
    }

    qr_b64 = create_qr_code_base64(login_url)

    return flask.jsonify({
        "device_code": code,
        "login_url": login_url,
        "qr_base64": qr_b64,
        "poll_interval": 3,
        "expires_in": 600,
    })


@app.route("/api/device/status/<code>")
def device_status(code):
    """Check login status for a device code."""
    device = devices.get(code)
    if not device:
        return flask.jsonify({"status": "error", "error": "Invalid code"}), 404

    if time.time() - device["created_at"] > 600:
        device["status"] = "expired"
        return flask.jsonify({"status": "expired"})

    resp = {"status": device["status"]}
    if device["status"] == "authenticated":
        resp["access_token"] = device["access_token"]
        resp["refresh_token"] = device.get("refresh_token")
        resp["email"] = device.get("email")
    if device["status"] == "error":
        resp["error"] = device.get("error")

    return flask.jsonify(resp)


@app.route("/api/device/refresh/<code>", methods=["POST"])
def device_refresh(code):
    """Refresh the access token for a device."""
    device = devices.get(code)
    if not device:
        return flask.jsonify({"status": "error", "error": "Invalid code"}), 404

    rt = device.get("refresh_token")
    if not rt:
        return flask.jsonify({"status": "error", "error": "No refresh token"}), 400

    new_at, new_rt, err = refresh_access_token(rt)
    if err:
        return flask.jsonify({"status": "error", "error": err}), 400

    device["access_token"] = new_at
    if new_rt:
        device["refresh_token"] = new_rt  # rotated

    return flask.jsonify({
        "status": "ok",
        "access_token": new_at,
        "refresh_token": device["refresh_token"],
    })


# ============================================================
# Phone Login Page
# ============================================================

@app.route("/login")
def login_page():
    """Phone login page with instructions."""
    code = flask.request.args.get("code", "")
    if not code or code not in devices:
        return "Invalid or expired login code", 400
    return flask.render_template("login.html", code=code)


@app.route("/login/submit", methods=["POST"])
def login_submit():
    """User pastes the URL containing the token from Astro login."""
    code = flask.request.form.get("code", "")
    pasted_url = flask.request.form.get("pasted_url", "")

    if not code or code not in devices:
        return flask.jsonify({"status": "error", "error": "Invalid code"}), 400
    if not pasted_url:
        return flask.render_template("login_error.html",
            code=code,
            error="Please paste the URL from your browser after logging in.",
        )

    log.info(f"Processing token URL for code {code}")

    # Reconstruct full URL if it was split by & in form data
    # (only when extra params look like URL fragment parts)
    for key in flask.request.form:
        if key not in ("code", "pasted_url") and "=" in pasted_url.split("#")[-1]:
            pasted_url += f"&{key}={flask.request.form[key]}"

    access_token, refresh_token, error = parse_token_from_url(pasted_url)
    if error:
        log.warning(f"Token parse failed: {error}")
        return flask.render_template("login_error.html",
            code=code,
            error=error,
        )

    # Extract email from URL if present (id_token might have it)
    email = None
    if "id_token" in pasted_url:
        # Try to decode JWT id_token for email
        fragment = pasted_url.split("#", 1)[1] if "#" in pasted_url else ""
        params = dict(p.split("=", 1) for p in fragment.split("&") if "=" in p)
        id_token = params.get("id_token")
        if id_token:
            try:
                # JWT is 3 parts, payload is base64
                payload = id_token.split(".")[1]
                padding = 4 - len(payload) % 4
                if padding != 4:
                    payload += "=" * padding
                import base64 as b64
                decoded = json.loads(b64.urlsafe_b64decode(payload))
                email = decoded.get("email") or decoded.get("sub")
            except Exception:
                pass

    devices[code]["status"] = "authenticated"
    devices[code]["access_token"] = access_token
    devices[code]["refresh_token"] = refresh_token
    devices[code]["email"] = email
    log.info(f"Token captured for code {code}" +
             (f" (email: {email})" if email else ""))

    return flask.redirect(f"/login/success?code={code}")


@app.route("/login/success")
def login_success():
    code = flask.request.args.get("code", "")
    return flask.render_template("login_success.html", code=code)


# ============================================================
# Content API Proxy
# ============================================================

@app.route("/api/content/<path:path>")
def proxy_content(path):
    """Proxy content API calls from Roku to Astro GO via SessionGuard."""
    token = flask.request.headers.get("X-Access-Token")
    if not token:
        return flask.jsonify({"error": "No access token"}), 401

    try:
        sg_url = f"https://{ASTRO_SG_HOST}:9443/apiv1/content/{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "AstroGoTV/1.0",
        }

        content_resp = requests.get(sg_url, headers=headers, timeout=15, verify=False)
        log.info(f"Content proxy [{path}]: {content_resp.status_code}")

        if content_resp.status_code == 200:
            try:
                return flask.jsonify(content_resp.json())
            except Exception:
                return flask.Response(content_resp.content, content_type="application/json")
        else:
            return flask.jsonify({
                "error": f"Content fetch failed: {content_resp.status_code}",
                "detail": content_resp.text[:500],
            }), content_resp.status_code

    except Exception as e:
        log.error(f"Content proxy error: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/api/playback/<content_id>")
def proxy_playback(content_id):
    """Proxy playback request to get stream URL + DRM info."""
    token = flask.request.headers.get("X-Access-Token")
    if not token:
        return flask.jsonify({"error": "No access token"}), 401

    try:
        sg_url = f"https://{ASTRO_SG_HOST}:9443/apiv1/playback/{content_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "AstroGoTV/1.0",
        }

        resp = requests.get(sg_url, headers=headers, timeout=15, verify=False)
        log.info(f"Playback proxy [{content_id}]: {resp.status_code}")

        if resp.status_code == 200:
            try:
                return flask.jsonify(resp.json())
            except Exception:
                return flask.Response(resp.content, content_type="application/json")
        else:
            return flask.jsonify({
                "error": f"Playback fetch failed: {resp.status_code}",
                "detail": resp.text[:500],
            }), resp.status_code

    except Exception as e:
        log.error(f"Playback proxy error: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/api/health")
def health():
    return flask.jsonify({"status": "ok", "devices_active": len(devices)})


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    templates_dir = Path(__file__).parent / "templates"
    templates_dir.mkdir(exist_ok=True)

    log.info(f"Starting Astro GO Backend v2 on port {PORT}")
    log.info(f"Login URL: https://YOUR_RENDER_URL/login?code=<code>")
    log.info(f"Device API: http://YOUR_SERVER_IP:{PORT}/api/device/start")
    log.info(f"Status API: http://YOUR_SERVER_IP:{PORT}/api/device/status/<code>")

    create_default_templates(templates_dir)
    app.run(host=HOST, port=PORT, debug=False)

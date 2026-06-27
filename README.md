# Astro GO Backend — Activation Server for Roku

Pairing server for Astro GO Roku channel. User logs in on phone, pastes URL with token, Roku polls and gets the token.

## Quick Deploy

### Render (1-click)

1. Fork this repo to your GitHub
2. Go to [Render.com](https://render.com) → New Web Service
3. Connect repo → Select `astro-go-backend`
4. Settings:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn server:app --bind 0.0.0.0:$PORT --workers 2 --timeout 30`
5. Deploy!

### Manual

```bash
pip install -r requirements.txt
python server.py
```

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/device/start` | GET | Generate pairing code + QR |
| `/api/device/status/<code>` | GET | Poll for token |
| `/api/device/refresh/<code>` | POST | Refresh expired token |
| `/login?code=<code>` | GET | Phone activation page |
| `/login/submit` | POST | Paste token URL |
| `/api/content/<path>` | GET | Proxy content API |
| `/api/playback/<id>` | GET | Proxy playback info |
| `/api/health` | GET | Health check |

## Roku Flow

1. Roku calls `/api/device/start` → gets pairing code
2. User opens URL on phone → logs in at Astro → pastes URL
3. Roku polls `/api/device/status/<code>` → gets access token
4. Roku uses token to call Astro's API (via proxy or directly)
# Force deploy

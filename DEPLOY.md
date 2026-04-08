# Deployment Notes

## Fast public access from phone via Cloudflare Tunnel (free)

This is currently the most reliable temporary method in this environment.

1. Start Streamlit:

```powershell
streamlit run webapp/turbo_dashboard.py --server.port 8501
```

2. In another terminal, start Cloudflare quick tunnel:

```powershell
cloudflared tunnel --url http://localhost:8501 --no-autoupdate
```

3. Open the generated `https://*.trycloudflare.com` URL on phone.

Important:
- Link works while your machine and both processes are running.
- URL changes on every tunnel restart.

## Fast public access from phone (free)

1. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

2. Start Streamlit in one terminal:

```powershell
streamlit run webapp/turbo_dashboard.py --server.port 8501
```

3. Start LocalTunnel in another terminal:

```powershell
npx localtunnel --port 8501
```

4. Open the generated `https://*.loca.lt` URL from phone.

Important: this URL works while your local machine and both processes are running.
Note: in this network, LocalTunnel may fail because of firewall restrictions.

## Permanent free hosting (recommended)

Use Streamlit Community Cloud:

1. Create a GitHub repository and push this project.
2. Go to https://share.streamlit.io
3. Create app:
   - Repository: your repo
   - Branch: `main`
   - Main file path: `webapp/turbo_dashboard.py`
4. (Optional) add `OPENDOTA_API_KEY` in app Secrets.
5. (Strongly recommended) add Google Drive snapshot secrets in app Secrets:
   - `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON`
   - `GOOGLE_DRIVE_FOLDER_ID`
   - optional: `GOOGLE_DRIVE_SNAPSHOT_NAME`
   - optional: `GOOGLE_DRIVE_MIN_UPLOAD_INTERVAL_SECONDS`
6. (Optional) add `DATABASE_URL` only if you also want the secondary Postgres backend path.

After deploy, you get a stable public HTTPS URL accessible from phone.

Notes:
- The app now includes a multipage `Database` view for cache coverage / backlog monitoring.
- Streamlit Community Cloud still does not provide a true always-on background worker inside the app process. The `Database` page can advance the queue while open, but 24/7 cache filling still needs an external runner plus shared persistent storage.
- Streamlit Community Cloud local files are ephemeral. Without Google Drive snapshot storage or another external backend, a reboot/redeploy can wipe the local SQLite cache and force the app to rebuild match history from OpenDota.

Current deployed app:
- https://open-dota-api-kzxvl2fznpz4cwwpfk2jmp.streamlit.app/

## Dependency stability

- `requirements.txt` is pinned to exact versions.
- Keep it pinned for Streamlit Cloud. Loose `>=` ranges let cloud restarts resolve different package versions than the last working deploy.
- When upgrading dependencies, update the pins intentionally, push, and verify the deployed `Build` hash.

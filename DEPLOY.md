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

After deploy, you get a stable public HTTPS URL accessible from phone.

Current deployed app:
- https://open-dota-api-kzxvl2fznpz4cwwpfk2jmp.streamlit.app/

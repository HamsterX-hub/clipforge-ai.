# ClipForge AI

Mobile-friendly PWA frontend plus a separate FastAPI video-processing service.

## Working in this first build
- Upload a local video from Android or desktop.
- Submit clip preferences to the backend.
- Scan for high visual-change moments using a lightweight baseline heuristic.
- Render vertical, square, or landscape MP4 clips with FFmpeg.
- Poll job status and display resulting clip links.

## Not implemented yet
This is a functional first processing pass, **not yet a semantic AI clipping model**. Prompt-aware event recognition, English speech transcription/subtitles, facecam detection/layout, chat spikes, and YouTube/Twitch/Kick source/chat integrations are not active yet. Settings for these are collected but not applied by the current detector. Process only media you own or are authorized to use.

## Deploy the backend
Deploy the `backend/` folder as a Docker web service on a host with FFmpeg and persistent disk. Set `DATA_DIR` to a writable persistent directory and `CORS_ORIGINS` to your GitHub Pages origin. Free hosts may sleep and impose CPU/storage limits.

Then open the GitHub Pages site, paste the backend base URL into **Processing server URL**, upload a video, and tap **Generate clips**.

## Run locally
```bash
cd backend
pip install -r requirements.txt
# Install ffmpeg separately and ensure ffmpeg and ffprobe are on PATH.
uvicorn app:app --host 0.0.0.0 --port 8000
```

## API
- `GET /api/health`
- `POST /api/jobs` (multipart upload + settings)
- `GET /api/jobs/{id}`
- `GET /clips/{filename}`

Jobs currently live in memory; a backend restart clears job status.

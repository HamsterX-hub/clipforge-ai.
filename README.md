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


## Hybrid processing mode (v0.7)
- **Automatic:** tries the configured cloud endpoint first, then falls back to local browser processing on the device.
- **Phone only:** processes a selected video in the browser with FFmpeg.wasm.
- **Cloud only:** uploads a selected video to a compatible ClipForge API server and polls for results.
- The cloud adapter expects `GET /api/health`, `POST /api/jobs` (multipart fields: file, prompt, format, duration, quantity, captions, facecam, highlights), and `GET /api/jobs/{id}`.
- No third-party cloud provider is preconfigured or guaranteed free. A provider must be verified as genuinely no-card/free and must support this API (or have a safe adapter) before it can be advertised as connected.
- Cloud uploads send the selected video to the configured server. Only use a server you trust and media you are authorized to process. Do not enter private API keys or passwords in the public website.
- Current local and backend detectors use visual scene-change heuristics, not semantic AI. YouTube/Twitch/Kick links are still not imported as media files.

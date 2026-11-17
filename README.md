# ClipForge AI

An early automatic-highlight clipping project. The web app is a mobile-friendly PWA; the Python API accepts a video file and creates short clips from high-audio-energy moments.

## Run the API

Requirements: Python 3.10+, FFmpeg (including ffprobe).

```bash
cd backend
python -m venv .venv
# activate the environment, then:
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open `index.html` in a browser. The frontend defaults to `http://localhost:8000`. On Android, run the API on a reachable server and set the browser's `localStorage` value `clipforge_api` to that API base URL.

## Current status

- PWA frontend and upload/job/results flow.
- FastAPI job API and FFmpeg rendering.
- First-pass highlight selection based on audio energy.
- Vertical, landscape and square output.
- Stream URL ingestion, Twitch/Kick/YouTube chat, speech transcription, semantic prompt ranking, facecam-aware reframing and subtitles are **not implemented yet**. The prompt is collected for the future analysis pipeline but does not currently change scoring.

Only process videos you own or have permission to download, edit and republish. This app does not bypass platform restrictions or download third-party streams.

## Hosting note

The GitHub Pages site can serve the frontend only. The Python API must run separately on a host with FFmpeg installed and enough disk/CPU for video processing. Free hosts may sleep or impose processing limits.

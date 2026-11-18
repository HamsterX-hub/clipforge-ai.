import os, uuid, shutil, subprocess, threading
from pathlib import Path
import cv2, numpy as np
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ROOT=Path(os.getenv("DATA_DIR","data")); UPLOADS=ROOT/"uploads"; OUTPUTS=ROOT/"clips"
UPLOADS.mkdir(parents=True,exist_ok=True); OUTPUTS.mkdir(parents=True,exist_ok=True)
JOBS={}
app=FastAPI(title="ClipForge AI API",version="0.2.0")
app.add_middleware(CORSMiddleware,allow_origins=os.getenv("CORS_ORIGINS","*").split(","),allow_credentials=False,allow_methods=["*"],allow_headers=["*"])
app.mount("/clips",StaticFiles(directory=str(OUTPUTS)),name="clips")

def duration_of(path):
 p=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],capture_output=True,text=True,check=True)
 return float(p.stdout.strip())

def audio_energy(path, step_seconds=2.0):
 """Return timestamped RMS audio energy using FFmpeg; silence/no audio gives an empty list."""
 cmd=["ffmpeg","-v","error","-i",str(path),"-vn","-ac","1","-ar","8000","-f","s16le","pipe:1"]
 try:
  proc=subprocess.run(cmd,capture_output=True,check=True,timeout=900)
  samples=np.frombuffer(proc.stdout,dtype="<i2").astype(np.float32)
 except (subprocess.SubprocessError, ValueError):
  return []
 if samples.size==0: return []
 rate=8000; window=int(step_seconds*rate); scores=[]
 for start in range(0,samples.size,window):
  chunk=samples[start:start+window]
  if chunk.size:
   rms=float(np.sqrt(np.mean(chunk*chunk)))
   scores.append((start/rate,rms))
 return scores

def normalized_scores(values):
 arr=np.asarray(values,dtype=np.float32)
 if arr.size==0: return arr
 lo=float(np.percentile(arr,10)); hi=float(np.percentile(arr,95))
 if hi<=lo: return np.zeros_like(arr)
 return np.clip((arr-lo)/(hi-lo),0,1)

def candidate_starts(path,count,length,total):
 cap=cv2.VideoCapture(str(path)); fps=cap.get(cv2.CAP_PROP_FPS) or 25
 visual=[]; prev=None; n=0; step=max(1,int(fps*2))
 while True:
  ok,frame=cap.read()
  if not ok: break
  if n%step==0:
   gray=cv2.cvtColor(cv2.resize(frame,(160,90)),cv2.COLOR_BGR2GRAY)
   if prev is not None: visual.append((n/fps,float(cv2.absdiff(gray,prev).mean())))
   prev=gray
  n+=1
 cap.release()
 audio=audio_energy(path)
 if not visual and not audio: return [max(0,(total-length)/2)]
 # Align both modalities to the same two-second timeline.
 step_seconds=2.0
 ticks=np.arange(0,max(total,step_seconds),step_seconds,dtype=np.float32)
 vt=np.asarray([x[0] for x in visual],dtype=np.float32)
 vv=np.asarray([x[1] for x in visual],dtype=np.float32)
 at=np.asarray([x[0] for x in audio],dtype=np.float32)
 av=np.asarray([x[1] for x in audio],dtype=np.float32)
 vscore=np.interp(ticks,vt,vv,left=0,right=0) if len(vt) else np.zeros_like(ticks)
 ascore=np.interp(ticks,at,av,left=0,right=0) if len(at) else np.zeros_like(ticks)
 # Both audio and video contribute; if a source has no usable signal, the other still works.
 vn=normalized_scores(vscore) if len(vt) else np.zeros_like(ticks)
 an=normalized_scores(ascore) if len(at) else np.zeros_like(ticks)
 combined=(0.55*vn+0.45*an) if len(at) else vn
 ranked=sorted(zip(ticks.tolist(),combined.tolist()),key=lambda x:x[1],reverse=True)
 starts=[]
 for t,score in ranked:
  start=max(0,min(max(0,total-length),t-length*.35))
  if all(abs(start-x)>length*.8 for x in starts): starts.append(start)
  if len(starts)>=count: break
 return sorted(starts or [max(0,(total-length)/2)])

def render(job):
 src=Path(job["input"]); total=duration_of(src); length=min(job["duration"],max(5,int(total)))
 starts=candidate_starts(src,job["quantity"],length,total); made=[]
 ratios={"9:16":"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920","1:1":"scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080","16:9":"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"}
 for i,start in enumerate(starts,1):
  name=f'{job["id"]}-{i}.mp4'; dest=OUTPUTS/name
  subprocess.run(["ffmpeg","-y","-ss",str(start),"-i",str(src),"-t",str(length),"-vf",ratios[job["format"]],"-c:v","libx264","-preset","veryfast","-crf","23","-c:a","aac","-movflags","+faststart",str(dest)],capture_output=True,check=True)
  made.append({"filename":name,"url":"/clips/"+name,"start_seconds":round(start,2),"duration":length})
 return made

def process(jid):
 j=JOBS[jid]; j.update(status="processing",message="Analyzing synchronized audio energy and visual changes…")
 try: j.update(status="completed",message="Audio/video moment scan and clip rendering complete.",clips=render(j))
 except Exception as e: j.update(status="failed",message="Processing failed.",error=str(e))

@app.get("/api/health")
def health(): return {"status":"ok","service":"ClipForge AI","features":["visual-change-scoring","audio-energy-scoring","synchronized-moment-ranking"]}

@app.post("/api/jobs")
async def create_job(file:UploadFile=File(...),prompt:str=Form(""),format:str=Form("9:16"),duration:int=Form(30),quantity:int=Form(5),captions:str=Form("en"),facecam:str=Form("true"),highlights:str=Form("")):
 if not file.filename or Path(file.filename).suffix.lower() not in (".mp4",".mov",".mkv",".webm",".m4v"): raise HTTPException(400,"Upload an MP4, MOV, MKV, or WebM video.")
 if format not in ("9:16","16:9","1:1") or duration not in (15,30,60,90) or quantity not in (3,5,10): raise HTTPException(400,"Invalid clip settings.")
 jid=uuid.uuid4().hex[:12]; dest=UPLOADS/(jid+Path(file.filename).suffix.lower())
 with dest.open("wb") as out: shutil.copyfileobj(file.file,out)
 JOBS[jid]={"id":jid,"status":"queued","message":"Video uploaded; processor starting.","input":str(dest),"prompt":prompt,"format":format,"duration":duration,"quantity":quantity,"captions":captions,"facecam":facecam=="true","highlights":highlights,"clips":[]}
 threading.Thread(target=process,args=(jid,),daemon=True).start()
 return {"id":jid,"status":"queued"}

@app.get("/api/jobs/{jid}")
def get_job(jid:str):
 if jid not in JOBS: raise HTTPException(404,"Job not found.")
 j=JOBS[jid]
 return {k:j[k] for k in ("id","status","message","error","clips") if k in j}

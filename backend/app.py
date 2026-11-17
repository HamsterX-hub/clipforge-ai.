import os, uuid, shutil, subprocess, threading
from pathlib import Path
import cv2, numpy as np
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ROOT=Path(os.getenv("DATA_DIR","data")); UPLOADS=ROOT/"uploads"; OUTPUTS=ROOT/"clips"
UPLOADS.mkdir(parents=True,exist_ok=True); OUTPUTS.mkdir(parents=True,exist_ok=True)
JOBS={}
app=FastAPI(title="ClipForge AI API",version="0.1.0")
app.add_middleware(CORSMiddleware,allow_origins=os.getenv("CORS_ORIGINS","*").split(","),allow_credentials=False,allow_methods=["*"],allow_headers=["*"])
app.mount("/clips",StaticFiles(directory=str(OUTPUTS)),name="clips")

def duration_of(path):
 p=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],capture_output=True,text=True,check=True)
 return float(p.stdout.strip())

def candidate_starts(path,count,length,total):
 cap=cv2.VideoCapture(str(path)); fps=cap.get(cv2.CAP_PROP_FPS) or 25; samples=[]; prev=None; n=0; step=max(1,int(fps*2))
 while True:
  ok,frame=cap.read()
  if not ok: break
  if n%step==0:
   gray=cv2.cvtColor(cv2.resize(frame,(160,90)),cv2.COLOR_BGR2GRAY)
   if prev is not None: samples.append((n/fps,float(cv2.absdiff(gray,prev).mean())))
   prev=gray
  n+=1
 cap.release()
 if not samples: return [max(0,(total-length)/2)]
 cutoff=float(np.percentile([s for _,s in samples],80)); ranked=sorted(((t,s) for t,s in samples if s>=cutoff),key=lambda x:x[1],reverse=True); starts=[]
 for t,_ in ranked:
  start=max(0,min(max(0,total-length),t-length*.35))
  if all(abs(start-x)>length*.8 for x in starts): starts.append(start)
  if len(starts)>=count: break
 return sorted(starts or [max(0,(total-length)/2)])

def render(job):
 src=Path(job["input"]); total=duration_of(src); length=min(job["duration"],max(5,int(total))); starts=candidate_starts(src,job["quantity"],length,total); made=[]
 ratios={"9:16":"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920","1:1":"scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080","16:9":"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"}
 for i,start in enumerate(starts,1):
  name=f'{job["id"]}-{i}.mp4'; dest=OUTPUTS/name
  subprocess.run(["ffmpeg","-y","-ss",str(start),"-i",str(src),"-t",str(length),"-vf",ratios[job["format"]],"-c:v","libx264","-preset","veryfast","-crf","23","-c:a","aac","-movflags","+faststart",str(dest)],capture_output=True,check=True)
  made.append({"filename":name,"url":"/clips/"+name,"start_seconds":round(start,2),"duration":length})
 return made

def process(jid):
 j=JOBS[jid]; j.update(status="processing",message="Scanning visual changes and rendering clips…")
 try: j.update(status="completed",message="Clip rendering complete.",clips=render(j))
 except Exception as e: j.update(status="failed",message="Processing failed.",error=str(e))

@app.get("/api/health")
def health(): return {"status":"ok","service":"ClipForge AI"}
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

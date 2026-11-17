from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import uuid, shutil, subprocess, json, math

ROOT=Path(__file__).parent
DATA=ROOT/'data'; UPLOADS=DATA/'uploads'; OUTPUTS=DATA/'clips'
for p in (UPLOADS,OUTPUTS): p.mkdir(parents=True,exist_ok=True)
app=FastAPI(title='ClipForge AI API',version='0.1.0')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])
app.mount('/clips',StaticFiles(directory=OUTPUTS),name='clips')
JOBS={}

def run(cmd):
    return subprocess.run(cmd,check=True,capture_output=True,text=True)
def duration(path):
    raw=run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(path)]).stdout
    return float(json.loads(raw)['format']['duration'])
def loudness_segments(path, total, limit, count):
    # FFmpeg's 1-second RMS measurements are a lightweight first-pass highlight signal.
    raw=run(['ffmpeg','-hide_banner','-i',str(path),'-vn','-af','astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level','-f','null','-']).stderr
    vals=[]
    for line in raw.splitlines():
        if 'lavfi.astats.Overall.RMS_level=' in line:
            try: vals.append(float(line.rsplit('=',1)[1]))
            except ValueError: pass
    if not vals: return []
    floor=sorted(vals)[len(vals)//2]
    peaks=sorted(range(len(vals)),key=lambda i: vals[i]-floor,reverse=True)
    chosen=[]
    for i in peaks:
        start=max(0.0,i-limit/2); end=min(total,start+limit)
        if end-start<5: continue
        if all(abs(start-s)>limit*.7 for s,_ in chosen): chosen.append((start,end))
        if len(chosen)>=count: break
    return sorted(chosen)
def make_clip(src,out,start,end,ratio):
    if ratio=='9:16': vf="scale='if(gt(a,9/16),-2,720)':'if(gt(a,9/16),1280,-2)',crop=720:1280"
    elif ratio=='1:1': vf="crop='min(iw,ih)':'min(iw,ih)',scale=1080:1080"
    else: vf="scale=1280:-2"
    run(['ffmpeg','-y','-ss',str(start),'-i',str(src),'-t',str(end-start),'-vf',vf,'-c:v','libx264','-preset','veryfast','-crf','23','-c:a','aac','-b:a','128k','-movflags','+faststart',str(out)])
def process(job_id,path,prompt,count,max_duration,ratio):
    try:
        JOBS[job_id].update(status='processing',message='Checking video and analysing audio…')
        total=duration(path)
        if total<5: raise ValueError('Video is too short (minimum 5 seconds).')
        spans=loudness_segments(path,total,max_duration,count)
        clips=[]
        for n,(start,end) in enumerate(spans,1):
            name=f'{job_id}-clip-{n}.mp4'; out=OUTPUTS/name
            make_clip(path,out,start,end,ratio)
            clips.append({'filename':name,'url':'/clips/'+name,'start':round(start,1),'end':round(end,1)})
            JOBS[job_id]['message']=f'Created {n} of {len(spans)} clips…'
        JOBS[job_id].update(status='completed',message=f'Finished. Created {len(clips)} clips using audio-energy highlights.',clips=clips)
    except Exception as e:
        JOBS[job_id].update(status='failed',message=str(e))
@app.get('/health')
def health(): return {'ok':True,'service':'ClipForge AI','ffmpeg':shutil.which('ffmpeg') is not None}
@app.post('/jobs')
async def create_job(background:BackgroundTasks,file:UploadFile=File(...),prompt:str=Form(''),clip_count:int=Form(5),max_duration:int=Form(30),aspect_ratio:str=Form('9:16')):
    if not file.filename or Path(file.filename).suffix.lower() not in {'.mp4','.mov','.webm','.mkv','.m4v'}: raise HTTPException(400,'Upload an MP4, MOV, WebM, MKV or M4V video.')
    if not 1<=clip_count<=10 or not 10<=max_duration<=60 or aspect_ratio not in {'9:16','16:9','1:1'}: raise HTTPException(400,'Invalid clip settings.')
    jid=uuid.uuid4().hex[:12]; path=UPLOADS/(jid+Path(file.filename).suffix.lower())
    with path.open('wb') as dest: shutil.copyfileobj(file.file,dest)
    JOBS[jid]={'id':jid,'status':'queued','message':'Video uploaded. Waiting to process…','clips':[]}
    background.add_task(process,jid,path,prompt,clip_count,max_duration,aspect_ratio)
    return {'id':jid,'status':'queued'}
@app.get('/jobs/{job_id}')
def get_job(job_id:str):
    if job_id not in JOBS: raise HTTPException(404,'Job not found')
    return JOBS[job_id]

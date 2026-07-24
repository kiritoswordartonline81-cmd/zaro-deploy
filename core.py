# ⚡ ZARO DEPLOY — Core Engine vFINAL
import json,os,sys,time,threading,subprocess,socket
from pathlib import Path
import requests
BASE_DIR=Path(__file__).parent.absolute()
APPS_DIR=BASE_DIR+"/apps"
os.makedirs(APPS_DIR,exist_ok=True)
class AppDeploy:
    def __init__(self):
        self.apps={}
        self.lock=threading.Lock()
        self._load()
        threading.Thread(target=self._health,daemon=True).start()
    def _sf(self):return BASE_DIR+"/state.json"
    def _load(self):
        sf=self._sf()
        if os.path.exists(sf):
            try:
                for s,i in json.loads(open(sf).read()).items():
                    self.apps[s]=dict(slug=s,**i,proc=None,port=i.get("port"))
            except:pass
    def _save(self):
        state={}
        for s,i in self.apps.items():
            state[s]=dict(name=i.get("name"),created=i.get("created"),type=i.get("type"),status=i.get("status"),port=i.get("port"),url=i.get("url"))
        open(self._sf(),"w").write(json.dumps(state,indent=2))
    def deploy(self,slug,name,files,app_type="static"):
        with self.lock:
            d=APPS_DIR+"/"+slug;os.makedirs(d,exist_ok=True)
            for fn,ct in files.items():open(d+"/"+fn,"w").write(ct)
            prev=self.apps.get(slug,{}).get("created",str(time.time()))
            self.apps[slug]=dict(slug=slug,name=name,type=app_type,status="deployed",proc=None,port=None,url="/apps/"+slug,created=prev)
            if app_type=="python":self._launch(slug)
            self._save();return self.apps[slug]
    def _free_port(self):
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
            s.bind(("",0));return s.getsockname()[1]
    def _launch(self,slug):
        info=self.apps.get(slug)
        if not info:return
        port=self._free_port();info["port"]=port
        d=APPS_DIR+"/"+slug
        proc=subprocess.Popen([sys.executable,d+"/app.py"],env={**os.environ,"PORT":str(port)},cwd=d,stdout=open(d+"/stdout.log","w"),stderr=open(d+"/stderr.log","w"))
        info["proc"]=proc;info["status"]="running";info["pid"]=proc.pid
        time.sleep(2)
        try:
            if requests.get("http://127.0.0.1:"+str(port)+"/",timeout=3).status_code<500:info["status"]="healthy"
        except:info["status"]="starting"
    def stop(self,slug):
        with self.lock:
            info=self.apps.get(slug)
            if info and info.get("proc"):
                try:info["proc"].terminate();info["proc"].wait(timeout=5)
                except:info["proc"].kill()
                info["proc"]=None;info["status"]="stopped";self._save()
    def delete(self,slug):
        self.stop(slug)
        with self.lock:
            self.apps.pop(slug,None)
            import shutil;shutil.rmtree(APPS_DIR+"/"+slug,ignore_errors=True);self._save()
    def _health(self):
        while True:
            time.sleep(30)
            with self.lock:
                for slug,info in list(self.apps.items()):
                    if info.get("type")!="python":continue
                    proc=info.get("proc")
                    if proc and proc.poll() is not None:
                        self._launch(slug)
                    elif info.get("port"):
                        try:
                            r=requests.get("http://127.0.0.1:"+str(info["port"])+"/",timeout=2)
                            if r.status_code<500:info["status"]="healthy"
                            else:info["status"]="unhealthy"
                        except:
                            info["status"]="unhealthy"
                            if proc:
                                try:proc.kill()
                                except:pass
                            self._launch(slug)

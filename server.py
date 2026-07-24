# ⚡ ZARO DEPLOY — SINGLE FILE vFINAL
import json,os,sys,time,threading,subprocess,socket
from pathlib import Path
from flask import Flask,request,jsonify,send_from_directory
from flask_cors import CORS
import requests

BASE_DIR=Path(__file__).parent.absolute()
APPS_DIR=BASE_DIR/"apps"
APPS_DIR.mkdir(exist_ok=True)

app=Flask(__name__,static_folder=None)
CORS(app)

class AppDeploy:
    def __init__(self):
        self.apps={}
        self.lock=threading.Lock()
        self._load()
        threading.Thread(target=self._health,daemon=True).start()

    def _sf(self):return BASE_DIR/"state.json"

    def _load(self):
        sf=self._sf()
        if sf.exists():
            try:
                for s,i in json.loads(sf.read_text()).items():
                    self.apps[s]=dict(slug=s,**i,proc=None,port=i.get("port"))
            except:pass

    def _save(self):
        state={}
        for s,i in self.apps.items():
            state[s]=dict(name=i.get("name"),created=i.get("created"),type=i.get("type"),
                status=i.get("status"),port=i.get("port"),url=i.get("url"))
        self._sf().write_text(json.dumps(state,indent=2))

    def deploy(self,slug,name,files,app_type="static"):
        with self.lock:
            d=APPS_DIR/slug;d.mkdir(exist_ok=True)
            for fn,ct in files.items():(d/fn).write_text(ct)
            prev=self.apps.get(slug,{}).get("created",str(time.time()))
            self.apps[slug]=dict(slug=slug,name=name,type=app_type,status="deployed",
                proc=None,port=None,url="/apps/"+slug,created=prev)
            if app_type=="python":self._launch(slug)
            self._save();return self.apps[slug]

    def _free_port(self):
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
            s.bind(("",0));return s.getsockname()[1]

    def _launch(self,slug):
        info=self.apps.get(slug)
        if not info:return
        port=self._free_port();info["port"]=port
        d=APPS_DIR/slug
        proc=subprocess.Popen([sys.executable,str(d/"app.py")],
            env={**os.environ,"PORT":str(port)},cwd=str(d),
            stdout=open(d/"stdout.log","w"),stderr=open(d/"stderr.log","w"))
        info["proc"]=proc;info["status"]="running";info["pid"]=proc.pid
        time.sleep(2)
        try:
            if requests.get("http://127.0.0.1:"+str(port)+"/",timeout=3).status_code<500:
                info["status"]="healthy"
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
            import shutil;shutil.rmtree(APPS_DIR/slug,ignore_errors=True);self._save()

    def _health(self):
        while True:
            time.sleep(30)
            with self.lock:
                for slug,info in list(self.apps.items()):
                    if info.get("type")!="python":continue
                    proc=info.get("proc")
                    if proc and proc.poll() is not None:self._launch(slug)
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

deployer=AppDeploy()

@app.route("/")
def dashboard():
    return "<!DOCTYPE html><html><head><meta charset=UTF-8><meta name=viewport content='width=device-width,initial-scale=1.0'><title>Zaro Deploy</title><style>body{background:#050510;color:#e0e0f0;font-family:system-ui;text-align:center;padding:50px}h1{font-size:2.5rem;background:linear-gradient(135deg,#6366f1,#10b981,#f59e0b);-webkit-background-clip:text;-webkit-text-fill-color:transparent}a{color:#6366f1}</style></head><body><h1>⚡ Zaro Deploy — LIVE</h1><p>Unlimited AI PaaS · 24/7 FREE</p><p>API: <code>POST /api/deploy</code> | <code>GET /api/apps</code> | <code>GET /api/health</code></p><p><a href=/api/apps>View Apps</a> | <a href=/api/health>Health</a></p></body></html>"

@app.route("/api/apps")
def list_apps():
    return jsonify({"apps":[dict(slug=s,name=i.get("name"),type=i.get("type"),
        status=i.get("status"),url=i.get("url"),port=i.get("port"),
        created=i.get("created"))for s,i in deployer.apps.items()]})

@app.route("/api/deploy",methods=["POST"])
def deploy_app():
    data=request.json
    slug=data.get("slug","").strip().lower().replace(" ","-")
    name=data.get("name",slug)
    files=data.get("files",{})
    app_type=data.get("type","static")
    if not slug:return jsonify({"error":"Slug required"}),400
    if not files:return jsonify({"error":"No files"}),400
    return jsonify(deployer.deploy(slug,name,files,app_type))

@app.route("/api/apps/<slug>",methods=["DELETE"])
def delete_app(slug):
    deployer.delete(slug)
    return jsonify({"ok":True})

@app.route("/api/health")
@app.route("/api/status")
@app.route("/health")
def health():
    return jsonify({"status":"healthy","apps":len(deployer.apps),"platform":"Zaro Deploy Unlimited AI PaaS"})

@app.route("/apps/<slug>/",defaults={"subpath":""})
@app.route("/apps/<slug>/<path:subpath>")
def serve_app(slug,subpath):
    info=deployer.apps.get(slug)
    if not info:return "App not found",404
    if info.get("type")=="python" and info.get("port"):
        try:
            r=requests.get("http://127.0.0.1:"+str(info["port"])+"/"+subpath,timeout=10)
            return r.text,r.status_code
        except Exception as e:return "Proxy error: "+str(e),502
    app_dir=APPS_DIR/slug
    if subpath:return send_from_directory(str(app_dir),subpath)
    return send_from_directory(str(app_dir),"index.html")

if __name__=="__main__":
    port=int(os.environ.get("PORT",9000))
    print("ZARO DEPLOY — http://0.0.0.0:"+str(port))
    app.run(host="0.0.0.0",port=port,debug=False,threaded=True)

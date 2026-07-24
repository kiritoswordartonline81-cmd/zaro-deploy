"""
⚡ ZARO DEPLOY — Unlimited Free PaaS Engine
Self-healing deployment server. Host unlimited websites.
Runs on a single port. Auto-restarts crashed apps. Zero config needed.
"""
import json, os, sys, time, threading, subprocess, signal
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests

BASE_DIR = Path(__file__).parent.absolute()
APPS_DIR = BASE_DIR / "apps"
APPS_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=None)
CORS(app)

# ── App Registry ──
class AppDeploy:
    """Manages deployed apps with health checks & auto-restart"""
    
    def __init__(self):
        self.apps = {}
        self.lock = threading.Lock()
        self._load_state()
        threading.Thread(target=self._health_check_loop, daemon=True).start()
    
    def _state_file(self):
        return BASE_DIR / "state.json"
    
    def _load_state(self):
        sf = self._state_file()
        if sf.exists():
            try:
                data = json.loads(sf.read_text())
                for slug, info in data.items():
                    self.apps[slug] = {"slug": slug, **info, "proc": None, "port": None}
            except: pass
    
    def _save_state(self):
        state = {}
        for slug, info in self.apps.items():
            state[slug] = {
                "name": info.get("name"),
                "created": info.get("created"),
                "type": info.get("type"),
                "status": info.get("status"),
                "port": info.get("port"),
                "url": info.get("url"),
            }
        self._state_file().write_text(json.dumps(state, indent=2))
    
    def deploy(self, slug: str, name: str, files: dict, app_type: str = "static"):
        """Deploy a new app or update existing"""
        with self.lock:
            app_dir = APPS_DIR / slug
            app_dir.mkdir(exist_ok=True)
            
            # Write files
            for fname, content in files.items():
                (app_dir / fname).write_text(content)
            
            # Register
            self.apps[slug] = {
                "slug": slug,
                "name": name,
                "type": app_type,
                "status": "deployed",
                "proc": None,
                "port": None,
                "url": f"/apps/{slug}",
                "created": self.apps.get(slug, {}).get("created", time.strftime("%Y-%m-%d %H:%M"))
            }
            
            # Launch if Python/Flask app
            if app_type == "python":
                self._launch_python(slug)
            
            self._save_state()
            return self.apps[slug]
    
    def _launch_python(self, slug: str):
        """Launch a Python app on a dynamic port"""
        info = self.apps.get(slug)
        if not info: return
        
        # Find free port
        port = self._find_free_port()
        info["port"] = port
        
        app_dir = APPS_DIR / slug
        proc = subprocess.Popen(
            [sys.executable, str(app_dir / "app.py")],
            env={**os.environ, "PORT": str(port)},
            cwd=str(app_dir),
            stdout=open(app_dir / "stdout.log", "w"),
            stderr=open(app_dir / "stderr.log", "w"),
        )
        info["proc"] = proc
        info["status"] = "running"
        info["pid"] = proc.pid
        
        # Wait for startup
        time.sleep(2)
        try:
            r = requests.get(f"http://127.0.0.1:{port}/", timeout=3)
            if r.status_code < 500:
                info["status"] = "healthy"
        except:
            info["status"] = "starting"
    
    def _find_free_port(self):
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]
    
    def stop(self, slug: str):
        with self.lock:
            info = self.apps.get(slug)
            if info and info.get("proc"):
                try:
                    info["proc"].terminate()
                    info["proc"].wait(timeout=5)
                except:
                    info["proc"].kill()
                info["proc"] = None
                info["status"] = "stopped"
                self._save_state()
    
    def delete(self, slug: str):
        self.stop(slug)
        with self.lock:
            self.apps.pop(slug, None)
            import shutil
            shutil.rmtree(APPS_DIR / slug, ignore_errors=True)
            self._save_state()
    
    def get_proxy_url(self, slug: str, path: str = ""):
        """Get proxy URL for an app"""
        info = self.apps.get(slug)
        if info and info.get("port"):
            return f"http://127.0.0.1:{info['port']}/{path.lstrip('/')}"
        return None
    
    def _health_check_loop(self):
        """Background health checks + auto-restart"""
        while True:
            time.sleep(30)
            with self.lock:
                for slug, info in list(self.apps.items()):
                    if info.get("type") != "python": continue
                    proc = info.get("proc")
                    if proc and proc.poll() is not None:
                        # Crashed! Restart
                        print(f"✄ [{slug}] crashed — auto-restarting...")
                        self._launch_python(slug)
                    elif info.get("port"):
                        # Check health
                        try:
                            r = requests.get(f"http://127.0.0.1:{info['port']}/", timeout=2)
                            info["status"] = "healthy" if r.status_code < 500 else "unhealthy"
                        except:
                            info["status"] = "unhealthy"
                            # Auto-restart on failed health check
                            print(f"✄ [{slug}] unhealthy — auto-restarting...")
                            if proc:
                                try: proc.kill()
                                except: pass
                            self._launch_python(slug)

deployer = AppDeploy()

# ── API Routes ──
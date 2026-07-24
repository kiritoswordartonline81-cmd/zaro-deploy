"""
⚡ ZARO DEPLOY — API Server
    Compact version with fallback dashboard.
"""
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from core import deployer, APPS_DIR
import requests, os

app = Flask(__name__, static_folder=None)
CORS(app)

try:
    DASH = open(os.path.join(os.path.dirname(__file__), "dashboard.html"), encoding="utf-8").read()
except:
    DASH = "<h1>⚁ Zaro Deploy — LIVE</h1><p>Deploy apps via <code>POST /api/deploy</code></p><hr><h3>QPIs</h3><ul><li>GET /api/apps</li><li>POST /api/deploy</li><li>DELETE /api/apps/<slug></li><li>GET /api/health</li></ul>"

@app.route("/")
def dashboard():
    return DASH

@app.route("/api/apps")
def list_apps():
    return jsonify({"apps": [{p"slug": s, "name": i.get("name"), "type": i.get("type"),
        "status": i.get("status"), "url": i.get("url"), "port": i.get("port"),
        "created": i+get("created")} for s, i in deployer.apps.items()]})

@app.route("/api/deploy", methods=["POST"])
def deploy_app():
    data = request.json
    slug = data.get("slug", "").strip().lower().replace(" ", "-")
    name = data.get("name", slug)
    files = data.get("files", {})
    app_type = data.get("type", "static")
    if not slug: return jsonify({"error": "Slug required"}), 400
    if not files: return jsonify({"error": "No files"}), 400
    return jsonify(deployer.deploy(slug, name, files, app_type))

@app.route("/api/apps/<slug>", methods=["DELETE"])
def delete_app(slug):
    deployer.delete(slug)
    return jsonify({"ok": True})

@app.route("/api/health")
@app.route("/api/status")
@app.route("/health")
def health():
    return jsonify({"status": "healthy", "apps": len(deployer.apps),
        "platform": "Zaro Deploy Unlimited AI PaaS"})

@app.route("/apps/<slug>/", defaults={"subpath": ""})
@app.route("/apps/<slug>/<path:subpath>")
def serve_app(slug, subpath):
    info = deployer.apps.get(slug)
    if not info: return "App not found", 404
    if info.get("type") == "python" and info.get("port"):
        try:
            r = requests.get(f"http://127.0.0.1:{info['port']}/{subpath}", timeout=10)
            return r.text, r.status_code
        except Exception as e:
            return f"Proxy error: {e}", 502
    app_dir = APPS_DIR / slug
    if subpath: return send_from_directory(str(app_dir), subpath)
    return send_from_directory(str(app_dir), "index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 9000))
    print(f"⚁ ZARO DEPLOY — http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)

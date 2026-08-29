import os
import json
import time
from http.server import BaseHTTPRequestHandler

HTML_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "dashboard.html")
HITS_CACHE_FILE = "/tmp/hits_cache.json" if os.path.exists("/tmp") else os.path.join(os.path.dirname(__file__), "hits_cache.json")

# Bellek içi dinamik istatistik ve hit deposu
CACHE = {
    "total_hits": 0,
    "total_accs": 0,
    "total_scans": 0,
    "total_vips": 1,
    "total_admins": 1,
    "active_proxies": 25,
    "recent_hits": []
}

def load_cache():
    global CACHE
    if os.path.exists(HITS_CACHE_FILE):
        try:
            with open(HITS_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                CACHE.update(data)
        except Exception:
            pass

def save_cache():
    try:
        with open(HITS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(CACHE, f, ensure_ascii=False)
    except Exception:
        pass

load_cache()

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        load_cache()
        path = self.path.split("?")[0]

        # 1. Ana Sayfa (Web Dashboard Arayüzü)
        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            if os.path.exists(HTML_FILE):
                with open(HTML_FILE, "r", encoding="utf-8") as f:
                    content = f.read()
                self.wfile.write(content.encode("utf-8"))
            else:
                self.wfile.write(b"<h1>CPM Dashboard</h1><p>Template not found.</p>")
            return

        # 2. Canlı Sağlık ve Ping Endpoint'i (/health veya /ping)
        elif path in ("/health", "/ping", "/api/health"):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            data = {
                "status": "healthy",
                "service": "CPM Vercel Web Dashboard & API",
                "active_proxies": CACHE.get("active_proxies", 25),
                "total_hits": CACHE.get("total_hits", 0),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        # 3. İstatistik ve Hit API'si (/api/stats)
        elif path == "/api/stats":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            data = {
                "status": "success",
                "total_hits": CACHE.get("total_hits", len(CACHE["recent_hits"])),
                "total_accs": CACHE.get("total_accs", 0),
                "total_scans": CACHE.get("total_scans", 0),
                "total_vips": CACHE.get("total_vips", 1),
                "total_admins": CACHE.get("total_admins", 1),
                "active_proxies": CACHE.get("active_proxies", 25),
                "recent_hits": CACHE.get("recent_hits", [])[:20]
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        # 4. 404
        else:
            self.send_response(404)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode("utf-8"))
            return

    def do_POST(self):
        path = self.path.split("?")[0]

        # Canlı Hit & İstatistik Senkronizasyonu (/api/hit_sync)
        if path == "/api/hit_sync":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body.decode("utf-8"))
                
                # Yeni hit ekleme
                if "hits" in payload and isinstance(payload["hits"], list):
                    for h in payload["hits"]:
                        CACHE["recent_hits"].insert(0, {
                            "email": h.get("email", "Gizli"),
                            "level": h.get("cpm_level", h.get("level", 0)),
                            "total_cars": h.get("cpm_total_cars", h.get("total_cars", 0)),
                            "created_at": h.get("checked_at", time.strftime("%Y-%m-%d %H:%M:%S"))
                        })
                    # En son 50 hiti tut
                    CACHE["recent_hits"] = CACHE["recent_hits"][:50]
                    CACHE["total_hits"] = CACHE.get("total_hits", 0) + len(payload["hits"])

                # İstatistik güncelleme
                if "stats" in payload:
                    st = payload["stats"]
                    CACHE["total_accs"] = st.get("total_accs", CACHE["total_accs"])
                    CACHE["total_scans"] = st.get("total_scans", CACHE["total_scans"])
                    CACHE["active_proxies"] = st.get("active_proxies", CACHE["active_proxies"])
                    if "total_hits" in st:
                        CACHE["total_hits"] = st["total_hits"]

                save_cache()

                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "synced", "total_hits": CACHE["total_hits"]}).encode("utf-8"))
                return
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                return
        else:
            self.send_response(404)
            self.end_headers()

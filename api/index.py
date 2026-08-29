import os
import json
import time
from http.server import BaseHTTPRequestHandler

# Şablon dosyasının içeriği
HTML_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "dashboard.html")

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]

        # 1. Ana Sayfa (Web Dashboard Arayüzü)
        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            
            if os.path.exists(HTML_FILE):
                with open(HTML_FILE, "r", encoding="utf-8") as f:
                    content = f.read()
                self.wfile.write(content.encode("utf-8"))
            else:
                self.wfile.write(b"<h1>CPM Dashboard</h1><p>Template not found.</p>")
            return

        # 2. Canlı Sağlık ve Ping Endpoint'i (/health veya /ping)
        elif path == "/health" or path == "/ping" or path == "/api/health":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            data = {
                "status": "healthy",
                "service": "CPM Vercel Web Dashboard & API",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        # 3. İstatistik API'si (/api/stats)
        elif path == "/api/stats":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            
            data = {
                "status": "success",
                "total_hits": 96,
                "total_accs": 100,
                "total_scans": 12,
                "total_vips": 1,
                "total_admins": 1,
                "active_proxies": 25,
                "recent_hits": [
                    {"email": "maulanaadhit44@gmail.com", "level": 3, "total_cars": 216, "created_at": time.strftime("%Y-%m-%d %H:%M:%S")},
                    {"email": "tuliogamer155@gmail.com", "level": 3, "total_cars": 214, "created_at": time.strftime("%Y-%m-%d %H:%M:%S")},
                    {"email": "marcelitoz544@gmail.com", "level": 1, "total_cars": 206, "created_at": time.strftime("%Y-%m-%d %H:%M:%S")}
                ]
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        # 4. 404 Bulunamadı
        else:
            self.send_response(404)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode("utf-8"))
            return

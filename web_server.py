import os
import time
from aiohttp import web
from database import db
from proxy_manager import proxy_mgr
from config import BASE_DIR

START_TIME = time.time()

routes = web.RouteTableDef()

@routes.get("/")
async def handle_dashboard(request):
    html_path = os.path.join(BASE_DIR, "templates", "dashboard.html")
    if os.path.exists(html_path):
        try:
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read()
            return web.Response(text=content, content_type="text/html")
        except Exception as e:
            return web.Response(text=f"<h1>Dashboard yüklenemedi: {e}</h1>", content_type="text/html")
    return web.Response(text="<h1>Dashboard Şablonu Bulunamadı!</h1>", content_type="text/html")

@routes.get("/health")
@routes.get("/ping")
async def handle_health(request):
    uptime_sec = round(time.time() - START_TIME, 1)
    return web.json_response({
        "status": "healthy",
        "service": "CPM Bot & Web Dashboard",
        "uptime_seconds": uptime_sec,
        "active_proxies": proxy_mgr.count(),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    })

@routes.get("/api/stats")
@routes.get("/api/all_hits")
async def handle_api_stats(request):
    global_stats = await db.get_global_stats()
    all_hits = await db.get_recent_hits(limit=100)
    
    return web.json_response({
        "status": "success",
        "total_hits": global_stats.get("total_hits", 0),
        "total_accs": global_stats.get("total_accs", 0),
        "total_scans": global_stats.get("total_scans", 0),
        "total_vips": global_stats.get("total_vips", 0),
        "total_admins": global_stats.get("total_admins", 0),
        "active_proxies": proxy_mgr.count(),
        "recent_hits": all_hits
    })

@routes.get("/api/export/txt")
async def handle_export_txt(request):
    all_hits = await db.get_recent_hits(limit=500)
    lines = [f"{h.get('email')}:{h.get('password', '123456')}" for h in all_hits]
    return web.Response(
        text="\n".join(lines),
        content_type="text/plain",
        headers={"Content-Disposition": 'attachment; filename="cpm_tum_hitler.txt"'}
    )

def create_web_app() -> web.Application:
    app = web.Application()
    app.add_routes(routes)
    return app

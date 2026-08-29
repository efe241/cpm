import os
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# 🔑 DISCORD & API AUTH CONFIGURATION
# =============================================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")

# Firebase & CPM Cloud Function Endpoints
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "AIzaSyBW1ZbMiUeDZHYUO2bY8Bfnf5rRgrQGPTM")
AUTH_LOGIN_URL = f"https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword?key={FIREBASE_API_KEY}"
AUTH_LOOKUP_URL = f"https://www.googleapis.com/identitytoolkit/v3/relyingparty/getAccountInfo?key={FIREBASE_API_KEY}"
CF_BASE_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net"

# =============================================================================
# 🌐 WEB DASHBOARD & PROXY AYARLARI
# =============================================================================
DEFAULT_WEB_DASHBOARD_URL = "https://tempapims-efes-projects-602609c9.vercel.app"
WEB_DASHBOARD_URL = os.getenv("WEB_DASHBOARD_URL", DEFAULT_WEB_DASHBOARD_URL).rstrip("/")

APIFY_PROXY_URL = os.getenv("APIFY_PROXY_URL", "")
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "")
PROXY_API_URL = os.getenv("PROXY_API_URL", "")

PROXY_TEST_TIMEOUT = float(os.getenv("PROXY_TEST_TIMEOUT", 2.5))
PROXY_TEST_URL = os.getenv("PROXY_TEST_URL", "https://httpbin.org/ip")
MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", 20))
PORT = int(os.getenv("PORT", 8080))

# =============================================================================
# 🎯 KULLANICI LİMİTLERİ & ROLLER
# =============================================================================
FREE_LIMIT = int(os.getenv("FREE_LIMIT", 25))
VIP_LIMIT = int(os.getenv("VIP_LIMIT", 100))
ADMIN_LIMIT = int(os.getenv("ADMIN_LIMIT", 500))

raw_admins = os.getenv("ADMIN_USER_IDS", "1114441502039478312")
ADMIN_USER_IDS = [int(x.strip()) for x in raw_admins.split(",") if x.strip().isdigit()]

raw_vip_roles = os.getenv("VIP_ROLE_IDS", "")
VIP_ROLE_IDS = [int(x.strip()) for x in raw_vip_roles.split(",") if x.strip().isdigit()]

# =============================================================================
# 📁 DOSYA YOLLARI
# =============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
HITS_DIR = os.path.join(BASE_DIR, "hits")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
DATABASE_PATH = os.path.join(DATA_DIR, "database.sqlite")
PROXIES_FILE_PATH = os.path.join(BASE_DIR, "proxies.txt")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(HITS_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# =============================================================================
# 🌍 KÜRESEL 25+ OTOMATİK PROXY KAYNAKLARI
# =============================================================================
BUILTIN_PROXY_SOURCES = [
    {"name": "ProxyScrape HTTP", "url": "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3000&country=all&ssl=all&anonymity=all", "type": "http"},
    {"name": "ProxyScrape HTTPS", "url": "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=https&timeout=3000&country=all", "type": "https"},
    {"name": "ProxyScrape SOCKS4", "url": "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks4&timeout=3000&country=all", "type": "socks4"},
    {"name": "ProxyScrape SOCKS5", "url": "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=3000&country=all", "type": "socks5"},
    {"name": "TheSpeedX HTTP", "url": "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt", "type": "http"},
    {"name": "TheSpeedX SOCKS4", "url": "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt", "type": "socks4"},
    {"name": "TheSpeedX SOCKS5", "url": "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt", "type": "socks5"},
    {"name": "Monosans HTTP", "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt", "type": "http"},
    {"name": "Monosans SOCKS4", "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt", "type": "socks4"},
    {"name": "Monosans SOCKS5", "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt", "type": "socks5"},
    {"name": "ShiftyTR HTTP", "url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt", "type": "http"},
    {"name": "ShiftyTR HTTPS", "url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt", "type": "https"},
    {"name": "ShiftyTR SOCKS4", "url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks4.txt", "type": "socks4"},
    {"name": "ShiftyTR SOCKS5", "url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt", "type": "socks5"},
    {"name": "Hookzof SOCKS5", "url": "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt", "type": "socks5"},
    {"name": "Jetkai HTTP", "url": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt", "type": "http"},
    {"name": "Jetkai HTTPS", "url": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-https.txt", "type": "https"},
    {"name": "Jetkai SOCKS4", "url": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks4.txt", "type": "socks4"},
    {"name": "Jetkai SOCKS5", "url": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt", "type": "socks5"},
    {"name": "Zloi HTTP", "url": "https://raw.githubusercontent.com/zloi-user/hideip.me/master/http.txt", "type": "http"},
    {"name": "Zloi HTTPS", "url": "https://raw.githubusercontent.com/zloi-user/hideip.me/master/https.txt", "type": "https"},
    {"name": "Zloi SOCKS4", "url": "https://raw.githubusercontent.com/zloi-user/hideip.me/master/socks4.txt", "type": "socks4"},
    {"name": "Zloi SOCKS5", "url": "https://raw.githubusercontent.com/zloi-user/hideip.me/master/socks5.txt", "type": "socks5"},
    {"name": "Clarketm HTTP", "url": "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt", "type": "http"},
    {"name": "Geonode Free Proxies", "url": "https://proxylist.geonode.com/api/proxy-list?limit=100&page=1&sort_by=lastChecked&sort_type=desc", "type": "json_geonode"},
]

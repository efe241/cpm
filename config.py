import os
from dotenv import load_dotenv

load_dotenv()

# Discord Bot Token
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "BURAYA_BOT_TOKENINI_YAZIN")

# Firebase & CPM API Bilgileri
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "AIzaSyBW1ZbMiUeDZHYUO2bY8Bfnf5rRgrQGPTM")
AUTH_LOGIN_URL = f"https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword?key={FIREBASE_API_KEY}"
AUTH_LOOKUP_URL = f"https://www.googleapis.com/identitytoolkit/v3/relyingparty/getAccountInfo?key={FIREBASE_API_KEY}"
CF_BASE_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net"

# Eşzamanlı maksimum istek sayısı (Asenkron tarama hızı)
MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", 20))

# 🎯 Limit Tanımlamaları (Free / VIP / Admin)
FREE_LIMIT = int(os.getenv("FREE_LIMIT", 25))        # Normal kullanıcı limiti
VIP_LIMIT = int(os.getenv("VIP_LIMIT", 100))         # VIP üye limiti
ADMIN_LIMIT = int(os.getenv("ADMIN_LIMIT", 500))     # Admin limiti

# 👑 Yönetici Discord Kullanıcı ID'leri (virgülle ayırarak .env içine yazabilirsiniz)
raw_admins = os.getenv("ADMIN_USER_IDS", "")
ADMIN_USER_IDS = [int(x.strip()) for x in raw_admins.split(",") if x.strip().isdigit()]

# 🌟 VIP Rol ID'leri (Sunucudaki VIP rollerinin ID'leri)
raw_vip_roles = os.getenv("VIP_ROLE_IDS", "")
VIP_ROLE_IDS = [int(x.strip()) for x in raw_vip_roles.split(",") if x.strip().isdigit()]

# 🌐 Proxy & Apify & Web Dashboard API Ayarları
APIFY_PROXY_URL = os.getenv("APIFY_PROXY_URL", "")
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "")
PROXY_API_URL = os.getenv("PROXY_API_URL", "")
WEB_DASHBOARD_URL = os.getenv("WEB_DASHBOARD_URL", "").rstrip("/")
PROXY_TEST_TIMEOUT = float(os.getenv("PROXY_TEST_TIMEOUT", 2.5))
PROXY_TEST_URL = os.getenv("PROXY_TEST_URL", "https://httpbin.org/ip")

# 🌍 Küresel & Dünya Çapında 25+ Otomatik Proxy Kaynağı
BUILTIN_PROXY_SOURCES = [
    # 1. ProxyScrape Global
    {"name": "ProxyScrape HTTP", "url": "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3000&country=all&ssl=all&anonymity=all", "type": "http"},
    {"name": "ProxyScrape HTTPS", "url": "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=https&timeout=3000&country=all", "type": "https"},
    {"name": "ProxyScrape SOCKS4", "url": "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks4&timeout=3000&country=all", "type": "socks4"},
    {"name": "ProxyScrape SOCKS5", "url": "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=3000&country=all", "type": "socks5"},

    # 2. TheSpeedX Mega Global Lists
    {"name": "TheSpeedX HTTP", "url": "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt", "type": "http"},
    {"name": "TheSpeedX SOCKS4", "url": "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt", "type": "socks4"},
    {"name": "TheSpeedX SOCKS5", "url": "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt", "type": "socks5"},

    # 3. Monosans Multi-protocol Global Lists
    {"name": "Monosans HTTP", "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt", "type": "http"},
    {"name": "Monosans SOCKS4", "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt", "type": "socks4"},
    {"name": "Monosans SOCKS5", "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt", "type": "socks5"},
    {"name": "Monosans Anon HTTP", "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_anonymous/http.txt", "type": "http"},

    # 4. Proxy-List Download Service
    {"name": "ProxyList HTTP", "url": "https://www.proxy-list.download/api/v1/get?type=http", "type": "http"},
    {"name": "ProxyList HTTPS", "url": "https://www.proxy-list.download/api/v1/get?type=https", "type": "https"},
    {"name": "ProxyList SOCKS5", "url": "https://www.proxy-list.download/api/v1/get?type=socks5", "type": "socks5"},

    # 5. ShiftyTR Worldwide Proxies
    {"name": "ShiftyTR HTTP", "url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt", "type": "http"},
    {"name": "ShiftyTR HTTPS", "url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt", "type": "https"},
    {"name": "ShiftyTR SOCKS5", "url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt", "type": "socks5"},

    # 6. Hookzof Dedicated SOCKS5
    {"name": "Hookzof SOCKS5", "url": "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt", "type": "socks5"},

    # 7. Zloi-user Worldwide
    {"name": "Zloi HTTP", "url": "https://raw.githubusercontent.com/Zloi-user/hideip.me/master/http.txt", "type": "http"},
    {"name": "Zloi HTTPS", "url": "https://raw.githubusercontent.com/Zloi-user/hideip.me/master/https.txt", "type": "https"},
    {"name": "Zloi SOCKS5", "url": "https://raw.githubusercontent.com/Zloi-user/hideip.me/master/socks5.txt", "type": "socks5"},

    # 8. Jetkai Multi-source Global
    {"name": "Jetkai HTTP", "url": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt", "type": "http"},
    {"name": "Jetkai HTTPS", "url": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-https.txt", "type": "https"},
    {"name": "Jetkai SOCKS5", "url": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt", "type": "socks5"},

    # 9. Clarketm Global Raw
    {"name": "Clarketm Raw", "url": "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt", "type": "http"}
]

# 📁 Dizin ve Dosya Yolları
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
HITS_DIR = os.path.join(BASE_DIR, "hits")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
DATABASE_PATH = os.path.join(DATA_DIR, "database.sqlite")
PROXIES_FILE = os.path.join(BASE_DIR, "proxies.txt")

# Gerekli klasörleri otomatik oluştur
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(HITS_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

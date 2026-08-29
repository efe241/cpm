import os
import sys

# Windows konsol Unicode / Emoji desteğini garantiye al
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import asyncio
import aiohttp
from aiohttp import web
import discord
from discord.ext import commands

from config import DISCORD_TOKEN
from database import db
from proxy_manager import proxy_mgr
from web_server import create_web_app

# Bot Tanımlamaları
intents = discord.Intents.default()
intents.message_content = True

class CPMBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )
        self.http_session: aiohttp.ClientSession = None
        self.web_runner: web.AppRunner = None

    async def setup_hook(self):
        # 1. SQLite Veritabanını Başlat
        print("💾 Veritabanı başlatılıyor...")
        await db.init_db()
        print("✅ Veritabanı tabloları hazır.")

        # 2. Ortak HTTP Session Havuzunu Başlat
        self.http_session = aiohttp.ClientSession()

        # 3. Cog Modüllerini Dinamik Yükle
        cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
        if os.path.exists(cogs_dir):
            for filename in os.listdir(cogs_dir):
                if filename.endswith(".py") and not filename.startswith("__"):
                    cog_name = f"cogs.{filename[:-3]}"
                    try:
                        await self.load_extension(cog_name)
                        print(f"📦 Cog yüklendi: {cog_name}")
                    except Exception as e:
                        print(f"❌ Cog yükleme hatası ({cog_name}): {e}")

        # 4. Proxy Sayısını Kontrol Et
        proxy_count = proxy_mgr.load_proxies()
        print(f"🌐 Aktif Proxy Sayısı: {proxy_count}")

        # 5. Render / Bulut Uyumlu Web Dashboard Sunucusunu Başlat
        try:
            port = int(os.getenv("PORT", 8080))
            app = create_web_app()
            self.web_runner = web.AppRunner(app)
            await self.web_runner.setup()
            site = web.TCPSite(self.web_runner, "0.0.0.0", port)
            await site.start()
            print(f"🌐 Web Dashboard Başlatıldı: http://0.0.0.0:{port} (Render / Uptime Portu Aktif)")
        except Exception as e:
            print(f"⚠️ Web Dashboard başlatılırken hata: {e}")

    async def close(self):
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
        if self.web_runner:
            await self.web_runner.cleanup()
        await super().close()

bot = CPMBot()

@bot.event
async def on_ready():
    print("=" * 60)
    print(f"🚀 Bot Başarıyla Giriş Yaptı: {bot.user.name} ({bot.user.id})")
    print(f"📊 Discord.py Sürümü: {discord.__version__}")
    print("=" * 60)

    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} adet Slash komutu senkronize edildi!")
    except Exception as e:
        print(f"❌ Slash komutları senkronize edilirken hata: {e}")

    await bot.change_presence(
        activity=discord.Game(name="/yardim | CPM Checker 🚗")
    )

if __name__ == "__main__":
    if DISCORD_TOKEN == "BURAYA_BOT_TOKENINI_YAZIN" or not DISCORD_TOKEN:
        print("\n❌ HATA: 'config.py' veya '.env' dosyasına bot tokeninizi girmelisiniz!")
        print("Lütfen config.py veya .env içindeki DISCORD_TOKEN alanını güncelleyin.\n")
    else:
        bot.run(DISCORD_TOKEN)

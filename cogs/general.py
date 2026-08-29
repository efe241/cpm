import time
import json
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from config import WEB_DASHBOARD_URL, DEFAULT_WEB_DASHBOARD_URL
from proxy_manager import proxy_mgr

class GeneralCog(commands.Cog, name="Genel Komutlar"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="yardim", description="CPM Checker Bot yardım ve komut rehberini gösterir.")
    async def cmd_yardim_slash(self, interaction: discord.Interaction):
        embed = self.create_help_embed(interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @commands.command(name="yardim", aliases=["help", "komutlar", "h"])
    async def cmd_yardim_prefix(self, ctx: commands.Context):
        embed = self.create_help_embed(ctx.author)
        await ctx.reply(embed=embed)

    @app_commands.command(name="webtest", description="Vercel Web Dashboard bağlantısını ve canlı veri gönderimini test eder.")
    async def cmd_webtest_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        embed = await self.run_web_diagnostics(interaction.user)
        await interaction.followup.send(embed=embed)

    @commands.command(name="webtest", aliases=["testweb", "sync_test"])
    async def cmd_webtest_prefix(self, ctx: commands.Context):
        msg = await ctx.reply("⏳ Vercel Web Dashboard bağlantısı test ediliyor...")
        embed = await self.run_web_diagnostics(ctx.author)
        await msg.edit(content=None, embed=embed)

    async def run_web_diagnostics(self, user) -> discord.Embed:
        target_base = WEB_DASHBOARD_URL or DEFAULT_WEB_DASHBOARD_URL
        embed = discord.Embed(
            title="🌐 Web Dashboard Canlı Senkronizasyon Tanı Testi",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.add_field(name="🔗 Hedef Web URL", value=f"`{target_base}`", inline=False)

        # 1. Test: GET /api/health
        get_url = f"{target_base}/api/health"
        get_status = "Bilinmiyor"
        get_time = 0.0
        try:
            t0 = time.time()
            async with aiohttp.ClientSession() as s:
                async with s.get(get_url, timeout=aiohttp.ClientTimeout(total=5.0)) as resp:
                    get_time = round((time.time() - t0) * 1000, 1)
                    get_status = f"HTTP {resp.status} (OK)" if resp.status == 200 else f"HTTP {resp.status}"
        except Exception as e:
            get_status = f"❌ Hata: {e}"

        embed.add_field(name="1️⃣ GET Sağlık Kontrolü (/api/health)", value=f"• **Durum:** `{get_status}`\n• **Gecikme:** `{get_time} ms`", inline=False)

        # 2. Test: POST /api/hit_sync
        post_url = f"{target_base}/api/hit_sync"
        post_status = "Bilinmiyor"
        post_time = 0.0
        test_email = f"webtest_{datetime.now().strftime('%H%M%S')}@gmail.com"
        test_payload = {
            "hits": [{
                "email": test_email,
                "password": "test_pass_123",
                "cpm_level": 10,
                "cpm_total_cars": 250,
                "cpm_unlocked_cars": 200,
                "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }],
            "stats": {
                "total_hits": 348,
                "total_accs": 416,
                "total_scans": 7,
                "active_proxies": proxy_mgr.count()
            }
        }

        try:
            t1 = time.time()
            async with aiohttp.ClientSession() as s:
                async with s.post(post_url, json=test_payload, timeout=aiohttp.ClientTimeout(total=6.0)) as resp:
                    post_time = round((time.time() - t1) * 1000, 1)
                    post_body = await resp.text()
                    post_status = f"HTTP {resp.status} ➔ {post_body}"
        except Exception as e:
            post_status = f"❌ Hata: {e}"

        embed.add_field(
            name="2️⃣ POST Hit Gönderim Testi (/api/hit_sync)",
            value=f"• **Durum:** `{post_status}`\n• **Gecikme:** `{post_time} ms`\n• **Gönderilen:** `{test_email}` (🚗 250 Araç)",
            inline=False
        )

        embed.set_footer(text=f"Test Eden: {user.name} • [Web Sitesine Git]({target_base})")
        return embed

    def create_help_embed(self, user) -> discord.Embed:
        embed = discord.Embed(
            title="🚗 Car Parking Multiplayer & Firebase Checker Bot",
            description="Aşağıda botun tüm komutları ve interaktif panelleri listelenmiştir:",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.add_field(
            name="🚗 `!checkpanel` veya `/checkpanel` (Ana Hesap Kontrol Paneli)",
            value="İnteraktif modal butonlarıyla tekli ve toplu hesap kontrolü yapmanızı sağlar.",
            inline=False
        )
        embed.add_field(
            name="🌍 `!proxypanel` veya `/proxypanel` (Proxy Yönetim Paneli)",
            value="25+ Küresel kaynaktan otomatik proxy çeker, paralel hız testi yapar ve havuzu yönetir.",
            inline=False
        )
        embed.add_field(
            name="⚡ `!check email:şifre` veya `/check`",
            value="Tek bir CPM hesabının tüm garaj araçlarını, açık araçlarını ve seviyesini doğrular.",
            inline=False
        )
        embed.add_field(
            name="📦 `!toplu` veya `/toplu_kontrol`",
            value="Doğrudan metin yapıştırarak veya `.txt` dosyası yükleyerek toplu tarama yapar.",
            inline=False
        )
        embed.add_field(
            name="📊 `!stats` veya `/istatistik`",
            value="Kişisel ve genel tarama başarı istatistiklerini görüntüler.",
            inline=False
        )
        embed.add_field(
            name="🌐 `!webtest` veya `/webtest` (Web Bağlantı Testi)",
            value="Vercel web sitesi ve API canlı veri akışını test eder.",
            inline=False
        )
        embed.add_field(
            name="🌐 Canlı Web Dashboard",
            value="[Web Dashboard Linki](https://tempapims-efes-projects-602609c9.vercel.app)",
            inline=False
        )
        embed.set_footer(text=f"İsteyen: {user.name} • CPM Turbo Engine")
        return embed

async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))

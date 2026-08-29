import time
from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands

from database import db
from proxy_manager import proxy_mgr

class StatsCog(commands.Cog, name="Stats"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.time()

    def get_uptime(self) -> str:
        delta = int(time.time() - self.start_time)
        hours, remainder = divmod(delta, 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        if days > 0:
            return f"{days}g {hours}s {minutes}dk {seconds}sn"
        return f"{hours}s {minutes}dk {seconds}sn"

    async def create_stats_embed(self, user: discord.User) -> discord.Embed:
        global_stats = await db.get_global_stats()
        user_stats = await db.get_user_stats(user.id)

        tot_accs = global_stats["total_accs"]
        tot_hits = global_stats["total_hits"]
        hit_rate = round((tot_hits / tot_accs * 100), 2) if tot_accs > 0 else 0.0

        embed = discord.Embed(
            title="📊 CPM Bot İstatistik & Durum Paneli",
            color=discord.Color.blurple(),
            timestamp=datetime.now()
        )

        embed.add_field(name="📦 Toplam Taranan Hesap", value=f"`{tot_accs:,}`", inline=True)
        embed.add_field(name="🎯 Toplam Bulunan Hit", value=f"`{tot_hits:,}`", inline=True)
        embed.add_field(name="📈 Başarı (Hit) Oranı", value=f"`%{hit_rate}`", inline=True)

        embed.add_field(name="🚀 Toplam Tarama İşlemi", value=f"`{global_stats['total_scans']}`", inline=True)
        embed.add_field(name="👑 Aktif VIP Sayısı", value=f"`{global_stats['total_vips']}`", inline=True)
        embed.add_field(name="🌐 Aktif Proxy Havuzu", value=f"`{proxy_mgr.count()}` adet", inline=True)

        u_accs = user_stats["total_accs"]
        u_hits = user_stats["hits"]
        u_scans = user_stats["scans"]
        embed.add_field(
            name="👤 Sizin İstatistikleriniz",
            value=f"• Yapılan Tarama: `{u_scans}`\n• Taranan Hesap: `{u_accs}`\n• Bulunan Hit: `{u_hits}`",
            inline=False
        )

        embed.add_field(name="⏱️ Bot Çalışma Süresi", value=f"`{self.get_uptime()}`", inline=True)
        embed.add_field(name="📡 Bot Ping", value=f"`{round(self.bot.latency * 1000)}ms`", inline=True)

        embed.set_footer(text=f"İsteyen: {user.name}")
        return embed

    @app_commands.command(name="istatistik", description="Botun genel ve kişisel tarama istatistiklerini görüntüler.")
    async def cmd_stats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        embed = await self.create_stats_embed(interaction.user)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.command(name="istatistik", aliases=["stats", "durum"])
    async def prefix_stats(self, ctx: commands.Context):
        """DM ve Sunucuda !istatistik komutu"""
        embed = await self.create_stats_embed(ctx.author)
        await ctx.reply(embed=embed)

    @app_commands.command(name="son_hitler", description="Son bulunan geçerli hesapların özetini listeler.")
    @app_commands.describe(adet="Gösterilecek kayıt sayısı (Maks 15)")
    async def cmd_recent_hits(self, interaction: discord.Interaction, adet: int = 5):
        await interaction.response.defer(ephemeral=True)

        adet = max(1, min(adet, 15))
        hits = await db.get_recent_hits(limit=adet, user_id=interaction.user.id)

        if not hits:
            await interaction.followup.send("ℹ️ Henüz adınıza kayıtlı bir hit bulunamadı.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🎯 Son Bulunan Hit Kayıtlarınız (Son {len(hits)})",
            color=discord.Color.teal(),
            timestamp=datetime.now()
        )

        for h in hits:
            created = h.get("created_at", "-")
            embed.add_field(
                name=f"🚗 {h.get('email')}",
                value=f"• Şifre: ||`{h.get('password')}`||\n• Seviye: `Lvl {h.get('level')}` | Araç: `{h.get('total_cars')}`\n• UID: `{h.get('uid')}`\n• Tarih: `{created}`",
                inline=False
            )

        embed.set_footer(text="Bu sonuçlar gizlidir ve yalnızca size gösterilir.")
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(StatsCog(bot))

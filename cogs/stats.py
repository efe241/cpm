import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from database import db
from proxy_manager import proxy_mgr

class StatsCog(commands.Cog, name="İstatistikler"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="istatistik", description="Kişisel ve genel tarama istatistiklerini gösterir.")
    async def cmd_stats_slash(self, interaction: discord.Interaction):
        embed = await self.create_stats_embed(interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @commands.command(name="stats", aliases=["istatistik", "stat", "bilgi"])
    async def cmd_stats_prefix(self, ctx: commands.Context):
        embed = await self.create_stats_embed(ctx.author)
        await ctx.reply(embed=embed)

    async def create_stats_embed(self, user) -> discord.Embed:
        user_id = user.id
        u_stats = await db.get_user_stats(user_id)
        g_stats = await db.get_global_stats()
        is_vip = await db.is_vip(user_id)
        is_admin = await db.is_admin_or_authorized(user_id)
        limit = db.get_user_limit(user_id, is_vip)

        status_tag = "👑 Yönetici" if is_admin else ("⭐ VIP Üye" if is_vip else "👤 Standart Üye")

        embed = discord.Embed(
            title="📊 CPM Checker İstatistik Raporu",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        embed.add_field(name="👤 Kullanıcı Durumu", value=f"**{status_tag}** (Limit: `{limit} CPM`)", inline=False)
        embed.add_field(name="📈 Kişisel Taramalar", value=f"`{u_stats['scans']}` işlem", inline=True)
        embed.add_field(name="🎯 Kişisel Hesaplar", value=f"`{u_stats['total_accs']}` taranan", inline=True)
        embed.add_field(name="✅ Kişisel Hit", value=f"**`{u_stats['hits']}`** çalışan", inline=True)

        embed.add_field(name="🌐 Genel Sistem Taranan", value=f"`{g_stats['total_accs']}` hesap", inline=True)
        embed.add_field(name="🏆 Genel Toplam Hit", value=f"**`{g_stats['total_hits']}`** çalışan", inline=True)
        embed.add_field(name="🌍 Aktif Proxy Havuzu", value=f"**`{proxy_mgr.count()}`** adet", inline=True)

        embed.set_footer(text=f"Talep eden: {user.name} • 7/24 Canlı Sistem")
        return embed

async def setup(bot: commands.Bot):
    await bot.add_cog(StatsCog(bot))

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

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
            name="🌐 Canlı Web Dashboard",
            value="[Web Dashboard Linki](https://tempapims-efes-projects-602609c9.vercel.app)",
            inline=False
        )
        embed.set_footer(text=f"İsteyen: {user.name} • CPM Turbo Engine")
        return embed

async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))

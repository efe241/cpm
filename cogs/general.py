import discord
from discord import app_commands
from discord.ext import commands

from config import FREE_LIMIT, VIP_LIMIT

class GeneralCog(commands.Cog, name="General"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def create_help_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🚗 Car Parking Multiplayer Bot - Komut Kılavuzu",
            description="Botu hem **Sunucularda** hem de **Özel Mesajda (DM)** butonlu panellerle ve `!` komutlarıyla kolayca kullanabilirsiniz.",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="🚗 `!checkpanel` veya `/checkpanel` (Ana Hesap Kontrol Paneli)",
            value="• Tek tuşla form açıp tekli hesap kontrolü yapın.\n"
                  "• Çoklu hesapları metin kutusuna yapıştırıp hızlı tarayın.\n"
                  "• İstatistiklerinizi ve son bulduğunuz hitleri görün.\n"
                  "• Sonuçlar adınıza özel `results/<isminiz>/` klasörüne kaydedilir.",
            inline=False
        )

        embed.add_field(
            name="🌐 `!proxypanel` veya `/proxypanel` (Yetkili Proxy Paneli)",
            value="• 25+ küresel kaynaktan tek tıkla canlı proxy çekip test edin.\n"
                  "• Havuzdaki ölü proxyleri temizleyin.\n"
                  "• Özel API / linkten anlık proxy yükleyin.",
            inline=False
        )

        embed.add_field(
            name="📁 Hızlı Doğrudan Komutlar",
            value="• `!check email:şifre` : Tekli hızlı kontrol.\n"
                  "• `!toplu` *(Dosya Ekleyerek)* : TXT dosyası ile turbo tarama.\n"
                  "• `!quick` : Mesaja alt alta yapıştırarak kontrol.\n"
                  "• `!istatistik` : Genel ve kişisel tarama verileri.",
            inline=False
        )

        embed.add_field(
            name="👑 Yetki & VIP Yönetimi",
            value="• `!yetkili_ekle @kullanici` : Panel ve proxy kontrol yetkisi tanımlar.\n"
                  "• `!vip_ekle @kullanici [gun]` : 100 CPM limitli VIP tanımlar.",
            inline=False
        )

        embed.set_footer(text="CPM Bot • DM ve Sunucu Uyumlu")
        return embed

    @app_commands.command(name="yardim", description="Bot komutlarını ve kılavuzunu gösterir.")
    async def cmd_help(self, interaction: discord.Interaction):
        embed = self.create_help_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="yardim", aliases=["help", "komutlar"])
    async def prefix_help(self, ctx: commands.Context):
        """DM ve Sunucuda !yardim komutu"""
        embed = self.create_help_embed()
        await ctx.reply(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))

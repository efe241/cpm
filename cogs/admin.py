import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from typing import Optional

from config import ADMIN_USER_IDS, PROXIES_FILE_PATH
from database import db
from proxy_manager import proxy_mgr

class ProxyApiModal(discord.ui.Modal, title="➕ Özel Proxy API / URL Ekle"):
    url_input = discord.ui.TextInput(
        label="Proxy URL Adresi (veya API Endpoint)",
        placeholder="https://raw.githubusercontent.com/.../proxies.txt",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        url = self.url_input.value.strip()
        found, working = await proxy_mgr.fetch_and_auto_test(custom_urls=[url])
        await interaction.followup.send(
            f"✅ **Özel Kaynak Eklendi & Test Edildi!**\n"
            f"📥 Çekilen Ham Proxy: **`{found}`**\n"
            f"🟢 Çalışan ve Havuza Eklenen: **`{working}`**\n"
            f"🌐 Güncel Havuz Boyutu: **`{proxy_mgr.count()}`**",
            ephemeral=True
        )

class ProxyPanelView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    async def check_admin(self, interaction: discord.Interaction) -> bool:
        if await db.is_admin_or_authorized(interaction.user.id):
            return True
        await interaction.response.send_message("❌ Bu paneli sadece **Yöneticiler** kullanabilir!", ephemeral=True)
        return False

    @discord.ui.button(label="🌍 25+ Kaynaktan Otomatik Çek & Test Et", style=discord.ButtonStyle.success, emoji="⚡", row=0)
    async def btn_fetch_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_admin(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        found, working = await proxy_mgr.fetch_and_auto_test()
        await interaction.followup.send(
            f"✅ **25+ Küresel Kaynaktan Otomatik Çekim Tamamlandı!**\n"
            f"📥 Toplam Bulunan: **`{found}`** adet\n"
            f"🟢 Testi Geçen Aktif: **`{working}`** adet\n"
            f"🌐 Toplam Havuz: **`{proxy_mgr.count()}`** adet",
            ephemeral=True
        )

    @discord.ui.button(label="🧪 Mevcut Havuzu Test Et", style=discord.ButtonStyle.primary, emoji="🔍", row=0)
    async def btn_test_pool(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_admin(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        current = list(proxy_mgr.proxies)
        if not current:
            await interaction.followup.send("⚠️ Havuzda test edilecek proxy yok!", ephemeral=True)
            return
        working = await proxy_mgr.test_and_filter_proxies(current, max_concurrency=60)
        await interaction.followup.send(
            f"✅ **Havuz Hız Testi Tamamlandı!**\n"
            f"📊 Önceki: **`{len(current)}`** ➔ Kalan Aktif: **`{len(working)}`**",
            ephemeral=True
        )

    @discord.ui.button(label="📂 Dosyadan Yeniden Yükle", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)
    async def btn_reload(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_admin(interaction):
            return
        cnt = proxy_mgr.load_proxies()
        await interaction.response.send_message(f"✅ `proxies.txt` dosyasından **`{cnt}`** adet proxy başarıyla yüklendi!", ephemeral=True)

    @discord.ui.button(label="➕ Özel API / URL Ekle", style=discord.ButtonStyle.secondary, emoji="🔗", row=1)
    async def btn_custom_url(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_admin(interaction):
            return
        await interaction.response.send_modal(ProxyApiModal())

    @discord.ui.button(label="📊 Havuz Durumu", style=discord.ButtonStyle.secondary, emoji="📈", row=2)
    async def btn_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🌐 Aktif Proxy Havuz Durumu", color=discord.Color.blue(), timestamp=datetime.now())
        embed.add_field(name="Aktif Proxy Sayısı", value=f"**`{proxy_mgr.count()}`** adet", inline=True)
        embed.add_field(name="Apify Proxy Durumu", value="🟢 Aktif / Bağlı", inline=True)
        embed.set_footer(text="Car Parking Multiplayer Turbo Proxy Motoru")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="👑 VIP & Yetkili Listesi", style=discord.ButtonStyle.secondary, emoji="📋", row=2)
    async def btn_vips(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_admin(interaction):
            return
        vips = await db.list_vips()
        admins = await db.list_admins()
        txt = f"**👑 Yönetici Sayısı:** `{len(admins)}`\n**⭐ Aktif VIP Sayısı:** `{len(vips)}`\n\n"
        if vips:
            txt += "**VIP Üyeler:**\n"
            for v in vips[:10]:
                exp = v.get("vip_expires_at") or "Süresiz"
                txt += f"• <@{v['user_id']}> (`{v['user_id']}`) - Bitiş: `{exp}`\n"
        await interaction.response.send_message(txt, ephemeral=True)

class AdminCog(commands.Cog, name="Yönetici Komutları"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="proxypanel", description="Gelişmiş Proxy Yönetim ve Çekim Panelini açar.")
    async def cmd_proxypanel_slash(self, interaction: discord.Interaction):
        if not await db.is_admin_or_authorized(interaction.user.id):
            await interaction.response.send_message("❌ Bu paneli sadece **Yöneticiler** açabilir!", ephemeral=True)
            return
        embed = self.create_proxy_panel_embed()
        view = ProxyPanelView(self.bot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

    @commands.command(name="proxypanel", aliases=["proxy", "proxyler"])
    async def cmd_proxypanel_prefix(self, ctx: commands.Context):
        if not await db.is_admin_or_authorized(ctx.author.id):
            await ctx.reply("❌ Bu komutu sadece **Yöneticiler** kullanabilir!")
            return
        embed = self.create_proxy_panel_embed()
        view = ProxyPanelView(self.bot)
        await ctx.reply(embed=embed, view=view)

    def create_proxy_panel_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🌍 25+ Küresel Otomatik Proxy Motoru & Yönetim Paneli",
            description=(
                "Aşağıdaki butonları kullanarak dünya genelindeki **25+ güvenilir proxy kaynağından** "
                "tek tıkla binlerce proxy çekebilir, paralel hız testi yapabilir ve havuzunuzu tazeleyebilirsiniz."
            ),
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(name="🌐 Mevcut Aktif Havuz", value=f"**`{proxy_mgr.count()}`** adet proxy", inline=True)
        embed.add_field(name="⚡ Test Toleransı", value="`2.5 saniye` (Ultra Hızlı)", inline=True)
        embed.add_field(name="🛡️ Apify Proxy Durumu", value="🟢 **Bağlı & Rotasyonda**", inline=True)
        embed.set_footer(text="CPM Proxy Motoru • !proxypanel")
        return embed

    @app_commands.command(name="vip_ekle", description="Bir kullanıcıya VIP üyelik tanımlar.")
    @app_commands.describe(kullanici="VIP verilecek kullanıcı", gun="Kaç gün verilecek (boş bırakılırsa süresiz)")
    async def cmd_add_vip(self, interaction: discord.Interaction, kullanici: discord.User, gun: Optional[int] = None):
        if not await db.is_admin_or_authorized(interaction.user.id):
            await interaction.response.send_message("❌ Yetkiniz yok!", ephemeral=True)
            return
        await db.add_vip(kullanici.id, interaction.user.id, days=gun)
        sure_txt = f"{gun} gün" if gun else "Süresiz"
        await interaction.response.send_message(f"✅ {kullanici.mention} kullanıcısına **{sure_txt} VIP** yetkisi tanımlandı!", ephemeral=False)

    @app_commands.command(name="vip_sil", description="Bir kullanıcının VIP üyeliğini kaldırır.")
    async def cmd_remove_vip(self, interaction: discord.Interaction, kullanici: discord.User):
        if not await db.is_admin_or_authorized(interaction.user.id):
            await interaction.response.send_message("❌ Yetkiniz yok!", ephemeral=True)
            return
        await db.remove_vip(kullanici.id)
        await interaction.response.send_message(f"✅ {kullanici.mention} kullanıcısının VIP yetkisi silindi.", ephemeral=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))

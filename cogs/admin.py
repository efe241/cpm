import time
from datetime import datetime
from typing import Optional
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from config import ADMIN_USER_IDS, FREE_LIMIT, VIP_LIMIT
from database import db
from proxy_manager import proxy_mgr

# =============================================================================
# 📥 PROXY API MODALI (POP-UP URL GİRME FORMU)
# =============================================================================
class ProxyApiModal(discord.ui.Modal, title="🌐 Özel API / Linkten Proxy Yükle"):
    url_input = discord.ui.TextInput(
        label="Proxy API veya Liste URL'si",
        placeholder="https://api.proxyscrape.com/v2/... veya https://.../proxies.txt",
        required=True
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        url = self.url_input.value.strip()

        session = getattr(self.bot, "http_session", None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            added = await proxy_mgr.fetch_from_api(session, url)
        finally:
            if close_session:
                await session.close()

        embed = discord.Embed(
            title="📥 API'den Proxy Yüklendi",
            description=f"✅ Belirtilen adresten **{added}** adet yeni proxy havuza eklendi.\n"
                        f"Toplam Havuz: **{proxy_mgr.count()}** proxy.\n\n"
                        f"💡 *`[🧪 Havuzu Test Et]` butonuna basarak çalışanları hemen filtreleyebilirsiniz.*",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


# =============================================================================
# 🎛️ PROXY PANEL VIEW (BUTONLAR)
# =============================================================================
class ProxyPanelView(discord.ui.View):
    def __init__(self, bot: commands.Bot, owner_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await db.is_admin_or_authorized(interaction.user.id):
            await interaction.response.send_message("❌ Bu paneli kullanmak için yönetim yetkiniz bulunmuyor!", ephemeral=True)
            return False
        return True

    # 1. Buton: 🌍 25+ Kaynaktan Otomatik Çek & Test Et
    @discord.ui.button(label="Oto Proxy Çek & Test", style=discord.ButtonStyle.success, emoji="🌍", row=0)
    async def btn_auto_fetch(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        session = getattr(self.bot, "http_session", None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            stats = await proxy_mgr.fetch_and_auto_test(session)
        finally:
            if close_session:
                await session.close()

        working_cnt = stats["working"]
        embed = discord.Embed(
            title="🌍 25+ Küresel Kaynaktan Proxy Çekildi & Test Edildi",
            description=f"✅ **{stats['total_fetched']}** proxy çekildi, **{stats['tested']}** test edildi.\n"
                        f"🎯 **{working_cnt}** adet canlı ve çalışan proxy havuza eklendi!\n"
                        f"💾 Aktif Havuz: **{proxy_mgr.count()}** proxy.",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        if stats["working_list"]:
            sample = [f"• `{x['proxy']}` ➔ ⚡ **{x['latency']} ms**" for x in stats["working_list"][:5]]
            embed.add_field(name="⚡ En Hızlılar", value="\n".join(sample), inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    # 2. Buton: 🧪 Havuzu Test Et (Ölüleri Temizle)
    @discord.ui.button(label="Havuzu Test Et", style=discord.ButtonStyle.primary, emoji="🧪", row=0)
    async def btn_test_pool(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        session = getattr(self.bot, "http_session", None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            results = await proxy_mgr.test_and_filter_proxies(session)
        finally:
            if close_session:
                await session.close()

        embed = discord.Embed(
            title="🧪 Havuz Sağlık Testi Tamamlandı",
            description=f"• Test Edilen: `{results['total']}`\n"
                        f"• ✅ Canlı & Çalışan: **`{results['working']}`**\n"
                        f"• ❌ Elenen / Ölü: `{results['failed']}`\n"
                        f"💾 Güncel Havuz: **{proxy_mgr.count()}** proxy.",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # 3. Buton: 📂 proxies.txt Dosyasından Oku
    @discord.ui.button(label="Dosyadan Oku", style=discord.ButtonStyle.secondary, emoji="📂", row=0)
    async def btn_reload_file(self, interaction: discord.Interaction, button: discord.ui.Button):
        cnt = proxy_mgr.load_proxies()
        await interaction.response.send_message(
            f"✅ `proxies.txt` dosyasından toplam **{cnt}** proxy okundu ve rotasyona alındı.",
            ephemeral=True
        )

    # 4. Buton: ➕ API / Linkten Proxy Ekle
    @discord.ui.button(label="API'den Proxy Çek", style=discord.ButtonStyle.secondary, emoji="➕", row=1)
    async def btn_api_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ProxyApiModal(self.bot))

    # 5. Buton: 📊 Havuz Durumu
    @discord.ui.button(label="Havuz Durumu", style=discord.ButtonStyle.secondary, emoji="📊", row=1)
    async def btn_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        global_stats = await db.get_global_stats()
        panel_embed = create_proxy_panel_embed(global_stats)
        await interaction.response.edit_message(embed=panel_embed, view=self)

    # 6. Buton: 👑 Yetkili & VIP Listesi
    @discord.ui.button(label="Yetkili & VIP'ler", style=discord.ButtonStyle.secondary, emoji="👑", row=1)
    async def btn_list_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        vips = await db.list_vips()
        admins = await db.list_admins()

        vip_lines = [f"• <@{v['user_id']}> (Bitiş: `{v.get('vip_expires_at') or 'Süresiz'}`)" for v in vips] or ["*Kayıtlı VIP yok*"]
        admin_lines = [f"• <@{a['user_id']}> (`{a['user_id']}`)" for a in admins] or ["*Ekstra yetkili yok*"]

        embed = discord.Embed(title="👑 Kayıtlı VIP & Panel Yetkilileri", color=discord.Color.gold())
        embed.add_field(name="🛡️ Panel & Proxy Yetkilileri", value="\n".join(admin_lines), inline=False)
        embed.add_field(name="⭐ VIP Üyeler (100 CPM)", value="\n".join(vip_lines), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


def create_proxy_panel_embed(stats: dict) -> discord.Embed:
    embed = discord.Embed(
        title="🌐 Proxy Yönetim Paneli (!proxypanel)",
        description="Aşağıdaki butonları kullanarak dünya genelindeki 25+ kaynaktan proxy çekebilir, ölüleri temizleyebilir ve havuzu yönetebilirsiniz.",
        color=discord.Color.teal(),
        timestamp=datetime.now()
    )
    embed.add_field(name="🌐 Aktif Proxy Havuzu", value=f"**`{proxy_mgr.count()}` adet**", inline=True)
    embed.add_field(name="🌍 Taranan Kaynak", value="`25+ Global API/Repo`", inline=True)
    embed.add_field(name="🛡️ Panel Yetkilisi", value=f"`{stats.get('total_admins', 0)}` kişi", inline=True)

    embed.add_field(name="📦 Toplam Taranan Hesap", value=f"`{stats.get('total_accs', 0):,}`", inline=True)
    embed.add_field(name="🎯 Toplam Hit", value=f"`{stats.get('total_hits', 0):,}`", inline=True)
    embed.add_field(name="👑 Aktif VIP Sayısı", value=f"`{stats.get('total_vips', 0)}`", inline=True)

    embed.set_footer(text="Yetkili Proxy Kontrol Paneli • Butonlara basarak işlem yapabilirsiniz.")
    return embed


# =============================================================================
# 📌 ADMIN COG
# =============================================================================
class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def check_admin_perm(self, user_id: int) -> bool:
        return await db.is_admin_or_authorized(user_id)

    # =========================================================================
    # 🌐 /proxypanel ve !proxypanel (!panel)
    # =========================================================================
    @app_commands.command(name="proxypanel", description="[Yetkili] İnteraktif Proxy Kontrol Panelini açar.")
    async def cmd_proxypanel_slash(self, interaction: discord.Interaction):
        if not await self.check_admin_perm(interaction.user.id):
            await interaction.response.send_message("❌ Bu paneli açmak için yönetim yetkiniz bulunmuyor!", ephemeral=True)
            return

        stats = await db.get_global_stats()
        embed = create_proxy_panel_embed(stats)
        view = ProxyPanelView(self.bot, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

    @commands.command(name="proxypanel", aliases=["panel", "proxy_panel", "pp"])
    async def cmd_proxypanel_prefix(self, ctx: commands.Context):
        """DM ve Sunucuda !proxypanel komutu"""
        if not await self.check_admin_perm(ctx.author.id):
            await ctx.reply("❌ Bu paneli açmak için yönetim yetkiniz bulunmuyor!")
            return

        stats = await db.get_global_stats()
        embed = create_proxy_panel_embed(stats)
        view = ProxyPanelView(self.bot, ctx.author.id)
        await ctx.reply(embed=embed, view=view)

    # =========================================================================
    # 🛡️ /yetkili_ekle & !yetkili_ekle
    # =========================================================================
    @app_commands.command(name="yetkili_ekle", description="[Admin] Bir kullanıcıya Panel ve Proxy yönetim yetkisi verir.")
    @app_commands.describe(kullanici="Yetki verilecek Discord kullanıcısı")
    async def cmd_add_admin_slash(self, interaction: discord.Interaction, kullanici: discord.User):
        if not await self.check_admin_perm(interaction.user.id):
            await interaction.response.send_message("❌ Bu komutu kullanmaya yetkiniz yok!", ephemeral=True)
            return

        await db.add_admin(kullanici.id, interaction.user.id)
        await interaction.response.send_message(
            f"✅ {kullanici.mention} artık **Panel & Proxy Yetkilisi** yapıldı! `!proxypanel` komutunu kullanabilir.",
            ephemeral=True
        )

    @commands.command(name="yetkili_ekle", aliases=["admin_ekle", "addadmin"])
    async def cmd_add_admin_prefix(self, ctx: commands.Context, kullanici: discord.User = None):
        if not await self.check_admin_perm(ctx.author.id):
            await ctx.reply("❌ Bu komutu kullanmaya yetkiniz yok!")
            return
        if not kullanici:
            await ctx.reply("❌ Kullanım: `!yetkili_ekle @kullanici`")
            return

        await db.add_admin(kullanici.id, ctx.author.id)
        await ctx.reply(f"✅ {kullanici.mention} artık **Panel & Proxy Yetkilisi** yapıldı!")

    # =========================================================================
    # 🛡️ /yetkili_sil & !yetkili_sil
    # =========================================================================
    @app_commands.command(name="yetkili_sil", description="[Admin] Bir kullanıcının Panel yönetim yetkisini kaldırır.")
    @app_commands.describe(kullanici="Yetkisi kaldırılacak Discord kullanıcısı")
    async def cmd_remove_admin_slash(self, interaction: discord.Interaction, kullanici: discord.User):
        if not await self.check_admin_perm(interaction.user.id):
            await interaction.response.send_message("❌ Bu komutu kullanmaya yetkiniz yok!", ephemeral=True)
            return

        await db.remove_admin(kullanici.id)
        await interaction.response.send_message(f"ℹ️ {kullanici.mention} kullanıcısının yönetim yetkisi kaldırıldı.", ephemeral=True)

    @commands.command(name="yetkili_sil", aliases=["admin_sil", "removeadmin"])
    async def cmd_remove_admin_prefix(self, ctx: commands.Context, kullanici: discord.User = None):
        if not await self.check_admin_perm(ctx.author.id):
            await ctx.reply("❌ Bu komutu kullanmaya yetkiniz yok!")
            return
        if not kullanici:
            await ctx.reply("❌ Kullanım: `!yetkili_sil @kullanici`")
            return

        await db.remove_admin(kullanici.id)
        await ctx.reply(f"ℹ️ {kullanici.mention} kullanıcısının yönetim yetkisi kaldırıldı.")

    # =========================================================================
    # 👑 /vip_ekle & !vip_ekle
    # =========================================================================
    @app_commands.command(name="vip_ekle", description="[Yetkili] Bir kullanıcıya VIP üyelik tanımlar (100 CPM limiti).")
    @app_commands.describe(
        kullanici="VIP yapılacak Discord kullanıcısı",
        gun="Kaç gün VIP kalsın? (Süresiz için boş bırakın)"
    )
    async def cmd_add_vip_slash(
        self,
        interaction: discord.Interaction,
        kullanici: discord.User,
        gun: Optional[int] = None
    ):
        if not await self.check_admin_perm(interaction.user.id):
            await interaction.response.send_message("❌ Bu komutu kullanmaya yetkiniz yok!", ephemeral=True)
            return

        await db.add_vip(kullanici.id, interaction.user.id, days=gun)
        dur_text = f"**{gun} gün**" if gun else "**Süresiz**"
        embed = discord.Embed(
            title="👑 VIP Üyelik Tanımlandı",
            description=f"✅ {kullanici.mention} artık VIP statüsüne yükseltildi!\n"
                        f"• Tarama Limiti: **{VIP_LIMIT} CPM**\n"
                        f"• Süre: {dur_text}",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="vip_ekle", aliases=["addvip"])
    async def cmd_add_vip_prefix(self, ctx: commands.Context, kullanici: discord.User = None, gun: int = None):
        if not await self.check_admin_perm(ctx.author.id):
            await ctx.reply("❌ Bu komutu kullanmaya yetkiniz yok!")
            return
        if not kullanici:
            await ctx.reply("❌ Kullanım: `!vip_ekle @kullanici [gün_sayısı]`")
            return

        await db.add_vip(kullanici.id, ctx.author.id, days=gun)
        dur_text = f"**{gun} gün**" if gun else "**Süresiz**"
        await ctx.reply(f"👑 {kullanici.mention} kullanıcısına **{VIP_LIMIT} CPM** limitli VIP yetkisi ({dur_text}) tanımlandı!")

    # =========================================================================
    # 👑 /vip_sil & !vip_sil
    # =========================================================================
    @app_commands.command(name="vip_sil", description="[Yetkili] Bir kullanıcının VIP üyeliğini kaldırır.")
    @app_commands.describe(kullanici="VIP üyeliği kaldırılacak Discord kullanıcısı")
    async def cmd_remove_vip_slash(self, interaction: discord.Interaction, kullanici: discord.User):
        if not await self.check_admin_perm(interaction.user.id):
            await interaction.response.send_message("❌ Bu komutu kullanmaya yetkiniz yok!", ephemeral=True)
            return

        await db.remove_vip(kullanici.id)
        embed = discord.Embed(
            title="🗑️ VIP Üyelik Kaldırıldı",
            description=f"ℹ️ {kullanici.mention} kullanıcısının VIP yetkisi silindi ve **{FREE_LIMIT} CPM** Free limitine çekildi.",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="vip_sil", aliases=["removevip"])
    async def cmd_remove_vip_prefix(self, ctx: commands.Context, kullanici: discord.User = None):
        if not await self.check_admin_perm(ctx.author.id):
            await ctx.reply("❌ Bu komutu kullanmaya yetkiniz yok!")
            return
        if not kullanici:
            await ctx.reply("❌ Kullanım: `!vip_sil @kullanici`")
            return

        await db.remove_vip(kullanici.id)
        await ctx.reply(f"ℹ️ {kullanici.mention} kullanıcısının VIP yetkisi silindi.")

    # =========================================================================
    # 👑 /vip_liste & !vip_liste
    # =========================================================================
    @app_commands.command(name="vip_liste", description="[Yetkili] Veritabanındaki aktif VIP üyeleri listeler.")
    async def cmd_list_vips_slash(self, interaction: discord.Interaction):
        if not await self.check_admin_perm(interaction.user.id):
            await interaction.response.send_message("❌ Bu komutu kullanmaya yetkiniz yok!", ephemeral=True)
            return

        vips = await db.list_vips()
        if not vips:
            await interaction.response.send_message("ℹ️ Şu an kayıtlı VIP kullanıcı bulunmuyor.", ephemeral=True)
            return

        embed = discord.Embed(title="👑 Kayıtlı VIP Kullanıcı Listesi", color=discord.Color.gold(), timestamp=datetime.now())
        lines = [f"• <@{v.get('user_id')}> (`{v.get('user_id')}`) - Bitiş: `{v.get('vip_expires_at') or 'Süresiz'}`" for v in vips]
        embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="vip_liste", aliases=["vipler", "listvip"])
    async def cmd_list_vips_prefix(self, ctx: commands.Context):
        if not await self.check_admin_perm(ctx.author.id):
            await ctx.reply("❌ Bu komutu kullanmaya yetkiniz yok!")
            return
        vips = await db.list_vips()
        if not vips:
            await ctx.reply("ℹ️ Şu an kayıtlı VIP kullanıcı bulunmuyor.")
            return

        lines = [f"• <@{v.get('user_id')}> - Bitiş: `{v.get('vip_expires_at') or 'Süresiz'}`" for v in vips]
        embed = discord.Embed(title="👑 Kayıtlı VIP Kullanıcı Listesi", description="\n".join(lines), color=discord.Color.gold())
        await ctx.reply(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))

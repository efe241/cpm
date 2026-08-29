import os
import re
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import aiosqlite

from config import (
    DATABASE_PATH,
    HITS_DIR,
    RESULTS_DIR,
    ADMIN_USER_IDS,
    VIP_ROLE_IDS,
    FREE_LIMIT,
    VIP_LIMIT,
    ADMIN_LIMIT
)

def sanitize_folder_name(name: str) -> str:
    """Dosya sistemi için geçersiz karakterleri temizler."""
    if not name:
        return "bilinmeyen_kullanici"
    clean = re.sub(r'[\\/*?:"<>|]', '_', name.strip())
    clean = re.sub(r'\s+', '_', clean)
    return clean or "kullanici"

class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path

    async def init_db(self):
        """Veritabanı tablolarını oluşturur."""
        async with aiosqlite.connect(self.db_path) as db:
            # VIP & Kullanıcı tablosu
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    is_vip INTEGER DEFAULT 0,
                    vip_expires_at TEXT,
                    added_by INTEGER,
                    created_at TEXT
                )
            """)
            # Yetkili / Panel Yöneticileri tablosu
            await db.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    added_by INTEGER,
                    created_at TEXT
                )
            """)
            # Tarama logları
            await db.execute("""
                CREATE TABLE IF NOT EXISTS scans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    scan_type TEXT,
                    total_count INTEGER,
                    valid_count INTEGER,
                    invalid_count INTEGER,
                    duration REAL,
                    created_at TEXT
                )
            """)
            # Hit kayıtları
            await db.execute("""
                CREATE TABLE IF NOT EXISTS hits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    email TEXT,
                    password TEXT,
                    uid TEXT,
                    level INTEGER,
                    total_cars INTEGER,
                    unlocked_cars INTEGER,
                    custom_cars INTEGER,
                    clan_id TEXT,
                    details_json TEXT,
                    created_at TEXT
                )
            """)
            await db.commit()

    async def is_admin_or_authorized(self, user_id: int) -> bool:
        """Kullanıcının Panel / Proxy yetkisi olup olmadığını kontrol eder."""
        # 1. config/env içindeki Root Adminler
        if ADMIN_USER_IDS and user_id in ADMIN_USER_IDS:
            return True

        # 2. Eğer ADMIN_USER_IDS hiç ayarlanmadıysa ilk aşamada yetki ver
        if not ADMIN_USER_IDS:
            return True

        # 3. Veritabanındaki yetkili yöneticiler
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            if row:
                return True
        return False

    async def add_admin(self, user_id: int, added_by: int) -> bool:
        """Kullanıcıya Panel & Proxy yönetim yetkisi tanımlar."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO admins (user_id, added_by, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO NOTHING
            """, (user_id, added_by, now))
            await db.commit()
            return True

    async def remove_admin(self, user_id: int) -> bool:
        """Kullanıcının Panel & Proxy yönetim yetkisini siler."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            await db.commit()
            return True

    async def list_admins(self) -> List[Dict[str, Any]]:
        """Yetkili yönetici listesini döndürür."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM admins")
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def is_vip(self, user_id: int, role_ids: Optional[List[int]] = None) -> bool:
        """Kullanıcının VIP veya Admin olup olmadığını kontrol eder."""
        if await self.is_admin_or_authorized(user_id):
            return True

        if role_ids:
            for r_id in role_ids:
                if r_id in VIP_ROLE_IDS:
                    return True

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT is_vip, vip_expires_at FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            if row and row["is_vip"] == 1:
                exp = row["vip_expires_at"]
                if exp:
                    try:
                        exp_date = datetime.strptime(exp, "%Y-%m-%d %H:%M:%S")
                        if datetime.now() <= exp_date:
                            return True
                        else:
                            await db.execute("UPDATE users SET is_vip = 0 WHERE user_id = ?", (user_id,))
                            await db.commit()
                            return False
                    except Exception:
                        return True
                return True
        return False

    def get_user_limit(self, user_id: int, is_vip: bool) -> int:
        """Kullanıcının taranabilir maksimum CPM limitini döndürür."""
        if user_id in ADMIN_USER_IDS:
            return ADMIN_LIMIT
        if is_vip:
            return VIP_LIMIT
        return FREE_LIMIT

    async def add_vip(self, user_id: int, added_by: int, days: Optional[int] = None) -> bool:
        """Kullanıcıya VIP yetkisi tanımlar."""
        expires_at = None
        if days and days > 0:
            expires_at = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO users (user_id, is_vip, vip_expires_at, added_by, created_at)
                VALUES (?, 1, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    is_vip = 1,
                    vip_expires_at = excluded.vip_expires_at,
                    added_by = excluded.added_by
            """, (user_id, expires_at, added_by, now))
            await db.commit()
            return True

    async def remove_vip(self, user_id: int) -> bool:
        """Kullanıcının VIP yetkisini kaldırır."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET is_vip = 0, vip_expires_at = NULL WHERE user_id = ?", (user_id,))
            await db.commit()
            return True

    async def list_vips(self) -> List[Dict[str, Any]]:
        """Kayıtlı aktif VIP listesini döndürür."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM users WHERE is_vip = 1")
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def record_scan(self, user_id: int, scan_type: str, total: int, valid: int, invalid: int, duration: float):
        """Tarama istatistiğini kaydeder."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO scans (user_id, scan_type, total_count, valid_count, invalid_count, duration, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, scan_type, total, valid, invalid, round(duration, 2), now))
            await db.commit()

    async def save_hit(self, user_id: int, acc: dict, username: Optional[str] = None):
        """Tekli hit kaydını veritabanına ve kullanıcının özel results klasörüne yazar."""
        await self.save_batch_hits(user_id, [acc], username=username)

    async def save_batch_hits(self, user_id: int, hits_list: List[dict], username: Optional[str] = None):
        """
        Toplu hitleri:
        1. SQLite veritabanına,
        2. Genel hits/ klasörüne,
        3. Kullanıcıya özel results/<username>/ klasörüne kaydeder.
        """
        if not hits_list:
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today_date = datetime.now().strftime("%Y-%m-%d")

        # 1. SQLite Kaydı
        async with aiosqlite.connect(self.db_path) as db:
            for acc in hits_list:
                email = acc.get("email", "")
                pwd = acc.get("password", "")
                uid = acc.get("uid", "")
                lvl = acc.get("cpm_level", 0)
                tot = acc.get("cpm_total_cars", 0)
                unl = acc.get("cpm_unlocked_cars", 0)
                cus = acc.get("cpm_custom_cars", 0)
                clan = acc.get("cpm_clan_id")
                details = json.dumps(acc, ensure_ascii=False)

                await db.execute("""
                    INSERT INTO hits (user_id, email, password, uid, level, total_cars, unlocked_cars, custom_cars, clan_id, details_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, email, pwd, uid, lvl, tot, unl, cus, clan, details, now_str))
            await db.commit()

        # 2. Genel hits/ Klasörüne Kayıt
        day_file = os.path.join(HITS_DIR, f"hitler_{today_date}.txt")
        all_file = os.path.join(HITS_DIR, "hitler_tum_gecmis.txt")
        detailed_file = os.path.join(HITS_DIR, f"detayli_hitler_{today_date}.txt")

        try:
            with open(day_file, "a", encoding="utf-8") as f_day, \
                 open(all_file, "a", encoding="utf-8") as f_all, \
                 open(detailed_file, "a", encoding="utf-8") as f_det:

                for acc in hits_list:
                    combo_line = f"{acc.get('email')}:{acc.get('password')}\n"
                    f_day.write(combo_line)
                    f_all.write(combo_line)

                    det_line = (
                        f"[{now_str}] User:{username or user_id} | {acc.get('email')}:{acc.get('password')} | "
                        f"Araç: {acc.get('cpm_total_cars', 0)} | Lvl: {acc.get('cpm_level', 0)} | UID: {acc.get('uid')}\n"
                    )
                    f_det.write(det_line)
        except Exception as e:
            print(f"⚠️ hits/ klasörüne yazılırken hata: {e}")

        # 3. 🎯 Kullanıcıya Özel results/<username>/ Klasörüne Kayıt
        target_user_folder = sanitize_folder_name(username or f"user_{user_id}")
        user_dir = os.path.join(RESULTS_DIR, target_user_folder)
        os.makedirs(user_dir, exist_ok=True)

        user_sade_file = os.path.join(user_dir, "calisanlar_sade.txt")
        user_gunluk_file = os.path.join(user_dir, f"calisanlar_{today_date}.txt")
        user_detayli_file = os.path.join(user_dir, "detayli_rapor.txt")

        try:
            with open(user_sade_file, "a", encoding="utf-8") as u_sade, \
                 open(user_gunluk_file, "a", encoding="utf-8") as u_gunluk, \
                 open(user_detayli_file, "a", encoding="utf-8") as u_det:

                for acc in hits_list:
                    combo_line = f"{acc.get('email')}:{acc.get('password')}\n"
                    u_sade.write(combo_line)
                    u_gunluk.write(combo_line)

                    u_det.write(f"=====================================================\n")
                    u_det.write(f"Tarih       : {now_str}\n")
                    u_det.write(f"Hesap       : {acc.get('email')}:{acc.get('password')}\n")
                    u_det.write(f"UID         : {acc.get('uid')}\n")
                    u_det.write(f"Seviye      : Level {acc.get('cpm_level')}\n")
                    u_det.write(f"Toplam Araç : {acc.get('cpm_total_cars')} adet (Açık: {acc.get('cpm_unlocked_cars')}, Garaj: {acc.get('cpm_custom_cars')})\n")
                    if acc.get("cpm_clan_id"):
                        u_det.write(f"Klan ID     : {acc.get('cpm_clan_id')}\n")
                    u_det.write(f"idToken     : {acc.get('idToken')}\n\n")

        except Exception as e:
            print(f"⚠️ results/{target_user_folder} klasörüne yazılırken hata: {e}")

    async def get_global_stats(self) -> Dict[str, Any]:
        """Tüm botun genel istatistiklerini getirir."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute("SELECT COUNT(*) as total_scans, SUM(total_count) as total_accs, SUM(valid_count) as total_hits, SUM(invalid_count) as total_fails FROM scans")
            scan_row = await cursor.fetchone()

            cursor = await db.execute("SELECT COUNT(*) as total_vips FROM users WHERE is_vip = 1")
            vip_row = await cursor.fetchone()

            cursor = await db.execute("SELECT COUNT(*) as total_admins FROM admins")
            admin_row = await cursor.fetchone()

            cursor = await db.execute("SELECT COUNT(*) as total_recorded_hits FROM hits")
            hit_row = await cursor.fetchone()

            return {
                "total_scans": scan_row["total_scans"] or 0,
                "total_accs": scan_row["total_accs"] or 0,
                "total_hits": scan_row["total_hits"] or 0,
                "total_fails": scan_row["total_fails"] or 0,
                "total_vips": vip_row["total_vips"] or 0,
                "total_admins": admin_row["total_admins"] or 0,
                "total_recorded_hits": hit_row["total_recorded_hits"] or 0,
            }

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Belirli bir kullanıcının istatistiklerini getirir."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                "SELECT COUNT(*) as scans, SUM(total_count) as total_accs, SUM(valid_count) as hits FROM scans WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            return {
                "scans": row["scans"] or 0,
                "total_accs": row["total_accs"] or 0,
                "hits": row["hits"] or 0,
            }

    async def get_recent_hits(self, limit: int = 10, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """En son bulunan hitleri listeler."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if user_id:
                cursor = await db.execute(
                    "SELECT * FROM hits WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                    (user_id, limit)
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM hits ORDER BY id DESC LIMIT ?",
                    (limit,)
                )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

# Global DB nesnesi
db = Database()

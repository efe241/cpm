import os
import re
import time
import random
import asyncio
from typing import Optional, List, Tuple, Dict, Any
import aiohttp

from config import (
    PROXIES_FILE,
    PROXY_TEST_URL,
    PROXY_TEST_TIMEOUT,
    APIFY_API_TOKEN,
    PROXY_API_URL,
    APIFY_PROXY_URL,
    BUILTIN_PROXY_SOURCES
)

# IP:PORT yakalayıcı regex deseni
IP_PORT_REGEX = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b')

class ProxyManager:
    """
    HTTP / HTTPS / SOCKS4 / SOCKS5 Küresel Proxy Yöneticisi.
    Dünya çapında 25+ farklı kaynaktan proxy çeker,
    otomatik paralel sağlık/hız testi yapar ve sadece çalışan hızlı proxyleri havuzda tutar.
    """
    def __init__(self, proxy_file: str = PROXIES_FILE):
        self.proxy_file = proxy_file
        self.proxies: List[str] = []
        self._index: int = 0
        self.load_proxies()

    def normalize_proxy(self, raw_proxy: str, default_protocol: str = "http") -> Optional[str]:
        raw_proxy = raw_proxy.strip()
        if not raw_proxy or raw_proxy.startswith("#"):
            return None

        if raw_proxy.startswith(("http://", "https://", "socks5://", "socks4://")):
            return raw_proxy

        parts = raw_proxy.split(":")
        if len(parts) == 4:
            ip, port, user, pwd = parts
            return f"{default_protocol}://{user}:{pwd}@{ip}:{port}"
        elif len(parts) == 2:
            ip, port = parts
            return f"{default_protocol}://{ip}:{port}"

        return f"{default_protocol}://{raw_proxy}"

    def load_proxies(self) -> int:
        loaded = []

        # 1. config/env içindeki APIFY_PROXY_URL varsa ilk sıraya ekle
        if APIFY_PROXY_URL:
            norm = self.normalize_proxy(APIFY_PROXY_URL)
            if norm:
                loaded.append(norm)

        # 2. proxies.txt dosyasını oku
        if os.path.exists(self.proxy_file):
            try:
                with open(self.proxy_file, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        p = self.normalize_proxy(line)
                        if p and p not in loaded:
                            loaded.append(p)
            except Exception as e:
                print(f"⚠️ Proxy dosyası okunurken hata: {e}")
        else:
            try:
                with open(self.proxy_file, "w", encoding="utf-8") as f:
                    f.write("# Proxylerinizi buraya her satıra bir adet gelecek şekilde yazabilirsiniz:\n")
                    if APIFY_PROXY_URL:
                        f.write(f"{APIFY_PROXY_URL}\n")
            except Exception:
                pass

        self.proxies = loaded
        self._index = 0
        return len(self.proxies)

    def save_proxies_to_file(self):
        """Mevcut havuzdaki çalışan proxyleri dosyaya kaydeder."""
        try:
            with open(self.proxy_file, "w", encoding="utf-8") as f:
                f.write("# Aktif Çalışan ve Test Edilmiş Küresel Proxy Listesi\n")
                for p in self.proxies:
                    f.write(f"{p}\n")
        except Exception as e:
            print(f"⚠️ Proxy dosyasına yazılırken hata: {e}")

    def get_proxy(self) -> Optional[str]:
        if not self.proxies:
            return None
        proxy = self.proxies[self._index % len(self.proxies)]
        self._index += 1
        return proxy

    def get_random_proxy(self) -> Optional[str]:
        if not self.proxies:
            return None
        return random.choice(self.proxies)

    def count(self) -> int:
        return len(self.proxies)

    async def test_single_proxy(
        self,
        session: aiohttp.ClientSession,
        proxy_url: str,
        test_url: str = PROXY_TEST_URL,
        timeout: float = PROXY_TEST_TIMEOUT
    ) -> Tuple[bool, float, Optional[str]]:
        """Tek bir proxy'nin çalışırlığını ve ping süresini (ms) test eder."""
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        start = time.time()
        try:
            async with session.get(test_url, proxy=proxy_url, timeout=client_timeout) as resp:
                if resp.status in (200, 204):
                    latency = round((time.time() - start) * 1000, 1)
                    return True, latency, None
                return False, 0.0, f"HTTP {resp.status}"
        except asyncio.TimeoutError:
            return False, 0.0, "Timeout"
        except Exception as e:
            return False, 0.0, str(e)

    async def test_and_filter_proxies(
        self,
        session: aiohttp.ClientSession,
        proxy_list: Optional[List[str]] = None,
        concurrency: int = 60
    ) -> Dict[str, Any]:
        """
        Verilen veya mevcut havuzdaki proxyleri yüksek eşzamanlılıkla (concurrency=60) paralel test eder.
        Çalışmayanları eler, çalışanları gecikmeye göre sıralayıp havuza alır.
        """
        targets = proxy_list if proxy_list is not None else list(self.proxies)
        if not targets:
            return {"total": 0, "working": 0, "failed": 0, "working_list": []}

        total_tested = len(targets)
        semaphore = asyncio.Semaphore(concurrency)
        working_results = []
        failed_count = 0

        async def worker(p):
            nonlocal failed_count
            async with semaphore:
                ok, lat, err = await self.test_single_proxy(session, p)
                if ok:
                    working_results.append({"proxy": p, "latency": lat})
                else:
                    failed_count += 1

        tasks = [worker(p) for p in targets]
        await asyncio.gather(*tasks)

        # En hızlıdan yavaşa sırala
        working_results.sort(key=lambda x: x["latency"])
        self.proxies = [item["proxy"] for item in working_results]
        self._index = 0
        self.save_proxies_to_file()

        return {
            "total": total_tested,
            "working": len(working_results),
            "failed": failed_count,
            "working_list": working_results
        }

    async def fetch_from_single_source(
        self,
        session: aiohttp.ClientSession,
        source: dict
    ) -> List[str]:
        """Tek bir küresel kaynaktan proxy metnini çeker ve regex ile IP:PORT ayrıştırır."""
        url = source["url"]
        proto = source.get("type", "http")
        proxies_found = []
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=6.0)) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    # Regex ile metindeki tüm IP:Port kombinasyonlarını yakala
                    matches = IP_PORT_REGEX.findall(text)
                    for ip_port in matches:
                        p = f"{proto}://{ip_port}"
                        proxies_found.append(p)
        except Exception:
            pass
        return proxies_found

    async def fetch_and_auto_test(
        self,
        session: aiohttp.ClientSession,
        max_test: int = 500,
        concurrency: int = 60
    ) -> Dict[str, Any]:
        """
        🌍 25+ farklı küresel internet kaynağından proxy çeker,
        hepsini paralel olarak test eder ve sadece çalışanları havuza ekler.
        """
        # 1. 25+ küresel kaynaktan paralel çekim
        tasks = [self.fetch_from_single_source(session, s) for s in BUILTIN_PROXY_SOURCES]
        if PROXY_API_URL:
            tasks.append(self.fetch_from_single_source(session, {"url": PROXY_API_URL, "type": "http"}))

        results = await asyncio.gather(*tasks)

        raw_all = []
        if APIFY_PROXY_URL:
            raw_all.append(self.normalize_proxy(APIFY_PROXY_URL))

        for r in results:
            raw_all.extend(r)

        # Tekilleştirme (Deduplication)
        unique_proxies = []
        seen = set()
        for p in raw_all:
            if p and p not in seen:
                seen.add(p)
                unique_proxies.append(p)

        total_fetched = len(raw_all)
        total_unique = len(unique_proxies)

        to_test = unique_proxies[:max_test]

        # 2. Hızlı Paralel Test
        test_summary = await self.test_and_filter_proxies(session, proxy_list=to_test, concurrency=concurrency)

        return {
            "sources_count": len(BUILTIN_PROXY_SOURCES),
            "total_fetched": total_fetched,
            "unique_fetched": total_unique,
            "tested": len(to_test),
            "working": test_summary["working"],
            "failed": test_summary["failed"],
            "working_list": test_summary["working_list"]
        }

    async def fetch_from_api(self, session: aiohttp.ClientSession, api_url: str) -> int:
        """Harici API'den çeker."""
        try:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10.0)) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    matches = IP_PORT_REGEX.findall(text)
                    added = 0
                    for ip_port in matches:
                        p = f"http://{ip_port}"
                        if p not in self.proxies:
                            self.proxies.append(p)
                            added += 1
                    if added > 0:
                        self.save_proxies_to_file()
                    return added
        except Exception as e:
            print(f"⚠️ Proxy API'den çekilirken hata: {e}")
        return 0

    async def fetch_from_apify(
        self,
        session: aiohttp.ClientSession,
        apify_token: Optional[str] = None
    ) -> int:
        token = apify_token or APIFY_API_TOKEN
        if not token:
            return 0

        apify_residential = f"http://groups-RESIDENTIAL:{token}@proxy.apify.com:8000"
        apify_datacenter = f"http://auto:{token}@proxy.apify.com:8000"

        added = 0
        for p in [apify_residential, apify_datacenter]:
            if p not in self.proxies:
                self.proxies.append(p)
                added += 1

        if added > 0:
            self.save_proxies_to_file()
        return added

# Global proxy manager nesnesi
proxy_mgr = ProxyManager()

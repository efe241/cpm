import os
import re
import random
import asyncio
import aiohttp
from typing import List, Optional, Tuple, Dict, Any

from config import (
    PROXIES_FILE_PATH,
    PROXY_TEST_TIMEOUT,
    PROXY_TEST_URL,
    BUILTIN_PROXY_SOURCES,
    APIFY_PROXY_URL
)

IP_PORT_REGEX = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b')

class ProxyManager:
    def __init__(self, file_path: str = PROXIES_FILE_PATH):
        self.file_path = file_path
        self.proxies: List[str] = []
        self._lock = asyncio.Lock()
        self.last_tested_count = 0

    def load_proxies(self) -> int:
        """proxies.txt dosyasından formatlayarak proxy listesini yükler."""
        if not os.path.exists(self.file_path):
            self.proxies = []
            return 0

        loaded = []
        with open(self.file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                matches = IP_PORT_REGEX.findall(line)
                if matches:
                    loaded.append(matches[0])
                else:
                    loaded.append(line)

        # Tekilleştir
        seen = set()
        clean = []
        for p in loaded:
            if p not in seen:
                seen.add(p)
                clean.append(p)

        self.proxies = clean
        return len(self.proxies)

    def save_proxies(self, proxy_list: List[str]):
        """Proxy listesini dosyaya kaydeder."""
        with open(self.file_path, "w", encoding="utf-8") as f:
            for p in proxy_list:
                f.write(f"{p}\n")
        self.proxies = list(proxy_list)

    def get_random_proxy(self) -> Optional[str]:
        """Havuzdan rastgele bir proxy döndürür."""
        if not self.proxies:
            return APIFY_PROXY_URL if APIFY_PROXY_URL else None
        p = random.choice(self.proxies)
        if not (p.startswith("http://") or p.startswith("https://") or p.startswith("socks5://") or p.startswith("socks4://")):
            return f"http://{p}"
        return p

    def count(self) -> int:
        return len(self.proxies)

    async def test_single_proxy(self, session: aiohttp.ClientSession, raw_proxy: str) -> Tuple[bool, str, float]:
        """Tek bir proxy'yi asenkron pingler."""
        p_formatted = raw_proxy
        if not (p_formatted.startswith("http://") or p_formatted.startswith("https://") or p_formatted.startswith("socks4://") or p_formatted.startswith("socks5://")):
            p_formatted = f"http://{p_formatted}"

        start = asyncio.get_event_loop().time()
        try:
            async with session.get(PROXY_TEST_URL, proxy=p_formatted, timeout=aiohttp.ClientTimeout(total=PROXY_TEST_TIMEOUT)) as resp:
                if resp.status == 200:
                    dur = round(asyncio.get_event_loop().time() - start, 2)
                    return True, raw_proxy, dur
        except Exception:
            pass
        return False, raw_proxy, 0.0

    async def test_and_filter_proxies(self, proxy_list: List[str], max_concurrency: int = 60) -> List[str]:
        """Verilen proxy listesini paralel test eder ve sadece çalışanları döndürür."""
        if not proxy_list:
            return []

        working_proxies = []
        semaphore = asyncio.Semaphore(max_concurrency)

        async with aiohttp.ClientSession() as session:
            async def bounded_test(p):
                async with semaphore:
                    ok, prx, _ = await self.test_single_proxy(session, p)
                    if ok:
                        working_proxies.append(prx)

            tasks = [bounded_test(p) for p in proxy_list]
            await asyncio.gather(*tasks)

        self.save_proxies(working_proxies)
        return working_proxies

    async def fetch_and_auto_test(self, custom_urls: Optional[List[str]] = None) -> Tuple[int, int]:
        """25+ küresel kaynaktan proxy çeker ve hızlıca test edip havuzu yeniler."""
        sources = list(BUILTIN_PROXY_SOURCES)
        if custom_urls:
            for u in custom_urls:
                sources.append({"name": "Özel Kaynak", "url": u, "type": "auto"})

        raw_found = []
        async with aiohttp.ClientSession() as session:
            async def fetch_source(src):
                try:
                    async with session.get(src["url"], timeout=aiohttp.ClientTimeout(total=5.0)) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            matches = IP_PORT_REGEX.findall(text)
                            return matches
                except Exception:
                    pass
                return []

            results = await asyncio.gather(*[fetch_source(s) for s in sources])
            for r in results:
                raw_found.extend(r)

        unique_raw = list(set(raw_found))
        if not unique_raw:
            return 0, 0

        # En hızlı 200 adedini test et
        sample = random.sample(unique_raw, min(200, len(unique_raw)))
        working = await self.test_and_filter_proxies(sample, max_concurrency=60)
        return len(unique_raw), len(working)

proxy_mgr = ProxyManager()

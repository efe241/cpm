# 🚗 Car Parking Multiplayer (CPM) Discord Checker Bot (V2 Modular)

Car Parking Multiplayer & Firebase hesaplarını hızlı, asenkron, proxy destekli ve detaylı bir şekilde kontrol eden Discord botu.

---

## 🌟 Öne Çıkan Özellikler

- 🚀 **Asenkron & Turbo Hız**: `aiohttp` bağlantı havuzuyla paralel yüksek performanslı tarama.
- 👑 **Rol & VIP Sistemi**:
  - **Free Üye Limiti**: 25 CPM
  - **VIP Üye Limiti**: 100 CPM
  - **Admin Limiti**: 500 CPM (veya limitsiz)
- 💾 **Otomatik Yerel Hit Kaydı (Local Hit Logger)**:
  - Bulunan tüm çalışan hesaplar hem SQLite veritabanına (`data/database.sqlite`) hem de `hits/` klasöründeki tarih bazlı dosyalara (`hits/hitler_YYYY-MM-DD.txt` & `hits/hitler_tum_gecmis.txt`) otomatik olarak arşivlenir.
- 🌐 **HTTP & SOCKS5 Proxy Desteği**:
  - `proxies.txt` üzerinden rotasyonlu proxy desteği ile Firebase rate limitlerini aşma.
  - `/proxy_yenile` ile botu kapatmadan proxy listesini canlı güncelleme.
- 🧩 **Modüler Cogs Mimarisi**: `cogs/checker.py`, `cogs/admin.py`, `cogs/stats.py`, `cogs/general.py`.
- 📊 **İstatistik & Geçmiş Paneli**: `/istatistik` ve `/son_hitler` komutları ile detaylı kullanım metrikleri.
- 📁 **İndirilebilir Çıktılar**: Toplu tarama bittiğinde çalışan hesapları otomatik olarak 3 formatta verir:
  1. `calisan_hesaplar_sade.txt` (`email:şifre` formatında)
  2. `detayli_rapor.txt` (Araç sayısı, seviye, garaj, UID dökümü)
  3. `detayli_rapor.json` (Kompakt tam JSON verisi)
- 🏆 **Otomatik Sıralama**: En çok aracı ve en yüksek seviyesi olan hesapları en üste sıralar.
- 🔒 **Gizlilik Desteği (Ephemeral)**: Şifrelerin sunucuda ifşa olmaması için sonuçları sorgulayan kişiye özel gönderebilir.

---

## 🛠️ Kurulum ve Çalıştırma

### 1. Bot Tokenini Ayarlama
`.env` dosyasını veya `config.py` dosyasını açıp bot tokeninizi yazın:
```env
DISCORD_TOKEN=MTE2ND...BOT_TOKENINIZ...
ADMIN_USER_IDS=123456789012345678
VIP_ROLE_IDS=987654321098765432
```

### 2. Gerekli Kütüphaneleri Yükleme
```bash
pip install -r requirements.txt
```

### 3. (Opsiyonel) Proxy Ekleme
`proxies.txt` dosyasını açıp her satıra bir adet proxy yazabilirsiniz (`http://user:pass@ip:port`, `socks5://ip:port`, `ip:port` vb.).

### 4. Botu Başlatma
`baslat.bat` dosyasına çift tıklayın veya terminalden çalıştırın:
```bash
python bot.py
```

---

## 🎮 Komut Listesi

| Komut | Yetki | Açıklama |
|---|---|---|
| `/check email: sifre:` | Herkes | Tek bir hesabı sorgular ve seviye, açık araç, modifiye garaj, ban, klan ve UID detaylarını gösterir. |
| `/toplu_kontrol dosya:` | Herkes | `.txt` dosyası yükleyerek toplu tarama yapar (Free: 25, VIP: 100). |
| `/quickcheck combo_metni:` | Herkes | Mesaj içine yapıştırılan hesapları anlık kontrol eder. |
| `/istatistik` | Herkes | Botun genel ve kişisel tarama verilerini, proxy durumunu ve bot uptime süresini gösterir. |
| `/son_hitler` | Herkes | Bulunan son çalışan hesap kayıtlarını listeler. |
| `/yardim` | Herkes | Komut kılavuzunu ve limit bilgilerini gösterir. |
| `/vip_ekle kullanici: gun:` | Admin | Bir kullanıcıya VIP yetkisi tanımlar (100 CPM limit). |
| `/vip_sil kullanici:` | Admin | Kullanıcının VIP yetkisini kaldırır (Free 25 limite düşer). |
| `/vip_liste` | Admin | Kayıtlı VIP üyeleri listeler. |
| `/proxy_yenile` | Admin | `proxies.txt` dosyasını botu kapatmadan yeniden yükler. |
| `!check email:şifre` | Herkes | Standart prefix komutu ile tekli kontrol. |

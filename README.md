# gnome-monitor-toggle

GNOME (Wayland) altında **tek bir monitörü kapatıp açmanızı** sağlayan küçük bir
araç. Windows'taki *"Yalnızca 1. ekranda göster"* seçeneğinin Ubuntu karşılığı
gibi düşünülebilir.

Hem basit bir **GTK4 arayüzü** (`monitor-ui`) hem de bir **komut satırı**
(`monitor`) içerir.

<p align="center"><em>GNOME Ayarlar → Ekranlar panelinde monitör kapatma
seçeneği yoktur; bu araç o boşluğu doldurur.</em></p>

## Neden gerekli?

- Wayland'de `xrandr` monitör kapatamaz (`BadMatch` hatası verir).
- GNOME'un **Ayarlar → Ekranlar** panelinde tek monitörü devre dışı bırakma
  anahtarı **yoktur**.
- Bu araç, GNOME'un kendi D-Bus arayüzünü (`org.gnome.Mutter.DisplayConfig`)
  kullanarak monitörü gerçekten kapatır.

## Ekran görüntüsü / arayüz

Arayüz, bağlı her monitör için bir anahtar gösterir:

```
┌───────────────────────────────────────────┐
│  Monitörler                    ⟳          │
│                                           │
│  Bağlı Monitörler                         │
│   DP-1                          [  ●]     │
│   DEL AW2521HFLA · 1920×1080 · birincil   │
│   DP-2                          [  ○]     │
│   ACI VG248 · 1920×1080 · kapalı          │
│                                           │
│  Seçenekler                               │
│   Kalıcı olarak hatırla         [  ○]     │
└───────────────────────────────────────────┘
```

## Gereksinimler

- GNOME 45+ (Wayland veya X11)
- Python 3 + `python3-gi`
- GTK4 ve libadwaita (yalnızca arayüz için)

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

## Kurulum

```bash
git clone git@github.com:anilsoylu/gnome-monitor-toggle.git
cd gnome-monitor-toggle
./install.sh              # CLI + arayüz
./install.sh --desktop    # ayrıca masaüstüne kısayol koyar
```

Kurulum; `monitorctl.py`, `monitor`, `monitor-ui` dosyalarını `~/.local/bin`
altına, uygulama simgesini de `~/.local/share/applications` altına kopyalar.

Kaldırmak için:

```bash
./uninstall.sh
```

## Kullanım — arayüz

Uygulamalar menüsünden **"Monitör Aç/Kapat"** ya da terminalden:

```bash
monitor-ui
```

- **DP-1 / DP-2**: monitör aç/kapat
- **Hepsini Aç**: tüm monitörleri geri getirir
- **Kalıcı olarak hatırla**: açıkken verdiğin ayar yeniden başlatınca da korunur

## Kullanım — komut satırı

```bash
monitor list                 # bağlı monitörler ve durumları
monitor off DP-1             # monitörü kapat (geçici)
monitor off DP-1 --persist   # yeniden girişte de kapalı kalsın
monitor on DP-1              # tek monitörü geri aç
monitor on                   # hepsini aç
```

Örnek çıktı:

```
Bağlı monitörler:
  * DP-1   DEL AW2521HFLA     AÇIK  1920x1080 (primary)
    DP-2   ACI VG248          kapalı 1920x1080
```

Monitor adını (connector) `monitor list` ile öğrenebilirsiniz: `DP-1`,
`DP-2`, `HDMI-A-1` vb.

## Nasıl çalışır?

`monitorctl.py` GNOME'un `org.gnome.Mutter.DisplayConfig` D-Bus arayüzünü
kullanır:

- `GetCurrentState` ile mevcut monitör düzenini okur.
- Kapatmadan önce **tam düzeni** `~/.cache/monitor-toggle.json` içine kaydeder.
- `ApplyMonitorsConfig` ile istenen monitörleri çıkarıp yeni düzeni uygular.

Kapalı bir monitörü geri açarken, kaydedilmiş düzen kullanılır; böylece konum,
ölçek ve **tazeleme hızı** (örn. 240 Hz) korunur.

Varsayılan olarak değişiklik **geçicidir**: oturumu kapatıp açtığınızda GNOME
kendi `monitors.xml` ayarına döner. Kalıcı istiyorsanız `--persist` kullanın
ya da arayüzde "Kalıcı olarak hatırla" anahtarını açın.

## Bilinen sınırlamalar

- Aynı monitörü (mirror) paylaşan birden fazla çıkış desteklenmez.
- Monitör kapalıyken düzenini GNOME Ayarlar'dan değiştirirseniz, kayıtlı düzen
  eski kalabilir. Çözüm: hepsini aç, yeniden düzenle, sonra tekrar kapat.
- En az bir monitör her zaman açık kalmalıdır.

## Lisans

MIT — bkz. [LICENSE](LICENSE).

---

<sub>English: A tiny GNOME/Wayland utility to turn individual monitors on and
off, since `xrandr` cannot do it on Wayland and GNOME Settings has no per-monitor
disable switch. Provides both a GTK4 GUI and a CLI.</sub>

# İsteğe bağlı: takvimin web sürümü

[English](web-dashboard.md)

Panelin başka bir şeye ihtiyacı yok. Takvimi tarayıcıda açılan bir sayfa olarak da istersen (claude.ai'de, sen paylaşmadıkça yalnızca sana açık), Claude aynı rakamlardan bir sayfa kurup zamanlanmış bir görevle güncel tutabilir. Bu kısım eklentiyle birlikte gelemez: sayfa senin claude.ai hesabında durur, görev de senin Claude Code'unda çalışır.

Sayfaya giden: günlük rakamların, limitlerin ve son bir günün oturum başlıkları ile kimlikleri. Bunların bilgisayarından çıkmasını istemiyorsan bu kısmı kurma.

Aşağıda `<SCRIPT>`, `scripts/collect_usage.py` dosyasının yoludur: bu deponun bir kopyasında ya da kurulu eklentinin klasöründe (`claude plugin list` nereden okunduğunu gösterir). Python'un adı `python` ise (Windows'ta çoğunlukla öyle) `python3` yerine onu kullan.

## 1. Rakamları bir klasöre yaz

```bash
python3 <SCRIPT> --out ~/.claude/usage-calendar-web
```

Bu, klasöre `daily.json`, `hours.json`, `sessions.json` ve `limits.json` yazar; `~` işaretini script kendisi açtığı için PowerShell ve cmd'de de çalışır. (`limits.json`, 3. adımdaki görev bir kez çalışana kadar boş kalır.)

## 2. Claude'dan sayfayı kurmasını iste

Masaüstü uygulamasında bir Claude Code oturumunda şöyle bir şey iste:

> `~/.claude/usage-calendar-web` klasöründeki JSON dosyalarından bir claude.ai panosu kur; her dosya için `daily`, `hours`, `sessions` ve `limits` adlı birer veri kaynağı olsun: `daily`'den GitHub tarzı günlük ısı haritası, `limits`'ten kullanım limitleri, `sessions`'tan aktif oturumlar, `hours`'tan saate göre istemler.

Claude sayfayı yayınlar ve bir bağlantı verir. O bağlantı senin `webUrl` ayarın.

## 3. Zamanlanmış görevle güncel tut

Claude'dan aşağıdaki metinle bir zamanlanmış görev kurmasını iste (ör. her sabah). `<DASHBOARD_URL>`, `<FOLDER>` (1. adımdaki klasör) ve `<SCRIPT>` yerlerini doldur; Claude'un göreve verdiği kimliği not al: o senin `webRefreshTask` ayarın.

İlk satırı olduğu gibi bırak. İstemi bu işaretle açılan oturum görevin kendi çalışmasıdır; takvim onu (ve alt ajanlarını) rakamlarından çıkarır. İşaretin bir mesajın başka bir yerinde geçmesi bir şey değiştirmez.

Görev metni İngilizce sürümdeki ile aynıdır: [web-dashboard.md](web-dashboard.md#3-keep-it-fresh-with-a-scheduled-task).

## 4. Paneli sayfaya bağla

`/config` altında eklentinin `webUrl` ayarına pano bağlantısını, `webRefreshTask` ayarına görev kimliğini yaz. Panelde **Web'de aç** ve **Web'i de güncelle** çıkar.

Zamanlanmış görevler Claude uygulaması açıkken çalışır; uygulama kapalıyken zamanı gelen görev, uygulamayı bir sonraki açışında çalışır. Görevi Auto modunda kaydet; yoksa adımlarını (`usage_raw.json` yazmak ve script'i çalıştırmak) onaylaman için durup bekler.

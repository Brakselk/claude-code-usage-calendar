<p align="center">
  <img src="docs/banner.svg" alt="Claude Code Kullanım Takvimi: bir yıllık günlük Claude Code kullanımı ısı haritası olarak; en çok kullanılan model, en yoğun ay, en uzun seri ve tahmini maliyet" width="100%">
</p>

<p align="center">
  <b>Claude Code kullanımının GitHub tarzı takvimi, sohbetin yanındaki yan panelde.</b><br>
  Günlük ısı haritası · canlı plan limitleri · oturum başına bağlam doluluğu · token ve tahmini maliyet
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="#kurulum">Kurulum</a> ·
  <a href="#neler-var">Neler var</a> ·
  <a href="#gizlilik">Gizlilik</a>
</p>

---

## Neler var

<img src="docs/panel.svg" alt="Panel: özet kutucuklar, ölçü ve renk seçimli günlük ısı haritası, kullanım limitleri ve aktif oturumlar" width="46%" align="right">

**Günlük aktivite ısı haritası.** Son 6 ya da 12 ay, her gün bir kare. Mesaj, istem, oturum, araç çağrısı ve token arasında geçiş yapabilirsin. Kareye gelince o günün sayısı görünür.

**Özet kutucuklar.** Aktif gün, mesaj, oturum, araç çağrısı, token, en çok kullandığın model, en yoğun ayın, en uzun ve şu anki serin.

**Canlı kullanım limitleri.** Planının 5 saatlik ve haftalık limitlerinden ne kadarının kullanıldığı ve ne zaman sıfırlanacağı. Rakamlar doğrudan Claude Code'dan gelir, sen çalıştıkça güncellenir.

**Oturum başına bağlam doluluğu.** Son 24 saatte kullanılan oturumlar ve masaüstü uygulamasında hâlâ açık duran son bir haftanın oturumları; her birinin bağlam penceresinin ne kadar dolu olduğu. İçinde olduğun oturum canlı güncellenir.

**Token detayları.** Giriş, çıkış ve toplam token; aynı kullanımın API liste fiyatlarıyla tahmini maliyeti.

**Günün saatlerine göre dağılım ve gün gün tablo**, her biri açılıp kapanan bir bölümde.

**Sana göre ayarlanır.** Tek tuşla İngilizce ya da Türkçe (`TR` / `EN`), yedi vurgu rengi; panel seçtiklerini hatırlar.

<br clear="right">

<p align="center">
  <img src="docs/colors.svg" alt="Yedi vurgu rengi: Clay, Ocean, Forest, Violet, Rose, Amber, Teal" width="100%">
</p>

> Yukarıdaki görseller uydurma örnek verilerle çizildi.

## Kurulum

**Claude Code 2.1.308 ya da üstü** ve **Python 3.7 ya da üstü** gerekir (`python3`, `python` ya da `py` komutlarından biri). Panel grafikleri Claude masaüstü uygulamasında çizer; terminalde kutucukları, tabloları ve limitleri gösterir, grafikleri ise tek satırlık bir yazıyla anlatır.

Claude Code terminal oturumunda:

```
/plugin install usage-calendar --marketplace Brakselk/claude-code-usage-calendar
```

Pazar yerini eklemek için `y`, ardından bir kapsam seç (Enter kullanıcı kapsamını alır). Ya da kabuktan:

```bash
claude plugin install usage-calendar --marketplace Brakselk/claude-code-usage-calendar
```

Masaüstü uygulamasında `/plugin` çalışmaz: istem kutusunun yanındaki **+**'ya, sonra **Plugins**'e tıkla; **Add marketplace** ile `Brakselk/claude-code-usage-calendar` ekle, ardından **Add plugin**.

## Kullanım

- Panel, oturum bir pencerede (masaüstü uygulamasında ya da terminalde) açıldığında kendiliğinden açılır. × onu o oturum için kapatır; eklenti yeniden yüklense de kapalı kalır. Yeniden açmak için mesaj kutusuna `/` yaz ve komut menüsünden `/usage-calendar`ı seç. Mesaj kutusunun altındaki durum satırı bu komutu hatırlatır ve 5 saatlik ile haftalık limitlerini gösterir (oturumdaki ilk yanıta kadar önceki bir oturumun son okumasını gösterir).
- **Refresh / Yenile** (panel klavyedeyken `R`) kullanımı yeniden sayar. Ayrıca tuttuğu rakamlar 30 dakikadan eskiyse kendiliğinden yenilenir. Bu, oturum bir pencerede açıldığında ve her 30 dakikada bir denetlenir; sayımı aynı anda yalnızca bir açık oturum çalıştırır.
- **TR / EN** dili, **Renk** yanındaki noktalar vurgu rengini değiştirir; bölüm başlıkları bölümü açıp kapatır.

## Ayarlar

İkisi de isteğe bağlı ve varsayılan olarak boş. Claude Code terminal oturumunda şununla ayarlanır:

```
/plugin configure usage-calendar@claude-code-usage-calendar
```

Ya da kabuktan kurarken ayarlanır:

```bash
claude plugin install usage-calendar --marketplace Brakselk/claude-code-usage-calendar --config webUrl=<bağlantı> --config webRefreshTask=<görev-kimliği>
```

Kabukta `claude plugin configure usage-calendar@claude-code-usage-calendar` ayarları ve hangilerinin boş olduğunu listeler; `--values-stdin` ile stdin'den okunan bir JSON nesnesindeki değerleri kaydeder.

| Ayar | Ne yapar |
|---|---|
| `webUrl` | Panonun web sürümünün bağlantısı. Panelde **Web'de aç** bağlantısı çıkar. |
| `webRefreshTask` | O web sürümünü yenileyen Claude Code zamanlanmış görevinin kimliği (id). **Web'i de güncelle** düğmesi çıkar. |

Web sürümünün nasıl kurulacağı [docs/web-dashboard.tr.md](docs/web-dashboard.tr.md) dosyasında.

## Gizlilik

- Her şey senin bilgisayarında çalışır. Panel Claude Code'un `~/.claude` altındaki kendi dosyalarını (oturum dökümleri ve `stats-cache.json`) ve masaüstü uygulamasının oturum listesini okur, rakamları eklentinin yerel deposunda tutar. Panel hiçbir şey yüklemez. Yalnızca isteğe bağlı web panosu ([docs/web-dashboard.tr.md](docs/web-dashboard.tr.md)) rakamları, oturum başlıklarını ve oturum kimliklerini claude.ai'de, sen paylaşmadıkça yalnızca sana açık bir sayfaya koyar.
- Script mesajları, istemleri, araç çağrılarını ve tokenları saymak için döküm satırlarını bellekte okur, oturum başlıklarını da okur. İstem metnine yalnızca iki şey için bakar: senin yazdığın istemleri sistem satırlarından ayırmak ve isteğe bağlı web yenileme görevinin kendi oturumlarını rakamlardan çıkarmak için `[usage-calendar-refresh]` işaretini bulmak. Mesaj metnini hiçbir zaman saklamaz, yazdırmaz ya da yüklemez: çıktısında rakamlar, model adları, oturum kimlikleri ve oturum başlıkları bulunur.
- Limitler ve bağlam doluluğu eklenti arayüzü üzerinden doğrudan Claude Code'dan gelir.

## Rakamlar nasıl sayılıyor

- **Mesaj**, bir oturumda senin ve Claude'un yazdığı her satırdır, araç sonuçları dahil. **İstem** yalnızca senin yazdığın mesajlardır. Claude Code bir satırı senin yazdığın olarak işaretlediyse (`origin` alanı) script bu işareti kullanır; işareti olmayan satırlar metinlerine göre ayırt edilir.
- **Token**, her yanıtın girişi, önbellek yazma ve okuması ile çıkışının toplamıdır; her yanıt bir kez sayılır.
- **Tahmini maliyet** model başına API liste fiyatlarını kullanır; önbellek yazma, giriş fiyatının 1,25 (5 dakika) ya da 2 (1 saat) katıdır. Abonelik planlarında bu ayrıca ödenmez; aynı kullanımın API'de ne tutacağını gösterir.
- Claude Code eski dökümleri bir süre sonra siler. O günler için yalnızca `stats-cache.json`'daki toplamlar kalır ve bunlar dökümlerle aynı biçimde sayılmaz. Bu yüzden script bu toplamları, ikisinin de bulunduğu günlerde ölçülen oranla ölçekler, giriş/çıkış dağılımlarını genel oranlarından tahmin eder ve o günleri tahmini olarak işaretler. Günün saatlerine göre dağılım yalnızca dökümleri duran günleri kapsar.

## Geliştirme

```bash
claude plugin validate .
claude plugin test .
python -m unittest discover -s tests -p "test_*.py"
```

İlki manifest ve hook'ları denetler, ikincisi panelin testlerini, üçüncüsü veri script'inin testlerini çalıştırır.

## Sınırlar

- Yalnızca bu bilgisayardaki Claude Code oturumları sayılır. claude.ai sohbetleri ve diğer bilgisayarlar dahil değildir.
- Panelin dayandığı eklenti arayüzü erken erişimdedir; Claude Code sürümleri arasında değişebilir.
- Fiyatlar `scripts/collect_usage.py` içinde sabittir; liste fiyatları değişince güncellenmeleri gerekir.

## Emeği geçenler

[Brakselk](https://github.com/Brakselk) tarafından, [Claude Code](https://claude.com/claude-code) ile birlikte yapıldı.

## Lisans

[MIT](LICENSE)

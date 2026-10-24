# İsteğe bağlı: takvimin web sürümü

[English](web-dashboard.md)

Panelin başka bir şeye ihtiyacı yok. Takvimi tarayıcıda açılan bir sayfa olarak da istersen (claude.ai'de, sen paylaşmadıkça yalnızca sana açık), Claude aynı rakamlardan bir sayfa kurup zamanlanmış bir görevle güncel tutabilir. Bu kısım eklentiyle birlikte gelemez: sayfa senin claude.ai hesabında durur, görev de senin Claude Code'unda çalışır.

Sayfaya giden: günlük rakamların ve saate göre istemlerin, limitlerin, son 24 saatte kullanılan oturumlarla masaüstü uygulamasında hâlâ açık duran son bir haftanın oturumlarının başlıkları ve kimlikleri. Bunların bilgisayarından çıkmasını istemiyorsan bu kısmı kurma.

Aşağıda `<SCRIPT>`, `scripts/collect_usage.py` dosyasının yoludur. Eklentiyi GitHub'dan kurduysan pazar yeri klasöründeki kopyayı kullan; onun yolu güncellemelerde değişmez:

- macOS ve Linux: `~/.claude/plugins/marketplaces/claude-code-usage-calendar/scripts/collect_usage.py`
- Windows: `%USERPROFILE%\.claude\plugins\marketplaces\claude-code-usage-calendar\scripts\collect_usage.py` (PowerShell'de `%USERPROFILE%` yerine `$env:USERPROFILE`)

`CLAUDE_CONFIG_DIR` ayarlıysa `~/.claude` yerine o klasör geçerlidir. Bu deponun bir kopyasını da kullanabilirsin. `claude plugin list --json` komutunun verdiği `installPath` yolunu kullanma: sonunda eklentinin sürümü vardır ve her güncellemede değişir. Python'un adı `python` ise (Windows'ta çoğunlukla öyle) `python3` yerine onu kullan.

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

Görev metni İngilizce kalır; yer tutucuları doldurup gerisini olduğu gibi kullan.

```text
[usage-calendar-refresh]
Refresh the Claude Code Usage Calendar dashboard at <DASHBOARD_URL>. Do only these steps and change nothing else. If a step fails, stop and say in one line which step it was.

1. Load the tools with ToolSearch: "select:mcp__ccd_session_mgmt__get_usage,ArtifactData".
2. Call mcp__ccd_session_mgmt__get_usage with no arguments. If plan.status is "ok", write the JSON it returns, unchanged, to <FOLDER>/usage_raw.json with the Write tool.
3. Run: python3 <SCRIPT> --out <FOLDER>
4. Upload each of daily.json, hours.json, sessions.json and limits.json from <FOLDER> to the dashboard with its own Artifact call (url: <DASHBOARD_URL>, asset: true), and note each new "/_blob/<id>" address.
5. Read the dashboard's datasets (ArtifactData action "list", collection "datasets") and note each one's version and current source.url.
6. In one ArtifactData "batch", update the datasets daily, hours, sessions and limits so each source is its new file ({"kind": "file", "url": "<new /_blob/ address>", "name": "<file name>"}) and its updated field is {"at": "<now, ISO 8601>", "by": "Scheduled task"}, pinned with if_version.
7. If the batch succeeded, delete the four old files (Artifact action "delete", path: the 32-character id from each old source.url).
8. Finish with one line: how many days and sessions were uploaded.
```

## 4. Paneli sayfaya bağla

`webUrl` ayarına pano bağlantısını, `webRefreshTask` ayarına görev kimliğini yaz. Claude Code terminal oturumunda:

```
/plugin configure usage-calendar@claude-code-usage-calendar
```

Ya da kabuktan (bash ya da PowerShell):

```bash
echo '{"webUrl": "<DASHBOARD_URL>", "webRefreshTask": "<TASK_ID>"}' | claude plugin configure usage-calendar@claude-code-usage-calendar --values-stdin
```

Panelde **Web'de aç** ve **Web'i de güncelle** çıkar. İkisi eklentiyi kurarken de ayarlanabilir; bkz. [Ayarlar](../README.tr.md#ayarlar).

Zamanlanmış görevler Claude uygulaması açıkken çalışır; uygulama kapalıyken zamanı gelen görev, uygulamayı bir sonraki açışında çalışır. Görevi Auto modunda kaydet; yoksa adımlarını (`usage_raw.json` yazmak ve script'i çalıştırmak) onaylaman için durup bekler.

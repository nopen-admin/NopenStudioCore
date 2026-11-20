# Python referansından C# motoruna geçiş

W001–W003 Python CLI, SQLite davranışı ve sahte platform testleri referans olarak kalır. W004A iş motoru ayrı `--state DIR` dizininde, ayrı JSON şemasıyla çalışır. Python SQLite yolunu kendiliğinden bulmaz ve oraya yeni motor durumu yazmaz.

## W003 SQLite envanteri

Uygulama kimliği `0x4E534343`, şema sürümü 2. Python varsayılan olarak `XDG_STATE_HOME/nopen-studio-core/memory.sqlite3` veya ev dizinindeki karşılığını WAL ile kullanır.

| Tablo | Alanlar ve sözleşme |
| --- | --- |
| `control` | `id, mode`. `STOPPED/PAUSED/READY` kuyruk kipi. |
| `permissions` | `capability, decision`. Yerel bildirim tercihleri. OS izni taşımaz. |
| `tasks` | `id, goal, state, summary, unknowns, next_step, priority, deadline`. |
| `events` | `seq, occurred_at, task_id, kind, source, detail`. Eklemeli, JSON detay. |
| `actions` | `seq, id, task_id, kind, payload, status`. Tekil eylem kimliği, JSON istek, kuyruk sonucu. |
| `checkpoints` | `action_id, task_id, event_seq, snapshot`. İşlemsel yazım ve JSON görev anlık görüntüsü. |

## Salt okunur kurgu okuyucusu

Linux’ta ayrı adla oluşturulmuş, kapanmış kurgu SQLite yedeğini kullanın.

```bash
Nopen.Buddy.Cli --sqlite-copy /path/w003-fixture.sqlite3 status
Nopen.Buddy.Cli --sqlite-copy /path/w003-fixture.sqlite3 export
Nopen.Buddy.Cli --sqlite-copy /path/w003-fixture.sqlite3 handoff fixture
```

Okuyucu SQLite `READONLY` ve `immutable=1` kullanır. WAL başlığı, yan dosya, varsayılan `memory.sqlite3` adı, uyumsuz sürüm ve bütünlük hatası reddedilir. Yedeği SQLite backup ile, ayrı bir dosyada `journal_mode=DELETE` olarak hazırlayın. Kaynak dosyayı kopyalamak tek başına yeterli sayılmaz. Okuyucunun kendi `nopen-buddy-w003-readonly-v1` JSON şeması vardır. `handoff` görev, sıralı geçmiş ve son kontrol noktasını verir. Çıktı Python dışa aktarım biçiminin birebir yerine geçmez. Hiçbir izin tercihi C# eylemine onay olarak aktarılmaz.

Okuma yolu Linux `libsqlite3.so.0`, JSON SQL fonksiyonları ve `pragma_table_list` içeren SQLite 3.38+ kullanır. Statik P/Invoke kaynak üretilir ve Native AOT ile sınanmıştır. Konsol motoru bu kütüphaneyi yalnız SQLite alt komutlarında yükler. Windows sağlayıcı seçimi ayrıca değerlendirilir.

## Yazma geçişi için sonraki adım

Yazma geçişi için ayrı yetki gerekir. Durdurulmuş kurgu veri üzerinde yedek, checksum, kayıt sayıları, olay sırası, görev/eylem/izin alan eşlemesi ve her kontrol noktasının doğrulanması gerekir. İlk gerçek kullanıcı verisi geçişi öncesi bağımsız onay, tek yazıcı planı, geri dönüş testi ve veri kaybı senaryosu hazırlanmalı.

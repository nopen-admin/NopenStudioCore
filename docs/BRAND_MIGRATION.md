# Nopen Buddy marka geçişi

W002 kullanıcıya dönük adı Nopen Buddy yapar. Önceki ad Nopen Studio Core, W001’in teknik geçmişini tanımlar. Ürün kararı ve kapsam için [Issue #4](https://github.com/nopen-admin/NopenStudioCore/issues/4) ve [Issue #5](https://github.com/nopen-admin/NopenStudioCore/issues/5).

| W001 envanteri | W002 davranışı |
| --- | --- |
| `nopen-admin/NopenStudioCore`, `nopen_core` ve `nopen` | Aynı depo, Python yolu ve çalıştırılabilir komut. |
| `init`, `status`, `run [--once]`, `pause`, `resume`, `stop`, `handoff`, `export`, `revoke`, `doctor`, `simulate-intervention`, `task` alt komutları | Mevcut argümanlar ve çıkış kodları geçerli. Yardım ve kurulum bildirimi Nopen Buddy adını kullanır. |
| `status.mode` ve W001 izin kayıtları | `mode` kuyruk kipidir. Yeni `active_mode` ürün modudur. Eski JSON alanları ve `nopen-core-memory-v1` dışa aktarım biçimi korunur. |
| `nopen-studio-core/memory.sqlite3` | Mutlak `XDG_STATE_HOME` altında, aksi halde `~/.local/state` altında aynı yol. WAL yan dosyaları ve `runner.lock` aynı konumda. |
| SQLite uygulama kimliği, şema v2, görevler, olaylar, eylemler, izinler ve kontrol noktaları | W002 şema geçişi veya veri kopyası gerektirmez. W001 izin kayıtları ve karar değerleri korunur. |
| `contrib/nopen-core.service` | Aynı birim adı ve başlatma komutu. Görünen açıklama Nopen Buddy adını kullanır. |
| W001 testleri | Önceki senaryolar korunur. Yeni mod okuma yolları erişim testine eklenir. |

## Sonraki teknik ad değişikliği

Depo, komut, modül veya durum yolu değişirse bunu ayrı ve onaylı bir geçiş olarak tasarlayın. Yeni komut eklenirse eski giriş noktasını uyumluluk takma adı olarak koruyun. Veri yolu değişirse önce eski kurulumu tespit edin ve çalışan kuyruğu durdurun. Doğrulanabilir bir SQLite yedeği ve geri dönüş planı oluşturduktan sonra tek hedef duruma geçin. İki ayrı yazılabilir kopya açılmasını engelleyin. Hem eski verinin okunmasını hem başarısız geçişten geri dönüşü test edin.

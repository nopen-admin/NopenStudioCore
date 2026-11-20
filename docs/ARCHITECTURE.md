# Mimari

- `nopen` ve `nopen_core/cli.py` komutları ayrıştırır, Türkçe ilk kurulum bildirimini sunar ve JSON üretir. `doctor` durum veritabanını açmaz.
- `nopen_core/store.py` kullanıcıya ait yerel durum yolunu, uygulama kimliğini ve şema sürümünü doğrular. SQLite WAL, `synchronous=FULL`, yabancı anahtarlar ve işlemli şema yükseltmesi kullanır.
- `nopen_core/core.py` görev bağlamını, izin kararlarını, eklemeli olayları ve kontrol noktası kuyruğunu yönetir. Olay kaynağı `human`, `scheduler` veya `simulation` olabilir.

## İşlem ve kurtarma

Kuyruk FIFO çalışır. Yalnızca `PENDING` ve `RUNNING` görevlerin bekleyen işlemleri seçilir. Görev durumları `PENDING`, `RUNNING`, `PAUSED`, `BLOCKED`, `DONE` ve `FAILED` değerlerini alabilir. Çalıştırıcı kipi görev durumundan bağımsızdır.

Çalıştırıcı için tek süreçlik `flock` alınır. SQLite yazma işlemi içinde kip tekrar okunur ve tek eylem seçilir. Görev durumu, olay, kontrol noktası ve eylemin tamamlandı işareti birlikte kaydedilir. `pause` ve `stop` aynı yazma kilidiyle sıralanır. Önceden girilmiş bir SQLite işlemi tamamlanabilir. Duraklatma veya durdurma işlemi kaydedildikten sonra sonraki eylem başlayamaz.

Süreç öldürülürse kilit OS tarafından bırakılır. Tamamlanmamış işlem SQLite tarafından geri alınır. Kullanıcının sonraki `run` çağrısı sırayı yeniden açar veya kalıcı duraklatmaya uyar. Aynı eylem kimliği, görev ve içerik tekrar verilirse mevcut kayıt döner. Farklı istekle aynı kimlik reddedilir.

## Bağlam

Görev kaydı amaç, özet, bilinmeyenler, sonraki adım, öncelik ve son tarih taşır. `handoff` bu bilgileri olay geçmişindeki kanıtlar, son kesin durum, son insan onayı ve son insan kararıyla birleştirir. Kullanıcı özeti güncelleyebilir. Kontrol noktası, o andaki bağlamın kopyasını oluşturur. Kanıt ve kararlar ayrı eklemeli olay kayıtlarında ve varsa önceki kontrol noktalarında korunur. Metin üreten bir model kullanılmaz.

İlk izin bildirimi sonucu iki kapsam için ayrı yerel kayıt halinde tutulur. `ACKNOWLEDGED`, `DECLINED` ve `REVOKED` değerleri bildirim tercihini açıklar. P1’de OS yetkisi, süreli ekran izni ve portal oturumu yoktur.

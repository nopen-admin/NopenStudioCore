# Gizlilik

Kalıcı dosyalar `${XDG_STATE_HOME}/nopen-studio-core` altında tutulur. Ortam değişkeni yoksa veya göreli ise `~/.local/state/nopen-studio-core` kullanılır. Bu dizinde SQLite veritabanı, geçici SQLite yan dosyaları ve çalıştırıcı kilit dosyası bulunabilir.

Görev alanlarına yazdığınız metin, kanıt referansı, insan kararı, izin bildirimi tercihi, zaman damgası ve kontrol noktaları yerel hafızaya kaydedilebilir. Uygulama şifre, token, işletim sistemi terminal geçmişi, ekran, pano veya ses verisi toplamak için kaynak açmaz. Kullanıcının göreve elle girdiği metin SQLite’da düz metin olarak saklanır. Hassas verileri göreve eklemeyin.

`nopen export` tüm hafızayı standart çıktıya verir. Terminal, yönlendirme ya da çağıran süreç bu çıktıyı saklayabilir. `revoke` tercih kaydını günceller, olay geçmişini silmez. Prototipte veri silme veya JSON içe aktarma komutu yoktur. Yerel kayıtları taşıma ve doğrulanmış ayrı ortam yedekleri P4 kapsamındadır.

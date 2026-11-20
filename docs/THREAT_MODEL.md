# W001 tehdit modeli

Korunan varlıklar görev metni, kanıt, insan kararları, izin kayıtları ve kontrol noktalarıdır. Güvenilen bileşenler kullanıcı oturumu, Linux dosya izinleri, Python ve SQLite’dır. Durum dizininin üst dizinleri kullanıcı veya işletim sistemi tarafından yönetilmelidir. Yerel dosya sistemi ve aynı kullanıcıya bağlı CLI çağrıları öngörülür.

| Tehdit | W001 önlemi | Sınır |
| --- | --- | --- |
| Süreç çökmesi veya aynı isteğin yeniden gönderimi | Durum, olay ve kontrol noktası tek SQLite işleminde yazılır. Aynı eylem kimliği aynı istek için mevcut sonucu verir. | Haricî yan etkiler bu kuyruğun parçası değildir. |
| İki çalıştırıcı veya duraklatma yarışı | `flock` ve SQLite yazma işlemi ile tek eylem kabulü. | Kaydedilmekte olan işlem tamamlanabilir. Fiziksel insan etkinliği P1’de algılanmaz. |
| Yanlış dosya, hatalı sürüm veya bozuk SQLite | Uygulama kimliği, sürüm ve yerel izin denetimi. Hatalı işlem geri alınır. | Disk hasarı, kötü niyetli aynı UID, root, değiştirilmiş çalıştırıcı ve dijital adli inceleme bu korumanın dışındadır. |
| Görev metninden komut veya veri sızıntısı | Parametreli SQL, sabit komutlar, JSON çıktısı. Kaynak metni dereference edilmez veya çalıştırılmaz. | Bilerek hassas veri girmek veya JSON çıktısını başka yere göndermek kullanıcı eylemidir. |
| Gizli masaüstü erişimi veya ağ bağlantısı | Uygulamada masaüstü adaptörü, subprocess veya ağ istemcisi bulunmaz. `doctor` destek dosyalarına ve ortam işaretlerine bakar. | P1 çekirdeği dışındaki Python/OS değişiklikleri ve çağıran ortamın ağ eylemleri bu uygulamanın kontrolünde değildir. |
| Başka yerel kullanıcı tarafından durum okuma | Özel dizin/dosya kipleri ve sahiplik denetimi. Durum dosyası ve yan dosyalarda sembolik bağlantılar reddedilir. | İçerik şifrelenmez. Sistem yedeği ve kullanıcı tarafından alınan kopyalar ayrı korunmalıdır. |

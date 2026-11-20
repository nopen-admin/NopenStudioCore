# Nopen Buddy modları

| Kimlik | Mod | W002 durumu |
| --- | --- | --- |
| `operator` | Operator Buddy | Varsayılan. Konsol ve W001 kontrol noktası kuyruğu çalışır. |
| `companion` | Companion Buddy | NOT IMPLEMENTED. Seçim kod 1 ile çıkar ve yerel hafızayı açmaz. |

`nopen modes` kuruluma ihtiyaç duymadan çalışma modlarını ve yetenek durumlarını listeler. `nopen status` içindeki `active_mode` ürün modunu, mevcut `mode` ise kuyruk kipini gösterir. İsteğe bağlı `nopen --mode operator <komut>` sözdizimi mevcut komutları korur. Global seçici alt komuttan önce gelir. Örneğin `nopen --mode companion run --once` açıkça reddedilir. Mod seçimi komut çağrısına aittir. Hafızaya tercih yazılmaz.

## Ortak hafıza ve güvenlik

İki arayüzün hedefi aynı SQLite görevlerini, kanıtlarını, insan kararlarını ve kontrol noktalarını kullanmaktır. Operator Buddy bugün mevcut W001 hafızası ve tek çalıştırıcı kilidiyle çalışır. Companion Buddy geliştiğinde aynı işlem sınırları ve denetim günlüğünden geçer. Sosyal karakter, kendi kendine izin veremez, insan kararını değiştiremez veya denetim kaydını atlayamaz. Riskli isteklerde işlem başına açık insan onayı gerekir.

| Yetenek | W002 durumu | Gelecekteki izin kapsamı |
| --- | --- | --- |
| `screen-read` | Kapalı | Yalnız kullanıcının seçtiği yüzey. |
| `input-control` | Kapalı | Ayrı fare/klavye kontrol izni. W001’deki kayıt anahtarı `screen-control`. |
| `microphone` | Kapalı | Dinleme oturumu için ayrı, görünür onay ve kapatma. |
| `audio-output` | Kapalı | Konuşma ve efektler için bağımsız kullanıcı tercihi. |
| `network` | Kapalı | Bağlantı amacı ve hedefi açıklanarak ayrı onay. |

`nopen modes` bu yetenekleri `NOT IMPLEMENTED` ve `os_access: false` olarak gösterir. W001 `init` bildirimi ve `revoke` yalnız mevcut yerel tercih kayıtlarını işler. Gelecekte ayrı erişimler için kapsam, süre, canlı gösterge ve bağımsız iptal tanımlanır. Varsayılan ağsız çalışma ilkesine uyulur.

## Duraklatma ve kapatma

`pause` yeni kuyruk işlemlerini bekletir. `stop` kuyruk kabulünü kapatır ve açık çalıştırıcıyı durdurur. Kaydedilmiş bağlam, kanıt ve kontrol noktaları sonraki başlatmaya taşınır. Önceden başlamış işlemin atomik yazımı tamamlanabilir. Gelecekte kullanıcı Companion Buddy’yi gizleyebilir veya tamamen kapatabilir. Kapatma Companion sensörünü, sesi, animasyonu ve izinli işlemleri sonlandırır. Uygulama genelinde durdurma kuralı her iki arayüzden gelen işlemlere uygulanır.

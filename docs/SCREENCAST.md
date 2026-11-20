# Nopen Buddy gözlem sözleşmesi

W003, olay tabanlı Operator çalışma döngüsünü ve salt okunur gözlemci sözleşmesini sağlar. Yerel D-Bus/PipeWire taşıyıcısı **NOT IMPLEMENTED**. Fedora’da gerçek yakalama **NOT TESTED**. CLI’daki gözlem durumu `UNAVAILABLE` ve `active: false` değerlerini gösterir. Enjekte edilen taşıyıcı yalnız kurgu testleri çalıştırır.

## Kuyruk ve durdurma

`nopen run`, kullanıcıya ait `0600` FIFO üzerinde bloklanır. CLI değişikliği SQLite’ta kaydettikten sonra tek bayt ile çalıştırıcıyı uyandırır. Bayt bir bildirimdir. Görev, eylem kimliği, kuyruk kipi ve güvenlik olayları SQLite’ta kalır. Bildirim doluysa, alıcı yoksa veya eski CLI ile komut işlenmişse bir sonraki zamanlı denetim doğru durumu okur. Varsayılan 30 saniye, `run --check-interval` ile değiştirilebilir. W001 `run --once`, tek aktif çalıştırıcı, WAL, FIFO görev sırası ve işlemsel tekrar gönderim davranışı korunur.

Simülasyonda `pause`, `stop`, müdahale olayı, `observe stop` ve `revoke screen-read|all` aktif gözlem oturumunu kapatır. Kısa bir `pause` ardından gelen `resume` gözlemi otomatik yeniden açmaz. Bekleyen SQLite eylemleri önceki atomik işlem sınırına uyar. Gerçek bir taşıyıcı eklenirse portal olayları aynı döngüyü beklemeden uyandırmalı ve kapanış sinyali geldiği anda kare tüketimini kesmelidir.

## Portal taşıyıcısı sözleşmesi

1. Komutun açık yerel onayını alın. W001 ilk kurulum bildirimi yalnız yerel tercih kaydıdır. Portal izni yalnız kullanıcının görünür sistem seçicisinde bir pencereyi onaylamasıyla geçerli olur.
2. Oturum D-Bus bağlantısında önce `CreateSession`, sonra `SelectSources` ve `Start` kullanın. `types=2` tek pencereyi, `multiple=false` bir kaynağı, `persist_mode=0` geçici izni ifade eder. Kalıcı izin veya geri yükleme anahtarı istemeyin. Portal sürümü gerekli seçenekleri ve kaynak türü doğrulamasını karşılamazsa isteği kapatın. [ScreenCast](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html)
3. Portal taşıyıcısı her istek için özgün handle token kullanmalı, `Response` dinleyicisini çağrıdan önce kurmalı ve dönüş handle’ını doğrulamalıdır. Kullanıcı reddi veya iptalinde akışı açmayın. Bekleyen isteğin zaman aşımında `Request.Close` çağırın ve geç gelen yanıtları dikkate almayın. [Request](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Request.html)
4. Başarılı `Start` yanıtında tam bir akış ve `source_type=WINDOW` doğrulayın. Yalnız o akış için `OpenPipeWireRemote` tanıtıcısını kullanın. Portal v6 ve sonrası kimlik yeniden kullanımı riskine karşı `pipewire-serial` ile hedefleyin. Eski sunucuda düğüm kimliğini yalnız o oturum içinde kullanın ve akış kaybında durun. Varsayılan PipeWire soketine geçiş veya başka düğüm seçimi yapmayın. [ScreenCast](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html)
5. Aktif akış yitirildiğinde, `Session.Closed`, portal bağlantısı kesilmesi veya kullanıcı kontrolü geldiğinde işlenmemiş kareleri atın. PipeWire akışını ve tanıtıcıyı bırakın, D-Bus oturumunu kapatın. Askıda kalan bir taşıyıcı iptal edilemiyorsa ayrılmış D-Bus istemci bağlantısını kapatın. Yeni başlatma için yeni onay gerekir. [Session](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Session.html)

Simülasyondaki çekme modeli en sık saniyede bir kare ister, çekmeyi 250 ms ve kareyi 16 MiB ile sınırlar. Sahte gözlemci tek boş yuva olduğunda kare kabul eder. Kareler SQLite’a, dosyaya, stdout’a veya günlüğe aktarılmaz. İzleme ve iptal olayları yalnız olay türü, sıra, kaynak, zaman ve durum içerir.

## Fedora GNOME Wayland deneme sırası

- **Bugünkü teslimle yapılabilir.** Ayrı bir `XDG_STATE_HOME` ile `nopen doctor`, `nopen modes` ve `nopen observe status` çalıştırın. `nopen observe start` için `BLOCKED`, `nopen observe start --consent` için `UNAVAILABLE` ve kod 1 bekleyin. Portal seçicisi açılmamalı. `nopen run` açıkken ikinci terminalden görev sıraya alın, ardından `pause`, `resume`, `observe stop` ve `stop` akışını doğrulayın. [Kaynak ölçümü](RESOURCE_MEASUREMENT.md) ile aynı koşullarda idle değerlerini alın.
- **Gerçek taşıyıcı ve ayrı açık izin sonrasında.** Kurgu içerikli iki pencereyle başlayın. Seçicide önce iptal edin ve akış açılmadığını doğrulayın. İkinci denemede yalnız kurgu penceresini seçin, sistem göstergesini ve ikinci pencerenin kapsam dışında kaldığını doğrulayın. Kaynak pencereyi kapatma, kilitleme, OS göstergesinden iptal, `pause`, `stop`, portala erişimin kaybolması ve zaman aşımı sonrası kare ve tanıtıcı kalmadığını ölçün. Yeni başlangıcın tekrar açık kullanıcı onayı gerektirdiğini kontrol edin. Görüntüler veya kişisel veriler test kanıtına eklenmemeli.

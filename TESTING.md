# Nopen Buddy testleri

Depo kökünde Fedora kullanıcı oturumunda çalıştırın.

```bash
python3 -m unittest discover -s tests -v
git diff --check
```

Testler Python standart kütüphanesini ve her test için ayrı bir kurgu veritabanını kullanır. Linux seccomp testi sistemde `libseccomp.so.2` arar. Filtreyi önce bir soket çağrısının süreç öldürdüğünü doğrulayarak sınar, sonra CLI örneklerini ağ soketi çağrıları yasaklı olarak çalıştırır. Python audit denetimi bu örneklerde masaüstü aygıtı açma, dinamik kütüphane yükleme ve alt süreç başlatma çağrılarını da engeller. Ayrı `strace` testi çalışabiliyorsa dosya, ioctl ve ağ sistem çağrılarını gözlemler. Bu ek testlerin araçları çalışma zamanı bağımlılığı değildir. Eksik araç veya ortam kısıtı ilgili testi atlatır.

Kapsamda işlem ortasında gerçek SIGKILL, yeniden başlatma sonrası geri yükleme, çift gönderim, eşzamanlı çalıştırıcı, pause/stop, insan müdahalesi simülasyonu, reddetme ve iptal, WAL şema geçişi, hatalı şema, bozuk veritabanı ve dosya izinleri bulunur. Yeniden başlatma kalıcı SQLite durumuyla denenir. Ayrı ortama yedek alma ve JSON içe aktarma P1’de yoktur.

W002 testleri kurulum öncesi mod listesini, kapalı yetenekleri, Companion Buddy seçiminin reddini, Operator Buddy durum alanını ve eski görev verilerinin durdurma/yeniden başlatma sırasında korunmasını kapsar. W001 testleri de aynı komutla çalışır.

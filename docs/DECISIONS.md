# Mimari kararlar

## Python ve SQLite

Python 3.11+ standart kütüphanesi tek çalıştırılabilir CLI, yerel argüman işleme ve test altyapısı sağlar. Fedora’da SQLite paketinin sağladığı WAL ve ACID işlemleri, ek paket, root, servis hesabı veya dış API eklemeden kalıcı görev durumuna imkân verir.

## Yalnız yerel kontrol noktası

Kuyruğun yetkisi SQLite içinde tamamlanabilen kontrol noktalarıyla sınırlıdır. Aynı işlem içinde yan etki ve tamamlanma yazıldığı için yerel eylemin tekrar gönderim sözleşmesi basittir. Gelecekte dosya, ağ veya ekran eylemleri için ayrı izin ve kesinti modeli gerekir.

## Bildirim kaydı ve manuel başlatma

P1’de saklanan izin, bildirimi okuma tercihidir. Masaüstü erişimi bileşenleri açılmaz. Çalıştırıcı terminalden veya örnek systemd kullanıcı biriminden elle başlar. Her süreç çökmesinden sonra çalışma ancak yeni bir başlatma çağrısı ile devam eder.

## MIT lisansı

W001 dalı için MIT seçildi. Kısa ve yaygın bir izin metniyle kaynak kodun kullanımı, değiştirilmesi ve yeniden dağıtımı mümkün olur. Bu seçim kullanıcı görev verilerini kapsamaz.

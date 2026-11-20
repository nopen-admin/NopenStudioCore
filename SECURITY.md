# Güvenlik

W001’de çalıştırıcının tek işlemi yerel SQLite kontrol noktasıdır. `pause` komutuyla yeni işlemleri bekletin, `stop` ile çalıştırıcıyı kapatın. `revoke all` yerel ekran izni bildirim kararlarını iptal eder. Bu sürüm için ekran erişimi yoktur. Müdahale algılama yalnızca CLI simülasyonu olarak bulunur.

Hafıza aynı kullanıcıya ait `0700` durum dizininde, `0600` veritabanında saklanır. Veritabanı şifrelenmez. Yedek veya terminal çıktısı oluştururken aynı gizlilik gerekliliklerini uygulayın.

Bir güvenlik sorununu proje sahibine özel kanaldan bildirin. GitHub’da özel güvenlik bildirimi açıksa depo güvenlik sekmesi kullanılabilir. Kayıt, veritabanı, token veya kişisel bilgi paylaşmadan, kurgu girdilerle yeniden üretim adımlarını, sürüm kimliğini ve etkiyi belirtin. Teknik sınırlar [tehdit modelinde](docs/THREAT_MODEL.md) açıklanır.

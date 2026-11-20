# Companion Buddy yol haritası

Companion Buddy W002’de **NOT IMPLEMENTED**. Ürün tasarımı, tatlı ama ciddi küçük bir robot karakter öngörüyor. Belirgin bir robot gövdesi, ayaklar ve yüz ifadesiyle karakterin silueti okunur olur. Robot masaüstünde yürüyebilir, pencere kenarına oturabilir veya tutunabilir, zıplayabilir ve özgün kısa “hiyya!” tepkileri verebilir. Kullanıcı karakteri gösterebilir, gizleyebilir veya tamamen kapatabilir.

Konuşma öncelikli arayüzde sesli etkileşim açık kullanıcı iznine bağlıdır. Mikrofon yalnız açıkça başlatılan dinleme oturumunda çalışır. Konuşma çıkışı ve kısa efektler bağımsız kapatılabilir. Altyazı erişilebilirlik seçeneği olarak değerlendirilebilir. Çevrimdışı konuşma cihaz üzerinde işlenir. Çevrimiçi bir seçenek ancak ayrı ağ onayı ve veri akışı bildirimiyle değerlendirilebilir.

| Platform | Sonraki teknik inceleme |
| --- | --- |
| Fedora Wayland | Karakteri uygulamanın kendi yüzeyinde çizerek başlamak. Pencere kenarı ve konum bilgisi için kompozitör sınırlarını incelemek. Ekran yakalama ve giriş kontrolü ayrı onaylı portal aşamalarına bağlıdır. |
| Windows | Pencere geometrisi, karakter katmanı ve işletim sistemi mikrofon izni için ayrı bir adaptör değerlendirmek. |
| Gelecekte NopenOS | Masaüstü kabuğunun sunduğu pencere ve animasyon arayüzleriyle entegrasyonu, platform yetki modeli belirlenince değerlendirmek. |

Ses fizibilitesi, görsel karakter ve ortak hafıza entegrasyonu aşamaları için [ürün kararı](https://github.com/nopen-admin/NopenStudioCore/issues/4) geçerlidir.

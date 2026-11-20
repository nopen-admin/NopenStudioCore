# NopenScript C runtime için host ABI sınırı

W004A, `SkillRegistry → PolicyGate → IActionExecutor → ActionCompleted` sırasını kurar. NopenScript derleyicisi veya VM bu teslimin çalışma zamanı bağımlılığı değildir. Ayrı bir C runtime olgunlaştığında aşağıdaki sözleşme ayrıca sürümlenir ve kurgu beceriyle doğrulanır.

| Sınır | Tasarım |
| --- | --- |
| Plan | Derlenmiş modül bildirimi beceri kimliği, API sürümü, giriş şeması, deterministik yetenek listesi ve kaynak bütçesi taşır. C# kayıt ve politika denetimi bu bildirimi doğrular. |
| ABI | Sürümlü C çağrı tablosu ve açık durum kodları. Opaque oturum tanıtıcısı, sabit genişlikli sayılar, uzunluklu UTF-8 giriş/çıkış. Sahiplik ve serbest bırakma her buffer için tek sorumluya bağlanır. |
| Yürütme | C# bir deneme anahtarı ve iptal işareti verir. VM'nin önerdiği eylem host'a dönerek yeniden PolicyGate denetiminden geçer. Kayıt, izin verme ve checkpoint C# host sorumluluğudur. |
| Kaynak ve hata | Komut/yakıt, bellek ve süre üst sınırı. ABI'de exception taşınmaz. İptalden sonra gelen sonuç atılır. Desteklenmeyen sürüm veya yetenek `BLOCKED`. |
| Süreç sınırı | Genel veya güvenilmeyen C kodu için aynı süreç güvenlik sınırı olarak kullanılamaz. İleride ayrı, kısıtlanmış yürütücü ve kapatılabilir süreç tasarımı gerekir. VM’ye ham dosya, ağ veya masaüstü tanıtıcısı verilmez. |

İlk gelecekteki kabul denemesi, dış sistem etkisi olmayan bir kurgu becerinin aynı girişle aynı sonucu üretmesi, iptalde sonucun atılması ve hatada C# durumunun bozulmamasıdır.

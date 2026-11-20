# Nopen Studio Core

W001, Fedora için terminalden yönetilen yerel görev hafızası prototipidir. Görev amacı, kanıt kaynağı, insan kararı ve kontrol noktası süreçler arasında korunur. Çalıştırıcı yalnız SQLite kontrol noktalarını işler. Ekran izleme, fare/klavye denetimi, pano, ses, model ve tarayıcı entegrasyonları P1’de kapalıdır.

- [Ürün sözleşmesi ve güvenlik sınırları (#1)](https://github.com/nopen-admin/NopenStudioCore/issues/1)
- [W001 görev ve kabul ölçütleri (#2)](https://github.com/nopen-admin/NopenStudioCore/issues/2)

## Fedora’da başlatma

Kaynağın doğrulanmış bir kopyasında, root kullanmadan aşağıdaki komutları çalıştırın. Çalışma zamanı için Fedora’daki Python 3.11 veya üstü, standart kütüphanedeki `sqlite3`, SQLite 3.31 veya üstü ve yerel depolama yeterlidir. Python paketi kurmak gerekmez.

```bash
python3 --version
python3 -c 'import sqlite3; print(sqlite3.sqlite_version)'
./nopen --help
./nopen init
./nopen doctor
```

İlk kurulum ekranı Türkçedir. `EVET` bildirimi okuduğunuzu kaydeder. Reddetmek için Enter’a basın veya `--decline` kullanın. Terminal dışı çağrıda tercih belirtilmezse kayıt reddedilmiş sayılır. Her iki tercihte de ekran yetkileri **NOT IMPLEMENTED** olarak gösterilir ve konsol kullanılabilir.

```bash
./nopen task add demo "Kurgu teslimi incele" --priority 2 --deadline 2030-01-10
./nopen task evidence demo "fixture:42" "Kurgu test çıktısı"
./nopen task decision demo approve "İnceleme kapsamı kabul edildi"
./nopen task context demo --summary "Hazırlık tamamlandı" --unknowns "Sonuç" --next-step "Testi incele"
./nopen task checkpoint demo demo-a1 --note "İlk kontrol noktası"
./nopen run --once
./nopen stop
./nopen run --once
./nopen handoff demo
```

| Komut | Davranış |
| --- | --- |
| `status` | Kuyruk kipini, sıradaki işlem sayısını, görev durumlarını ve izin kayıtlarını gösterir. |
| `run` | Terminalde çalışır ve kuyruğu işler. `--once` en fazla bir işlemden sonra çıkar. |
| `pause` / `resume` | Yeni işlem kabulünü kapatır / açar. Açık çalıştırıcı bekler. |
| `stop` | Yeni işlem kabulünü kapatır. Açık çalıştırıcı çıkar. `Ctrl+C` de durdurur. |
| `simulate-intervention` | Test için kaynak bilgisi `simulation` olan bir duraklatma olayı kaydeder. |
| `handoff ID` | Güncel görev bağlamını ve en son kaydedilen kontrol noktasını gösterir. |
| `export` | Görev hafızasının JSON anlık görüntüsünü standart çıktıya yazar. |
| `revoke screen-read`, `revoke screen-control`, `revoke all` | Yerel karar kaydını iptal eder. |
| `doctor` | Dağıtım, Wayland/X11, portal manifesti, PipeWire soket yolu ve libei dosyası göstergelerini okur. |

Bir terminalde `./nopen run` çalışırken başka bir terminalden `pause`, `resume` ve `stop` kullanılabilir. `READY`, kuyruğun işlem almaya açık olduğunu gösterir. Bir PID veya canlılık göstergesi değildir. Bekleyen işlem sırası FIFO’dur. Öncelik ve son tarih devir bilgisi olarak tutulur. `doctor` yerel dosya ve ortam işaretleriyle sınırlıdır. Portal yetkisinin, hizmet sağlığının veya gerçek ekran erişiminin doğrulaması değildir.

### İsteğe bağlı systemd kullanıcı birimi

Otomatik başlatma kapalıdır. Manuel kullanım için önce kaynak dizininden `nopen` komutunu kullanıcı yoluna bağlayın, ardından örnek birimi kurun.

```bash
mkdir -p "$HOME/.local/bin" "$HOME/.config/systemd/user"
ln -s "$(pwd)/nopen" "$HOME/.local/bin/nopen"
install -m 0644 contrib/nopen-core.service "$HOME/.config/systemd/user/nopen-core.service"
systemctl --user daemon-reload
systemctl --user start nopen-core.service
systemctl --user stop nopen-core.service
```

Birimi kullanıcı oturumunda manuel olarak başlatın. Bilgisayar kapalı veya uykudayken görev kuyruğu ilerlemez. Etkileşimli kurulumdan önce birimi başlatırsanız başlangıç başarısız olur.

## Veri akışı ve doğrulama

Kullanıcının CLI’ye verdiği görev, karar, kaynak referansı, bağlam ve komut durumu yerel SQLite dosyasına gider. `handoff` ve `export` sonucu terminale çıkar. Kaynak referansları metin olarak saklanır. Uygulama bağlantıları açmaz, telemetri göndermez ve terminal geçmişini okumaz. GitHub’dan ilk kaynak edinimi ayrıca ağ bağlantısı gerektirebilir.

Resmî kaynak [Nopen Studio Core](https://github.com/nopen-admin/NopenStudioCore). Kaynağı çalıştırmadan önce `git rev-parse HEAD` çıktısını proje sahibinin paylaştığı tam commit kimliğiyle karşılaştırın. W001 imzasız kaynak prototipidir. İmzalı dağıtım veya yayın paketi bulunmuyor.

[Lisans](LICENSE) · [Güvenlik](SECURITY.md) · [Gizlilik](PRIVACY.md) · [Mimari](docs/ARCHITECTURE.md) · [Tehdit modeli](docs/THREAT_MODEL.md) · [Kararlar](docs/DECISIONS.md) · [Test](TESTING.md)

## Geliştirme

Değişiklikler ayrı bir geliştirme dalından `main` hedefli taslak PR ile değerlendirilir. Depoya kişisel veri, ekran görüntüsü, parola, API anahtarı veya özel konuşma içeriği eklemeyin. Kabul iddialarını çalıştırılan testlerle sınırlayın.

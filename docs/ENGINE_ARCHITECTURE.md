# Nopen Buddy C# motoru

NB-W004A, UI’dan bağımsız bir .NET 10 kütüphanesi ve konsol uygulamasıdır. İlk beceri yerel bir kurgu kontrol noktası üretir. Girdi, ekran, mikrofon, ağ, model ve GPU adaptörü bulunmaz.

## Başlatma

```bash
export DOTNET_CLI_TELEMETRY_OPTOUT=1
dotnet build src/Nopen.Buddy.Cli -c Release
state_dir="$(mktemp -d)"
export DOTNET_EnableDiagnostics=0
dotnet src/Nopen.Buddy.Cli/bin/Release/net10.0/Nopen.Buddy.Cli.dll --state "$state_dir" run
```

Konsolda `durum`, `kurgu görev çalıştır demo`, `onayla demo`, `handoff demo`, `duraklat`, `devam`, `dur`, `izni-iptal`, `kontrol` veya `çık` kullanılabilir. Durum ve sonuçlar JSON satırıdır. Onay yanıtı `RUNNING`, kalıcı sonuç kullanılabilir olduğunda `handoff demo` yanıtı `DONE` döner. Bilinmeyen komut `UNSUPPORTED` döner. Tek seferlik `--state DIR demo demo --approve` ilk kurgu verisi için isteği, açık onayı ve sonucu beklemeyi birleştirir. `status` tek seferlik durum okumasıdır. Test için ayrıca ayrılmış boş bir durum dizini kullanın.

| Bileşen | Sorumluluk |
| --- | --- |
| Konsol hostu | Komutu sabit sözdiziminden bir olaya çevirir. stdin kapanışı, `çık`, SIGTERM ve Ctrl+C durdurma isteği verir. |
| `BuddyEngine` | Kapasitesi 64 olan Channel üzerinde bekleyen tek olay tüketicisi. `TaskRequested`, `UserIntervention`, `PermissionRevoked`, `StopRequested`, `ActionCompleted` ve `TimeTick` dahil olayları sırayla işler. W004A’da `kontrol` bir `TimeTick` gönderir. Idle timer kurulmaz. |
| `SkillRegistry` | Yalnız kayıtlı `fixture` ve geçerli görev anahtarından deterministik plan üretir. |
| `PolicyGate` | Kurgu dışı her kapasiteyi reddeder. Kurgu işi açık görev onayı, etkin insan kısıtları ve yürütme durumu denetiminden geçer. |
| `MockExecutor` | İptal edilebilir saf kurgu sonucu üretir. Kalıcı yan etki yalnız döngünün yazdığı kontrol noktasıdır. |
| `EngineStateStore` | Ayrı durum dizininde tek yazıcı kilidi, şema v1 JSON ve görev anahtarına göre idempotency. |

## Olay sırası ve kurtarma

Bir iş onay beklerken veya yürürken ikinci iş başlamaz. `IDLE`, `RUNNING`, `PAUSED`, `NEEDS_APPROVAL`, `BLOCKED` ve `DONE` durumları raporlanır. Durdurma, müdahale ve iptal önce iş onayını siler ve varsa yürütücüye iptal bildirir. İptalden sonra başarı dönse bile eski denemenin sonucu atılır. Bekleyen yürütücü bitene dek ikinci yürütücü açılmaz. Kanalda tamamlanma daha önce işlendiyse tamamlanmış kontrol noktası korunur. `devam` duraklatmayı açar. İzin iptali aynı durum dosyasında kalır ve `devam` ile geri alınmaz.

Aynı dizinde Linux 0700 dizin ve 0600 kontrol noktası kullanılır. Dizin kullanıcıya ait ve güvenilir bir yerel dosya sisteminde olmalı. Motor dosyayı geçici kardeş dosyaya yazar, flush eder ve atomik rename ile değiştirir. Aygıt güç kaybı için dizin fsync garantisi bu kesitte yok. Hatalı sürüm veya bozuk kayıt yeni veriyle üzerine yazılmaz. Kaydedilmiş görev anahtarı yeni eylem başlatmadan önceki sonucu döndürür. Süreç öldürüldüğünde kaydedilmemiş saf kurgu işi ve onayı kaybolur, yeni istek ve onay gerekir. Gerçek yan etkiler için ayrı bir idempotency ve onay protokolü gerekir.

## .NET 10 ve Native AOT

Normal Release derlemesi .NET 10 çalışma zamanı kullanır. Native AOT doğrudan çalıştırılabilen hedef platform ELF dosyası üretir. Motor statik beceri kaydı, kaynak üretilmiş JSON ve opsiyonel SQLite için kaynak üretilmiş P/Invoke kullanır. Yansıma ile eklenti yükleme ve dinamik kod üretimi planlanmadı. Native AOT yayın komutu burada yalnız yerel derleme çıktısı üretir.

```bash
dotnet publish src/Nopen.Buddy.Cli -c Release -r linux-x64 -p:PublishAot=true -p:EventSourceSupport=false
```

Native derleme için hedef RID araç zinciri, zlib geliştirme dosyaları, ilk derleme sırasında NuGet derleyici paketleri ve uygun Linux tabanı gerekir. Fedora’da araç zinciri ve hedef dağıtım kabulü ayrıca doğrulanmalı. Uygulama için Python gerekmez. Geliştirmedeki .NET host yerel teşhis soketini açabildiğinden managed test ve ölçümde `DOTNET_EnableDiagnostics=0` kullanılır. Ölçülen AOT çıktısı bu ortam değişkeni olmadan çalıştırıldı. [Native AOT belgeleri](https://learn.microsoft.com/en-us/dotnet/core/deploying/native-aot/) · [.NET teşhis ayarları](https://learn.microsoft.com/en-us/dotnet/core/runtime-config/debugging-profiling)

Bu çalışma ortamı AF_UNIX soketi açmayı engelledi. Standart komut ILLink görev hostunu başlatırken MSB4216 ve MSB4027 verdi. Ölçülen AOT çıktısı için aynı SDK ve paketle, yerel geçici MSBuild dosyasından ILLink görevleri işlem içinde çalıştırıldı ve GCC seçildi. Tekrarlama komutları [TESTING.md](../TESTING.md) içindedir.

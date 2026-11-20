# Nopen Buddy testleri

Depo kökünde Fedora kullanıcı oturumunda çalıştırın.

```bash
python3 -m unittest discover -s tests -v
git diff --check
```

Testler Python standart kütüphanesini ve her test için ayrı bir kurgu veritabanını kullanır. Linux seccomp testi sistemde `libseccomp.so.2` arar. Filtreyi önce bir soket çağrısının süreç öldürdüğünü doğrulayarak sınar, sonra CLI örneklerini ağ soketi çağrıları yasaklı olarak çalıştırır. Python audit denetimi bu örneklerde masaüstü aygıtı açma, dinamik kütüphane yükleme ve alt süreç başlatma çağrılarını da engeller. Ayrı `strace` testi çalışabiliyorsa dosya, ioctl ve ağ sistem çağrılarını gözlemler. Bu ek testlerin araçları çalışma zamanı bağımlılığı değildir. Eksik araç veya ortam kısıtı ilgili testi atlatır.

Kapsamda işlem ortasında gerçek SIGKILL, yeniden başlatma sonrası geri yükleme, çift gönderim, eşzamanlı çalıştırıcı, pause/stop, insan müdahalesi simülasyonu, reddetme ve iptal, WAL şema geçişi, hatalı şema, bozuk veritabanı ve dosya izinleri bulunur. Yeniden başlatma kalıcı SQLite durumuyla denenir. Ayrı ortama yedek alma ve JSON içe aktarma P1’de yoktur.

W002 testleri kurulum öncesi mod listesini, kapalı yetenekleri, Companion Buddy seçiminin reddini, Operator Buddy durum alanını ve eski görev verilerinin durdurma/yeniden başlatma sırasında korunmasını kapsar. W001 testleri de aynı komutla çalışır.

W003 testleri yerel kuyruk bildirimi, SIGKILL sonrası tekrar başlatma ve sahte portal ile izin, kaynak seçimi, zaman aşımı ve teardown akışlarını kapsar. Gerçek portal ve Fedora deneme adımları [gözlem sözleşmesinde](docs/SCREENCAST.md). Idle CPU/RSS ölçümü [kaynak raporunda](docs/RESOURCE_MEASUREMENT.md).

## NB-W004A C# testleri

```bash
export DOTNET_CLI_TELEMETRY_OPTOUT=1
dotnet build src/Nopen.Buddy.Cli -c Release
dotnet run --project tests/Nopen.Buddy.Engine.Tests -c Release
python3 tests/check_csharp_cli.py "$(command -v dotnet)" src/Nopen.Buddy.Cli/bin/Release/net10.0/Nopen.Buddy.Cli.dll
python3 scripts/measure_engine.py -- "$(command -v dotnet)" src/Nopen.Buddy.Cli/bin/Release/net10.0/Nopen.Buddy.Cli.dll
```

C# motor ve test projesi üçüncü parti .NET paketi istemez. Python burada yalnız Linux süreç testleri, sentetik W003 yedeği ve ölçüm aracı için kullanılır. CLI çalıştırmak için Python gerekmez. Linux süreç testi `libseccomp.so.2` ve SQLite sistem kitaplığını ister. Seccomp ağ soketi denemesini sonlandırdığını negatif kontrolle doğrular. Ardından komut, checkpoint, SIGKILL/SIGTERM ve salt okunur SQLite senaryoları filtreden geçer.

### Native AOT derlemesi

Standart yerel komut mimari belgesinde yer alır. AF_UNIX engelli bu Debian ortamında `MSB4216/MSB4027` için 10.0.100 SDK ve 10.0.0 ILLink paketleriyle aşağıdaki geçici MSBuild ayarı kullanıldı. Paketin içeriği değişmedi.

```bash
build_override="$(mktemp --suffix=.targets)"
cat > "$build_override" <<'MSBUILD'
<Project>
  <UsingTask TaskName="ComputeManagedAssemblies" AssemblyFile="$(BuddyLinkTasks)" Override="true" />
  <UsingTask TaskName="ILLink" AssemblyFile="$(BuddyLinkTasks)" Override="true" />
</Project>
MSBUILD

dotnet publish src/Nopen.Buddy.Cli -c Release -r linux-x64 \
  -p:PublishAot=true -p:EventSourceSupport=false -p:CppCompilerAndLinker=gcc \
  -p:UseSharedCompilation=false -m:1 -nr:false \
  -p:CustomAfterMicrosoftCommonTargets="$build_override" \
  -p:BuddyLinkTasks="$HOME/.nuget/packages/microsoft.net.illink.tasks/10.0.0/tools/net/ILLink.Tasks.dll" \
  -o /tmp/nopen-buddy-aot
python3 tests/check_csharp_cli.py /tmp/nopen-buddy-aot/Nopen.Buddy.Cli
python3 scripts/measure_engine.py -- /tmp/nopen-buddy-aot/Nopen.Buddy.Cli
```

Fedora/GNOME/PipeWire, Windows, güç kaybı ve gerçek dış sistem eylemleri **NOT TESTED**.

### Debian 13 x86-64 sonuçları

.NET SDK 10.0.100, runtime 10.0.0, GCC 14.2.0, glibc 2.41 ve sistem SQLite 3.46.1. C# motor testleri 11/11 geçti. Managed ve Native AOT CLI için beş Linux süreç denetimi grubu ayrı ayrı geçti. Kurgu W003 yedeğinin SHA-256 değeri değişmedi ve SQLite yan dosyası oluşmadı. Yanlış şema sürümü, v2’de eksik kolon, bozuk başlık, WAL başlığı ve WAL yan dosyası reddedildi. Python W001–W003 regresyonu 34 geçti, 1 `strace` testi `ptrace` kısıtı nedeniyle atlandı. Yerel Native AOT ikilisi boş ortam ve geçersiz PATH ile doğrudan çalıştırıldığında `DONE` ve `fixture-completed` döndü.

| Ölçüm | Managed Release | Native AOT |
| --- | ---: | ---: |
| Yeni süreçte `status`, medyan / p95 | 52,188 / 68,004 ms | 2,140 / 2,838 ms |
| Yeni süreçte onaylı kurgu eylemi, checkpoint ve çıkış, medyan / p95 | 67,439 / 81,425 ms | 2,392 / 3,470 ms |
| Boşta örnek süresi | 30,002 s | 30,014 s |
| Boşta CPU farkı, 100 tick/s | 0 tick | 0 tick |
| Boşta RSS, başlangıç → bitiş | 34.252 → 34.260 KiB | 4.424 → 4.424 KiB |
| Dosya boyutu | 27.648 bayt yalnız CLI DLL | 2.987.280 bayt ELF |

Her gecikme satırı için 30 yeni süreç ve ayrı durum dizini kullanıldı. Ölçüm başlangıçtan çıktı ve süreç kapanışına kadardır. İşletim sistemi disk önbelleği sıfırlanmadı. RSS tepe değer yerine iki örnektir. Her iki kipte GPU aygıtı, tanınan GPU kitaplığı veya soket tanıtıcısı örneklerde görülmedi. Native AOT ikilisi dinamik Linux sistem kitaplıklarına bağlıdır. SQLite okuma yolu sistem SQLite kitaplığını ayrıca yükler. Bu ölçümler aynı Debian ortamındaki yerel prototipe aittir. Fedora donanımı ve etkin masaüstü senaryosu ölçülmedi.

Ölçülen Native AOT ikilisi SHA-256 `9099fd2892684bb43ee0f4249443682b59acf099df31765f32c71f2bd08c3126`.

# W003 kaynak ölçümü

```bash
python3 scripts/measure_idle.py --seconds 35 --check-interval 30
```

Ölçüm yalnız geçici kurgu durumuyla bir boş çalıştırıcı başlatır, `/proc` sayaçlarını okur ve çalıştırıcıyı durdurur. Gözlemci pasiftir. W003, Python standart kütüphanesi ve mevcut SQLite ile çalışır. Model, GPU veya görüntü işleme çalışma zamanı eklenmedi.

| Ölçüm | Debian 13 x86_64, Python 3.12.14, SQLite 3.53.1 |
| --- | --- |
| Boş örnek penceresi | 35.001 s, zamanlı kontrol aralığı 30 s |
| Süreç CPU sayacı | 0 tick farkı, sayaç hızı 100 tick/s |
| Süreç RSS | Başlangıç 11.676 KiB, bitiş 11.680 KiB (yaklaşık 11,4 MiB) |
| GPU aygıt tanıtıcısı / tanınan GPU kitaplığı | İki örnekte de görülmedi |
| Soket tanıtıcısı | İki örnekte de görülmedi |

Sıfır tick, ölçümün sayaç çözünürlüğünde CPU farkı saptanmadığını gösterir. RSS iki nokta örneğidir. Seccomp testinde CLI yolları sistem ağ çağrıları kapalıyken çalıştı. Fedora donanımı, etkin PipeWire akışı, tepe bellek ve gerçek gözlem CPU tüketimi **NOT TESTED**.

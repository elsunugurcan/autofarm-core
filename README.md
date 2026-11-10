# AutoFarm-30 — Komuta Merkezi v7.5

Windows üzerinde Android cihaz filosunu yöneten Python / CustomTkinter masaüstü paneli.

## Özellikler

- Filo durumu, ekran izleme ve cihaz kontrolü.
- Kampanya dağıtımı ve işlem bazında telefon seçimi.
- Ortak Grup & Sayfa Merkezi: yerel görsel ve başlık paylaşımı.
- Anahtar kelime nöbetçisi: gelen yorumları izleme, sıralı ve dengeli yanıt dağıtımı.
- Ayarlanabilir işlem aralıkları, paylaşım geçmişi ve tanı kayıtları.
- Panel yeniden açıldığında görevler kullanıcı başlatana kadar bekler.

## Windows kurulumu

Python ve Android Platform Tools (adb) kurulu olmalı; adb PATH üzerinde bulunmalı. Telefonlarda USB hata ayıklama iznini verin.

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config/devices.example.json config/devices.json
.\AutoFarm_Baslat.bat
```

Cihaz bilgilerini yerel `config/devices.json` dosyasında düzenleyin. UIAutomator2 cihaz kurulumunu kullanılan sürümün gereksinimlerine göre tamamlayın. Ana masaüstü giriş noktası `src/gui.py`; `main.py` eski konsol arayüzüdür. Docker/macOS dosyaları eski yardımcı akışlar içindir.

## Kullanım ve kayıtlar

Güncel sıralı işlem rehberi: [V75_SIRALI_NOBETCI_KULLANIM.txt](V75_SIRALI_NOBETCI_KULLANIM.txt).

Gerçek cihaz ve Facebook arayüzü sürümüne göre canlı doğrulama gerekir. Gönderimi belirsiz kalan işlemler mükerrer işlem olmaması için otomatik tekrar edilmez. İşlemleri yalnız yetkili olduğunuz hesap ve hedeflerde kullanın.

Hesap/proxy ayarları, veritabanları, yüklenen görseller, yedekler ve tanı kayıtları yereldir; Git takibine alınmaz. Yeni kurulum mevcut cihazın görevlerini veya hesap verilerini taşımaz.

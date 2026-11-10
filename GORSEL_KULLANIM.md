# Paylaşım geçmişi güncellemesi

Güncelleme bilgisayarınızdaki mevcut AutoFarm klasörüne kuruldu. Terminal veya dosya kopyalama işlemi gerekmiyor. Masaüstündeki **AutoFarm-30** kısayolu güncel sürümü açar.

1. **Telegram & Grup Butonları** bölümünde görseli seçin ve başlığı yazın. Ürün linki alanı kaldırıldı; paylaşım görsel ve başlıktan oluşur.
2. Kullanacağınız telefonları ve grupları seçip paylaşımı başlatın.
3. **Canlı Operasyon** konsolunun üzerindeki **Paylaşım Geçmişi** tablosunu izleyin. Görsel, tarih/saat, NODE/seri numarası, kayıtlı Facebook hesap adı, hedef ve durum burada görünür. Yaklaşık dört saniyede bir yenilenir.
4. Bir kayda çift tıklayın veya kaydı seçip **Seçili Kaydın Ayrıntıları** butonuna basın. Büyük görseli, başlığı, hedef bağlantısını, alınabildiyse gönderi bağlantısını ve hata açıklamasını görebilirsiniz. Hesap adı, filo tablosunda sizin kaydettiğiniz addır; Facebook'tan kimlik doğrulaması yapıldığı anlamına gelmez.
5. Alan kazanmak için **Geçmişi Gizle**, geri açmak için **Geçmişi Göster** kullanın. **Daha Eski Kayıtlar** her tıklamada 200 kayıt daha yükler.

Kayıtlar program kapanınca kaybolmaz. Görsellerin arşiv kopyaları da saklanır; asıl dosyayı taşımanız geçmişteki önizlemeyi bozmaz. Önceki sürümlerde kaydedilmemiş paylaşımlar otomatik geri getirilemez. Yeni kayıtlar bu güncellemeden sonraki işlemler için oluşur.

**Durumların anlamı:** Hazırlanıyor / Gönderim deneniyor / Gönderim denendi, doğrulanamadı / Bağlantı alındı, yayın teyitsiz / Hata / Atlandı / Yarıda kesildi. Bir bağlantı alınması tek başına doğru hesap, görsel ve yayının doğrulandığı anlamına gelmez. Gerçek yayın sonucunu Facebook'ta kontrol edin.

Geçmiş `share_history.db` ve `share_history_media` içinde tutulur. Tam proje yedeği alırken bu iki öğeyi de dahil edin. Önceki sürüm dosyaları ve config yedeği proje içindeki `backups/gecmis-oncesi-20261109-193334` klasöründedir.

19 otomatik kontrol ve gerçek Tk arayüzünde tablo/ayrıntı/gizle-göster kontrolleri geçti. Gerçek Facebook paylaşımı gönderilmedi. Ekran yakalama aracı zaman aşımına uğradığı için görsel ekran görüntüsü denetimi yapılamadı; program açılışı ve hata günlüğü kontrol edildi.

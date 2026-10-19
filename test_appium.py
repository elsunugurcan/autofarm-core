import time
from appium import webdriver
from appium.options.android import UiAutomator2Options

options = UiAutomator2Options()
options.platform_name = "Android"
options.automation_name = "UiAutomator2"
options.device_name = "Redmi_15C"

# adb devices çıktısındaki seri numarası
options.udid = "TKUW99U8QCNNJ7RC"

# Test için Android Ayarlar uygulaması
options.app_package = "com.android.settings"
options.app_activity = "com.android.settings.Settings"
options.no_reset = True

# Appium sunucusuna bağlanma
print("[*] Appium sunucusuna bağlanılıyor...")
driver = webdriver.Remote("http://127.0.0.1:4723", options=options)

print("[+] Bağlantı başarılı! Ayarlar uygulaması açıldı.")
time.sleep(3)

# Ekran boyutu bilgisi alma
window_size = driver.get_window_size()
print(f"[i] Ekran Çözünürlüğü: {window_size['width']}x{window_size['height']}")

# Oturumu güvenli sonlandırma
driver.quit()
print("[+] Test tamamlandı ve oturum kapatıldı.")

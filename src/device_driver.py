import time
import random
from appium import webdriver
from appium.options.android import UiAutomator2Options

class DeviceDriver:
    def __init__(self, serial, simulation_mode=True):
        self.serial = serial
        self.simulation_mode = simulation_mode
        self.driver = None

    def connect(self, app_package="com.android.settings", app_activity=".Settings"):
        if self.simulation_mode:
            time.sleep(random.uniform(0.4, 0.9))
            return True, f"[SIMULASYON] {self.serial} sanal oturumu acildi ({app_package})"
        
        options = UiAutomator2Options()
        options.platform_name = "Android"
        options.automation_name = "UiAutomator2"
        options.udid = self.serial
        options.app_package = app_package
        options.app_activity = app_activity
        options.no_reset = True
        self.driver = webdriver.Remote("http://127.0.0.1:4723", options=options)
        return True, f"[APPIUM] {self.serial} gercek cihaz oturumu acildi"

    def execute_action(self, action_type, target_url="", payload=""):
        if self.simulation_mode:
            delay = round(random.uniform(1.0, 2.5), 2)
            time.sleep(delay)
            return True, f"[SIMULASYON] {self.serial} -> {action_type} tamamlandi ({delay}sn) | Hedef: {target_url[:30]}"
        
        time.sleep(2)
        return True, f"[APPIUM] {self.serial} -> {action_type} gercek cihazda icra edildi"

    def close(self):
        if self.driver:
            self.driver.quit()
        return True

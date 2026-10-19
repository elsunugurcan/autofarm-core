import random
import time

class Humanizer:
    @staticmethod
    def wait(min_sec=1.5, max_sec=4.0):
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)
        return round(delay, 2)

    @staticmethod
    def tap(d, x, y, jitter=18):
        jx = x + random.randint(-jitter, jitter)
        jy = y + random.randint(-jitter, jitter)
        d.click(jx, jy)
        Humanizer.wait(0.8, 2.2)
        return (jx, jy)

    @staticmethod
    def swipe_up_feed(d):
        w, h = d.window_size()
        start_x = int(w * random.uniform(0.42, 0.58))
        start_y = int(h * random.uniform(0.72, 0.84))
        end_x = start_x + random.randint(-40, 40)
        end_y = int(h * random.uniform(0.18, 0.28))
        duration = random.uniform(0.16, 0.42)
        d.swipe(start_x, start_y, end_x, end_y, duration=duration)

import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery("autofarm_queue", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json", timezone="Europe/Istanbul", enable_utc=True)

@celery_app.task(bind=True, name="src.task_queue.execute_facebook_task")
def execute_facebook_task(self, device_id, post_link, action_type, comment_text):
    print(f"[CELERY WORKER] Cihaz ID {device_id} icin gorev baslatildi -> {action_type}: {post_link}")
    return f"Success: Device {device_id} completed {action_type}"

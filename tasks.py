from celery import Celery

celery_app = Celery(
    "t3",
    broker="redis://ip del server:6379/0",
    backend="redis://ip del server:6379/0",
)

celery_app.conf.task_routes = {
    "app.tasks.*": {"queue": "celery"},
}

celery_app.autodiscover_tasks(["app.tasks"])

@celery_app.task
def procesar_en_vm(data):
    return f"Procesado {data} en la VM"
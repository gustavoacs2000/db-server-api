from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.base import JobLookupError

# Instância global do scheduler
scheduler: BackgroundScheduler | None = None

def init_scheduler() -> None:
    """Inicializa o scheduler global."""
    global scheduler
    if scheduler is None:
        scheduler = BackgroundScheduler()
        scheduler.start()

def get_scheduler() -> BackgroundScheduler:
    """Retorna a instância do scheduler."""
    if scheduler is None:
        init_scheduler()
    return scheduler  # type: ignore

def stop_scheduler() -> None:
    """Para o scheduler."""
    global scheduler
    if scheduler is not None:
        scheduler.shutdown()
        scheduler = None
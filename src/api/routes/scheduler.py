from fastapi import APIRouter
from typing import List, Dict, Any
from ...core.scheduler import get_scheduler
from ..models import ScheduleRequest
from .python import executar_em_contexto
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.base import JobLookupError

router = APIRouter(prefix="/agendar")

def criar_funcao_agendada(code: str, contexto: str = "global"):
    """Cria uma função que será executada pelo scheduler."""
    def job_function():
        try:
            result = executar_em_contexto(code, contexto)
            if not result["ok"]:
                print(f"Erro na execução agendada: {result['erro']}")
            return result
        except Exception as e:
            print(f"Erro na execução agendada: {str(e)}")
            return {"ok": False, "erro": str(e)}
    return job_function

@router.post("")
async def agendar_tarefa(request: ScheduleRequest):
    """Agenda uma tarefa Python para execução futura."""
    try:
        scheduler = get_scheduler()
        
        # Cria a função que será executada
        job_func = criar_funcao_agendada(request.code, request.contexto)
        
        # Configura o trigger baseado no tipo
        if request.trigger_type == "cron":
            trigger = CronTrigger(**request.trigger_args)
        elif request.trigger_type == "interval":
            trigger = IntervalTrigger(**request.trigger_args)
        elif request.trigger_type == "date":
            trigger = DateTrigger(**request.trigger_args)
        else:
            return {"ok": False, "erro": "Tipo de trigger inválido"}
        
        # Agenda a tarefa
        job = scheduler.add_job(
            job_func,
            trigger=trigger,
            id=request.job_id,
            replace_existing=True
        )
        
        return {
            "ok": True,
            "job_id": job.id,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None
        }
    except Exception as e:
        return {"ok": False, "erro": str(e)}

@router.get("/ativos")
async def listar_jobs():
    """Lista todas as tarefas agendadas ativas."""
    try:
        scheduler = get_scheduler()
        jobs = scheduler.get_jobs()
        
        jobs_info = [{
            "id": job.id,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger)
        } for job in jobs]
        
        return {"ok": True, "jobs": jobs_info}
    except Exception as e:
        return {"ok": False, "erro": str(e)}

@router.post("/remover")
async def remover_job(job_id: str):
    """Remove uma tarefa agendada pelo ID."""
    try:
        scheduler = get_scheduler()
        scheduler.remove_job(job_id)
        return {"ok": True, "mensagem": f"Job {job_id} removido com sucesso"}
    except JobLookupError:
        return {"ok": False, "erro": f"Job {job_id} não encontrado"}
    except Exception as e:
        return {"ok": False, "erro": str(e)}
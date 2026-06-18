"""Fila sequencial para processamento IA da Curva ABC."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from config import USE_CELERY_QUEUE
from services.abc_job import fail_job, get_job, init_job, update_job

logger = logging.getLogger(__name__)

JobProcessor = Callable[["AbcQueueJob"], Awaitable[None]]

_queue: asyncio.Queue[AbcQueueJob] = asyncio.Queue()
_pending_ids: list[str] = []
_worker_task: Optional[asyncio.Task] = None
_processor: Optional[JobProcessor] = None
_is_processing = False

_REDIS_QUEUE_KEY = "abc:queue:pending"
_redis_client = None
_redis_checked = False


@dataclass
class AbcQueueJob:
    upload_id: str
    user_id: str
    filename: str
    table_ids: list[str]


def _get_redis():
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client

    _redis_checked = True
    if not USE_CELERY_QUEUE:
        return None

    try:
        from config import REDIS_URL
        import redis

        if not REDIS_URL:
            return None

        _redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception as exc:
        logger.warning("Redis indisponível para fila ABC: %s", exc)
        _redis_client = None
        return None


def is_celery_abc_queue_enabled() -> bool:
    return USE_CELERY_QUEUE and _get_redis() is not None


def _queued_upload_ids() -> list[str]:
    if is_celery_abc_queue_enabled():
        client = _get_redis()
        if client:
            try:
                return list(client.lrange(_REDIS_QUEUE_KEY, 0, -1))
            except Exception as exc:
                logger.warning("Erro ao ler fila ABC Redis: %s", exc)
    return list(_pending_ids)


def get_queue_position(upload_id: str) -> int:
    job = get_job(upload_id)
    if job and job.get("status") == "processing":
        return 0

    if not is_celery_abc_queue_enabled() and _is_processing:
        job = get_job(upload_id)
        if job and job.get("status") == "processing":
            return 0

    try:
        ids = _queued_upload_ids()
        if upload_id in ids:
            return ids.index(upload_id) + 1
    except Exception:
        pass
    return 0


def _refresh_queue_positions() -> None:
    for index, upload_id in enumerate(_queued_upload_ids(), start=1):
        offset = 0 if is_celery_abc_queue_enabled() else (1 if _is_processing else 0)
        position = index + offset
        update_job(
            upload_id,
            queue_position=position,
            message=f"Na fila de processamento (posição {position})…",
        )


def mark_abc_job_started(upload_id: str) -> None:
    client = _get_redis()
    if client:
        try:
            client.lrem(_REDIS_QUEUE_KEY, 0, upload_id)
        except Exception as exc:
            logger.warning("Erro ao remover %s da fila ABC: %s", upload_id, exc)

    job = get_job(upload_id) or {}
    tables_total = len(job.get("table_ids") or [])
    update_job(
        upload_id,
        status="processing",
        message="IA analisando tabelas e montando Curva ABC…",
        queue_position=0,
        pages_total=tables_total,
        pages_done=0,
    )
    _refresh_queue_positions()


def _enqueue_memory(job: AbcQueueJob) -> int:
    position = _queue.qsize() + (1 if _is_processing else 0) + 1
    update_job(
        job.upload_id,
        status="queued",
        table_ids=job.table_ids,
        pages_total=len(job.table_ids),
        pages_done=0,
        message=f"Na fila de processamento (posição {position})…",
        queue_position=position,
    )
    _pending_ids.append(job.upload_id)
    _queue.put_nowait(job)
    return position


def _enqueue_celery(job: AbcQueueJob) -> int:
    client = _get_redis()
    if not client:
        return _enqueue_memory(job)

    try:
        client.rpush(_REDIS_QUEUE_KEY, job.upload_id)
        position = int(client.llen(_REDIS_QUEUE_KEY))
    except Exception as exc:
        logger.error("Falha ao enfileirar ABC no Redis: %s", exc)
        return _enqueue_memory(job)

    update_job(
        job.upload_id,
        status="queued",
        table_ids=job.table_ids,
        pages_total=len(job.table_ids),
        pages_done=0,
        message=f"Na fila de processamento (posição {position})…",
        queue_position=position,
    )

    from tasks.abc_tasks import process_abc_celery_task

    process_abc_celery_task.delay(
        upload_id=job.upload_id,
        user_id=job.user_id,
        filename=job.filename,
        table_ids=job.table_ids,
    )
    return position


def enqueue_abc_job(job: AbcQueueJob) -> int:
    if is_celery_abc_queue_enabled():
        return _enqueue_celery(job)
    return _enqueue_memory(job)


async def _worker_loop() -> None:
    global _is_processing
    logger.info("Worker da fila Curva ABC iniciado")
    while True:
        job = await _queue.get()
        if job.upload_id in _pending_ids:
            _pending_ids.remove(job.upload_id)
        _is_processing = True
        try:
            mark_abc_job_started(job.upload_id)
            if _processor:
                await _processor(job)
            else:
                fail_job(job.upload_id, "Processador da fila ABC não configurado")
        except Exception as exc:
            logger.exception("Erro no worker ABC para %s", job.upload_id)
            fail_job(job.upload_id, str(exc))
        finally:
            _is_processing = False
            _queue.task_done()
            _refresh_queue_positions()


def start_abc_queue_worker(processor: JobProcessor) -> None:
    global _worker_task, _processor
    _processor = processor
    if is_celery_abc_queue_enabled():
        logger.info("Fila Curva ABC: Celery+Redis ativo")
        return
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_worker_loop())

import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from app.database import AsyncSessionLocal, SystemSettings
from app.collectors.olt import run_olt_routine
from app.collectors.mikrotik import run_mikrotik_routine

logger = logging.getLogger("scheduler")
scheduler = AsyncIOScheduler()

async def scheduled_olt_job():
    logger.info("Executing scheduled OLT routine...")
    try:
        await run_olt_routine()
    except Exception as e:
        logger.error(f"Error in scheduled OLT job: {e}")

async def scheduled_mikrotik_job():
    logger.info("Executing scheduled MikroTik routine...")
    try:
        await run_mikrotik_routine()
    except Exception as e:
        logger.error(f"Error in scheduled MikroTik job: {e}")

async def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler background service started.")

    # Retrieve stored intervals from database
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(SystemSettings).where(SystemSettings.id == 1))
        settings = result.scalar_one_or_none()
        olt_minutes = settings.olt_interval_minutes if settings else 120
        mk_minutes = settings.mikrotik_interval_minutes if settings else 20

    reschedule_jobs(olt_minutes, mk_minutes)


def reschedule_jobs(olt_minutes: int, mikrotik_minutes: int):
    # OLT Job
    if scheduler.get_job('olt_job'):
        scheduler.reschedule_job('olt_job', trigger=IntervalTrigger(minutes=max(1, olt_minutes)))
    else:
        scheduler.add_job(
            scheduled_olt_job,
            trigger=IntervalTrigger(minutes=max(1, olt_minutes)),
            id='olt_job',
            replace_existing=True
        )

    # MikroTik Job
    if scheduler.get_job('mikrotik_job'):
        scheduler.reschedule_job('mikrotik_job', trigger=IntervalTrigger(minutes=max(1, mikrotik_minutes)))
    else:
        scheduler.add_job(
            scheduled_mikrotik_job,
            trigger=IntervalTrigger(minutes=max(1, mikrotik_minutes)),
            id='mikrotik_job',
            replace_existing=True
        )
    logger.info(f"Scheduled routines updated: OLT = {olt_minutes} min, MikroTik = {mikrotik_minutes} min.")

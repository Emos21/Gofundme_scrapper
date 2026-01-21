from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()
scheduler.start()


def get_scraper_functions():
    """Import scraper functions lazily to avoid circular imports."""
    from app import scrape_campaign, discover_campaigns, app, db
    from models import Campaign, CampaignSnapshot, ScheduledTask
    return scrape_campaign, discover_campaigns, app, db, Campaign, CampaignSnapshot, ScheduledTask


def run_scheduled_scrape(task_id):
    """Execute a scheduled scraping task."""
    scrape_campaign, discover_campaigns, app, db, Campaign, CampaignSnapshot, ScheduledTask = get_scraper_functions()
    
    with app.app_context():
        task = ScheduledTask.query.get(task_id)
        if not task or not task.is_active:
            return
        
        logger.info(f"Running scheduled task: {task.name}")
        
        try:
            if task.task_type == 'scrape':
                urls = json.loads(task.urls) if task.urls else []
                for url in urls:
                    scrape_campaign(url, save_to_db=True)
            
            elif task.task_type == 'discover_and_scrape':
                result = discover_campaigns(max_urls=20)
                if 'urls' in result:
                    for url in result['urls']:
                        scrape_campaign(url, save_to_db=True)
            
            elif task.task_type == 'track_all':
                campaigns = Campaign.query.filter_by(is_active=True).all()
                for campaign in campaigns:
                    scrape_campaign(campaign.url, save_to_db=True)
            
            task.last_run = datetime.utcnow()
            db.session.commit()
            logger.info(f"Task {task.name} completed successfully")
            
        except Exception as e:
            logger.error(f"Task {task.name} failed: {e}")


def add_scheduled_task(task):
    """Add a task to the scheduler."""
    job_id = f"task_{task.id}"
    
    # Remove existing job if any
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    
    if not task.is_active:
        return
    
    # Parse schedule (supports: hourly, daily, weekly, or cron expression)
    schedule = task.schedule.lower()
    
    if schedule == 'hourly':
        trigger = IntervalTrigger(hours=1)
    elif schedule == 'daily':
        trigger = CronTrigger(hour=0, minute=0)
    elif schedule == 'weekly':
        trigger = CronTrigger(day_of_week='mon', hour=0, minute=0)
    elif schedule.startswith('every_'):
        # Format: every_30_minutes, every_2_hours
        parts = schedule.split('_')
        if len(parts) == 3:
            amount = int(parts[1])
            unit = parts[2]
            if unit == 'minutes':
                trigger = IntervalTrigger(minutes=amount)
            elif unit == 'hours':
                trigger = IntervalTrigger(hours=amount)
            else:
                trigger = IntervalTrigger(hours=1)
        else:
            trigger = IntervalTrigger(hours=1)
    else:
        # Assume cron expression
        try:
            cron_parts = schedule.split()
            if len(cron_parts) == 5:
                trigger = CronTrigger(
                    minute=cron_parts[0],
                    hour=cron_parts[1],
                    day=cron_parts[2],
                    month=cron_parts[3],
                    day_of_week=cron_parts[4]
                )
            else:
                trigger = IntervalTrigger(hours=1)
        except:
            trigger = IntervalTrigger(hours=1)
    
    scheduler.add_job(
        run_scheduled_scrape,
        trigger=trigger,
        args=[task.id],
        id=job_id,
        name=task.name,
        replace_existing=True
    )
    
    logger.info(f"Scheduled task {task.name} added with schedule: {task.schedule}")


def remove_scheduled_task(task_id):
    """Remove a task from the scheduler."""
    job_id = f"task_{task_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"Removed scheduled task {task_id}")


def load_tasks_from_db():
    """Load all active tasks from database on startup."""
    _, _, app, db, _, _, ScheduledTask = get_scraper_functions()
    
    with app.app_context():
        tasks = ScheduledTask.query.filter_by(is_active=True).all()
        for task in tasks:
            add_scheduled_task(task)
        logger.info(f"Loaded {len(tasks)} scheduled tasks from database")


def get_scheduler_jobs():
    """Get list of all scheduled jobs."""
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            'id': job.id,
            'name': job.name,
            'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
            'trigger': str(job.trigger)
        })
    return jobs

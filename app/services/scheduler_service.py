"""
Scheduler service for running background tasks
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.memory import MemoryJobStore
import logging
import atexit
from datetime import datetime

class SchedulerService:
    def __init__(self, app=None):
        self.scheduler = None
        self.app = app
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize the scheduler with the Flask app"""
        self.app = app
        
        # Configure scheduler
        jobstores = {
            'default': MemoryJobStore()
        }
        
        executors = {
            'default': ThreadPoolExecutor(max_workers=3)
        }
        
        job_defaults = {
            'coalesce': False,
            'max_instances': 1,
            'misfire_grace_time': 300  # 5 minutes
        }
        
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='Asia/Hong_Kong'  # KGV is in Hong Kong
        )
        
        # Set up logging
        logging.getLogger('apscheduler').setLevel(logging.INFO)
        
        # Start scheduler
        self.scheduler.start()
        
        # Add bulletin scraping job
        self.add_bulletin_scraper_job()
        
        # Shutdown scheduler when app closes
        atexit.register(lambda: self.scheduler.shutdown())
        
        app.logger.info("Scheduler service initialized and started")
    
    def add_bulletin_scraper_job(self):
        """Add the daily bulletin scraper job"""
        try:
            # Remove existing job if it exists
            try:
                self.scheduler.remove_job('daily_bulletin_scraper')
            except Exception:
                pass
            
            # Add new job to run every day at 4 PM (16:00)
            self.scheduler.add_job(
                func=self.scrape_bulletins_job,
                trigger=CronTrigger(hour=16, minute=0),  # 4 PM daily
                id='daily_bulletin_scraper',
                name='Daily Bulletin Scraper',
                replace_existing=True
            )
            
            self.app.logger.info("Daily bulletin scraper job scheduled for 4:00 PM every day")
            
        except Exception as e:
            self.app.logger.error(f"Failed to schedule bulletin scraper job: {e}")
    
    def scrape_bulletins_job(self):
        """Job function to scrape bulletins"""
        try:
            with self.app.app_context():
                from app.services.bulletin_scraper import BulletinScraperService
                
                self.app.logger.info("Starting scheduled bulletin scraping...")
                
                scraper = BulletinScraperService()
                new_count = scraper.scrape_and_save_bulletins(max_items=50)
                
                self.app.logger.info(f"Scheduled bulletin scraping completed: {new_count} new items added")
                
                # Optionally send notification email to admin about the scraping results
                self.send_scraping_notification(new_count)
                
        except Exception as e:
            self.app.logger.error(f"Error in scheduled bulletin scraping: {e}")
    
    def send_scraping_notification(self, new_count):
        """Send notification email to admin about scraping results"""
        try:
            if new_count > 0:
                from app.services.email_service import EmailService
                from app.models import User
                
                # Get admin users
                admin_users = User.query.filter_by(is_admin=True, is_active=True).all()
                
                if admin_users:
                    email_service = EmailService()
                    subject = f"KGV Bulletin Scraper: {new_count} new items found"
                    content = f"""
                    <h3>Daily Bulletin Scraping Report</h3>
                    <p>The scheduled bulletin scraping has completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.</p>
                    <p><strong>Results:</strong></p>
                    <ul>
                        <li>New bulletin items found: {new_count}</li>
                        <li>Scraping time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
                    </ul>
                    <p>You can view the new items in the admin dashboard.</p>
                    """
                    
                    # Send to first admin (you can modify this to send to all admins)
                    email_service.send_custom_email(
                        user=admin_users[0],
                        subject=subject,
                        content=content
                    )
                    
                    self.app.logger.info(f"Scraping notification sent to {admin_users[0].email}")
                    
        except Exception as e:
            self.app.logger.warning(f"Failed to send scraping notification: {e}")
    
    def get_jobs(self):
        """Get information about scheduled jobs"""
        if not self.scheduler:
            return []
        
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        
        return jobs
    
    def trigger_bulletin_scraper_now(self):
        """Manually trigger the bulletin scraper job"""
        try:
            with self.app.app_context():
                self.scrape_bulletins_job()
            return True
        except Exception as e:
            self.app.logger.error(f"Failed to manually trigger bulletin scraper: {e}")
            return False

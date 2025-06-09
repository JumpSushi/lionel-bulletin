#!/usr/bin/env python3
"""
Script to clear all bulletin items and trigger a fresh scrape
"""
import sys
import os

# Add the parent directory to the Python path so we can import from app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import BulletinItem
from app.services.bulletin_scraper import BulletinScraperService

def clear_all_bulletins():
    """Delete all bulletin items from the database"""
    try:
        count = BulletinItem.query.count()
        print(f"Found {count} bulletin items in the database")
        
        if count == 0:
            print("No bulletin items to delete")
            return True
            
        # Ask for confirmation
        response = input(f"Are you sure you want to delete all {count} bulletin items? (y/N): ")
        if response.lower() != 'y':
            print("Operation cancelled")
            return False
            
        # Delete all bulletin items
        BulletinItem.query.delete()
        db.session.commit()
        
        print(f"Successfully deleted all {count} bulletin items")
        return True
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting bulletin items: {e}")
        return False

def trigger_manual_scrape():
    """Trigger a manual scrape of bulletins"""
    try:
        print("\nStarting manual scrape...")
        scraper = BulletinScraperService()
        
        # Scrape with a higher limit to get more items
        new_count = scraper.scrape_and_save_bulletins(max_items=50)
        
        print(f"Manual scrape completed: {new_count} new items added")
        
        # Send notification email to admin
        send_manual_scrape_notification(new_count)
        
        return True
        
    except Exception as e:
        print(f"Error during manual scrape: {e}")
        return False

def send_manual_scrape_notification(new_count):
    """Send notification email to admin about manual scrape results"""
    try:
        if new_count > 0:
            from app.services.email_service import EmailService
            from app.models import User
            from datetime import datetime
            
            # Get admin users
            admin_users = User.query.filter_by(is_admin=True, is_active=True).all()
            
            if admin_users:
                email_service = EmailService()
                subject = f"KGV Bulletin Manual Scrape: {new_count} new items found"
                content = f"""
                <h3>Manual Bulletin Scraping Report</h3>
                <p>A manual bulletin scrape has been completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.</p>
                <p><strong>Results:</strong></p>
                <ul>
                    <li>Database cleared and refreshed</li>
                    <li>New bulletin items found: {new_count}</li>
                    <li>Scraping time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
                </ul>
                <p>You can view the new items in the admin dashboard.</p>
                """
                
                # Send to first admin
                email_service.send_custom_email(
                    user=admin_users[0],
                    subject=subject,
                    content=content
                )
                
                print(f"Notification email sent to {admin_users[0].email}")
                
    except Exception as e:
        print(f"Warning: Failed to send notification email: {e}")

def main():
    """Main function"""
    print("KGV Bulletin Clear and Scrape Tool")
    print("=" * 40)
    
    # Create Flask app context
    app = create_app()
    
    with app.app_context():
        # Step 1: Clear all bulletin items
        print("Step 1: Clearing all bulletin items...")
        if not clear_all_bulletins():
            print("Failed to clear bulletin items. Aborting.")
            return 1
            
        # Step 2: Trigger manual scrape
        print("\nStep 2: Triggering manual scrape...")
        if not trigger_manual_scrape():
            print("Failed to trigger manual scrape.")
            return 1
            
        print("\nOperation completed successfully!")
        
        # Show final count
        final_count = BulletinItem.query.count()
        print(f"Database now contains {final_count} bulletin items")
        
    return 0

if __name__ == "__main__":
    sys.exit(main())

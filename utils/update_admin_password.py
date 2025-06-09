#!/usr/bin/env python3
"""
Script to update the admin user's password
"""
import os
import sys
from datetime import datetime

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User

def update_admin_password():
    """Update the admin user's password"""
    app = create_app()
    
    with app.app_context():
        try:
            # Find the admin user
            admin_user = User.query.filter_by(email='email').first()
            
            if not admin_user:
                print("Admin user not found!")
                return
            
            # Get new password from environment variable or prompt user
            new_password = os.getenv('NEW_ADMIN_PASSWORD')
            if not new_password:
                import getpass
                new_password = getpass.getpass("Enter new admin password: ")
            
            if not new_password:
                print("❌ Password cannot be empty")
                return
            admin_user.set_password(new_password)
            db.session.commit()
            
            print(f"✅ Admin password updated successfully!")
            print(f"Email: {admin_user.email}")
            print(f"New Password: {new_password}")
            
            # Test the password
            if admin_user.check_password(new_password):
                print("✅ Password verification successful!")
            else:
                print("❌ Password verification failed!")
                
        except Exception as e:
            print(f"❌ Error updating password: {e}")
            db.session.rollback()

if __name__ == "__main__":
    update_admin_password()

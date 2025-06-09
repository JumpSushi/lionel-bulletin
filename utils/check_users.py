#!/usr/bin/env python3
"""
Script to check users in the database
"""
import os
import sys
from datetime import datetime

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User

def check_users():
    """Check all users in the database"""
    app = create_app()
    
    with app.app_context():
        try:
            users = User.query.all()
            
            if not users:
                print("No users found in the database.")
                return
            
            print(f"Found {len(users)} user(s) in the database:\n")
            print("-" * 80)
            
            for user in users:
                print(f"ID: {user.id}")
                print(f"Email: {user.email}")
                print(f"Name: {user.name}")
                print(f"Is Admin: {user.is_admin}")
                print(f"Is Active: {user.is_active}")
                print(f"Email Verified: {user.is_email_verified}")
                print(f"Preferences Set: {user.preferences_set}")
                print(f"Email Frequency: {user.email_frequency}")
                print(f"Year Group: {user.year_group}")
                print(f"Created At: {user.created_at}")
                print(f"Last Login: {user.last_login}")
                print("-" * 80)
                
        except Exception as e:
            print(f"Error checking users: {e}")

if __name__ == "__main__":
    check_users()

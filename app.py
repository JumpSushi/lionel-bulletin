#!/usr/bin/env python3
"""
KGV Bulletin Service - Main Application
A Flask web application for managing and distributing KGV school bulletins
with user authentication and email notifications.
"""

from app import create_app
from app.models import db, User, BulletinItem, EmailLog, EmailSubscription
import os
import logging
from logging.handlers import RotatingFileHandler

def create_admin_user(app):
    """Create default admin user if it doesn't exist"""
    with app.app_context():
        admin = User.query.filter_by(email='admin@kgv.edu.hk').first()
        if not admin:
            admin = User(
                name='Admin User',
                email='admin@kgv.edu.hk',
                is_admin=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Default admin user created: admin@kgv.edu.hk/admin123")
        else:
            print("Admin user already exists")

def setup_logging(app):
    """Setup application logging"""
    if not app.debug and not app.testing:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        
        file_handler = RotatingFileHandler(
            'logs/kgv_bulletin.log',
            maxBytes=10240000,
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        
        app.logger.setLevel(logging.INFO)
        app.logger.info('KGV Bulletin Service startup')

def main():
    """Main application entry point"""
    app = create_app()
    
    # Setup logging
    setup_logging(app)
    
    # Create database tables
    with app.app_context():
        db.create_all()
        create_admin_user(app)
    
    # Get configuration
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', 8081))  # Changed to 8081
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    print(f"""
    ╔══════════════════════════════════════════════════════════╗
    ║                KGV Bulletin Service                      ║
    ║                                                          ║
    ║  🌐 Running on: http://{host}:{port}                    ║
    ║  🔧 Debug mode: {'ON' if debug else 'OFF'}                             ║
    ║  🗄️  Database: SQLite                                    ║
    ║  📧 Email: {'Configured' if app.config.get('MAIL_SERVER') else 'Not configured'}                                  ║
    ║                                                          ║
    ║  Default admin credentials:                              ║
    ║  Email: admin@kgv.edu.hk                                 ║
    ║  Password: admin123                                      ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    try:
        app.run(
            host=host,
            port=port,
            debug=debug,
            threaded=True
        )
    except KeyboardInterrupt:
        print("\n\n🛑 Application stopped by user")
    except Exception as e:
        print(f"\n💥 Application error: {e}")
        app.logger.error(f"Application startup error: {e}")

if __name__ == '__main__':
    main()

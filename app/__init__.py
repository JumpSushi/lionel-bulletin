from flask import Flask, jsonify, request, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_cors import CORS
from dotenv import load_dotenv
import os
from datetime import timedelta, datetime

# Load environment variables
load_dotenv()

# Initialize extensions
db = SQLAlchemy()
jwt = JWTManager()
mail = Mail()
migrate = Migrate()
cors = CORS()

def create_app(config_name='default'):
    app = Flask(__name__)
    
    # Load configuration based on environment
    if config_name == 'production':
        from config_production import ProductionConfig
        app.config.from_object(ProductionConfig)
    else:
        # Default configuration
        app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
        app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key')
        app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///bulletin_service.db')
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        # JWT Configuration
        app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=4)
        app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=30)
        app.config['JWT_ERROR_MESSAGE_KEY'] = 'error'
        
        # Email configuration
        app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
        app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
        app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
        app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
        app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
        app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', os.getenv('MAIL_USERNAME'))
    
    # Initialize extensions with app
    db.init_app(app)
    jwt.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app)
    
    # Initialize scheduler service (only in production or when explicitly enabled)
    enable_scheduler = os.getenv('ENABLE_SCHEDULER', 'true').lower() == 'true'
    if enable_scheduler:
        from app.services.scheduler_service import SchedulerService
        scheduler = SchedulerService()
        scheduler.init_app(app)
        app.scheduler = scheduler  # Store reference for access in routes
    
    # Production security enhancements
    if config_name == 'production':
        try:
            from flask_limiter import Limiter
            from flask_limiter.util import get_remote_address
            from flask_talisman import Talisman
            
            # Rate limiting
            limiter = Limiter(
                app,
                key_func=get_remote_address,
                default_limits=["100 per hour", "20 per minute"]
            )
            
            # Security headers
            csp = {
                'default-src': "'self'",
                'script-src': "'self' 'unsafe-inline' https://cdn.jsdelivr.net",
                'style-src': "'self' 'unsafe-inline' https://cdn.jsdelivr.net",
                'font-src': "'self' https://cdn.jsdelivr.net",
                'img-src': "'self' data: https:",
                'connect-src': "'self'"
            }
            
            Talisman(app, 
                    force_https=False,  # Set to True when using HTTPS
                    strict_transport_security=True,
                    content_security_policy=csp,
                    content_security_policy_nonce_in=['script-src', 'style-src'])
            
            # Apply rate limiting to sensitive endpoints
            @app.before_request
            def apply_rate_limits():
                if request.endpoint in ['auth.login', 'auth.register', 'auth.forgot_password']:
                    limiter.limit("5 per minute")
                elif request.endpoint and request.endpoint.startswith('admin.'):
                    limiter.limit("30 per minute")
                    
        except ImportError:
            app.logger.warning("Security packages not available, running without enhanced security")
    
    # Force HTTPS in production
    @app.before_request
    def force_https():
        """Force HTTPS in production environment"""
        if app.config.get('FORCE_HTTPS', False):
            if not request.is_secure and request.headers.get('X-Forwarded-Proto', 'http') != 'https':
                return redirect(request.url.replace('http://', 'https://'), code=301)
    
    # Enhanced security headers
    @app.after_request
    def add_security_headers(response):
        """Add security headers to all responses"""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Add HSTS header in production
        if app.config.get('FORCE_HTTPS', False):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        return response

    # Health check endpoint
    @app.route('/health')
    def health_check():
        """Health check endpoint for monitoring"""
        try:
            # Check database connectivity
            db.session.execute('SELECT 1')
            db_status = 'healthy'
        except Exception as e:
            db_status = f'unhealthy: {str(e)}'
        
        return jsonify({
            'status': 'healthy' if db_status == 'healthy' else 'unhealthy',
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.0.0',
            'database': db_status,
            'environment': config_name
        }), 200 if db_status == 'healthy' else 503
    
    # Metrics endpoint (admin only)
    @app.route('/metrics')
    def metrics():
        """System metrics endpoint for monitoring"""
        from flask_jwt_extended import jwt_required, get_jwt_identity
        from app.models import User, BulletinItem, EmailLog
        
        try:
            # Check if user is admin (if JWT token provided)
            current_user_id = get_jwt_identity()
            if current_user_id:
                user = User.query.get(current_user_id)
                if not user or not user.is_admin:
                    return jsonify({'error': 'Admin access required'}), 403
            else:
                # Allow local access without authentication for monitoring tools
                if not request.remote_addr in ['127.0.0.1', '::1', 'localhost']:
                    return jsonify({'error': 'Authentication required'}), 401
            
            # Basic metrics
            metrics = {
                'timestamp': datetime.utcnow().isoformat(),
                'users': {
                    'total': User.query.count(),
                    'active': User.query.filter_by(is_active=True).count(),
                    'admins': User.query.filter_by(is_admin=True).count()
                },
                'bulletins': {
                    'total': BulletinItem.query.count(),
                    'recent': BulletinItem.query.filter(
                        BulletinItem.created_at >= datetime.utcnow() - timedelta(days=7)
                    ).count()
                },
                'emails': {
                    'total': EmailLog.query.count(),
                    'recent': EmailLog.query.filter(
                        EmailLog.sent_at >= datetime.utcnow() - timedelta(days=7)
                    ).count()
                }
            }
            
            return jsonify(metrics)
            
        except Exception as e:
            app.logger.error(f"Metrics error: {e}")
            return jsonify({'error': 'Failed to get metrics'}), 500
    
    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.bulletin import bulletin_bp
    from app.routes.admin import admin_bp
    from app.routes.main import main_bp
    from app.routes.filters import filters_bp
    
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(bulletin_bp, url_prefix='/api')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(filters_bp, url_prefix='/api')
    app.register_blueprint(main_bp)
    
    # Create tables
    with app.app_context():
        try:
            db.create_all()
            
            # Create admin user if it doesn't exist
            from app.models import User
            admin_email = os.getenv('ADMIN_EMAIL', 'admin@example.com')
            admin_password = os.getenv('ADMIN_PASSWORD')
            
            # Only create admin user if password is provided via environment variable
            if admin_password and not User.query.filter_by(email=admin_email).first():
                admin_user = User(
                    email=admin_email,
                    name='Administrator',
                    is_admin=True,
                    is_active=True,
                    is_email_verified=True,
                    preferences_set=True
                )
                admin_user.set_password(admin_password)
                db.session.add(admin_user)
                db.session.commit()
                print(f"Admin user created: {admin_email}")
        except Exception as e:
            print(f"Warning: Error during database initialization: {e}")
            # Continue anyway, as tables might already exist
    
    return app

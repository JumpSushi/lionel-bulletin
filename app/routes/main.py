from flask import Blueprint, render_template, send_from_directory, request, jsonify, redirect, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from app import db
from app.models import User, BulletinItem, EmailLog, EmailSubscription
from datetime import datetime, timedelta
from sqlalchemy import func
import os
import psutil
from functools import wraps

main_bp = Blueprint('main', __name__)

def admin_required(f):
    """Decorator to require admin access for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            # Try to verify JWT token - this will work for API requests with Authorization header
            verify_jwt_in_request()
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
            
            if not user or not user.is_admin:
                return render_template('error.html', error="403 Forbidden", 
                                     message="You don't have permission to access this page."), 403
            
            return f(*args, **kwargs)
        except Exception:
            # For regular page requests, let the client-side JavaScript handle authentication
            # The admin template will check localStorage and redirect if needed
            return f(*args, **kwargs)
    
    return decorated_function

@main_bp.route('/')
def index():
    return render_template('index.html')

@main_bp.route('/login')
def login_page():
    return render_template('login.html')

@main_bp.route('/register')
def register_page():
    return render_template('register.html')

@main_bp.route('/verify-email')
def verify_email_page():
    return render_template('verify_email.html')

@main_bp.route('/setup-preferences')
def setup_preferences_page():
    return render_template('setup_preferences.html')

@main_bp.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@main_bp.route('/admin')
@admin_required
def admin_dashboard():
    return render_template('admin.html')

@main_bp.route('/profile')
def profile():
    return render_template('profile.html')

# Serve static files
@main_bp.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

# Health check endpoint for monitoring
@main_bp.route('/health')
def health_check():
    """Health check endpoint for production monitoring"""
    try:
        health_data = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.0.0',
            'checks': {}
        }
        
        # Database check
        try:
            db.session.execute('SELECT 1')
            health_data['checks']['database'] = 'healthy'
        except Exception as e:
            health_data['checks']['database'] = f'error: {str(e)}'
            health_data['status'] = 'unhealthy'
        
        # System metrics (optional, requires psutil)
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            health_data['checks']['system'] = {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'disk_percent': (disk.used / disk.total) * 100
            }
            
            # Alert if resources are critically low
            if memory.percent > 90 or (disk.used / disk.total) * 100 > 90:
                health_data['status'] = 'warning'
                
        except Exception:
            # System metrics are optional
            health_data['checks']['system'] = 'unavailable'
        
        # Application check
        try:
            user_count = User.query.count()
            bulletin_count = BulletinItem.query.count()
            health_data['checks']['application'] = {
                'users': user_count,
                'bulletins': bulletin_count
            }
        except Exception as e:
            health_data['checks']['application'] = f'error: {str(e)}'
            health_data['status'] = 'unhealthy'
        
        # Return appropriate HTTP status
        status_code = 200 if health_data['status'] == 'healthy' else 503
        return jsonify(health_data), status_code
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'timestamp': datetime.utcnow().isoformat(),
            'error': str(e)
        }), 500

# API Routes
@main_bp.route('/api/dashboard/stats', methods=['GET'])
@jwt_required()
def dashboard_stats():
    try:
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get bulletin stats for user's year group
        total_bulletins = BulletinItem.query.filter(
            db.or_(
                BulletinItem.year_groups.contains(user.year_group),
                BulletinItem.year_groups.is_(None)
            )
        ).count()
        
        # Get bulletins from last 7 days
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_bulletins = BulletinItem.query.filter(
            BulletinItem.created_at >= week_ago,
            db.or_(
                BulletinItem.year_groups.contains(user.year_group),
                BulletinItem.year_groups.is_(None)
            )
        ).count()
        
        # Get email stats
        emails_sent = EmailLog.query.filter_by(user_id=user.id).count()
        
        # Get subscription status
        subscription = EmailSubscription.query.filter_by(user_id=user.id, is_active=True).first()
        is_subscribed = subscription is not None
        
        return jsonify({
            'total_bulletins': total_bulletins,
            'recent_bulletins': recent_bulletins,
            'emails_sent': emails_sent,
            'is_subscribed': is_subscribed
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get stats', 'details': str(e)}), 500

@main_bp.route('/api/subscription/status', methods=['GET'])
@jwt_required()
def subscription_status():
    try:
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        subscription = EmailSubscription.query.filter_by(user_id=user.id, is_active=True).first()
        
        return jsonify({
            'is_subscribed': subscription is not None,
            'frequency': user.email_frequency,
            'subscription_id': subscription.id if subscription else None
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get subscription status', 'details': str(e)}), 500

@main_bp.route('/api/subscription/toggle', methods=['POST'])
@jwt_required()
def toggle_subscription():
    try:
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Check if user has active subscription
        subscription = EmailSubscription.query.filter_by(user_id=user.id, is_active=True).first()
        
        if subscription:
            # Unsubscribe
            subscription.is_active = False
            subscription.unsubscribed_at = datetime.utcnow()
            action = 'unsubscribed'
        else:
            # Subscribe or reactivate
            existing_subscription = EmailSubscription.query.filter_by(user_id=user.id).first()
            if existing_subscription:
                existing_subscription.is_active = True
                existing_subscription.unsubscribed_at = None
            else:
                # Create new subscription
                new_subscription = EmailSubscription(
                    user_id=user.id,
                    frequency=user.email_frequency,
                    is_active=True
                )
                db.session.add(new_subscription)
            action = 'subscribed'
        
        db.session.commit()
        
        return jsonify({
            'message': f'Successfully {action}',
            'is_subscribed': action == 'subscribed'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to toggle subscription', 'details': str(e)}), 500

@main_bp.route('/api/profile', methods=['GET'])
@jwt_required()
def get_profile():
    try:
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({'user': user.to_dict()}), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get profile', 'details': str(e)}), 500

@main_bp.route('/api/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    try:
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        
        # Update allowed fields
        if 'name' in data:
            user.name = data['name'].strip()
        if 'year_group' in data:
            user.year_group = data['year_group']
        if 'email_frequency' in data:
            user.email_frequency = data['email_frequency']
        
        db.session.commit()
        
        return jsonify({
            'message': 'Profile updated successfully',
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update profile', 'details': str(e)}), 500

@main_bp.route('/api/profile/password', methods=['PUT'])
@jwt_required()
def update_password():
    try:
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        
        if not data.get('current_password') or not data.get('new_password'):
            return jsonify({'error': 'Current password and new password are required'}), 400
        
        # Verify current password
        if not user.check_password(data['current_password']):
            return jsonify({'error': 'Current password is incorrect'}), 400
        
        # Validate new password
        if len(data['new_password']) < 6:
            return jsonify({'error': 'New password must be at least 6 characters long'}), 400
        
        # Update password
        user.set_password(data['new_password'])
        db.session.commit()
        
        return jsonify({'message': 'Password updated successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update password', 'details': str(e)}), 500

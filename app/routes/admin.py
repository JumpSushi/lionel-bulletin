from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import User, BulletinItem, EmailLog, EmailSubscription, BulletinFilter, AdminAction
from datetime import datetime, timedelta
from sqlalchemy import func, or_, and_
import json

admin_bp = Blueprint('admin', __name__)

def log_admin_action(admin_user_id, action_type, target_user_id=None, details=None, ip_address=None):
    """Log admin actions for audit trail"""
    try:
        action = AdminAction(
            admin_user_id=admin_user_id,
            target_user_id=target_user_id,
            action_type=action_type,
            ip_address=ip_address or request.remote_addr
        )
        if details:
            action.set_details(details)
        db.session.add(action)
        db.session.commit()
    except Exception as e:
        print(f"Failed to log admin action: {e}")

def can_delete_user(current_admin_id, target_user_id):
    """Check if current admin can delete target user"""
    # Admin cannot delete themselves
    if current_admin_id == target_user_id:
        return False, "Cannot delete your own account"
    
    target_user = User.query.get(target_user_id)
    if not target_user:
        return False, "User not found"
    
    # If target is admin, check if there are other admins
    if target_user.is_admin:
        admin_count = User.query.filter(User.is_admin == True, User.is_active == True).count()
        if admin_count <= 1:
            return False, "Cannot delete the last admin user"
    
    return True, "OK"

@admin_bp.before_request
def check_admin_access():
    """Check if user has admin access before processing any request to admin endpoints"""
    try:
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        verify_jwt_in_request()
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or not user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
    except Exception:
        return jsonify({'error': 'Authentication required'}), 401

def admin_required(f):
    """Decorator to require admin access"""
    def decorated_function(*args, **kwargs):
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        
        if not user or not user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        return f(*args, **kwargs)
    
    decorated_function.__name__ = f.__name__
    return decorated_function

@admin_bp.route('/users', methods=['GET'])
@jwt_required()
@admin_required
def get_users():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        search = request.args.get('search', '').strip()
        
        query = User.query
        
        # Apply search filter
        if search:
            query = query.filter(
                db.or_(
                    User.email.contains(search),
                    User.name.contains(search)
                )
            )
        
        # Order by creation date (newest first)
        query = query.order_by(User.created_at.desc())
        
        # Paginate
        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        users = [user.to_dict() for user in pagination.items]
        
        return jsonify({
            'users': users,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get users', 'details': str(e)}), 500

# User update and delete routes moved to API section to avoid conflicts

@admin_bp.route('/bulletin-items', methods=['GET'])
@jwt_required()
@admin_required
def get_all_bulletin_items():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        search = request.args.get('search', '').strip()
        item_type = request.args.get('type', '')  # feedback, donation, normal
        
        query = BulletinItem.query
        
        # Apply search filter
        if search:
            query = query.filter(
                db.or_(
                    BulletinItem.title.contains(search),
                    BulletinItem.content.contains(search),
                    BulletinItem.ai_headline.contains(search)
                )
            )
        
        # Apply type filter
        if item_type == 'feedback':
            query = query.filter(BulletinItem.is_feedback == True)
        elif item_type == 'donation':
            query = query.filter(BulletinItem.is_donation == True)
        elif item_type == 'normal':
            query = query.filter(
                BulletinItem.is_feedback == False,
                BulletinItem.is_donation == False
            )
        
        # Order by creation date (newest first)
        query = query.order_by(BulletinItem.created_at.desc())
        
        # Paginate
        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        items = [item.to_dict() for item in pagination.items]
        
        return jsonify({
            'items': items,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get bulletin items', 'details': str(e)}), 500

@admin_bp.route('/bulletin-items/<int:item_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_bulletin_item(item_id):
    try:
        item = BulletinItem.query.get(item_id)
        if not item:
            return jsonify({'error': 'Bulletin item not found'}), 404
        
        db.session.delete(item)
        db.session.commit()
        
        return jsonify({'message': 'Bulletin item deleted successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to delete bulletin item', 'details': str(e)}), 500

@admin_bp.route('/email-logs', methods=['GET'])
@jwt_required()
@admin_required
def get_email_logs():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        status = request.args.get('status', '')  # sent, failed, pending
        
        query = EmailLog.query
        
        # Apply status filter
        if status:
            query = query.filter(EmailLog.status == status)
        
        # Order by creation date (newest first)
        query = query.order_by(EmailLog.created_at.desc())
        
        # Paginate
        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        logs = []
        for log in pagination.items:
            log_dict = log.to_dict()
            log_dict['user_email'] = log.user.email if log.user else 'Unknown'
            logs.append(log_dict)
        
        return jsonify({
            'logs': logs,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get email logs', 'details': str(e)}), 500

@admin_bp.route('/dashboard-stats', methods=['GET'])
@jwt_required()
@admin_required
def get_dashboard_stats():
    try:
        # User statistics
        total_users = User.query.count()
        active_users = User.query.filter(User.is_active == True).count()
        admin_users = User.query.filter(User.is_admin == True).count()
        
        # Users registered in the last 30 days
        month_ago = datetime.utcnow() - timedelta(days=30)
        new_users = User.query.filter(User.created_at >= month_ago).count()
        
        # Bulletin item statistics
        total_items = BulletinItem.query.count()
        feedback_items = BulletinItem.query.filter(BulletinItem.is_feedback == True).count()
        donation_items = BulletinItem.query.filter(BulletinItem.is_donation == True).count()
        
        # Recent items (last 7 days)
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_items = BulletinItem.query.filter(BulletinItem.created_at >= week_ago).count()
        
        # Email statistics
        total_emails = EmailLog.query.count()
        sent_emails = EmailLog.query.filter(EmailLog.status == 'sent').count()
        failed_emails = EmailLog.query.filter(EmailLog.status == 'failed').count()
        
        # Recent emails (last 7 days)
        recent_emails = EmailLog.query.filter(EmailLog.created_at >= week_ago).count()
        
        # Email frequency distribution
        email_frequency_stats = db.session.query(
            User.email_frequency,
            func.count(User.id).label('count')
        ).group_by(User.email_frequency).all()
        
        frequency_distribution = {freq: count for freq, count in email_frequency_stats}
        
        return jsonify({
            'users': {
                'total': total_users,
                'active': active_users,
                'admin': admin_users,
                'new_this_month': new_users
            },
            'bulletin_items': {
                'total': total_items,
                'feedback': feedback_items,
                'donation': donation_items,
                'recent': recent_items
            },
            'emails': {
                'total': total_emails,
                'sent': sent_emails,
                'failed': failed_emails,
                'recent': recent_emails
            },
            'email_frequency_distribution': frequency_distribution,
            'last_updated': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get dashboard stats', 'details': str(e)}), 500

# Bulk Email Functionality
@admin_bp.route('/users/filtered', methods=['POST'])
@jwt_required()
@admin_required
def get_filtered_users():
    """Get users based on filter criteria for bulk operations"""
    try:
        data = request.get_json()
        
        # Build query based on filter criteria
        query = User.query.filter(User.is_active == True)
        
        # Filter by keywords (search in name or email)
        if data.get('keywords'):
            keyword_filters = []
            for keyword in data['keywords']:
                keyword_filters.append(User.name.contains(keyword))
                keyword_filters.append(User.email.contains(keyword))
            query = query.filter(or_(*keyword_filters))
        
        # Filter by admin status
        if data.get('admin_only'):
            query = query.filter(User.is_admin == True)
        
        # Filter by year groups (if stored in user profile - placeholder for now)
        if data.get('year_groups'):
            # This would need to be implemented based on how year groups are stored
            pass
        
        users = query.all()
        
        user_list = []
        for user in users:
            user_list.append({
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'is_admin': user.is_admin,
                'created_at': user.created_at.isoformat()
            })
        
        return jsonify({
            'users': user_list,
            'count': len(user_list)
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get filtered users', 'details': str(e)}), 500

@admin_bp.route('/send-bulk-email', methods=['POST'])
@jwt_required()
@admin_required
def send_bulk_email():
    """Send bulk email to selected users"""
    try:
        current_user_id = int(get_jwt_identity())
        data = request.get_json()
        
        # Validate required fields
        if not data.get('subject') or not data.get('content') or not data.get('recipient_ids'):
            return jsonify({'error': 'Subject, content, and recipient IDs are required'}), 400
        
        subject = data['subject']
        content = data['content']
        recipient_ids = data['recipient_ids']
        
        # Get recipients
        recipients = User.query.filter(User.id.in_(recipient_ids), User.is_active == True).all()
        
        if not recipients:
            return jsonify({'error': 'No valid recipients found'}), 400
        
        # Log the admin action
        log_admin_action(
            admin_user_id=current_user_id,
            action_type='send_bulk_email',
            target_user_id=None,
            details={
                'subject': subject,
                'recipient_count': len(recipients),
                'recipient_ids': recipient_ids
            }
        )
        
        # Send emails using EmailService
        from app.services.email_service import EmailService
        email_service = EmailService()
        
        result = email_service.send_bulk_email(recipients, subject, content)
        
        return jsonify({
            'message': f'Bulk email processed: {result["successful_sends"]} sent, {result["failed_sends"]} failed',
            'successful_sends': result['successful_sends'],
            'failed_sends': result['failed_sends'],
            'total_recipients': result['total_recipients']
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to send bulk email', 'details': str(e)}), 500

@admin_bp.route('/stats', methods=['GET'])
@jwt_required()
@admin_required
def admin_stats():
    """Get admin dashboard statistics"""
    try:
        from app.models import User, BulletinItem, EmailLog, EmailSubscription
        
        total_users = User.query.count()
        total_subscribers = EmailSubscription.query.filter_by(is_active=True).count()
        total_bulletins = BulletinItem.query.count()
        total_emails_sent = EmailLog.query.count()
        
        return jsonify({
            'total_users': total_users,
            'total_subscribers': total_subscribers,
            'total_bulletins': total_bulletins,
            'total_emails_sent': total_emails_sent
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/users', methods=['GET'])
@jwt_required()
@admin_required
def get_all_users():
    """Get all users for admin management"""
    try:
        users = User.query.all()
        users_data = []
        
        for user in users:
            subscription = EmailSubscription.query.filter_by(user_id=user.id, is_active=True).first()
            users_data.append({
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'is_admin': user.is_admin,
                'subscribed': subscription is not None,
                'created_at': user.created_at.isoformat()
            })
        
        return jsonify({'users': users_data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/users/<int:user_id>', methods=['GET'])
@jwt_required()
@admin_required
def get_user(user_id):
    """Get specific user details"""
    try:
        user = User.query.get_or_404(user_id)
        return jsonify({
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'is_admin': user.is_admin,
            'created_at': user.created_at.isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/users', methods=['POST'])
@jwt_required()
@admin_required
def create_user():
    """Create new user"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name') or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Name, email, and password are required'}), 400
        
        # Check if user already exists
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already exists'}), 400
        
        # Create user
        user = User(
            name=data['name'],
            email=data['email'],
            is_admin=data.get('is_admin', False)
        )
        user.set_password(data['password'])
        
        db.session.add(user)
        db.session.commit()
        
        return jsonify({'message': 'User created successfully', 'id': user.id}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@jwt_required()
@admin_required
def admin_update_user(user_id):
    """Update user details"""
    try:
        user = User.query.get_or_404(user_id)
        data = request.get_json()
        
        # Update fields
        if 'name' in data:
            user.name = data['name']
        
        if 'email' in data:
            existing = User.query.filter(User.email == data['email'], User.id != user_id).first()
            if existing:
                return jsonify({'error': 'Email already taken'}), 400
            user.email = data['email']
        
        if 'is_admin' in data:
            user.is_admin = data['is_admin']
        
        if 'password' in data and data['password']:
            user.set_password(data['password'])
        
        db.session.commit()
        return jsonify({'message': 'User updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def admin_delete_user(user_id):
    """Delete user"""
    try:
        user = User.query.get_or_404(user_id)
        
        # Don't allow deleting the last admin
        if user.is_admin:
            admin_count = User.query.filter_by(is_admin=True).count()
            if admin_count <= 1:
                return jsonify({'error': 'Cannot delete the last admin user'}), 400
        
        # Delete related records
        EmailSubscription.query.filter_by(user_id=user_id).delete()
        EmailLog.query.filter_by(user_id=user_id).delete()
        BulletinFilter.query.filter_by(user_id=user_id).delete()
        
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({'message': 'User deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/bulletins', methods=['GET'])
@jwt_required()
@admin_required
def get_all_bulletins():
    """Get all bulletins for admin management"""
    try:
        from app.models import BulletinItem
        bulletins = BulletinItem.query.order_by(BulletinItem.created_at.desc()).all()
        
        bulletins_data = []
        for bulletin in bulletins:
            bulletins_data.append({
                'id': bulletin.id,
                'title': bulletin.title,
                'content': bulletin.content,
                'category': bulletin.category,
                'is_year9': bulletin.is_year9,
                'date': bulletin.date,
                'ai_headline': bulletin.ai_headline,
                'created_at': bulletin.created_at.isoformat()
            })
        
        return jsonify({'bulletins': bulletins_data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/email-logs', methods=['GET'])
@jwt_required()
@admin_required
def admin_get_email_logs():
    """Get email logs for admin monitoring"""
    try:
        logs = EmailLog.query.order_by(EmailLog.sent_at.desc()).limit(100).all()
        
        logs_data = []
        for log in logs:
            logs_data.append({
                'id': log.id,
                'user_email': log.user.email if log.user else 'Unknown',
                'subject': log.subject,
                'status': log.status,
                'sent_at': log.sent_at.isoformat() if log.sent_at else None
            })
        
        return jsonify({'logs': logs_data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/refresh-bulletins', methods=['POST'])
@jwt_required()
@admin_required
def refresh_bulletins():
    """Manually refresh bulletins from KGV website"""
    try:
        from app.services.bulletin_scraper import BulletinScraperService
        
        scraper = BulletinScraperService()
        new_count = scraper.scrape_and_save_bulletins()
        
        return jsonify({
            'message': f'Successfully refreshed bulletins. {new_count} new items added.',
            'new_count': new_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# API Routes
@admin_bp.route('/stats', methods=['GET'])
@jwt_required()
@admin_required
def admin_stats_api():
    try:
        # Get total counts
        total_users = User.query.count()
        total_bulletins = BulletinItem.query.count()
        total_emails = EmailLog.query.count()
        active_subscriptions = EmailSubscription.query.filter_by(is_active=True).count()
        
        # Get recent activity (last 7 days)
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_users = User.query.filter(User.created_at >= week_ago).count()
        recent_bulletins = BulletinItem.query.filter(BulletinItem.created_at >= week_ago).count()
        recent_emails = EmailLog.query.filter(EmailLog.sent_at >= week_ago).count()
        
        return jsonify({
            'total_users': total_users,
            'total_bulletins': total_bulletins,
            'total_emails': total_emails,
            'active_subscriptions': active_subscriptions,
            'recent_users': recent_users,
            'recent_bulletins': recent_bulletins,
            'recent_emails': recent_emails
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get admin stats', 'details': str(e)}), 500

@admin_bp.route('/users', methods=['GET'])
@jwt_required()
@admin_required
def admin_users_api():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        search = request.args.get('search', '').strip()
        
        query = User.query
        
        # Apply search filter
        if search:
            query = query.filter(
                db.or_(
                    User.email.contains(search),
                    User.name.contains(search)
                )
            )
        
        # Order by creation date (newest first)
        query = query.order_by(User.created_at.desc())
        
        # Paginate
        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        users = [user.to_dict() for user in pagination.items]
        
        return jsonify({
            'users': users,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get users', 'details': str(e)}), 500

@admin_bp.route('/bulletins', methods=['GET'])
@jwt_required()
@admin_required
def admin_bulletins_api():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        search = request.args.get('search', '').strip()
        item_type = request.args.get('type', '')
        
        query = BulletinItem.query
        
        # Apply search filter
        if search:
            query = query.filter(
                db.or_(
                    BulletinItem.title.contains(search),
                    BulletinItem.content.contains(search),
                    BulletinItem.ai_headline.contains(search)
                )
            )
        
        # Apply type filter
        if item_type == 'feedback':
            query = query.filter(BulletinItem.is_feedback == True)
        elif item_type == 'donation':
            query = query.filter(BulletinItem.is_donation == True)
        elif item_type == 'normal':
            query = query.filter(
                BulletinItem.is_feedback == False,
                BulletinItem.is_donation == False
            )
        
        # Order by creation date (newest first)
        query = query.order_by(BulletinItem.created_at.desc())
        
        # Paginate
        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        bulletins = [bulletin.to_dict() for bulletin in pagination.items]
        
        return jsonify({
            'bulletins': bulletins,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get bulletins', 'details': str(e)}), 500

@admin_bp.route('/email-logs', methods=['GET'])
@jwt_required()
@admin_required
def admin_email_logs_api():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        status = request.args.get('status', '')
        
        query = EmailLog.query
        
        # Apply status filter
        if status:
            query = query.filter(EmailLog.status == status)
        
        # Order by sent date (newest first)
        query = query.order_by(EmailLog.sent_at.desc())
        
        # Paginate
        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        email_logs = []
        for log in pagination.items:
            log_data = log.to_dict()
            # Add user name for display
            if log.user:
                log_data['user_name'] = log.user.name
                log_data['user_email'] = log.user.email
            email_logs.append(log_data)
        
        return jsonify({
            'email_logs': email_logs,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get email logs', 'details': str(e)}), 500

@admin_bp.route('/refresh-bulletins', methods=['POST'])
@jwt_required()
@admin_required
def admin_refresh_bulletins_api():
    """Manually refresh bulletins from KGV website"""
    try:
        from app.services.bulletin_scraper import BulletinScraperService
        
        scraper = BulletinScraperService()
        new_count = scraper.scrape_and_save_bulletins()
        
        return jsonify({
            'message': f'Successfully refreshed bulletins. {new_count} new items added.',
            'new_count': new_count
        }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to refresh bulletins', 'details': str(e)}), 500

@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@jwt_required()
@admin_required
def admin_update_user_api(user_id):
    try:
        user = User.query.get(user_id)
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
        if 'is_admin' in data:
            user.is_admin = bool(data['is_admin'])
        if 'is_active' in data:
            user.is_active = bool(data['is_active'])
        
        db.session.commit()
        
        return jsonify({
            'message': 'User updated successfully',
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update user', 'details': str(e)}), 500

@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def admin_delete_user_api(user_id):
    try:
        current_user_id = int(get_jwt_identity())
        
        # Check if deletion is allowed
        can_delete, message = can_delete_user(current_user_id, user_id)
        if not can_delete:
            return jsonify({'error': message}), 400
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Log the action before deletion
        log_admin_action(
            admin_user_id=current_user_id,
            action_type='delete_user',
            target_user_id=user_id,
            details={
                'user_name': user.name,
                'user_email': user.email,
                'was_admin': user.is_admin
            }
        )
        
        # Delete related records first
        EmailSubscription.query.filter_by(user_id=user_id).delete()
        EmailLog.query.filter_by(user_id=user_id).delete()
        BulletinFilter.query.filter_by(user_id=user_id).delete()
        AdminAction.query.filter_by(target_user_id=user_id).delete()
        
        # Delete the user
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({'message': 'User deleted successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to delete user', 'details': str(e)}), 500

# Bulletin Filter Management Routes
@admin_bp.route('/bulletin-filters', methods=['GET'])
@jwt_required()
@admin_required
def get_bulletin_filters():
    """Get all bulletin filters for admin management"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        user_id = request.args.get('user_id', type=int)
        
        query = BulletinFilter.query
        
        # Filter by user if specified
        if user_id:
            query = query.filter(BulletinFilter.user_id == user_id)
        
        # Order by creation date (newest first)
        query = query.order_by(BulletinFilter.created_at.desc())
        
        # Paginate
        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        filters = []
        for filter_item in pagination.items:
            filter_data = filter_item.to_dict()
            filter_data['user_name'] = filter_item.user.name if filter_item.user else 'Unknown'
            filters.append(filter_data)
        
        return jsonify({
            'filters': filters,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get bulletin filters', 'details': str(e)}), 500

@admin_bp.route('/bulletin-filters/<int:filter_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_bulletin_filter(filter_id):
    """Delete a bulletin filter"""
    try:
        current_user_id = int(get_jwt_identity())
        filter_item = BulletinFilter.query.get(filter_id)
        
        if not filter_item:
            return jsonify({'error': 'Filter not found'}), 404
        
        # Log the action
        log_admin_action(
            admin_user_id=current_user_id,
            action_type='delete_bulletin_filter',
            target_user_id=filter_item.user_id,
            details={
                'filter_name': filter_item.name,
                'filter_id': filter_id
            }
        )
        
        db.session.delete(filter_item)
        db.session.commit()
        
        return jsonify({'message': 'Filter deleted successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to delete filter', 'details': str(e)}), 500

@admin_bp.route('/bulletin-filters/<int:filter_id>', methods=['GET'])
@jwt_required()
@admin_required
def get_bulletin_filter_details(filter_id):
    """Get detailed information about a specific bulletin filter"""
    try:
        filter_item = BulletinFilter.query.get(filter_id)
        
        if not filter_item:
            return jsonify({'error': 'Filter not found'}), 404
        
        # Get filter data
        filter_data = filter_item.to_dict()
        filter_data['user_name'] = filter_item.user.name if filter_item.user else 'Unknown'
        filter_data['user_email'] = filter_item.user.email if filter_item.user else 'Unknown'
        
        # Add usage statistics (can be enhanced with actual tracking later)
        # For now, we'll provide mock data based on filter complexity and age
        days_since_creation = (datetime.utcnow() - filter_item.created_at).days
        complexity_score = (
            len(filter_data.get('keywords', [])) * 2 +
            len(filter_data.get('categories', [])) * 1.5 +
            len(filter_data.get('year_groups', [])) * 1
        )
        
        filter_data['usage_count'] = max(0, int(days_since_creation * complexity_score * 0.1))
        filter_data['match_count'] = max(1, int(days_since_creation * 2 + complexity_score * 5))
        
        return jsonify(filter_data), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get filter details', 'details': str(e)}), 500

# Admin Action Audit Log Routes
@admin_bp.route('/audit-logs', methods=['GET'])
@jwt_required()
@admin_required
def get_audit_logs():
    """Get admin action audit logs"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        action_type = request.args.get('action_type', '')
        admin_user_id = request.args.get('admin_user_id', type=int)
        
        query = AdminAction.query
        
        # Apply filters
        if action_type:
            query = query.filter(AdminAction.action_type == action_type)
        if admin_user_id:
            query = query.filter(AdminAction.admin_user_id == admin_user_id)
        
        # Order by timestamp (newest first)
        query = query.order_by(AdminAction.timestamp.desc())
        
        # Paginate
        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        logs = [log.to_dict() for log in pagination.items]
        
        return jsonify({
            'logs': logs,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get audit logs', 'details': str(e)}), 500

# Enhanced User Management Routes
@admin_bp.route('/users/<int:user_id>/toggle-admin', methods=['POST'])
@jwt_required()
@admin_required
def toggle_user_admin(user_id):
    """Toggle admin status for a user"""
    try:
        current_user_id = int(get_jwt_identity())
        
        if current_user_id == user_id:
            return jsonify({'error': 'Cannot modify your own admin status'}), 400
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # If removing admin status, check if there are other admins
        if user.is_admin:
            admin_count = User.query.filter(User.is_admin == True, User.is_active == True).count()
            if admin_count <= 1:
                return jsonify({'error': 'Cannot remove admin status from the last admin'}), 400
        
        # Toggle admin status
        old_status = user.is_admin
        user.is_admin = not user.is_admin
        
        # Log the action
        log_admin_action(
            admin_user_id=current_user_id,
            action_type='toggle_admin_status',
            target_user_id=user_id,
            details={
                'user_name': user.name,
                'old_admin_status': old_status,
                'new_admin_status': user.is_admin
            }
        )
        
        db.session.commit()
        
        action = 'granted' if user.is_admin else 'revoked'
        return jsonify({'message': f'Admin privileges {action} for {user.name}'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to toggle admin status', 'details': str(e)}), 500

@admin_bp.route('/users/<int:user_id>/deactivate', methods=['POST'])
@jwt_required()
@admin_required
def deactivate_user(user_id):
    """Deactivate a user account (soft delete)"""
    try:
        current_user_id = int(get_jwt_identity())
        
        if current_user_id == user_id:
            return jsonify({'error': 'Cannot deactivate your own account'}), 400
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # If deactivating admin, check if there are other admins
        if user.is_admin and user.is_active:
            active_admin_count = User.query.filter(User.is_admin == True, User.is_active == True).count()
            if active_admin_count <= 1:
                return jsonify({'error': 'Cannot deactivate the last active admin'}), 400
        
        user.is_active = False
        
        # Log the action
        log_admin_action(
            admin_user_id=current_user_id,
            action_type='deactivate_user',
            target_user_id=user_id,
            details={
                'user_name': user.name,
                'user_email': user.email,
                'was_admin': user.is_admin
            }
        )
        
        db.session.commit()
        
        return jsonify({'message': f'User {user.name} has been deactivated'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to deactivate user', 'details': str(e)}), 500

@admin_bp.route('/users/<int:user_id>/reactivate', methods=['POST'])
@jwt_required()
@admin_required
def reactivate_user(user_id):
    """Reactivate a user account"""
    try:
        current_user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user.is_active = True
        
        # Log the action
        log_admin_action(
            admin_user_id=current_user_id,
            action_type='reactivate_user',
            target_user_id=user_id,
            details={
                'user_name': user.name,
                'user_email': user.email,
                'is_admin': user.is_admin
            }
        )
        
        db.session.commit()
        
        return jsonify({'message': f'User {user.name} has been reactivated'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to reactivate user', 'details': str(e)}), 500

# Scheduler Management Routes
@admin_bp.route('/scheduler/status', methods=['GET'])
@jwt_required()
@admin_required
def get_scheduler_status():
    """Get scheduler status and jobs"""
    try:
        if hasattr(current_app, 'scheduler'):
            jobs = current_app.scheduler.get_jobs()
            return jsonify({
                'scheduler_active': True,
                'jobs': jobs
            }), 200
        else:
            return jsonify({
                'scheduler_active': False,
                'message': 'Scheduler not initialized'
            }), 200
    except Exception as e:
        return jsonify({'error': 'Failed to get scheduler status', 'details': str(e)}), 500

@admin_bp.route('/scheduler/trigger-scraper', methods=['POST'])
@jwt_required()
@admin_required
def trigger_bulletin_scraper():
    """Manually trigger bulletin scraper"""
    try:
        if hasattr(current_app, 'scheduler'):
            success = current_app.scheduler.trigger_bulletin_scraper_now()
            if success:
                return jsonify({'message': 'Bulletin scraper triggered successfully'}), 200
            else:
                return jsonify({'error': 'Failed to trigger bulletin scraper'}), 500
        else:
            return jsonify({'error': 'Scheduler not available'}), 503
    except Exception as e:
        return jsonify({'error': 'Failed to trigger scraper', 'details': str(e)}), 500

@admin_bp.route('/bulletins/clear-all', methods=['POST'])
@jwt_required()
@admin_required
def clear_all_bulletins():
    """Clear all bulletin items from the database"""
    try:
        current_user_id = int(get_jwt_identity())
        
        # Get current count
        count = BulletinItem.query.count()
        
        if count == 0:
            return jsonify({'message': 'No bulletin items to delete', 'deleted_count': 0}), 200
        
        # Log the action
        log_admin_action(
            admin_user_id=current_user_id,
            action_type='clear_all_bulletins',
            target_user_id=None,
            details={'items_deleted': count}
        )
        
        # Delete all bulletin items
        BulletinItem.query.delete()
        db.session.commit()
        
        return jsonify({
            'message': f'Successfully deleted all {count} bulletin items',
            'deleted_count': count
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to clear bulletins', 'details': str(e)}), 500

@admin_bp.route('/bulletins/clear-and-scrape', methods=['POST'])
@jwt_required()
@admin_required
def clear_and_scrape_bulletins():
    """Clear all bulletin items and trigger a fresh scrape"""
    try:
        current_user_id = int(get_jwt_identity())
        
        # Step 1: Clear all bulletin items
        count = BulletinItem.query.count()
        
        # Log the action
        log_admin_action(
            admin_user_id=current_user_id,
            action_type='clear_and_scrape_bulletins',
            target_user_id=None,
            details={'items_deleted': count}
        )
        
        if count > 0:
            BulletinItem.query.delete()
            db.session.commit()
        
        # Step 2: Trigger fresh scrape
        from app.services.bulletin_scraper import BulletinScraperService
        scraper = BulletinScraperService()
        new_count = scraper.scrape_and_save_bulletins(max_items=50)
        
        return jsonify({
            'message': f'Successfully cleared {count} items and added {new_count} new items',
            'deleted_count': count,
            'new_count': new_count
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to clear and scrape bulletins', 'details': str(e)}), 500

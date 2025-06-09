from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import User, BulletinItem, EmailLog, EmailSubscription
from app.services.bulletin_scraper import BulletinScraperService
from datetime import datetime, timedelta
import json

bulletin_bp = Blueprint('bulletin', __name__)

@bulletin_bp.route('/bulletins/<int:bulletin_id>', methods=['GET'])
@jwt_required()
def get_bulletin_detail(bulletin_id):
    """Get details for a specific bulletin"""
    try:
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get the bulletin
        bulletin = BulletinItem.query.get(bulletin_id)
        if not bulletin:
            return jsonify({'error': 'Bulletin not found'}), 404
            
        # Convert to dict for response
        bulletin_data = bulletin.to_dict()
        
        return jsonify({
            'bulletin': bulletin_data
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get bulletin detail', 'details': str(e)}), 500

@bulletin_bp.route('/bulletins', methods=['GET'])
@jwt_required()
def get_bulletins_for_user():
    """Get bulletins for the current user - matches /api/bulletins"""
    try:
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get query parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 50)
        
        # Build query for user's year group
        query = BulletinItem.query.filter(
            db.or_(
                BulletinItem.year_groups.contains(user.year_group),
                BulletinItem.year_groups.is_(None)
            )
        ).filter(
            # Show all teacher posts, only filter out student feedback/donation requests
            db.or_(
                BulletinItem.is_from_student == False,  # Show all teacher posts
                db.and_(
                    BulletinItem.is_from_student == True,  # For student posts
                    BulletinItem.is_feedback == False,     # Filter out feedback
                    BulletinItem.is_donation == False      # Filter out donations
                )
            )
        ).order_by(BulletinItem.created_at.desc())
        
        # Paginate
        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        bulletins = []
        for item in pagination.items:
            bulletin_data = item.to_dict()
            bulletins.append(bulletin_data)
        
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

@bulletin_bp.route('/scrape', methods=['POST'])
@jwt_required()
def scrape_bulletin():
    try:
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        
        if not user or not user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        # Get optional parameters
        data = request.get_json() or {}
        max_items = data.get('max_items', 20)
        generate_headlines = data.get('generate_headlines', True)
        
        # Initialize scraper service
        scraper = BulletinScraperService()
        
        # Scrape bulletin items
        scraped_items = scraper.scrape_bulletin(
            max_items=max_items,
            generate_headlines=generate_headlines
        )
        
        # Save to database
        saved_count = 0
        for item_data in scraped_items:
            # Check if item already exists (by content hash or similar)
            existing_item = BulletinItem.query.filter_by(
                content=item_data['content']
            ).first()
            
            if not existing_item:
                bulletin_item = BulletinItem(
                    title=item_data.get('title'),
                    content=item_data['content'],
                    ai_headline=item_data.get('ai_headline'),
                    is_feedback=item_data.get('is_feedback', False),
                    is_donation=item_data.get('is_donation', False),
                    is_from_student=item_data.get('is_from_student', False),
                    year_groups=item_data.get('year_groups'),
                    scraped_at=datetime.utcnow()
                )
                
                # Set metadata and attachments
                if item_data.get('metadata'):
                    bulletin_item.set_metadata(item_data['metadata'])
                
                if item_data.get('attachments'):
                    bulletin_item.set_attachments(item_data['attachments'])
                
                db.session.add(bulletin_item)
                saved_count += 1
        
        db.session.commit()
        
        return jsonify({
            'message': 'Bulletin scraped successfully',
            'total_scraped': len(scraped_items),
            'new_items_saved': saved_count
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to scrape bulletin', 'details': str(e)}), 500

@bulletin_bp.route('/preview-email', methods=['POST'])
@jwt_required()
def preview_email():
    try:
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json() or {}
        items_count = data.get('items_count', 5)
        
        # Get recent bulletin items for the user's year group
        query = BulletinItem.query
        
        if user.year_group:
            query = query.filter(
                db.or_(
                    BulletinItem.year_groups.contains(user.year_group),
                    BulletinItem.year_groups.is_(None)
                )
            )
        
        # Filter out feedback and donation requests
        query = query.filter(
            BulletinItem.is_feedback == False,
            BulletinItem.is_donation == False
        )
        
        items = query.order_by(BulletinItem.created_at.desc()).limit(items_count).all()
        
        # Generate email content
        from app.services.email_service import EmailService
        email_service = EmailService()
        
        subject, html_content = email_service.generate_bulletin_email(
            user=user,
            items=items
        )
        
        return jsonify({
            'subject': subject,
            'html_content': html_content,
            'items_count': len(items)
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to preview email', 'details': str(e)}), 500

@bulletin_bp.route('/send-test-email', methods=['POST'])
@jwt_required()
def send_test_email():
    try:
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get recent bulletin items
        query = BulletinItem.query
        
        if user.year_group:
            query = query.filter(
                db.or_(
                    BulletinItem.year_groups.contains(user.year_group),
                    BulletinItem.year_groups.is_(None)
                )
            )
        
        query = query.filter(
            BulletinItem.is_feedback == False,
            BulletinItem.is_donation == False
        )
        
        items = query.order_by(BulletinItem.created_at.desc()).limit(5).all()
        
        # Send test email
        from app.services.email_service import EmailService
        email_service = EmailService()
        
        success = email_service.send_bulletin_email(
            user=user,
            items=items,
            is_test=True
        )
        
        if success:
            return jsonify({'message': 'Test email sent successfully'}), 200
        else:
            return jsonify({'error': 'Failed to send test email'}), 500
        
    except Exception as e:
        return jsonify({'error': 'Failed to send test email', 'details': str(e)}), 500

@bulletin_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_bulletin_stats():
    try:
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get statistics
        total_items = BulletinItem.query.count()
        
        # Items from last 7 days
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_items = BulletinItem.query.filter(
            BulletinItem.created_at >= week_ago
        ).count()
        
        # User-specific stats
        if user.year_group:
            year_specific_items = BulletinItem.query.filter(
                BulletinItem.year_groups.contains(user.year_group)
            ).count()
        else:
            year_specific_items = 0
        
        # Feedback and donation counts
        feedback_items = BulletinItem.query.filter(
            BulletinItem.is_feedback == True
        ).count()
        
        donation_items = BulletinItem.query.filter(
            BulletinItem.is_donation == True
        ).count()
        
        return jsonify({
            'total_items': total_items,
            'recent_items': recent_items,
            'year_specific_items': year_specific_items,
            'feedback_items': feedback_items,
            'donation_items': donation_items,
            'last_updated': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get stats', 'details': str(e)}), 500

# Duplicate routes removed - these are handled in main.py

@bulletin_bp.route('/bulletins/<int:bulletin_id>/email', methods=['POST'])
@jwt_required()
def email_bulletin(bulletin_id):
    """Send specific bulletin via email"""
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        bulletin = BulletinItem.query.get(bulletin_id)
        if not bulletin:
            return jsonify({'error': 'Bulletin not found'}), 404
        
        # Import email service
        from app.services.email_service import EmailService
        email_service = EmailService()
        
        # Send email - pass user object and list of bulletins
        success = email_service.send_bulletin_email(user, [bulletin])
        
        if success:
            return jsonify({'message': 'Email sent successfully'}), 200
        else:
            return jsonify({'error': 'Failed to send email'}), 500
            
    except Exception as e:
        return jsonify({'error': 'Failed to send email', 'details': str(e)}), 500

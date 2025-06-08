from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models import User, BulletinItem, BulletinFilter
from datetime import datetime
from sqlalchemy import or_, and_
import json

filters_bp = Blueprint('filters', __name__)

@filters_bp.route('/filters', methods=['GET'])
@jwt_required()
def get_user_filters():
    """Get current user's bulletin filters"""
    try:
        current_user_id = int(get_jwt_identity())
        
        filters = BulletinFilter.query.filter_by(
            user_id=current_user_id,
            is_active=True
        ).order_by(BulletinFilter.created_at.desc()).all()
        
        return jsonify({
            'filters': [f.to_dict() for f in filters]
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get filters', 'details': str(e)}), 500

@filters_bp.route('/filters', methods=['POST'])
@jwt_required()
def create_filter():
    """Create a new bulletin filter"""
    try:
        current_user_id = int(get_jwt_identity())
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name'):
            return jsonify({'error': 'Filter name is required'}), 400
        
        # Check if filter name already exists for this user
        existing = BulletinFilter.query.filter_by(
            user_id=current_user_id,
            name=data['name']
        ).first()
        
        if existing:
            return jsonify({'error': 'Filter name already exists'}), 400
        
        # Create new filter
        filter_obj = BulletinFilter(
            user_id=current_user_id,
            name=data['name'],
            description=data.get('description', ''),
            exclude_feedback=data.get('exclude_feedback', True),
            exclude_donations=data.get('exclude_donations', True)
        )
        
        # Set filter criteria
        if data.get('keywords'):
            filter_obj.set_keywords(data['keywords'])
        if data.get('categories'):
            filter_obj.set_categories(data['categories'])
        if data.get('year_groups'):
            filter_obj.set_year_groups(data['year_groups'])
        
        db.session.add(filter_obj)
        db.session.commit()
        
        return jsonify({
            'message': 'Filter created successfully',
            'filter': filter_obj.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create filter', 'details': str(e)}), 500

@filters_bp.route('/filters/<int:filter_id>', methods=['GET'])
@jwt_required()
def get_filter(filter_id):
    """Get a specific filter"""
    try:
        current_user_id = int(get_jwt_identity())
        
        filter_obj = BulletinFilter.query.filter_by(
            id=filter_id,
            user_id=current_user_id
        ).first()
        
        if not filter_obj:
            return jsonify({'error': 'Filter not found'}), 404
        
        return jsonify({'filter': filter_obj.to_dict()}), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get filter', 'details': str(e)}), 500

@filters_bp.route('/filters/<int:filter_id>', methods=['PUT'])
@jwt_required()
def update_filter(filter_id):
    """Update a bulletin filter"""
    try:
        current_user_id = int(get_jwt_identity())
        data = request.get_json()
        
        filter_obj = BulletinFilter.query.filter_by(
            id=filter_id,
            user_id=current_user_id
        ).first()
        
        if not filter_obj:
            return jsonify({'error': 'Filter not found'}), 404
        
        # Update fields
        if 'name' in data:
            # Check if new name conflicts with existing filters
            existing = BulletinFilter.query.filter(
                BulletinFilter.user_id == current_user_id,
                BulletinFilter.name == data['name'],
                BulletinFilter.id != filter_id
            ).first()
            
            if existing:
                return jsonify({'error': 'Filter name already exists'}), 400
            
            filter_obj.name = data['name']
        
        if 'description' in data:
            filter_obj.description = data['description']
        if 'keywords' in data:
            filter_obj.set_keywords(data['keywords'])
        if 'categories' in data:
            filter_obj.set_categories(data['categories'])
        if 'year_groups' in data:
            filter_obj.set_year_groups(data['year_groups'])
        if 'exclude_feedback' in data:
            filter_obj.exclude_feedback = data['exclude_feedback']
        if 'exclude_donations' in data:
            filter_obj.exclude_donations = data['exclude_donations']
        if 'is_active' in data:
            filter_obj.is_active = data['is_active']
        
        filter_obj.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': 'Filter updated successfully',
            'filter': filter_obj.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update filter', 'details': str(e)}), 500

@filters_bp.route('/filters/<int:filter_id>', methods=['DELETE'])
@jwt_required()
def delete_filter(filter_id):
    """Delete a bulletin filter"""
    try:
        current_user_id = int(get_jwt_identity())
        
        filter_obj = BulletinFilter.query.filter_by(
            id=filter_id,
            user_id=current_user_id
        ).first()
        
        if not filter_obj:
            return jsonify({'error': 'Filter not found'}), 404
        
        db.session.delete(filter_obj)
        db.session.commit()
        
        return jsonify({'message': 'Filter deleted successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to delete filter', 'details': str(e)}), 500

@filters_bp.route('/filters/<int:filter_id>/apply', methods=['GET'])
@jwt_required()
def apply_filter(filter_id):
    """Apply a filter to get filtered bulletins"""
    try:
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        filter_obj = BulletinFilter.query.filter_by(
            id=filter_id,
            user_id=current_user_id,
            is_active=True
        ).first()
        
        if not filter_obj:
            return jsonify({'error': 'Filter not found or inactive'}), 404
        
        # Get query parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 50)
        
        # Build base query
        query = BulletinItem.query
        
        # Apply user's year group filter (unless overridden by filter)
        filter_year_groups = filter_obj.get_year_groups()
        if filter_year_groups:
            year_group_conditions = [BulletinItem.year_groups.contains(yg) for yg in filter_year_groups]
            query = query.filter(or_(*year_group_conditions))
        else:
            # Use user's default year group
            query = query.filter(
                or_(
                    BulletinItem.year_groups.contains(user.year_group),
                    BulletinItem.year_groups.is_(None)
                )
            )
        
        # Apply keyword filters
        keywords = filter_obj.get_keywords()
        if keywords:
            keyword_conditions = []
            for keyword in keywords:
                keyword_conditions.extend([
                    BulletinItem.title.contains(keyword),
                    BulletinItem.content.contains(keyword),
                    BulletinItem.ai_headline.contains(keyword)
                ])
            query = query.filter(or_(*keyword_conditions))
        
        # Apply category filters
        categories = filter_obj.get_categories()
        if categories:
            category_conditions = [BulletinItem.category == cat for cat in categories]
            query = query.filter(or_(*category_conditions))
        
        # Apply exclusion filters
        if filter_obj.exclude_feedback:
            query = query.filter(BulletinItem.is_feedback == False)
        if filter_obj.exclude_donations:
            query = query.filter(BulletinItem.is_donation == False)
        
        # Order by creation date (newest first)
        query = query.order_by(BulletinItem.created_at.desc())
        
        # Paginate
        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        bulletins = [item.to_dict() for item in pagination.items]
        
        return jsonify({
            'bulletins': bulletins,
            'filter': filter_obj.to_dict(),
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
        return jsonify({'error': 'Failed to apply filter', 'details': str(e)}), 500

@filters_bp.route('/filter-options', methods=['GET'])
@jwt_required()
def get_filter_options():
    """Get available options for creating filters"""
    try:
        # Get distinct categories
        categories = db.session.query(BulletinItem.category).distinct().filter(
            BulletinItem.category.isnot(None)
        ).all()
        categories = [cat[0] for cat in categories if cat[0]]
        
        # Get common year groups
        year_groups = ['7', '8', '9', '10', '11', '12', '13']
        
        # Get sample keywords (most common words from titles/headlines)
        # This is a simplified version - in production you might want more sophisticated keyword extraction
        sample_keywords = [
            'sports', 'music', 'drama', 'science', 'mathematics', 'english',
            'history', 'geography', 'art', 'technology', 'careers', 'university',
            'scholarship', 'competition', 'event', 'workshop', 'club', 'society'
        ]
        
        return jsonify({
            'categories': sorted(categories),
            'year_groups': year_groups,
            'sample_keywords': sorted(sample_keywords)
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Failed to get filter options', 'details': str(e)}), 500

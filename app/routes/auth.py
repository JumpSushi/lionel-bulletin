from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity, get_jwt
from app import db
from app.models import User, EmailSubscription, EmailLog
from datetime import datetime, timedelta
import re

auth_bp = Blueprint('auth', __name__)

# In-memory blacklist for revoked tokens (in production, use Redis)
blacklisted_tokens = set()

def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

@auth_bp.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['email', 'name', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        email = data['email'].lower().strip()
        name = data['name'].strip()
        password = data['password']
        
        # Validate email format
        if not is_valid_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        # Validate password strength
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters long'}), 400
        
        # Check if user already exists
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already registered'}), 409
        
        # Create new user
        user = User(
            email=email,
            name=name,
            year_group=data.get('year_group', '9'),
            email_frequency=data.get('email_frequency', 'daily'),
            is_email_verified=False  # Require email verification
        )
        user.set_password(password)
        
        # Generate verification token
        verification_token = user.generate_verification_token()
        
        db.session.add(user)
        db.session.commit()
        
        # Send verification email
        try:
            from app.services.email_service import EmailService
            email_service = EmailService()
            email_service.send_verification_email(user, verification_token)
        except Exception as e:
            print(f"Failed to send verification email: {e}")
        
        return jsonify({
            'message': 'User registered successfully. Please check your email to verify your account.',
            'user': user.to_dict(),
            'email_verification_required': True
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Registration failed', 'details': str(e)}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        
        if not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Email and password are required'}), 400
        
        email = data['email'].lower().strip()
        password = data['password']
        
        # Find user
        user = User.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            return jsonify({'error': 'Invalid email or password'}), 401
        
        if not user.is_active:
            return jsonify({'error': 'Account is disabled'}), 403
        
        # Check if email is verified (unless admin)
        if not user.is_email_verified and not user.is_admin:
            return jsonify({
                'error': 'Email not verified. Please check your email and verify your account.',
                'email_verification_required': True,
                'user_id': user.id
            }), 403
        
        # Update last login
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        # Check if user needs to set preferences (first login after verification)
        needs_preferences = not user.preferences_set and user.is_email_verified
        
        # Create tokens
        access_token = create_access_token(
            identity=str(user.id),
            expires_delta=timedelta(hours=4)  # Increase from 1 hour to 4 hours
        )
        refresh_token = create_refresh_token(
            identity=str(user.id),
            expires_delta=timedelta(days=30)
        )
        
        return jsonify({
            'message': 'Login successful',
            'user': user.to_dict(),
            'access_token': access_token,
            'refresh_token': refresh_token
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Login failed', 'details': str(e)}), 500

@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or not user.is_active:
            return jsonify({'error': 'User not found or inactive'}), 404
        
        # Create new access token
        access_token = create_access_token(
            identity=user.id,
            expires_delta=timedelta(hours=4)  # Use 4 hours to match login
        )
        
        return jsonify({
            'access_token': access_token,
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({'error': 'Token refresh failed', 'details': str(e)}), 500

@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    try:
        jti = get_jwt()['jti']
        blacklisted_tokens.add(jti)
        return jsonify({'message': 'Successfully logged out'}), 200
    except Exception as e:
        return jsonify({'error': 'Logout failed', 'details': str(e)}), 500

@auth_bp.route('/profile', methods=['GET'])
@jwt_required()
def get_profile():
    """Get current user's profile"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get subscription status
        subscription = EmailSubscription.query.filter_by(user_id=user_id, is_active=True).first()
        
        # Get user stats
        emails_received = EmailLog.query.filter_by(user_id=user_id).count()
        
        return jsonify({
            'username': user.name,  # Use name instead of username
            'email': user.email,
            'role': 'admin' if user.is_admin else 'user',
            'email_subscription': subscription is not None,
            'preferences': {
                'sports': True,  # Default preferences
                'academic': True,
                'events': True,
                'general': True
            },
            'stats': {
                'emails_received': emails_received,
                'bulletins_viewed': 0,  # Could be tracked separately
                'last_login': user.created_at.isoformat(),
                'member_since': user.created_at.isoformat()
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    """Update current user's profile"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        
        # Update basic info
        if 'username' in data:
            # Update name field instead of username
            user.name = data['username']
        
        if 'email' in data:
            # Check if email is already taken
            existing = User.query.filter(User.email == data['email'], User.id != user_id).first()
            if existing:
                return jsonify({'error': 'Email already taken'}), 400
            user.email = data['email']
        
        # Update subscription
        if 'email_subscription' in data:
            subscription = EmailSubscription.query.filter_by(user_id=user_id).first()
            if subscription:
                subscription.is_active = data['email_subscription']
            elif data['email_subscription']:
                subscription = EmailSubscription(user_id=user_id, is_active=True)
                db.session.add(subscription)
        
        db.session.commit()
        return jsonify({'message': 'Profile updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/profile/password', methods=['PUT'])
@jwt_required()
def change_password():
    """Change user password"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if not current_password or not new_password:
            return jsonify({'error': 'Both current and new passwords are required'}), 400
        
        if not user.check_password(current_password):
            return jsonify({'error': 'Current password is incorrect'}), 400
        
        if len(new_password) < 8:
            return jsonify({'error': 'New password must be at least 8 characters long'}), 400
        
        user.set_password(new_password)
        db.session.commit()
        
        return jsonify({'message': 'Password changed successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/profile', methods=['DELETE'])
@jwt_required()
def delete_account():
    """Delete user account"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        password = data.get('password')
        
        if not password:
            return jsonify({'error': 'Password is required'}), 400
        
        if not user.check_password(password):
            return jsonify({'error': 'Password is incorrect'}), 400
        
        # Delete related records
        EmailSubscription.query.filter_by(user_id=user_id).delete()
        EmailLog.query.filter_by(user_id=user_id).delete()
        
        # Delete user
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({'message': 'Account deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/verify-email/<token>', methods=['GET'])
def verify_email(token):
    from app.models import User
    try:
        user = User.query.filter_by(email_verification_token=token).first()
        if not user:
            return jsonify({'error': 'Invalid or expired verification token.'}), 400
        if user.is_email_verified:
            return jsonify({'message': 'Email already verified.'}), 200
        user.is_email_verified = True
        user.email_verification_token = None
        user.email_verification_sent_at = None
        db.session.commit()
        return jsonify({'message': 'Email verified successfully. You can now log in.'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Verification failed', 'details': str(e)}), 500

@auth_bp.route('/resend-verification', methods=['POST'])
def resend_verification():
    """Resend email verification to user"""
    try:
        data = request.get_json()
        
        if not data.get('email'):
            return jsonify({'error': 'Email is required'}), 400
        
        email = data['email'].lower().strip()
        
        # Find user
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        if user.is_email_verified:
            return jsonify({'message': 'Email is already verified'}), 200
        
        # Check if we recently sent a verification email (rate limiting)
        if user.email_verification_sent_at:
            time_since_last_send = datetime.utcnow() - user.email_verification_sent_at
            if time_since_last_send.total_seconds() < 300:  # 5 minutes
                remaining_time = 300 - int(time_since_last_send.total_seconds())
                return jsonify({
                    'error': f'Please wait {remaining_time} seconds before requesting another verification email'
                }), 429
        
        # Generate new verification token
        verification_token = user.generate_verification_token()
        db.session.commit()
        
        # Send verification email
        try:
            from app.services.email_service import EmailService
            email_service = EmailService()
            success = email_service.send_verification_email(user, verification_token)
            
            if success:
                return jsonify({
                    'message': 'Verification email sent successfully. Please check your email.'
                }), 200
            else:
                return jsonify({'error': 'Failed to send verification email'}), 500
                
        except Exception as e:
            print(f"Failed to send verification email: {e}")
            return jsonify({'error': 'Failed to send verification email'}), 500
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to resend verification email', 'details': str(e)}), 500

# Check if token is blacklisted
@auth_bp.before_app_request
def check_if_token_revoked():
    try:
        if request.endpoint and 'auth' in request.endpoint:
            return
        
        from flask_jwt_extended import verify_jwt_in_request, get_jwt
        verify_jwt_in_request(optional=True)
        jti = get_jwt().get('jti') if get_jwt() else None
        
        if jti and jti in blacklisted_tokens:
            return jsonify({'error': 'Token has been revoked'}), 401
            
    except Exception:
        pass

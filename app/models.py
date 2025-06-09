from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
import json


class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    is_email_verified = db.Column(db.Boolean, default=False)
    email_verification_token = db.Column(db.String(255), nullable=True)
    email_verification_code = db.Column(db.String(6), nullable=True)  # 6-digit verification code
    email_verification_sent_at = db.Column(db.DateTime, nullable=True)
    email_frequency = db.Column(db.String(20), default='daily')  # daily, weekly, disabled
    year_group = db.Column(db.String(10), default='9')  # Year group preference
    preferences_set = db.Column(db.Boolean, default=False)  # Track if user has set preferences
    email_preferences = db.Column(db.Text, nullable=True)  # JSON string for email preferences
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    subscriptions = db.relationship('EmailSubscription', backref='user', lazy=True, cascade='all, delete-orphan')
    bulletin_filters = db.relationship('BulletinFilter', backref='user', lazy=True, cascade='all, delete-orphan')
    email_logs = db.relationship('EmailLog', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def set_email_preferences(self, preferences_dict):
        """Set user email preferences as JSON"""
        self.email_preferences = json.dumps(preferences_dict) if preferences_dict else None
    
    def get_email_preferences(self):
        """Get user email preferences from JSON"""
        if self.email_preferences:
            return json.loads(self.email_preferences)
        # Return default preferences if none set
        return {
            'sports': True,
            'academic': True,
            'events': True,
            'general': True,
            'feedback_forms': False,
            'donations': False
        }
    
    def generate_verification_token(self):
        """Generate a unique email verification token"""
        import secrets
        self.email_verification_token = secrets.token_urlsafe(32)
        self.email_verification_sent_at = datetime.utcnow()
        return self.email_verification_token
    
    def generate_verification_code(self):
        """Generate a 6-digit verification code"""
        import random
        code = str(random.randint(100000, 999999))
        self.email_verification_code = code
        self.email_verification_sent_at = datetime.utcnow()
        return code
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'is_admin': self.is_admin,
            'is_active': self.is_active,
            'email_frequency': self.email_frequency,
            'year_group': self.year_group,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }

class EmailSubscription(db.Model):
    __tablename__ = 'email_subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    frequency = db.Column(db.String(20), nullable=False)  # daily, weekly
    time_preference = db.Column(db.String(10), default='08:00')  # HH:MM format
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'frequency': self.frequency,
            'time_preference': self.time_preference,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class BulletinItem(db.Model):
    __tablename__ = 'bulletin_items'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    content = db.Column(db.Text, nullable=False)
    ai_headline = db.Column(db.String(200))
    item_metadata = db.Column(db.Text)  # JSON string for metadata
    attachments = db.Column(db.Text)  # JSON string for attachments
    is_feedback = db.Column(db.Boolean, default=False)
    is_donation = db.Column(db.Boolean, default=False)
    is_from_student = db.Column(db.Boolean, default=False)
    has_specific_targeting = db.Column(db.Boolean, default=False)  # Renamed from is_year9 for clarity
    category = db.Column(db.String(50), default='general')  # Category field
    date = db.Column(db.String(20))  # Date string from bulletin
    year_groups = db.Column(db.String(50))  # Comma-separated year groups
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    scraped_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_attachments(self, attachments_list):
        self.attachments = json.dumps(attachments_list) if attachments_list else None
    
    def get_attachments(self):
        return json.loads(self.attachments) if self.attachments else []
    
    def set_metadata(self, metadata_dict):
        self.item_metadata = json.dumps(metadata_dict) if metadata_dict else None
    
    def get_metadata(self):
        return json.loads(self.item_metadata) if self.item_metadata else {}
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'ai_headline': self.ai_headline,
            'metadata': self.get_metadata(),
            'attachments': self.get_attachments(),
            'is_feedback': self.is_feedback,
            'is_donation': self.is_donation,
            'is_from_student': self.is_from_student,
            'is_year9': self.has_specific_targeting,  # Keep for API compatibility
            'has_specific_targeting': self.has_specific_targeting,
            'category': self.category,
            'date': self.date,
            'year_groups': self.year_groups,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'scraped_at': self.scraped_at.isoformat() if self.scraped_at else None
        }


class BulletinFilter(db.Model):
    """User-defined filters for bulletins"""
    __tablename__ = 'bulletin_filters'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    
    # Filter criteria
    keywords = db.Column(db.Text)  # JSON array of keywords
    categories = db.Column(db.Text)  # JSON array of categories  
    year_groups = db.Column(db.Text)  # JSON array of year groups
    exclude_feedback = db.Column(db.Boolean, default=True)
    exclude_donations = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def set_keywords(self, keywords_list):
        self.keywords = json.dumps(keywords_list) if keywords_list else None
    
    def get_keywords(self):
        return json.loads(self.keywords) if self.keywords else []
    
    def set_categories(self, categories_list):
        self.categories = json.dumps(categories_list) if categories_list else None
    
    def get_categories(self):
        return json.loads(self.categories) if self.categories else []
    
    def set_year_groups(self, year_groups_list):
        self.year_groups = json.dumps(year_groups_list) if year_groups_list else None
    
    def get_year_groups(self):
        return json.loads(self.year_groups) if self.year_groups else []
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'description': self.description,
            'keywords': self.get_keywords(),
            'categories': self.get_categories(),
            'year_groups': self.get_year_groups(),
            'exclude_feedback': self.exclude_feedback,
            'exclude_donations': self.exclude_donations,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class AdminAction(db.Model):
    """Log admin actions for audit trail"""
    __tablename__ = 'admin_actions'
    
    id = db.Column(db.Integer, primary_key=True)
    admin_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    target_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action_type = db.Column(db.String(50), nullable=False)  # create_user, delete_user, update_user, etc.
    action_details = db.Column(db.Text)  # JSON details of the action
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))  # Support IPv6
    
    # Relationships
    admin_user = db.relationship('User', foreign_keys=[admin_user_id], backref='admin_actions_performed')
    target_user = db.relationship('User', foreign_keys=[target_user_id], backref='admin_actions_received')
    
    def set_details(self, details_dict):
        self.action_details = json.dumps(details_dict) if details_dict else None
    
    def get_details(self):
        return json.loads(self.action_details) if self.action_details else {}
    
    def to_dict(self):
        return {
            'id': self.id,
            'admin_user_id': self.admin_user_id,
            'admin_user_name': self.admin_user.name if self.admin_user else 'Unknown',
            'target_user_id': self.target_user_id,
            'target_user_name': self.target_user.name if self.target_user else 'Unknown',
            'action_type': self.action_type,
            'action_details': self.get_details(),
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'ip_address': self.ip_address
        }


class EmailLog(db.Model):
    __tablename__ = 'email_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, sent, failed
    error_message = db.Column(db.Text)
    sent_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'subject': self.subject,
            'status': self.status,
            'error_message': self.error_message,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

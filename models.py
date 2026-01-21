from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Campaign(db.Model):
    """GoFundMe campaign model."""
    __tablename__ = 'campaigns'
    
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), unique=True, nullable=False)
    title = db.Column(db.String(500))
    description = db.Column(db.Text)
    goal_amount = db.Column(db.Float)
    currency = db.Column(db.String(10), default='USD')
    category = db.Column(db.String(100))
    organizer = db.Column(db.String(200))
    location = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    snapshots = db.relationship('CampaignSnapshot', backref='campaign', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'url': self.url,
            'title': self.title,
            'description': self.description,
            'goal_amount': self.goal_amount,
            'currency': self.currency,
            'category': self.category,
            'organizer': self.organizer,
            'location': self.location,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'is_active': self.is_active,
            'latest_snapshot': self.snapshots.order_by(CampaignSnapshot.scraped_at.desc()).first().to_dict() if self.snapshots.count() > 0 else None
        }


class CampaignSnapshot(db.Model):
    """Point-in-time snapshot of campaign funding progress."""
    __tablename__ = 'campaign_snapshots'
    
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'), nullable=False)
    amount_raised = db.Column(db.Float)
    donor_count = db.Column(db.Integer)
    share_count = db.Column(db.Integer)
    scraped_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'amount_raised': self.amount_raised,
            'donor_count': self.donor_count,
            'share_count': self.share_count,
            'scraped_at': self.scraped_at.isoformat() if self.scraped_at else None
        }


class Donation(db.Model):
    """Individual donation records."""
    __tablename__ = 'donations'
    
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'), nullable=False)
    donor_name = db.Column(db.String(200))
    amount = db.Column(db.Float)
    message = db.Column(db.Text)
    donated_at = db.Column(db.DateTime)
    scraped_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    campaign = db.relationship('Campaign', backref=db.backref('donations', lazy='dynamic'))
    
    def to_dict(self):
        return {
            'id': self.id,
            'donor_name': self.donor_name,
            'amount': self.amount,
            'message': self.message,
            'donated_at': self.donated_at.isoformat() if self.donated_at else None
        }


class ScheduledTask(db.Model):
    """Scheduled scraping tasks."""
    __tablename__ = 'scheduled_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    task_type = db.Column(db.String(50))  # 'scrape', 'discover'
    schedule = db.Column(db.String(100))  # cron expression
    urls = db.Column(db.Text)  # JSON array of URLs
    is_active = db.Column(db.Boolean, default=True)
    last_run = db.Column(db.DateTime)
    next_run = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'task_type': self.task_type,
            'schedule': self.schedule,
            'is_active': self.is_active,
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'next_run': self.next_run.isoformat() if self.next_run else None
        }


class User(db.Model):
    """User accounts for multi-user support."""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False)
    api_key = db.Column(db.String(64), unique=True)
    tier = db.Column(db.String(20), default='free')  # free, pro, enterprise
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'is_admin': self.is_admin,
            'tier': self.tier,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

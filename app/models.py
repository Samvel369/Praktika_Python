from datetime import datetime
from flask_login import UserMixin
from app.extensions import db, ignored_users

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False, unique=True)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password = db.Column(db.String(256), nullable=False)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)
    avatar_url = db.Column(db.String(300), default="/app/static/uploads/default-avatar.png")
    birthdate = db.Column(db.Date)
    status = db.Column(db.String(100), default="Приветствую всех!")
    about = db.Column(db.Text, default="Пока ничего о себе не рассказал.")
    ignored_users = db.relationship(
        'User',
        secondary=ignored_users,
        primaryjoin=(id == db.foreign(ignored_users.c.ignorer_id)),
        secondaryjoin=(id == db.foreign(ignored_users.c.ignored_id)),
        backref='ignored_by'
    )

class Action(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    text = db.Column(db.String(255), nullable=False)
    is_published = db.Column(db.Boolean, default=False)
    is_daily = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref='actions')


class ActionMark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action_id = db.Column(db.Integer, db.ForeignKey('action.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='marks')
    action = db.relationship('Action', backref='marks')


class FriendRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')  # 'pending', 'accepted', 'declined'

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_requests')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_requests')


class Subscriber(db.Model):
    __tablename__ = 'subscribers'
    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class PotentialFriendView(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    viewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    viewer = db.relationship('User', foreign_keys=[viewer_id], backref='potential_views')
    user = db.relationship('User', foreign_keys=[user_id])

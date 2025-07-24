import os
import uuid
from datetime import datetime, timedelta
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename
from sqlalchemy import or_
from app.extensions import db, login_manager, socketio

def create_app():
    app = Flask(__name__)
    app.secret_key = "mysecretkey"
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI')

    db.init_app(app)
    login_manager.init_app(app)
    socketio.init_app(app)

    login_manager.login_view = 'auth_bp.login'

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.before_request
    def update_last_seen():
        if current_user.is_authenticated:
            current_user.last_active = datetime.utcnow()
            db.session.commit()

    # Регистрируем блюпринты
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.profile import profile_bp
    from app.routes.friends import friends_bp
    from app.routes.actions import actions_bp
    from app.routes.my_actions import my_actions_bp
    from app.routes.world import world_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(friends_bp)
    app.register_blueprint(actions_bp)
    app.register_blueprint(my_actions_bp)
    app.register_blueprint(world_bp)
    
    @app.context_processor
    def inject_user_counts():
        now = datetime.utcnow()
        active_threshold = now - timedelta(seconds=1)
        online_users = User.query.filter(User.last_active >= active_threshold).count()
        total_users = User.query.count()
        return dict(online_users=online_users, total_users=total_users)

    return app

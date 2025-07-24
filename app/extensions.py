from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_moment import Moment
from flask_socketio import SocketIO
from sqlalchemy import Table, Column, Integer, ForeignKey

# Инициализация расширений (без привязки к app)
db = SQLAlchemy()
login_manager = LoginManager()
moment = Moment()
socketio = SocketIO(async_mode='eventlet')  # или 'gevent'

# Настройка login_manager
login_manager.login_view = 'auth.login'

ignored_users = Table(
    'ignored_users',
    db.metadata,
    Column('ignorer_id', Integer, ForeignKey('user.id')),
    Column('ignored_id', Integer, ForeignKey('user.id'))
)
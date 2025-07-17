from flask import Flask, render_template, request, redirect, flash, url_for, jsonify, abort, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import uuid
from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_user, logout_user, current_user, login_required, UserMixin
from sqlalchemy import or_, and_
from flask_socketio import emit, join_room, SocketIO

app = Flask(__name__)
app.secret_key = "mysecretkey"
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI')
db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode='eventlet')
ignored_users = db.Table(
    'ignored_users',
    db.Column('ignorer_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('ignored_id', db.Integer, db.ForeignKey('user.id'))
)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False, unique=True)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password = db.Column(db.String(256), nullable=False)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)
    avatar_url = db.Column(db.String(300), default="/static/uploads/default-avatar.png")
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

def get_possible_friends(user):
    # Все пользователи, кроме себя
    users = User.query.filter(User.id != user.id).all()

    # ID уже отправленных заявок (ожидающих)
    sent_ids = [
        fr.receiver_id for fr in FriendRequest.query.filter_by(sender_id=user.id, status=True).all()
    ]

    # ID тех, кто уже в друзьях
    friend_ids = []
    accepted = FriendRequest.query.filter(
        or_(
            and_(FriendRequest.sender_id == user.id),
            and_(FriendRequest.receiver_id == user.id)
        ),
        FriendRequest.status == 'accepted'
    ).all()
    for fr in accepted:
        if fr.sender_id != user.id:
            friend_ids.append(fr.sender_id)
        else:
            friend_ids.append(fr.receiver_id)

    # Исключаем всех, кому отправлены заявки или кто уже в друзьях
    return [u for u in users if u.id not in sent_ids and u.id not in friend_ids]

@app.before_request
def update_last_seen():
    if current_user.is_authenticated:
        current_user.last_active = datetime.utcnow()
        db.session.commit()


@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('main'))
    return render_template('index.html')


@app.route('/main')
@login_required
def main():
    now = datetime.utcnow()
    active_actions = Action.query.filter(Action.is_published == True, Action.expires_at > now).all()

    from collections import Counter
    one_minute_ago = now - timedelta(minutes=1)
    marks = ActionMark.query.filter(ActionMark.timestamp >= one_minute_ago).all()

    mark_counts = Counter()
    for mark in marks:
        mark_counts[mark.action_id] += 1

    top_actions = sorted(
        active_actions,
        key=lambda a: mark_counts.get(a.id, 0),
        reverse=True
    )[:10]

    return render_template('main.html', top_actions=top_actions)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('Пароли не совпадают')
            return render_template('register.html')
        if not username or not email or not password:
            flash('Заполните все поля!')
            return render_template('register.html')

        hashed_password = generate_password_hash(password)
        new_user = User(username=username, email=email, password=hashed_password)

        db.session.add(new_user)
        db.session.commit()

        flash('Регистрация прошла успешно!')
        return redirect('/')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('main'))
        else:
            return 'Неверный логин или пароль'
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из аккаунта')
    return redirect(url_for('login'))


@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    user = current_user

    if request.method == 'POST':
        # Загружаем аватар
        if 'avatar' in request.files:
            avatar = request.files['avatar']
            if avatar and avatar.filename != '':
                ext = avatar.filename.rsplit('.', 1)[-1].lower()
                allowed = {"png", "jpg", "jpeg", "gif"}
                if ext in allowed:
                    filename = f"{uuid.uuid4().hex}.{ext}"
                    upload_path = os.path.join('static', 'uploads', filename)
                    os.makedirs(os.path.dirname(upload_path), exist_ok=True)
                    avatar.save(upload_path)
                    user.avatar_url = f"/static/uploads/{filename}"

        # Обработка остальных полей
        birthdate_input = request.form.get('birthdate')
        if birthdate_input:
            try:
                user.birthdate = datetime.strptime(birthdate_input, '%Y-%m-%d').date()
            except:
                flash("Неверный формат даты")

        user.status = request.form.get('status') or ''
        user.about = request.form.get('about') or ''

        db.session.commit()
        flash("Профиль обновлён!")
        return redirect(url_for('profile'))

    return render_template('edit_profile.html', user=user)

@app.route('/profile/<int:user_id>')
@login_required
def view_profile(user_id):
    user = User.query.get_or_404(user_id)

    # Сам себе — полный профиль
    if user.id == current_user.id:
        return render_template('profile.html', user=user)

    # Проверка: друг или нет
    is_friend = FriendRequest.query.filter_by(
        sender_id=current_user.id,
        receiver_id=user.id,
        status='accepted'  # <--- Важно: сравниваем со строкой
    ).first() or FriendRequest.query.filter_by(
        sender_id=user.id,
        receiver_id=current_user.id,
        status='accepted'
    ).first()

    # Если друг — показать public-профиль
    if is_friend:
        return render_template('public_profile.html', user=user)

    # Не друг — ограниченный просмотр
    return render_template('user_preview.html', user=user)

@app.route('/upload_avatar', methods=['POST'])
@login_required
def upload_avatar():
    file = request.files.get('avatar')
    if file and '.' in file.filename:
        ext = file.filename.rsplit('.', 1)[1].lower()
        allowed = {"png", "jpg", "jpeg", "gif"}
        if ext in allowed:
            filename = f"{uuid.uuid4().hex}.{ext}"
            upload_path = os.path.join("static", "uploads", filename)
            os.makedirs(os.path.dirname(upload_path), exist_ok=True)
            file.save(upload_path)

            # Обновляем путь к аватару только у текущего пользователя
            current_user.avatar_url = f"/static/uploads/{filename}"
            db.session.commit()
            flash("Аватар успешно обновлён.")
        else:
            flash("Недопустимый формат файла.")
    else:
        flash("Файл не выбран.")
    
    return redirect(url_for("profile"))

@app.route('/world', methods=['GET', 'POST'])
@login_required
def world():
    user = current_user
    if request.method == 'POST':
        if 'daily_action' in request.form:
            text = request.form.get('daily_action')
            if text:
                action = Action(text=text, is_daily=True, is_published=True)
                db.session.add(action)
                db.session.commit()
        elif 'draft_action' in request.form:
            text = request.form.get('draft_action')
            if text:
                action = Action(user_id=user.id, text=text, is_published=False)
                db.session.add(action)
                db.session.commit()
        return redirect(url_for('world'))

    now = datetime.utcnow()
    daily_actions = Action.query.filter_by(is_daily=True).all()
    my_created = Action.query.filter_by(user_id=user.id, is_published=False).all()
    published = Action.query.filter(Action.is_published == True, Action.expires_at > now)\
        .order_by(Action.created_at.desc()).all()

    return render_template('world.html',
        daily_actions=daily_actions,
        my_created=my_created,
        published=published)


@app.route('/edit_action/<int:action_id>', methods=['POST'])
@login_required
def edit_action(action_id):
    user = current_user
    action = Action.query.get(action_id)
    new_text = request.form.get('edit_text')

    if action and new_text and action.user_id == user.id:
        action.text = new_text
        db.session.commit()
    return redirect(url_for('world'))


@app.route('/delete_action/<int:action_id>', methods=['POST'])
@login_required
def delete_action(action_id):
    user = current_user
    action = Action.query.get(action_id)

    if action and action.user_id == user.id:
        db.session.delete(action)
        db.session.commit()
    return redirect(url_for('world'))


@app.route('/publish_action/<int:action_id>', methods=['POST'])
@login_required
def publish_action(action_id):
    user = current_user
    action = Action.query.get(action_id)
    if not action or action.user_id != user.id:
        return jsonify({'error': 'Not allowed'}), 403

    recent_actions = Action.query.filter(
        Action.user_id == user.id,
        Action.is_published == True,
        Action.text.ilike(f"%{action.text}%")
    ).all()

    now = datetime.utcnow()
    for a in recent_actions:
        if a.expires_at and a.expires_at > now:
            return jsonify({'error': 'Похожее действие уже опубликовано'}), 400

    data = request.get_json()
    duration_minutes = int(data.get('duration', 10))
    action.is_published = True
    action.expires_at = now + timedelta(minutes=duration_minutes)
    db.session.commit()
    return jsonify({'success': True, 'id': action.id, 'text': action.text})


@app.route('/update_activity', methods=['POST'])
@login_required
def update_activity():
    current_user.last_active = datetime.utcnow()
    db.session.commit()
    print(f"✅ Активность обновлена для: {current_user.username}")
    return '', 204


@app.route('/get_published_actions')
def get_published_actions():
    now = datetime.utcnow()
    actions = Action.query.filter(Action.is_published == True, Action.expires_at > now)\
        .order_by(Action.created_at.desc()).all()
    return jsonify([{'id': a.id, 'text': a.text} for a in actions])


@app.context_processor
def inject_user_counts():
    now = datetime.utcnow()
    active_threshold = now - timedelta(seconds=1)
    online_users = User.query.filter(User.last_active >= active_threshold).count()
    total_users = User.query.count()
    return dict(online_users=online_users, total_users=total_users)


@app.route('/mark_action/<int:action_id>', methods=['POST'])
@login_required
def mark_action(action_id):
    user_id = current_user.id
    now = datetime.utcnow()
    ten_minutes_ago = now - timedelta(minutes=10)

    print(f"✅ [mark_action] Пользователь {user_id} отмечает действие {action_id} в {now}")

    # Проверка на повторную отметку
    recent_mark = ActionMark.query.filter_by(user_id=user_id, action_id=action_id) \
        .filter(ActionMark.timestamp >= ten_minutes_ago).first()
    if recent_mark:
        remaining = 600 - int((now - recent_mark.timestamp).total_seconds())
        print("⏱ Уже была отметка. Ждём:", remaining, "секунд")
        return jsonify({'error': 'wait', 'remaining': remaining})

    # Добавляем новую отметку
    print("➕ Добавляем новую отметку")
    new_mark = ActionMark(user_id=user_id, action_id=action_id)
    db.session.add(new_mark)
    db.session.commit()

    # Уведомляем автора
    action = Action.query.get(action_id)
    if action and action.user_id != user_id:
        print(f"📣 Действие принадлежит пользователю {action.user_id}, проверим potential_friend_view")

        existing_view = PotentialFriendView.query.filter_by(
            viewer_id=action.user_id,
            user_id=user_id
        ).first()

        if not existing_view:
            print("🆕 Нет записи — добавим")
            view = PotentialFriendView(
                viewer_id=action.user_id,
                user_id=user_id,
                timestamp=now
            )
            db.session.add(view)
            db.session.commit()
        else:
            print("⚠ Запись уже есть, не добавляем")

        # Отправим сокет-событие
        print(f"📤 Отправка socketio-события в комнату user_{action.user_id}")
        socketio.emit(
            'update_possible_friends',
            {
                'user_id': user_id,
                'username': current_user.username
            },
            to=f'user_{action.user_id}'
        )

    return jsonify({'success': True})

@app.route('/get_mark_counts')
def get_mark_counts():
    now = datetime.utcnow()
    one_minute_ago = now - timedelta(minutes=1)
    recent_marks = ActionMark.query.filter(ActionMark.timestamp >= one_minute_ago).all()

    counts = {}
    for mark in recent_marks:
        counts[mark.action_id] = counts.get(mark.action_id, 0) + 1

    return jsonify(counts)


@app.route('/action/<int:action_id>')
def action_card(action_id):
    action = Action.query.get_or_404(action_id)
    marks = ActionMark.query.filter_by(action_id=action.id).order_by(ActionMark.timestamp.asc()).all()
    user_ids = list({mark.user_id for mark in marks})
    users = User.query.filter(User.id.in_(user_ids)).all()

    from collections import defaultdict
    minute_counts = defaultdict(int)
    for mark in marks:
        minute_key = mark.timestamp.replace(second=0, microsecond=0)
        minute_counts[minute_key] += 1
    peak = max(minute_counts.values(), default=0)

    return render_template('action_card.html', action=action, total_marks=len(marks), users=users, peak=peak)


@app.route('/action_stats/<int:action_id>')
def action_stats(action_id):
    now = datetime.utcnow()
    one_minute_ago = now - timedelta(minutes=1)

    all_marks = ActionMark.query.filter_by(action_id=action_id).all()
    recent_marks = ActionMark.query.filter(ActionMark.action_id == action_id, ActionMark.timestamp >= one_minute_ago).all()

    total_marks = len(all_marks)
    peak = len(recent_marks)
    user_ids = set(mark.user_id for mark in all_marks)
    users = User.query.filter(User.id.in_(user_ids)).all()

    return jsonify({
        'total_marks': total_marks,
        'peak': peak,
        'users': [user.username for user in users]
    })


@app.route('/my_actions', methods=['GET', 'POST'])
@login_required
def my_actions():
    user = current_user

    if request.method == 'POST':
        if 'new_action' in request.form:
            text = request.form.get('new_action')
            if text:
                action = Action(user_id=user.id, text=text, is_published=False)
                db.session.add(action)
                db.session.commit()
                flash('Новое действие добавлено!')

        elif 'delete_id' in request.form:
            action = Action.query.get(int(request.form.get('delete_id')))
            if action and action.user_id == user.id:
                ActionMark.query.filter_by(action_id=action.id).delete()
                db.session.delete(action)
                db.session.commit()
                flash('Действие и все отметки удалены!')

        elif 'publish_id' in request.form:
            action = Action.query.get(int(request.form.get('publish_id')))
            if action and action.user_id == user.id:
                action.is_published = True
                duration = int(request.form.get('duration', 10))
                action.expires_at = datetime.utcnow() + timedelta(minutes=duration)
                db.session.commit()
                flash('Действие опубликовано! Перейдите в "Наш мир" для просмотра.', 'info')

        return redirect(url_for('my_actions'))

    drafts = Action.query.filter_by(user_id=user.id, is_published=False).order_by(Action.created_at.desc()).all()
    published = Action.query.filter_by(user_id=user.id, is_published=True).order_by(Action.created_at.desc()).all()

    return render_template('my_actions.html', drafts=drafts, published=published, now=datetime.utcnow())


@app.route('/get_top_actions')
def get_top_actions():
    now = datetime.utcnow()
    one_minute_ago = now - timedelta(minutes=1)

    active_actions = Action.query.filter(Action.is_published == True, Action.expires_at > now).all()
    marks = ActionMark.query.filter(ActionMark.timestamp >= one_minute_ago).all()

    from collections import Counter
    mark_counts = Counter(mark.action_id for mark in marks)

    top_actions = sorted(active_actions, key=lambda a: mark_counts.get(a.id, 0), reverse=True)[:10]

    return jsonify([
        {
            'id': a.id,
            'text': a.text,
            'marks': mark_counts.get(a.id, 0)
        } for a in top_actions
    ])


@app.route("/friends", methods=["GET", "POST"])
@login_required
def friends():
    # Принятые друзья
    friends_1 = FriendRequest.query.filter_by(sender_id=current_user.id, status='accepted').all()
    friends_2 = FriendRequest.query.filter_by(receiver_id=current_user.id, status='accepted').all()
    friends = [req.receiver for req in friends_1] + [req.sender for req in friends_2]

    # Входящие и исходящие заявки
    incoming_requests = FriendRequest.query.filter_by(receiver_id=current_user.id, status='pending').all()
    outgoing_requests = FriendRequest.query.filter_by(sender_id=current_user.id, status='pending').all()

    # Все действия текущего пользователя
    user_actions = Action.query.filter_by(user_id=current_user.id).all()
    user_action_ids = [action.id for action in user_actions]

    # Пользователи, отметившиеся на моих действиях
    marked_user_ids_raw = (
        db.session.query(ActionMark.user_id)
        .filter(ActionMark.action_id.in_(user_action_ids))
        .filter(ActionMark.user_id != current_user.id)
        .distinct()
        .all()
    )
    marked_user_ids = [uid for (uid,) in marked_user_ids_raw]

    # Подписчики (отметились, но не в друзьях и не в заявках)
    subscriber_entries = Subscriber.query.filter_by(owner_id=current_user.id).all()
    subscribed_ids = [s.subscriber_id for s in subscriber_entries]

    # Исключаем: себя, друзей, заявки, игнор и подписчиков
    exclude_ids = set(
        [current_user.id] +
        [r.receiver_id for r in outgoing_requests] +
        [r.sender_id for r in incoming_requests] +
        [f.id for f in friends] +
        subscribed_ids
    )

    if hasattr(current_user, 'ignored_users'):
        exclude_ids.update(u.id for u in current_user.ignored_users)

    # ===== НОВОЕ: фильтрация по времени хранения =====
    if request.method == 'POST':
        selected_minutes = int(request.form.get('cleanup_time', 10))
        session['cleanup_time'] = selected_minutes
        return redirect(url_for('friends'))

    cleanup_time = session.get('cleanup_time', 10)
    threshold_time = datetime.utcnow() - timedelta(minutes=cleanup_time)

    recent_potential_ids = db.session.query(PotentialFriendView.user_id) \
        .filter(PotentialFriendView.viewer_id == current_user.id) \
        .filter(PotentialFriendView.timestamp >= threshold_time).all()
    recent_ids = [uid for (uid,) in recent_potential_ids]

    # Возможные друзья = отметились, не в исключениях, и не устарели
    possible_ids = [
        uid for uid in marked_user_ids
        if uid not in exclude_ids and uid in recent_ids
    ]
    users = User.query.filter(User.id.in_(possible_ids)).all()

    # Подписчики
    subscribers = User.query.filter(User.id.in_(subscribed_ids)).all()

    # Подписки
    subscriptions = (
        db.session.query(User)
        .join(Subscriber, Subscriber.owner_id == User.id)
        .filter(Subscriber.subscriber_id == current_user.id)
        .all()
    )

    return render_template(
        "friends.html",
        users=users,
        friends=friends,
        incoming_requests=incoming_requests,
        outgoing_requests=outgoing_requests,
        subscribers=subscribers,
        subscriptions=subscriptions,
        cleanup_time=cleanup_time  # передаём в шаблон
    )
    
def get_friend_ids(user_id):
    friend_ids = set()

    # Принятые заявки — мы добавили или нас добавили
    accepted_requests = FriendRequest.query.filter(
        ((FriendRequest.sender_id == user_id) | (FriendRequest.receiver_id == user_id)) &
        (FriendRequest.status == 'accepted')
    ).all()

    for fr in accepted_requests:
        if fr.sender_id != user_id:
            friend_ids.add(fr.sender_id)
        if fr.receiver_id != user_id:
            friend_ids.add(fr.receiver_id)

    return friend_ids

@app.route('/friends_partial')
@login_required
def friends_partial():
    cleanup_time = session.get('cleanup_time', 10)
    cutoff = datetime.utcnow() - timedelta(minutes=cleanup_time)

    # 🔎 Найдём user_id всех, кто отмечался на действиях текущего пользователя
    recent_viewers_subq = db.session.query(PotentialFriendView.user_id).filter(
        PotentialFriendView.viewer_id == current_user.id,
        PotentialFriendView.timestamp >= cutoff
    ).subquery()

    # 🔒 Исключим: самого себя, друзей, входящие/исходящие заявки, подписки
    friend_ids = get_friend_ids(current_user.id)

    incoming = db.session.query(FriendRequest.sender_id).filter_by(
        receiver_id=current_user.id
    ).subquery()

    outgoing = db.session.query(FriendRequest.receiver_id).filter_by(
        sender_id=current_user.id
    ).subquery()

    subscribers = db.session.query(Subscriber.owner_id).filter_by(
        subscriber_id=current_user.id
    ).subquery()

    # 👥 Выборка возможных друзей
    users = User.query.filter(
        User.id.in_(recent_viewers_subq),
        User.id != current_user.id,
        ~User.id.in_(friend_ids),
        ~User.id.in_(incoming),
        ~User.id.in_(outgoing),
        ~User.id.in_(subscribers)
    ).all()

    return render_template(
        'partials/possible_friends.html',
        users=users,
        cleanup_time=cleanup_time
    )

@app.route('/send_friend_request/<int:user_id>', methods=['POST'])
@login_required
def send_friend_request(user_id):
    existing = FriendRequest.query.filter_by(sender_id=current_user.id, receiver_id=user_id).first()
    if existing:
        flash("Заявка уже отправлена.")
        return redirect(url_for('friends'))

    # Создаём новую заявку
    new_request = FriendRequest(
        sender_id=current_user.id,
        receiver_id=user_id,
        status='pending'
    )
    db.session.add(new_request)

    # 🧹 Удаляем из подписчиков, если такой есть
    subscriber = Subscriber.query.filter_by(
        owner_id=current_user.id,
        subscriber_id=user_id
    ).first()
    if subscriber:
        db.session.delete(subscriber)

    db.session.commit()

    # Уведомляем через Socket.IO
    data = {
        'request_id': new_request.id,
        'sender_id': current_user.id,
        'sender_username': current_user.username,
        'sender_avatar': current_user.avatar_url
    }
    socketio.emit('friend_request_sent', data, to=f"user_{user_id}")

    return redirect(url_for('friends'))

@app.route("/cancel_friend_request/<int:request_id>", methods=["POST"])
@login_required
def cancel_friend_request(request_id):
    req = FriendRequest.query.get_or_404(request_id)

    # Проверка: только отправитель или получатель может отменить
    if req.sender_id != current_user.id and req.receiver_id != current_user.id:
        abort(403)

    # Флаг подписки
    subscribe_flag = request.form.get("subscribe") == "true"

    if subscribe_flag:
        # Кто кого подписывает:
        # current_user — это получатель заявки (оставляющий в подписчиках)
        # req.sender_id — это отправитель заявки
        subscriber_id = req.sender_id
        owner_id = current_user.id

        existing = Subscriber.query.filter_by(
            subscriber_id=subscriber_id,
            owner_id=owner_id
        ).first()

        if not existing:
            new_sub = Subscriber(subscriber_id=subscriber_id, owner_id=owner_id)
            db.session.add(new_sub)
            db.session.commit()

            # Реалтайм-сообщение владельцу (current_user)
            subscriber_user = User.query.get(subscriber_id)
            subscriber_data = {
                'subscriber_id': subscriber_user.id,
                'subscriber_username': subscriber_user.username,
                'subscriber_avatar': subscriber_user.avatar_url
            }
            socketio.emit("new_subscriber", subscriber_data, to=f"user_{owner_id}")

            # Реалтайм-сообщение подписчику
            socketio.emit("subscribed_to", {
                'user_id': owner_id,
                'username': current_user.username,
                'avatar': current_user.avatar_url
            }, to=f"user_{subscriber_id}")

    # Удаляем заявку
    db.session.delete(req)
    db.session.commit()

    # Уведомим обе стороны
    socketio.emit('friend_request_cancelled', {
        'request_id': request_id,
        'user_id': current_user.id,
    }, room=f"user_{req.sender_id}")

    socketio.emit('friend_request_cancelled', {
        'request_id': request_id,
        'user_id': current_user.id,
    }, room=f"user_{req.receiver_id}")

    return redirect(url_for("friends"))

# При обработке приёма заявки
@app.route('/accept_friend_request/<int:request_id>', methods=['POST'])
@login_required
def accept_friend_request(request_id):
    friend_request = FriendRequest.query.get_or_404(request_id)

    # Только получатель может принять
    if friend_request.receiver_id != current_user.id:
        flash("Вы не можете принять эту заявку.")
        return redirect(url_for('friends'))

    friend_request.status = 'accepted'

    # Удаляем подписку, если sender был подписчиком receiver
    subscription = Subscriber.query.filter_by(
        owner_id=friend_request.receiver_id,
        subscriber_id=friend_request.sender_id
    ).first()

    if subscription:
        db.session.delete(subscription)

        # Уведомим sender'а, что его подписка исчезла
        socketio.emit('subscriber_removed', {
            'subscriber_id': friend_request.sender_id
        }, to=f"user_{friend_request.receiver_id}")

    db.session.commit()

    # Отправка данных в обе стороны
    data = {
        'request_id': request_id,
        'friend_id': current_user.id,
        'friend_username': current_user.username,
        'friend_avatar': current_user.avatar_url
    }

    socketio.emit('friend_accepted', data, to=f"user_{friend_request.sender_id}")
    socketio.emit('friend_accepted', data, to=f"user_{friend_request.receiver_id}")

    return redirect(url_for('friends'))

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room(f"user_{current_user.id}")
        
@socketio.on('join')
def on_join(data):
    room = data.get('room')
    join_room(room)
    print(f"🔌 Пользователь присоединился к комнате: {room}")

@app.route('/remove_friend/<int:user_id>', methods=['POST'])
@login_required
def remove_friend(user_id):
    req1 = FriendRequest.query.filter_by(sender_id=current_user.id, receiver_id=user_id, status='accepted').first()
    req2 = FriendRequest.query.filter_by(sender_id=user_id, receiver_id=current_user.id, status='accepted').first()

    if req1:
        db.session.delete(req1)
    if req2:
        db.session.delete(req2)

    db.session.commit()
    flash('Пользователь удалён из друзей.')

    # Уведомляем другого пользователя в реальном времени
    socketio.emit('friend_removed', {
        'user_id': current_user.id
    }, room=f'user_{user_id}')

    return redirect(url_for('friends'))

@app.route("/remove_possible_friend/<int:user_id>", methods=["POST"])
@login_required
def remove_possible_friend(user_id):
    user_to_ignore = User.query.get_or_404(user_id)
    if user_to_ignore not in current_user.ignored_users:
        current_user.ignored_users.append(user_to_ignore)
        db.session.commit()
    return redirect(url_for("friends"))

@app.route('/subscribe/<int:user_id>', methods=['POST'])
@login_required
def subscribe(user_id):
    # Проверка: нельзя подписаться на себя
    if user_id == current_user.id:
        abort(400)

    # Проверка: уже подписан
    existing = Subscriber.query.filter_by(subscriber_id=current_user.id, owner_id=user_id).first()
    if existing:
        flash("Вы уже подписаны.")
        return redirect(url_for('friends'))

    # Создание подписки
    new_sub = Subscriber(subscriber_id=current_user.id, owner_id=user_id)
    db.session.add(new_sub)
    db.session.commit()

    # Отправка сокет-события пользователю-владельцу
    data = {
        'subscriber_id': current_user.id,
        'subscriber_username': current_user.username,
        'subscriber_avatar': current_user.avatar_url,
    }
    socketio.emit('new_subscriber', {
        'subscriber_id': current_user.id,
        'subscriber_username': current_user.username,
        'subscriber_avatar': current_user.avatar_url
    }, to=f"user_{user_id}")

    return redirect(url_for('friends'))

@app.route("/cleanup_potential_friends", methods=["POST"])
@login_required
def cleanup_potential_friends():
    minutes = int(request.form.get("cleanup_time", 10))
    threshold = datetime.utcnow() - timedelta(minutes=minutes)

    # Удаляем старые записи только для текущего пользователя
    PotentialFriendView.query.filter(
        PotentialFriendView.viewer_id == current_user.id,
        PotentialFriendView.timestamp < threshold
    ).delete()
    db.session.commit()
    return '', 204  # Успешно, без контента

@app.route('/leave_in_subscribers/<int:user_id>', methods=['POST'])
@login_required
def leave_in_subscribers(user_id):
    if user_id == current_user.id:
        return redirect(url_for('friends'))

    existing = Subscriber.query.filter_by(subscriber_id=user_id, owner_id=current_user.id).first()
    if not existing:
        sub = Subscriber(subscriber_id=user_id, owner_id=current_user.id)
        db.session.add(sub)
        db.session.commit()
    return redirect(url_for('friends'))

@app.route('/debug/friends')
@login_required
def debug_friends():
    requests = FriendRequest.query.all()
    output = ""
    for r in requests:
        output += f"From: {r.sender_id}, To: {r.receiver_id}, Status: {r.status}<br>"
    return output

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)

from flask import Flask, render_template, request, redirect, flash, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_user, logout_user, current_user, login_required, UserMixin
from sqlalchemy import or_, and_
from flask_socketio import SocketIO
from flask_socketio import emit, join_room

app = Flask(__name__)
app.secret_key = "mysecretkey"
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI')
db = SQLAlchemy(app)
socketio = SocketIO(app)

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
    avatar_url = db.Column(db.String(300), default="/static/default-avatar.png")
    birthdate = db.Column(db.Date)
    status = db.Column(db.String(100), default="Приветствую всех!")
    about = db.Column(db.Text, default="Пока ничего о себе не рассказал.")


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
    status = db.Column(db.String(20), default='pending')  # Добавлено поле
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_requests')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_requests')

def get_possible_friends(user):
    # Все пользователи, кроме себя
    users = User.query.filter(User.id != user.id).all()

    # ID уже отправленных заявок (ожидающих)
    sent_ids = [
        fr.receiver_id for fr in FriendRequest.query.filter_by(sender_id=user.id, status='pending').all()
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
        if 'avatar' in request.files:
            avatar = request.files['avatar']
            if avatar and avatar.filename != '':
                filename = secure_filename(avatar.filename)
                filepath = os.path.join('static/uploads', filename)
                avatar.save(filepath)
                user.avatar_url = '/' + filepath

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

    # Проверка: друзья или нет
    is_friend = FriendRequest.query.filter_by(
        sender_id=current_user.id,
        receiver_id=user.id,
        status='accepted'
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

    recent_mark = ActionMark.query.filter_by(user_id=user_id, action_id=action_id)\
        .filter(ActionMark.timestamp >= ten_minutes_ago).first()

    if recent_mark:
        remaining = 600 - int((now - recent_mark.timestamp).total_seconds())
        return jsonify({'error': 'wait', 'remaining': remaining})

    new_mark = ActionMark(user_id=user_id, action_id=action_id)
    db.session.add(new_mark)
    db.session.commit()
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


@app.route('/friends')
@login_required
def friends():
    # Возможные друзья (оставляем как есть)
    user_actions = Action.query.filter_by(user_id=current_user.id).all()
    user_action_ids = [action.id for action in user_actions]

    marked_user_ids = (
        db.session.query(ActionMark.user_id)
        .filter(ActionMark.action_id.in_(user_action_ids))
        .filter(ActionMark.user_id != current_user.id)
        .distinct()
        .all()
    )

    marked_user_ids = [uid for (uid,) in marked_user_ids]
    suggested_friends = User.query.filter(User.id.in_(marked_user_ids)).all()

    # Входящие заявки (оставляем объекты FriendRequest)
    incoming_requests = FriendRequest.query.filter_by(
        receiver_id=current_user.id, status='pending'
    ).all()

    # Принятые друзья
    friends = []
    requests = FriendRequest.query.filter_by(status='accepted').all()
    for req in requests:
        if req.sender_id == current_user.id:
            friends.append(User.query.get(req.receiver_id))
        elif req.receiver_id == current_user.id:
            friends.append(User.query.get(req.sender_id))

    return render_template(
        'friends.html',
        users=suggested_friends,
        incoming_requests=incoming_requests,
        friends=friends
    )

@app.route('/send_friend_request/<int:user_id>', methods=['POST'])
@login_required
def send_friend_request(user_id):
    existing = FriendRequest.query.filter_by(sender_id=current_user.id, receiver_id=user_id).first()
    if existing:
        flash("Заявка уже отправлена.")
        return redirect(url_for('friends'))

    new_request = FriendRequest(sender_id=current_user.id, receiver_id=user_id)
    db.session.add(new_request)
    db.session.commit()

    # Подготовка данных для JS
    data = {
        'request_id': new_request.id,
        'sender_id': current_user.id,
        'sender_username': current_user.username,
        'sender_avatar': current_user.avatar_url
    }

    # Отправляем realtime-событие только получателю
    socketio.emit('friend_request_sent', data, to=f"user_{user_id}")

    return redirect(url_for('friends'))


# При обработке приёма заявки
@app.route('/accept_friend_request/<int:request_id>', methods=['POST'])
@login_required
def accept_friend_request(request_id):
    friend_request = FriendRequest.query.get_or_404(request_id)
    
    if friend_request.receiver_id != current_user.id:
        flash("Вы не можете принять эту заявку.")
        return redirect(url_for('friends'))

    # Подтверждаем дружбу
    friend_request.status = 'accepted'
    db.session.commit()

    # Отправка событий двум пользователям
    data = {
        'request_id': request_id,
        'friend_id': current_user.id,
        'friend_username': current_user.username,
        'friend_avatar': current_user.avatar_url
    }

    # Отправка отправителю заявки
    socketio.emit('friend_accepted', data, to=f"user_{friend_request.sender.id}")
    
    # Отправка получателю заявки
    socketio.emit('friend_accepted', data, to=f"user_{friend_request.receiver_id}")

    return redirect(url_for('friends'))

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room(f"user_{current_user.id}")

@app.route('/remove_friend/<int:user_id>', methods=['POST'])
@login_required
def remove_friend(user_id):
    # Находим заявку в обе стороны
    request = FriendRequest.query.filter(
        or_(
            and_(FriendRequest.sender_id == current_user.id, FriendRequest.receiver_id == user_id),
            and_(FriendRequest.sender_id == user_id, FriendRequest.receiver_id == current_user.id)
        ),
        FriendRequest.status == 'accepted'
    ).first()

    if request:
        db.session.delete(request)
        db.session.commit()
        flash('Пользователь удалён из друзей.')
    else:
        flash('Вы больше не друзья.')

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
    socketio.run(app, debug=True)

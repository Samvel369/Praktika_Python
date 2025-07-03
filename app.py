from flask import Flask, render_template, request, redirect, flash, session, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
from flask import jsonify

app = Flask(__name__)
app.secret_key = "mysecretkey"
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://samlion:333693@localhost/flaskdb'
db = SQLAlchemy(app)

class User(db.Model):
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

    user = db.relationship('User', backref='actions')
    
class ActionMark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action_id = db.Column(db.Integer, db.ForeignKey('action.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='marks')
    action = db.relationship('Action', backref='marks')

@app.before_request
def update_last_seen():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            user.last_active = datetime.utcnow()
            db.session.commit()

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('main'))
    return render_template('index.html')

@app.route('/main')
def main():
    user_id = session.get('user_id')
    if not user_id:
        flash('Пожалуйста, войдите в систему')
        return redirect(url_for('login'))

    top_actions = ['Чихнул', 'Зевнул', 'Смеялся']
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
            session['user_id'] = user.id
            return redirect(url_for('main'))
        else:
            return 'Неверный логин или пароль'
    return render_template('login.html')

@app.route('/profile')
def profile():
    user_id = session.get('user_id')
    if not user_id:
        flash('Пожалуйста, войдите в систему')
        return redirect(url_for('login'))
    user = User.query.get(user_id)
    return render_template('profile.html', user=user)

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    user_id = session.get('user_id')
    if not user_id:
        flash('Пожалуйста, войдите в систему')
        return redirect(url_for('login'))

    user = User.query.get(user_id)
    if user is None:
        flash('Пользователь не найден.')
        return redirect(url_for('login'))

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

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Вы вышли из аккаунта')
    return redirect(url_for('login'))

@app.route('/world', methods=['GET', 'POST'])
def world():
    user_id = session.get('user_id')
    if not user_id:
        flash('Пожалуйста, войдите в систему')
        return redirect(url_for('login'))
    
    user = User.query.get(user_id)

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

    daily_actions = Action.query.filter_by(is_daily=True).all()
    my_created = Action.query.filter_by(user_id=user.id).order_by(Action.created_at.desc()).all()
    published = Action.query.filter_by(is_published=True).all()  # <- ВАЖНО

    return render_template('world.html',
        daily_actions=daily_actions,
        my_created=my_created,
        published=published
    )

@app.route('/edit_action/<int:action_id>', methods=['POST'])
def edit_action(action_id):
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    action = Action.query.get(action_id)

    new_text = request.form.get('edit_text')

    if action and new_text and user and action.user_id == user.id:
        action.text = new_text
        db.session.commit()

    return redirect(url_for('world'))

@app.route('/delete_action/<int:action_id>', methods=['POST'])
def delete_action(action_id):
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    action = Action.query.get(action_id)

    if action and user and action.user_id == user.id:
        db.session.delete(action)
        db.session.commit()

    return redirect(url_for('world'))

@app.route('/publish_action/<int:action_id>', methods=['POST'])
def publish_action(action_id):
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    if not user_id:
        return redirect(url_for('login'))

    action = Action.query.get(action_id)
    if action and user and action.user_id == user.id:
        action.is_published = True
        db.session.commit()

    return redirect(url_for('world'))

@app.route('/update_activity', methods=['POST'])
def update_activity():
    user_id = session.get('user_id')
    if user_id:
        user = User.query.get(user_id)
        if user:
            user.last_active = datetime.utcnow()
            db.session.commit()
            print(f"✅ Активность обновлена для: {user.username}")
    return '', 204

@app.context_processor
def inject_user_counts():
    now = datetime.utcnow()
    active_threshold = now - timedelta(seconds=1)
    online_users = User.query.filter(User.last_active >= active_threshold).count()
    total_users = User.query.count()
    return dict(online_users=online_users, total_users=total_users)

@app.route('/mark_action/<int:action_id>', methods=['POST'])
def mark_action(action_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

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



with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)

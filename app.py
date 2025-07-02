from flask import Flask, render_template, request, redirect, flash, session, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename

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

# 🟡 Здесь позже появится таблица "действий"

@app.before_request
def update_last_seen():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            user.last_seen = datetime.utcnow()
            db.session.commit()

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('main'))
    return render_template('index.html')

@app.route('/main')
def main():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите в систему')
        return redirect(url_for('login'))

    # В будущем — тут будет top_actions из базы
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
        # Загрузка аватара
        if 'avatar' in request.files:
            avatar = request.files['avatar']
            if avatar and avatar.filename != '':
                filename = secure_filename(avatar.filename)
                filepath = os.path.join('static/uploads', filename)
                avatar.save(filepath)
                user.avatar_url = '/' + filepath  # путь для браузера

        # Остальные поля
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

@app.route('/world')
def world():
    user_id = session.get('user_id')
    if not user_id:
        flash('Пожалуйста, войдите в систему')
        return redirect(url_for('login'))
    return render_template('world.html')

@app.route('/update_activity', methods=['POST'])
def update_activity():
    user_id = session.get('user_id')
    if user_id:
        user = User.query.get(user_id)
        if user:
            user.last_active = datetime.utcnow()
            db.session.commit()
    return '', 204

@app.context_processor
def inject_user_counts():
    now = datetime.utcnow()
    active_threshold = now - timedelta(seconds=1)
    online_users = User.query.filter(User.last_active >= active_threshold).count()
    total_users = User.query.count()
    return dict(online_users=online_users, total_users=total_users)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)

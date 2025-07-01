from flask import Flask, render_template, request, redirect, flash, session, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "mysecretkey"
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://samlion:333693@localhost/flaskdb'
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False, unique=True)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password = db.Column(db.String(256), nullable=False)
    

@app.route('/')
def home():
    return render_template('index.html')

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
            return redirect(url_for('profile'))
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

@app.route('/world')
def world():
    user_id = session.get('user_id')
    if not user_id:
        flash('Пожалуйста, войдите в систему')
        return redirect(url_for('login'))
    
    return render_template('world.html')
    

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
from flask import Flask, render_template, request, redirect, flash

app = Flask(__name__)
app.secret_key = "mysecretkey"
app.config['SQLACHEMY_DATABASE_URL'] = 'postgresql://samlion:333693@localhost/flaskdb'

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
        flash('Регистрация прошла успешно!')
        return redirect('/')
    
    return render_template('register.html')

if __name__ == '__main__':
    app.run(debug=True)
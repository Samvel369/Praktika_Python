# routes/profile.py

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.models import db, User, FriendRequest
from datetime import datetime, timedelta
import os
import uuid
from app.extensions import db

profile_bp = Blueprint('profile_bp', __name__)

@profile_bp.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

@profile_bp.route('/profile/<int:user_id>')
@login_required
def view_profile(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        return render_template('profile.html', user=user)

    is_friend = FriendRequest.query.filter_by(
        sender_id=current_user.id,
        receiver_id=user.id,
        status='accepted'
    ).first() or FriendRequest.query.filter_by(
        sender_id=user.id,
        receiver_id=current_user.id,
        status='accepted'
    ).first()

    if is_friend:
        return render_template('public_profile.html', user=user)

    return render_template('user_preview.html', user=user)

@profile_bp.route('/edit_profile', methods=['GET', 'POST'])
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
                    upload_path = os.path.join('app', 'static', 'uploads', filename)
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
        return redirect(url_for('profile_bp.profile'))

    return render_template('edit_profile.html', user=user)

@profile_bp.route('/user_preview/<int:user_id>')
@login_required
def user_preview(user_id):
    user = User.query.get_or_404(user_id)
    full_access = False

    if user.id == current_user.id:
        full_access = True
    else:
        # Проверка: являются ли друзьями
        is_friend = FriendRequest.query.filter_by(
            sender_id=current_user.id, receiver_id=user.id, status='accepted'
        ).first() or FriendRequest.query.filter_by(
            sender_id=user.id, receiver_id=current_user.id, status='accepted'
        ).first()
        full_access = bool(is_friend)

    return render_template('user_preview.html', user=user, full_access=full_access)

@profile_bp.route('/upload_avatar', methods=['POST'])
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

            current_user.avatar_url = f"/static/uploads/{filename}"
            db.session.commit()
            flash("Аватар успешно обновлён.")
        else:
            flash("Недопустимый формат файла.")
    else:
        flash("Файл не выбран.")
    
    return redirect(url_for("profile_bp.profile"))

@profile_bp.route('/update_activity', methods=['POST'])
@login_required
def update_activity():
    current_user.last_active = datetime.utcnow()
    db.session.commit()
    print(f"✅ Активность обновлена для: {current_user.username}")
    return '', 204

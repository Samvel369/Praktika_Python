from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app.extensions import db, socketio
from app.models import Action, ActionMark, PotentialFriendView, User

world_bp = Blueprint("world_bp", __name__)


@world_bp.route('/world', methods=['GET', 'POST'])
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
        return redirect(url_for('world_bp.world'))

    now = datetime.utcnow()
    daily_actions = Action.query.filter_by(is_daily=True).all()
    my_created = Action.query.filter_by(user_id=user.id, is_published=False).all()
    published = Action.query.filter(
        Action.is_published == True,
        Action.expires_at > now
    ).order_by(Action.created_at.desc()).all()

    return render_template(
        'world.html',
        daily_actions=daily_actions,
        my_created=my_created,
        published=published
    )

@world_bp.route('/edit_action/<int:action_id>', methods=['POST'])
@login_required
def edit_action(action_id):
    user = current_user
    action = Action.query.get(action_id)
    new_text = request.form.get('edit_text')

    if action and new_text and action.user_id == user.id:
        action.text = new_text
        db.session.commit()
    return redirect(url_for('world_bp.world'))


@world_bp.route('/delete_action/<int:action_id>', methods=['POST'])
@login_required
def delete_action(action_id):
    user = current_user
    action = Action.query.get(action_id)

    if action and action.user_id == user.id:
        db.session.delete(action)
        db.session.commit()
    return redirect(url_for('world_bp.world'))


@world_bp.route('/publish_action/<int:action_id>', methods=['POST'])
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

@world_bp.route('/get_published_actions')
def get_published_actions():
    now = datetime.utcnow()
    actions = Action.query.filter(
        Action.is_published == True,
        Action.expires_at > now
    ).order_by(Action.created_at.desc()).all()
    
    return jsonify([{'id': a.id, 'text': a.text} for a in actions])

@world_bp.route('/mark_action/<int:action_id>', methods=['POST'])
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

@world_bp.route('/get_mark_counts')
def get_mark_counts():
    now = datetime.utcnow()
    one_minute_ago = now - timedelta(minutes=1)
    recent_marks = ActionMark.query.filter(ActionMark.timestamp >= one_minute_ago).all()

    counts = {}
    for mark in recent_marks:
        counts[mark.action_id] = counts.get(mark.action_id, 0) + 1

    return jsonify(counts)

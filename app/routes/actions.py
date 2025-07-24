from flask import Blueprint, request, jsonify, render_template, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from app.extensions import db, socketio
from app.models import Action, ActionMark, PotentialFriendView, User

actions_bp = Blueprint("actions_bp", __name__)


@actions_bp.route('/action/<int:action_id>')
def action_card(action_id):
    action = Action.query.get_or_404(action_id)
    marks = (
        ActionMark.query
        .filter_by(action_id=action.id)
        .order_by(ActionMark.timestamp.asc())
        .all()
    )

    user_ids = {mark.user_id for mark in marks}
    users = User.query.filter(User.id.in_(user_ids)).all()

    minute_counts = defaultdict(int)
    for mark in marks:
        minute_key = mark.timestamp.replace(second=0, microsecond=0)
        minute_counts[minute_key] += 1
    peak = max(minute_counts.values(), default=0)

    return render_template(
        'action_card.html',
        action=action,
        total_marks=len(marks),
        users=users,
        peak=peak
    )

@actions_bp.route('/mark_action/<int:action_id>', methods=['POST'])
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


@actions_bp.route('/get_mark_counts')
def get_mark_counts():
    now = datetime.utcnow()
    one_minute_ago = now - timedelta(minutes=1)
    recent_marks = ActionMark.query.filter(ActionMark.timestamp >= one_minute_ago).all()

    counts = {}
    for mark in recent_marks:
        counts[mark.action_id] = counts.get(mark.action_id, 0) + 1

    return jsonify(counts)


@actions_bp.route("/get_published_actions")
def get_published_actions():
    now = datetime.utcnow()
    actions = Action.query.filter(Action.is_published == True, Action.expires_at > now)\
        .order_by(Action.created_at.desc()).all()

    return jsonify([{'id': a.id, 'text': a.text} for a in actions])

@actions_bp.route('/action_stats/<int:action_id>')
def action_stats(action_id):
    now = datetime.utcnow()
    one_minute_ago = now - timedelta(minutes=1)

    all_marks = ActionMark.query.filter_by(action_id=action_id).all()
    recent_marks = ActionMark.query.filter(
        ActionMark.action_id == action_id,
        ActionMark.timestamp >= one_minute_ago
    ).all()

    total_marks = len(all_marks)
    peak = len(recent_marks)
    user_ids = {mark.user_id for mark in all_marks}
    users = User.query.filter(User.id.in_(user_ids)).all()

    return jsonify({
        'total_marks': total_marks,
        'peak': peak,
        'users': [user.username for user in users]
    })
    
@actions_bp.route('/get_top_actions')
def get_top_actions():
    now = datetime.utcnow()
    one_minute_ago = now - timedelta(minutes=1)

    active_actions = (
        Action.query
        .filter(Action.is_published.is_(True), Action.expires_at > now)
        .all()
    )
    marks = ActionMark.query.filter(ActionMark.timestamp >= one_minute_ago).all()

    mark_counts = Counter(mark.action_id for mark in marks)
    top_actions = sorted(
        active_actions,
        key=lambda a: mark_counts.get(a.id, 0),
        reverse=True
    )[:10]

    return jsonify([
        {
            'id': a.id,
            'text': a.text,
            'marks': mark_counts.get(a.id, 0)
        } for a in top_actions
    ])
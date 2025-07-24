from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, abort
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import or_, and_
from app.extensions import db, socketio
from app.models import User, FriendRequest, Action, ActionMark, Subscriber, PotentialFriendView, Subscriber
from flask_socketio import join_room

friends_bp = Blueprint("friends_bp", __name__)

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


@friends_bp.route("/friends", methods=["GET", "POST"])
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
        return redirect(url_for('friends_bp.friends'))

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
        cleanup_time=cleanup_time
    )

@friends_bp.route('/friends_partial')
@login_required
def friends_partial():
    cleanup_time = session.get('cleanup_time', 10)
    cutoff = datetime.utcnow() - timedelta(minutes=cleanup_time)

    # 🔎 Потенциальные друзья (не фильтруем здесь — сделаем позже)
    potential_views = db.session.query(PotentialFriendView).filter(
        PotentialFriendView.viewer_id == current_user.id,
        PotentialFriendView.timestamp >= cutoff
    ).all()

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

    # 👥 Отфильтровываем подходящих пользователей из potential_views
    users = []
    for view in potential_views:
        u = view.user
        if (
            u.id != current_user.id and
            u.id not in friend_ids and
            u.id not in [row[0] for row in db.session.query(incoming).all()] and
            u.id not in [row[0] for row in db.session.query(outgoing).all()] and
            u.id not in [row[0] for row in db.session.query(subscribers).all()]
        ):
            u.timestamp_ms = int(view.timestamp.timestamp() * 1000)
            users.append(u)
            
    return render_template(
        'partials/possible_friends.html',
        users=users,
        cleanup_time=cleanup_time
    )


@friends_bp.route('/send_friend_request/<int:user_id>', methods=['POST'])
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

    return redirect(url_for('friends_bp.friends'))


@friends_bp.route("/cancel_friend_request/<int:request_id>", methods=["POST"])
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

    return redirect(url_for("friends_bp.friends"))

# При обработке приёма заявки


@friends_bp.route('/accept_friend_request/<int:request_id>', methods=['POST'])
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

    return redirect(url_for('friends_bp.friends'))


@friends_bp.route('/remove_friend/<int:user_id>', methods=['POST'])
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

    return redirect(url_for('friends_bp.friends'))


@friends_bp.route("/remove_possible_friend/<int:user_id>", methods=["POST"])
@login_required
def remove_possible_friend(user_id):
    user_to_ignore = User.query.get_or_404(user_id)
    if user_to_ignore not in current_user.ignored_users:
        current_user.ignored_users.append(user_to_ignore)
        db.session.commit()
    return redirect(url_for("friends_bp.friends"))


@friends_bp.route('/subscribe/<int:user_id>', methods=['POST'])
@login_required
def subscribe(user_id):
    if user_id == current_user.id:
        abort(400)

    existing = Subscriber.query.filter_by(subscriber_id=current_user.id, owner_id=user_id).first()
    if existing:
        flash("Вы уже подписаны.")
        return redirect(url_for('friends_bp.friends'))

    new_sub = Subscriber(subscriber_id=current_user.id, owner_id=user_id)
    db.session.add(new_sub)
    db.session.commit()

    data = {
        'subscriber_id': current_user.id,
        'subscriber_username': current_user.username,
        'subscriber_avatar': current_user.avatar_url,
    }

    socketio.emit('new_subscriber', data, to=f"user_{user_id}")

    return redirect(url_for('friends_bp.friends'))


@friends_bp.route("/cleanup_potential_friends", methods=["POST"])
@login_required
def cleanup_potential_friends():
    minutes = int(request.form.get("cleanup_time", 10))
    threshold = datetime.utcnow() - timedelta(minutes=minutes)

    PotentialFriendView.query.filter(
        PotentialFriendView.viewer_id == current_user.id,
        PotentialFriendView.timestamp < threshold
    ).delete()
    db.session.commit()
    return '', 204  # Успешно, без контента


@friends_bp.route('/leave_in_subscribers/<int:user_id>', methods=['POST'])
@login_required
def leave_in_subscribers(user_id):
    if user_id == current_user.id:
        return redirect(url_for('friends_bp.friends'))

    existing = Subscriber.query.filter_by(subscriber_id=user_id, owner_id=current_user.id).first()
    if not existing:
        sub = Subscriber(subscriber_id=user_id, owner_id=current_user.id)
        db.session.add(sub)
        db.session.commit()
    return redirect(url_for('friends_bp.friends'))


@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room(f"user_{current_user.id}")
        
@socketio.on('join')
def on_join(data):
    room = data.get('room')
    if room:
        join_room(room)
        print(f"🔌 Пользователь присоединился к комнате: {room}")
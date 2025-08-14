from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, abort
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import or_, and_
from app.extensions import db, socketio
from app.models import User, FriendRequest, Action, ActionMark, Subscriber, PotentialFriendView, Subscriber
from flask_socketio import join_room

friends_bp = Blueprint("friends_bp", __name__)

def are_friends(a: int, b: int) -> bool:
    return FriendRequest.query.filter(
        FriendRequest.status == 'accepted',
        or_(
            and_(FriendRequest.sender_id == a, FriendRequest.receiver_id == b),
            and_(FriendRequest.sender_id == b, FriendRequest.receiver_id == a),
        )
    ).first() is not None

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

def _collect_friends_page_data(user_id):
    incoming = (FriendRequest.query
                .filter_by(receiver_id=user_id, status='pending')
                .order_by(FriendRequest.id.desc())
                .all())

    outgoing = (FriendRequest.query
                .filter_by(sender_id=user_id, status='pending')
                .order_by(FriendRequest.id.desc())
                .all())

    # Друзья = accepted заявки в обе стороны
    accepted = (FriendRequest.query
                .filter(FriendRequest.status == 'accepted',
                        or_(and_(FriendRequest.sender_id == user_id),
                            and_(FriendRequest.receiver_id == user_id)))
                .all())
    friend_ids = []
    for fr in accepted:
        other = fr.receiver_id if fr.sender_id == user_id else fr.sender_id
        friend_ids.append(other)
    friends = User.query.filter(User.id.in_(friend_ids)).all() if friend_ids else []

    subscribers = (User.query
                   .join(Subscriber, Subscriber.subscriber_id == User.id)
                   .filter(Subscriber.owner_id == user_id)
                   .all())

    subscriptions = (User.query
                     .join(Subscriber, Subscriber.owner_id == User.id)
                     .filter(Subscriber.subscriber_id == user_id)
                     .all())

    return incoming, outgoing, friends, subscribers, subscriptions


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
    user_id = current_user.id
    cleanup_time = session.get('cleanup_time', 10)
    cutoff = datetime.utcnow() - timedelta(minutes=cleanup_time)

    # --- accepted (друзья) ---
    accepted_pairs = (
        db.session.query(FriendRequest.sender_id, FriendRequest.receiver_id)
        .filter(
            FriendRequest.status == 'accepted',
            or_(FriendRequest.sender_id == user_id,
                FriendRequest.receiver_id == user_id)
        ).all()
    )
    friend_ids = {
        (sid if rid == user_id else rid)
        for sid, rid in accepted_pairs
    }

    # --- pending входящие/исходящие ---
    incoming_senders = {
        sid for (sid,) in db.session.query(FriendRequest.sender_id)
        .filter(FriendRequest.receiver_id == user_id,
                FriendRequest.status == 'pending')
        .all()
    }
    outgoing_receivers = {
        rid for (rid,) in db.session.query(FriendRequest.receiver_id)
        .filter(FriendRequest.sender_id == user_id,
                FriendRequest.status == 'pending')
        .all()
    }

    # --- твои подписчики (те, кто на тебя подписан) ---
    subscriber_ids = {
        sid for (sid,) in db.session.query(Subscriber.subscriber_id)
        .filter(Subscriber.owner_id == user_id)
        .all()
    }

    # --- кандидаты из PotentialFriendView (join сразу на User) ---
    candidates = (
        db.session.query(User, PotentialFriendView.timestamp)
        .join(PotentialFriendView, PotentialFriendView.user_id == User.id)
        .filter(
            PotentialFriendView.viewer_id == user_id,
            PotentialFriendView.timestamp >= cutoff
        )
        .all()
    )

    users = []
    for u, ts in candidates:
        if u.id == user_id:              # не ты сам
            continue
        if u.id in friend_ids:           # уже друзья
            continue
        if u.id in incoming_senders:     # у тебя входящая от него
            continue
        if u.id in outgoing_receivers:   # у тебя исходящая к нему
            continue
        if u.id in subscriber_ids:       # он уже подписчик
            continue

        # для фронта: метка появления
        u.timestamp_ms = int(ts.timestamp() * 1000)
        users.append(u)

    return render_template(
        'partials/possible_friends.html',
        users=users,
        cleanup_time=cleanup_time
    )


@friends_bp.route('/send_friend_request/<int:user_id>', methods=['POST'])
@login_required
def send_friend_request(user_id):
    sender_id = current_user.id
    receiver_id = user_id
    if sender_id == receiver_id:
        return jsonify(ok=False, message='Нельзя добавить в друзья самого себя'), 400

    # Уже друзья? (есть accepted в любом направлении)
    accepted = FriendRequest.query.filter(
        FriendRequest.status == 'accepted',
        or_(
            and_(FriendRequest.sender_id == sender_id, FriendRequest.receiver_id == receiver_id),
            and_(FriendRequest.sender_id == receiver_id, FriendRequest.receiver_id == sender_id),
        )
    ).first()
    if accepted:
        return jsonify(ok=True, message='Вы уже друзья')

    # Уже есть PENDING в любом направлении?
    pending = FriendRequest.query.filter(
        FriendRequest.status == 'pending',
        or_(
            and_(FriendRequest.sender_id == sender_id, FriendRequest.receiver_id == receiver_id),
            and_(FriendRequest.sender_id == receiver_id, FriendRequest.receiver_id == sender_id),
        )
    ).first()
    if pending:
        return jsonify(ok=True, message='Заявка уже существует', data={'request_id': pending.id})

    # Создаём PENDING
    fr = FriendRequest(sender_id=sender_id, receiver_id=receiver_id, status='pending')
    db.session.add(fr)

    # Уберём «возможного друга» из списка отправителя — он уже в процессе
    PotentialFriendView.query.filter_by(viewer_id=sender_id, user_id=receiver_id).delete(synchronize_session=False)

    db.session.commit()

    # Уведомление получателю
    socketio.emit('friend_request_sent', {
        'request_id': fr.id,
        'sender_id': sender_id,
        'sender_username': current_user.username,
        'sender_avatar': current_user.avatar_url,
    }, to=f'user_{receiver_id}')

    return jsonify(ok=True, message='Заявка отправлена', data={'request_id': fr.id})


@friends_bp.route('/cancel_friend_request/<int:request_id>', methods=['POST'])
@login_required
def cancel_friend_request(request_id):
    fr = FriendRequest.query.get_or_404(request_id)
    me = current_user.id
    if me not in (fr.sender_id, fr.receiver_id):
        return abort(403)

    # сохраняем id заранее (после delete fr станет detached)
    sender_id, receiver_id = fr.sender_id, fr.receiver_id

    # если получатель отклоняет и просит «оставить в подписчиках»
    subscribe_flag = request.form.get('subscribe') in ('1', 'true', 'True', 'on')
    if subscribe_flag and me == receiver_id:
        # подписчик = отправитель, владелец = получатель
        exists = Subscriber.query.filter_by(
            subscriber_id=sender_id, owner_id=receiver_id
        ).first()
        if not exists:
            db.session.add(Subscriber(
                subscriber_id=sender_id,
                owner_id=receiver_id
            ))
            db.session.commit()

        # один раз получаем данные пользователей для событий
        sender   = User.query.get(sender_id)
        receiver = User.query.get(receiver_id)

        # владельцу: у него новый подписчик
        socketio.emit('new_subscriber', {
            'subscriber_id': sender_id,
            'subscriber_username': sender.username,
            'subscriber_avatar': sender.avatar_url,
        }, to=f'user_{receiver_id}')

        # подписчику: он теперь подписан на receiver
        socketio.emit('subscribed_to', {
            'user_id': receiver_id,
            'username': receiver.username,
            'avatar': receiver.avatar_url,
        }, to=f'user_{sender_id}')

    # удаляем заявку
    db.session.delete(fr)
    db.session.commit()

    # обеим сторонам — чтобы исчезли входящая/исходящая без F5
    socketio.emit('friend_request_cancelled', {'request_id': request_id}, to=f'user_{sender_id}')
    socketio.emit('friend_request_cancelled', {'request_id': request_id}, to=f'user_{receiver_id}')

    return jsonify(ok=True, message='Заявка отменена')



@friends_bp.route('/accept_friend_request/<int:request_id>', methods=['POST'])
@login_required
def accept_friend_request(request_id):
    fr = FriendRequest.query.get_or_404(request_id)
    if fr.receiver_id != current_user.id:
        return abort(403)
    if fr.status != 'pending':
        return jsonify(ok=True, message='Уже обработано')

    fr.status = 'accepted'
    db.session.commit()

    # Удаляем подписки в обе стороны — дружба «перекрывает» подписку
    Subscriber.query.filter(
        or_(
            and_(Subscriber.owner_id == fr.sender_id,  Subscriber.subscriber_id == fr.receiver_id),
            and_(Subscriber.owner_id == fr.receiver_id, Subscriber.subscriber_id == fr.sender_id),
        )
    ).delete(synchronize_session=False)
    db.session.commit()

    # Уведомим обе стороны: обновятся «Друзья/Исходящие»
    socketio.emit('friend_accepted', {'request_id': fr.id}, to=f'user_{fr.sender_id}')
    socketio.emit('friend_accepted', {'request_id': fr.id}, to=f'user_{fr.receiver_id}')

    # ✨ Дополнительно: освежим подписочные секции у обеих сторон
    socketio.emit('subscribers_refresh', {}, to=f'user_{fr.sender_id}')
    socketio.emit('subscribers_refresh', {}, to=f'user_{fr.receiver_id}')

    # Уберём «возможных друзей» в обе стороны (чтобы карточка исчезла)
    PotentialFriendView.query.filter(
        or_(
            and_(PotentialFriendView.viewer_id == fr.sender_id,  PotentialFriendView.user_id == fr.receiver_id),
            and_(PotentialFriendView.viewer_id == fr.receiver_id, PotentialFriendView.user_id == fr.sender_id),
        )
    ).delete(synchronize_session=False)
    db.session.commit()

    return jsonify(ok=True, message='Заявка принята')


@friends_bp.route('/remove_friend/<int:user_id>', methods=['POST'])
@login_required
def remove_friend(user_id):
    me = current_user.id
    fr = FriendRequest.query.filter(
        FriendRequest.status == 'accepted',
        or_(
            and_(FriendRequest.sender_id == me, FriendRequest.receiver_id == user_id),
            and_(FriendRequest.sender_id == user_id, FriendRequest.receiver_id == me),
        )
    ).first()
    if fr:
        db.session.delete(fr)
        db.session.commit()
        socketio.emit('friend_removed', {'user_id': me}, to=f'user_{user_id}')

    return jsonify(ok=True, message='Удалено из друзей')



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
    follower = current_user.id
    if follower == user_id:
        return jsonify(ok=False, message='Нельзя подписаться на себя'), 400

    exists = Subscriber.query.filter_by(subscriber_id=follower, owner_id=user_id).first()
    if exists:
        return jsonify(ok=True, message='Уже подписаны')

    if are_friends(follower, user_id):
        return jsonify(ok=False, message='Вы уже друзья — подписка не нужна'), 400

    db.session.add(Subscriber(subscriber_id=follower, owner_id=user_id))
    db.session.commit()

    socketio.emit('new_subscriber', {
        'subscriber_id': follower,
        'subscriber_username': current_user.username,
        'subscriber_avatar': current_user.avatar_url,
    }, to=f'user_{user_id}')

    socketio.emit('subscribed_to', {
        'user_id': user_id,
        'username': User.query.get(user_id).username,
        'avatar': User.query.get(user_id).avatar_url,
    }, to=f'user_{current_user.id}')

    return jsonify(ok=True, message='Подписка оформлена')



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

@friends_bp.route('/friends_partial/incoming')
@login_required
def friends_partial_incoming():
    incoming, *_ = _collect_friends_page_data(current_user.id)
    return render_template('partials/incoming_requests.html', incoming_requests=incoming)

@friends_bp.route('/friends_partial/outgoing')
@login_required
def friends_partial_outgoing():
    _, outgoing, *_ = _collect_friends_page_data(current_user.id)
    return render_template('partials/outgoing_requests.html', outgoing_requests=outgoing)

@friends_bp.route('/friends_partial/friends')
@login_required
def friends_partial_friends():
    *_, friends, __, ___ = _collect_friends_page_data(current_user.id)
    return render_template('partials/friends_list.html', friends=friends)

@friends_bp.route('/friends_partial/subscribers')
@login_required
def friends_partial_subscribers():
    *___, subscribers, ____ = _collect_friends_page_data(current_user.id)
    return render_template('partials/subscribers.html', subscribers=subscribers)

@friends_bp.route('/friends_partial/subscriptions')
@login_required
def friends_partial_subscriptions():
    *____, subscriptions = _collect_friends_page_data(current_user.id)
    return render_template('partials/subscriptions.html', subscriptions=subscriptions)


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
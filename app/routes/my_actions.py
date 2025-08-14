from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app.models import Action, ActionMark  # <-- добавили ActionMark
from app.extensions import db

my_actions_bp = Blueprint('my_actions_bp', __name__)

# ---------- Helpers ----------
def _action_to_dict(a: Action):
    return {
        "id": a.id,
        "text": a.text,
        "is_published": bool(a.is_published),
        "is_daily": bool(getattr(a, 'is_daily', False)),
        "created_at": a.created_at.isoformat() if getattr(a, 'created_at', None) else None,
        "expires_at": a.expires_at.isoformat() if getattr(a, 'expires_at', None) else None,
    }

# ---------- Routes ----------
@my_actions_bp.route('/my_actions', methods=['GET', 'POST'])
@login_required
def my_actions():
    user = current_user

    if request.method == 'POST':
        # Создать черновик
        if 'new_action' in request.form:
            text = (request.form.get('new_action') or '').strip()
            if not text:
                return jsonify({"ok": False, "message": "Введите текст действия"}), 400

            action = Action(user_id=user.id, text=text, is_published=False)
            db.session.add(action)
            db.session.commit()
            return jsonify({"ok": True, "message": "Действие создано", "data": {"action": _action_to_dict(action)}})

        # Удалить действие (и все его отметки)
        if 'delete_id' in request.form:
            try:
                action_id = int(request.form.get('delete_id'))
            except (TypeError, ValueError):
                return jsonify({"ok": False, "message": "Некорректный ID"}), 400

            action = Action.query.get_or_404(action_id)
            if action.user_id != user.id:
                return jsonify({"ok": False, "message": "Нет прав"}), 403

            # Удаляем связанные отметки, чтобы не упасть на NOT NULL
            ActionMark.query.filter_by(action_id=action_id).delete(synchronize_session=False)
            db.session.delete(action)
            db.session.commit()
            return jsonify({"ok": True, "message": "Действие удалено", "data": {"id": action_id}})

        # Опубликовать действие (publish_id + duration)
        if 'publish_id' in request.form:
            try:
                action_id = int(request.form.get('publish_id'))
            except (TypeError, ValueError):
                return jsonify({"ok": False, "message": "Некорректный ID"}), 400

            duration = (request.form.get('duration') or '').strip()
            if duration not in {'10', '30', '60'}:
                return jsonify({"ok": False, "message": "Неверная длительность"}), 400

            action = Action.query.get_or_404(action_id)
            if action.user_id != user.id:
                return jsonify({"ok": False, "message": "Нет прав"}), 403

            minutes = int(duration)
            action.is_published = True
            action.expires_at = datetime.utcnow() + timedelta(minutes=minutes)
            db.session.commit()

            return jsonify({"ok": True, "message": "Опубликовано", "data": {"action": _action_to_dict(action)}})

        return jsonify({"ok": False, "message": "Неподдерживаемое действие"}), 400

    # GET: отрисовываем страницу (передаём now для шаблона)
    drafts = (Action.query
              .filter_by(user_id=user.id, is_published=False)
              .order_by(Action.created_at.desc())
              .all())
    published = (Action.query
                 .filter_by(user_id=user.id, is_published=True)
                 .order_by(Action.created_at.desc())
                 .all())

    return render_template('my_actions.html', drafts=drafts, published=published, now=datetime.utcnow())


@my_actions_bp.route("/delete_my_action/<int:action_id>", methods=["POST"])
@login_required
def delete_my_action(action_id):
    action = Action.query.get_or_404(action_id)
    if action.user_id != current_user.id:
        return jsonify({'ok': False, 'message': 'Нет прав'}), 403

    # Удаляем связанные отметки до удаления действия
    ActionMark.query.filter_by(action_id=action_id).delete(synchronize_session=False)
    db.session.delete(action)
    db.session.commit()
    return jsonify({"ok": True, "message": "Действие удалено", "data": {"id": action_id}})


@my_actions_bp.route("/publish_action/<int:action_id>", methods=["POST"])
@login_required
def publish_action(action_id):
    action = Action.query.get_or_404(action_id)
    if action.user_id != current_user.id:
        return jsonify({'ok': False, 'message': 'Нет прав'}), 403

    duration = (request.form.get('duration') or '').strip()
    if duration not in {'10', '30', '60'}:
        return jsonify({"ok": False, "message": "Неверная длительность"}), 400

    minutes = int(duration)
    action.is_published = True
    action.expires_at = datetime.utcnow() + timedelta(minutes=minutes)
    db.session.commit()

    return jsonify({"ok": True, "message": "Опубликовано", "data": {"action": _action_to_dict(action)}})

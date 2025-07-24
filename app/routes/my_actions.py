from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app.models import db, Action, ActionMark
from app.extensions import db

my_actions_bp = Blueprint('my_actions_bp', __name__)

@my_actions_bp.route('/my_actions', methods=['GET', 'POST'])
@login_required
def my_actions():
    user = current_user

    if request.method == 'POST':
        if 'new_action' in request.form:
            text = request.form.get('new_action')
            if text:
                action = Action(user_id=user.id, text=text, is_published=False)
                db.session.add(action)
                db.session.commit()
                flash('Новое действие добавлено!')

        elif 'delete_id' in request.form:
            action = Action.query.get(int(request.form.get('delete_id')))
            if action and action.user_id == user.id:
                ActionMark.query.filter_by(action_id=action.id).delete()
                db.session.delete(action)
                db.session.commit()
                flash('Действие и все отметки удалены!')

        elif 'publish_id' in request.form:
            action = Action.query.get(int(request.form.get('publish_id')))
            if action and action.user_id == user.id:
                action.is_published = True
                duration = int(request.form.get('duration', 10))
                action.expires_at = datetime.utcnow() + timedelta(minutes=duration)
                db.session.commit()
                flash('Действие опубликовано! Перейдите в "Наш мир" для просмотра.', 'info')

        return redirect(url_for('my_actions_bp.my_actions'))

    drafts = Action.query.filter_by(user_id=user.id, is_published=False).order_by(Action.created_at.desc()).all()
    published = Action.query.filter_by(user_id=user.id, is_published=True).order_by(Action.created_at.desc()).all()

    return render_template('my_actions.html', drafts=drafts, published=published, now=datetime.utcnow())
    

@my_actions_bp.route('/publish_action/<int:action_id>', methods=['POST'])
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


@my_actions_bp.route("/delete_my_action/<int:action_id>", methods=["POST"])
@login_required
def delete_my_action(action_id):
    action = Action.query.get_or_404(action_id)
    if action.user_id != current_user.id:
        return jsonify({'error': 'Not authorized'}), 403

    db.session.delete(action)
    db.session.commit()

    flash("Действие удалено.")
    return redirect(url_for("my_actions_bp.my_actions"))

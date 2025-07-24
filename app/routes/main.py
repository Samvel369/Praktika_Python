from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from collections import Counter
from app.models import Action, ActionMark

main_bp = Blueprint('main_bp', __name__)

@main_bp.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('main_bp.main'))
    return render_template('index.html')

@main_bp.route('/main')
@login_required
def main():
    now = datetime.utcnow()
    active_actions = Action.query.filter(Action.is_published == True, Action.expires_at > now).all()

    one_minute_ago = now - timedelta(minutes=1)
    marks = ActionMark.query.filter(ActionMark.timestamp >= one_minute_ago).all()

    mark_counts = Counter()
    for mark in marks:
        mark_counts[mark.action_id] += 1

    top_actions = sorted(
        active_actions,
        key=lambda a: mark_counts.get(a.id, 0),
        reverse=True
    )[:10]

    return render_template('main.html', top_actions=top_actions)
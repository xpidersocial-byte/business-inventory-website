from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from core.utils import log_action
from core.middleware import login_required
from core.db import get_notes_collection
from bson.objectid import ObjectId
from datetime import datetime, timedelta

bulletin_bp = Blueprint('bulletin', __name__)

@bulletin_bp.route('/bulletin')
@login_required
def bulletin():
    notes_collection = get_notes_collection()
    # Auto-deletion of 'done' notes older than 1 week
    one_week_ago = datetime.now() - timedelta(days=7)

    notes_collection.delete_many({
        "status": "done",
        "done_at": {"$lt": one_week_ago}
    })

    # Sort by status (pending first), then pinned (descending), then by timestamp
    all_notes = list(notes_collection.find().sort([
        ("status", -1), 
        ("pinned", -1), 
        ("timestamp", -1)
    ]))
    return render_template('notes.html', notes=all_notes, role=session.get('role'))

@bulletin_bp.route('/bulletin/add', methods=['POST'])
@login_required
def add_bulletin():
    notes_collection = get_notes_collection()
    content = request.form.get('content')
    color = request.form.get('color', 'blue')
    tag = request.form.get('tag', 'Normal') # Urgent, Normal, Pending
    if content:
        notes_collection.insert_one({
            "content": content,
            "color": color,
            "tag": tag,
            "author": session.get('email'),
            "timestamp": datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'),
            "pinned": False,
            "status": "pending",
            "done_at": None,
            "done_by": None
        })
        log_action("ADD_BULLETIN", f"Created a {tag} bulletin.")
    return redirect(url_for('bulletin.bulletin'))

@bulletin_bp.route('/bulletin/edit/<id>', methods=['POST'])
@login_required
def edit_bulletin(id):
    notes_collection = get_notes_collection()
    note = notes_collection.find_one({"_id": ObjectId(id)})
    if not note or note.get('author') != session.get('email'):
        flash("Unauthorized: Only the author can edit this post.", "danger")
        return redirect(url_for('bulletin.bulletin'))

    content = request.form.get('content')
    tag = request.form.get('tag')
    color = request.form.get('color')

    update_data = {}
    if content: update_data['content'] = content
    if tag: update_data['tag'] = tag
    if color: update_data['color'] = color

    if update_data:
        notes_collection.update_one({"_id": ObjectId(id)}, {"$set": update_data})
        log_action("EDIT_BULLETIN", "Updated a bulletin post.")
        flash("Bulletin updated!", "success")

    return redirect(url_for('bulletin.bulletin'))

@bulletin_bp.route('/bulletin/toggle_status/<id>', methods=['POST'])
@login_required
def toggle_bulletin_status(id):
    notes_collection = get_notes_collection()
    note = notes_collection.find_one({"_id": ObjectId(id)})
    if note:
        current_status = note.get('status', 'pending')
        new_status = 'done' if current_status == 'pending' else 'pending'
        done_at = datetime.now() if new_status == 'done' else None
        done_by = session.get('email') if new_status == 'done' else None

        notes_collection.update_one(
            {"_id": ObjectId(id)}, 
            {"$set": {"status": new_status, "done_at": done_at, "done_by": done_by}}
        )
        log_action("UPDATE_BULLETIN_STATUS", f"Bulletin marked as {new_status} by {session.get('email')}.")
    return redirect(url_for('bulletin.bulletin'))

@bulletin_bp.route('/bulletin/update_color/<id>', methods=['POST'])
@login_required
def update_bulletin_color(id):
    notes_collection = get_notes_collection()
    note = notes_collection.find_one({"_id": ObjectId(id)})
    if not note or note.get('author') != session.get('email'):
        return redirect(url_for('bulletin.bulletin'))

    color = request.form.get('color')
    if color:
        notes_collection.update_one(
            {"_id": ObjectId(id)}, 
            {"$set": {"color": color}}
        )
    return redirect(url_for('bulletin.bulletin'))

@bulletin_bp.route('/bulletin/pin/<id>', methods=['POST'])
@login_required
def pin_bulletin(id):
    notes_collection = get_notes_collection()
    note = notes_collection.find_one({"_id": ObjectId(id)})
    if note:
        new_status = not note.get('pinned', False)
        notes_collection.update_one({"_id": ObjectId(id)}, {"$set": {"pinned": new_status}})
    return redirect(url_for('bulletin.bulletin'))

@bulletin_bp.route('/bulletin/delete/<id>', methods=['POST'])
@login_required
def delete_bulletin(id):
    notes_collection = get_notes_collection()
    note = notes_collection.find_one({"_id": ObjectId(id)})
    if note and note.get('author') == session.get('email'):
        notes_collection.delete_one({"_id": ObjectId(id)})
        log_action("DELETE_BULLETIN", "Author removed a bulletin.")
        flash("Bulletin removed.", "info")
    else:
        flash("Unauthorized deletion attempt.", "danger")
    return redirect(url_for('bulletin.bulletin'))

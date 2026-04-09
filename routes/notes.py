from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from core.utils import log_action, send_email_notification
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

    user_email = session.get('email', '')
    all_notes = list(notes_collection.find().sort([
        ("status", -1), 
        ("pinned", -1), 
        ("timestamp", -1)
    ]))
    
    # Identify unread notes for the current user
    for note in all_notes:
        note['unread'] = user_email not in note.get('read_by', [])

    # Mark as read for this user
    from core.db import get_users_collection
    try:
        get_users_collection().update_one(
            {"email": user_email},
            {"$set": {"last_views.bulletins": datetime.now()}}
        )
    except: pass
        
    return render_template('notes.html', notes=all_notes, role=session.get('role'))

@bulletin_bp.route('/bulletin/add', methods=['POST'])
@login_required
def add_bulletin():
    notes_collection = get_notes_collection()
    data = request.get_json() if request.is_json else request.form
    content = data.get('content')
    color = data.get('color', 'blue')
    tag = data.get('tag', 'Normal') # Urgent, Normal, Pending
    if content:
        notes_collection.insert_one({
            "title": content[:30] + ('...' if len(content) > 30 else ''),
            "content": content,
            "color": color,
            "tag": tag,
            "author": session.get('email'),
            "created_at": datetime.now(),
            "timestamp": datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'),
            "pinned": False,
            "status": "pending",
            "done_at": None,
            "done_by": None
        })
        log_action("ADD_BULLETIN", f"Created a {tag} bulletin.")
        send_email_notification(
            "New Bulletin Posted",
            f"A new bulletin was posted.\n\nTag: {tag}\nAuthor: {session.get('email')}\nContent: {content[:200]}{'...' if len(content) > 200 else ''}\nTime: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}",
            notif_type="bulletin"
        )
    if request.is_json or 'application/json' in request.headers.get('Accept', ''):
        return jsonify({"success": True})
    return redirect(url_for('bulletin.bulletin'))

@bulletin_bp.route('/bulletin/edit/<id>', methods=['POST'])
@login_required
def edit_bulletin(id):
    notes_collection = get_notes_collection()
    note = notes_collection.find_one({"_id": ObjectId(id)})
    if not note or note.get('author') != session.get('email'):
        flash("Unauthorized: Only the author can edit this post.", "danger")
        return redirect(url_for('bulletin.bulletin'))

    data = request.get_json() if request.is_json else request.form
    content = data.get('content')
    tag = data.get('tag')
    color = data.get('color')

    update_data = {}
    if content: update_data['content'] = content
    if tag: update_data['tag'] = tag
    if color: update_data['color'] = color

    if update_data:
        notes_collection.update_one({"_id": ObjectId(id)}, {"$set": update_data})
        log_action("EDIT_BULLETIN", "Updated a bulletin post.")
        flash("Bulletin updated!", "success")

    if request.is_json or 'application/json' in request.headers.get('Accept', ''):
        return jsonify({"success": True})
    return redirect(url_for('bulletin.bulletin'))

@bulletin_bp.route('/bulletin/toggle_status/<id>', methods=['POST'])
@login_required
def toggle_bulletin_status(id):
    notes_collection = get_notes_collection()
    try:
        oid = ObjectId(id)
    except:
        return jsonify({"success": False, "error": "Invalid ID format"}), 400

    note = notes_collection.find_one({"_id": oid})
    if note:
        current_status = note.get('status', 'pending')
        new_status = 'done' if current_status == 'pending' else 'pending'
        done_at = datetime.now() if new_status == 'done' else None
        done_by = session.get('email') if new_status == 'done' else None

        notes_collection.update_one(
            {"_id": oid}, 
            {"$set": {"status": new_status, "done_at": done_at, "done_by": done_by}}
        )
        log_action("UPDATE_BULLETIN_STATUS", f"Bulletin marked as {new_status} by {session.get('email')}.")
        if new_status == 'done':
            send_email_notification(
                "Bulletin Marked as Done",
                f"A bulletin was marked as completed.\n\nContent: {note.get('content', '')[:200]}\nCompleted by: {session.get('email')}\nTime: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}",
                notif_type="bulletin"
            )
    if request.is_json or 'application/json' in request.headers.get('Accept', ''):
        return jsonify({"success": True})
    return redirect(url_for('bulletin.bulletin'))

@bulletin_bp.route('/bulletin/update_color/<id>', methods=['POST'])
@login_required
def update_bulletin_color(id):
    notes_collection = get_notes_collection()
    note = notes_collection.find_one({"_id": ObjectId(id)})
    if not note or note.get('author') != session.get('email'):
        return redirect(url_for('bulletin.bulletin'))

    data = request.get_json() if request.is_json else request.form
    color = data.get('color')
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
    try:
        oid = ObjectId(id)
    except:
        return jsonify({"success": False, "error": "Invalid ID format"}), 400

    note = notes_collection.find_one({"_id": oid})
    if note:
        new_status = not note.get('pinned', False)
        notes_collection.update_one({"_id": oid}, {"$set": {"pinned": new_status}})
    if request.is_json or 'application/json' in request.headers.get('Accept', ''):
        return jsonify({"success": True})
    return redirect(url_for('bulletin.bulletin'))

@bulletin_bp.route('/bulletin/delete/<id>', methods=['POST'])
@login_required
def delete_bulletin(id):
    notes_collection = get_notes_collection()
    try:
        oid = ObjectId(id)
    except:
        return jsonify({"success": False, "error": "Invalid ID format"}), 400

    note = notes_collection.find_one({"_id": oid})
    if note and note.get('author') == session.get('email'):
        notes_collection.delete_one({"_id": oid})
        log_action("DELETE_BULLETIN", "Author removed a bulletin.")
        flash("Bulletin removed.", "info")
    else:
        flash("Unauthorized deletion attempt or post not found.", "danger")
    if request.is_json or 'application/json' in request.headers.get('Accept', ''):
        return jsonify({"success": True})
    return redirect(url_for('bulletin.bulletin'))

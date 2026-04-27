from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from core.utils import log_action, send_email_notification, trigger_notification, get_site_config
from core.middleware import login_required, role_required
from core.db import get_notes_collection, get_notifications_collection, get_users_collection
from extensions import socketio
from bson.objectid import ObjectId
from datetime import datetime, timedelta, timezone

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
    role = session.get('role', 'cashier')
    branch_id = session.get('branch_id')
    
    query = {}
    if branch_id:
        query["branch_id"] = {"$in": [branch_id, ObjectId(branch_id)]}

    all_notes = list(notes_collection.find(query).sort([
        ("status", -1), 
        ("pinned", -1), 
        ("timestamp", -1)
    ]))
    
    # Identify unread notes for the current user
    for note in all_notes:
        note['unread'] = user_email not in note.get('read_by', [])

    # Mark as read for this user (branch-specific)
    try:
        # Mark all notes in this branch as read by this user
        note_q = {"read_by": {"$ne": user_email}}
        if branch_id:
            note_q["branch_id"] = {"$in": [branch_id, ObjectId(branch_id)]}
        get_notes_collection().update_many(note_q, {"$addToSet": {"read_by": user_email}})
        
        # Update last view timestamp
        get_users_collection().update_one(
            {"email": user_email},
            {"$set": {"last_views.bulletins": datetime.now(timezone.utc)}}
        )
        # Clear persistent bulletin notifications for this user in this branch
        bn_q = {"type": "bulletin", "read_by": {"$ne": user_email}}
        if branch_id:
            bn_q["branch_id"] = {"$in": [branch_id, ObjectId(branch_id)]}
        get_notifications_collection().update_many(bn_q, {"$addToSet": {"read_by": user_email}})
        socketio.emit('dashboard_update')
    except: pass
        
    return render_template('notes.html', notes=all_notes, role=session.get('role'), site_config=get_site_config())

@bulletin_bp.route('/bulletin/add', methods=['POST'])
@login_required
def add_bulletin():
    notes_collection = get_notes_collection()
    data = request.get_json() if request.is_json else request.form
    content = data.get('content')
    color = data.get('color', 'blue')
    tag = data.get('tag', 'ANNOUNCEMENT')
    
    if content:
        res = notes_collection.insert_one({
            "content": content,
            "color": color,
            "tag": tag,
            "author": session.get('email'),
            "branch_id": session.get('branch_id'),
            "created_at": datetime.now(timezone.utc),
            "timestamp": datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'),
            "pinned": False,
            "status": "pending",
            "read_by": [session.get('email')]
        })
        log_action("ADD_BULLETIN", f"Posted bulletin: {content[:50]}...")
        trigger_notification("bulletin", "New Bulletin Posted", f"{session.get('email')} posted a new bulletin in the board.", {"content": content[:100]})
        send_email_notification(
            "New Bulletin Posted",
            f"A new bulletin was posted.\n\nTag: {tag}\nAuthor: {session.get('email')}\nContent: {content[:200]}{'...' if len(content) > 200 else ''}\nTime: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}",
            notif_type="bulletin"
        )
        socketio.emit('dashboard_update')
        
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({"success": True, "message": "Bulletin posted."})
    return redirect(url_for('bulletin.bulletin'))

@bulletin_bp.route('/bulletin/delete/<id>', methods=['GET', 'POST'])
@login_required
def delete_bulletin(id):
    notes_collection = get_notes_collection()
    notes_collection.delete_one({"_id": ObjectId(id)})
    log_action("DELETE_BULLETIN", f"Deleted bulletin ID: {id}")
    socketio.emit('dashboard_update')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({"success": True, "message": "Bulletin deleted."})
    return redirect(url_for('bulletin.bulletin'))

@bulletin_bp.route('/bulletin/toggle/<id>', methods=['GET', 'POST'])
@login_required
def toggle_bulletin(id):
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
        log_action("TOGGLE_BULLETIN", f"Marked bulletin as {new_status}: {id}")
        
        if new_status == 'done':
            send_email_notification(
                "Bulletin Marked as Done",
                f"A bulletin was marked as completed.\n\nContent: {note.get('content', '')[:200]}\nCompleted by: {session.get('email')}\nTime: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}",
                notif_type="bulletin"
            )
        socketio.emit('dashboard_update')
            
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({"success": True, "message": "Bulletin status updated."})
    return redirect(url_for('bulletin.bulletin'))

@bulletin_bp.route('/bulletin/pin/<id>', methods=['GET', 'POST'])
@login_required
def pin_bulletin(id):
    notes_collection = get_notes_collection()
    note = notes_collection.find_one({"_id": ObjectId(id)})
    if note:
        new_pinned = not note.get('pinned', False)
        notes_collection.update_one({"_id": ObjectId(id)}, {"$set": {"pinned": new_pinned}})
        log_action("PIN_BULLETIN", f"{'Pinned' if new_pinned else 'Unpinned'} bulletin: {id}")
        socketio.emit('dashboard_update')
        
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({"success": True, "message": "Bulletin pin toggled."})
    return redirect(url_for('bulletin.bulletin'))

@bulletin_bp.route('/bulletin/edit/<id>', methods=['POST'])
@login_required
def edit_bulletin(id):
    notes_collection = get_notes_collection()
    note = notes_collection.find_one({"_id": ObjectId(id)})
    if not note:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({"success": False, "message": "Bulletin not found."}), 404
        return redirect(url_for('bulletin.bulletin'))
    
    # Only author can edit
    if note.get('author') != session.get('email'):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({"success": False, "message": "You can only edit your own posts."}), 403
        flash("You can only edit your own posts.", "danger")
        return redirect(url_for('bulletin.bulletin'))
        
    data = request.get_json() if request.is_json else request.form
    content = data.get('content')
    color = data.get('color')
    tag = data.get('tag')
    
    update_data = {}
    if content: update_data['content'] = content
    if color: update_data['color'] = color
    if tag: update_data['tag'] = tag
    
    if update_data:
        notes_collection.update_one({"_id": ObjectId(id)}, {"$set": update_data})
        log_action("EDIT_BULLETIN", f"Edited bulletin ID: {id}")
        socketio.emit('dashboard_update')
        
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({"success": True, "message": "Bulletin updated."})
    return redirect(url_for('bulletin.bulletin'))

@bulletin_bp.route('/bulletin/purge-done', methods=['POST'])
@login_required
@role_required('owner')
def purge_done_bulletins():
    notes_collection = get_notes_collection()
    # Be flexible with status casing (done, DONE, Done)
    res = notes_collection.delete_many({"status": {"$in": ["done", "DONE", "Done"]}})
    log_action("PURGE_BULLETINS", f"Purged {res.deleted_count} completed bulletins")
    
    # Force a dashboard update for all clients
    socketio.emit('dashboard_update')
    
    return jsonify({
        "success": True, 
        "message": f"Successfully purged {res.deleted_count} completed bulletins.",
        "count": res.deleted_count
    })

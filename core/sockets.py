from datetime import datetime
from core.db import get_users_collection
from extensions import socketio

online_users = {} # sid -> user_info

def init_socket_handlers():
    @socketio.on('connect')
    def handle_connect():
        from flask import session, request
        email = session.get('email', 'Guest')
        role = session.get('role', 'N/A')
        
        online_users[request.sid] = {
            'email': email,
            'role': role,
            'since': datetime.now().strftime('%I:%M %p')
        }
        emit_online_users()

    @socketio.on('disconnect')
    def handle_disconnect():
        from flask import request
        if request.sid in online_users:
            del online_users[request.sid]
        emit_online_users()

def emit_online_users():
    unique_users = []
    seen_emails = set()
    for sid, info in online_users.items():
        if info['email'] not in seen_emails:
            unique_users.append(info)
            seen_emails.add(info['email'])
    
    socketio.emit('online_users_update', {
        'count': len(unique_users),
        'users': unique_users
    })

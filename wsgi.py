import eventlet
eventlet.monkey_patch(all=True)

from app import app as application
import os

if __name__ == "__main__":
    from extensions import socketio
    port = int(os.getenv("PORT", 5000))
    socketio.run(application, host="0.0.0.0", port=port, debug=True, use_reloader=False)

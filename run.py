import eventlet
eventlet.monkey_patch(all=True)

import os
from app import app
from extensions import socketio

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    # use_reloader=False is critical when combined with monkey_patch
    socketio.run(app, host="0.0.0.0", port=port, debug=True, use_reloader=False)

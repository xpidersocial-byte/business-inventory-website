from flask import Blueprint, render_template, request, jsonify, session
from core.utils import log_action
from core.middleware import login_required
from core.db import get_items_collection, get_inventory_log_collection, get_system_log_collection
import ai_engine

ai_bp = Blueprint('ai', __name__)

@ai_bp.route('/ai-strategist')
@login_required
def ai_strategist():
    items_collection = get_items_collection()
    inventory_log_collection = get_inventory_log_collection()
    items_list = list(items_collection.find({}, {'_id': 0}))
    recent_logs = list(inventory_log_collection.find({"type": "OUT"}, {'_id': 0}).sort("timestamp", -1).limit(10))
    
    context_data = {
        "items": items_list,
        "recent_sales": recent_logs,
        "user_role": session.get('role', 'cashier')
    }
    
    ai_insight = ai_engine.get_ai_response("Analyze this business and provide 3-4 strategic bullets.", context_data=context_data)
    
    return render_template('ai_strategist.html', 
                           insight=ai_insight, 
                           role=session.get('role'))

@ai_bp.route('/debugging-ai')
@login_required
def debugging_ai():
    return render_template('debugging_ai.html', role=session.get('role'))

@ai_bp.route('/debugging-ai/scan', methods=['POST'])
@login_required
def scan_website():
    base_url = "http://127.0.0.1:5000"
    scan_results = ai_engine.run_full_site_scan(base_url, cookies=request.cookies)
    return jsonify({"success": True, "data": scan_results})

@ai_bp.route('/debugging-ai/fix', methods=['POST'])
@login_required
def fix_error():
    try:
        error_context = request.json.get('context', 'Unknown Error')
        prompt = f"A website error was detected. ERROR CONTEXT: {error_context}"
        fix_suggestion = ai_engine.get_ai_response(prompt)
        return jsonify({"success": True, "fix": fix_suggestion})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@ai_bp.route('/debugging-ai/analyze', methods=['POST'])
@login_required
def ai_analyze_errors():
    system_log_collection = get_system_log_collection()
    sys_logs = list(system_log_collection.find().sort("timestamp", -1).limit(15))
    log_summary = ""
    for l in sys_logs:
        log_summary += f"[{l.get('timestamp')}] {l.get('action')}: {l.get('details')}\n"

    prompt = f"Analyze these system logs: {log_summary}"
    try:
        analysis = ai_engine.get_ai_response(prompt)
        return jsonify({"success": True, "analysis": analysis})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

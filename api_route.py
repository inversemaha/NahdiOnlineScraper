"""
Simplified Flask API for Nahdi Online Description Fetcher

Only includes the update_all_descriptions functionality.

Routes:
    GET  /                          - API info
    POST /descriptions/all          - Update descriptions for all products
    GET  /descriptions/status       - Get update status/stats

Usage:
    python api_route.py
    
    # Then in another terminal:
    curl -X POST http://localhost:5000/descriptions/all
    curl http://localhost:5000/descriptions/status
"""

from flask import Flask, request, jsonify
import threading
import time
from datetime import datetime

# Import description fetcher functions
try:
    from product_description_service import update_all_descriptions
    DESCRIPTION_FETCHER_AVAILABLE = True
except ImportError:
    DESCRIPTION_FETCHER_AVAILABLE = False

app = Flask(__name__)

# Global status tracking
current_status = {
    "status": "idle",
    "operation": None,
    "start_time": None,
    "progress": None,
    "last_update": None
}

# Thread lock for status updates
status_lock = threading.Lock()


def update_status(status, operation=None, progress=None):
    """Update current operation status"""
    with status_lock:
        current_status["status"] = status
        current_status["operation"] = operation
        current_status["progress"] = progress
        current_status["last_update"] = datetime.utcnow().isoformat()
        if status == "running" and current_status["start_time"] is None:
            current_status["start_time"] = datetime.utcnow().isoformat()
        elif status == "idle":
            current_status["start_time"] = None


@app.route('/')
def api_info():
    """API information"""
    return jsonify({
        "name": "Nahdi Online Description Fetcher API",
        "version": "1.0.0",
        "description_fetcher_available": DESCRIPTION_FETCHER_AVAILABLE,
        "endpoints": {
            "GET /": "This info",
            "GET /descriptions/status": "Get current operation status",
            "POST /descriptions/all": "Update descriptions for all products"
        }
    })


@app.route('/descriptions/status')
def get_status():
    """Get current operation status"""
    with status_lock:
        return jsonify(current_status.copy())


@app.route('/descriptions/all', methods=['POST'])
def update_all_descriptions_route():
    """Update descriptions for all products"""
    if not DESCRIPTION_FETCHER_AVAILABLE:
        return jsonify({"error": "Description fetcher not available"}), 500
    
    if current_status["status"] == "running":
        return jsonify({"error": "Another operation is already running"}), 409
    
    def run_update():
        try:
            update_status("running", "update_all_descriptions")
            stats = update_all_descriptions()
            update_status("completed", progress=stats)
        except Exception as e:
            update_status("error", progress={"error": str(e)})
    
    # Run in background thread
    thread = threading.Thread(target=run_update)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "message": "Description update started for all products",
        "status": "running",
        "check_status_url": "/descriptions/status"
    })


if __name__ == '__main__':
    print("🚀 Starting Nahdi Online Description Fetcher API")
    print("📝 Available endpoints:")
    print("   GET  / - API info")
    print("   GET  /descriptions/status - Status")
    print("   POST /descriptions/all - Update all descriptions")
    print("🌐 Server starting ")
    
    # Set to False in production
    app.run(debug=True, host='0.0.0.0', port=5000)
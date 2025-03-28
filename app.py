import os
import sqlite3
import random
import string
import logging
import json
import sys
from flask import Flask, jsonify, request, g
from pathlib import Path
from api import public_endpoints, private_endpoints
from database import init_db, get_db
from auth import generate_api_credentials, get_api_credentials

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

# Set up database folder
data_dir = Path('./data')
data_dir.mkdir(exist_ok=True)
app.config['DATABASE'] = str(data_dir / 'kraken_sandbox.db')

@app.before_request
def before_request():
    g.db = get_db()

@app.teardown_request
def teardown_request(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# Initialize database on startup
with app.app_context():
    init_db()
    # Generate API credentials if they don't exist
    api_key, api_secret = generate_api_credentials()
    if api_key and api_secret:
        print("\n=== KRAKEN SANDBOX API CREDENTIALS ===", flush=True)
        print(f"API KEY: {api_key}", flush=True)
        print(f"API SECRET: {api_secret}", flush=True)
        print("=====================================\n", flush=True)
    else:
        # If no new credentials were generated, get existing ones
        cursor = get_db().cursor()
        cursor.execute('SELECT api_key, api_secret FROM api_credentials LIMIT 1')
        creds = cursor.fetchone()
        if creds:
            print("\n=== KRAKEN SANDBOX API CREDENTIALS ===", flush=True)
            print(f"API KEY: {creds['api_key']}", flush=True)
            print(f"API SECRET: {creds['api_secret']}", flush=True)
            print("=====================================\n", flush=True)
        else:
            print("ERROR: Could not retrieve API credentials", flush=True)

# Register API endpoints
@app.route('/')
def index():
    return jsonify({
        "status": "OK",
        "message": "Kraken Sandbox API is running",
        "version": "1.0.0"
    })

# Register public API endpoints
app.register_blueprint(public_endpoints.bp)

# Register private API endpoints 
app.register_blueprint(private_endpoints.bp)

# Error handling
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": ["Invalid API endpoint or method"],
        "result": {}
    }), 404

@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Unhandled exception: {str(e)}")
    return jsonify({
        "error": ["Internal server error"],
        "result": {}
    }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 
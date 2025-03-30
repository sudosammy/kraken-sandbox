import os
import base64
import hashlib
import hmac
import time
import urllib.parse
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import random
import string
import logging
from flask import request, g, current_app
from database import seed_account_balances

logger = logging.getLogger(__name__)

def generate_api_key(length=56):
    """Generate a random API key"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def generate_api_secret(length=64):
    """Generate a random API secret"""
    return base64.b64encode(os.urandom(length)).decode('utf-8')

def generate_api_credentials():
    """Generate and store API credentials if they don't exist"""
    db = g.db
    cursor = db.cursor()
    
    # Check if credentials exist
    cursor.execute('SELECT api_key, api_secret FROM api_credentials LIMIT 1')
    result = cursor.fetchone()
    
    if result:
        # Credentials already exist
        return None, None
    
    # Generate new credentials
    api_key = generate_api_key()
    api_secret = generate_api_secret()

    # Store in database
    cursor.execute(
        'INSERT INTO api_credentials (api_key, api_secret) VALUES (?, ?)',
        (api_key, api_secret)
    )
    db.commit()
    
    # Seed account balances with the new API key
    logger.info("Now seeding account balance")
    seed_account_balances(db, api_key)
    
    return api_key, api_secret

def get_api_credentials():
    """Get existing API credentials"""
    db = g.db
    cursor = db.cursor()
    
    cursor.execute('SELECT api_key, api_secret FROM api_credentials LIMIT 1')
    result = cursor.fetchone()
    
    if result:
        return result['api_key'], result['api_secret']
    return None, None

def get_api_secret(api_key):
    """Get API secret for the given API key"""
    db = g.db
    cursor = db.cursor()
    
    cursor.execute('SELECT api_secret FROM api_credentials WHERE api_key = ?', (api_key,))
    result = cursor.fetchone()
    
    if result:
        return result[0]
    return None

def verify_api_credentials():
    """Verify that the API credentials in the request are valid"""
    # Get API key and signature from request headers
    api_key = request.headers.get('API-Key')
    api_sign = request.headers.get('API-Sign')
    
    if not api_key or not api_sign:
        return False, {"error": ["EAPI:Invalid key"]}
    
    # Get API secret from database
    api_secret = get_api_secret(api_key)
    if not api_secret:
        return False, {"error": ["EAPI:Invalid key"]}
    
    # Get nonce and additional params from request
    nonce = request.form.get('nonce')
    if not nonce:
        return False, {"error": ["EAPI:Invalid nonce"]}
    
    try:
        # In production Kraken API, this would verify the signature against the request
        # For our sandbox, we'll just check that the API key is valid
        return True, {"api_key": api_key}
    except Exception as e:
        logger.error(f"Error verifying API credentials: {str(e)}")
        return False, {"error": ["EAPI:Invalid signature"]}

def create_kraken_signature(api_path, data, secret):
    """Create Kraken API signature for private endpoints (for reference)"""
    postdata = urllib.parse.urlencode(data)
    encoded = (str(data['nonce']) + postdata).encode()
    message = api_path.encode() + hashlib.sha256(encoded).digest()
    
    # Add padding if needed
    if len(secret) % 4:
        # Add required padding
        padding = '=' * (4 - len(secret) % 4)
        secret += padding
    
    try:
        mac = hmac.new(base64.b64decode(secret), message, hashlib.sha512)
        sigdigest = base64.b64encode(mac.digest())
        return sigdigest.decode()
    except Exception as e:
        logger.error(f"Error creating signature: {str(e)}")
        raise ValueError("Invalid API secret format") 
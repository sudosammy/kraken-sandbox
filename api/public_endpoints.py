import json
import logging
import requests
from flask import Blueprint, request, jsonify, g
import utils
import sqlite3
import random
import datetime

logger = logging.getLogger(__name__)

# Create Blueprint for public endpoints
bp = Blueprint('public', __name__, url_prefix='/0/public')

def get_params():
    """Helper function to get parameters from all possible sources.
    
    This function collects parameters from query string, form data, and JSON body,
    ensuring endpoint handlers can access parameters regardless of how they're sent.
    
    Returns:
        dict: Combined parameters from all sources
    """
    # Start with query parameters (present in both GET and POST)
    params = request.args.copy()
    
    # If it's a POST request, also check form data and JSON content
    if request.method == 'POST':
        # Add form data if present
        if request.form:
            for key in request.form:
                params[key] = request.form[key]
                
        # Add JSON data if present and is a dict
        if request.is_json and request.json and isinstance(request.json, dict):
            for key in request.json:
                params[key] = request.json[key]
                
    return params

@bp.route('/AssetPairs', methods=['GET', 'POST'])
def asset_pairs():
    """Get tradable asset pairs
    
    Endpoint implementation based on: 
    https://docs.kraken.com/api/docs/rest-api/get-tradable-asset-pairs
    """
    params = get_params()
    
    pair = params.get('pair')
    info = params.get('info', 'info')
    country_code = params.get('country_code')
    
    db = g.db
    cursor = db.cursor()
    
    try:
        # Filter by pair if specified
        if pair:
            pairs = pair.split(',')
            placeholders = ', '.join('?' for _ in pairs)
            cursor.execute(
                f'''SELECT pair_name, altname, wsname, base, quote, pair_decimals, 
                   cost_decimals, lot_decimals, status, data 
                   FROM asset_pairs WHERE pair_name IN ({placeholders})''',
                pairs
            )
        else:
            cursor.execute(
                '''SELECT pair_name, altname, wsname, base, quote, pair_decimals, 
                   cost_decimals, lot_decimals, status, data 
                   FROM asset_pairs'''
            )
            
        rows = cursor.fetchall()
        result = {}
        
        for row in rows:
            pair_data = {
                'altname': row['altname'],
                'wsname': row['wsname'],
                'aclass_base': 'currency',
                'base': row['base'],
                'aclass_quote': 'currency',
                'quote': row['quote'],
                'pair_decimals': row['pair_decimals'],
                'cost_decimals': row['cost_decimals'],
                'lot_decimals': row['lot_decimals'],
                'status': row['status']
            }
            
            # Add additional data from JSON field
            additional_data = json.loads(row['data']) if row['data'] else {}
            
            # Filter data based on info parameter
            if info == 'info' or info is None:
                pair_data.update(additional_data)
            elif info == 'leverage' and 'leverage_buy' in additional_data:
                pair_data['leverage_buy'] = additional_data.get('leverage_buy', [])
                pair_data['leverage_sell'] = additional_data.get('leverage_sell', [])
            elif info == 'fees' and 'fees' in additional_data:
                pair_data['fees'] = additional_data.get('fees', [])
                if 'fees_maker' in additional_data:
                    pair_data['fees_maker'] = additional_data.get('fees_maker', [])
                pair_data['fee_volume_currency'] = additional_data.get('fee_volume_currency', 'ZUSD')
            elif info == 'margin' and 'margin_call' in additional_data:
                pair_data['margin_call'] = additional_data.get('margin_call', 80)
                pair_data['margin_stop'] = additional_data.get('margin_stop', 40)
            
            result[row['pair_name']] = pair_data
        
        return jsonify({
            'error': [],
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in AssetPairs endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500

@bp.route('/Ticker', methods=['GET', 'POST'])
def ticker():
    """Get ticker information
    
    Endpoint implementation based on: 
    https://docs.kraken.com/api/docs/rest-api/get-ticker-information
    """
    params = get_params()
    
    pair = params.get('pair')
    
    db = g.db
    cursor = db.cursor()
    
    try:
        # Get pairs to query
        if pair:
            pairs = pair.split(',')
        else:
            # Get all available pairs
            cursor.execute('SELECT pair_name FROM asset_pairs')
            pairs = [row['pair_name'] for row in cursor.fetchall()]
        
        result = {}
        
        for p in pairs:
            # Get current price from external API or generate realistic values
            current_price = utils.get_market_price(p)
            
            # Generate realistic ticker data
            price_float = float(current_price)
            bid_price = price_float * 0.9995  # Slightly lower than current price
            ask_price = price_float * 1.0005  # Slightly higher than current price
            
            # 24h volume (random but realistic)
            volume_24h = random.uniform(100, 5000)
            volume_today = volume_24h * random.uniform(0.3, 0.8)  # Today's volume is a portion of 24h
            
            # VWAP (volume-weighted average price)
            vwap_24h = price_float * random.uniform(0.98, 1.02)
            vwap_today = price_float * random.uniform(0.99, 1.01)
            
            # Trade count
            trades_24h = int(volume_24h * random.uniform(5, 15))
            trades_today = int(trades_24h * random.uniform(0.3, 0.8))
            
            # High/low
            high_24h = price_float * random.uniform(1.01, 1.05)
            high_today = min(high_24h, price_float * random.uniform(1.005, 1.03))
            low_24h = price_float * random.uniform(0.95, 0.99)
            low_today = max(low_24h, price_float * random.uniform(0.97, 0.995))
            
            # Opening price
            opening_price = price_float * random.uniform(0.97, 1.03)
            
            # Format according to Kraken's expected response
            ticker_data = {
                'a': [f"{ask_price:.8f}", "1", "1.000"],  # Ask [price, whole lot volume, lot volume]
                'b': [f"{bid_price:.8f}", "1", "1.000"],  # Bid [price, whole lot volume, lot volume]
                'c': [f"{price_float:.8f}", f"{random.uniform(0.00001, 0.1):.8f}"],  # Last trade closed [price, lot volume]
                'v': [f"{volume_today:.8f}", f"{volume_24h:.8f}"],  # Volume [today, last 24h]
                'p': [f"{vwap_today:.5f}", f"{vwap_24h:.5f}"],  # VWAP [today, last 24h]
                't': [trades_today, trades_24h],  # Number of trades [today, last 24h]
                'l': [f"{low_today:.8f}", f"{low_24h:.8f}"],  # Low [today, last 24h]
                'h': [f"{high_today:.8f}", f"{high_24h:.8f}"],  # High [today, last 24h]
                'o': f"{opening_price:.8f}"  # Today's opening price
            }
            
            result[p] = ticker_data
        
        return jsonify({
            'error': [],
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in Ticker endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500

@bp.route('/OHLC', methods=['GET', 'POST'])
def ohlc():
    """Get OHLC data
    
    Endpoint implementation based on: 
    https://docs.kraken.com/api/docs/rest-api/get-ohlc-data
    """
    params = get_params()
    
    pair = params.get('pair')
    interval = params.get('interval', '1')  # Default 1 minute
    since = params.get('since')
    
    if not pair:
        logger.error("Error in OHLC endpoint: Missing required parameter 'pair'")
        return jsonify({
            'error': ['EGeneral:Invalid arguments:pair'],
            'result': {}
        }), 400
    
    try:
        # Generate OHLC data for the pair
        ohlc_data, last_timestamp = utils.format_ohlc_data(pair, interval, since)
        
        result = {
            pair: ohlc_data,
            'last': last_timestamp
        }
        
        return jsonify({
            'error': [],
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in OHLC endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500

@bp.route('/Time', methods=['GET', 'POST'])
def server_time():
    """Get server time
    
    Endpoint implementation based on:
    https://docs.kraken.com/api/docs/rest-api/get-server-time
    """
    try:
        # Get current Unix timestamp
        unixtime = utils.get_kraken_server_time()
        
        # Format RFC 1123 time
        dt = datetime.datetime.fromtimestamp(unixtime)
        rfc1123 = dt.strftime('%a, %d %b %y %H:%M:%S +0000')
        
        return jsonify({
            'error': [],
            'result': {
                'unixtime': unixtime,
                'rfc1123': rfc1123
            }
        })
        
    except Exception as e:
        logger.error(f"Error in Time endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500

@bp.route('/Assets', methods=['GET', 'POST'])
def assets():
    """Get asset info
    
    Endpoint implementation based on:
    https://docs.kraken.com/api/docs/rest-api/get-asset-info
    """
    params = get_params()
    
    asset = params.get('asset')
    aclass = params.get('aclass', 'currency')
    
    db = g.db
    cursor = db.cursor()
    
    try:
        # Filter by asset if specified
        if asset:
            assets = asset.split(',')
            placeholders = ', '.join('?' for _ in assets)
            cursor.execute(
                f'''SELECT asset, asset_name, decimals, display_decimals, status, data 
                   FROM assets WHERE asset IN ({placeholders})''',
                assets
            )
        else:
            cursor.execute(
                '''SELECT asset, asset_name, decimals, display_decimals, status, data 
                   FROM assets'''
            )
            
        rows = cursor.fetchall()
        result = {}
        
        for row in rows:
            asset_data = {
                'aclass': aclass,
                'altname': row['asset_name'],
                'decimals': row['decimals'],
                'display_decimals': row['display_decimals'],
                'status': row['status']
            }
            
            # Add additional data from JSON field
            if row['data']:
                additional_data = json.loads(row['data'])
                asset_data.update(additional_data)
            
            result[row['asset']] = asset_data
        
        return jsonify({
            'error': [],
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in Assets endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500

@bp.route('/Depth', methods=['GET', 'POST'])
def order_book():
    """Get order book
    
    Endpoint implementation based on:
    https://docs.kraken.com/api/docs/rest-api/get-order-book
    """
    params = get_params()
    
    pair = params.get('pair')
    count = params.get('count', '100')
    
    if not pair:
        logger.error("Error in Depth endpoint: Missing required parameter 'pair'")
        return jsonify({
            'error': ['EGeneral:Invalid arguments:pair'],
            'result': {}
        }), 400
    
    try:
        count = int(count)
        count = min(500, max(1, count))  # Bound count between 1 and 500
        pairs = pair.split(',')
        result = {}
        
        for p in pairs:
            # Get current price
            current_price = float(utils.get_market_price(p))
            
            # Generate asks (higher than current price)
            asks = []
            for i in range(count):
                price = current_price * (1 + (i + 1) * 0.0001)
                volume = random.uniform(0.1, 10.0)
                timestamp = utils.current_timestamp()
                asks.append([f"{price:.8f}", f"{volume:.8f}", timestamp])
            
            # Generate bids (lower than current price)
            bids = []
            for i in range(count):
                price = current_price * (1 - (i + 1) * 0.0001)
                volume = random.uniform(0.1, 10.0)
                timestamp = utils.current_timestamp()
                bids.append([f"{price:.8f}", f"{volume:.8f}", timestamp])
            
            result[p] = {
                'asks': asks,
                'bids': bids
            }
        
        return jsonify({
            'error': [],
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in Depth endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500

@bp.route('/Trades', methods=['GET', 'POST'])
def trades():
    """Get recent trades
    
    Endpoint implementation based on:
    https://docs.kraken.com/api/docs/rest-api/get-recent-trades
    """
    params = get_params()
    
    pair = params.get('pair')
    since = params.get('since')
    count = params.get('count', '1000')  # Not in official API but useful for limiting
    
    if not pair:
        logger.error("Error in Trades endpoint: Missing required parameter 'pair'")
        return jsonify({
            'error': ['EGeneral:Invalid arguments:pair'],
            'result': {}
        }), 400
    
    try:
        count = int(count)
        count = min(1000, max(1, count))  # Bound count between 1 and 1000
        
        if since:
            since_time = int(since)
        else:
            # Default to last hour
            since_time = utils.current_timestamp() - 3600
        
        pairs = pair.split(',')
        result = {}
        last_id = utils.current_timestamp()
        
        for p in pairs:
            # Get current price
            current_price = float(utils.get_market_price(p))
            
            # Generate trade data
            trades_data = []
            for i in range(count):
                # Timestamp decreases as we go back in time
                trade_time = since_time + (i * (utils.current_timestamp() - since_time) // count)
                
                # Price varies around current price
                price = current_price * (1 + random.uniform(-0.01, 0.01))
                
                # Random volume
                volume = random.uniform(0.001, 2.0)
                
                # Random buy/sell
                buy_sell = "b" if random.random() > 0.5 else "s"
                
                # Random market/limit
                market_limit = "m" if random.random() > 0.8 else "l"
                
                # Random miscellaneous flag
                misc = ""
                
                # Trade data format: [price, volume, time, buy/sell, market/limit, miscellaneous]
                trades_data.append([
                    f"{price:.8f}",
                    f"{volume:.8f}",
                    trade_time,
                    buy_sell,
                    market_limit,
                    misc
                ])
            
            result[p] = trades_data
        
        # Add last ID for pagination
        result['last'] = last_id
        
        return jsonify({
            'error': [],
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in Trades endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500

@bp.route('/Spread', methods=['GET', 'POST'])
def spread():
    """Get recent spreads
    
    Endpoint implementation based on:
    https://docs.kraken.com/api/docs/rest-api/get-recent-spreads
    """
    params = get_params()
    
    pair = params.get('pair')
    since = params.get('since')
    
    if not pair:
        logger.error("Error in Spread endpoint: Missing required parameter 'pair'")
        return jsonify({
            'error': ['EGeneral:Invalid arguments:pair'],
            'result': {}
        }), 400
    
    try:
        if since:
            since_time = int(since)
        else:
            # Default to last hour
            since_time = utils.current_timestamp() - 3600
        
        pairs = pair.split(',')
        result = {}
        last_id = utils.current_timestamp()
        
        for p in pairs:
            # Get current price
            current_price = float(utils.get_market_price(p))
            
            # Generate spread data (50 entries per pair)
            spread_data = []
            for i in range(50):
                # Timestamp decreases as we go back in time
                spread_time = since_time + (i * (utils.current_timestamp() - since_time) // 50)
                
                # Bid is lower than current price
                bid = current_price * (1 - random.uniform(0.001, 0.005))
                
                # Ask is higher than current price
                ask = current_price * (1 + random.uniform(0.001, 0.005))
                
                # Spread data format: [time, bid, ask]
                spread_data.append([
                    spread_time,
                    f"{bid:.8f}",
                    f"{ask:.8f}"
                ])
            
            result[p] = spread_data
        
        # Add last ID for pagination
        result['last'] = last_id
        
        return jsonify({
            'error': [],
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in Spread endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500

@bp.route('/SystemStatus', methods=['GET', 'POST'])
def system_status():
    """Get system status
    
    Endpoint implementation based on:
    https://docs.kraken.com/api/docs/rest-api/get-system-status
    """
    try:
        # Status options: "online", "maintenance", "cancel_only", "post_only"
        status = "online"
        
        # Generate a timestamp for the status update
        timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        
        return jsonify({
            'error': [],
            'result': {
                'status': status,
                'timestamp': timestamp
            }
        })
        
    except Exception as e:
        logger.error(f"Error in SystemStatus endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500

# We need to import random here for the ticker function
import random 
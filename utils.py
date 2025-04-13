import time
import random
import string
import json
import requests
import logging
from decimal import Decimal
import pprint
from flask import request

logger = logging.getLogger(__name__)

def log_request_info():
    """Log details of every request to the API"""
    logger.info(f"=== API REQUEST ===")
    logger.info(f"URL: {request.url}")
    logger.info(f"Method: {request.method}")
    logger.info(f"Endpoint: {request.endpoint}")
    logger.info(f"Path: {request.path}")
    
    # Log API key information
    api_key = request.headers.get('API-Key', '')
    api_sign = request.headers.get('API-Sign', '')
    
    has_api_key = bool(api_key)
    has_api_sign = bool(api_sign)
    
    # Log first 8 characters of API key and signature if available
    key_preview = api_key[:8] if has_api_key else 'None'
    sign_preview = api_sign[:8] if has_api_sign else 'None'
    
    logger.info(f"API Keys included: {has_api_key and has_api_sign}, Key: {key_preview}, Sign: {sign_preview}")
    
    # Add query parameters for GET requests
    if request.args:
        logger.info("Query Parameters:")
        for key, value in request.args.items():
            logger.info(f"  {key}: {value}")
    
    # Add form data or JSON body for POST requests
    if request.method == 'POST':
        if request.is_json:
            logger.info("JSON Body:")
            for key, value in request.json.items():
                logger.info(f"  {key}: {value}")
        elif request.form:
            logger.info("Form Data:")
            for key, value in request.form.items():
                logger.info(f"  {key}: {value}")
    
    logger.info(f"==================")

def current_timestamp():
    """Return current timestamp in seconds"""
    return int(time.time())

def generate_order_id():
    """Generate a random order ID in Kraken format"""
    letters = ''.join(random.choices(string.ascii_uppercase, k=6))
    numbers = ''.join(random.choices(string.digits, k=10))
    return f"O{letters}-{numbers}"

def generate_trade_id():
    """Generate a random trade ID in Kraken format"""
    letters = ''.join(random.choices(string.ascii_uppercase, k=6))
    numbers = ''.join(random.choices(string.digits, k=10))
    return f"T{letters}-{numbers}"

def get_market_price(pair):
    """Get current market price for a trading pair from public APIs"""
    # Define headers that clearly identify as a bot but prevent caching
    headers = {
        'User-Agent': 'KrakenSandbox-Bot/1.0',
        'Accept': 'application/json',
        'X-Bot-Client': 'true',
        'X-Request-Source': 'kraken-sandbox-api',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }
    
    # Add cache-busting timestamp
    cache_buster = int(time.time() * 1000)
    
    # Try Kraken API first
    try:
        # Normalize pair format for API call
        kraken_pair = pair
        
        # Construct the Kraken API URL
        url = "https://api.kraken.com/0/public/Ticker"
        params = {"pair": kraken_pair, "_": cache_buster}
        
        response = requests.get(url, headers=headers, params=params, timeout=5)
        # Disable response caching
        response.headers["Cache-Control"] = "no-store"
        data = response.json()
        
        # Check for errors
        if data.get("error") and len(data["error"]) > 0:
            logger.warning(f"Kraken API error: {data['error']}")
            raise Exception(f"Kraken API error: {data['error']}")
        
        # Extract price from response
        # The 'c' field contains the last trade closed [price, volume]
        result = data.get("result", {})
        if result and kraken_pair in result:
            return str(result[kraken_pair]["c"][0])
        
        # If the exact pair key isn't found, try searching through all results
        for key, value in result.items():
            if key.startswith(kraken_pair) or kraken_pair in key:
                return str(value["c"][0])
        
        logger.warning(f"Kraken pair not found: {kraken_pair}, falling back to CoinGecko")
        raise Exception(f"Kraken pair not found: {kraken_pair}")
        
    except Exception as e:
        logger.warning(f"Kraken API failed, trying CoinGecko: {str(e)}")
        
        # Fall back to CoinGecko
        try:
            if pair == 'XXBTZUSD' or pair == 'XBTUSD':
                url = f"https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&_={cache_buster}"
                response = requests.get(url, headers=headers, timeout=5)
                data = response.json()
                return str(data['bitcoin']['usd'])
            elif pair == 'XETHZUSD' or pair == 'ETHUSD':
                url = f"https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd&_={cache_buster}"
                response = requests.get(url, headers=headers, timeout=5)
                data = response.json()
                return str(data['ethereum']['usd'])
            elif pair == 'XXBTZAUD' or pair == 'XBTAUD':
                url = f"https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=aud&_={cache_buster}"
                response = requests.get(url, headers=headers, timeout=5)
                data = response.json()
                return str(data['bitcoin']['aud'])
            elif pair == 'XETHZAUD' or pair == 'ETHAUD':
                url = f"https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=aud&_={cache_buster}"
                response = requests.get(url, headers=headers, timeout=5)
                data = response.json()
                return str(data['ethereum']['aud'])
            else:
                # For unknown pairs, log and return a default value
                logger.info(f"Using default price for unknown pair: {pair}")
                return str(random.uniform(100, 50000))
        except Exception as e:
            logger.error(f"Error fetching market price for {pair}: {str(e)}")
            # Log and raise exception instead of falling back to random values
            error_msg = f"Failed to get market price for {pair}. All API calls failed."
            logger.critical(error_msg)
            raise Exception(error_msg) from e

def calculate_fee(volume, price, fee_percentage=0.26):
    """Calculate the fee for a trade
    
    Calculate the fee based on the standard Kraken fee structure.
    Default fee is 0.26% for taker and 0.16% for maker.
    
    Args:
        volume: Trade volume in base currency
        price: Trade price
        fee_percentage: Custom fee percentage (defaults to 0.26% taker fee)
        
    Returns:
        Fee amount as a string with 8 decimal precision
    """
    volume = Decimal(volume)
    price = Decimal(price)
    fee_percentage = Decimal(fee_percentage)
    
    cost = volume * price
    fee = cost * fee_percentage / Decimal('100')
    
    return str(fee.quantize(Decimal('0.00000001')))

def calculate_cost(volume, price):
    """Calculate the cost for a trade"""
    volume = Decimal(volume)
    price = Decimal(price)
    
    cost = volume * price
    
    return str(cost.quantize(Decimal('0.00000001')))

def generate_amend_id():
    """Generate a random amend ID in Kraken format (e.g., TEZA4R-DSDGT-IJBOJK)"""
    parts = []
    for _ in range(3):
        parts.append(''.join(random.choices(string.ascii_uppercase, k=6)))
    return '-'.join(parts)

def validate_price_precision(price, pair=None):
    """Validate that price has the correct number of decimal places for the pair
    
    For fiat currency pairs (e.g., USD, AUD), only 2 decimal places are allowed.
    Returns a tuple of (is_valid, error_message)
    
    Args:
        price: The price to validate as a string
        pair: The trading pair (e.g., 'ETHAUD', 'XBTUSD')
        
    Returns:
        A tuple (is_valid, error_message)
    """
    if price is None:
        return True, None
    
    # If no pair specified, default to allowing the price
    if not pair:
        return True, None
    
    # Get the quote currency from the pair
    fiat_currencies = ["ZUSD", "ZAUD", "USD", "AUD"]
    is_fiat_pair = False
    
    # First check if pair directly contains a fiat currency code
    for fiat in fiat_currencies:
        if fiat in pair:
            is_fiat_pair = True
            break
    
    if not is_fiat_pair:
        # If not found directly, we need to query the database to get the quote currency
        from flask import g
        if hasattr(g, 'db'):
            db = g.db
            cursor = db.cursor()
            cursor.execute('SELECT quote FROM asset_pairs WHERE pair_name = ? OR altname = ?', 
                          (pair, pair))
            result = cursor.fetchone()
            
            if result and result['quote'] in fiat_currencies:
                is_fiat_pair = True
    
    if is_fiat_pair:
        # For fiat currencies, only allow 2 decimal places
        try:
            decimal_price = Decimal(price)
            price_str = str(decimal_price)
            if '.' in price_str:
                integer_part, decimal_part = price_str.split('.')
                if len(decimal_part) > 2:
                    fiat = "AUD" if "AUD" in pair else "USD"
                    return False, f"Invalid price:{pair} price can only be specified up to 2 decimals."
        except:
            return False, "Invalid price format"
    
    return True, None

def get_kraken_server_time():
    """Get the current Kraken server time"""
    # Instead of calling the real Kraken API, use our sandbox's time
    return current_timestamp()

def format_ohlc_data(pair, interval='1', since=None):
    """Format OHLC data for a pair"""
    # Generate sample OHLC data
    current_time = current_timestamp()
    interval_seconds = int(interval) * 60
    
    # Default to 720 data points
    count = 720
    
    # If since is provided, calculate how many intervals to generate
    if since:
        since = int(since)
        time_diff = current_time - since
        count = min(720, max(1, time_diff // interval_seconds))
    
    # Get current price as a base
    base_price = float(get_market_price(pair))
    
    ohlc_data = []
    for i in range(count):
        # Calculate time for this candle
        candle_time = current_time - (count - i) * interval_seconds
        
        # Generate realistic price variation around base
        volatility = base_price * 0.005  # 0.5% volatility per candle
        open_price = base_price * (1 + random.uniform(-0.01, 0.01))
        high_price = open_price * (1 + random.uniform(0, 0.02))
        low_price = open_price * (1 - random.uniform(0, 0.02))
        close_price = random.uniform(low_price, high_price)
        
        # Adjust base price for next candle
        base_price = close_price
        
        # Generate volume
        volume = random.uniform(0.1, 10.0)
        
        # Format to Kraken's OHLC format
        ohlc = [
            candle_time,
            f"{open_price:.1f}",
            f"{high_price:.1f}",
            f"{low_price:.1f}",
            f"{close_price:.1f}",
            f"{close_price:.1f}",  # vwap (using close for simplicity)
            f"{volume:.8f}",
            random.randint(5, 100)  # random trade count
        ]
        
        ohlc_data.append(ohlc)
    
    return ohlc_data, current_time 
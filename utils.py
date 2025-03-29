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
    # Build request information dictionary
    request_info = {
        'url': request.url,
        'method': request.method,
        'endpoint': request.endpoint,
        'path': request.path,
    }
    
    # Add query parameters for GET requests
    if request.args:
        request_info['query_params'] = dict(request.args)
    
    # Add form data or JSON body for POST requests
    if request.method == 'POST':
        if request.is_json:
            request_info['json_body'] = request.json
        elif request.form:
            request_info['form_data'] = dict(request.form)
    
    # Pretty print the request info
    pretty_request = pprint.pformat(request_info, indent=2)
    logger.info(f"Received API request:\n{pretty_request}")

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
    # Define common browser headers to avoid rate limiting
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'Referer': 'https://www.coingecko.com/',
        'Cache-Control': 'no-cache'
    }
    
    # Using CoinGecko as a free price source
    try:
        if pair == 'XXBTZUSD' or pair == 'XBTUSD':
            url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
            response = requests.get(url, headers=headers, timeout=5)
            data = response.json()
            return str(data['bitcoin']['usd'])
        elif pair == 'XETHZUSD' or pair == 'ETHUSD':
            url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
            response = requests.get(url, headers=headers, timeout=5)
            data = response.json()
            return str(data['ethereum']['usd'])
        elif pair == 'XXBTZAUD' or pair == 'XBTAUD':
            url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=aud"
            response = requests.get(url, headers=headers, timeout=5)
            data = response.json()
            return str(data['bitcoin']['aud'])
        elif pair == 'XETHZAUD' or pair == 'ETHAUD':
            url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=aud"
            response = requests.get(url, headers=headers, timeout=5)
            data = response.json()
            return str(data['ethereum']['aud'])
        else:
            # For unknown pairs, log and return a default value
            logger.info(f"Using default price for unknown pair: {pair}")
            return str(random.uniform(100, 50000))
    except Exception as e:
        logger.error(f"Error fetching market price for {pair}: {str(e)}")
        # Fallback to fixed values if API call fails
        if 'XBT' in pair or 'BTC' in pair:
            return str(random.uniform(28000, 32000))
        elif 'ETH' in pair:
            return str(random.uniform(1800, 2200))
        else:
            return str(random.uniform(100, 50000))

def calculate_fee(volume, price, fee_percentage=0.26):
    """Calculate the fee for a trade"""
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
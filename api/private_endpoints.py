import json
import logging
import time
import sqlite3
from decimal import Decimal
from flask import Blueprint, request, jsonify, g
from auth import verify_api_credentials
import utils

logger = logging.getLogger(__name__)

# Create Blueprint for private endpoints
bp = Blueprint('private', __name__, url_prefix='/0/private')

@bp.before_request
def before_request():
    """Verify API credentials before processing any private endpoint request"""
    is_valid, response = verify_api_credentials()
    if not is_valid:
        logger.error(f"API authentication failed: {response.get('error', ['Unknown error'])}")
        return jsonify(response), 401

@bp.route('/Balance', methods=['POST'])
def balance():
    """Get account balance
    
    Endpoint implementation based on:
    https://docs.kraken.com/api/docs/rest-api/get-account-balance
    """
    api_key = request.headers.get('API-Key')
    
    db = g.db
    cursor = db.cursor()
    
    try:
        cursor.execute(
            'SELECT asset, balance FROM account_balances WHERE api_key = ?',
            (api_key,)
        )
        
        rows = cursor.fetchall()
        result = {}
        
        for row in rows:
            result[row['asset']] = row['balance']
        
        return jsonify({
            'error': [],
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in Balance endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500

@bp.route('/OpenOrders', methods=['POST'])
def open_orders():
    """Get open orders
    
    Endpoint implementation based on:
    https://docs.kraken.com/api/docs/rest-api/get-open-orders
    """
    api_key = request.headers.get('API-Key')
    
    # Get optional parameters
    trades = request.form.get('trades', 'false').lower() == 'true'
    userref = request.form.get('userref')
    
    db = g.db
    cursor = db.cursor()
    
    try:
        # Build the query based on parameters
        query = '''SELECT order_id, pair, type, order_type, price, price2, volume, 
                  executed_volume, status, opened_time, user_ref, data 
                  FROM orders WHERE api_key = ? AND status = 'open' '''
        params = [api_key]
        
        if userref:
            query += ' AND user_ref = ?'
            params.append(userref)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        result = {'open': {}}
        
        for row in rows:
            order_data = {
                'status': row['status'],
                'opentm': row['opened_time'],
                'vol': row['volume'],
                'vol_exec': row['executed_volume'],
                'cost': '0', # Will be calculated for executed portions
                'fee': '0',  # Will be calculated for executed portions
                'price': '0' # Will be calculated for executed portions
            }
            
            # Add order details
            if row['order_type'] == 'limit':
                order_data['price'] = row['price'] if row['price'] else '0'
                order_data['ordertype'] = 'limit'
            elif row['order_type'] == 'market':
                order_data['ordertype'] = 'market'
            else:
                order_data['ordertype'] = row['order_type']
                if row['price']:
                    order_data['price'] = row['price']
                if row['price2']:
                    order_data['price2'] = row['price2']
            
            order_data['type'] = row['type']  # buy or sell
            order_data['pair'] = row['pair']
            
            if row['user_ref']:
                order_data['userref'] = row['user_ref']
            
            # Calculate fees and cost for partially executed orders
            if float(row['executed_volume']) > 0:
                # Get trade details for this order
                cursor.execute(
                    '''SELECT SUM(cost) as total_cost, SUM(fee) as total_fee, 
                    AVG(price) as avg_price FROM trades 
                    WHERE api_key = ? AND order_id = ?''',
                    (api_key, row['order_id'])
                )
                trade_summary = cursor.fetchone()
                
                if trade_summary:
                    order_data['cost'] = str(trade_summary['total_cost'] or '0')
                    order_data['fee'] = str(trade_summary['total_fee'] or '0')
                    order_data['price'] = str(trade_summary['avg_price'] or '0')
                
                # Add trade information if requested
                if trades:
                    cursor.execute(
                        '''SELECT trade_id FROM trades 
                        WHERE api_key = ? AND order_id = ?''',
                        (api_key, row['order_id'])
                    )
                    trade_rows = cursor.fetchall()
                    
                    if trade_rows:
                        order_data['trades'] = [row['trade_id'] for row in trade_rows]
            
            result['open'][row['order_id']] = order_data
        
        return jsonify({
            'error': [],
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in OpenOrders endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500

@bp.route('/AddOrder', methods=['POST'])
def add_order():
    """Place an order
    
    Endpoint implementation based on:
    https://docs.kraken.com/api/docs/rest-api/add-order
    """
    api_key = request.headers.get('API-Key')
    
    # Required parameters
    pair = request.form.get('pair')
    type = request.form.get('type')  # buy or sell
    ordertype = request.form.get('ordertype')  # market, limit, etc.
    volume = request.form.get('volume')
    
    # Optional parameters
    price = request.form.get('price')
    price2 = request.form.get('price2')
    userref = request.form.get('userref')
    
    # Validate parameters
    if not pair or not type or not ordertype or not volume:
        logger.error(f"Error in AddOrder endpoint: Missing required parameters - pair: {pair}, type: {type}, ordertype: {ordertype}, volume: {volume}")
        return jsonify({
            'error': ['EGeneral:Invalid arguments'],
            'result': {}
        }), 400
    
    # Validate order type
    if ordertype not in ['market', 'limit', 'stop-loss', 'take-profit', 'stop-loss-limit', 'take-profit-limit', 'settle-position']:
        logger.error(f"Error in AddOrder endpoint: Invalid ordertype '{ordertype}'")
        return jsonify({
            'error': ['EGeneral:Invalid ordertype'],
            'result': {}
        }), 400
    
    # Validate order direction
    if type not in ['buy', 'sell']:
        logger.error(f"Error in AddOrder endpoint: Invalid type '{type}'")
        return jsonify({
            'error': ['EGeneral:Invalid type'],
            'result': {}
        }), 400
    
    # Additional validation for limit orders
    if ordertype in ['limit', 'stop-loss-limit', 'take-profit-limit'] and not price:
        logger.error(f"Error in AddOrder endpoint: Missing price for {ordertype} order")
        return jsonify({
            'error': ['EGeneral:Invalid arguments:price'],
            'result': {}
        }), 400
    
    db = g.db
    cursor = db.cursor()
    
    try:
        # Verify pair exists
        cursor.execute('SELECT pair_name FROM asset_pairs WHERE pair_name = ? OR altname = ?', (pair, pair))
        pair_row = cursor.fetchone()
        if not pair_row:
            logger.error(f"Error in AddOrder endpoint: Invalid pair '{pair}'")
            return jsonify({
                'error': ['EGeneral:Invalid arguments:pair'],
                'result': {}
            }), 400
        
        # Verify sufficient balance for buy or sell
        cursor.execute('SELECT pair_name, base, quote FROM asset_pairs WHERE pair_name = ? OR altname = ?', (pair, pair))
        pair_info = cursor.fetchone()
        
        if type == 'buy':
            # Check if user has enough of the quote currency (e.g., USD for BTC/USD)
            quote_asset = pair_info['quote']
            
            cursor.execute('SELECT balance FROM account_balances WHERE api_key = ? AND asset = ?', 
                          (api_key, quote_asset))
            balance_row = cursor.fetchone()
            
            if not balance_row:
                # Create balance record if it doesn't exist
                cursor.execute('INSERT INTO account_balances (api_key, asset, balance) VALUES (?, ?, ?)',
                              (api_key, quote_asset, '0'))
                db.commit()
                balance = Decimal('0')
            else:
                balance = Decimal(balance_row['balance'])
            
            # For market orders, we need the current price
            if ordertype == 'market':
                price = utils.get_market_price(pair)
            
            # Check if balance is sufficient
            cost = Decimal(volume) * Decimal(price) if price else Decimal('0')
            
            if cost > balance:
                logger.error(f"Error in AddOrder endpoint: Insufficient funds for buy order - cost: {cost}, balance: {balance}")
                return jsonify({
                    'error': ['EOrder:Insufficient funds'],
                    'result': {}
                }), 400
            
        elif type == 'sell':
            # Check if user has enough of the base currency (e.g., BTC for BTC/USD)
            base_asset = pair_info['base']
            
            cursor.execute('SELECT balance FROM account_balances WHERE api_key = ? AND asset = ?', 
                          (api_key, base_asset))
            balance_row = cursor.fetchone()
            
            if not balance_row:
                # Create balance record if it doesn't exist
                cursor.execute('INSERT INTO account_balances (api_key, asset, balance) VALUES (?, ?, ?)',
                              (api_key, base_asset, '0'))
                db.commit()
                balance = Decimal('0')
            else:
                balance = Decimal(balance_row['balance'])
            
            # Check if balance is sufficient
            volume_dec = Decimal(volume)
            
            if volume_dec > balance:
                logger.error(f"Error in AddOrder endpoint: Insufficient funds for sell order - volume: {volume_dec}, balance: {balance}")
                return jsonify({
                    'error': ['EOrder:Insufficient funds'],
                    'result': {}
                }), 400
        
        # Generate order ID
        order_id = utils.generate_order_id()
        timestamp = utils.current_timestamp()
        
        # Store order in database
        cursor.execute('''
        INSERT INTO orders 
        (api_key, order_id, pair, type, order_type, price, price2, volume, 
         status, opened_time, user_ref, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            api_key, order_id, pair, type, ordertype, price, price2, volume,
            'open', timestamp, userref, '{}'
        ))
        
        # For demonstration purposes:
        # 1. Execute market orders immediately
        # 2. Execute limit orders if they're within 5% of the current price
        # 3. Keep limit orders open if they're more than 5% away from the current price
        execute_order = False
        
        if ordertype == 'market':
            # Market orders always execute
            execute_order = True
            exec_price = utils.get_market_price(pair)
        elif ordertype == 'limit':
            # For limit orders, check if price is close to market
            current_price = Decimal(utils.get_market_price(pair))
            limit_price = Decimal(price)
            price_difference_pct = abs((limit_price - current_price) / current_price * 100)

            # Execute if within 5% of market price
            if price_difference_pct <= 5:
                execute_order = True
                exec_price = price
            else:
                logger.info(f"Keeping limit order open as price difference is > 5%")
        
        if execute_order:
            # Execute the order
            executed_volume = volume
            cost = utils.calculate_cost(volume, exec_price)
            fee = utils.calculate_fee(volume, exec_price)
            
            # Generate trade ID
            trade_id = utils.generate_trade_id()
            
            # Update order status
            cursor.execute('''
            UPDATE orders SET status = ?, executed_volume = ?, closed_time = ? 
            WHERE order_id = ?
            ''', ('closed', executed_volume, timestamp, order_id))
            
            # Create trade record
            cursor.execute('''
            INSERT INTO trades 
            (api_key, trade_id, order_id, pair, type, price, cost, fee, volume, time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                api_key, trade_id, order_id, pair, type, exec_price, cost, fee, volume, timestamp
            ))
            
            # Update balances (subtract fee from the received amount)
            if type == 'buy':
                # Deduct quote currency (e.g., USD) and add base currency (e.g., BTC)
                quote_asset = pair_info['quote']
                base_asset = pair_info['base']
                
                # Update or insert quote asset balance
                cursor.execute('''
                INSERT INTO account_balances (api_key, asset, balance) 
                VALUES (?, ?, ?) 
                ON CONFLICT(api_key, asset) 
                DO UPDATE SET balance = CAST(balance AS DECIMAL) - ?
                ''', (api_key, quote_asset, str(Decimal('0') - Decimal(cost)), str(cost)))
                
                # Update or insert base asset balance
                cursor.execute('''
                INSERT INTO account_balances (api_key, asset, balance) 
                VALUES (?, ?, ?) 
                ON CONFLICT(api_key, asset) 
                DO UPDATE SET balance = CAST(balance AS DECIMAL) + ?
                ''', (api_key, base_asset, str(volume), str(volume)))
                
            elif type == 'sell':
                # Add quote currency (e.g., USD) and deduct base currency (e.g., BTC)
                quote_asset = pair_info['quote']
                base_asset = pair_info['base']
                
                # Update or insert quote asset balance (subtract fee)
                fee_decimal = Decimal(fee)
                net_proceeds = Decimal(cost) - fee_decimal
                
                cursor.execute('''
                INSERT INTO account_balances (api_key, asset, balance) 
                VALUES (?, ?, ?) 
                ON CONFLICT(api_key, asset) 
                DO UPDATE SET balance = CAST(balance AS DECIMAL) + ?
                ''', (api_key, quote_asset, str(net_proceeds), str(net_proceeds)))
                
                # Update or insert base asset balance
                cursor.execute('''
                INSERT INTO account_balances (api_key, asset, balance) 
                VALUES (?, ?, ?) 
                ON CONFLICT(api_key, asset) 
                DO UPDATE SET balance = CAST(balance AS DECIMAL) - ?
                ''', (api_key, base_asset, str(Decimal('0') - Decimal(volume)), str(volume)))
        
        db.commit()
        
        # Return success response with order details
        result = {
            'descr': {
                'order': f"{type} {volume} {pair} @ {price if price else 'market'} {ordertype}"
            },
            'txid': [order_id]
        }
        
        return jsonify({
            'error': [],
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in AddOrder endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500

@bp.route('/ClosedOrders', methods=['POST'])
def closed_orders():
    """Get closed orders
    
    Endpoint implementation based on:
    https://docs.kraken.com/api/docs/rest-api/get-closed-orders
    """
    api_key = request.headers.get('API-Key')
    
    # Get optional parameters
    trades = request.form.get('trades', 'false').lower() == 'true'
    userref = request.form.get('userref')
    start = request.form.get('start')
    end = request.form.get('end')
    ofs = request.form.get('ofs', '0')
    closetime = request.form.get('closetime', 'both')
    
    db = g.db
    cursor = db.cursor()
    
    try:
        # Build the query based on parameters
        query = '''SELECT order_id, pair, type, order_type, price, price2, volume, 
                  executed_volume, status, opened_time, closed_time, user_ref, data 
                  FROM orders WHERE api_key = ? AND status != 'open' '''
        params = [api_key]
        
        if userref:
            query += ' AND user_ref = ?'
            params.append(userref)
        
        if start:
            query += ' AND closed_time >= ?'
            params.append(int(start))
            
        if end:
            query += ' AND closed_time <= ?'
            params.append(int(end))
        
        # Add order by and limit
        query += ' ORDER BY closed_time DESC LIMIT 50 OFFSET ?'
        params.append(int(ofs))
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        result = {'closed': {}}
        
        for row in rows:
            order_data = {
                'status': row['status'],
                'opentm': row['opened_time'],
                'closetm': row['closed_time'],
                'vol': row['volume'],
                'vol_exec': row['executed_volume'],
                'cost': '0', # Will be calculated from trades
                'fee': '0',  # Will be calculated from trades
                'price': '0' # Will be calculated from trades
            }
            
            # Add order details
            if row['order_type'] == 'limit':
                order_data['price'] = row['price'] if row['price'] else '0'
                order_data['ordertype'] = 'limit'
            elif row['order_type'] == 'market':
                order_data['ordertype'] = 'market'
            else:
                order_data['ordertype'] = row['order_type']
                if row['price']:
                    order_data['price'] = row['price']
                if row['price2']:
                    order_data['price2'] = row['price2']
            
            order_data['type'] = row['type']  # buy or sell
            order_data['pair'] = row['pair']
            
            if row['user_ref']:
                order_data['userref'] = row['user_ref']
            
            # Get trade information
            if float(row['executed_volume']) > 0:
                cursor.execute(
                    '''SELECT SUM(cost) as total_cost, SUM(fee) as total_fee, 
                    AVG(price) as avg_price FROM trades 
                    WHERE api_key = ? AND order_id = ?''',
                    (api_key, row['order_id'])
                )
                trade_summary = cursor.fetchone()
                
                if trade_summary:
                    order_data['cost'] = str(trade_summary['total_cost'] or '0')
                    order_data['fee'] = str(trade_summary['total_fee'] or '0')
                    order_data['price'] = str(trade_summary['avg_price'] or '0')
                
                # Add trade details if requested
                if trades:
                    cursor.execute(
                        '''SELECT trade_id FROM trades 
                        WHERE api_key = ? AND order_id = ?''',
                        (api_key, row['order_id'])
                    )
                    trade_rows = cursor.fetchall()
                    
                    if trade_rows:
                        order_data['trades'] = [row['trade_id'] for row in trade_rows]
            
            result['closed'][row['order_id']] = order_data
        
        # Count total number of closed orders
        cursor.execute(
            'SELECT COUNT(*) as count FROM orders WHERE api_key = ? AND status != ?',
            (api_key, 'open')
        )
        count_row = cursor.fetchone()
        result['count'] = count_row['count'] if count_row else 0
        
        return jsonify({
            'error': [],
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in ClosedOrders endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500

@bp.route('/QueryTrades', methods=['POST'])
def query_trades():
    """Get information about specific trades
    
    Endpoint implementation based on:
    https://docs.kraken.com/api/docs/rest-api/get-trades-info
    """
    api_key = request.headers.get('API-Key')
    
    # Required parameters
    txid = request.form.get('txid')
    
    if not txid:
        logger.error("Error in QueryTrades endpoint: Missing required parameter 'txid'")
        return jsonify({
            'error': ['EGeneral:Invalid arguments'],
            'result': {}
        }), 400
    
    ids = txid.split(',')
    
    db = g.db
    cursor = db.cursor()
    
    try:
        result = {}
        
        # First try to find the IDs as trade IDs
        if ids:
            # Build placeholders for SQL query
            placeholders = ', '.join('?' for _ in ids)
            
            cursor.execute(
                f'''SELECT trade_id, order_id, pair, type, price, cost, fee, volume, time 
                FROM trades WHERE api_key = ? AND trade_id IN ({placeholders})''',
                [api_key] + ids
            )
            
            rows = cursor.fetchall()
            
            for row in rows:
                # Get order type for this trade
                cursor.execute(
                    'SELECT order_type FROM orders WHERE order_id = ?',
                    (row['order_id'],)
                )
                order_row = cursor.fetchone()
                ordertype = order_row['order_type'] if order_row else 'market'
                
                trade_data = {
                    'ordertxid': row['order_id'],
                    'pair': row['pair'],
                    'time': row['time'],
                    'type': row['type'],
                    'ordertype': ordertype,
                    'price': row['price'],
                    'cost': row['cost'],
                    'fee': row['fee'],
                    'vol': row['volume'],
                    'margin': False,  # Default to not margin trade
                    'misc': ''        # No misc info by default
                }
                
                result[row['trade_id']] = trade_data
        
        # If no trades found and we have exactly one ID, try to find trades by order ID
        if not result and len(ids) == 1:
            order_id = ids[0]
            
            cursor.execute(
                '''SELECT trade_id, order_id, pair, type, price, cost, fee, volume, time 
                FROM trades WHERE api_key = ? AND order_id = ?''',
                (api_key, order_id)
            )
            
            rows = cursor.fetchall()
            
            for row in rows:
                # Get order type for this trade
                cursor.execute(
                    'SELECT order_type FROM orders WHERE order_id = ?',
                    (row['order_id'],)
                )
                order_row = cursor.fetchone()
                ordertype = order_row['order_type'] if order_row else 'market'
                
                trade_data = {
                    'ordertxid': row['order_id'],
                    'pair': row['pair'],
                    'time': row['time'],
                    'type': row['type'],
                    'ordertype': ordertype,
                    'price': row['price'],
                    'cost': row['cost'],
                    'fee': row['fee'],
                    'vol': row['volume'],
                    'margin': False,
                    'misc': ''
                }
                
                result[row['trade_id']] = trade_data
            
            # If still no trades found, check if order exists
            if not result:
                cursor.execute(
                    '''SELECT order_id, pair, type, order_type, price, volume, opened_time 
                    FROM orders WHERE api_key = ? AND order_id = ?''',
                    (api_key, order_id)
                )
                
                order_row = cursor.fetchone()
                
                if order_row:
                    # Create a dummy trade for the order
                    trade_id = utils.generate_trade_id()
                    price = order_row['price'] or utils.get_market_price(order_row['pair'])
                    volume = order_row['volume']
                    cost = utils.calculate_cost(volume, price)
                    fee = utils.calculate_fee(volume, price)
                    timestamp = order_row['opened_time']
                    
                    # Insert dummy trade for testing purposes
                    cursor.execute('''
                    INSERT INTO trades 
                    (api_key, trade_id, order_id, pair, type, price, cost, fee, volume, time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        api_key, trade_id, order_id, order_row['pair'], order_row['type'], 
                        price, cost, fee, volume, timestamp
                    ))
                    
                    db.commit()
                    
                    # Add the dummy trade to the result
                    result[trade_id] = {
                        'ordertxid': order_id,
                        'pair': order_row['pair'],
                        'time': timestamp,
                        'type': order_row['type'],
                        'ordertype': order_row['order_type'],
                        'price': price,
                        'cost': cost,
                        'fee': fee,
                        'vol': volume,
                        'margin': False,
                        'misc': ''
                    }
                     
        return jsonify({
            'error': [],
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in QueryTrades endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500

@bp.route('/TradesHistory', methods=['POST'])
def trades_history():
    """Get trade history
    
    Endpoint implementation based on:
    https://docs.kraken.com/api/docs/rest-api/get-trade-history
    """
    api_key = request.headers.get('API-Key')
    
    # Optional parameters
    type = request.form.get('type', 'all')
    trades = request.form.get('trades', 'false').lower() == 'true'
    start = request.form.get('start')
    end = request.form.get('end')
    ofs = request.form.get('ofs', '0')
    
    db = g.db
    cursor = db.cursor()
    
    try:
        # Build the query based on parameters
        query = '''SELECT trade_id, order_id, pair, type, price, cost, fee, volume, time 
                  FROM trades WHERE api_key = ? '''
        params = [api_key]
        
        if type != 'all':
            query += ' AND type = ?'
            params.append(type)
        
        if start:
            query += ' AND time >= ?'
            params.append(int(start))
            
        if end:
            query += ' AND time <= ?'
            params.append(int(end))
        
        # Add order by and limit
        query += ' ORDER BY time DESC LIMIT 50 OFFSET ?'
        params.append(int(ofs))
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        result = {'trades': {}}
        
        for row in rows:
            # Get the order type for this trade
            cursor.execute(
                'SELECT order_type FROM orders WHERE order_id = ?',
                (row['order_id'],)
            )
            order_row = cursor.fetchone()
            ordertype = order_row['order_type'] if order_row else 'market'
            
            trade_data = {
                'ordertxid': row['order_id'],
                'pair': row['pair'],
                'time': row['time'],
                'type': row['type'],
                'ordertype': ordertype,
                'price': row['price'],
                'cost': row['cost'],
                'fee': row['fee'],
                'vol': row['volume'],
                'margin': False,  # Default to not margin trade
                'misc': ''        # No misc info by default
            }
            
            result['trades'][row['trade_id']] = trade_data
        
        # Count total number of trades
        cursor.execute(
            'SELECT COUNT(*) as count FROM trades WHERE api_key = ?',
            (api_key,)
        )
        count_row = cursor.fetchone()
        result['count'] = count_row['count'] if count_row else 0
        
        return jsonify({
            'error': [],
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in TradesHistory endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500

@bp.route('/CancelOrder', methods=['POST'])
def cancel_order():
    """Cancel an open order
    
    Endpoint implementation based on:
    https://docs.kraken.com/api/docs/rest-api/cancel-order
    """
    api_key = request.headers.get('API-Key')
    
    # Required parameters
    txid = request.form.get('txid')
    
    if not txid:
        logger.error("Error in CancelOrder endpoint: Missing required parameter 'txid'")
        return jsonify({
            'error': ['EGeneral:Invalid arguments'],
            'result': {}
        }), 400
    
    db = g.db
    cursor = db.cursor()
    
    try:
        # Check if the order exists and is open
        cursor.execute(
            'SELECT order_id, status FROM orders WHERE api_key = ? AND order_id = ?',
            (api_key, txid)
        )
        
        order_row = cursor.fetchone()
        
        if not order_row:
            logger.error(f"Error in CancelOrder endpoint: Order not found - API Key: {api_key}, txid: {txid}")
            return jsonify({
                'error': ['EOrder:Unknown order'],
                'result': {}
            }), 400
        
        if order_row['status'] != 'open':
            logger.error(f"Error in CancelOrder endpoint: Order not open - status: {order_row['status']}")
            return jsonify({
                'error': ['EOrder:Cannot cancel closed order'],
                'result': {}
            }), 400
        
        # Update order status
        timestamp = utils.current_timestamp()
        cursor.execute(
            'UPDATE orders SET status = ?, closed_time = ? WHERE order_id = ?',
            ('canceled', timestamp, txid)
        )
        
        db.commit()
        
        return jsonify({
            'error': [],
            'result': {
                'count': 1
            }
        })
        
    except Exception as e:
        logger.error(f"Error in CancelOrder endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500

@bp.route('/EditOrder', methods=['POST'])
def edit_order():
    """Amend an existing order by canceling it and creating a new one
    
    Endpoint implementation based on:
    https://docs.kraken.com/api/docs/rest-api/edit-order
    """
    api_key = request.headers.get('API-Key')
    
    # Required parameters
    txid = request.form.get('txid')
    userref = request.form.get('userref')
    pair = request.form.get('pair')
    
    if not txid and not userref:
        logger.error("Error in EditOrder endpoint: Missing required parameter 'txid' or 'userref'")
        return jsonify({
            'error': ['EGeneral:Invalid arguments'],
            'result': {}
        }), 400
    
    if not pair:
        logger.error("Error in EditOrder endpoint: Missing required parameter 'pair'")
        return jsonify({
            'error': ['EGeneral:Invalid arguments:pair'],
            'result': {}
        }), 400
    
    # Optional parameters
    volume = request.form.get('volume')
    displayvol = request.form.get('displayvol')
    price = request.form.get('price')
    price2 = request.form.get('price2')
    oflags = request.form.get('oflags', '')
    deadline = request.form.get('deadline')
    cancel_response = request.form.get('cancel_response', 'false').lower() == 'true'
    validate = request.form.get('validate', 'false').lower() == 'true'
    
    if not volume and not price and not price2 and not displayvol:
        logger.error("Error in EditOrder endpoint: No parameters to edit")
        return jsonify({
            'error': ['EGeneral:No parameters to edit'],
            'result': {}
        }), 400
    
    db = g.db
    cursor = db.cursor()
    
    try:
        # Find the original order
        if txid:
            cursor.execute(
                '''SELECT order_id, status, type, order_type, pair, price, price2, volume, 
                executed_volume, opened_time, user_ref FROM orders 
                WHERE api_key = ? AND order_id = ?''',
                (api_key, txid)
            )
        else:  # userref
            cursor.execute(
                '''SELECT order_id, status, type, order_type, pair, price, price2, volume, 
                executed_volume, opened_time, user_ref FROM orders 
                WHERE api_key = ? AND user_ref = ?''',
                (api_key, userref)
            )
        
        original_order = cursor.fetchone()
        
        if not original_order:
            logger.error(f"Error in EditOrder endpoint: Order not found - API Key: {api_key}, txid: {txid}, userref: {userref}")
            return jsonify({
                'error': ['EOrder:Unknown order'],
                'result': {}
            }), 400
        
        if original_order['status'] != 'open':
            logger.error(f"Error in EditOrder endpoint: Cannot edit closed order with status: {original_order['status']}")
            return jsonify({
                'error': ['EOrder:Cannot edit closed order'],
                'result': {}
            }), 400
        
        if original_order['order_type'] == 'market':
            logger.error("Error in EditOrder endpoint: Cannot edit market order")
            return jsonify({
                'error': ['EOrder:Cannot edit market order'],
                'result': {}
            }), 400
        
        # Check if order has conditional closes or stops/takes attached
        # (For this sandbox implementation, we'll assume no conditional closes)
        
        # Check if executed volume is greater than new volume
        if volume and float(volume) < float(original_order['executed_volume']):
            logger.error(f"Error in EditOrder endpoint: New volume {volume} is less than executed volume {original_order['executed_volume']}")
            return jsonify({
                'error': ['EOrder:Invalid volume:New volume must be greater than executed volume'],
                'result': {}
            }), 400
        
        # Store original order data
        original_txid = original_order['order_id']
        order_type = original_order['order_type']
        type = original_order['type']
        original_userref = original_order['user_ref']
        
        # If we're only validating, return success without making changes
        if validate:
            return jsonify({
                'error': [],
                'result': {
                    'descr': {
                        'order': f"{type} {volume or original_order['volume']} {pair} @ {price or original_order['price'] or 'market'} {order_type}"
                    }
                }
            })
        
        # Step 1: Cancel the original order
        timestamp = utils.current_timestamp()
        cursor.execute(
            'UPDATE orders SET status = ?, closed_time = ? WHERE order_id = ?',
            ('canceled', timestamp, original_txid)
        )
        
        # Step 2: Create a new order with updated parameters
        new_txid = utils.generate_order_id()
        
        # Use original values for any parameters not provided
        new_volume = volume or original_order['volume']
        new_price = price or original_order['price']
        new_price2 = price2 or original_order['price2']
        new_userref = userref or original_userref
        
        # Prepare data field for special options
        data = {}
        if displayvol:
            data['display_qty'] = displayvol
        
        # Insert the new order
        cursor.execute('''
        INSERT INTO orders 
        (api_key, order_id, pair, type, order_type, price, price2, volume, 
         executed_volume, status, opened_time, user_ref, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            api_key, new_txid, pair, type, order_type, new_price, new_price2, 
            new_volume, '0', 'open', timestamp, new_userref, json.dumps(data)
        ))
        
        db.commit()
        
        # Return success response
        result = {
            'status': 'ok',
            'txid': new_txid,
            'originaltxid': original_txid,
            'volume': new_volume,
            'price': new_price,
            'price2': new_price2,
            'orders_cancelled': 1,
            'descr': {
                'order': f"{type} {new_volume} {pair} @ {order_type} {new_price or 'market'}"
            }
        }
        
        if original_userref:
            result['olduserref'] = original_userref
            
        if new_userref:
            result['newuserref'] = new_userref
        
        return jsonify({
            'error': [],
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in EditOrder endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500

@bp.route('/AmendOrder', methods=['POST'])
def amend_order():
    """Amend an existing order in-place
    
    Endpoint implementation based on:
    https://docs.kraken.com/api/docs/rest-api/amend-order
    """
    api_key = request.headers.get('API-Key')
    
    # Required parameters - either txid or cl_ord_id is required
    txid = request.form.get('txid')
    cl_ord_id = request.form.get('cl_ord_id')
    
    if not txid and not cl_ord_id:
        logger.error("Error in AmendOrder endpoint: Missing required parameter 'txid' or 'cl_ord_id'")
        return jsonify({
            'error': ['EGeneral:Invalid arguments'],
            'result': {}
        }), 400
    
    # Optional parameters
    order_qty = request.form.get('order_qty')
    display_qty = request.form.get('display_qty')
    limit_price = request.form.get('limit_price')
    trigger_price = request.form.get('trigger_price')
    post_only = request.form.get('post_only', 'false').lower() == 'true'
    deadline = request.form.get('deadline')
    
    if not order_qty and not display_qty and not limit_price and not trigger_price:
        logger.error("Error in AmendOrder endpoint: No parameters to amend")
        return jsonify({
            'error': ['EGeneral:No parameters to amend'],
            'result': {}
        }), 400
    
    db = g.db
    cursor = db.cursor()
    
    try:
        # Build the query based on parameters to find the order
        if txid:
            cursor.execute(
                'SELECT order_id, status, order_type, pair, executed_volume FROM orders WHERE api_key = ? AND order_id = ?',
                (api_key, txid)
            )
        else:  # cl_ord_id
            cursor.execute(
                'SELECT order_id, status, order_type, pair, executed_volume FROM orders WHERE api_key = ? AND user_ref = ?',
                (api_key, cl_ord_id)
            )
        
        order_row = cursor.fetchone()
        
        if not order_row:
            logger.error(f"Error in AmendOrder endpoint: Order not found - API Key: {api_key}, txid: {txid}, cl_ord_id: {cl_ord_id}")
            return jsonify({
                'error': ['EOrder:Unknown order'],
                'result': {}
            }), 400
        
        if order_row['status'] != 'open':
            logger.error(f"Error in AmendOrder endpoint: Cannot amend closed order with status: {order_row['status']}")
            return jsonify({
                'error': ['EOrder:Cannot amend closed order'],
                'result': {}
            }), 400
        
        # Check if order type supports amendments
        if order_row['order_type'] == 'market':
            logger.error("Error in AmendOrder endpoint: Cannot amend market order")
            return jsonify({
                'error': ['EOrder:Cannot amend market order'],
                'result': {}
            }), 400
        
        # Check if the new quantity is less than executed quantity
        if order_qty and float(order_qty) < float(order_row['executed_volume']):
            logger.error(f"Error in AmendOrder endpoint: New quantity {order_qty} is less than executed quantity {order_row['executed_volume']}")
            return jsonify({
                'error': ['EOrder:Invalid order_qty:New quantity must be greater than executed quantity'],
                'result': {}
            }), 400
        
        # Validate display_qty for iceberg orders
        if display_qty and order_qty:
            if float(display_qty) < float(order_qty) / 15:
                logger.error(f"Error in AmendOrder endpoint: display_qty {display_qty} must be at least 1/15 of order_qty {order_qty}")
                return jsonify({
                    'error': ['EOrder:Invalid display_qty:Display quantity must be at least 1/15 of order quantity'],
                    'result': {}
                }), 400
        
        # Update order details
        update_fields = []
        update_values = []
        
        if order_qty:
            update_fields.append('volume = ?')
            update_values.append(order_qty)
            
        if limit_price:
            update_fields.append('price = ?')
            update_values.append(limit_price)
            
        if trigger_price:
            update_fields.append('price2 = ?')
            update_values.append(trigger_price)
        
        # For display_qty, we'll store it in the data JSON field
        if display_qty:
            cursor.execute('SELECT data FROM orders WHERE order_id = ?', (order_row['order_id'],))
            data_row = cursor.fetchone()
            data = json.loads(data_row['data'] or '{}')
            data['display_qty'] = display_qty
            update_fields.append('data = ?')
            update_values.append(json.dumps(data))
        
        if update_fields:
            update_sql = f'UPDATE orders SET {", ".join(update_fields)} WHERE order_id = ?'
            cursor.execute(update_sql, update_values + [order_row['order_id']])
            
            db.commit()
        
        # Generate amend_id
        amend_id = utils.generate_amend_id()
        
        # Return success response
        result = {
            'amend_id': amend_id
        }
        
        return jsonify({
            'error': [],
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in AmendOrder endpoint: {str(e)}")
        return jsonify({
            'error': ['EGeneral:Internal error'],
            'result': {}
        }), 500 
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
            
            # Add trade information if requested
            if trades and float(row['executed_volume']) > 0:
                # Get trade details for this order
                cursor.execute(
                    '''SELECT trade_id, price, cost, fee, volume, time 
                    FROM trades WHERE api_key = ? AND order_id = ?''',
                    (api_key, row['order_id'])
                )
                trade_rows = cursor.fetchall()
                
                if trade_rows:
                    trade_data = {}
                    for trade_row in trade_rows:
                        trade_data[trade_row['trade_id']] = {
                            'price': trade_row['price'],
                            'cost': trade_row['cost'],
                            'fee': trade_row['fee'],
                            'vol': trade_row['volume'],
                            'time': trade_row['time']
                        }
                    order_data['trades'] = trade_data
            
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
        return jsonify({
            'error': ['EGeneral:Invalid arguments'],
            'result': {}
        }), 400
    
    # Validate order type
    if ordertype not in ['market', 'limit', 'stop-loss', 'take-profit', 'stop-loss-limit', 'take-profit-limit', 'settle-position']:
        return jsonify({
            'error': ['EGeneral:Invalid ordertype'],
            'result': {}
        }), 400
    
    # Validate order direction
    if type not in ['buy', 'sell']:
        return jsonify({
            'error': ['EGeneral:Invalid type'],
            'result': {}
        }), 400
    
    # Additional validation for limit orders
    if ordertype in ['limit', 'stop-loss-limit', 'take-profit-limit'] and not price:
        return jsonify({
            'error': ['EGeneral:Invalid arguments:price'],
            'result': {}
        }), 400
    
    db = g.db
    cursor = db.cursor()
    
    try:
        # Verify pair exists
        cursor.execute('SELECT pair_name FROM asset_pairs WHERE pair_name = ?', (pair,))
        pair_row = cursor.fetchone()
        if not pair_row:
            return jsonify({
                'error': ['EGeneral:Invalid arguments:pair'],
                'result': {}
            }), 400
        
        # Verify sufficient balance for buy or sell
        cursor.execute('SELECT pair_name, base, quote FROM asset_pairs WHERE pair_name = ?', (pair,))
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
            
            # Log balance information for debugging
            logger.info(f"Buy order - Asset: {quote_asset}, Balance: {balance}, Cost: {cost}")
            
            if cost > balance:
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
            
            logger.info(f"Limit order - Current price: {current_price}, Limit price: {limit_price}, Difference: {price_difference_pct}%")
            
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
            
            # Update balances
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
                
                # Update or insert quote asset balance
                cursor.execute('''
                INSERT INTO account_balances (api_key, asset, balance) 
                VALUES (?, ?, ?) 
                ON CONFLICT(api_key, asset) 
                DO UPDATE SET balance = CAST(balance AS DECIMAL) + ?
                ''', (api_key, quote_asset, str(cost), str(cost)))
                
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
                        '''SELECT trade_id, price, cost, fee, volume, time 
                        FROM trades WHERE api_key = ? AND order_id = ?''',
                        (api_key, row['order_id'])
                    )
                    trade_rows = cursor.fetchall()
                    
                    if trade_rows:
                        trade_data = {}
                        for trade_row in trade_rows:
                            trade_data[trade_row['trade_id']] = {
                                'price': trade_row['price'],
                                'cost': trade_row['cost'],
                                'fee': trade_row['fee'],
                                'vol': trade_row['volume'],
                                'time': trade_row['time']
                            }
                        order_data['trades'] = trade_data
            
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
                trade_data = {
                    'ordertxid': row['order_id'],
                    'pair': row['pair'],
                    'time': row['time'],
                    'type': row['type'],
                    'ordertype': 'market',  # We assume market orders for simplicity
                    'price': row['price'],
                    'cost': row['cost'],
                    'fee': row['fee'],
                    'vol': row['volume']
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
                trade_data = {
                    'ordertxid': row['order_id'],
                    'pair': row['pair'],
                    'time': row['time'],
                    'type': row['type'],
                    'ordertype': 'market',  # We assume market orders for simplicity
                    'price': row['price'],
                    'cost': row['cost'],
                    'fee': row['fee'],
                    'vol': row['volume']
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
                        'vol': volume
                    }
                    
                    logger.info(f"Created dummy trade {trade_id} for order {order_id}")
        
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
            trade_data = {
                'ordertxid': row['order_id'],
                'pair': row['pair'],
                'time': row['time'],
                'type': row['type'],
                'price': row['price'],
                'cost': row['cost'],
                'fee': row['fee'],
                'vol': row['volume']
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
        logger.info("Missing txid parameter")
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
            logger.info(f"Order not found - API Key: {api_key}, txid: {txid}")
            return jsonify({
                'error': ['EOrder:Unknown order'],
                'result': {}
            }), 400
        
        if order_row['status'] != 'open':
            logger.info(f"Order not open - status: {order_row['status']}")
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
        logger.info(f"Order successfully canceled - txid: {txid}")
        
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
    """Amend an existing order
    
    Endpoint implementation based on:
    https://docs.kraken.com/api/docs/rest-api/edit-order
    """
    api_key = request.headers.get('API-Key')
    
    # Required parameters
    txid = request.form.get('txid')
    
    if not txid:
        return jsonify({
            'error': ['EGeneral:Invalid arguments'],
            'result': {}
        }), 400
    
    # Optional parameters
    volume = request.form.get('volume')
    price = request.form.get('price')
    price2 = request.form.get('price2')
    
    if not volume and not price and not price2:
        return jsonify({
            'error': ['EGeneral:No parameters to edit'],
            'result': {}
        }), 400
    
    db = g.db
    cursor = db.cursor()
    
    try:
        # Check if the order exists and is open
        cursor.execute(
            'SELECT order_id, status, order_type, pair FROM orders WHERE api_key = ? AND order_id = ?',
            (api_key, txid)
        )
        
        order_row = cursor.fetchone()
        
        if not order_row:
            return jsonify({
                'error': ['EOrder:Unknown order'],
                'result': {}
            }), 400
        
        if order_row['status'] != 'open':
            return jsonify({
                'error': ['EOrder:Cannot edit closed order'],
                'result': {}
            }), 400
        
        # Market orders cannot be edited
        if order_row['order_type'] == 'market':
            return jsonify({
                'error': ['EOrder:Cannot edit market order'],
                'result': {}
            }), 400
        
        # Update order details
        update_fields = []
        update_values = []
        
        if volume:
            update_fields.append('volume = ?')
            update_values.append(volume)
            
        if price:
            update_fields.append('price = ?')
            update_values.append(price)
            
        if price2:
            update_fields.append('price2 = ?')
            update_values.append(price2)
        
        if update_fields:
            update_sql = f'UPDATE orders SET {", ".join(update_fields)} WHERE order_id = ?'
            cursor.execute(update_sql, update_values + [txid])
            
            db.commit()
        
        # Return the updated order description
        cursor.execute(
            'SELECT type, volume, pair, price, price2, order_type FROM orders WHERE order_id = ?',
            (txid,)
        )
        updated_order = cursor.fetchone()
        
        result = {
            'txid': [txid],
            'descr': {
                'order': f"{updated_order['type']} {updated_order['volume']} {updated_order['pair']} @ {updated_order['price'] if updated_order['price'] else 'market'} {updated_order['order_type']}"
            }
        }
        
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
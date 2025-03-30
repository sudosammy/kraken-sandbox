import sqlite3
import os
from flask import g, current_app
import json
import logging

logger = logging.getLogger(__name__)

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    return g.db

def init_db():
    """Initialize database tables if they don't exist"""
    db = get_db()
    
    # Create API credentials table
    db.execute('''
    CREATE TABLE IF NOT EXISTS api_credentials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT UNIQUE NOT NULL,
        api_secret TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create asset pairs table
    db.execute('''
    CREATE TABLE IF NOT EXISTS asset_pairs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pair_name TEXT UNIQUE NOT NULL,
        altname TEXT NOT NULL,
        wsname TEXT,
        base TEXT NOT NULL,
        quote TEXT NOT NULL,
        pair_decimals INTEGER,
        cost_decimals INTEGER,
        lot_decimals INTEGER,
        status TEXT DEFAULT 'online',
        data JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create account balances table
    db.execute('''
    CREATE TABLE IF NOT EXISTS account_balances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT NOT NULL,
        asset TEXT NOT NULL,
        balance TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(api_key, asset)
    )
    ''')
    
    # Create orders table
    db.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT NOT NULL,
        order_id TEXT UNIQUE NOT NULL,
        pair TEXT NOT NULL,
        type TEXT NOT NULL,
        order_type TEXT NOT NULL,
        price TEXT,
        price2 TEXT,
        volume TEXT NOT NULL,
        executed_volume TEXT DEFAULT '0',
        status TEXT DEFAULT 'open',
        opened_time INTEGER,
        closed_time INTEGER DEFAULT NULL,
        user_ref INTEGER,
        data JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create trades table
    db.execute('''
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT NOT NULL,
        trade_id TEXT UNIQUE NOT NULL,
        order_id TEXT NOT NULL,
        pair TEXT NOT NULL,
        type TEXT NOT NULL,
        price TEXT NOT NULL,
        cost TEXT NOT NULL,
        fee TEXT NOT NULL,
        volume TEXT NOT NULL,
        time INTEGER,
        data JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create assets table
    db.execute('''
    CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset TEXT UNIQUE NOT NULL,
        asset_name TEXT NOT NULL,
        decimals INTEGER DEFAULT 10,
        display_decimals INTEGER DEFAULT 5,
        status TEXT DEFAULT 'active',
        data JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Seed initial asset pairs if the table is empty
    cursor = db.cursor()
    cursor.execute('SELECT COUNT(*) FROM asset_pairs')
    if cursor.fetchone()[0] == 0:
        seed_asset_pairs(db)
    
    # Seed initial assets if the table is empty
    cursor.execute('SELECT COUNT(*) FROM assets')
    if cursor.fetchone()[0] == 0:
        seed_assets(db)
    
    # Account balances are seeded in auth.py when API credentials are generated
    
    db.commit()

def seed_asset_pairs(db):
    pairs = [
        {
            'pair_name': 'XXBTZUSD',
            'altname': 'XBTUSD',
            'wsname': 'XBT/USD',
            'base': 'XXBT',
            'quote': 'ZUSD',
            'pair_decimals': 1,
            'cost_decimals': 5,
            'lot_decimals': 8,
            'status': 'online',
            'data': json.dumps({
                'lot': 'unit',
                'lot_multiplier': 1,
                'leverage_buy': [2, 3, 4, 5],
                'leverage_sell': [2, 3, 4, 5],
                'fees': [[0, 0.26], [50000, 0.24], [100000, 0.22]],
                'fees_maker': [[0, 0.16], [50000, 0.14], [100000, 0.12]],
                'fee_volume_currency': 'ZUSD',
                'margin_call': 80,
                'margin_stop': 40,
                'ordermin': '0.0001',
                'costmin': '0.5',
                'tick_size': '0.1',
                'long_position_limit': 250,
                'short_position_limit': 200
            })
        },
        {
            'pair_name': 'XETHZUSD',
            'altname': 'ETHUSD',
            'wsname': 'ETH/USD',
            'base': 'XETH',
            'quote': 'ZUSD',
            'pair_decimals': 2,
            'cost_decimals': 6,
            'lot_decimals': 8,
            'status': 'online',
            'data': json.dumps({
                'lot': 'unit',
                'lot_multiplier': 1,
                'leverage_buy': [2, 3, 4, 5],
                'leverage_sell': [2, 3, 4, 5],
                'fees': [[0, 0.26], [50000, 0.24], [100000, 0.22]],
                'fees_maker': [[0, 0.16], [50000, 0.14], [100000, 0.12]],
                'fee_volume_currency': 'ZUSD',
                'margin_call': 80,
                'margin_stop': 40,
                'ordermin': '0.001',
                'costmin': '0.5',
                'tick_size': '0.01',
                'long_position_limit': 500,
                'short_position_limit': 300
            })
        },
        {
            'pair_name': 'XXBTZAUD',
            'altname': 'XBTAUD',
            'wsname': 'XBT/AUD',
            'base': 'XXBT',
            'quote': 'ZAUD',
            'pair_decimals': 1,
            'cost_decimals': 5,
            'lot_decimals': 8,
            'status': 'online',
            'data': json.dumps({
                'lot': 'unit',
                'lot_multiplier': 1,
                'leverage_buy': [2, 3, 4, 5],
                'leverage_sell': [2, 3, 4, 5],
                'fees': [[0, 0.26], [50000, 0.24], [100000, 0.22]],
                'fees_maker': [[0, 0.16], [50000, 0.14], [100000, 0.12]],
                'fee_volume_currency': 'ZUSD',
                'margin_call': 80,
                'margin_stop': 40,
                'ordermin': '0.0001',
                'costmin': '0.5',
                'tick_size': '0.1',
                'long_position_limit': 250,
                'short_position_limit': 200
            })
        },
        {
            'pair_name': 'XETHZAUD',
            'altname': 'ETHAUD',
            'wsname': 'ETH/AUD',
            'base': 'XETH',
            'quote': 'ZAUD',
            'pair_decimals': 2,
            'cost_decimals': 6,
            'lot_decimals': 8,
            'status': 'online',
            'data': json.dumps({
                'lot': 'unit',
                'lot_multiplier': 1,
                'leverage_buy': [2, 3, 4, 5],
                'leverage_sell': [2, 3, 4, 5],
                'fees': [[0, 0.26], [50000, 0.24], [100000, 0.22]],
                'fees_maker': [[0, 0.16], [50000, 0.14], [100000, 0.12]],
                'fee_volume_currency': 'ZUSD',
                'margin_call': 80,
                'margin_stop': 40,
                'ordermin': '0.001',
                'costmin': '0.5',
                'tick_size': '0.01',
                'long_position_limit': 500,
                'short_position_limit': 300
            })
        }
    ]
    
    for pair in pairs:
        db.execute('''
        INSERT INTO asset_pairs 
        (pair_name, altname, wsname, base, quote, pair_decimals, cost_decimals, lot_decimals, status, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            pair['pair_name'], 
            pair['altname'], 
            pair['wsname'], 
            pair['base'], 
            pair['quote'], 
            pair['pair_decimals'],
            pair['cost_decimals'],
            pair['lot_decimals'],
            pair['status'],
            pair['data']
        ))
    
    logger.info("Seeded asset pairs")
    
def seed_account_balances(db, api_key):
    balances = [
        ('XXBT', '100.0'),
        ('XETH', '100.0'),
        ('ZUSD', '1000000.0'),
        ('ZAUD', '1000000.0')
    ]
    
    for asset, balance in balances:
        db.execute('''
        INSERT INTO account_balances 
        (api_key, asset, balance)
        VALUES (?, ?, ?)
        ''', (api_key, asset, balance))
    
    # Commit changes to ensure they're saved to disk
    db.commit()
    
    # Verify balances were inserted
    cursor = db.cursor()
    cursor.execute('SELECT COUNT(*) FROM account_balances WHERE api_key = ?', (api_key,))
    count = cursor.fetchone()[0]
    logger.info(f"Seeded account balances with ample funds - verified {count} balance records")
    
    if count != len(balances):
        logger.error(f"Failed to seed all account balances! Expected {len(balances)}, but got {count}")
    
    return count > 0

def seed_assets(db):
    assets = [
        {
            'asset': 'XXBT',
            'asset_name': 'XBT',
            'decimals': 10,
            'display_decimals': 5,
            'status': 'active',
            'data': json.dumps({
                'collateral_value': 1.0,
                'withdraw_fee': '0.0005',
                'min_withdrawal': '0.0001'
            })
        },
        {
            'asset': 'XETH',
            'asset_name': 'ETH',
            'decimals': 10,
            'display_decimals': 5,
            'status': 'active',
            'data': json.dumps({
                'collateral_value': 0.8,
                'withdraw_fee': '0.005',
                'min_withdrawal': '0.005'
            })
        },
        {
            'asset': 'ZUSD',
            'asset_name': 'USD',
            'decimals': 4,
            'display_decimals': 2,
            'status': 'active',
            'data': json.dumps({
                'collateral_value': 1.0,
                'withdraw_fee': '2.5',
                'min_withdrawal': '5'
            })
        },
        {
            'asset': 'ZAUD',
            'asset_name': 'AUD',
            'decimals': 4,
            'display_decimals': 2,
            'status': 'active',
            'data': json.dumps({
                'collateral_value': 0.7,
                'withdraw_fee': '2.5',
                'min_withdrawal': '5'
            })
        }
    ]
    
    for asset in assets:
        db.execute('''
        INSERT INTO assets 
        (asset, asset_name, decimals, display_decimals, status, data)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            asset['asset'],
            asset['asset_name'],
            asset['decimals'],
            asset['display_decimals'], 
            asset['status'],
            asset['data']
        ))
    
    logger.info("Seeded assets") 
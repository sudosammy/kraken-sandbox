import sqlite3
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_account_balances():
    """Update account balances with high values"""
    
    # Path to database
    db_path = 'data/kraken_sandbox.db'
    
    if not os.path.exists(db_path):
        logger.error(f"Database file not found: {db_path}")
        return False
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # First check if there are any API keys
        cursor.execute('SELECT api_key FROM api_credentials')
        api_keys = cursor.fetchall()
        
        if not api_keys:
            logger.error("No API keys found in the database")
            return False
        
        # Update balances for each API key
        for row in api_keys:
            api_key = row['api_key']
            
            # Set high balances for all assets
            balances = [
                ('XXBT', '10.0'),      # 10 BTC
                ('XETH', '100.0'),     # 100 ETH
                ('ZUSD', '1000000.0'), # 1 million USD
                ('ZAUD', '1000000.0'), # 1 million AUD
                # Yield-bearing products (.B) - new balances in yield-bearing products
                ('XBT.B', '5.0'),     # Fixed: was XXBT.B
                ('ETH.B', '10.0'),     # Fixed: was XETH.B
                ('USD.B', '50000.0'),  # Fixed: was ZUSD.B
                # Opt-in rewards (.M) - similar to staked balances
                ('XBT.M', '2.5'),     # Fixed: was XXBT.M
                ('ETH.M', '3.2'),     # Fixed: was XETH.M
                # Kraken Rewards (.F) - automatically earning balances
                ('ETH.F', '20.1'),    # Fixed: was XETH.F
                ('XBT.F', '14.8')     # Fixed: was XXBT.F
            ]
            
            # Delete existing balances to avoid conflicts
            cursor.execute('DELETE FROM account_balances WHERE api_key = ?', (api_key,))
            
            # Insert new balances
            for asset, balance in balances:
                cursor.execute('''
                INSERT INTO account_balances 
                (api_key, asset, balance)
                VALUES (?, ?, ?)
                ''', (api_key, asset, balance))
                
            logger.info(f"Updated balances for API key: {api_key}")
        
        # Commit the changes
        conn.commit()
        logger.info("All account balances updated successfully")
        
        # Verify the updated balances
        cursor.execute('SELECT api_key, asset, balance FROM account_balances')
        updated_balances = cursor.fetchall()
        
        for row in updated_balances:
            logger.info(f"Updated balance: API Key: {row['api_key']}, Asset: {row['asset']}, Balance: {row['balance']}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error updating account balances: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    update_account_balances() 
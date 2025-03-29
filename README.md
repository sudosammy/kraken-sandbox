# Kraken Sandbox API

A local development environment that mimics the [Kraken Spot REST API](https://docs.kraken.com/api/docs/rest-api/add-order) for testing and development purposes.

### Why?
Kraken support regarding access to a Staging/UAT API:
> We currently provide a UAT environment which is used for testing, however, this is only available for the Business Pro account and third party service developers. If you are interested in this and not a third party service developer, then please generate a business pro account with Kraken and after generating an account we can further move to create an UAT environment for you.
> If you are a third party service developer, can you provide some details on which APIs and endpoints you will be using, details of the company, and the use case for the API.

Umm yeah, fuck that.

## Supported Endpoints

### Public Endpoints (All)
- `/0/public/Time` - Get server time
- `/0/public/Assets` - Get information about assets
- `/0/public/AssetPairs` - Get information about trading pairs
- `/0/public/Ticker` - Get current price information
- `/0/public/OHLC` - Get Open, High, Low, Close data
- `/0/public/Depth` - Get order book
- `/0/public/Trades` - Get recent trades
- `/0/public/Spread` - Get recent spread data
- `/0/public/SystemStatus` - Get system status

### Private Endpoints
- `/0/private/Balance` - Get account balances
- `/0/private/OpenOrders` - Get open orders
- `/0/private/AddOrder` - Place a market order
- `/0/private/ClosedOrders` - Get closed orders
- `/0/private/QueryTrades` - Get detailed information about specific trades
- `/0/private/TradesHistory` - Get trade history
- `/0/private/CancelOrder` - Cancel an open order
- `/0/private/EditOrder` - Amend an existing order

## Order Execution Behavior

The Kraken Sandbox API simulates realistic order execution behavior:

- **Market Orders**: Always execute immediately at the current market price.
- **Limit Orders**: 
  - Limit orders placed within 5% of the current market price are automatically executed.
  - Limit orders placed more than 5% away from the current market price remain open.
  - This behavior allows for testing both order execution and order management (cancellation, editing).

The 5% threshold simulates a reasonable price range for immediate execution, while orders outside this range require price movements before execution.

## Supported Trading Pairs

- BTC/USD (XXBTZUSD)
- ETH/USD (XETHZUSD)
- BTC/AUD (XXBTZAUD)
- ETH/AUD (XETHZAUD)

### Adding New Pairs

To add new trading pairs, update the `seed_asset_pairs` function in `database.py`.

## Getting Started

### Using Docker (Recommended)

1. Clone this repository:
   ```
   git clone https://github.com/sudosammy/kraken-sandbox.git
   cd kraken-sandbox
   ```

2. Create the docker network. This will expose the container at `kraken-sandbox:5555` to other containers on this network:
   ```
   docker network create kraken_network
   ```

3. Start the Docker container:
   ```
   docker compose up
   ```

4. The API will be available outside the container at http://localhost:5555 and API credentials will be printed to the console and are available at http://localhost:5555/admin. If you started the server with `docker compose up -d` you can also find the credentials via `docker compose logs kraken-sandbox`

### Manual Setup

1. Clone this repository:
   ```
   git clone https://github.com/sudosammy/kraken-sandbox.git
   cd kraken-sandbox
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Start the API server:
   ```
   python app.py
   ```

4. The API will be available at http://localhost:5555 and API credentials will be printed to the console & are available at http://localhost:5555/admin.

### Configuring Logging

The API's logging level can be configured using the `LOG_LEVEL` environment variable. Supported levels are:

- `DEBUG`: Detailed debug information
- `INFO`: Confirmation that things are working as expected (default)
- `WARNING`: Indication that something unexpected happened
- `ERROR`: An error occurred but the application can continue
- `CRITICAL`: A serious error that may prevent the application from continuing

### Making API Requests

If you want to access the API from another container, ensure you have created the `kraken_network` network and specify it via `--network` or an `external: true` network configuration in the other container's `docker-compose.yml`. Then the sandbox API will be available at `http://kraken-sandbox:5555`.

#### Public Endpoints

Public endpoints can be accessed directly via GET requests:

```
curl http://localhost:5555/0/public/Ticker?pair=XXBTZUSD
```

#### Private Endpoints

Private endpoints require API key authentication:

```
curl -X POST \
  -H "API-Key: YOUR_API_KEY" \
  -H "API-Sign: YOUR_API_SIGN" \
  -d "nonce=$(date +%s000)" \
  http://localhost:5555/0/private/Balance
```

## API Key Authentication

The API automatically generates an API key and secret when first started. These credentials will be printed to the console. All private API requests must include:

1. `API-Key` header with your API key
2. `API-Sign` header with a valid signature
3. `nonce` parameter in the request body

For testing purposes, the sandbox has simplified authentication - it only checks if the API key exists.

## Testing the API

A test script (`test_kraken_sandbox.sh`) is included to verify that all API endpoints are working correctly. The script tests both public and private endpoints, including order placement, cancellation, and editing.

To run the test script:

```bash
# After starting the API server
./test_kraken_sandbox.sh localhost:5555 your_api_key your_api_secret
```

The test script will:
1. Test all public endpoints
2. Test all private endpoints
3. Place various types of orders (market, limit)
4. Test order cancellation and editing
5. Verify trades and order history

Successful tests will be marked with a green check mark, while failures will show a red X with error details.

## Admin Dashboard

The Kraken Sandbox includes an admin dashboard that provides a user-friendly interface to view all data in the database, including:

- API Credentials
- Assets
- Asset Pairs
- Account Balances
- Orders
- Trades

To access the admin dashboard, navigate to: `http://localhost:5555/admin`. The dashboard provides a single-page application interface with tabs for each data category, allowing you to easily monitor the state of the sandbox environment.

![Kraken Sandbox Admin Dashboard](static/sandbox-sc.png)

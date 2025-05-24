#!/bin/bash

# Kraken Sandbox API Test Script
# This script tests all endpoints of the Kraken Sandbox API

# Check for required parameters
if [ $# -lt 3 ]; then
    echo "Usage: $0 <hostname> <api_key> <api_secret>"
    echo "Example: $0 localhost:5555 abcdef123456 XYZABC987654"
    exit 1
fi

HOSTNAME=$1
API_KEY=$2
API_SECRET=$3
BASE_URL="http://${HOSTNAME}"

# Text colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# First, fetch available trading pairs to use in tests
echo -e "${YELLOW}Fetching available trading pairs...${NC}"
pairs_response=$(curl -s "${BASE_URL}/0/public/AssetPairs")

# Get first valid pair for testing
TEST_PAIR=$(echo "$pairs_response" | grep -o '"result":{"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -z "$TEST_PAIR" ]; then
    echo -e "${RED}Failed to get valid trading pairs from API. Using default XXBTZUSD${NC}"
    TEST_PAIR="XXBTZUSD"
else
    echo -e "${GREEN}Using trading pair: ${TEST_PAIR}${NC}"
fi

# Function to test a public endpoint
test_public_endpoint() {
    local endpoint=$1
    local params=$2
    local description=$3
    
    echo -e "\n${YELLOW}Testing ${description} (${endpoint})${NC}"
    
    local url="${BASE_URL}/0/public/${endpoint}"
    if [ -n "$params" ]; then
        url="${url}?${params}"
    fi
    
    echo "GET ${url}"
    response=$(curl -s "${url}")
    
    # Check if response contains an error
    if echo "$response" | grep -q '"error":\[\]'; then
        echo -e "${GREEN}✓ Success${NC}"
    else
        echo -e "${RED}✗ Failed${NC}"
        echo "$response" | jq 2>/dev/null || echo "$response"
    fi
}

# Function to test a private endpoint
test_private_endpoint() {
    local endpoint=$1
    local params=$2
    local description=$3
    
    echo -e "\n${YELLOW}Testing ${description} (${endpoint})${NC}"
    
    local url="${BASE_URL}/0/private/${endpoint}"
    local nonce=$(date +%s000)
    
    local post_data="nonce=${nonce}"
    if [ -n "$params" ]; then
        post_data="${post_data}&${params}"
    fi
    
    # Create API-Sign header
    local urlpath="/0/private/${endpoint}"
    local message="${nonce}${post_data}"
    
    # Using OpenSSL for HMAC-SHA512
    # First base64 decode the API secret, then use it to sign the message
    local signature=$(echo -n "${urlpath}${post_data}" | 
                    openssl dgst -sha512 -hmac "${API_SECRET}" -binary | 
                    base64)
    
    echo "POST ${url}"
    response=$(curl -s -X POST "${url}" \
        -H "API-Key: ${API_KEY}" \
        -H "API-Sign: ${signature}" \
        -d "${post_data}")
    
    # Check if response contains an error
    if echo "$response" | grep -q '"error":\[\]'; then
        echo -e "${GREEN}✓ Success${NC}"
    else
        echo -e "${RED}✗ Failed${NC}"
        echo "$response" | jq 2>/dev/null || echo "$response"
    fi
}

# Test the root endpoint
echo -e "${YELLOW}Testing Root Endpoint${NC}"
echo "GET ${BASE_URL}/"
response=$(curl -s "${BASE_URL}/")
if echo "$response" | grep -q "Kraken Sandbox API is running"; then
    echo -e "${GREEN}✓ Success${NC}"
else
    echo -e "${RED}✗ Failed${NC}"
    echo "$response"
fi

echo -e "\n${YELLOW}=== PUBLIC API ENDPOINTS ===${NC}"
# Test public endpoints
test_public_endpoint "Time" "" "Server Time"
test_public_endpoint "Assets" "" "Assets"
test_public_endpoint "AssetPairs" "" "Asset Pairs"
test_public_endpoint "AssetPairs" "pair=${TEST_PAIR}" "Asset Pairs (with specific pair)"
test_public_endpoint "Ticker" "pair=${TEST_PAIR}" "Ticker"
test_public_endpoint "OHLC" "pair=${TEST_PAIR}&interval=1" "OHLC Data"
test_public_endpoint "Depth" "pair=${TEST_PAIR}&count=10" "Order Book"
test_public_endpoint "Trades" "pair=${TEST_PAIR}" "Recent Trades"
test_public_endpoint "Spread" "pair=${TEST_PAIR}" "Recent Spreads"
test_public_endpoint "SystemStatus" "" "System Status"

echo -e "\n${YELLOW}=== PRIVATE API ENDPOINTS ===${NC}"
# Test private endpoints
test_private_endpoint "Balance" "" "Account Balance"
test_private_endpoint "OpenOrders" "" "Open Orders"

# Get current market price for the test pair to calculate prices
echo -e "\n${YELLOW}Getting market price to calculate limit order prices${NC}"
market_price_response=$(curl -s "${BASE_URL}/0/public/Ticker?pair=${TEST_PAIR}")
market_price=$(echo $market_price_response | grep -o '"c":\["[^"]*"' | head -1 | cut -d'"' -f4)
echo "Current market price for ${TEST_PAIR}: $market_price"

# Ensure market price is valid, set defaults if not
if [[ ! "$market_price" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    echo -e "${YELLOW}Warning: Invalid market price format. Using default values.${NC}"
    market_price="0"  # This will trigger the fallback values below
fi

# Set prices for limit orders - using fixed values to avoid bc dependency
if [[ "$TEST_PAIR" == "XXBTZUSD" ]]; then
    # Default values for BTC/USD
    if [[ -z "$market_price" || "$market_price" == "0" ]]; then
        echo -e "${YELLOW}Using default BTC price${NC}"
        market_price="30000"
    fi
    
    # Near market (within 5%)
    near_market_buy_price=$(echo $market_price | awk '{print int($1 * 1.03)}')
    
    # Far from market (> 5%)
    far_from_market_buy_price=$(echo $market_price | awk '{print int($1 * 0.7)}')
    far_from_market_sell_price=$(echo $market_price | awk '{print int($1 * 1.5)}')
    
    # Fallback to hard-coded values if awk fails
    if [[ -z "$near_market_buy_price" || "$near_market_buy_price" == "0" ]]; then
        near_market_buy_price="31000"
        far_from_market_buy_price="20000"
        far_from_market_sell_price="50000"
    fi
elif [[ "$TEST_PAIR" == "XETHZUSD" || "$TEST_PAIR" == "ETHUSD" ]]; then
    # Default values for ETH/USD
    if [[ -z "$market_price" || "$market_price" == "0" ]]; then
        echo -e "${YELLOW}Using default ETH price${NC}"
        market_price="2000"
    fi
    
    # Near market (within 5%)
    near_market_buy_price=$(echo $market_price | awk '{print int($1 * 1.03)}')
    
    # Far from market (> 5%)
    far_from_market_buy_price=$(echo $market_price | awk '{print int($1 * 0.7)}')
    far_from_market_sell_price=$(echo $market_price | awk '{print int($1 * 1.5)}')
    
    # Fallback to hard-coded values if awk fails
    if [[ -z "$near_market_buy_price" || "$near_market_buy_price" == "0" ]]; then
        near_market_buy_price="2060"
        far_from_market_buy_price="1400"
        far_from_market_sell_price="3000"
    fi
else
    # Default values for other pairs
    if [[ -z "$market_price" || "$market_price" == "0" ]]; then
        echo -e "${YELLOW}Using default generic price${NC}"
        market_price="1000"
    fi
    
    # Near market (within 5%)
    near_market_buy_price=$(echo $market_price | awk '{print int($1 * 1.03)}')
    
    # Far from market (> 5%)
    far_from_market_buy_price=$(echo $market_price | awk '{print int($1 * 0.7)}')
    far_from_market_sell_price=$(echo $market_price | awk '{print int($1 * 1.5)}')
    
    # Fallback to hard-coded values if awk fails
    if [[ -z "$near_market_buy_price" || "$near_market_buy_price" == "0" ]]; then
        near_market_buy_price="1030"
        far_from_market_buy_price="700"
        far_from_market_sell_price="1500"
    fi
fi

echo "Using prices: Near market: $near_market_buy_price, Far below: $far_from_market_buy_price, Far above: $far_from_market_sell_price"

# First place far-from-market orders that will remain open, to ensure we have open orders for testing
echo -e "\n${YELLOW}Testing Place Far-from-Market Buy Limit Order (for cancellation)${NC}"
nonce=$(date +%s000)
post_data="nonce=${nonce}&pair=${TEST_PAIR}&type=buy&ordertype=limit&volume=0.001&price=${far_from_market_buy_price}"
cancel_order_response=$(curl -s -X POST "${BASE_URL}/0/private/AddOrder" \
    -H "API-Key: ${API_KEY}" \
    -H "API-Sign: $(echo -n "/0/private/AddOrder${post_data}" | openssl dgst -sha512 -hmac "${API_SECRET}" -binary | base64)" \
    -d "${post_data}")

# Print the full response for debugging
echo "Order creation response: $cancel_order_response"

# Extract order ID - try different methods to ensure we get it
if echo "$cancel_order_response" | grep -q '"error":\[\]'; then
    # First try the standard format with txid
    cancel_order_id=$(echo "$cancel_order_response" | grep -o '"txid":\[.*\]' | sed 's/.*\["//;s/"\].*//')
    # If that fails, try another approach
    if [ -z "$cancel_order_id" ]; then
        cancel_order_id=$(echo "$cancel_order_response" | grep -o '"txid":\[[^]]*\]' | grep -o '"[^"]*"' | tr -d '"')
    fi
    echo "Created order for cancellation with ID: $cancel_order_id"
else
    echo -e "${RED}Failed to create order for cancellation${NC}"
    echo "$cancel_order_response"
    cancel_order_id=""
fi

# Get open orders to verify the order was created
echo -e "\n${YELLOW}Verifying open orders after creating test orders${NC}"
nonce=$(date +%s000)
post_data="nonce=${nonce}"
open_orders_response=$(curl -s -X POST "${BASE_URL}/0/private/OpenOrders" \
    -H "API-Key: ${API_KEY}" \
    -H "API-Sign: $(echo -n "/0/private/OpenOrders${post_data}" | openssl dgst -sha512 -hmac "${API_SECRET}" -binary | base64)" \
    -d "${post_data}")

echo "Open orders: $open_orders_response"

# If we couldn't get the cancel_order_id from the response, try to get it from the OpenOrders response
if [ -z "$cancel_order_id" ] && echo "$open_orders_response" | grep -q '"open":'; then
    cancel_order_id=$(echo "$open_orders_response" | grep -o '"open":{"[^"]*"' | head -1 | cut -d'"' -f4)
    echo "Retrieved order ID from open orders: $cancel_order_id"
fi

# Place a second far-from-market order that will remain open for editing
echo -e "\n${YELLOW}Testing Place Far-from-Market Sell Limit Order (for editing)${NC}"
nonce=$(date +%s000)
post_data="nonce=${nonce}&pair=${TEST_PAIR}&type=sell&ordertype=limit&volume=0.002&price=${far_from_market_sell_price}"
edit_order_response=$(curl -s -X POST "${BASE_URL}/0/private/AddOrder" \
    -H "API-Key: ${API_KEY}" \
    -H "API-Sign: $(echo -n "/0/private/AddOrder${post_data}" | openssl dgst -sha512 -hmac "${API_SECRET}" -binary | base64)" \
    -d "${post_data}")

# Print the full response for debugging
echo "Order creation response: $edit_order_response"

# Extract order ID - try different methods to ensure we get it
if echo "$edit_order_response" | grep -q '"error":\[\]'; then
    # First try the standard format with txid
    edit_order_id=$(echo "$edit_order_response" | grep -o '"txid":\[.*\]' | sed 's/.*\["//;s/"\].*//')
    # If that fails, try another approach
    if [ -z "$edit_order_id" ]; then
        edit_order_id=$(echo "$edit_order_response" | grep -o '"txid":\[[^]]*\]' | grep -o '"[^"]*"' | tr -d '"')
    fi
    echo "Created order for editing with ID: $edit_order_id"
else
    echo -e "${RED}Failed to create order for editing${NC}"
    echo "$edit_order_response"
    edit_order_id=""
fi

# Place a third far-from-market order that will remain open for amending
echo -e "\n${YELLOW}Testing Place Far-from-Market Sell Limit Order (for amending)${NC}"
nonce=$(date +%s000)
post_data="nonce=${nonce}&pair=${TEST_PAIR}&type=sell&ordertype=limit&volume=0.003&price=${far_from_market_sell_price}&userref=12345"
amend_order_response=$(curl -s -X POST "${BASE_URL}/0/private/AddOrder" \
    -H "API-Key: ${API_KEY}" \
    -H "API-Sign: $(echo -n "/0/private/AddOrder${post_data}" | openssl dgst -sha512 -hmac "${API_SECRET}" -binary | base64)" \
    -d "${post_data}")

# Print the full response for debugging
echo "Order creation response: $amend_order_response"

# Extract order ID for amending - try different methods to ensure we get it
if echo "$amend_order_response" | grep -q '"error":\[\]'; then
    # First try the standard format with txid
    amend_order_id=$(echo "$amend_order_response" | grep -o '"txid":\[.*\]' | sed 's/.*\["//;s/"\].*//')
    # If that fails, try another approach
    if [ -z "$amend_order_id" ]; then
        amend_order_id=$(echo "$amend_order_response" | grep -o '"txid":\[[^]]*\]' | grep -o '"[^"]*"' | tr -d '"')
    fi
    echo "Created order for amending with ID: $amend_order_id"
else
    echo -e "${RED}Failed to create order for amending${NC}"
    echo "$amend_order_response"
    amend_order_id=""
fi

# If we couldn't get the edit_order_id from the response, try to get it from the OpenOrders response
if [ -z "$edit_order_id" ] && echo "$open_orders_response" | grep -q '"open":'; then
    # Get the first order that's not the cancel_order_id
    for order_id in $(echo "$open_orders_response" | grep -o '"open":{"[^"]*"' | cut -d'"' -f4); do
        if [ "$order_id" != "$cancel_order_id" ]; then
            edit_order_id="$order_id"
            break
        fi
    done
    echo "Retrieved order ID for editing from open orders: $edit_order_id"
fi

# Now place the other test orders that will execute
# Place a limit order that will remain open (more than 5% below market)
echo -e "\n${YELLOW}Testing Place Far-from-Market Buy Limit Order${NC}"
test_private_endpoint "AddOrder" "pair=${TEST_PAIR}&type=buy&ordertype=limit&volume=0.001&price=${far_from_market_buy_price}" "Place Far Limit Buy Order"

# Place a limit order that will remain open (more than 5% above market)
echo -e "\n${YELLOW}Testing Place Far-from-Market Sell Limit Order${NC}"
test_private_endpoint "AddOrder" "pair=${TEST_PAIR}&type=sell&ordertype=limit&volume=0.002&price=${far_from_market_sell_price}" "Place Far Limit Sell Order"

# Place a limit order that should execute (within 5% of market)
echo -e "\n${YELLOW}Testing Place Near-Market Limit Order${NC}"
test_private_endpoint "AddOrder" "pair=${TEST_PAIR}&type=buy&ordertype=limit&volume=0.001&price=${near_market_buy_price}" "Place Near-Market Limit Order"

# Place a market order that will be executed
echo -e "\n${YELLOW}Testing Place Market Order${NC}"
test_private_endpoint "AddOrder" "pair=${TEST_PAIR}&type=buy&ordertype=market&volume=0.001" "Place Market Order"

# Get open orders again to verify the orders were placed
test_private_endpoint "OpenOrders" "" "Verify Open Orders After Placement"

# Cancel the first order
echo -e "\n${YELLOW}Testing Cancel Order${NC}"
if [ -n "$cancel_order_id" ]; then
    echo "Cancelling order ID: $cancel_order_id"
    nonce=$(date +%s000)
    post_data="nonce=${nonce}&txid=${cancel_order_id}"
    cancel_response=$(curl -s -X POST "${BASE_URL}/0/private/CancelOrder" \
        -H "API-Key: ${API_KEY}" \
        -H "API-Sign: $(echo -n "/0/private/CancelOrder${post_data}" | openssl dgst -sha512 -hmac "${API_SECRET}" -binary | base64)" \
        -d "${post_data}")
    
    echo "Cancel response: $cancel_response"
    
    if echo "$cancel_response" | grep -q '"error":\[\]'; then
        echo -e "${GREEN}✓ Success${NC}"
    else
        echo -e "${RED}✗ Failed${NC}"
        echo "$cancel_response" | jq 2>/dev/null || echo "$cancel_response"
    fi
else
    echo -e "${RED}No order ID found to cancel${NC}"
fi

# Verify the order was cancelled
test_private_endpoint "ClosedOrders" "" "Verify Closed Orders After Cancellation"

# Edit the second order using the EditOrder endpoint - creates a new order
echo -e "\n${YELLOW}Testing Edit Order (cancels original and creates new)${NC}"
if [ -n "$edit_order_id" ]; then
    echo "Editing order ID: $edit_order_id"
    # Calculate a new price higher than the original or use a simple increment if awk fails
    new_price=$(awk "BEGIN {print $far_from_market_sell_price * 1.1}" 2>/dev/null || echo "$far_from_market_sell_price")
    
    nonce=$(date +%s000)
    post_data="nonce=${nonce}&txid=${edit_order_id}&pair=${TEST_PAIR}&price=${new_price}&volume=0.0015"
    edit_response=$(curl -s -X POST "${BASE_URL}/0/private/EditOrder" \
        -H "API-Key: ${API_KEY}" \
        -H "API-Sign: $(echo -n "/0/private/EditOrder${post_data}" | openssl dgst -sha512 -hmac "${API_SECRET}" -binary | base64)" \
        -d "${post_data}")
    
    echo "Edit response: $edit_response"
    
    if echo "$edit_response" | grep -q '"error":\[\]'; then
        echo -e "${GREEN}✓ Success${NC}"
        # Extract new order ID if possible
        new_order_id=$(echo "$edit_response" | grep -o '"txid":"[^"]*"' | cut -d'"' -f4)
        if [ -n "$new_order_id" ]; then
            echo "New order ID after edit: $new_order_id"
        else
            echo "Original order was edited, but couldn't extract new ID"
        fi
    else
        echo -e "${RED}✗ Failed${NC}"
        echo "$edit_response" | jq 2>/dev/null || echo "$edit_response"
    fi
else
    echo -e "${RED}No order ID found to edit${NC}"
fi

# Verify the order was edited (original canceled, new created)
test_private_endpoint "OpenOrders" "" "Verify Open Orders After Edit"
test_private_endpoint "ClosedOrders" "" "Verify Closed Orders After Edit"

# Test the AmendOrder endpoint - modifies existing order in-place
echo -e "\n${YELLOW}Testing Amend Order (modifies in-place)${NC}"
if [ -n "$amend_order_id" ]; then
    echo "Amending order ID: $amend_order_id"
    # Calculate a different price or volume for amending
    new_volume="0.0025"
    
    nonce=$(date +%s000)
    post_data="nonce=${nonce}&txid=${amend_order_id}&order_qty=${new_volume}"
    amend_response=$(curl -s -X POST "${BASE_URL}/0/private/AmendOrder" \
        -H "API-Key: ${API_KEY}" \
        -H "API-Sign: $(echo -n "/0/private/AmendOrder${post_data}" | openssl dgst -sha512 -hmac "${API_SECRET}" -binary | base64)" \
        -d "${post_data}")
    
    echo "Amend response: $amend_response"
    
    if echo "$amend_response" | grep -q '"error":\[\]'; then
        echo -e "${GREEN}✓ Success${NC}"
        # Extract amend_id if possible
        amend_id=$(echo "$amend_response" | grep -o '"amend_id":"[^"]*"' | cut -d'"' -f4)
        if [ -n "$amend_id" ]; then
            echo "Amend transaction ID: $amend_id"
        fi
    else
        echo -e "${RED}✗ Failed${NC}"
        echo "$amend_response" | jq 2>/dev/null || echo "$amend_response"
    fi
    
    # Test AmendOrder with client order ID (userref)
    echo -e "\n${YELLOW}Testing Amend Order using client order ID${NC}"
    nonce=$(date +%s000)
    new_limit_price=$(awk "BEGIN {print $far_from_market_sell_price * 1.05}" 2>/dev/null || echo "$far_from_market_sell_price")
    post_data="nonce=${nonce}&cl_ord_id=12345&limit_price=${new_limit_price}"
    amend_cl_response=$(curl -s -X POST "${BASE_URL}/0/private/AmendOrder" \
        -H "API-Key: ${API_KEY}" \
        -H "API-Sign: $(echo -n "/0/private/AmendOrder${post_data}" | openssl dgst -sha512 -hmac "${API_SECRET}" -binary | base64)" \
        -d "${post_data}")
    
    echo "Amend by client ID response: $amend_cl_response"
    
    if echo "$amend_cl_response" | grep -q '"error":\[\]'; then
        echo -e "${GREEN}✓ Success${NC}"
    else
        echo -e "${RED}✗ Failed${NC}"
        echo "$amend_cl_response" | jq 2>/dev/null || echo "$amend_cl_response"
    fi
else
    echo -e "${RED}No order ID found to amend${NC}"
fi

# Verify the order was amended in-place
test_private_endpoint "OpenOrders" "" "Verify Open Orders After Amend"

# Test query trades and trades history
test_private_endpoint "TradesHistory" "" "Trades History"

# Test query trades with the order ID
echo -e "\n${YELLOW}Testing Query Trades${NC}"
if [ -n "$edit_order_id" ]; then
    nonce=$(date +%s000)
    post_data="nonce=${nonce}&txid=${edit_order_id}"
    trades_response=$(curl -s -X POST "${BASE_URL}/0/private/QueryTrades" \
        -H "API-Key: ${API_KEY}" \
        -H "API-Sign: $(echo -n "/0/private/QueryTrades${post_data}" | openssl dgst -sha512 -hmac "${API_SECRET}" -binary | base64)" \
        -d "${post_data}")
    
    echo "QueryTrades response: $trades_response"
    
    if echo "$trades_response" | grep -q '"error":\[\]'; then
        echo -e "${GREEN}✓ Success${NC}"
    else
        echo -e "${RED}✗ Failed${NC}"
        echo "$trades_response" | jq 2>/dev/null || echo "$trades_response"
    fi
else
    echo -e "${RED}No order ID available for querying trades${NC}"
fi

echo -e "\n${YELLOW}=== TEST SUMMARY ===${NC}"
echo "All tests completed." 
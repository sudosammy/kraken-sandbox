// Initialize DataTables instances
let credentialsTable, assetsTable, pairsTable, balancesTable, ordersTable, tradesTable;

// Initialize the application when DOM is fully loaded
document.addEventListener('DOMContentLoaded', function() {
    // Setup tab navigation
    setupTabNavigation();
    
    // Initialize all tables with default settings
    initializeDataTables();
    
    // Load data for the initial tab
    loadApiCredentials();
});

// Setup tab navigation functionality
function setupTabNavigation() {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Remove active class from all links
            document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
            
            // Add active class to clicked link
            this.classList.add('active');
            
            // Hide all tabs
            document.querySelectorAll('.tab-pane').forEach(tab => {
                tab.classList.remove('show', 'active');
            });
            
            // Show the corresponding tab
            const tabId = this.getAttribute('href').substring(1);
            const tabPane = document.getElementById(tabId);
            if (tabPane) {
                tabPane.classList.add('show', 'active');
                
                // Load data based on the selected tab
                switch(tabId) {
                    case 'api-credentials':
                        loadApiCredentials();
                        break;
                    case 'assets':
                        loadAssets();
                        break;
                    case 'asset-pairs':
                        loadAssetPairs();
                        break;
                    case 'account-balances':
                        loadAccountBalances();
                        break;
                    case 'orders':
                        loadOrders();
                        break;
                    case 'trades':
                        loadTrades();
                        break;
                }
            }
        });
    });
}

// Initialize DataTables with common configurations
function initializeDataTables() {
    const commonConfig = {
        responsive: true,
        pageLength: 10,
        lengthMenu: [[10, 25, 50, -1], [10, 25, 50, "All"]],
        dom: '<"top"lf>rt<"bottom"ip><"clear">',
        language: {
            search: "_INPUT_",
            searchPlaceholder: "Search records"
        },
        order: [[0, 'desc']] // Order by first column (ID) in descending order
    };
    
    // Initialize each datatable with empty data
    credentialsTable = $('#credentials-table').DataTable({
        ...commonConfig,
        columns: [
            { data: 'id' },
            { data: 'api_key' },
            { data: 'api_secret' },
            { data: 'created_at', render: formatDateTime }
        ]
    });
    
    assetsTable = $('#assets-table').DataTable({
        ...commonConfig,
        columns: [
            { data: 'id' },
            { data: 'asset' },
            { data: 'asset_name' },
            { data: 'decimals' },
            { data: 'display_decimals' },
            { data: 'status' },
            { data: 'created_at', render: formatDateTime }
        ]
    });
    
    pairsTable = $('#pairs-table').DataTable({
        ...commonConfig,
        columns: [
            { data: 'id' },
            { data: 'pair_name' },
            { data: 'altname' },
            { data: 'wsname', defaultContent: '-' },
            { data: 'base' },
            { data: 'quote' },
            { data: 'status' }
        ]
    });
    
    balancesTable = $('#balances-table').DataTable({
        ...commonConfig,
        columns: [
            { data: 'id' },
            { data: 'api_key' },
            { data: 'asset' },
            { data: 'balance' },
            { data: 'updated_at', render: formatDateTime }
        ]
    });
    
    ordersTable = $('#orders-table').DataTable({
        ...commonConfig,
        columns: [
            { data: 'id' },
            { data: 'order_id' },
            { data: 'api_key' },
            { data: 'pair' },
            { data: 'type' },
            { data: 'order_type' },
            { data: 'price', defaultContent: '-' },
            { data: 'volume' },
            { data: 'status' }
        ]
    });
    
    tradesTable = $('#trades-table').DataTable({
        ...commonConfig,
        columns: [
            { data: 'id' },
            { data: 'trade_id' },
            { data: 'order_id' },
            { data: 'api_key' },
            { data: 'pair' },
            { data: 'type' },
            { data: 'price' },
            { data: 'volume' }
        ]
    });
}

// Load API credentials from backend
function loadApiCredentials() {
    fetch('/admin/api/credentials')
        .then(response => response.json())
        .then(data => {
            // Clear and reload the table
            credentialsTable.clear();
            credentialsTable.rows.add(data).draw();
        })
        .catch(error => {
            console.error('Error loading API credentials:', error);
            showErrorMessage('Failed to load API credentials.');
        });
}

// Load assets from backend
function loadAssets() {
    fetch('/admin/api/assets')
        .then(response => response.json())
        .then(data => {
            // Clear and reload the table
            assetsTable.clear();
            assetsTable.rows.add(data).draw();
        })
        .catch(error => {
            console.error('Error loading assets:', error);
            showErrorMessage('Failed to load assets.');
        });
}

// Load asset pairs from backend
function loadAssetPairs() {
    fetch('/admin/api/asset_pairs')
        .then(response => response.json())
        .then(data => {
            // Clear and reload the table
            pairsTable.clear();
            pairsTable.rows.add(data).draw();
        })
        .catch(error => {
            console.error('Error loading asset pairs:', error);
            showErrorMessage('Failed to load asset pairs.');
        });
}

// Load account balances from backend
function loadAccountBalances() {
    fetch('/admin/api/account_balances')
        .then(response => response.json())
        .then(data => {
            // Clear and reload the table
            balancesTable.clear();
            balancesTable.rows.add(data).draw();
        })
        .catch(error => {
            console.error('Error loading account balances:', error);
            showErrorMessage('Failed to load account balances.');
        });
}

// Load orders from backend
function loadOrders() {
    fetch('/admin/api/orders')
        .then(response => response.json())
        .then(data => {
            // Clear and reload the table
            ordersTable.clear();
            ordersTable.rows.add(data).draw();
        })
        .catch(error => {
            console.error('Error loading orders:', error);
            showErrorMessage('Failed to load orders.');
        });
}

// Load trades from backend
function loadTrades() {
    fetch('/admin/api/trades')
        .then(response => response.json())
        .then(data => {
            // Clear and reload the table
            tradesTable.clear();
            tradesTable.rows.add(data).draw();
        })
        .catch(error => {
            console.error('Error loading trades:', error);
            showErrorMessage('Failed to load trades.');
        });
}

// Helper function to format date and time
function formatDateTime(dateTimeStr) {
    if (!dateTimeStr) return '-';
    
    try {
        const date = new Date(dateTimeStr);
        return date.toLocaleString();
    } catch (e) {
        return dateTimeStr;
    }
}

// Helper function to show error messages
function showErrorMessage(message) {
    // You can implement a toast or other notification here
    console.error(message);
    
    // For now, just show an alert
    alert(message);
} 
"""
Analytics & Reporting Endpoints
KPI dashboards, business reports, and data analytics
"""

from flask import Blueprint, request, jsonify, make_response
from datetime import datetime, timezone, timedelta
from utils.auth_decorators import token_required, role_required
from utils.database import get_db_manager, execute_query, paginate_query

# Initialize blueprint
analytics_bp = Blueprint('analytics', __name__)

# Import analytics services with error handling
try:
    from analytics.kpi_system import KPISystem, ReportExporter
    from models.database_models import DatabaseUtils
    analytics_services_available = True
    
    kpi_system = KPISystem()
    report_exporter = ReportExporter()
    
except ImportError as e:
    print(f"Warning: Analytics services not available: {e}")
    analytics_services_available = False
    
    # Create fallback classes
    class KPISystem:
        def generate_dashboard_data(self, data):
            return {"message": "Analytics service not available"}
        
        def generate_report(self, report_type, data, date_range=None):
            return {"message": "Report generation not available"}
    
    class ReportExporter:
        def export_to_csv(self, data, filename):
            return "CSV export not available"
        
        def export_to_json(self, data):
            return {"message": "JSON export not available"}
    
    class DatabaseUtils:
        @staticmethod
        def get_customer_metrics(customer_id, transactions, policies):
            return {}
    
    kpi_system = KPISystem()
    report_exporter = ReportExporter()

@analytics_bp.route('/health')
@token_required
@role_required('wholesale_reseller')
def analytics_health():
    """Analytics service health check"""
    return jsonify({
        'service': 'Analytics & Reporting API',
        'status': 'healthy' if analytics_services_available else 'degraded',
        'analytics_services_available': analytics_services_available,
        'features': {
            'dashboard_data': analytics_services_available,
            'report_generation': analytics_services_available,
            'data_export': analytics_services_available,
            'kpi_calculations': analytics_services_available,
            'real_time_metrics': False
        },
        'timestamp': datetime.now(timezone.utc).isoformat() + "Z"
    })

@analytics_bp.route('/dashboard', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def get_dashboard():
    """Get analytics dashboard data"""
    try:
        user_id = request.current_user.get('user_id')
        user_role = request.current_user.get('role')
        date_range = request.args.get('date_range', '30')  # days
        
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=int(date_range))
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get transactions data
            transactions_result = execute_query('''
                SELECT 
                    COUNT(*) as total_transactions,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_transactions,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_transactions,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END), 0) as total_revenue,
                    COALESCE(AVG(CASE WHEN status = 'completed' THEN amount ELSE NULL END), 0) as avg_transaction_amount
                FROM transactions 
                WHERE created_at >= %s AND created_at <= %s
            ''', (start_date, end_date), 'one')
            
            # Get daily revenue trend
            daily_revenue_result = execute_query('''
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as transaction_count,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END), 0) as daily_revenue
                FROM transactions 
                WHERE created_at >= %s AND created_at <= %s
                GROUP BY DATE(created_at)
                ORDER BY date
            ''', (start_date, end_date))
            
            # Get product performance
            product_performance_result = execute_query('''
                SELECT 
                    metadata->>'product_type' as product_type,
                    COUNT(*) as quote_count,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as conversion_count,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END), 0) as revenue
                FROM transactions 
                WHERE created_at >= %s AND created_at <= %s
                AND metadata->>'product_type' IS NOT NULL
                GROUP BY metadata->>'product_type'
                ORDER BY revenue DESC
            ''', (start_date, end_date))
            
            # Build dashboard data
            dashboard_data = {
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'days': int(date_range)
                },
                'overview': {},
                'trends': {
                    'daily_revenue': [],
                    'conversion_rate': 0
                },
                'products': []
            }
            
            # Process overview metrics
            if transactions_result['success'] and transactions_result['data']:
                txn_data = transactions_result['data']
                total_txns = txn_data['total_transactions'] or 0
                completed_txns = txn_data['completed_transactions'] or 0
                
                dashboard_data['overview'] = {
                    'total_transactions': total_txns,
                    'completed_transactions': completed_txns,
                    'failed_transactions': txn_data['failed_transactions'] or 0,
                    'total_revenue': float(txn_data['total_revenue'] or 0),
                    'avg_transaction_amount': float(txn_data['avg_transaction_amount'] or 0),
                    'conversion_rate': round((completed_txns / total_txns * 100), 2) if total_txns > 0 else 0
                }
            
            # Process daily trends
            if daily_revenue_result['success'] and daily_revenue_result['data']:
                for row in daily_revenue_result['data']:
                    dashboard_data['trends']['daily_revenue'].append({
                        'date': row['date'].isoformat(),
                        'transaction_count': row['transaction_count'],
                        'revenue': float(row['daily_revenue'])
                    })
            
            # Process product performance
            if product_performance_result['success'] and product_performance_result['data']:
                for row in product_performance_result['data']:
                    conversion_rate = 0
                    if row['quote_count'] > 0:
                        conversion_rate = round((row['conversion_count'] / row['quote_count'] * 100), 2)
                    
                    dashboard_data['products'].append({
                        'product_type': row['product_type'],
                        'quote_count': row['quote_count'],
                        'conversion_count': row['conversion_count'],
                        'conversion_rate': conversion_rate,
                        'revenue': float(row['revenue'])
                    })
            
            return jsonify(dashboard_data)
        
        else:
            # Fallback analytics for when database is not available
            fallback_data = {
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'days': int(date_range)
                },
                'overview': {
                    'total_transactions': 0,
                    'completed_transactions': 0,
                    'failed_transactions': 0,
                    'total_revenue': 0.0,
                    'avg_transaction_amount': 0.0,
                    'conversion_rate': 0.0
                },
                'trends': {'daily_revenue': []},
                'products': [],
                'message': 'Database not available - showing placeholder data'
            }
            
            return jsonify(fallback_data)

    except Exception as e:
        return jsonify(f'Failed to generate dashboard: {str(e)}'), 500

@analytics_bp.route('/customer-dashboard', methods=['GET'])
@token_required
@role_required('customer')
def get_customer_dashboard():
    """Customer-specific dashboard with limited data"""
    try:
        customer_user_id = request.current_user.get('user_id')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get customer's own data
            customer_result = execute_query('''
                SELECT c.id as customer_id, c.customer_id as customer_ref
                FROM customers c
                WHERE c.user_id = %s
            ''', (customer_user_id,), 'one')
            
            if customer_result['success'] and customer_result['data']:
                customer_ref = customer_result['data']['customer_ref']
                
                # Get customer transactions
                transactions_result = execute_query('''
                    SELECT 
                        COUNT(*) as total_transactions,
                        COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_transactions,
                        COALESCE(SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END), 0) as total_spent
                    FROM transactions 
                    WHERE customer_id = %s
                ''', (customer_ref,), 'one')
                
                # Get active protection plans
                plans_result = execute_query('''
                    SELECT 
                        COUNT(*) as total_plans,
                        COUNT(CASE WHEN status = 'active' THEN 1 END) as active_plans
                    FROM protection_plans 
                    WHERE customer_email = (SELECT email FROM users WHERE id = %s)
                ''', (customer_user_id,), 'one')
                
                customer_metrics = {
                    'transactions': {
                        'total': transactions_result['data']['total_transactions'] if transactions_result['success'] else 0,
                        'completed': transactions_result['data']['completed_transactions'] if transactions_result['success'] else 0,
                        'total_spent': float(transactions_result['data']['total_spent']) if transactions_result['success'] else 0.0
                    },
                    'protection_plans': {
                        'total': plans_result['data']['total_plans'] if plans_result['success'] else 0,
                        'active': plans_result['data']['active_plans'] if plans_result['success'] else 0
                    }
                }
                
                return jsonify(customer_metrics)
            else:
                return jsonify('Customer profile not found'), 404
        else:
            # Fallback customer metrics
            return jsonify({
                'transactions': {
                    'total': 0,
                    'completed': 0,
                    'total_spent': 0.0
                },
                'protection_plans': {
                    'total': 0,
                    'active': 0
                },
                'message': 'Database not available - showing placeholder data'
            })
            
    except Exception as e:
        return jsonify(f'Failed to generate customer dashboard: {str(e)}'), 500

@analytics_bp.route('/reports/<report_type>', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def generate_report(report_type):
    """Generate specific business report"""
    try:
        # Get date range from query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        export_format = request.args.get('format', 'json')
        
        # Set default date range if not provided
        if not end_date:
            end_date = datetime.now(timezone.utc)
        else:
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        
        if not start_date:
            start_date = end_date - timedelta(days=30)
        else:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        
        valid_report_types = [
            'sales_summary', 'product_performance', 'customer_analysis',
            'conversion_rates', 'revenue_trends', 'transaction_details'
        ]
        
        if report_type not in valid_report_types:
            return jsonify(f'Invalid report type. Must be one of: {", ".join(valid_report_types)}'), 400
        
        db_manager = get_db_manager()
        
        if not db_manager.available:
            return jsonify('Database not available for report generation'), 503
        
        report_data = {
            'report_type': report_type,
            'date_range': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'generated_at': datetime.now(timezone.utc).isoformat() + 'Z',
            'data': {}
        }
        
        if report_type == 'sales_summary':
            # Sales summary report
            result = execute_query('''
                SELECT 
                    COUNT(*) as total_quotes,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_sales,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END), 0) as total_revenue,
                    COALESCE(AVG(CASE WHEN status = 'completed' THEN amount ELSE NULL END), 0) as avg_sale_amount,
                    COUNT(DISTINCT customer_id) as unique_customers
                FROM transactions 
                WHERE created_at >= %s AND created_at <= %s
            ''', (start_date, end_date), 'one')
            
            if result['success']:
                report_data['data'] = dict(result['data'])
                # Convert Decimal to float for JSON serialization
                for key, value in report_data['data'].items():
                    if isinstance(value, (int, float)) and str(value).replace('.', '').isdigit():
                        report_data['data'][key] = float(value)
        
        elif report_type == 'product_performance':
            # Product performance report
            result = execute_query('''
                SELECT 
                    COALESCE(metadata->>'product_type', 'unknown') as product_type,
                    COUNT(*) as total_quotes,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as conversions,
                    ROUND((COUNT(CASE WHEN status = 'completed' THEN 1 END) * 100.0 / COUNT(*)), 2) as conversion_rate,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END), 0) as revenue,
                    COALESCE(AVG(CASE WHEN status = 'completed' THEN amount ELSE NULL END), 0) as avg_revenue_per_sale
                FROM transactions 
                WHERE created_at >= %s AND created_at <= %s
                GROUP BY metadata->>'product_type'
                ORDER BY revenue DESC
            ''', (start_date, end_date))
            
            if result['success']:
                products = []
                for row in result['data']:
                    product = dict(row)
                    # Convert Decimal to float
                    for key, value in product.items():
                        if isinstance(value, (int, float)) and str(value).replace('.', '').replace('-', '').isdigit():
                            product[key] = float(value)
                    products.append(product)
                report_data['data'] = {'products': products}
        
        elif report_type == 'customer_analysis':
            # Customer analysis report
            result = execute_query('''
                SELECT 
                    customer_id,
                    COUNT(*) as transaction_count,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END), 0) as total_spent,
                    COALESCE(AVG(CASE WHEN status = 'completed' THEN amount ELSE NULL END), 0) as avg_transaction,
                    MIN(created_at) as first_transaction,
                    MAX(created_at) as last_transaction
                FROM transactions 
                WHERE created_at >= %s AND created_at <= %s
                AND customer_id IS NOT NULL
                GROUP BY customer_id
                ORDER BY total_spent DESC
                LIMIT 50
            ''', (start_date, end_date))
            
            if result['success']:
                customers = []
                for row in result['data']:
                    customer = dict(row)
                    customer['total_spent'] = float(customer['total_spent'])
                    customer['avg_transaction'] = float(customer['avg_transaction'])
                    customer['first_transaction'] = customer['first_transaction'].isoformat() if customer['first_transaction'] else None
                    customer['last_transaction'] = customer['last_transaction'].isoformat() if customer['last_transaction'] else None
                    customers.append(customer)
                report_data['data'] = {'customers': customers}
        
        elif report_type == 'conversion_rates':
            # Conversion rates by time period
            result = execute_query('''
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as total_quotes,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as conversions,
                    ROUND((COUNT(CASE WHEN status = 'completed' THEN 1 END) * 100.0 / COUNT(*)), 2) as conversion_rate
                FROM transactions 
                WHERE created_at >= %s AND created_at <= %s
                GROUP BY DATE(created_at)
                ORDER BY date
            ''', (start_date, end_date))
            
            if result['success']:
                daily_conversions = []
                for row in result['data']:
                    day_data = dict(row)
                    day_data['date'] = day_data['date'].isoformat()
                    day_data['conversion_rate'] = float(day_data['conversion_rate'])
                    daily_conversions.append(day_data)
                report_data['data'] = {'daily_conversions': daily_conversions}
        
        elif report_type == 'revenue_trends':
            # Revenue trends over time
            result = execute_query('''
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as transaction_count,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END), 0) as daily_revenue,
                    COALESCE(AVG(CASE WHEN status = 'completed' THEN amount ELSE NULL END), 0) as avg_transaction_amount
                FROM transactions 
                WHERE created_at >= %s AND created_at <= %s
                GROUP BY DATE(created_at)
                ORDER BY date
            ''', (start_date, end_date))
            
            if result['success']:
                revenue_trends = []
                for row in result['data']:
                    trend_data = dict(row)
                    trend_data['date'] = trend_data['date'].isoformat()
                    trend_data['daily_revenue'] = float(trend_data['daily_revenue'])
                    trend_data['avg_transaction_amount'] = float(trend_data['avg_transaction_amount'])
                    revenue_trends.append(trend_data)
                report_data['data'] = {'revenue_trends': revenue_trends}
        
        elif report_type == 'transaction_details':
            # Detailed transaction report
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 100, type=int)
            
            base_query = '''
                SELECT 
                    t.transaction_number,
                    t.customer_id,
                    t.amount,
                    t.currency,
                    t.status,
                    t.type,
                    t.created_at,
                    t.processed_at,
                    t.metadata->>'product_type' as product_type,
                    c.email as customer_email
                FROM transactions t
                LEFT JOIN customers c ON t.customer_id = c.customer_id
                WHERE t.created_at >= %s AND t.created_at <= %s
                ORDER BY t.created_at DESC
            '''
            
            paginated_result = paginate_query(base_query, (start_date, end_date), page, per_page)
            
            if paginated_result['success']:
                transactions = []
                for row in paginated_result['data']:
                    txn = dict(row)
                    txn['amount'] = float(txn['amount'])
                    txn['created_at'] = txn['created_at'].isoformat() if txn['created_at'] else None
                    txn['processed_at'] = txn['processed_at'].isoformat() if txn['processed_at'] else None
                    transactions.append(txn)
                
                report_data['data'] = {
                    'transactions': transactions,
                    'pagination': paginated_result['pagination']
                }
        
        # Handle export format
        if export_format == 'csv':
            return export_report_as_csv(report_data, report_type)
        else:
            return jsonify(report_data)

    except Exception as e:
        return jsonify(f'Failed to generate report: {str(e)}'), 500

def export_report_as_csv(report_data, report_type):
    """Export report data as CSV"""
    try:
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header based on report type
        if report_type == 'sales_summary':
            writer.writerow(['Metric', 'Value'])
            for key, value in report_data['data'].items():
                writer.writerow([key.replace('_', ' ').title(), value])
        
        elif report_type == 'product_performance':
            writer.writerow(['Product Type', 'Total Quotes', 'Conversions', 'Conversion Rate %', 'Revenue', 'Avg Revenue Per Sale'])
            for product in report_data['data']['products']:
                writer.writerow([
                    product['product_type'],
                    product['total_quotes'],
                    product['conversions'],
                    product['conversion_rate'],
                    product['revenue'],
                    product['avg_revenue_per_sale']
                ])
        
        elif report_type == 'customer_analysis':
            writer.writerow(['Customer ID', 'Transaction Count', 'Total Spent', 'Avg Transaction', 'First Transaction', 'Last Transaction'])
            for customer in report_data['data']['customers']:
                writer.writerow([
                    customer['customer_id'],
                    customer['transaction_count'],
                    customer['total_spent'],
                    customer['avg_transaction'],
                    customer['first_transaction'],
                    customer['last_transaction']
                ])
        
        elif report_type == 'transaction_details':
            writer.writerow(['Transaction Number', 'Customer ID', 'Customer Email', 'Amount', 'Currency', 'Status', 'Type', 'Product Type', 'Created At', 'Processed At'])
            for txn in report_data['data']['transactions']:
                writer.writerow([
                    txn['transaction_number'],
                    txn['customer_id'],
                    txn['customer_email'],
                    txn['amount'],
                    txn['currency'],
                    txn['status'],
                    txn['type'],
                    txn['product_type'],
                    txn['created_at'],
                    txn['processed_at']
                ])
        
        else:
            # Generic CSV export
            writer.writerow(['Report Type', 'Generated At'])
            writer.writerow([report_type, report_data['generated_at']])
            writer.writerow([])
            writer.writerow(['Data'])
            writer.writerow([str(report_data['data'])])
        
        csv_content = output.getvalue()
        output.close()
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename={report_type}_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        return response
        
    except Exception as e:
        return jsonify(f'CSV export failed: {str(e)}'), 500

@analytics_bp.route('/reports/<report_type>/export', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def export_report(report_type):
    """Export report in specified format"""
    try:
        export_format = request.args.get('format', 'json')
        
        if export_format == 'csv':
            # Redirect to the CSV export functionality in generate_report
            return generate_report(report_type)
        elif export_format == 'json':
            # Generate and return JSON report
            return generate_report(report_type)
        else:
            return jsonify('Unsupported export format. Use csv or json'), 400

    except Exception as e:
        return jsonify(f'Failed to export report: {str(e)}'), 500

@analytics_bp.route('/metrics/real-time', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def get_real_time_metrics():
    """Get real-time metrics for live dashboard"""
    try:
        db_manager = get_db_manager()
        
        if not db_manager.available:
            return jsonify('Database not available for real-time metrics'), 503
        
        # Get metrics for the last 24 hours
        last_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        
        # Recent transactions
        recent_transactions = execute_query('''
            SELECT COUNT(*) as count
            FROM transactions 
            WHERE created_at >= %s
        ''', (last_24h,), 'one')
        
        # Recent revenue
        recent_revenue = execute_query('''
            SELECT COALESCE(SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END), 0) as revenue
            FROM transactions 
            WHERE created_at >= %s
        ''', (last_24h,), 'one')
        
        # Active sessions (would require session tracking in production)
        active_sessions = 0  # Placeholder
        
        # Recent quotes by hour
        hourly_quotes = execute_query('''
            SELECT 
                EXTRACT(hour from created_at) as hour,
                COUNT(*) as quote_count
            FROM transactions 
            WHERE created_at >= %s
            GROUP BY EXTRACT(hour from created_at)
            ORDER BY hour
        ''', (last_24h,))
        
        real_time_metrics = {
            'last_24_hours': {
                'transactions': recent_transactions['data']['count'] if recent_transactions['success'] else 0,
                'revenue': float(recent_revenue['data']['revenue']) if recent_revenue['success'] else 0.0,
                'active_sessions': active_sessions
            },
            'hourly_distribution': []
        }
        
        if hourly_quotes['success']:
            for row in hourly_quotes['data']:
                real_time_metrics['hourly_distribution'].append({
                    'hour': int(row['hour']),
                    'quote_count': row['quote_count']
                })
        
        real_time_metrics['updated_at'] = datetime.now(timezone.utc).isoformat() + 'Z'
        
        return jsonify(real_time_metrics)

    except Exception as e:
        return jsonify(f'Failed to get real-time metrics: {str(e)}'), 500

@analytics_bp.route('/kpi-summary', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def get_kpi_summary():
    """Get KPI summary for executive dashboard"""
    try:
        date_range = request.args.get('period', '30')  # days
        compare_previous = request.args.get('compare', 'true').lower() == 'true'
        
        # Current period
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=int(date_range))
        
        # Previous period for comparison
        prev_end_date = start_date
        prev_start_date = prev_end_date - timedelta(days=int(date_range))
        
        db_manager = get_db_manager()
        
        if not db_manager.available:
            return jsonify('Database not available for KPI calculation'), 503
        
        # Current period KPIs
        current_kpis = execute_query('''
            SELECT 
                COUNT(*) as total_quotes,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as conversions,
                COALESCE(SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END), 0) as revenue,
                COUNT(DISTINCT customer_id) as unique_customers,
                COALESCE(AVG(CASE WHEN status = 'completed' THEN amount ELSE NULL END), 0) as avg_order_value
            FROM transactions 
            WHERE created_at >= %s AND created_at <= %s
        ''', (start_date, end_date), 'one')
        
        kpi_summary = {
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'days': int(date_range)
            },
            'kpis': {}
        }
        
        if current_kpis['success'] and current_kpis['data']:
            current_data = current_kpis['data']
            conversion_rate = (current_data['conversions'] / current_data['total_quotes'] * 100) if current_data['total_quotes'] > 0 else 0
            
            kpi_summary['kpis'] = {
                'total_quotes': current_data['total_quotes'],
                'conversions': current_data['conversions'],
                'conversion_rate': round(conversion_rate, 2),
                'revenue': float(current_data['revenue']),
                'unique_customers': current_data['unique_customers'],
                'avg_order_value': float(current_data['avg_order_value'])
            }
            
            # Calculate growth rates if comparison is requested
            if compare_previous:
                prev_kpis = execute_query('''
                    SELECT 
                        COUNT(*) as total_quotes,
                        COUNT(CASE WHEN status = 'completed' THEN 1 END) as conversions,
                        COALESCE(SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END), 0) as revenue,
                        COUNT(DISTINCT customer_id) as unique_customers,
                        COALESCE(AVG(CASE WHEN status = 'completed' THEN amount ELSE NULL END), 0) as avg_order_value
                    FROM transactions 
                    WHERE created_at >= %s AND created_at <= %s
                ''', (prev_start_date, prev_end_date), 'one')
                
                if prev_kpis['success'] and prev_kpis['data']:
                    prev_data = prev_kpis['data']
                    
                    growth_rates = {}
                    for key in ['total_quotes', 'conversions', 'revenue', 'unique_customers', 'avg_order_value']:
                        current_val = float(current_data[key]) if current_data[key] else 0
                        prev_val = float(prev_data[key]) if prev_data[key] else 0
                        
                        if prev_val > 0:
                            growth_rate = ((current_val - prev_val) / prev_val) * 100
                            growth_rates[f'{key}_growth'] = round(growth_rate, 2)
                        else:
                            growth_rates[f'{key}_growth'] = 0 if current_val == 0 else 100
                    
                    kpi_summary['growth_rates'] = growth_rates
                    kpi_summary['comparison_period'] = {
                        'start_date': prev_start_date.isoformat(),
                        'end_date': prev_end_date.isoformat()
                    }
        
        return jsonify(kpi_summary)

    except Exception as e:
        return jsonify(f'Failed to calculate KPIs: {str(e)}'), 500
#!/usr/bin/env python3
"""
ConnectedAutoCare.com - Admin Analytics Dashboard API
Comprehensive analytics and reporting for admin panel
"""

import json
import os
import functools
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Blueprint, request, jsonify

# Create blueprint for analytics
analytics_bp = Blueprint('analytics_dashboard', __name__)

# Import authentication decorators - handle import gracefully
try:
    from ..auth.admin_auth import require_admin_auth, require_permission, AdminSecurity
except ImportError:
    # Fallback for when running independently
    def require_admin_auth(f):
        @functools.wraps(f)  # This preserves the original function name
        def auth_wrapper(*args, **kwargs):
            return f(*args, **kwargs)
        return auth_wrapper

    def require_permission(permission):
        def decorator(f):
            @functools.wraps(f)  # This preserves the original function name
            def permission_wrapper(*args, **kwargs):
                return f(*args, **kwargs)
            return permission_wrapper
        return decorator

    class AdminSecurity:
        @staticmethod
        def log_admin_action(username, action, details=None):
            print(f"ADMIN ACTION: {username} - {action} - {details}")

# Analytics data storage (in production, use database)
ANALYTICS_DATA_FILE = "/tmp/analytics_data.json"
QUOTES_DATA_FILE = "/tmp/quotes_data.json"
SALES_DATA_FILE = "/tmp/sales_data.json"


class AnalyticsManager:
    """Analytics and reporting utilities"""

    @staticmethod
    def load_analytics_data():
        """Load analytics data from storage"""
        try:
            if os.path.exists(ANALYTICS_DATA_FILE):
                with open(ANALYTICS_DATA_FILE, 'r') as f:
                    return json.load(f)
            else:
                return AnalyticsManager.get_default_analytics()
        except Exception as e:
            print(f"Error loading analytics: {e}")
            return AnalyticsManager.get_default_analytics()

    @staticmethod
    def save_analytics_data(data):
        """Save analytics data to storage"""
        try:
            with open(ANALYTICS_DATA_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving analytics: {e}")
            return False

    @staticmethod
    def get_default_analytics():
        """Get default analytics data structure"""
        return {
            "dashboard_stats": {
                "total_quotes": 0,
                "total_sales": 0,
                "total_revenue": 0.0,
                "conversion_rate": 0.0,
                "avg_quote_value": 0.0,
                "active_products": 0
            },
            "quote_history": [],
            "sales_history": [],
            "product_performance": {},
            "traffic_stats": {
                "daily_visitors": 0,
                "page_views": 0,
                "bounce_rate": 0.0,
                "avg_session_duration": 0
            },
            "customer_stats": {
                "new_customers": 0,
                "returning_customers": 0,
                "customer_lifetime_value": 0.0
            }
        }

    @staticmethod
    def record_quote(quote_data):
        """Record a new quote for analytics"""
        analytics = AnalyticsManager.load_analytics_data()

        quote_record = {
            "id": quote_data.get("quote_id", ""),
            "product_type": quote_data.get("product_type", ""),
            "product_name": quote_data.get("product_name", ""),
            "quote_amount": quote_data.get("total_price", 0),
            "customer_type": quote_data.get("customer_type", "retail"),
            "timestamp": datetime.utcnow().isoformat(),
            "converted": False
        }

        analytics["quote_history"].append(quote_record)
        analytics["dashboard_stats"]["total_quotes"] += 1

        # Update product performance
        product_key = quote_data.get("product_type", "unknown")
        if product_key not in analytics["product_performance"]:
            analytics["product_performance"][product_key] = {
                "quotes": 0,
                "sales": 0,
                "revenue": 0.0,
                "conversion_rate": 0.0
            }

        analytics["product_performance"][product_key]["quotes"] += 1

        # Recalculate averages
        AnalyticsManager.recalculate_stats(analytics)
        AnalyticsManager.save_analytics_data(analytics)

        return quote_record

    @staticmethod
    def record_sale(sale_data):
        """Record a new sale for analytics"""
        analytics = AnalyticsManager.load_analytics_data()

        sale_record = {
            "id": sale_data.get("sale_id", ""),
            "quote_id": sale_data.get("quote_id", ""),
            "product_type": sale_data.get("product_type", ""),
            "product_name": sale_data.get("product_name", ""),
            "sale_amount": sale_data.get("total_price", 0),
            "customer_type": sale_data.get("customer_type", "retail"),
            "payment_method": sale_data.get("payment_method", ""),
            "timestamp": datetime.utcnow().isoformat()
        }

        analytics["sales_history"].append(sale_record)
        analytics["dashboard_stats"]["total_sales"] += 1
        analytics["dashboard_stats"]["total_revenue"] += sale_data.get(
            "total_price", 0)

        # Update product performance
        product_key = sale_data.get("product_type", "unknown")
        if product_key not in analytics["product_performance"]:
            analytics["product_performance"][product_key] = {
                "quotes": 0,
                "sales": 0,
                "revenue": 0.0,
                "conversion_rate": 0.0
            }

        analytics["product_performance"][product_key]["sales"] += 1
        analytics["product_performance"][product_key]["revenue"] += sale_data.get(
            "total_price", 0)

        # Mark corresponding quote as converted
        quote_id = sale_data.get("quote_id")
        if quote_id:
            for quote in analytics["quote_history"]:
                if quote["id"] == quote_id:
                    quote["converted"] = True
                    break

        # Recalculate stats
        AnalyticsManager.recalculate_stats(analytics)
        AnalyticsManager.save_analytics_data(analytics)

        return sale_record

    @staticmethod
    def recalculate_stats(analytics):
        """Recalculate dashboard statistics"""
        total_quotes = analytics["dashboard_stats"]["total_quotes"]
        total_sales = analytics["dashboard_stats"]["total_sales"]
        total_revenue = analytics["dashboard_stats"]["total_revenue"]

        # Calculate conversion rate
        if total_quotes > 0:
            analytics["dashboard_stats"]["conversion_rate"] = (
                total_sales / total_quotes) * 100

        # Calculate average quote value
        if total_quotes > 0:
            total_quote_value = sum(quote["quote_amount"]
                                    for quote in analytics["quote_history"])
            analytics["dashboard_stats"]["avg_quote_value"] = total_quote_value / total_quotes

        # Calculate product conversion rates
        for product_key, performance in analytics["product_performance"].items():
            if performance["quotes"] > 0:
                performance["conversion_rate"] = (
                    performance["sales"] / performance["quotes"]) * 100

    @staticmethod
    def get_date_range_data(start_date, end_date):
        """Get analytics data for specific date range"""
        analytics = AnalyticsManager.load_analytics_data()

        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

        filtered_quotes = [
            quote for quote in analytics["quote_history"]
            if start_dt <= datetime.fromisoformat(quote["timestamp"].replace('Z', '+00:00')) <= end_dt
        ]

        filtered_sales = [
            sale for sale in analytics["sales_history"]
            if start_dt <= datetime.fromisoformat(sale["timestamp"].replace('Z', '+00:00')) <= end_dt
        ]

        return {
            "quotes": filtered_quotes,
            "sales": filtered_sales,
            "summary": {
                "total_quotes": len(filtered_quotes),
                "total_sales": len(filtered_sales),
                "total_revenue": sum(sale["sale_amount"] for sale in filtered_sales),
                "conversion_rate": (len(filtered_sales) / len(filtered_quotes) * 100) if filtered_quotes else 0
            }
        }

# Analytics routes


@analytics_bp.route('/health', methods=['GET'])
def analytics_dashboard_health():
    """Analytics health check"""
    return jsonify({
        'success': True,
        'message': 'Analytics dashboard is operational',
        'features': ['Dashboard Stats', 'Quote Analytics', 'Sales Analytics', 'Product Performance', 'Data Export']
    })


@analytics_bp.route('/dashboard', methods=['GET'])
@require_admin_auth
@require_permission('analytics')
def get_dashboard_stats():
    """Get main dashboard statistics"""
    try:
        analytics = AnalyticsManager.load_analytics_data()

        if hasattr(request, 'admin_user'):
            AdminSecurity.log_admin_action(
                request.admin_user['username'],
                'view_dashboard'
            )

        return jsonify({
            'success': True,
            'data': {
                'dashboard_stats': analytics['dashboard_stats'],
                # Last 10 quotes
                'recent_quotes': analytics['quote_history'][-10:],
                # Last 10 sales
                'recent_sales': analytics['sales_history'][-10:],
                'product_performance': analytics['product_performance']
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to load dashboard: {str(e)}'
        }), 500


@analytics_bp.route('/quotes', methods=['GET'])
@require_admin_auth
@require_permission('analytics')
def get_quotes_analytics():
    """Get detailed quotes analytics"""
    try:
        # Get query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        product_type = request.args.get('product_type')

        analytics = AnalyticsManager.load_analytics_data()
        quotes = analytics['quote_history']

        # Filter by date range if provided
        if start_date and end_date:
            data = AnalyticsManager.get_date_range_data(start_date, end_date)
            quotes = data['quotes']

        # Filter by product type if provided
        if product_type:
            quotes = [q for q in quotes if q['product_type'] == product_type]

        # Calculate analytics
        total_quotes = len(quotes)
        converted_quotes = len(
            [q for q in quotes if q.get('converted', False)])
        total_quote_value = sum(q['quote_amount'] for q in quotes)

        # Group by product type
        by_product = defaultdict(
            lambda: {'count': 0, 'value': 0, 'converted': 0})
        for quote in quotes:
            product = quote['product_type']
            by_product[product]['count'] += 1
            by_product[product]['value'] += quote['quote_amount']
            if quote.get('converted', False):
                by_product[product]['converted'] += 1

        # Group by date (daily)
        by_date = defaultdict(lambda: {'count': 0, 'value': 0})
        for quote in quotes:
            date = quote['timestamp'][:10]  # YYYY-MM-DD
            by_date[date]['count'] += 1
            by_date[date]['value'] += quote['quote_amount']

        return jsonify({
            'success': True,
            'data': {
                'summary': {
                    'total_quotes': total_quotes,
                    'converted_quotes': converted_quotes,
                    'conversion_rate': (converted_quotes / total_quotes * 100) if total_quotes > 0 else 0,
                    'total_quote_value': total_quote_value,
                    'avg_quote_value': total_quote_value / total_quotes if total_quotes > 0 else 0
                },
                'by_product': dict(by_product),
                'by_date': dict(by_date),
                'quotes': quotes
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to load quotes analytics: {str(e)}'
        }), 500


@analytics_bp.route('/sales', methods=['GET'])
@require_admin_auth
@require_permission('analytics')
def get_sales_analytics():
    """Get detailed sales analytics"""
    try:
        # Get query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        product_type = request.args.get('product_type')

        analytics = AnalyticsManager.load_analytics_data()
        sales = analytics['sales_history']

        # Filter by date range if provided
        if start_date and end_date:
            data = AnalyticsManager.get_date_range_data(start_date, end_date)
            sales = data['sales']

        # Filter by product type if provided
        if product_type:
            sales = [s for s in sales if s['product_type'] == product_type]

        # Calculate analytics
        total_sales = len(sales)
        total_revenue = sum(s['sale_amount'] for s in sales)

        # Group by product type
        by_product = defaultdict(lambda: {'count': 0, 'revenue': 0})
        for sale in sales:
            product = sale['product_type']
            by_product[product]['count'] += 1
            by_product[product]['revenue'] += sale['sale_amount']

        # Group by date (daily)
        by_date = defaultdict(lambda: {'count': 0, 'revenue': 0})
        for sale in sales:
            date = sale['timestamp'][:10]  # YYYY-MM-DD
            by_date[date]['count'] += 1
            by_date[date]['revenue'] += sale['sale_amount']

        # Group by customer type
        by_customer_type = defaultdict(lambda: {'count': 0, 'revenue': 0})
        for sale in sales:
            customer_type = sale.get('customer_type', 'retail')
            by_customer_type[customer_type]['count'] += 1
            by_customer_type[customer_type]['revenue'] += sale['sale_amount']

        return jsonify({
            'success': True,
            'data': {
                'summary': {
                    'total_sales': total_sales,
                    'total_revenue': total_revenue,
                    'avg_sale_value': total_revenue / total_sales if total_sales > 0 else 0
                },
                'by_product': dict(by_product),
                'by_date': dict(by_date),
                'by_customer_type': dict(by_customer_type),
                'sales': sales
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to load sales analytics: {str(e)}'
        }), 500


@analytics_bp.route('/product-performance', methods=['GET'])
@require_admin_auth
@require_permission('analytics')
def get_product_performance():
    """Get product performance analytics"""
    try:
        analytics = AnalyticsManager.load_analytics_data()
        performance = analytics['product_performance']

        # Calculate additional metrics
        enhanced_performance = {}
        for product_id, data in performance.items():
            enhanced_performance[product_id] = {
                **data,
                'avg_sale_value': data['revenue'] / data['sales'] if data['sales'] > 0 else 0,
                'quote_to_sale_ratio': data['sales'] / data['quotes'] if data['quotes'] > 0 else 0
            }

        return jsonify({
            'success': True,
            'data': enhanced_performance
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to load product performance: {str(e)}'
        }), 500


@analytics_bp.route('/export', methods=['POST'])
@require_admin_auth
@require_permission('analytics')
def export_analytics_data():
    """Export analytics data for external analysis"""
    try:
        data = request.get_json()
        export_type = data.get('type', 'all')  # 'quotes', 'sales', 'all'
        start_date = data.get('start_date')
        end_date = data.get('end_date')

        analytics = AnalyticsManager.load_analytics_data()
        export_data = {}

        if export_type in ['quotes', 'all']:
            quotes = analytics['quote_history']
            if start_date and end_date:
                range_data = AnalyticsManager.get_date_range_data(
                    start_date, end_date)
                quotes = range_data['quotes']
            export_data['quotes'] = quotes

        if export_type in ['sales', 'all']:
            sales = analytics['sales_history']
            if start_date and end_date:
                range_data = AnalyticsManager.get_date_range_data(
                    start_date, end_date)
                sales = range_data['sales']
            export_data['sales'] = sales

        if export_type == 'all':
            export_data['dashboard_stats'] = analytics['dashboard_stats']
            export_data['product_performance'] = analytics['product_performance']

        if hasattr(request, 'admin_user'):
            AdminSecurity.log_admin_action(
                request.admin_user['username'],
                'export_analytics',
                {'type': export_type,
                    'date_range': f"{start_date} to {end_date}" if start_date else 'all'}
            )

        return jsonify({
            'success': True,
            'data': export_data,
            'export_info': {
                'type': export_type,
                'date_range': f"{start_date} to {end_date}" if start_date else 'all_time',
                'exported_at': datetime.utcnow().isoformat()
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to export analytics: {str(e)}'
        }), 500


@analytics_bp.route('/record-quote', methods=['POST'])
@require_admin_auth
@require_permission('analytics')
def record_quote_manually():
    """Manually record a quote for testing/admin purposes"""
    try:
        data = request.get_json()
        quote_record = AnalyticsManager.record_quote(data)

        if hasattr(request, 'admin_user'):
            AdminSecurity.log_admin_action(
                request.admin_user['username'],
                'record_quote_manual',
                {'quote_id': quote_record['id']}
            )

        return jsonify({
            'success': True,
            'data': quote_record
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to record quote: {str(e)}'
        }), 500


@analytics_bp.route('/record-sale', methods=['POST'])
@require_admin_auth
@require_permission('analytics')
def record_sale_manually():
    """Manually record a sale for testing/admin purposes"""
    try:
        data = request.get_json()
        sale_record = AnalyticsManager.record_sale(data)

        if hasattr(request, 'admin_user'):
            AdminSecurity.log_admin_action(
                request.admin_user['username'],
                'record_sale_manual',
                {'sale_id': sale_record['id']}
            )

        return jsonify({
            'success': True,
            'data': sale_record
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to record sale: {str(e)}'
        }), 500


if __name__ == "__main__":
    # Test analytics system
    manager = AnalyticsManager()
    analytics = manager.get_default_analytics()
    print("Analytics system initialized successfully")

    # Test recording a quote
    test_quote = {
        "quote_id": "test_001",
        "product_type": "home_protection",
        "product_name": "Home Protection Plan",
        "total_price": 399,
        "customer_type": "retail"
    }

    quote_record = manager.record_quote(test_quote)
    print(f"Test quote recorded: {quote_record['id']}")

    # Test recording a sale
    test_sale = {
        "sale_id": "sale_001",
        "quote_id": "test_001",
        "product_type": "home_protection",
        "product_name": "Home Protection Plan",
        "total_price": 399,
        "customer_type": "retail",
        "payment_method": "credit_card"
    }

    sale_record = manager.record_sale(test_sale)
    print(f"Test sale recorded: {sale_record['id']}")

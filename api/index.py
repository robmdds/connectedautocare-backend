#!/usr/bin/env python3
"""
ConnectedAutoCare.com - Main Application Entry Point
Modular Flask application with organized endpoint blueprints
"""

import os
import sys
import time
from datetime import datetime, timezone, timedelta

import psycopg2
from flask import Flask, jsonify, Blueprint, request
from flask_cors import CORS
import json
from utils.database import execute_query

# Add the current directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import configuration and utilities
try:
    from config.app_config import AppConfig
    from utils.response_helpers import error_response
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False

# Import all endpoint blueprints with error handling
try:
    from endpoints.health_endpoints import health_bp
    from endpoints.hero_endpoints import hero_bp
    from endpoints.vsc_endpoints import vsc_bp
    from endpoints.vin_endpoints import vin_bp
    from endpoints.user_auth_endpoints import user_auth_bp
    from endpoints.customer_endpoints import customer_bp
    from endpoints.reseller_endpoints import reseller_bp
    from endpoints.admin_endpoints import admin_bp
    from endpoints.payment_endpoints import payment_bp
    from endpoints.video_endpoints import video_bp
    from endpoints.video_public_endpoints import video_public_bp 
    from endpoints.pricing_endpoints import pricing_bp
    from endpoints.analytics_endpoints import analytics_bp
    from admin.contract_management import contract_bp
    from endpoints.tpa_endpoints import tpa_bp
    from endpoints.contact_endpoints import contact_bp
    ENDPOINTS_AVAILABLE = True
except ImportError:
    ENDPOINTS_AVAILABLE = False
    # Create fallback blueprints
    
    health_bp = Blueprint('health_fallback', __name__)
    hero_bp = Blueprint('hero_fallback', __name__)
    vsc_bp = Blueprint('vsc_fallback', __name__)
    vin_bp = Blueprint('vin_fallback', __name__)
    user_auth_bp = Blueprint('user_auth_fallback', __name__)
    customer_bp = Blueprint('customer_fallback', __name__)
    reseller_bp = Blueprint('reseller_fallback', __name__)
    admin_bp = Blueprint('admin_fallback', __name__)
    payment_bp = Blueprint('payment_fallback', __name__)
    video_bp = Blueprint('video_fallback', __name__)
    video_public_bp = Blueprint('video_public_fallback', __name__)
    pricing_bp = Blueprint('pricing_fallback', __name__)
    analytics_bp = Blueprint('analytics_fallback', __name__)
    contract_bp = Blueprint('contract_fallback', __name__)
    tpa_bp = Blueprint('tpa_fallback', __name__)
    contact_bp = Blueprint('contact_fallback', __name__)
    
    # Add essential fallback routes
    @health_bp.route('/health')
    def fallback_health():
        return jsonify({
            "status": "fallback", 
            "message": "Endpoints not fully loaded",
            "timestamp": datetime.now(timezone.utc).isoformat() + 'Z'
        })
    
    @video_public_bp.route('/landing/video')
    def fallback_video():
        return jsonify({
            'video_url': '',
            'thumbnail_url': '',
            'title': 'ConnectedAutoCare Hero Protection',
            'description': 'Comprehensive protection plans',
            'duration': '2:30',
            'updated_at': datetime.now(timezone.utc).isoformat() + 'Z'
        })

# Initialize Flask app
app = Flask(__name__)


def save_shared_quote_transaction(transaction_data, existing_customer_id):
    """Save transaction for shared quote with existing customer"""
    try:
        helcim_response = transaction_data.get('helcim_response', {})
        quote_data = transaction_data.get('quote_data', {})
        customer_info = transaction_data.get('customer_info', {})
        billing_info = transaction_data.get('billing_info', {})
        amount = float(transaction_data.get('amount', 0))

        # Validate required data
        if not helcim_response:
            return {'success': False, 'error': 'Payment response data required'}

        if amount <= 0:
            return {'success': False, 'error': 'Invalid transaction amount'}

        # Generate transaction identifiers
        quote_id = transaction_data.get('quote_id', f'SHARED-{int(time.time())}')
        transaction_number = f"TXN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{quote_id.split('-')[-1]}"

        # Extract key information from HelcimJS response
        processor_transaction_id = (
                helcim_response.get('transactionId') or
                helcim_response.get('cardBatchId') or
                helcim_response.get('id') or
                f"HELCIM-{int(time.time())}"
        )

        payment_status = 'approved' if helcim_response.get('approved') else 'completed'

        # Get client IP address
        client_ip = request.headers.get('X-Forwarded-For',
                                        request.headers.get('X-Real-IP',
                                                            request.remote_addr))
        if not client_ip or client_ip == '127.0.0.1':
            client_ip = '192.168.1.1'

        # Get database URL from environment
        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return {'success': False, 'error': 'Database configuration not available'}

        # Connect to database
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        try:
            # Update existing customer with payment info
            if customer_info or billing_info:
                cursor.execute('''
                               UPDATE customers
                               SET personal_info = COALESCE(personal_info, '{}') || %s,
                                   contact_info  = COALESCE(contact_info, '{}') || %s,
                                   billing_info  = %s,
                                   updated_at    = CURRENT_TIMESTAMP,
                                   last_activity = CURRENT_TIMESTAMP
                               WHERE id = %s;
                               ''', (
                                   json.dumps({
                                       'first_name': customer_info.get('first_name', ''),
                                       'last_name': customer_info.get('last_name', '')
                                   }),
                                   json.dumps({
                                       'email': customer_info.get('email', ''),
                                       'phone': customer_info.get('phone', '')
                                   }),
                                   json.dumps(billing_info),
                                   existing_customer_id
                               ))

            # Insert transaction record
            cursor.execute('''
                           INSERT INTO transactions (transaction_number, customer_id, type, amount,
                                                     currency, status, payment_method, metadata,
                                                     processed_at, processor_response, created_by)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
                           ''', (
                               transaction_number,
                               existing_customer_id,  # Use the existing customer UUID
                               'payment',
                               amount,
                               transaction_data.get('currency', 'USD'),
                               payment_status,
                               json.dumps({
                                   'method': 'credit_card',
                                   'processor': 'helcim',
                                   'quote_id': quote_id,
                                   'processor_transaction_id': processor_transaction_id,
                                   'share_token': transaction_data.get('share_token')
                               }),
                               json.dumps({
                                   'quote_id': quote_id,
                                   'quote_data': quote_data,
                                   'customer_info': customer_info,
                                   'billing_info': billing_info,
                                   'payment_method': 'credit_card',
                                   'product_type': transaction_data.get('product_type', 'unknown'),
                                   'vehicle_info': transaction_data.get('vehicle_info'),
                                   'processed_at': datetime.now(timezone.utc).isoformat(),
                                   'ip_address': client_ip,
                                   'user_agent': request.headers.get('User-Agent', ''),
                                   'share_token': transaction_data.get('share_token')
                               }),
                               datetime.now(timezone.utc),
                               json.dumps({
                                   'helcim_response': helcim_response,
                                   'processor': 'helcim',
                                   'transaction_id': processor_transaction_id,
                                   'success': True,
                                   'payment_date': datetime.now(timezone.utc).isoformat()
                               }),
                               None  # No user_id for shared quote transactions
                           ))

            transaction_id = cursor.fetchone()[0]

            # Create protection plan record if quote data exists
            protection_plan_result = None
            if quote_data:
                protection_plan_result = create_shared_quote_protection_plan_record(
                    cursor, transaction_id, quote_data, existing_customer_id,
                    transaction_data.get('vehicle_info')
                )

            # Commit all changes
            conn.commit()
            cursor.close()
            conn.close()

            # Return success response
            return {
                'success': True,
                'data': {
                    'transaction_id': str(transaction_id),
                    'transaction_number': transaction_number,
                    'confirmation_number': f"CAC-{transaction_number}",
                    'processor_transaction_id': processor_transaction_id,
                    'status': payment_status,
                    'amount': amount,
                    'currency': transaction_data.get('currency', 'USD'),
                    'customer_id': str(existing_customer_id),
                    'protection_plan_id': protection_plan_result['plan_id'] if protection_plan_result else None,
                    'protection_plan_db_id': str(protection_plan_result['db_id']) if protection_plan_result else None
                }
            }

        except Exception as db_error:
            conn.rollback()
            cursor.close()
            conn.close()
            raise db_error

    except Exception as e:
        return {'success': False, 'error': f'Failed to save transaction: {str(e)}'}


def create_shared_quote_protection_plan_record(cursor, transaction_id, quote_data, customer_id, vehicle_info):
    """Create a protection plan record for shared quote transaction"""
    try:
        # Generate protection plan ID
        plan_id = f"PLAN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{transaction_id}"

        # Determine plan type and details from quote data
        coverage_details = quote_data.get('coverage_details', {})
        product_info = quote_data.get('product_info', {})
        pricing = quote_data.get('pricing', {})

        plan_type = 'vsc' if vehicle_info else 'hero'
        plan_name = (
                coverage_details.get('coverage_level') or
                product_info.get('product_type') or
                quote_data.get('product_type') or
                'Protection Plan'
        )

        # Calculate plan dates
        start_date = datetime.now(timezone.utc).date()

        # Determine end date based on plan type and quote data
        if plan_type == 'vsc':
            term_months = (
                    coverage_details.get('term_months') or
                    product_info.get('term_months') or
                    quote_data.get('term_months') or
                    12
            )
            if isinstance(term_months, str):
                term_months = int(term_months)
            end_date = start_date + timedelta(days=term_months * 30)
        else:
            term_years = (
                    coverage_details.get('term_years') or
                    product_info.get('term_years') or
                    quote_data.get('term_years') or
                    1
            )
            if isinstance(term_years, str):
                term_years = int(term_years)
            end_date = start_date + timedelta(days=term_years * 365)

        # Insert protection plan record
        cursor.execute('''
                       INSERT INTO protection_plans (plan_id, transaction_id, customer_id, plan_type,
                                                     plan_name, coverage_details, vehicle_info,
                                                     start_date, end_date, status, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
                       ''', (
                           plan_id,
                           transaction_id,
                           customer_id,  # Using UUID customer_id
                           plan_type,
                           plan_name,
                           json.dumps({
                               **coverage_details,
                               **product_info,
                               'quote_data': quote_data,
                               'pricing': pricing
                           }),
                           json.dumps(vehicle_info) if vehicle_info else None,
                           start_date,
                           end_date,
                           'active',
                           datetime.now(timezone.utc)
                       ))

        protection_plan_db_id = cursor.fetchone()[0]

        return {
            'plan_id': plan_id,
            'db_id': protection_plan_db_id,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat()
        }

    except Exception as e:
        print(f"Error creating protection plan record: {str(e)}")
        return None


# Load configuration
if CONFIG_AVAILABLE:
    config = AppConfig()
    app.config.update(config.get_flask_config())
    
    # Configure CORS
    CORS(app, 
         origins=config.ALLOWED_ORIGINS, 
         supports_credentials=True,
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
         
    # Enhanced CORS handling for production
    @app.after_request
    def after_request(response):
        return config.handle_cors_response(response)

    @app.before_request
    def handle_preflight():
        return config.handle_preflight_request()
        
else:
    # Fallback configuration
    app.config.update({
        'SECRET_KEY': os.environ.get('SECRET_KEY', 'fallback-secret-key-2025'),
        'DEBUG': False,
        'TESTING': False,
        'MAX_CONTENT_LENGTH': 16 * 1024 * 1024
    })
    
    # Basic CORS
    CORS(app, origins="*", supports_credentials=True)

# Register all blueprints
def register_blueprints(app):
    """Register all endpoint blueprints"""
    
    try:
        # Core API endpoints
        app.register_blueprint(health_bp, url_prefix='/api')
        app.register_blueprint(hero_bp, url_prefix='/api/hero')
        app.register_blueprint(vsc_bp, url_prefix='/api/vsc')
        app.register_blueprint(vin_bp, url_prefix='/api/vin')
        
        # User management endpoints
        app.register_blueprint(user_auth_bp, url_prefix='/api/auth')
        app.register_blueprint(customer_bp, url_prefix='/api/customers')
        app.register_blueprint(reseller_bp, url_prefix='/api/resellers')
        
        # Admin endpoints
        app.register_blueprint(admin_bp, url_prefix='/api/admin')
        app.register_blueprint(pricing_bp, url_prefix='/api/admin/pricing')
        
        # Analytics endpoints
        app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
        
        # Contract endpoints
        app.register_blueprint(contract_bp, url_prefix='/api/admin/contracts')
        
        # Video endpoints - Admin routes
        app.register_blueprint(video_bp, url_prefix='/api/admin/video')
        
        # tpa endpoints
        app.register_blueprint(tpa_bp, url_prefix='/api/admin/tpas')
        
        # Contact endpoints
        app.register_blueprint(contact_bp, url_prefix='/api/contact')
        # Video endpoints - Public routes
        app.register_blueprint(video_public_bp, url_prefix='/api')
        
        # Payment endpoints
        app.register_blueprint(payment_bp, url_prefix='/api/payments')
        
    except Exception as e:
        import traceback
        print(f"Error registering blueprints: {e}")
        print(f"Traceback: {traceback.format_exc()}")

# Register all blueprints
register_blueprints(app)

# Global error handlers
@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    if CONFIG_AVAILABLE:
        return error_response("Endpoint not found", 404)
    else:
        return jsonify({
            "success": False,
            "error": "Endpoint not found",
            "timestamp": datetime.now(timezone.utc).isoformat() + 'Z'
        }), 404

@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors"""
    if CONFIG_AVAILABLE:
        return error_response("Method not allowed", 405)
    else:
        return jsonify({
            "success": False,
            "error": "Method not allowed",
            "timestamp": datetime.now(timezone.utc).isoformat() + 'Z'
        }), 405

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    if CONFIG_AVAILABLE:
        return error_response("Internal server error", 500)
    else:
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "timestamp": datetime.now(timezone.utc).isoformat() + 'Z'
        }), 500

@app.errorhandler(Exception)
def handle_exception(error):
    """Handle unexpected exceptions"""
    import traceback
    print(f"Unexpected error: {str(error)}")
    print(f"Traceback: {traceback.format_exc()}")
    
    if CONFIG_AVAILABLE:
        return error_response("An unexpected error occurred", 500)
    else:
        return jsonify({
            "success": False,
            "error": "An unexpected error occurred",
            "timestamp": datetime.now(timezone.utc).isoformat() + 'Z'
        }), 500

# Root endpoint
@app.route('/')
def root():
    """Root endpoint with API information"""
    return {
        "service": "ConnectedAutoCare Unified Platform",
        "version": "4.0.0",
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "endpoints": {
            "health": "/api/health",
            "hero_products": "/api/hero/products",
            "vsc_quotes": "/api/vsc/quote",
            "vin_decoder": "/api/vin/decode",
            "user_auth": "/api/auth/login",
            "admin": "/api/admin/health",
            "payments": "/api/payments/methods",
            "resellers": "/api/resellers",
            "video_public": "/api/landing/video",
            "video_admin": "/api/admin/video"
        },
        "documentation": "https://api.connectedautocare.com/docs"
    }

# Health check endpoint
@app.route('/health')
def health_check():
    """Simple health check endpoint"""
    return {
        "status": "healthy",
        "service": "ConnectedAutoCare API",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "endpoints_loaded": ENDPOINTS_AVAILABLE,
        "config_loaded": CONFIG_AVAILABLE
    }

# API status endpoint
@app.route('/api/status')
def api_status():
    """API status endpoint with detailed information"""
    return jsonify({
        "api_status": "operational",
        "version": "4.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "services": {
            "core_api": "healthy",
            "video_service": "healthy" if ENDPOINTS_AVAILABLE else "degraded",
            "configuration": "loaded" if CONFIG_AVAILABLE else "fallback"
        },
        "endpoints_available": ENDPOINTS_AVAILABLE
    })


@app.route('/quote/shared/<share_token>', methods=['GET'])
def view_shared_quote(share_token):
    """Public endpoint for customers to view shared quotes"""
    try:
        print(f"DEBUG - Looking up shared quote with token: {share_token}")

        # Find quote by share token
        quote_result = execute_query('''
                                     SELECT q.quote_id,
                                            q.product_type,
                                            q.quote_data,
                                            q.total_price,
                                            q.expires_at,
                                            q.status,
                                            c.personal_info,
                                            c.contact_info,
                                            r.business_name as reseller_name
                                     FROM quotes q
                                              JOIN customers c ON q.customer_id = c.id
                                              JOIN resellers r ON q.reseller_id = r.user_id
                                     WHERE q.share_token = %s
                                       AND q.is_shareable = true
                                       AND q.status = 'active'
                                     ''', (share_token,), 'one')

        print(f"DEBUG - Quote lookup result: {quote_result}")

        if not quote_result['success'] or not quote_result['data']:
            return jsonify({'error': 'Quote not found or no longer available'}), 404

        # Access RealDictRow by column names instead of indices
        quote_data = quote_result['data']
        quote_id = quote_data['quote_id']
        product_type = quote_data['product_type']
        quote_details = quote_data['quote_data']
        total_price = quote_data['total_price']
        expires_at = quote_data['expires_at']
        status = quote_data['status']
        personal_info = quote_data['personal_info']
        contact_info = quote_data['contact_info']
        reseller_name = quote_data['reseller_name']

        print(f"DEBUG - Quote data extracted: ID={quote_id}, Product={product_type}, Price={total_price}")

        # Check if quote has expired
        if expires_at:
            # Handle timezone comparison - make both datetimes timezone-aware or both naive
            current_time = datetime.now(timezone.utc)

            # If expires_at is naive (no timezone info), assume it's UTC and make it aware
            if expires_at.tzinfo is None:
                expires_at_aware = expires_at.replace(tzinfo=timezone.utc)
            else:
                expires_at_aware = expires_at

            if current_time > expires_at_aware:
                return jsonify({'error': 'Quote has expired'}), 410

        # Log quote view activity
        quote_uuid_result = execute_query('''
                                          SELECT id
                                          FROM quotes
                                          WHERE share_token = %s
                                          ''', (share_token,), 'one')

        if quote_uuid_result['success'] and quote_uuid_result['data']:
            quote_uuid = quote_uuid_result['data']['id']  # Access by column name

            print(f"DEBUG - Logging quote view activity for quote UUID: {quote_uuid}")

            # Log the activity (handle case where quote_activities table might not have user_agent column)
            try:
                activity_result = execute_query('''
                                                INSERT INTO quote_activities (quote_id, activity_type, actor_type,
                                                                              description, ip_address, user_agent)
                                                VALUES (%s, %s, %s, %s, %s, %s)
                                                ''', (
                                                    quote_uuid, 'viewed', 'customer',
                                                    'Quote viewed via shared link', request.remote_addr,
                                                    request.user_agent.string if request.user_agent else 'Unknown'
                                                ), 'none')

                print(f"DEBUG - Activity log result: {activity_result}")

            except Exception as activity_error:
                # If user_agent column doesn't exist, try without it
                print(f"DEBUG - Activity log with user_agent failed, trying without: {str(activity_error)}")
                try:
                    activity_result = execute_query('''
                                                    INSERT INTO quote_activities (quote_id, activity_type, actor_type, description, ip_address)
                                                    VALUES (%s, %s, %s, %s, %s)
                                                    ''', (
                                                        quote_uuid, 'viewed', 'customer',
                                                        'Quote viewed via shared link', request.remote_addr
                                                    ), 'none')

                    print(f"DEBUG - Activity log result (without user_agent): {activity_result}")

                except Exception as activity_error2:
                    print(f"WARNING - Failed to log quote activity: {str(activity_error2)}")

            # Update customer_accessed_at (handle case where these columns might not exist)
            try:
                update_result = execute_query('''
                                              UPDATE quotes
                                              SET customer_accessed_at = CURRENT_TIMESTAMP,
                                                  customer_ip_address  = %s
                                              WHERE share_token = %s
                                              ''', (request.remote_addr, share_token), 'none')

                print(f"DEBUG - Quote update result: {update_result}")

            except Exception as update_error:
                print(f"WARNING - Failed to update quote access info: {str(update_error)}")

        # Prepare response (remove sensitive data)
        response_data = {
            'quote_id': quote_id,
            'product_type': product_type,
            'quote_details': quote_details if quote_details else {},
            'total_price': float(total_price) if total_price else 0,
            'expires_at': expires_at.isoformat() + 'Z' if expires_at else None,
            'customer_info': personal_info if personal_info else {},
            'contact_info': contact_info if contact_info else {},
            'reseller_name': reseller_name
        }

        print(f"DEBUG - Returning successful quote response")

        return jsonify({
            'success': True,
            'quote': response_data
        })

    except Exception as e:
        print(f"DEBUG - Exception in view_shared_quote: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to fetch quote: {str(e)}'}), 500


@app.route('/quote/<share_token>/accept', methods=['POST'])
def accept_shared_quote(share_token):
    """Enhanced endpoint for customers to accept/purchase from shared quote with payment integration"""
    try:
        data = request.get_json()
        payment_data = data.get('payment_data', {})

        print(f"DEBUG - Accept shared quote called with token: {share_token}")
        print(f"DEBUG - Payment data present: {bool(payment_data)}")

        # Find and validate quote
        quote_result = execute_query('''
                                     SELECT q.id,
                                            q.quote_id,
                                            q.customer_id,
                                            q.reseller_id,
                                            q.total_price,
                                            q.commission_amount,
                                            q.product_type,
                                            q.quote_data,
                                            q.expires_at,
                                            c.personal_info as customer_personal_info,
                                            c.contact_info  as customer_contact_info
                                     FROM quotes q
                                              LEFT JOIN customers c ON q.customer_id = c.id
                                     WHERE q.share_token = %s
                                       AND q.is_shareable = true
                                       AND q.status = 'active'
                                     ''', (share_token,), 'one')

        if not quote_result['success'] or not quote_result['data']:
            return jsonify({'success': False, 'error': 'Quote not found or no longer available'}), 404

        quote_info = quote_result['data']
        quote_uuid = quote_info['id']
        quote_id = quote_info['quote_id']
        customer_id = quote_info['customer_id']
        reseller_id = quote_info['reseller_id']
        total_price = quote_info['total_price']
        commission_amount = quote_info['commission_amount']
        product_type = quote_info['product_type']
        quote_data = quote_info['quote_data']
        expires_at = quote_info['expires_at']

        # Check if expired
        if expires_at:
            current_time = datetime.now(timezone.utc)
            if expires_at.tzinfo is None:
                expires_at_aware = expires_at.replace(tzinfo=timezone.utc)
            else:
                expires_at_aware = expires_at

            if current_time > expires_at_aware:
                return jsonify({'success': False, 'error': 'Quote has expired'}), 410

        # Verify reseller exists
        reseller_check = execute_query('''
                                       SELECT id, commission_rate, business_name
                                       FROM resellers
                                       WHERE user_id = %s
                                       ''', (reseller_id,), 'one')

        if not reseller_check['success'] or not reseller_check['data']:
            return jsonify({'success': False, 'error': 'Reseller not found'}), 404

        reseller_data = reseller_check['data']
        commission_rate = reseller_data['commission_rate']

        print(f"DEBUG - Quote found: {quote_id}, Customer: {customer_id}, Reseller: {reseller_id}")

        # Process payment if payment data is provided
        payment_result = None
        if payment_data and payment_data.get('helcim_response'):
            try:
                print("DEBUG - Processing payment transaction")

                # Save the payment transaction
                transaction_data = {
                    'helcim_response': payment_data['helcim_response'],
                    'quote_data': quote_data,
                    'customer_info': payment_data.get('customer_info', {}),
                    'billing_info': payment_data.get('billing_info', {}),
                    'payment_method': payment_data.get('payment_method', 'credit_card'),
                    'amount': payment_data.get('amount', total_price),
                    'product_type': product_type,
                    'vehicle_info': quote_data.get('vehicle_info') if quote_data else None,
                    'currency': 'USD',
                    'share_token': share_token,
                    'quote_id': quote_id
                }

                payment_result = save_shared_quote_transaction(transaction_data, customer_id)

                if not payment_result['success']:
                    print(f"ERROR - Payment processing failed: {payment_result.get('error')}")
                    return jsonify({
                        'success': False,
                        'error': f'Payment processing failed: {payment_result.get("error", "Unknown error")}'
                    }), 400

                print("DEBUG - Payment processed successfully")

            except Exception as payment_error:
                print(f"ERROR - Payment processing exception: {str(payment_error)}")
                return jsonify({
                    'success': False,
                    'error': f'Payment processing failed: {str(payment_error)}'
                }), 500

        # Update quote status to converted
        convert_result = execute_query('''
                                       UPDATE quotes
                                       SET converted_to_policy = true,
                                           converted_at        = CURRENT_TIMESTAMP,
                                           status              = 'converted'
                                       WHERE id = %s
                                       ''', (quote_uuid,), 'none')

        if not convert_result['success']:
            return jsonify({
                'success': False,
                'error': f'Failed to update quote: {convert_result.get("error", "Unknown error")}'
            }), 500

        print("DEBUG - Quote marked as converted")

        # Create sales record for reseller
        try:
            sales_result = execute_query('''
                                         INSERT INTO reseller_sales (reseller_id, quote_id, customer_id, sale_type,
                                                                     product_type, gross_amount, commission_rate,
                                                                     commission_amount, commission_status, sale_date)
                                         VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_DATE)
                                         ''', (
                                             reseller_id,  # This matches the foreign key constraint
                                             quote_uuid,  # quotes.id (UUID)
                                             customer_id,  # customers.id (UUID)
                                             'quote_conversion',
                                             product_type,
                                             total_price,
                                             commission_rate,
                                             commission_amount,
                                             'pending'
                                         ), 'none')

            if sales_result['success']:
                print("DEBUG - Sales record created successfully")
            else:
                print(f"WARNING - Failed to create sales record: {sales_result.get('error', 'Unknown error')}")

        except Exception as sales_error:
            print(f"WARNING - Exception creating sales record: {str(sales_error)}")

        # Log conversion activity
        try:
            activity_result = execute_query('''
                                            INSERT INTO quote_activities (quote_id, activity_type, actor_type,
                                                                          description, ip_address)
                                            VALUES (%s, %s, %s, %s, %s)
                                            ''', (
                                                quote_uuid, 'converted', 'customer',
                                                'Quote converted to policy via shared link',
                                                request.remote_addr
                                            ), 'none')

            if activity_result['success']:
                print("DEBUG - Activity logged successfully")

        except Exception as activity_error:
            print(f"WARNING - Failed to log activity: {str(activity_error)}")

        # Prepare response
        response_data = {
            'success': True,
            'message': 'Quote accepted successfully',
            'quote_id': quote_id,
            'total_amount': float(total_price) if total_price else 0,
            'payment_processed': bool(payment_data and payment_result)
        }

        # Add transaction data if payment was processed
        if payment_result and payment_result.get('success'):
            response_data['transaction_data'] = payment_result['data']

        print("DEBUG - Returning successful response")
        return jsonify(response_data)

    except Exception as e:
        print(f"ERROR - Exception in accept_shared_quote: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Failed to accept quote: {str(e)}'}), 500

# For local development only
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
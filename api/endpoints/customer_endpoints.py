"""
Customer Management Endpoints
Customer portal, profile management, and customer-specific functionality
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
import uuid
import json
from utils.auth_decorators import token_required
from utils.database import get_db_manager, execute_query
from utils.service_availability import ServiceChecker

# Initialize blueprint
customer_bp = Blueprint('customer', __name__)

# Import customer services with error handling
try:
    from auth.user_auth import UserAuth, SecurityUtils
    from models.database_models import UserModel, CustomerModel, DatabaseUtils
    customer_services_available = True
    
    # Initialize models
    user_model = UserModel()
    customer_model = CustomerModel()
    customers_db = {}
    
except ImportError as e:
    print(f"Warning: Customer services not available: {e}")
    customer_services_available = False
    
    # Create fallback classes
    class UserAuth:
        @staticmethod
        def hash_password(password):
            import hashlib
            return hashlib.sha256(password.encode()).hexdigest()
        
        @staticmethod
        def verify_password(password, hash):
            return UserAuth.hash_password(password) == hash
    
    class SecurityUtils:
        @staticmethod
        def log_security_event(user_id, event, data):
            print(f"Security Event: {event} by {user_id} - {data}")
    
    class UserModel:
        def create_user(self, data):
            return {**data, 'id': str(uuid.uuid4()), 'created_at': datetime.now(timezone.utc)}
    
    class CustomerModel:
        def create_customer(self, data):
            return {**data, 'id': str(uuid.uuid4()), 'created_at': datetime.now(timezone.utc)}
    
    class DatabaseUtils:
        @staticmethod
        def get_customer_metrics(customer_id, transactions, policies):
            return {'total_transactions': 0, 'total_spent': 0.0, 'active_policies': 0}
    
    user_model = UserModel()
    customer_model = CustomerModel()
    customers_db = {}

# ================================
# CUSTOMER HEALTH & STATUS
# ================================

@customer_bp.route('/health')
def customer_health():
    """Customer service health check"""
    service_checker = ServiceChecker()
    
    return jsonify({
        'service': 'Customer Management API',
        'status': 'healthy' if customer_services_available else 'degraded',
        'customer_services_available': customer_services_available,
        'features': {
            'profile_management': customer_services_available,
            'quote_history': True,
            'policy_management': True,
            'transaction_history': True,
            'document_access': True,
            'support_tickets': True
        },
        'database_integration': service_checker.database_settings_available,
        'timestamp': datetime.now(timezone.utc).isoformat() + "Z"
    })

# ================================
# CUSTOMER REGISTRATION & PROFILE
# ================================

@customer_bp.route('/register', methods=['POST'])
def register_customer():
    """Register new customer"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['email', 'password', 'first_name', 'last_name']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify(f"Missing fields: {', '.join(missing_fields)}"), 400
        
        email = data.get('email').lower().strip()
        password = data.get('password')
        first_name = data.get('first_name').strip()
        last_name = data.get('last_name').strip()
        phone = data.get('phone', '').strip()
        
        # Validate email format
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return jsonify('Invalid email format'), 400
        
        # Validate password strength
        if len(password) < 8:
            return jsonify('Password must be at least 8 characters long'), 400
        
        # Check password complexity
        if not re.search(r'[A-Z]', password):
            return jsonify('Password must contain at least one uppercase letter'), 400
        if not re.search(r'[a-z]', password):
            return jsonify('Password must contain at least one lowercase letter'), 400
        if not re.search(r'\d', password):
            return jsonify('Password must contain at least one number'), 400
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Check if customer already exists
            existing_customer = execute_query(
                'SELECT id FROM users WHERE email = %s',
                (email,),
                'one'
            )
            
            if existing_customer['success'] and existing_customer['data']:
                return jsonify('Customer already exists with this email'), 409
            
            # Create user account
            user_id = str(uuid.uuid4())
            customer_id = str(uuid.uuid4())
            
            # Insert user
            user_result = execute_query('''
                INSERT INTO users (id, email, password_hash, role, status, profile, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING created_at
            ''', (
                user_id,
                email,
                UserAuth.hash_password(password),
                'customer',
                'active',
                json.dumps({
                    'first_name': first_name,
                    'last_name': last_name,
                    'registration_source': 'customer_portal'
                })
            ), 'one')
            
            if user_result['success']:
                # Insert customer profile
                customer_result = execute_query('''
                    INSERT INTO customers (id, user_id, customer_id, first_name, last_name, email, phone, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING created_at
                ''', (
                    str(uuid.uuid4()),
                    user_id,
                    customer_id,
                    first_name,
                    last_name,
                    email,
                    phone
                ), 'one')
                
                if customer_result['success']:
                    # Generate welcome token
                    from utils.auth_decorators import generate_jwt_token
                    token = generate_jwt_token({
                        'id': user_id,
                        'email': email,
                        'role': 'customer',
                        'customer_id': customer_id
                    })
                    
                    # Log registration
                    SecurityUtils.log_security_event(user_id, 'customer_registered', {
                        'email': email,
                        'registration_method': 'self_registration'
                    })
                    
                    return jsonify({
                        'message': 'Customer registered successfully',
                        'customer': {
                            'id': customer_id,
                            'user_id': user_id,
                            'email': email,
                            'first_name': first_name,
                            'last_name': last_name,
                            'phone': phone,
                            'created_at': user_result['data'][0].isoformat() if user_result['data'][0] else None
                        },
                        'token': token,
                        'next_steps': [
                            'Complete your profile',
                            'Explore our protection plans',
                            'Get your first quote'
                        ]
                    }), 201
                else:
                    # Rollback user creation if customer creation failed
                    execute_query('DELETE FROM users WHERE id = %s', (user_id,), 'none')
                    return jsonify('Failed to create customer profile'), 500
            else:
                return jsonify('Failed to create user account'), 500
        else:
            return jsonify('Database not available for registration'), 503

    except Exception as e:
        return jsonify(f'Registration failed: {str(e)}'), 500

@customer_bp.route('/profile', methods=['GET'])
@token_required
def get_customer_profile():
    """Get customer profile and account information"""
    try:
        user_id = request.current_user.get('user_id')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get customer profile with related data
            result = execute_query('''
                SELECT 
                    u.id as user_id, u.email, u.created_at as user_created_at, u.last_login,
                    c.id, c.customer_id, c.first_name, c.last_name, c.phone, 
                    c.billing_address, c.created_at,
                    COUNT(DISTINCT t.id) as total_transactions,
                    COUNT(DISTINCT p.id) as total_policies,
                    COALESCE(SUM(CASE WHEN t.status = 'completed' THEN t.amount ELSE 0 END), 0) as total_spent
                FROM users u
                LEFT JOIN customers c ON u.id = c.user_id
                LEFT JOIN transactions t ON c.customer_id = t.customer_id
                LEFT JOIN policies p ON c.customer_id = p.customer_id
                WHERE u.id = %s
                GROUP BY u.id, u.email, u.created_at, u.last_login, c.id, c.customer_id, 
                         c.first_name, c.last_name, c.phone, c.billing_address, c.created_at
            ''', (user_id,), 'one')
            
            if result['success'] and result['data']:
                profile = dict(result['data'])
                
                # Format dates
                profile['user_created_at'] = profile['user_created_at'].isoformat() if profile['user_created_at'] else None
                profile['created_at'] = profile['created_at'].isoformat() if profile['created_at'] else None
                profile['last_login'] = profile['last_login'].isoformat() if profile['last_login'] else None
                
                # Parse billing address if exists
                if profile['billing_address']:
                    try:
                        profile['billing_address'] = json.loads(profile['billing_address']) if isinstance(profile['billing_address'], str) else profile['billing_address']
                    except (json.JSONDecodeError, TypeError):
                        profile['billing_address'] = {}
                
                # Calculate metrics
                profile['account_metrics'] = {
                    'total_transactions': profile['total_transactions'],
                    'total_policies': profile['total_policies'],
                    'total_spent': float(profile['total_spent']),
                    'customer_since': profile['created_at'],
                    'membership_duration_days': (datetime.now(timezone.utc) - profile['created_at'].replace(tzinfo=timezone.utc)).days if profile['created_at'] else 0
                }
                
                return jsonify(profile)
            else:
                return jsonify('Customer profile not found'), 404
        else:
            # Fallback to basic user info
            user_info = {
                'user_id': user_id,
                'email': request.current_user.get('email'),
                'role': request.current_user.get('role'),
                'source': 'token_data'
            }
            return jsonify(user_info)

    except Exception as e:
        return jsonify(f'Failed to get profile: {str(e)}'), 500

@customer_bp.route('/profile', methods=['PUT'])
@token_required
def update_customer_profile():
    """Update customer profile information"""
    try:
        data = request.get_json()
        user_id = request.current_user.get('user_id')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get current customer record
            customer_result = execute_query(
                'SELECT id, customer_id FROM customers WHERE user_id = %s',
                (user_id,),
                'one'
            )
            
            if not customer_result['success'] or not customer_result['data']:
                return jsonify('Customer record not found'), 404
            
            customer_record_id = customer_result['data'][0]
            
            # Prepare update fields
            update_fields = []
            update_values = []
            
            # Fields that can be updated
            updatable_fields = {
                'first_name': data.get('first_name'),
                'last_name': data.get('last_name'),
                'phone': data.get('phone'),
                'billing_address': json.dumps(data.get('billing_address')) if data.get('billing_address') else None
            }
            
            for field, value in updatable_fields.items():
                if value is not None:
                    update_fields.append(f"{field} = %s")
                    update_values.append(value)
            
            if update_fields:
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                update_values.append(customer_record_id)
                
                query = f"UPDATE customers SET {', '.join(update_fields)} WHERE id = %s RETURNING updated_at"
                result = execute_query(query, tuple(update_values), 'one')
                
                if result['success']:
                    # Also update user profile if email change requested
                    if data.get('email') and data['email'] != request.current_user.get('email'):
                        email_result = execute_query('''
                            UPDATE users 
                            SET email = %s, updated_at = CURRENT_TIMESTAMP 
                            WHERE id = %s
                        ''', (data['email'].lower().strip(), user_id), 'none')
                        
                        if not email_result['success']:
                            return jsonify('Failed to update email'), 500
                    
                    # Log profile update
                    SecurityUtils.log_security_event(user_id, 'profile_updated', {
                        'updated_fields': list(updatable_fields.keys())
                    })
                    
                    return jsonify({
                        'message': 'Profile updated successfully',
                        'updated_at': result['data'][0].isoformat() if result['data'][0] else None,
                        'updated_fields': [field for field, value in updatable_fields.items() if value is not None]
                    })
                else:
                    return jsonify('Failed to update profile'), 500
            else:
                return jsonify('No valid fields to update'), 400
        else:
            return jsonify('Database not available for profile update'), 503

    except Exception as e:
        return jsonify(f'Profile update failed: {str(e)}'), 500

# ================================
# CUSTOMER DASHBOARD
# ================================

@customer_bp.route('/dashboard', methods=['GET'])
@token_required
def get_customer_dashboard():
    """Get customer dashboard with overview data"""
    try:
        user_id = request.current_user.get('user_id')
        
        db_manager = get_db_manager()
        dashboard_data = {
            'overview': {
                'total_policies': 0,
                'active_policies': 0,
                'total_spent': 0.0,
                'pending_claims': 0,
                'last_transaction': None
            },
            'recent_activity': [],
            'active_policies': [],
            'quick_actions': [
                {'action': 'get_quote', 'title': 'Get New Quote', 'description': 'Get a quote for a new protection plan'},
                {'action': 'file_claim', 'title': 'File Claim', 'description': 'File a new claim for existing policy'},
                {'action': 'view_documents', 'title': 'View Documents', 'description': 'Access your policy documents'},
                {'action': 'contact_support', 'title': 'Contact Support', 'description': 'Get help from our support team'}
            ],
            'notifications': []
        }
        
        if db_manager.available:
            # Get customer ID
            customer_result = execute_query(
                'SELECT customer_id FROM customers WHERE user_id = %s',
                (user_id,),
                'one'
            )
            
            if customer_result['success'] and customer_result['data']:
                customer_id = customer_result['data'][0]
                
                # Get policy summary
                policy_summary = execute_query('''
                    SELECT 
                        COUNT(*) as total_policies,
                        COUNT(*) FILTER (WHERE status = 'active') as active_policies,
                        COUNT(*) FILTER (WHERE status = 'pending') as pending_policies
                    FROM policies
                    WHERE customer_id = %s
                ''', (customer_id,), 'one')
                
                if policy_summary['success'] and policy_summary['data']:
                    stats = policy_summary['data']
                    dashboard_data['overview']['total_policies'] = stats[0]
                    dashboard_data['overview']['active_policies'] = stats[1]
                    dashboard_data['overview']['pending_policies'] = stats[2]
                
                # Get transaction summary
                transaction_summary = execute_query('''
                    SELECT 
                        COALESCE(SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END), 0) as total_spent,
                        MAX(CASE WHEN status = 'completed' THEN created_at ELSE NULL END) as last_transaction_date
                    FROM transactions
                    WHERE customer_id = %s
                ''', (customer_id,), 'one')
                
                if transaction_summary['success'] and transaction_summary['data']:
                    stats = transaction_summary['data']
                    dashboard_data['overview']['total_spent'] = float(stats[0])
                    dashboard_data['overview']['last_transaction'] = stats[1].isoformat() if stats[1] else None
                
                # Get recent activity
                recent_activity = execute_query('''
                    SELECT 
                        'transaction' as activity_type,
                        transaction_number as reference,
                        amount,
                        status,
                        created_at
                    FROM transactions
                    WHERE customer_id = %s
                    UNION ALL
                    SELECT 
                        'policy' as activity_type,
                        policy_number as reference,
                        NULL as amount,
                        status,
                        created_at
                    FROM policies
                    WHERE customer_id = %s
                    ORDER BY created_at DESC
                    LIMIT 10
                ''', (customer_id, customer_id))
                
                if recent_activity['success']:
                    for activity in recent_activity['data']:
                        dashboard_data['recent_activity'].append({
                            'type': activity[0],
                            'reference': activity[1],
                            'amount': float(activity[2]) if activity[2] else None,
                            'status': activity[3],
                            'date': activity[4].isoformat() if activity[4] else None
                        })
                
                # Get active policies
                active_policies = execute_query('''
                    SELECT policy_number, product_type, start_date, end_date, status, coverage_amount
                    FROM policies
                    WHERE customer_id = %s AND status = 'active'
                    ORDER BY start_date DESC
                    LIMIT 5
                ''', (customer_id,))
                
                if active_policies['success']:
                    for policy in active_policies['data']:
                        dashboard_data['active_policies'].append({
                            'policy_number': policy[0],
                            'product_type': policy[1],
                            'start_date': policy[2].isoformat() if policy[2] else None,
                            'end_date': policy[3].isoformat() if policy[3] else None,
                            'status': policy[4],
                            'coverage_amount': float(policy[5]) if policy[5] else 0.0
                        })
                
                # Generate notifications
                if dashboard_data['overview']['active_policies'] == 0:
                    dashboard_data['notifications'].append({
                        'type': 'info',
                        'title': 'No Active Policies',
                        'message': 'You don\'t have any active policies. Get a quote to get started!',
                        'action': 'get_quote'
                    })
                
                # Check for expiring policies
                expiring_policies = execute_query('''
                    SELECT COUNT(*)
                    FROM policies
                    WHERE customer_id = %s AND status = 'active' 
                    AND end_date <= CURRENT_DATE + INTERVAL '30 days'
                ''', (customer_id,), 'one')
                
                if expiring_policies['success'] and expiring_policies['data'] and expiring_policies['data'][0] > 0:
                    dashboard_data['notifications'].append({
                        'type': 'warning',
                        'title': 'Policies Expiring Soon',
                        'message': f'{expiring_policies["data"][0]} policy(ies) expire within 30 days',
                        'action': 'renew_policy'
                    })
        
        return jsonify(dashboard_data)
        
    except Exception as e:
        return jsonify(f'Failed to load dashboard: {str(e)}'), 500

# ================================
# QUOTES & POLICIES
# ================================

@customer_bp.route('/quotes', methods=['GET'])
@token_required
def get_customer_quotes():
    """Get customer's quote history"""
    try:
        user_id = request.current_user.get('user_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        product_type = request.args.get('product_type')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get customer ID
            customer_result = execute_query(
                'SELECT customer_id FROM customers WHERE user_id = %s',
                (user_id,),
                'one'
            )
            
            if customer_result['success'] and customer_result['data']:
                customer_id = customer_result['data'][0]
                
                # Build query with filters
                where_conditions = ['customer_id = %s']
                params = [customer_id]
                
                if product_type:
                    where_conditions.append("quote_data->>'product_type' = %s")
                    params.append(product_type)
                
                where_clause = ' AND '.join(where_conditions)
                
                # Get total count
                count_result = execute_query(
                    f"SELECT COUNT(*) FROM quotes WHERE {where_clause}",
                    tuple(params),
                    'one'
                )
                total_count = count_result['data'][0] if count_result['success'] and count_result['data'] else 0
                
                # Get paginated quotes
                offset = (page - 1) * per_page
                quotes_result = execute_query(f'''
                    SELECT 
                        quote_id, quote_data, total_price, status, 
                        created_at, expires_at, converted_to_policy
                    FROM quotes
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                ''', tuple(params + [per_page, offset]))
                
                if quotes_result['success']:
                    quotes = []
                    for quote in quotes_result['data']:
                        quote_dict = {
                            'quote_id': quote[0],
                            'quote_data': quote[1] if quote[1] else {},
                            'total_price': float(quote[2]) if quote[2] else 0.0,
                            'status': quote[3],
                            'created_at': quote[4].isoformat() if quote[4] else None,
                            'expires_at': quote[5].isoformat() if quote[5] else None,
                            'converted_to_policy': quote[6]
                        }
                        quotes.append(quote_dict)
                    
                    return jsonify({
                        'quotes': quotes,
                        'pagination': {
                            'page': page,
                            'per_page': per_page,
                            'total': total_count,
                            'pages': (total_count + per_page - 1) // per_page
                        },
                        'filters': {'product_type': product_type}
                    })
                else:
                    return jsonify('Failed to fetch quotes'), 500
            else:
                return jsonify('Customer record not found'), 404
        else:
            # Return empty quotes when database not available
            return jsonify({
                'quotes': [],
                'pagination': {'page': 1, 'per_page': per_page, 'total': 0, 'pages': 0},
                'source': 'database_unavailable'
            })

    except Exception as e:
        return jsonify(f'Failed to get quotes: {str(e)}'), 500

@customer_bp.route('/quotes/<quote_id>', methods=['GET'])
@token_required
def get_quote_details(quote_id):
    """Get detailed information about a specific quote"""
    try:
        user_id = request.current_user.get('user_id')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get customer ID and verify quote ownership
            result = execute_query('''
                SELECT 
                    q.quote_id, q.quote_data, q.total_price, q.status, 
                    q.created_at, q.expires_at, q.converted_to_policy,
                    c.customer_id
                FROM quotes q
                JOIN customers c ON q.customer_id = c.customer_id
                WHERE q.quote_id = %s AND c.user_id = %s
            ''', (quote_id, user_id), 'one')
            
            if result['success'] and result['data']:
                quote = dict(result['data'])
                
                # Format dates
                quote['created_at'] = quote['created_at'].isoformat() if quote['created_at'] else None
                quote['expires_at'] = quote['expires_at'].isoformat() if quote['expires_at'] else None
                
                # Calculate quote status
                if quote['expires_at']:
                    expires_at = datetime.fromisoformat(quote['expires_at'].replace('Z', '+00:00'))
                    if datetime.now(timezone.utc) > expires_at:
                        quote['is_expired'] = True
                    else:
                        quote['is_expired'] = False
                        quote['expires_in_hours'] = (expires_at - datetime.now(timezone.utc)).total_seconds() / 3600
                
                quote['total_price'] = float(quote['total_price']) if quote['total_price'] else 0.0
                
                return jsonify(quote)
            else:
                return jsonify('Quote not found or access denied'), 404
        else:
            return jsonify('Database not available'), 503

    except Exception as e:
        return jsonify(f'Failed to get quote details: {str(e)}'), 500

@customer_bp.route('/policies', methods=['GET'])
@token_required
def get_customer_policies():
    """Get customer's policies"""
    try:
        user_id = request.current_user.get('user_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status_filter = request.args.get('status')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get customer ID
            customer_result = execute_query(
                'SELECT customer_id FROM customers WHERE user_id = %s',
                (user_id,),
                'one'
            )
            
            if customer_result['success'] and customer_result['data']:
                customer_id = customer_result['data'][0]
                
                # Build query with filters
                where_conditions = ['customer_id = %s']
                params = [customer_id]
                
                if status_filter:
                    where_conditions.append("status = %s")
                    params.append(status_filter)
                
                where_clause = ' AND '.join(where_conditions)
                
                # Get total count
                count_result = execute_query(
                    f"SELECT COUNT(*) FROM policies WHERE {where_clause}",
                    tuple(params),
                    'one'
                )
                total_count = count_result['data'][0] if count_result['success'] and count_result['data'] else 0
                
                # Get paginated policies
                offset = (page - 1) * per_page
                policies_result = execute_query(f'''
                    SELECT 
                        policy_number, product_type, coverage_amount, premium_amount,
                        start_date, end_date, status, payment_status, created_at
                    FROM policies
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                ''', tuple(params + [per_page, offset]))
                
                if policies_result['success']:
                    policies = []
                    for policy in policies_result['data']:
                        policy_dict = {
                            'policy_number': policy[0],
                            'product_type': policy[1],
                            'coverage_amount': float(policy[2]) if policy[2] else 0.0,
                            'premium_amount': float(policy[3]) if policy[3] else 0.0,
                            'start_date': policy[4].isoformat() if policy[4] else None,
                            'end_date': policy[5].isoformat() if policy[5] else None,
                            'status': policy[6],
                            'payment_status': policy[7],
                            'created_at': policy[8].isoformat() if policy[8] else None
                        }
                        
                        # Calculate days until expiration
                        if policy[5]:  # end_date
                            days_until_expiry = (policy[5] - datetime.now().date()).days
                            policy_dict['days_until_expiry'] = days_until_expiry
                            policy_dict['expires_soon'] = days_until_expiry <= 30
                        
                        policies.append(policy_dict)
                    
                    return jsonify({
                        'policies': policies,
                        'pagination': {
                            'page': page,
                            'per_page': per_page,
                            'total': total_count,
                            'pages': (total_count + per_page - 1) // per_page
                        },
                        'filters': {'status': status_filter}
                    })
                else:
                    return jsonify('Failed to fetch policies'), 500
            else:
                return jsonify('Customer record not found'), 404
        else:
            # Return empty policies when database not available
            return jsonify({
                'policies': [],
                'pagination': {'page': 1, 'per_page': per_page, 'total': 0, 'pages': 0},
                'source': 'database_unavailable'
            })

    except Exception as e:
        return jsonify(f'Failed to get policies: {str(e)}'), 500

@customer_bp.route('/policies/<policy_number>', methods=['GET'])
@token_required
def get_policy_details(policy_number):
    """Get detailed information about a specific policy"""
    try:
        user_id = request.current_user.get('user_id')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get policy details and verify ownership
            result = execute_query('''
                SELECT 
                    p.policy_number, p.product_type, p.coverage_amount, p.premium_amount,
                    p.start_date, p.end_date, p.status, p.payment_status, p.created_at,
                    p.policy_terms, p.coverage_details, p.deductible_amount,
                    c.customer_id, c.first_name, c.last_name
                FROM policies p
                JOIN customers c ON p.customer_id = c.customer_id
                WHERE p.policy_number = %s AND c.user_id = %s
            ''', (policy_number, user_id), 'one')
            
            if result['success'] and result['data']:
                policy = dict(result['data'])
                
                # Format dates
                policy['start_date'] = policy['start_date'].isoformat() if policy['start_date'] else None
                policy['end_date'] = policy['end_date'].isoformat() if policy['end_date'] else None
                policy['created_at'] = policy['created_at'].isoformat() if policy['created_at'] else None
                
                # Parse JSON fields
                if policy['policy_terms']:
                    try:
                        policy['policy_terms'] = json.loads(policy['policy_terms']) if isinstance(policy['policy_terms'], str) else policy['policy_terms']
                    except (json.JSONDecodeError, TypeError):
                        policy['policy_terms'] = {}
                
                if policy['coverage_details']:
                    try:
                        policy['coverage_details'] = json.loads(policy['coverage_details']) if isinstance(policy['coverage_details'], str) else policy['coverage_details']
                    except (json.JSONDecodeError, TypeError):
                        policy['coverage_details'] = {}
                
                # Calculate policy metrics
                if policy['end_date']:
                    end_date = datetime.fromisoformat(policy['end_date'].replace('Z', '+00:00'))
                    days_remaining = (end_date.date() - datetime.now().date()).days
                    policy['days_remaining'] = days_remaining
                    policy['expires_soon'] = days_remaining <= 30
                    policy['is_expired'] = days_remaining < 0
                
                # Convert amounts to float
                policy['coverage_amount'] = float(policy['coverage_amount']) if policy['coverage_amount'] else 0.0
                policy['premium_amount'] = float(policy['premium_amount']) if policy['premium_amount'] else 0.0
                policy['deductible_amount'] = float(policy['deductible_amount']) if policy['deductible_amount'] else 0.0
                
                # Get related claims
                claims_result = execute_query('''
                    SELECT claim_number, claim_type, amount_claimed, status, filed_date
                    FROM claims
                    WHERE policy_number = %s
                    ORDER BY filed_date DESC
                ''', (policy_number,))
                
                policy['claims'] = []
                if claims_result['success']:
                    for claim in claims_result['data']:
                        policy['claims'].append({
                            'claim_number': claim[0],
                            'claim_type': claim[1],
                            'amount_claimed': float(claim[2]) if claim[2] else 0.0,
                            'status': claim[3],
                            'filed_date': claim[4].isoformat() if claim[4] else None
                        })
                
                return jsonify(policy)
            else:
                return jsonify('Policy not found or access denied'), 404
        else:
            return jsonify('Database not available'), 503

    except Exception as e:
        return jsonify(f'Failed to get policy details: {str(e)}'), 500

# ================================
# TRANSACTIONS & PAYMENTS
# ================================

@customer_bp.route('/transactions', methods=['GET'])
@token_required
def get_customer_transactions():
    """Get customer's transaction history"""
    try:
        user_id = request.current_user.get('user_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        transaction_type = request.args.get('type')
        status_filter = request.args.get('status')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get customer ID
            customer_result = execute_query(
                'SELECT customer_id FROM customers WHERE user_id = %s',
                (user_id,),
                'one'
            )
            
            if customer_result['success'] and customer_result['data']:
                customer_id = customer_result['data'][0]
                
                # Build query with filters
                where_conditions = ['customer_id = %s']
                params = [customer_id]
                
                if transaction_type:
                    where_conditions.append("type = %s")
                    params.append(transaction_type)
                
                if status_filter:
                    where_conditions.append("status = %s")
                    params.append(status_filter)
                
                where_clause = ' AND '.join(where_conditions)
                
                # Get total count
                count_result = execute_query(
                    f"SELECT COUNT(*) FROM transactions WHERE {where_clause}",
                    tuple(params),
                    'one'
                )
                total_count = count_result['data'][0] if count_result['success'] and count_result['data'] else 0
                
                # Get paginated transactions
                offset = (page - 1) * per_page
                transactions_result = execute_query(f'''
                    SELECT 
                        transaction_number, type, amount, currency, status,
                        payment_method, created_at, processed_at, description
                    FROM transactions
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                ''', tuple(params + [per_page, offset]))
                
                if transactions_result['success']:
                    transactions = []
                    for txn in transactions_result['data']:
                        transaction_dict = {
                            'transaction_number': txn[0],
                            'type': txn[1],
                            'amount': float(txn[2]) if txn[2] else 0.0,
                            'currency': txn[3] or 'USD',
                            'status': txn[4],
                            'payment_method': txn[5] if txn[5] else {},
                            'created_at': txn[6].isoformat() if txn[6] else None,
                            'processed_at': txn[7].isoformat() if txn[7] else None,
                            'description': txn[8]
                        }
                        
                        # Parse payment method if it's a JSON string
                        if isinstance(transaction_dict['payment_method'], str):
                            try:
                                transaction_dict['payment_method'] = json.loads(transaction_dict['payment_method'])
                            except (json.JSONDecodeError, TypeError):
                                transaction_dict['payment_method'] = {'method': transaction_dict['payment_method']}
                        
                        transactions.append(transaction_dict)
                    
                    return jsonify({
                        'transactions': transactions,
                        'pagination': {
                            'page': page,
                            'per_page': per_page,
                            'total': total_count,
                            'pages': (total_count + per_page - 1) // per_page
                        },
                        'filters': {
                            'type': transaction_type,
                            'status': status_filter
                        }
                    })
                else:
                    return jsonify('Failed to fetch transactions'), 500
            else:
                return jsonify('Customer record not found'), 404
        else:
            return jsonify({
                'transactions': [],
                'pagination': {'page': 1, 'per_page': per_page, 'total': 0, 'pages': 0},
                'source': 'database_unavailable'
            })

    except Exception as e:
        return jsonify(f'Failed to get transactions: {str(e)}'), 500

@customer_bp.route('/transactions/<transaction_number>', methods=['GET'])
@token_required
def get_transaction_details(transaction_number):
    """Get detailed information about a specific transaction"""
    try:
        user_id = request.current_user.get('user_id')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get transaction details and verify ownership
            result = execute_query('''
                SELECT 
                    t.transaction_number, t.type, t.amount, t.currency, t.status,
                    t.payment_method, t.processor_response, t.created_at, t.processed_at,
                    t.description, t.metadata, t.fees, t.taxes,
                    c.customer_id, c.first_name, c.last_name
                FROM transactions t
                JOIN customers c ON t.customer_id = c.customer_id
                WHERE t.transaction_number = %s AND c.user_id = %s
            ''', (transaction_number, user_id), 'one')
            
            if result['success'] and result['data']:
                transaction = dict(result['data'])
                
                # Format dates
                transaction['created_at'] = transaction['created_at'].isoformat() if transaction['created_at'] else None
                transaction['processed_at'] = transaction['processed_at'].isoformat() if transaction['processed_at'] else None
                
                # Parse JSON fields
                json_fields = ['payment_method', 'processor_response', 'metadata', 'fees', 'taxes']
                for field in json_fields:
                    if transaction[field]:
                        try:
                            transaction[field] = json.loads(transaction[field]) if isinstance(transaction[field], str) else transaction[field]
                        except (json.JSONDecodeError, TypeError):
                            transaction[field] = {}
                    else:
                        transaction[field] = {}
                
                # Convert amount to float
                transaction['amount'] = float(transaction['amount']) if transaction['amount'] else 0.0
                
                return jsonify(transaction)
            else:
                return jsonify('Transaction not found or access denied'), 404
        else:
            return jsonify('Database not available'), 503

    except Exception as e:
        return jsonify(f'Failed to get transaction details: {str(e)}'), 500

# ================================
# DOCUMENTS & DOWNLOADS
# ================================

@customer_bp.route('/documents', methods=['GET'])
@token_required
def get_customer_documents():
    """Get customer's documents (policies, contracts, receipts)"""
    try:
        user_id = request.current_user.get('user_id')
        document_type = request.args.get('type')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get customer ID
            customer_result = execute_query(
                'SELECT customer_id FROM customers WHERE user_id = %s',
                (user_id,),
                'one'
            )
            
            if customer_result['success'] and customer_result['data']:
                customer_id = customer_result['data'][0]
                
                # Build query with filters
                where_conditions = ['customer_id = %s']
                params = [customer_id]
                
                if document_type:
                    where_conditions.append("document_type = %s")
                    params.append(document_type)
                
                where_clause = ' AND '.join(where_conditions)
                
                # Get documents
                documents_result = execute_query(f'''
                    SELECT 
                        document_id, document_type, document_name, file_url,
                        file_size, created_at, policy_number, transaction_number
                    FROM customer_documents
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                ''', tuple(params))
                
                if documents_result['success']:
                    documents = []
                    for doc in documents_result['data']:
                        document_dict = {
                            'document_id': doc[0],
                            'document_type': doc[1],
                            'document_name': doc[2],
                            'file_url': doc[3],
                            'file_size': doc[4],
                            'created_at': doc[5].isoformat() if doc[5] else None,
                            'policy_number': doc[6],
                            'transaction_number': doc[7]
                        }
                        documents.append(document_dict)
                    
                    # Group documents by type
                    grouped_documents = {}
                    for doc in documents:
                        doc_type = doc['document_type']
                        if doc_type not in grouped_documents:
                            grouped_documents[doc_type] = []
                        grouped_documents[doc_type].append(doc)
                    
                    return jsonify({
                        'documents': documents,
                        'grouped_documents': grouped_documents,
                        'total_documents': len(documents),
                        'available_types': list(grouped_documents.keys())
                    })
                else:
                    return jsonify('Failed to fetch documents'), 500
            else:
                return jsonify('Customer record not found'), 404
        else:
            # Return sample documents when database not available
            sample_documents = [
                {
                    'document_id': 'DOC-001',
                    'document_type': 'policy',
                    'document_name': 'Sample Policy Document.pdf',
                    'file_url': '/documents/sample-policy.pdf',
                    'file_size': 245760,
                    'created_at': datetime.now(timezone.utc).isoformat() + 'Z',
                    'policy_number': 'POL-001',
                    'transaction_number': None
                }
            ]
            
            return jsonify({
                'documents': sample_documents,
                'total_documents': len(sample_documents),
                'source': 'sample_data'
            })

    except Exception as e:
        return jsonify(f'Failed to get documents: {str(e)}'), 500

@customer_bp.route('/documents/<document_id>/download', methods=['GET'])
@token_required
def download_document(document_id):
    """Download a specific document"""
    try:
        user_id = request.current_user.get('user_id')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Verify document ownership and get file info
            result = execute_query('''
                SELECT 
                    cd.document_name, cd.file_url, cd.document_type,
                    c.customer_id
                FROM customer_documents cd
                JOIN customers c ON cd.customer_id = c.customer_id
                WHERE cd.document_id = %s AND c.user_id = %s
            ''', (document_id, user_id), 'one')
            
            if result['success'] and result['data']:
                document_name, file_url, document_type, customer_id = result['data']
                
                # Log document access
                SecurityUtils.log_security_event(user_id, 'document_downloaded', {
                    'document_id': document_id,
                    'document_type': document_type,
                    'customer_id': customer_id
                })
                
                # In production, this would redirect to a secure file URL or stream the file
                # For now, return the file URL
                return jsonify({
                    'document_name': document_name,
                    'download_url': file_url,
                    'document_type': document_type,
                    'message': 'Document ready for download'
                })
            else:
                return jsonify('Document not found or access denied'), 404
        else:
            return jsonify('Database not available'), 503

    except Exception as e:
        return jsonify(f'Failed to download document: {str(e)}'), 500

# ================================
# SUPPORT & CLAIMS
# ================================

@customer_bp.route('/support/tickets', methods=['GET'])
@token_required
def get_support_tickets():
    """Get customer's support tickets"""
    try:
        user_id = request.current_user.get('user_id')
        status_filter = request.args.get('status')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get customer ID
            customer_result = execute_query(
                'SELECT customer_id FROM customers WHERE user_id = %s',
                (user_id,),
                'one'
            )
            
            if customer_result['success'] and customer_result['data']:
                customer_id = customer_result['data'][0]
                
                # Build query with filters
                where_conditions = ['customer_id = %s']
                params = [customer_id]
                
                if status_filter:
                    where_conditions.append("status = %s")
                    params.append(status_filter)
                
                where_clause = ' AND '.join(where_conditions)
                
                # Get support tickets
                tickets_result = execute_query(f'''
                    SELECT 
                        ticket_number, subject, status, priority, category,
                        created_at, updated_at, last_response_at
                    FROM support_tickets
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                ''', tuple(params))
                
                if tickets_result['success']:
                    tickets = []
                    for ticket in tickets_result['data']:
                        ticket_dict = {
                            'ticket_number': ticket[0],
                            'subject': ticket[1],
                            'status': ticket[2],
                            'priority': ticket[3],
                            'category': ticket[4],
                            'created_at': ticket[5].isoformat() if ticket[5] else None,
                            'updated_at': ticket[6].isoformat() if ticket[6] else None,
                            'last_response_at': ticket[7].isoformat() if ticket[7] else None
                        }
                        tickets.append(ticket_dict)
                    
                    return jsonify({
                        'tickets': tickets,
                        'total_tickets': len(tickets),
                        'filters': {'status': status_filter}
                    })
                else:
                    return jsonify('Failed to fetch support tickets'), 500
            else:
                return jsonify('Customer record not found'), 404
        else:
            return jsonify({
                'tickets': [],
                'total_tickets': 0,
                'source': 'database_unavailable'
            })

    except Exception as e:
        return jsonify(f'Failed to get support tickets: {str(e)}'), 500

@customer_bp.route('/support/tickets', methods=['POST'])
@token_required
def create_support_ticket():
    """Create a new support ticket"""
    try:
        data = request.get_json()
        user_id = request.current_user.get('user_id')
        
        # Validate required fields
        required_fields = ['subject', 'description', 'category']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify(f"Missing fields: {', '.join(missing_fields)}"), 400
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get customer ID
            customer_result = execute_query(
                'SELECT customer_id FROM customers WHERE user_id = %s',
                (user_id,),
                'one'
            )
            
            if customer_result['success'] and customer_result['data']:
                customer_id = customer_result['data'][0]
                
                # Generate ticket number
                ticket_number = f"TKT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
                
                # Create support ticket
                result = execute_query('''
                    INSERT INTO support_tickets 
                    (ticket_number, customer_id, subject, description, category, priority, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING created_at
                ''', (
                    ticket_number,
                    customer_id,
                    data['subject'],
                    data['description'],
                    data['category'],
                    data.get('priority', 'medium'),
                    'open'
                ), 'one')
                
                if result['success']:
                    # Log ticket creation
                    SecurityUtils.log_security_event(user_id, 'support_ticket_created', {
                        'ticket_number': ticket_number,
                        'category': data['category']
                    })
                    
                    return jsonify({
                        'message': 'Support ticket created successfully',
                        'ticket': {
                            'ticket_number': ticket_number,
                            'subject': data['subject'],
                            'category': data['category'],
                            'priority': data.get('priority', 'medium'),
                            'status': 'open',
                            'created_at': result['data'][0].isoformat() if result['data'][0] else None
                        },
                        'next_steps': [
                            'You will receive email updates on ticket progress',
                            'Expected initial response within 24 hours',
                            'Check your customer portal for updates'
                        ]
                    }), 201
                else:
                    return jsonify('Failed to create support ticket'), 500
            else:
                return jsonify('Customer record not found'), 404
        else:
            return jsonify('Database not available for ticket creation'), 503

    except Exception as e:
        return jsonify(f'Failed to create support ticket: {str(e)}'), 500

@customer_bp.route('/claims', methods=['GET'])
@token_required
def get_customer_claims():
    """Get customer's claims"""
    try:
        user_id = request.current_user.get('user_id')
        status_filter = request.args.get('status')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get customer ID
            customer_result = execute_query(
                'SELECT customer_id FROM customers WHERE user_id = %s',
                (user_id,),
                'one'
            )
            
            if customer_result['success'] and customer_result['data']:
                customer_id = customer_result['data'][0]
                
                # Build query with filters
                where_conditions = ['c.customer_id = %s']
                params = [customer_id]
                
                if status_filter:
                    where_conditions.append("cl.status = %s")
                    params.append(status_filter)
                
                where_clause = ' AND '.join(where_conditions)
                
                # Get claims with policy information
                claims_result = execute_query(f'''
                    SELECT 
                        cl.claim_number, cl.claim_type, cl.amount_claimed, 
                        cl.amount_approved, cl.status, cl.filed_date, cl.processed_date,
                        p.policy_number, p.product_type
                    FROM claims cl
                    JOIN policies p ON cl.policy_number = p.policy_number
                    JOIN customers c ON p.customer_id = c.customer_id
                    WHERE {where_clause}
                    ORDER BY cl.filed_date DESC
                ''', tuple(params))
                
                if claims_result['success']:
                    claims = []
                    for claim in claims_result['data']:
                        claim_dict = {
                            'claim_number': claim[0],
                            'claim_type': claim[1],
                            'amount_claimed': float(claim[2]) if claim[2] else 0.0,
                            'amount_approved': float(claim[3]) if claim[3] else 0.0,
                            'status': claim[4],
                            'filed_date': claim[5].isoformat() if claim[5] else None,
                            'processed_date': claim[6].isoformat() if claim[6] else None,
                            'policy_number': claim[7],
                            'product_type': claim[8]
                        }
                        claims.append(claim_dict)
                    
                    return jsonify({
                        'claims': claims,
                        'total_claims': len(claims),
                        'filters': {'status': status_filter}
                    })
                else:
                    return jsonify('Failed to fetch claims'), 500
            else:
                return jsonify('Customer record not found'), 404
        else:
            return jsonify({
                'claims': [],
                'total_claims': 0,
                'source': 'database_unavailable'
            })

    except Exception as e:
        return jsonify(f'Failed to get claims: {str(e)}'), 500

# ================================
# CUSTOMER PREFERENCES & SETTINGS
# ================================

@customer_bp.route('/preferences', methods=['GET'])
@token_required
def get_customer_preferences():
    """Get customer preferences and settings"""
    try:
        user_id = request.current_user.get('user_id')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get customer preferences
            result = execute_query('''
                SELECT 
                    email_notifications, sms_notifications, push_notifications,
                    marketing_emails, newsletter_subscription, language_preference,
                    currency_preference, timezone_preference
                FROM customer_preferences
                WHERE user_id = %s
            ''', (user_id,), 'one')
            
            if result['success'] and result['data']:
                preferences = dict(result['data'])
                return jsonify(preferences)
            else:
                # Return default preferences
                default_preferences = {
                    'email_notifications': True,
                    'sms_notifications': False,
                    'push_notifications': True,
                    'marketing_emails': False,
                    'newsletter_subscription': False,
                    'language_preference': 'en',
                    'currency_preference': 'USD',
                    'timezone_preference': 'UTC'
                }
                return jsonify(default_preferences)
        else:
            return jsonify('Database not available'), 503

    except Exception as e:
        return jsonify(f'Failed to get preferences: {str(e)}'), 500

@customer_bp.route('/preferences', methods=['PUT'])
@token_required
def update_customer_preferences():
    """Update customer preferences"""
    try:
        data = request.get_json()
        user_id = request.current_user.get('user_id')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Prepare update fields
            updatable_fields = {
                'email_notifications': data.get('email_notifications'),
                'sms_notifications': data.get('sms_notifications'),
                'push_notifications': data.get('push_notifications'),
                'marketing_emails': data.get('marketing_emails'),
                'newsletter_subscription': data.get('newsletter_subscription'),
                'language_preference': data.get('language_preference'),
                'currency_preference': data.get('currency_preference'),
                'timezone_preference': data.get('timezone_preference')
            }
            
            # Filter out None values
            update_data = {k: v for k, v in updatable_fields.items() if v is not None}
            
            if update_data:
                # Build UPDATE query
                set_clauses = []
                values = []
                
                for field, value in update_data.items():
                    set_clauses.append(f"{field} = %s")
                    values.append(value)
                
                set_clauses.append("updated_at = CURRENT_TIMESTAMP")
                values.append(user_id)
                
                query = f'''
                    INSERT INTO customer_preferences (user_id, {', '.join(update_data.keys())}, updated_at)
                    VALUES (%s, {', '.join(['%s'] * len(update_data))}, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id)
                    DO UPDATE SET {', '.join(set_clauses)}
                    RETURNING updated_at
                '''
                
                values = [user_id] + list(update_data.values()) + values
                
                result = execute_query(query, tuple(values), 'one')
                
                if result['success']:
                    # Log preference update
                    SecurityUtils.log_security_event(user_id, 'preferences_updated', {
                        'updated_fields': list(update_data.keys())
                    })
                    
                    return jsonify({
                        'message': 'Preferences updated successfully',
                        'updated_preferences': update_data,
                        'updated_at': result['data'][0].isoformat() if result['data'][0] else None
                    })
                else:
                    return jsonify('Failed to update preferences'), 500
            else:
                return jsonify('No valid preferences to update'), 400
        else:
            return jsonify('Database not available'), 503

    except Exception as e:
        return jsonify(f'Failed to update preferences: {str(e)}'), 500

# ================================
# CUSTOMER ANALYTICS (LIMITED)
# ================================

@customer_bp.route('/analytics', methods=['GET'])
@token_required
def get_customer_analytics():
    """Get customer-specific analytics (limited data for privacy)"""
    try:
        user_id = request.current_user.get('user_id')
        date_range = request.args.get('date_range', '12')  # months
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get customer ID
            customer_result = execute_query(
                'SELECT customer_id FROM customers WHERE user_id = %s',
                (user_id,),
                'one'
            )
            
            if customer_result['success'] and customer_result['data']:
                customer_id = customer_result['data'][0]
                
                # Get spending analytics
                spending_result = execute_query(f'''
                    SELECT 
                        EXTRACT(YEAR FROM created_at) as year,
                        EXTRACT(MONTH FROM created_at) as month,
                        COUNT(*) as transaction_count,
                        SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END) as total_spent
                    FROM transactions
                    WHERE customer_id = %s 
                    AND created_at >= CURRENT_DATE - INTERVAL '{date_range} months'
                    GROUP BY EXTRACT(YEAR FROM created_at), EXTRACT(MONTH FROM created_at)
                    ORDER BY year, month
                ''', (customer_id,))
                
                spending_by_month = []
                if spending_result['success']:
                    for row in spending_result['data']:
                        spending_by_month.append({
                            'year': int(row[0]),
                            'month': int(row[1]),
                            'transaction_count': row[2],
                            'total_spent': float(row[3])
                        })
                
                # Get policy analytics
                policy_result = execute_query('''
                    SELECT 
                        product_type,
                        COUNT(*) as policy_count,
                        SUM(coverage_amount) as total_coverage,
                        SUM(premium_amount) as total_premiums
                    FROM policies
                    WHERE customer_id = %s
                    GROUP BY product_type
                ''', (customer_id,))
                
                policies_by_type = []
                if policy_result['success']:
                    for row in policy_result['data']:
                        policies_by_type.append({
                            'product_type': row[0],
                            'policy_count': row[1],
                            'total_coverage': float(row[2]) if row[2] else 0.0,
                            'total_premiums': float(row[3]) if row[3] else 0.0
                        })
                
                # Calculate summary metrics
                total_spent = sum(month['total_spent'] for month in spending_by_month)
                total_transactions = sum(month['transaction_count'] for month in spending_by_month)
                avg_transaction = total_spent / total_transactions if total_transactions > 0 else 0
                
                analytics_data = {
                    'summary': {
                        'total_spent': total_spent,
                        'total_transactions': total_transactions,
                        'average_transaction': round(avg_transaction, 2),
                        'total_policies': len(policies_by_type),
                        'date_range_months': int(date_range)
                    },
                    'spending_by_month': spending_by_month,
                    'policies_by_type': policies_by_type,
                    'generated_at': datetime.now(timezone.utc).isoformat() + 'Z'
                }
                
                return jsonify(analytics_data)
            else:
                return jsonify('Customer record not found'), 404
        else:
            return jsonify({
                'summary': {'total_spent': 0, 'total_transactions': 0, 'average_transaction': 0, 'total_policies': 0},
                'spending_by_month': [],
                'policies_by_type': [],
                'source': 'database_unavailable'
            })

    except Exception as e:
        return jsonify(f'Failed to get analytics: {str(e)}'), 500

# ================================
# CUSTOMER NOTIFICATIONS
# ================================

@customer_bp.route('/notifications', methods=['GET'])
@token_required
def get_customer_notifications():
    """Get customer notifications"""
    try:
        user_id = request.current_user.get('user_id')
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Build query with filters
            where_conditions = ['user_id = %s']
            params = [user_id]
            
            if unread_only:
                where_conditions.append("read_at IS NULL")
            
            where_clause = ' AND '.join(where_conditions)
            
            # Get notifications
            notifications_result = execute_query(f'''
                SELECT 
                    id, notification_type, title, message, action_url,
                    created_at, read_at, priority
                FROM customer_notifications
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT 50
            ''', tuple(params))
            
            if notifications_result['success']:
                notifications = []
                for notif in notifications_result['data']:
                    notification_dict = {
                        'id': notif[0],
                        'type': notif[1],
                        'title': notif[2],
                        'message': notif[3],
                        'action_url': notif[4],
                        'created_at': notif[5].isoformat() if notif[5] else None,
                        'read_at': notif[6].isoformat() if notif[6] else None,
                        'priority': notif[7] or 'normal',
                        'is_read': notif[6] is not None
                    }
                    notifications.append(notification_dict)
                
                # Get unread count
                unread_count_result = execute_query('''
                    SELECT COUNT(*) FROM customer_notifications
                    WHERE user_id = %s AND read_at IS NULL
                ''', (user_id,), 'one')
                
                unread_count = unread_count_result['data'][0] if unread_count_result['success'] and unread_count_result['data'] else 0
                
                return jsonify({
                    'notifications': notifications,
                    'unread_count': unread_count,
                    'total_notifications': len(notifications)
                })
            else:
                return jsonify('Failed to fetch notifications'), 500
        else:
            # Return sample notifications when database not available
            sample_notifications = [
                {
                    'id': 'NOTIF-001',
                    'type': 'policy_reminder',
                    'title': 'Policy Expiring Soon',
                    'message': 'Your auto protection policy expires in 30 days',
                    'action_url': '/customer/policies',
                    'created_at': datetime.now(timezone.utc).isoformat() + 'Z',
                    'read_at': None,
                    'priority': 'high',
                    'is_read': False
                }
            ]
            
            return jsonify({
                'notifications': sample_notifications,
                'unread_count': 1,
                'source': 'sample_data'
            })
    except Exception as e:
        return jsonify(f'Failed to get notifications: {str(e)}'), 500

@customer_bp.route('/notifications/<notification_id>/read', methods=['PUT'])
@token_required
def mark_notification_read(notification_id):
    """Mark notification as read"""
    try:
        user_id = request.current_user.get('user_id')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Mark notification as read
            result = execute_query('''
                UPDATE customer_notifications
                SET read_at = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id = %s AND read_at IS NULL
                RETURNING read_at
            ''', (notification_id, user_id), 'one')
            
            if result['success'] and result['data']:
                return jsonify({
                    'message': 'Notification marked as read',
                    'notification_id': notification_id,
                    'read_at': result['data'][0].isoformat() if result['data'][0] else None
                })
            else:
                return jsonify('Notification not found or already read'), 404
        else:
            return jsonify('Database not available'), 503

    except Exception as e:
        return jsonify(f'Failed to mark notification as read: {str(e)}'), 500

@customer_bp.route('/notifications/read-all', methods=['PUT'])
@token_required
def mark_all_notifications_read():
    """Mark all notifications as read"""
    try:
        user_id = request.current_user.get('user_id')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Mark all unread notifications as read
            result = execute_query('''
                UPDATE customer_notifications
                SET read_at = CURRENT_TIMESTAMP
                WHERE user_id = %s AND read_at IS NULL
            ''', (user_id,), 'none')
            
            if result['success']:
                affected_rows = result.get('affected_rows', 0)
                return jsonify({
                    'message': f'Marked {affected_rows} notifications as read',
                    'marked_count': affected_rows
                })
            else:
                return jsonify('Failed to mark notifications as read'), 500
        else:
            return jsonify('Database not available'), 503

    except Exception as e:
        return jsonify(f'Failed to mark all notifications as read: {str(e)}'), 500

# ================================
# CUSTOMER ACCOUNT MANAGEMENT
# ================================

@customer_bp.route('/account/password', methods=['PUT'])
@token_required
def change_password():
    """Change customer password"""
    try:
        data = request.get_json()
        user_id = request.current_user.get('user_id')
        
        # Validate required fields
        required_fields = ['current_password', 'new_password']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify(f"Missing fields: {', '.join(missing_fields)}"), 400
        
        current_password = data['current_password']
        new_password = data['new_password']
        
        # Validate new password strength
        if len(new_password) < 8:
            return jsonify('New password must be at least 8 characters long'), 400
        
        import re
        if not re.search(r'[A-Z]', new_password):
            return jsonify('New password must contain at least one uppercase letter'), 400
        if not re.search(r'[a-z]', new_password):
            return jsonify('New password must contain at least one lowercase letter'), 400
        if not re.search(r'\d', new_password):
            return jsonify('New password must contain at least one number'), 400
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get current password hash
            current_hash_result = execute_query(
                'SELECT password_hash FROM users WHERE id = %s',
                (user_id,),
                'one'
            )
            
            if current_hash_result['success'] and current_hash_result['data']:
                current_hash = current_hash_result['data'][0]
                
                # Verify current password
                if not UserAuth.verify_password(current_password, current_hash):
                    # Log failed password change attempt
                    SecurityUtils.log_security_event(user_id, 'password_change_failed', {
                        'reason': 'incorrect_current_password'
                    })
                    return jsonify('Current password is incorrect'), 400
                
                # Update password
                new_hash = UserAuth.hash_password(new_password)
                update_result = execute_query('''
                    UPDATE users 
                    SET password_hash = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (new_hash, user_id), 'none')
                
                if update_result['success']:
                    # Log successful password change
                    SecurityUtils.log_security_event(user_id, 'password_changed', {
                        'changed_by': 'customer'
                    })
                    
                    return jsonify({
                        'message': 'Password changed successfully',
                        'changed_at': datetime.now(timezone.utc).isoformat() + 'Z'
                    })
                else:
                    return jsonify('Failed to update password'), 500
            else:
                return jsonify('User not found'), 404
        else:
            return jsonify('Database not available'), 503

    except Exception as e:
        return jsonify(f'Password change failed: {str(e)}'), 500

@customer_bp.route('/account/deactivate', methods=['POST'])
@token_required
def deactivate_account():
    """Deactivate customer account"""
    try:
        data = request.get_json()
        user_id = request.current_user.get('user_id')
        
        # Require password confirmation
        password = data.get('password')
        reason = data.get('reason', 'Customer request')
        
        if not password:
            return jsonify('Password confirmation required'), 400
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Verify password
            password_result = execute_query(
                'SELECT password_hash FROM users WHERE id = %s',
                (user_id,),
                'one'
            )
            
            if password_result['success'] and password_result['data']:
                password_hash = password_result['data'][0]
                
                if not UserAuth.verify_password(password, password_hash):
                    SecurityUtils.log_security_event(user_id, 'account_deactivation_failed', {
                        'reason': 'incorrect_password'
                    })
                    return jsonify('Incorrect password'), 400
                
                # Check for active policies
                active_policies_result = execute_query('''
                    SELECT COUNT(*)
                    FROM policies p
                    JOIN customers c ON p.customer_id = c.customer_id
                    WHERE c.user_id = %s AND p.status = 'active'
                ''', (user_id,), 'one')
                
                active_policies_count = 0
                if active_policies_result['success'] and active_policies_result['data']:
                    active_policies_count = active_policies_result['data'][0]
                
                if active_policies_count > 0:
                    return jsonify(f'Cannot deactivate account with {active_policies_count} active policies. Please contact support.'), 400
                
                # Deactivate account
                deactivate_result = execute_query('''
                    UPDATE users 
                    SET status = 'inactive', updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (user_id,), 'none')
                
                if deactivate_result['success']:
                    # Log account deactivation
                    SecurityUtils.log_security_event(user_id, 'account_deactivated', {
                        'reason': reason,
                        'deactivated_by': 'customer'
                    })
                    
                    return jsonify({
                        'message': 'Account deactivated successfully',
                        'deactivated_at': datetime.now(timezone.utc).isoformat() + 'Z',
                        'reason': reason,
                        'note': 'You can reactivate your account by contacting support'
                    })
                else:
                    return jsonify('Failed to deactivate account'), 500
            else:
                return jsonify('User not found'), 404
        else:
            return jsonify('Database not available'), 503

    except Exception as e:
        return jsonify(f'Account deactivation failed: {str(e)}'), 500

# ================================
# ERROR HANDLERS
# ================================

@customer_bp.errorhandler(401)
def unauthorized(error):
    """Handle unauthorized access"""
    return jsonify('Authentication required for customer access'), 401

@customer_bp.errorhandler(403)
def forbidden(error):
    """Handle forbidden access"""
    return jsonify('Insufficient permissions for customer operation'), 403

@customer_bp.errorhandler(404)
def not_found(error):
    """Handle not found errors"""
    return jsonify('Customer resource not found'), 404

@customer_bp.errorhandler(429)
def rate_limit_exceeded(error):
    """Handle rate limit exceeded"""
    return jsonify('Rate limit exceeded. Please try again later.'), 429

@customer_bp.errorhandler(500)
def internal_error(error):
    """Handle internal server errors"""
    return jsonify('Internal customer service error'), 500
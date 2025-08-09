
from flask import Blueprint, request, jsonify
from datetime import datetime, timezone, timedelta
import uuid
import json
from auth.user_auth import token_required, role_required, SecurityUtils, UserAuth
from utils.database import get_db_manager, execute_query
from utils.service_availability import ServiceChecker
import re
import os

# Initialize blueprint
reseller_bp = Blueprint('reseller', __name__)

FRONTEND_BASE_URL = os.getenv('FRONTEND_BASE_URL', 'http://localhost:5173')

# Import reseller services with error handling
try:
    from models.database_models import UserModel, CustomerModel, ResellerModel, DatabaseUtils
    reseller_services_available = True
    
    # Initialize models
    user_model = UserModel()
    customer_model = CustomerModel()
    reseller_model = ResellerModel()
    resellers_db = {}
    
except ImportError as e:
    print(f"Warning: Reseller services not available: {e}")
    reseller_services_available = False
    
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
    
    class ResellerModel:
        def create_reseller(self, data):
            return {**data, 'id': str(uuid.uuid4()), 'created_at': datetime.now(timezone.utc)}
    
    class DatabaseUtils:
        @staticmethod
        def get_customer_metrics(customer_id, transactions, policies):
            return {'total_transactions': 0, 'total_spent': 0.0, 'active_policies': 0}
    
    user_model = UserModel()
    customer_model = CustomerModel()
    reseller_model = ResellerModel()
    resellers_db = {}

# ================================
# RESELLER HEALTH & STATUS
# ================================

@reseller_bp.route('/health')
def reseller_health():
    """Reseller service health check"""
    service_checker = ServiceChecker()
    
    return jsonify({
        'service': 'Reseller Management API',
        'status': 'healthy' if reseller_services_available else 'degraded',
        'reseller_services_available': reseller_services_available,
        'features': {
            'commission_tracking': reseller_services_available,
            'customer_management': reseller_services_available,
            'sales_analytics': True,
            'quote_generation': True,
            'lead_management': True,
            'performance_reports': True,
            'wholesale_pricing': True
        },
        'database_integration': service_checker.database_settings_available,
        'timestamp': datetime.now(timezone.utc).isoformat() + "Z"
    })

# ================================
# RESELLER REGISTRATION & PROFILE
# ================================

@reseller_bp.route('/register', methods=['POST'])
def register_reseller():
    """Register new wholesale reseller"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['email', 'password', 'business_name', 'license_number', 'license_state', 'contact_name']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify(f"Missing fields: {', '.join(missing_fields)}"), 400
        
        email = data.get('email').lower().strip()
        password = data.get('password')
        business_name = data.get('business_name').strip()
        license_number = data.get('license_number').strip()
        license_state = data.get('license_state').strip().upper()
        contact_name = data.get('contact_name').strip()
        
        # Validate email format
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return jsonify('Invalid email format'), 400
        
        # Validate password strength
        if len(password) < 8:
            return jsonify('Password must be at least 8 characters long'), 400
        
        # Validate license state
        valid_states = ['AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 
                       'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
                       'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
                       'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
                       'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY']
        
        if license_state not in valid_states:
            return jsonify('Invalid license state'), 400
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Check if reseller already exists
            existing_reseller = execute_query(
                'SELECT id FROM users WHERE email = %s',
                (email,),
                'one'
            )
            
            if existing_reseller['success'] and existing_reseller['data']:
                return jsonify('Reseller already exists with this email'), 409
            
            # Check for duplicate license number
            duplicate_license = execute_query(
                'SELECT id FROM resellers WHERE license_number = %s AND license_state = %s',
                (license_number, license_state),
                'one'
            )
            
            if duplicate_license['success'] and duplicate_license['data']:
                return jsonify('License number already registered in this state'), 409
            
            # Create user account
            user_id = str(uuid.uuid4())
            reseller_id = str(uuid.uuid4())
            
            # Insert user
            user_result = execute_query('''
                INSERT INTO users (id, email, password_hash, role, status, profile, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING created_at
            ''', (
                user_id,
                email,
                UserAuth.hash_password(password),
                'wholesale_reseller',
                'pending_approval',  # Resellers require approval
                json.dumps({
                    'business_name': business_name,
                    'contact_name': contact_name,
                    'registration_source': 'reseller_portal'
                })
            ), 'one')
            
            if user_result['success']:
                # Insert reseller profile
                reseller_result = execute_query('''
                    INSERT INTO resellers (
                        id, user_id, reseller_id, business_name, license_number, 
                        license_state, contact_name, email, phone, business_type,
                        commission_rate, status, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING created_at
                ''', (
                    str(uuid.uuid4()),
                    user_id,
                    reseller_id,
                    business_name,
                    license_number,
                    license_state,
                    contact_name,
                    email,
                    data.get('phone', ''),
                    data.get('business_type', 'insurance_agency'),
                    data.get('commission_rate', 0.15),  # Default 15% commission
                    'pending_approval'
                ), 'one')
                
                if reseller_result['success']:
                    # Log registration
                    SecurityUtils.log_security_event(user_id, 'reseller_registered', {
                        'email': email,
                        'business_name': business_name,
                        'license_state': license_state,
                        'registration_method': 'self_registration'
                    })
                    
                    return jsonify({
                        'message': 'Reseller registration submitted successfully',
                        'reseller': {
                            'id': reseller_id,
                            'user_id': user_id,
                            'email': email,
                            'business_name': business_name,
                            'license_number': license_number,
                            'license_state': license_state,
                            'status': 'pending_approval',
                            'created_at': user_result['data'][0].isoformat() if user_result['data'][0] else None
                        },
                        'next_steps': [
                            'Your application is pending approval',
                            'You will receive email notification when approved',
                            'Typical approval time is 2-3 business days',
                            'Contact support if you have questions'
                        ]
                    }), 201
                else:
                    # Rollback user creation if reseller creation failed
                    execute_query('DELETE FROM users WHERE id = %s', (user_id,), 'none')
                    return jsonify('Failed to create reseller profile'), 500
            else:
                return jsonify('Failed to create user account'), 500
        else:
            return jsonify('Database not available for registration'), 503

    except Exception as e:
        return jsonify(f'Registration failed: {str(e)}'), 500

@reseller_bp.route('/profile', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def get_reseller_profile():
    """Get reseller profile and business information"""
    try:
        user_id = request.current_user.get('user_id')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get reseller profile with metrics
            result = execute_query('''
                SELECT 
                    u.id as user_id, u.email, u.created_at as user_created_at, u.last_login, u.status as user_status,
                    r.id, r.reseller_id, r.business_name, r.license_number, r.license_state,
                    r.contact_name, r.phone, r.business_type, r.commission_rate, r.status,
                    r.website, r.address, r.tax_id, r.created_at,
                    COUNT(DISTINCT c.id) as total_customers,
                    COUNT(DISTINCT t.id) as total_transactions,
                    COALESCE(SUM(CASE WHEN t.status = 'completed' THEN t.amount * r.commission_rate ELSE 0 END), 0) as total_commissions_earned,
                    COALESCE(SUM(CASE WHEN t.status = 'completed' THEN t.amount ELSE 0 END), 0) as total_sales_volume
                FROM users u
                LEFT JOIN resellers r ON u.id = r.user_id
                LEFT JOIN customers c ON r.reseller_id = c.assigned_reseller_id
                LEFT JOIN transactions t ON c.customer_id = t.customer_id
                WHERE u.id = %s
                GROUP BY u.id, u.email, u.created_at, u.last_login, u.status, r.id, r.reseller_id, 
                         r.business_name, r.license_number, r.license_state, r.contact_name, r.phone, 
                         r.business_type, r.commission_rate, r.status, r.website, r.address, r.tax_id, r.created_at
            ''', (user_id,), 'one')
            
            if result['success'] and result['data']:
                profile = dict(result['data'])
                
                # Format dates
                profile['user_created_at'] = profile['user_created_at'].isoformat() if profile['user_created_at'] else None
                profile['created_at'] = profile['created_at'].isoformat() if profile['created_at'] else None
                profile['last_login'] = profile['last_login'].isoformat() if profile['last_login'] else None
                
                # Parse address if exists
                if profile['address']:
                    try:
                        profile['address'] = json.loads(profile['address']) if isinstance(profile['address'], str) else profile['address']
                    except (json.JSONDecodeError, TypeError):
                        profile['address'] = {}
                
                # Calculate business metrics
                profile['business_metrics'] = {
                    'total_customers': profile['total_customers'],
                    'total_transactions': profile['total_transactions'],
                    'total_commissions_earned': float(profile['total_commissions_earned']),
                    'total_sales_volume': float(profile['total_sales_volume']),
                    'average_transaction_value': float(profile['total_sales_volume']) / profile['total_transactions'] if profile['total_transactions'] > 0 else 0,
                    'commission_rate': float(profile['commission_rate']),
                    'reseller_since': profile['created_at']
                }
                
                # Get recent performance
                performance_result = execute_query('''
                    SELECT 
                        EXTRACT(YEAR FROM t.created_at) as year,
                        EXTRACT(MONTH FROM t.created_at) as month,
                        COUNT(*) as transaction_count,
                        SUM(t.amount) as sales_volume,
                        SUM(t.amount * r.commission_rate) as commissions_earned
                    FROM transactions t
                    JOIN customers c ON t.customer_id = c.customer_id
                    JOIN resellers r ON c.assigned_reseller_id = r.reseller_id
                    WHERE r.user_id = %s AND t.status = 'completed'
                    AND t.created_at >= CURRENT_DATE - INTERVAL '12 months'
                    GROUP BY EXTRACT(YEAR FROM t.created_at), EXTRACT(MONTH FROM t.created_at)
                    ORDER BY year DESC, month DESC
                    LIMIT 12
                ''', (user_id,))
                
                profile['recent_performance'] = []
                if performance_result['success']:
                    for row in performance_result['data']:
                        profile['recent_performance'].append({
                            'year': int(row[0]),
                            'month': int(row[1]),
                            'transaction_count': row[2],
                            'sales_volume': float(row[3]),
                            'commissions_earned': float(row[4])
                        })
                
                return jsonify(profile)
            else:
                return jsonify('Reseller profile not found'), 404
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

@reseller_bp.route('/profile', methods=['PUT'])
@token_required
@role_required('wholesale_reseller')
def update_reseller_profile():
    """Update reseller profile information"""
    try:
        data = request.get_json()
        user_id = request.current_user.get('user_id')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get current reseller record
            reseller_result = execute_query(
                'SELECT id, reseller_id FROM resellers WHERE user_id = %s',
                (user_id,),
                'one'
            )
            
            if not reseller_result['success'] or not reseller_result['data']:
                return jsonify('Reseller record not found'), 404
            
            reseller_record_id = reseller_result['data'][0]
            
            # Prepare update fields (excluding sensitive fields like commission_rate)
            update_fields = []
            update_values = []
            
            updatable_fields = {
                'business_name': data.get('business_name'),
                'contact_name': data.get('contact_name'),
                'phone': data.get('phone'),
                'website': data.get('website'),
                'business_type': data.get('business_type'),
                'address': json.dumps(data.get('address')) if data.get('address') else None,
                'tax_id': data.get('tax_id')
            }
            
            for field, value in updatable_fields.items():
                if value is not None:
                    update_fields.append(f"{field} = %s")
                    update_values.append(value)
            
            if update_fields:
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                update_values.append(reseller_record_id)
                
                query = f"UPDATE resellers SET {', '.join(update_fields)} WHERE id = %s RETURNING updated_at"
                result = execute_query(query, tuple(update_values), 'one')
                
                if result['success']:
                    # Log profile update
                    SecurityUtils.log_security_event(user_id, 'reseller_profile_updated', {
                        'updated_fields': [field for field, value in updatable_fields.items() if value is not None]
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
# RESELLER DASHBOARD
# ================================

@reseller_bp.route('/dashboard', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def get_reseller_dashboard():
    """Get reseller dashboard with business metrics"""
    try:
        user_id = request.current_user.get('user_id')
        
        db_manager = get_db_manager()
        dashboard_data = {
            'overview': {
                'total_customers': 0,
                'active_customers': 0,
                'total_sales': 0.0,
                'monthly_commissions': 0.0,
                'pending_commissions': 0.0,
                'this_month_sales': 0.0
            },
            'recent_activity': [],
            'top_customers': [],
            'performance_trends': [],
            'commission_summary': {},
            'quick_actions': [
                {'action': 'create_quote', 'title': 'Create Quote', 'description': 'Generate quote for customer'},
                {'action': 'add_customer', 'title': 'Add Customer', 'description': 'Register new customer'},
                {'action': 'view_commissions', 'title': 'View Commissions', 'description': 'Check commission statements'},
                {'action': 'sales_tools', 'title': 'Sales Tools', 'description': 'Access marketing materials'}
            ],
            'alerts': []
        }
        
        if db_manager.available:
            # Get reseller ID
            reseller_result = execute_query(
                'SELECT reseller_id, commission_rate FROM resellers WHERE user_id = %s',
                (user_id,),
                'one'
            )
            
            if reseller_result['success'] and reseller_result['data']:
                reseller_id, commission_rate = reseller_result['data']
                
                # Get customer metrics
                customer_metrics = execute_query('''
                    SELECT 
                        COUNT(*) as total_customers,
                        COUNT(*) FILTER (WHERE last_transaction_date >= CURRENT_DATE - INTERVAL '30 days') as active_customers
                    FROM customers
                    WHERE assigned_reseller_id = %s
                ''', (reseller_id,), 'one')
                
                if customer_metrics['success'] and customer_metrics['data']:
                    stats = customer_metrics['data']
                    dashboard_data['overview']['total_customers'] = stats[0]
                    dashboard_data['overview']['active_customers'] = stats[1]
                
                # Get sales metrics
                sales_metrics = execute_query('''
                    SELECT 
                        COALESCE(SUM(CASE WHEN t.status = 'completed' THEN t.amount ELSE 0 END), 0) as total_sales,
                        COALESCE(SUM(CASE WHEN t.status = 'completed' THEN t.amount * %s ELSE 0 END), 0) as total_commissions,
                        COALESCE(SUM(CASE WHEN t.status = 'completed' AND t.created_at >= DATE_TRUNC('month', CURRENT_DATE) THEN t.amount ELSE 0 END), 0) as this_month_sales,
                        COALESCE(SUM(CASE WHEN t.status = 'completed' AND t.created_at >= DATE_TRUNC('month', CURRENT_DATE) THEN t.amount * %s ELSE 0 END), 0) as this_month_commissions
                    FROM transactions t
                    JOIN customers c ON t.customer_id = c.customer_id
                    WHERE c.assigned_reseller_id = %s
                ''', (commission_rate, commission_rate, reseller_id), 'one')
                
                if sales_metrics['success'] and sales_metrics['data']:
                    stats = sales_metrics['data']
                    dashboard_data['overview']['total_sales'] = float(stats[0])
                    dashboard_data['overview']['monthly_commissions'] = float(stats[3])
                    dashboard_data['overview']['this_month_sales'] = float(stats[2])
                
                # Get recent activity
                recent_activity = execute_query('''
                    SELECT 
                        'transaction' as activity_type,
                        t.transaction_number as reference,
                        t.amount,
                        t.status,
                        t.created_at,
                        c.first_name || ' ' || c.last_name as customer_name
                    FROM transactions t
                    JOIN customers c ON t.customer_id = c.customer_id
                    WHERE c.assigned_reseller_id = %s
                    ORDER BY t.created_at DESC
                    LIMIT 10
                ''', (reseller_id,))
                
                if recent_activity['success']:
                    for activity in recent_activity['data']:
                        dashboard_data['recent_activity'].append({
                            'type': activity[0],
                            'reference': activity[1],
                            'amount': float(activity[2]) if activity[2] else None,
                            'status': activity[3],
                            'date': activity[4].isoformat() if activity[4] else None,
                            'customer_name': activity[5]
                        })
                
                # Get top customers
                top_customers = execute_query('''
                    SELECT 
                        c.customer_id,
                        c.first_name || ' ' || c.last_name as customer_name,
                        COUNT(t.id) as transaction_count,
                        COALESCE(SUM(CASE WHEN t.status = 'completed' THEN t.amount ELSE 0 END), 0) as total_spent,
                        MAX(t.created_at) as last_transaction
                    FROM customers c
                    LEFT JOIN transactions t ON c.customer_id = t.customer_id
                    WHERE c.assigned_reseller_id = %s
                    GROUP BY c.customer_id, c.first_name, c.last_name
                    ORDER BY total_spent DESC
                    LIMIT 5
                ''', (reseller_id,))
                
                if top_customers['success']:
                    for customer in top_customers['data']:
                        dashboard_data['top_customers'].append({
                            'customer_id': customer[0],
                            'customer_name': customer[1],
                            'transaction_count': customer[2],
                            'total_spent': float(customer[3]),
                            'last_transaction': customer[4].isoformat() if customer[4] else None
                        })
                
                # Get performance trends (last 6 months)
                performance_trends = execute_query('''
                    SELECT 
                        EXTRACT(YEAR FROM t.created_at) as year,
                        EXTRACT(MONTH FROM t.created_at) as month,
                        COUNT(*) as transaction_count,
                        SUM(t.amount) as sales_volume,
                        SUM(t.amount * %s) as commissions_earned
                    FROM transactions t
                    JOIN customers c ON t.customer_id = c.customer_id
                    WHERE c.assigned_reseller_id = %s AND t.status = 'completed'
                    AND t.created_at >= CURRENT_DATE - INTERVAL '6 months'
                    GROUP BY EXTRACT(YEAR FROM t.created_at), EXTRACT(MONTH FROM t.created_at)
                    ORDER BY year, month
                ''', (commission_rate, reseller_id))
                
                if performance_trends['success']:
                    for trend in performance_trends['data']:
                        dashboard_data['performance_trends'].append({
                            'year': int(trend[0]),
                            'month': int(trend[1]),
                            'transaction_count': trend[2],
                            'sales_volume': float(trend[3]),
                            'commissions_earned': float(trend[4])
                        })
                
                # Generate alerts
                if dashboard_data['overview']['total_customers'] == 0:
                    dashboard_data['alerts'].append({
                        'type': 'info',
                        'title': 'No Customers Yet',
                        'message': 'Start adding customers to begin earning commissions',
                        'action': 'add_customer'
                    })
                
                if dashboard_data['overview']['this_month_sales'] == 0:
                    dashboard_data['alerts'].append({
                        'type': 'warning',
                        'title': 'No Sales This Month',
                        'message': 'Reach out to your customers or generate new quotes',
                        'action': 'create_quote'
                    })
        
        return jsonify(dashboard_data) 
        
    except Exception as e:
        return jsonify(f'Failed to load dashboard: {str(e)}'), 500

# ================================
# CUSTOMER MANAGEMENT FOR RESELLERS
# ================================

@reseller_bp.route('/customers', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def get_reseller_customers():
    """Get all customers assigned to this reseller"""
    try:
        user_id = request.current_user.get('user_id')
        if not user_id:
            return jsonify({
                'success': False,
                'error': 'User ID not found in token'
            }), 401

        search = request.args.get('search', '').strip()
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))

        offset = (page - 1) * limit

        # Build search condition
        search_condition = ""
        params = [user_id]

        if search:
            search_condition = '''AND (
                c.personal_info->>'first_name' ILIKE %s OR
                c.personal_info->>'last_name' ILIKE %s OR
                c.contact_info->>'email' ILIKE %s OR
                c.business_info->>'company_name' ILIKE %s
            )'''
            search_param = f'%{search}%'
            params.extend([search_param, search_param, search_param, search_param])

        params.extend([limit, offset])

        customers_result = execute_query(f'''
            SELECT c.id, c.customer_type, c.personal_info, c.contact_info, c.business_info,
                   c.lifetime_value, c.total_policies, c.active_policies, c.created_at, c.last_activity,
                   COUNT(q.id) as total_quotes,
                   COUNT(CASE WHEN q.converted_to_policy THEN 1 END) as converted_quotes
            FROM customers c
            LEFT JOIN quotes q ON c.id = q.customer_id
            WHERE c.assigned_reseller_id = %s {search_condition}
            GROUP BY c.id, c.customer_type, c.personal_info, c.contact_info, c.business_info,
                     c.lifetime_value, c.total_policies, c.active_policies, c.created_at, c.last_activity
            ORDER BY c.last_activity DESC NULLS LAST
            LIMIT %s OFFSET %s
        ''', tuple(params), 'all')

        # Check if query execution was successful
        if not customers_result.get('success', False):
            return jsonify({
                'success': False,
                'error': 'Failed to execute query'
            }), 500

        # Format customer data
        customers = []
        for customer_data in customers_result.get('data', []):
            try:
                # JSONB fields are already parsed as dicts by psycopg2, no need for json.loads()
                personal_info = customer_data['personal_info'] if customer_data['personal_info'] else {}
                contact_info = customer_data['contact_info'] if customer_data['contact_info'] else {}
                business_info = customer_data['business_info'] if customer_data['business_info'] else {}

                # Handle datetime formatting safely
                created_at = customer_data['created_at']
                last_activity = customer_data['last_activity']

                customers.append({
                    'id': str(customer_data['id']),
                    'customer_type': customer_data['customer_type'],
                    'name': f"{personal_info.get('first_name', '')} {personal_info.get('last_name', '')}".strip(),
                    'email': contact_info.get('email', ''),
                    'company': business_info.get('company_name', ''),
                    'phone': contact_info.get('phone', ''),
                    'lifetime_value': float(customer_data['lifetime_value']) if customer_data[
                        'lifetime_value'] else 0.0,
                    'total_policies': customer_data['total_policies'] or 0,
                    'active_policies': customer_data['active_policies'] or 0,
                    'total_quotes': customer_data['total_quotes'] or 0,
                    'converted_quotes': customer_data['converted_quotes'] or 0,
                    'created_at': created_at.isoformat() + 'Z' if created_at else None,
                    'last_activity': last_activity.isoformat() + 'Z' if last_activity else None
                })
            except (KeyError, ValueError, TypeError) as e:
                print(f"Error processing customer data: {e}")
                print(
                    f"Available keys: {list(customer_data.keys()) if hasattr(customer_data, 'keys') else 'Not a dict-like object'}")
                continue

        return jsonify({
            'success': True,
            'customers': customers,
            'total': len(customers),
            'page': page,
            'limit': limit
        })

    except Exception as e:
        print(f"Error in get_reseller_customers: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to fetch customers: {str(e)}'
        }), 500


@reseller_bp.route('/customers', methods=['POST'])
@token_required
@role_required('wholesale_reseller')
def create_customer():
    """Create a new customer assigned to this reseller"""
    try:
        user_id = request.current_user.get('user_id')
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['customer_type']
        if data.get('customer_type') == 'individual':
            required_fields.extend(['first_name', 'last_name', 'email'])
        else:  # business
            required_fields.extend(['company_name', 'contact_email'])
        
        missing_fields = []
        for field in required_fields:
            if field in ['first_name', 'last_name']:
                if not data.get('personal_info', {}).get(field):
                    missing_fields.append(field)
            elif field == 'email':
                if not data.get('contact_info', {}).get('email'):
                    missing_fields.append('email')
            elif field == 'company_name':
                if not data.get('business_info', {}).get('company_name'):
                    missing_fields.append('company_name')
            elif field == 'contact_email':
                if not data.get('contact_info', {}).get('email'):
                    missing_fields.append('contact_email')
            elif not data.get(field):
                missing_fields.append(field)
        
        if missing_fields:
            return jsonify(f"Missing required fields: {', '.join(missing_fields)}"), 400
        
        # Create customer
        customer_result = execute_query('''
            INSERT INTO customers (
                customer_type, personal_info, business_info, contact_info, 
                billing_info, preferences, assigned_reseller_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            data.get('customer_type', 'individual'),
            json.dumps(data.get('personal_info', {})),
            json.dumps(data.get('business_info', {})),
            json.dumps(data.get('contact_info', {})),
            json.dumps(data.get('billing_info', {})),
            json.dumps(data.get('preferences', {})),
            user_id
        ), 'one')
        
        if customer_result['success']:
            customer_id = customer_result['data'][0]
            return jsonify({
                'success': True,
                'customer_id': str(customer_id),
                'message': 'Customer created successfully'
            })
        
        return jsonify('Failed to create customer'), 500
        
    except Exception as e:
        return jsonify(f'Failed to create customer: {str(e)}'), 500


@reseller_bp.route('/customers/<customer_id>', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def get_customer_details(customer_id):
    """Get detailed information about a specific customer"""
    try:
        user_id = request.current_user.get('user_id')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Verify customer belongs to this reseller and get details
            result = execute_query('''
                SELECT 
                    c.customer_id, c.first_name, c.last_name, c.email, c.phone,
                    c.created_at, c.last_transaction_date, c.billing_address,
                    r.reseller_id, r.commission_rate,
                    COUNT(DISTINCT t.id) as total_transactions,
                    COUNT(DISTINCT p.id) as total_policies,
                    COALESCE(SUM(CASE WHEN t.status = 'completed' THEN t.amount ELSE 0 END), 0) as total_spent,
                    COALESCE(SUM(CASE WHEN t.status = 'completed' THEN t.amount * r.commission_rate ELSE 0 END), 0) as total_commissions_earned
                FROM customers c
                JOIN resellers r ON c.assigned_reseller_id = r.reseller_id
                LEFT JOIN transactions t ON c.customer_id = t.customer_id
                LEFT JOIN policies p ON c.customer_id = p.customer_id
                WHERE c.customer_id = %s AND r.user_id = %s
                GROUP BY c.customer_id, c.first_name, c.last_name, c.email, c.phone,
                         c.created_at, c.last_transaction_date, c.billing_address,
                         r.reseller_id, r.commission_rate
            ''', (customer_id, user_id), 'one')
            
            if result['success'] and result['data']:
                customer = dict(result['data'])
                
                # Format dates
                customer['created_at'] = customer['created_at'].isoformat() if customer['created_at'] else None
                customer['last_transaction_date'] = customer['last_transaction_date'].isoformat() if customer['last_transaction_date'] else None
                
                # Parse billing address
                if customer['billing_address']:
                    try:
                        customer['billing_address'] = json.loads(customer['billing_address']) if isinstance(customer['billing_address'], str) else customer['billing_address']
                    except (json.JSONDecodeError, TypeError):
                        customer['billing_address'] = {}
                
                # Convert amounts
                customer['total_spent'] = float(customer['total_spent'])
                customer['total_commissions_earned'] = float(customer['total_commissions_earned'])
                customer['commission_rate'] = float(customer['commission_rate'])
                
                # Get recent transactions
                transactions_result = execute_query('''
                    SELECT transaction_number, amount, status, created_at, type
                    FROM transactions
                    WHERE customer_id = %s
                    ORDER BY created_at DESC
                    LIMIT 10
                ''', (customer_id,))
                
                customer['recent_transactions'] = []
                if transactions_result['success']:
                    for txn in transactions_result['data']:
                        customer['recent_transactions'].append({
                            'transaction_number': txn[0],
                            'amount': float(txn[1]) if txn[1] else 0.0,
                            'status': txn[2],
                            'created_at': txn[3].isoformat() if txn[3] else None,
                            'type': txn[4]
                        })
                
                # Get active policies
                policies_result = execute_query('''
                    SELECT policy_number, product_type, coverage_amount, status, start_date, end_date
                    FROM policies
                    WHERE customer_id = %s AND status = 'active'
                    ORDER BY start_date DESC
                ''', (customer_id,))
                
                customer['active_policies'] = []
                if policies_result['success']:
                    for policy in policies_result['data']:
                        customer['active_policies'].append({
                            'policy_number': policy[0],
                            'product_type': policy[1],
                            'coverage_amount': float(policy[2]) if policy[2] else 0.0,
                            'status': policy[3],
                            'start_date': policy[4].isoformat() if policy[4] else None,
                            'end_date': policy[5].isoformat() if policy[5] else None
                        })
                
                return jsonify(customer)
            else:
                return jsonify('Customer not found or access denied'), 404
        else:
            return jsonify('Database not available'), 503

    except Exception as e:
        return jsonify(f'Failed to get customer details: {str(e)}'), 500

@reseller_bp.route('/leads', methods=['POST'])
@token_required
@role_required('wholesale_reseller')
def add_lead():
    """Add new lead to reseller's pipeline"""
    try:
        data = request.get_json()
        user_id = request.current_user.get('user_id')
        
        # Validate required fields
        required_fields = ['first_name', 'last_name', 'email']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify(f"Missing fields: {', '.join(missing_fields)}"), 400
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get reseller ID
            reseller_result = execute_query(
                'SELECT reseller_id FROM resellers WHERE user_id = %s',
                (user_id,),
                'one'
            )
            
            if reseller_result['success'] and reseller_result['data']:
                reseller_id = reseller_result['data'][0]
                
                # Generate lead ID
                lead_id = f"LEAD-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
                
                # Create lead record
                lead_result = execute_query('''
                    INSERT INTO leads (
                        lead_id, assigned_reseller_id, first_name, last_name, email, phone,
                        lead_source, status, interest_level, product_interest, estimated_value,
                        notes, created_by, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING id, created_at
                ''', (
                    lead_id,
                    reseller_id,
                    data['first_name'],
                    data['last_name'],
                    data['email'],
                    data.get('phone', ''),
                    data.get('lead_source', 'manual_entry'),
                    'new',
                    data.get('interest_level', 'medium'),
                    data.get('product_interest', ''),
                    data.get('estimated_value', 0),
                    data.get('notes', ''),
                    user_id
                ), 'one')
                
                if lead_result['success']:
                    # Log lead creation
                    SecurityUtils.log_security_event(user_id, 'lead_added_by_reseller', {
                        'lead_id': lead_id,
                        'reseller_id': reseller_id
                    })
                    
                    return jsonify({
                        'message': 'Lead added successfully',
                        'lead': {
                            'lead_id': lead_id,
                            'status': 'new',
                            'created_at': lead_result['data'][1].isoformat() if lead_result['data'][1] else None,
                            **data
                        }
                    }), 201
                else:
                    return jsonify('Failed to create lead'), 500
            else:
                return jsonify('Reseller record not found'), 404
        else:
            return jsonify('Database not available'), 503

    except Exception as e:
        return jsonify(f'Failed to add lead: {str(e)}'), 500

# ================================
# QUOTE GENERATION FOR RESELLERS
# ================================

@reseller_bp.route('/quotes/generate', methods=['POST'])
@token_required
@role_required('wholesale_reseller')
def generate_quote_for_customer():
    """Generate quote for customer with wholesale pricing and optional sharing"""
    try:
        data = request.get_json()
        user_id = request.current_user.get('user_id')

        # Validate required fields
        required_fields = ['product_type', 'customer_info']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify(f"Missing fields: {', '.join(missing_fields)}"), 400

        customer_info = data['customer_info']
        product_type = data['product_type']
        create_shareable = data.get('create_shareable', True)

        # Validate customer info required fields
        customer_required = ['first_name', 'last_name', 'email']
        customer_missing = [field for field in customer_required if not customer_info.get(field)]
        if customer_missing:
            return jsonify(f"Missing customer fields: {', '.join(customer_missing)}"), 400

        db_manager = get_db_manager()

        if db_manager.available:
            # Get reseller info
            reseller_result = execute_query(
                'SELECT id, commission_rate, business_name, status FROM resellers WHERE user_id = %s',
                (user_id,),
                'one'
            )

            if not reseller_result['success']:
                return jsonify(f"Database error during reseller lookup: {reseller_result.get('error', 'Unknown')}"), 500

            if not reseller_result['data']:
                return jsonify({
                    'error': 'Reseller record not found',
                    'user_id': str(user_id),
                    'help': 'Please ensure your reseller account is properly set up'
                }), 404

            # Access RealDictRow fields by name
            reseller_data = reseller_result['data']
            reseller_id = reseller_data['id']
            commission_rate = reseller_data['commission_rate']
            business_name = reseller_data['business_name']
            reseller_status = reseller_data['status']

            # Check if reseller is active
            if reseller_status != 'active':
                return jsonify({
                    'error': f'Reseller account is {reseller_status}',
                    'help': 'Please contact support to activate your reseller account'
                }), 403

            assigned_reseller_id = user_id

            # Process hero_product_type if it exists and clean coverage suffixes
            hero_product_type = data.get('hero_product_type', product_type)
            original_hero_product_type = hero_product_type
            coverage_amount = None

            # Use regex to clean hero_product_type and extract coverage amount
            coverage_pattern = r'_(\d+)$'  # Matches _500, _1000, _1500, etc. at end of string
            match = re.search(coverage_pattern, hero_product_type)

            if match:
                coverage_amount = int(match.group(1))  # Extract the number (500, 1000, etc.)
                hero_product_type = re.sub(coverage_pattern, '', hero_product_type)  # Remove _XXX from end

            # Check if customer exists by email
            existing_customer = execute_query('''
                                              SELECT id
                                              FROM customers
                                              WHERE contact_info ->>'email' = %s
                                                AND assigned_reseller_id = %s
                                              ''', (customer_info['email'].lower(), assigned_reseller_id), 'one')

            customer_uuid = None

            if existing_customer['success'] and existing_customer['data']:
                # Customer exists, use existing ID
                customer_uuid = existing_customer['data']['id']

                # Update customer info
                update_customer_result = execute_query('''
                                                       UPDATE customers
                                                       SET personal_info = %s,
                                                           contact_info  = %s,
                                                           business_info = %s,
                                                           updated_at    = CURRENT_TIMESTAMP
                                                       WHERE id = %s RETURNING id
                                                       ''', (
                                                           json.dumps({
                                                               'first_name': customer_info['first_name'],
                                                               'last_name': customer_info['last_name']
                                                           }),
                                                           json.dumps({
                                                               'email': customer_info['email'].lower(),
                                                               'phone': customer_info.get('phone', '')
                                                           }),
                                                           json.dumps({
                                                               'company_name': customer_info.get('company', '')
                                                           }),
                                                           customer_uuid
                                                       ), 'one')

            else:
                # Create new customer
                customer_create_result = execute_query('''
                                                       INSERT INTO customers (customer_type, personal_info,
                                                                              contact_info, business_info,
                                                                              assigned_reseller_id, created_at)
                                                       VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP) RETURNING id
                                                       ''', (
                                                           'individual' if not customer_info.get('company') else 'business',
                                                           json.dumps({
                                                               'first_name': customer_info['first_name'],
                                                               'last_name': customer_info['last_name']
                                                           }),
                                                           json.dumps({
                                                               'email': customer_info['email'].lower(),
                                                               'phone': customer_info.get('phone', '')
                                                           }),
                                                           json.dumps({
                                                               'company_name': customer_info.get('company', '')
                                                           }),
                                                           assigned_reseller_id
                                                       ), 'one')

                if customer_create_result['success']:
                    customer_uuid = customer_create_result['data']['id']

                    # Log customer creation
                    SecurityUtils.log_security_event(user_id, 'customer_created_by_reseller', {
                        'customer_id': str(customer_uuid),
                        'customer_email': customer_info['email'],
                        'reseller_user_id': assigned_reseller_id,
                        'reseller_table_id': reseller_id
                    })
                else:
                    return jsonify(f"Failed to create customer: {customer_create_result.get('error', 'Unknown error')}"), 500

            # Generate quote based on product type
            quote_result = None

            if product_type in ['hero', 'home_protection', 'hero_level_protection_home', 'comprehensive_auto_protection',
                                  'home_deductible_reimbursement', 'multi_vehicle_deductible_reimbursement',
                                  'auto_advantage_deductible_reimbursement', 'all_vehicle_deductible_reimbursement',
                                  'auto_rv_deductible_reimbursement']:
                try:
                    from services.hero_rating_service import HeroRatingService
                    hero_service = HeroRatingService()

                    # Use extracted coverage_amount if available, otherwise use provided coverage_limit
                    coverage_limit = coverage_amount if coverage_amount else data.get('coverage_limit', 500)

                    quote_result = hero_service.generate_quote(
                        product_type=hero_product_type,  # Use cleaned hero_product_type
                        term_years=data.get('term_years', 1),
                        coverage_limit=coverage_limit,
                        customer_type='wholesale',
                        state=data.get('state', 'FL'),
                        zip_code=data.get('zip_code', '33101')
                    )
                except ImportError:
                    return jsonify('Hero service not available'), 503

            elif product_type in ['vsc', 'vehicle_service_contract']:
                try:
                    from services.vsc_rating_service import VSCRatingService
                    vsc_service = VSCRatingService()

                    # Use extracted coverage_amount for deductible if available
                    deductible = coverage_amount if coverage_amount else data.get('deductible', 100)

                    quote_result = vsc_service.generate_quote(
                        make=data.get('make', ''),
                        year=data.get('year', 2020),
                        mileage=data.get('mileage', 50000),
                        coverage_level=data.get('coverage_level', 'gold'),
                        term_months=data.get('term_months', 36),
                        deductible=deductible,
                        customer_type='wholesale'
                    )
                except ImportError:
                    return jsonify('VSC service not available'), 503
            else:
                return jsonify({
                    'error': f'Unsupported product type: {product_type}',
                    'supported_types': [
                        'hero', 'home_protection', 'hero_level_protection_home',
                        'vsc', 'vehicle_service_contract', 'comprehensive_auto_protection',
                        'home_deductible_reimbursement', 'multi_vehicle_deductible_reimbursement',
                        'auto_advantage_deductible_reimbursement', 'all_vehicle_deductible_reimbursement',
                        'auto_rv_deductible_reimbursement'
                    ],
                    'note': 'Vehicle and auto products can have _500 or _1000 suffixes (e.g., all_vehicle_deductible_reimbursement_500)'
                }), 400

            if not quote_result or not quote_result.get('success'):
                return jsonify(quote_result.get('error', 'Quote generation failed')), 400

            # Calculate commission
            total_price = quote_result.get('pricing_breakdown', {}).get('total_price', 0)
            commission_amount = total_price * float(commission_rate)

            # Generate share token if requested
            share_token = None
            share_url = None
            if create_shareable:
                share_token = str(uuid.uuid4())
                share_url = f"{FRONTEND_BASE_URL}/quote/shared/{share_token}"

            # Save quote to database
            quote_id = f"QTE-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:8].upper()}"
            expires_at = datetime.now(timezone.utc) + timedelta(days=30)

            save_quote_result = execute_query('''
                                              INSERT INTO quotes (quote_id, customer_id, reseller_id, product_type,
                                                                  quote_data,
                                                                  total_price, commission_amount, status, created_by,
                                                                  created_at,
                                                                  expires_at, share_token, is_shareable, shared_at,
                                                                  customer_info)
                                              VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s,
                                                      %s, %s) RETURNING id
                                              ''', (
                                                  quote_id, customer_uuid, user_id, product_type,
                                                  json.dumps(quote_result),
                                                  total_price, commission_amount, 'active', user_id, expires_at,
                                                  share_token, create_shareable,
                                                  datetime.now(timezone.utc) if create_shareable else None,
                                                  json.dumps(customer_info)
                                              ), 'one')

            if not save_quote_result['success']:
                return jsonify(f"Failed to save quote: {save_quote_result.get('error', 'Unknown error')}"), 500

            quote_uuid = save_quote_result['data']['id']

            # Log quote creation activity
            try:
                execute_query('''
                              INSERT INTO quote_activities (quote_id, activity_type, actor_type, actor_id, description,
                                                            ip_address)
                              VALUES (%s, %s, %s, %s, %s, %s)
                              ''', (
                                  quote_uuid, 'created', 'reseller', user_id,
                                  f'Quote created for customer: {customer_info["first_name"]} {customer_info["last_name"]}',
                                  request.remote_addr
                              ), 'none')
            except Exception:
                pass  # Don't fail the whole request if activity logging fails

            # Prepare response
            response_data = {
                'success': True,
                'quote_id': quote_id,
                'quote_uuid': str(quote_uuid),
                'customer_id': str(customer_uuid),
                'expires_at': expires_at.isoformat() + 'Z',
                'reseller_info': {
                    'reseller_id': str(reseller_id),
                    'commission_rate': float(commission_rate),
                    'estimated_commission': commission_amount
                },
                **quote_result
            }

            # Add sharing info if applicable
            if create_shareable and share_token:
                response_data['sharing'] = {
                    'share_token': share_token,
                    'share_url': share_url,
                    'shareable': True
                }

            return jsonify(response_data)

        else:
            return jsonify('Database not available'), 503

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify(f'Quote generation failed: {str(e)}'), 500


@reseller_bp.route('/quotes/<quote_id>/share', methods=['POST'])
@token_required
@role_required('wholesale_reseller')
def create_shareable_quote(quote_id):
    """Make an existing quote shareable"""
    try:
        user_id = request.current_user.get('user_id')
        
        # Check if quote exists and belongs to this reseller
        quote_result = execute_query('''
            SELECT id, share_token, is_shareable 
            FROM quotes 
            WHERE quote_id = %s AND reseller_id = %s AND status = 'active'
        ''', (quote_id, user_id), 'one')
        
        if not quote_result['success'] or not quote_result['data']:
            return jsonify('Quote not found or access denied'), 404
        
        quote_uuid, existing_token, is_shareable = quote_result['data']
        
        if is_shareable and existing_token:
            # Already shareable, return existing info
            share_url_result = execute_query('''
                SELECT share_url FROM quotes WHERE id = %s
            ''', (quote_uuid,), 'one')
            
            return jsonify({
                'success': True,
                'share_token': existing_token,
                'share_url': share_url_result['data'][0] if share_url_result['success'] else None,
                'message': 'Quote is already shareable'
            })
        
        # Generate new share token
        share_token_result = execute_query('SELECT generate_quote_share_token()', (), 'one')
        if not share_token_result['success']:
            return jsonify('Failed to generate share token'), 500
        
        share_token = share_token_result['data'][0]
        
        # Update quote to make it shareable
        update_result = execute_query('''
            UPDATE quotes 
            SET share_token = %s, is_shareable = true, shared_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING share_url
        ''', (share_token, quote_uuid), 'one')
        
        if not update_result['success']:
            return jsonify('Failed to update quote'), 500
        
        share_url = update_result['data'][0]
        
        # Log sharing activity
        execute_query('''
            INSERT INTO quote_activities (quote_id, activity_type, actor_type, actor_id, description, ip_address)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (
            quote_uuid, 'shared', 'reseller', user_id,
            'Quote made shareable', request.remote_addr
        ), 'none')
        
        return jsonify({
            'success': True,
            'share_token': share_token,
            'share_url': share_url,
            'message': 'Quote is now shareable'
        })
        
    except Exception as e:
        return jsonify(f'Failed to create shareable quote: {str(e)}'), 500


@reseller_bp.route('/quotes', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def get_reseller_quotes():
    """Get all quotes for the current reseller"""
    try:
        user_id = request.current_user.get('user_id')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'all')
        
        offset = (page - 1) * limit
        
        # Build query based on status filter
        status_condition = ""
        params = [user_id, limit, offset]
        
        if status != 'all':
            status_condition = "AND q.status = %s"
            params.insert(1, status)
        
        quotes_result = execute_query(f'''
            SELECT q.quote_id, q.product_type, q.total_price, q.commission_amount, 
                   q.status, q.created_at, q.expires_at, q.is_shareable, q.share_url,
                   q.converted_to_policy, c.personal_info->>'first_name' as customer_first_name,
                   c.personal_info->>'last_name' as customer_last_name,
                   c.contact_info->>'email' as customer_email
            FROM quotes q
            JOIN customers c ON q.customer_id = c.id
            WHERE q.reseller_id = %s {status_condition}
            ORDER BY q.created_at DESC
            LIMIT %s OFFSET %s
        ''', tuple(params), 'all')
        
        if not quotes_result['success']:
            return jsonify('Failed to fetch quotes'), 500
        
        # Get total count for pagination
        count_params = [user_id]
        if status != 'all':
            count_params.append(status)
        
        count_result = execute_query(f'''
            SELECT COUNT(*) as total 
            FROM quotes 
            WHERE reseller_id = %s {status_condition}
        ''', tuple(count_params), 'one')
        
        total_quotes = count_result['data'][0] if count_result['success'] else 0
        
        return jsonify({
            'success': True,
            'quotes': quotes_result['data'] or [],
            'pagination': {
                'current_page': page,
                'total_pages': (total_quotes + limit - 1) // limit,
                'total_items': total_quotes,
                'items_per_page': limit
            }
        })
        
    except Exception as e:
        return jsonify(f'Failed to fetch quotes: {str(e)}'), 500


@reseller_bp.route('/sales/dashboard', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def get_sales_dashboard():
    """Get sales dashboard data for reseller"""
    try:
        user_id = request.current_user.get('user_id')
        
        # Get dashboard stats from the view we created
        stats_result = execute_query('''
            SELECT * FROM reseller_dashboard_stats WHERE reseller_id = %s
        ''', (user_id,), 'one')
        
        if not stats_result['success']:
            return jsonify('Failed to fetch dashboard stats'), 500
        
        # Get recent sales
        recent_sales_result = execute_query('''
            SELECT rs.sale_date, rs.product_type, rs.gross_amount, rs.commission_amount,
                   rs.commission_status, c.personal_info->>'first_name' as customer_first_name,
                   c.personal_info->>'last_name' as customer_last_name
            FROM reseller_sales rs
            JOIN customers c ON rs.customer_id = c.id
            WHERE rs.reseller_id = %s
            ORDER BY rs.sale_date DESC
            LIMIT 10
        ''', (user_id,), 'all')
        
        # Get monthly commission summary
        monthly_summary_result = execute_query('''
            SELECT DATE_TRUNC('month', sale_date) as month,
                   COUNT(*) as sales_count,
                   SUM(gross_amount) as total_sales,
                   SUM(commission_amount) as total_commission
            FROM reseller_sales
            WHERE reseller_id = %s AND sale_date >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '11 months'
            GROUP BY DATE_TRUNC('month', sale_date)
            ORDER BY month DESC
        ''', (user_id,), 'all')
        
        return jsonify({
            'success': True,
            'stats': stats_result['data'],
            'recent_sales': recent_sales_result['data'] or [],
            'monthly_summary': monthly_summary_result['data'] or []
        })
        
    except Exception as e:
        return jsonify(f'Failed to fetch dashboard data: {str(e)}'), 500

# ================================
# RESELLER TOOLS & RESOURCES
# ================================

@reseller_bp.route('/tools/marketing-materials', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def get_marketing_materials():
    """Get available marketing materials for resellers"""
    try:
        user_id = request.current_user.get('user_id')
        
        # Return available marketing materials
        marketing_materials = {
            'brochures': [
                {
                    'id': 'hero-brochure-2025',
                    'title': 'Hero Protection Plans Brochure',
                    'description': 'Comprehensive overview of Hero protection plans',
                    'file_type': 'PDF',
                    'file_size': '2.5 MB',
                    'download_url': '/assets/marketing/hero-brochure-2025.pdf',
                    'last_updated': '2025-01-15'
                },
                {
                    'id': 'vsc-overview-2025',
                    'title': 'Vehicle Service Contract Overview',
                    'description': 'VSC benefits and coverage explanation',
                    'file_type': 'PDF',
                    'file_size': '1.8 MB',
                    'download_url': '/assets/marketing/vsc-overview-2025.pdf',
                    'last_updated': '2025-01-10'
                }
            ],
            'presentations': [
                {
                    'id': 'sales-deck-2025',
                    'title': 'Sales Presentation Deck',
                    'description': 'Complete sales presentation for customer meetings',
                    'file_type': 'PPTX',
                    'file_size': '15.2 MB',
                    'download_url': '/assets/marketing/sales-deck-2025.pptx',
                    'last_updated': '2025-01-20'
                }
            ],
            'digital_assets': [
                {
                    'id': 'email-templates',
                    'title': 'Email Marketing Templates',
                    'description': 'Pre-designed email templates for customer outreach',
                    'file_type': 'ZIP',
                    'file_size': '5.1 MB',
                    'download_url': '/assets/marketing/email-templates.zip',
                    'last_updated': '2025-01-12'
                },
                {
                    'id': 'social-media-kit',
                    'title': 'Social Media Kit',
                    'description': 'Images and copy for social media marketing',
                    'file_type': 'ZIP',
                    'file_size': '12.8 MB',
                    'download_url': '/assets/marketing/social-media-kit.zip',
                    'last_updated': '2025-01-18'
                }
            ],
            'training_materials': [
                {
                    'id': 'product-training-video',
                    'title': 'Product Training Video Series',
                    'description': 'Complete training on all protection products',
                    'file_type': 'Video Link',
                    'duration': '45 minutes',
                    'download_url': '/training/product-training-series',
                    'last_updated': '2025-01-05'
                }
            ]
        }
        
        # Log access
        SecurityUtils.log_security_event(user_id, 'marketing_materials_accessed', {
            'materials_count': sum(len(materials) for materials in marketing_materials.values())
        })
        
        return jsonify(marketing_materials)

    except Exception as e:
        return jsonify(f'Failed to get marketing materials: {str(e)}'), 500

@reseller_bp.route('/tools/commission-calculator', methods=['POST'])
@token_required
@role_required('wholesale_reseller')
def calculate_commission():
    """Calculate potential commission for given sale amount"""
    try:
        data = request.get_json()
        user_id = request.current_user.get('user_id')
        
        if not data.get('sale_amount'):
            return jsonify('sale_amount is required'), 400
        
        sale_amount = float(data['sale_amount'])
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get reseller commission rate
            reseller_result = execute_query(
                'SELECT commission_rate FROM resellers WHERE user_id = %s',
                (user_id,),
                'one'
            )
            
            if reseller_result['success'] and reseller_result['data']:
                commission_rate = float(reseller_result['data'][0])
                
                commission_calculation = {
                    'sale_amount': sale_amount,
                    'commission_rate': commission_rate,
                    'commission_amount': sale_amount * commission_rate,
                    'net_to_company': sale_amount * (1 - commission_rate),
                    'calculation_details': {
                        'commission_percentage': f"{commission_rate * 100:.1f}%",
                        'breakdown': {
                            'gross_sale': sale_amount,
                            'commission_earned': round(sale_amount * commission_rate, 2),
                            'company_revenue': round(sale_amount * (1 - commission_rate), 2)
                        }
                    }
                }
                
                return jsonify(commission_calculation)
            else:
                return jsonify('Reseller record not found'), 404
        else:
            # Default commission rate when database not available
            default_rate = 0.15
            return jsonify({
                'sale_amount': sale_amount,
                'commission_rate': default_rate,
                'commission_amount': sale_amount * default_rate,
                'note': 'Using default commission rate - connect to update with your actual rate'
            })

    except Exception as e:
        return jsonify(f'Commission calculation failed: {str(e)}'), 500

# ================================
# ERROR HANDLERS
# ================================

@reseller_bp.errorhandler(401)
def unauthorized(error):
    """Handle unauthorized access"""
    return jsonify('Authentication required for reseller access'), 401

@reseller_bp.errorhandler(403)
def forbidden(error):
    """Handle forbidden access"""
    return jsonify('Insufficient permissions for reseller operation'), 403

@reseller_bp.errorhandler(404)
def not_found(error):
    """Handle not found errors"""
    return jsonify('Reseller resource not found'), 404

@reseller_bp.errorhandler(500)
def internal_error(error):
    """Handle internal server errors"""
    return jsonify('Internal reseller service error'), 500
                

# ================================
# COMMISSION MANAGEMENT
# ================================

@reseller_bp.route('/commissions', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def get_commissions():
    """Get reseller commission history and statements"""
    try:
        user_id = request.current_user.get('user_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        period = request.args.get('period', 'all')  
        status_filter = request.args.get('status')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get reseller info
            reseller_result = execute_query(
                'SELECT reseller_id, commission_rate FROM resellers WHERE user_id = %s',
                (user_id,),
                'one'
            )
            
            if reseller_result['success'] and reseller_result['data']:
                reseller_id, commission_rate = reseller_result['data']
                
                # Build date filter
                date_conditions = []
                if period == 'current_month':
                    date_conditions.append("t.created_at >= DATE_TRUNC('month', CURRENT_DATE)")
                elif period == 'last_month':
                    date_conditions.append("t.created_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month'")
                    date_conditions.append("t.created_at < DATE_TRUNC('month', CURRENT_DATE)")
                elif period == 'year':
                    date_conditions.append("t.created_at >= DATE_TRUNC('year', CURRENT_DATE)")
                
                # Build query conditions
                where_conditions = ['c.assigned_reseller_id = %s', 't.status = %s']
                params = [reseller_id, 'completed']
                
                if date_conditions:
                    where_conditions.extend(date_conditions)
                
                if status_filter:
                    where_conditions.append("cm.status = %s")
                    params.append(status_filter)
                
                where_clause = ' AND '.join(where_conditions)
                
                # Get commission transactions
                commissions_result = execute_query(f'''
                    SELECT 
                        t.transaction_number,
                        t.amount as transaction_amount,
                        t.amount * %s as commission_amount,
                        t.created_at as transaction_date,
                        c.first_name || ' ' || c.last_name as customer_name,
                        c.customer_id,
                        COALESCE(cm.status, 'pending') as commission_status,
                        COALESCE(cm.paid_date, NULL) as paid_date
                    FROM transactions t
                    JOIN customers c ON t.customer_id = c.customer_id
                    LEFT JOIN commission_payments cm ON t.id = cm.transaction_id
                    WHERE {where_clause}
                    ORDER BY t.created_at DESC
                    LIMIT %s OFFSET %s
                ''', tuple([commission_rate] + params + [per_page, (page - 1) * per_page]))
                
                if commissions_result['success']:
                    commissions = []
                    total_pending = 0.0
                    total_paid = 0.0
                    
                    for commission in commissions_result['data']:
                        commission_dict = {
                            'transaction_number': commission[0],
                            'transaction_amount': float(commission[1]),
                            'commission_amount': float(commission[2]),
                            'transaction_date': commission[3].isoformat() if commission[3] else None,
                            'customer_name': commission[4],
                            'customer_id': commission[5],
                            'commission_status': commission[6],
                            'paid_date': commission[7].isoformat() if commission[7] else None
                        }
                        
                        if commission_dict['commission_status'] == 'paid':
                            total_paid += commission_dict['commission_amount']
                        else:
                            total_pending += commission_dict['commission_amount']
                        
                        commissions.append(commission_dict)
                    
                    # Get summary statistics
                    summary_result = execute_query(f'''
                        SELECT 
                            COUNT(*) as total_transactions,
                            SUM(t.amount) as total_sales,
                            SUM(t.amount * %s) as total_commissions,
                            AVG(t.amount * %s) as avg_commission
                        FROM transactions t
                        JOIN customers c ON t.customer_id = c.customer_id
                        WHERE {where_clause}
                    ''', tuple([commission_rate, commission_rate] + params))
                    
                    summary = {}
                    if summary_result['success'] and summary_result['data']:
                        stats = summary_result['data'][0]
                        summary = {
                            'total_transactions': stats[0],
                            'total_sales': float(stats[1]) if stats[1] else 0.0,
                            'total_commissions': float(stats[2]) if stats[2] else 0.0,
                            'average_commission': float(stats[3]) if stats[3] else 0.0,
                            'commission_rate': float(commission_rate),
                            'total_pending': total_pending,
                            'total_paid': total_paid
                        }
                    
                    return jsonify({
                        'commissions': commissions,
                        'summary': summary,
                        'pagination': {
                            'page': page,
                            'per_page': per_page,
                            'total': len(commissions)
                        },
                        'filters': {
                            'period': period,
                            'status': status_filter
                        }
                    })
                else:
                    return jsonify('Failed to fetch commissions'), 500
            else:
                return jsonify('Reseller record not found'), 404
        else:
            return jsonify({
                'commissions': [],
                'summary': {'total_commissions': 0, 'total_pending': 0, 'total_paid': 0},
                'source': 'database_unavailable'
            })

    except Exception as e:
        return jsonify(f'Failed to get commissions: {str(e)}'), 500

@reseller_bp.route('/commissions/summary', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def get_commission_summary():
    """Get commission summary by period"""
    try:
        user_id = request.current_user.get('user_id')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get reseller info
            reseller_result = execute_query(
                'SELECT reseller_id, commission_rate FROM resellers WHERE user_id = %s',
                (user_id,),
                'one'
            )
            
            if reseller_result['success'] and reseller_result['data']:
                reseller_id, commission_rate = reseller_result['data']
                
                # Get commission summary by month (last 12 months)
                monthly_summary = execute_query('''
                    SELECT 
                        EXTRACT(YEAR FROM t.created_at) as year,
                        EXTRACT(MONTH FROM t.created_at) as month,
                        COUNT(*) as transaction_count,
                        SUM(t.amount) as sales_volume,
                        SUM(t.amount * %s) as commission_earned,
                        COUNT(CASE WHEN cm.status = 'paid' THEN 1 END) as paid_count,
                        SUM(CASE WHEN cm.status = 'paid' THEN t.amount * %s ELSE 0 END) as paid_amount
                    FROM transactions t
                    JOIN customers c ON t.customer_id = c.customer_id
                    LEFT JOIN commission_payments cm ON t.id = cm.transaction_id
                    WHERE c.assigned_reseller_id = %s AND t.status = 'completed'
                    AND t.created_at >= CURRENT_DATE - INTERVAL '12 months'
                    GROUP BY EXTRACT(YEAR FROM t.created_at), EXTRACT(MONTH FROM t.created_at)
                    ORDER BY year DESC, month DESC
                ''', (commission_rate, commission_rate, reseller_id))
                
                commission_summary = {
                    'monthly_breakdown': [],
                    'totals': {
                        'total_earned': 0.0,
                        'total_paid': 0.0,
                        'total_pending': 0.0,
                        'total_transactions': 0
                    }
                }
                
                if monthly_summary['success']:
                    for row in monthly_summary['data']:
                        month_data = {
                            'year': int(row[0]),
                            'month': int(row[1]),
                            'transaction_count': row[2],
                            'sales_volume': float(row[3]),
                            'commission_earned': float(row[4]),
                            'paid_count': row[5],
                            'paid_amount': float(row[6]),
                            'pending_amount': float(row[4]) - float(row[6])
                        }
                        commission_summary['monthly_breakdown'].append(month_data)
                        
                        # Add to totals
                        commission_summary['totals']['total_earned'] += month_data['commission_earned']
                        commission_summary['totals']['total_paid'] += month_data['paid_amount']
                        commission_summary['totals']['total_pending'] += month_data['pending_amount']
                        commission_summary['totals']['total_transactions'] += month_data['transaction_count']
                
                return jsonify(commission_summary)
            else:
                return jsonify('Reseller record not found'), 404
        else:
            return jsonify({
                'monthly_breakdown': [],
                'totals': {'total_earned': 0, 'total_paid': 0, 'total_pending': 0},
                'source': 'database_unavailable'
            })

    except Exception as e:
        return jsonify(f'Failed to get commission summary: {str(e)}'), 500

# ================================
# SALES ANALYTICS & REPORTS
# ================================

@reseller_bp.route('/analytics', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def get_reseller_analytics():
    """Get comprehensive reseller analytics"""
    try:
        user_id = request.current_user.get('user_id')
        date_range = request.args.get('date_range', '12')  # months
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get reseller info
            reseller_result = execute_query(
                'SELECT reseller_id, commission_rate FROM resellers WHERE user_id = %s',
                (user_id,),
                'one'
            )
            
            if reseller_result['success'] and reseller_result['data']:
                reseller_id, commission_rate = reseller_result['data']
                
                analytics_data = {
                    'performance_metrics': {},
                    'sales_trends': [],
                    'customer_analytics': {},
                    'product_performance': [],
                    'commission_analytics': {},
                    'comparative_analysis': {}
                }
                
                # Performance metrics
                performance_result = execute_query(f'''
                    SELECT 
                        COUNT(DISTINCT c.customer_id) as total_customers,
                        COUNT(DISTINCT t.id) as total_transactions,
                        COALESCE(SUM(CASE WHEN t.status = 'completed' THEN t.amount ELSE 0 END), 0) as total_sales,
                        COALESCE(SUM(CASE WHEN t.status = 'completed' THEN t.amount * %s ELSE 0 END), 0) as total_commissions,
                        COALESCE(AVG(CASE WHEN t.status = 'completed' THEN t.amount ELSE NULL END), 0) as avg_transaction_value,
                        COUNT(DISTINCT p.id) as total_policies
                    FROM customers c
                    LEFT JOIN transactions t ON c.customer_id = t.customer_id 
                        AND t.created_at >= CURRENT_DATE - INTERVAL '{date_range} months'
                    LEFT JOIN policies p ON c.customer_id = p.customer_id
                    WHERE c.assigned_reseller_id = %s
                ''', (commission_rate, reseller_id), 'one')
                
                if performance_result['success'] and performance_result['data']:
                    stats = performance_result['data']
                    analytics_data['performance_metrics'] = {
                        'total_customers': stats[0],
                        'total_transactions': stats[1],
                        'total_sales': float(stats[2]),
                        'total_commissions': float(stats[3]),
                        'avg_transaction_value': float(stats[4]),
                        'total_policies': stats[5],
                        'commission_rate': float(commission_rate),
                        'date_range_months': int(date_range)
                    }
                
                # Sales trends
                trends_result = execute_query(f'''
                    SELECT 
                        EXTRACT(YEAR FROM t.created_at) as year,
                        EXTRACT(MONTH FROM t.created_at) as month,
                        COUNT(*) as transaction_count,
                        SUM(t.amount) as sales_volume,
                        SUM(t.amount * %s) as commission_earned,
                        COUNT(DISTINCT c.customer_id) as unique_customers
                    FROM transactions t
                    JOIN customers c ON t.customer_id = c.customer_id
                    WHERE c.assigned_reseller_id = %s AND t.status = 'completed'
                    AND t.created_at >= CURRENT_DATE - INTERVAL '{date_range} months'
                    GROUP BY EXTRACT(YEAR FROM t.created_at), EXTRACT(MONTH FROM t.created_at)
                    ORDER BY year, month
                ''', (commission_rate, reseller_id))
                
                if trends_result['success']:
                    for row in trends_result['data']:
                        analytics_data['sales_trends'].append({
                            'year': int(row[0]),
                            'month': int(row[1]),
                            'transaction_count': row[2],
                            'sales_volume': float(row[3]),
                            'commission_earned': float(row[4]),
                            'unique_customers': row[5]
                        })
                
                # Customer analytics
                customer_analytics_result = execute_query(f'''
                    SELECT 
                        COUNT(*) FILTER (WHERE c.created_at >= CURRENT_DATE - INTERVAL '{date_range} months') as new_customers,
                        COUNT(*) FILTER (WHERE c.last_transaction_date >= CURRENT_DATE - INTERVAL '30 days') as active_customers,
                        COALESCE(AVG(customer_metrics.transaction_count), 0) as avg_transactions_per_customer,
                        COALESCE(AVG(customer_metrics.total_spent), 0) as avg_customer_value
                    FROM customers c
                    LEFT JOIN (
                        SELECT 
                            customer_id,
                            COUNT(*) as transaction_count,
                            SUM(amount) as total_spent
                        FROM transactions 
                        WHERE status = 'completed'
                        GROUP BY customer_id
                    ) customer_metrics ON c.customer_id = customer_metrics.customer_id
                    WHERE c.assigned_reseller_id = %s
                ''', (reseller_id,), 'one')
                
                if customer_analytics_result['success'] and customer_analytics_result['data']:
                    stats = customer_analytics_result['data']
                    analytics_data['customer_analytics'] = {
                        'new_customers': stats[0],
                        'active_customers': stats[1],
                        'avg_transactions_per_customer': float(stats[2]),
                        'avg_customer_value': float(stats[3])
                    }
                
                # Product performance
                product_performance_result = execute_query('''
                    SELECT 
                        p.product_type,
                        COUNT(*) as policy_count,
                        SUM(p.premium_amount) as total_premiums,
                        AVG(p.premium_amount) as avg_premium
                    FROM policies p
                    JOIN customers c ON p.customer_id = c.customer_id
                    WHERE c.assigned_reseller_id = %s
                    GROUP BY p.product_type
                    ORDER BY total_premiums DESC
                ''', (reseller_id,))
                
                if product_performance_result['success']:
                    for row in product_performance_result['data']:
                        analytics_data['product_performance'].append({
                            'product_type': row[0],
                            'policy_count': row[1],
                            'total_premiums': float(row[2]) if row[2] else 0.0,
                            'avg_premium': float(row[3]) if row[3] else 0.0
                        })
                
                return jsonify(analytics_data)
            else:
                return jsonify('Reseller record not found'), 404
        else:
            return jsonify({
                'performance_metrics': {'total_sales': 0, 'total_commissions': 0},
                'sales_trends': [],
                'customer_analytics': {},
                'product_performance': [],
                'source': 'database_unavailable'
            })

    except Exception as e:
        return jsonify(f'Failed to get analytics: {str(e)}'), 500


@reseller_bp.route('/quotes/<quote_id>', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def get_quote_details(quote_id):
    """Get detailed information about a specific quote"""
    try:
        user_id = request.current_user.get('user_id')
        
        quote_result = execute_query('''
            SELECT q.quote_id, q.product_type, q.quote_data, q.total_price, q.commission_amount,
                   q.status, q.created_at, q.expires_at, q.is_shareable, q.share_url,
                   q.converted_to_policy, q.converted_at, q.customer_accessed_at,
                   c.personal_info, c.contact_info, c.business_info,
                   r.business_name as reseller_name
            FROM quotes q
            JOIN customers c ON q.customer_id = c.id
            JOIN resellers r ON q.reseller_id = r.user_id
            WHERE q.quote_id = %s AND q.reseller_id = %s
        ''', (quote_id, user_id), 'one')
        
        if not quote_result['success'] or not quote_result['data']:
            return jsonify('Quote not found'), 404
        
        quote_data = quote_result['data']
        
        # Get quote activities
        activities_result = execute_query('''
            SELECT activity_type, actor_type, description, created_at, ip_address
            FROM quote_activities
            WHERE quote_id = (SELECT id FROM quotes WHERE quote_id = %s)
            ORDER BY created_at DESC
        ''', (quote_id,), 'all')
        
        return jsonify({
            'success': True,
            'quote': {
                'quote_id': quote_data[0],
                'product_type': quote_data[1],
                'quote_data': json.loads(quote_data[2]) if quote_data[2] else {},
                'total_price': float(quote_data[3]),
                'commission_amount': float(quote_data[4]),
                'status': quote_data[5],
                'created_at': quote_data[6].isoformat() + 'Z',
                'expires_at': quote_data[7].isoformat() + 'Z' if quote_data[7] else None,
                'is_shareable': quote_data[8],
                'share_url': quote_data[9],
                'converted_to_policy': quote_data[10],
                'converted_at': quote_data[11].isoformat() + 'Z' if quote_data[11] else None,
                'customer_accessed_at': quote_data[12].isoformat() + 'Z' if quote_data[12] else None,
                'customer_info': {
                    'personal': json.loads(quote_data[13]) if quote_data[13] else {},
                    'contact': json.loads(quote_data[14]) if quote_data[14] else {},
                    'business': json.loads(quote_data[15]) if quote_data[15] else {}
                }
            },
            'activities': activities_result['data'] or []
        })
        
    except Exception as e:
        return jsonify(f'Failed to fetch quote details: {str(e)}'), 500


@reseller_bp.route('/quotes/<quote_id>/duplicate', methods=['POST'])
@token_required
@role_required('wholesale_reseller')
def duplicate_quote(quote_id):
    """Create a duplicate of an existing quote with optional modifications"""
    try:
        user_id = request.current_user.get('user_id')
        data = request.get_json() or {}
        
        # Get original quote
        original_quote_result = execute_query('''
            SELECT customer_id, product_type, quote_data, reseller_id
            FROM quotes
            WHERE quote_id = %s AND reseller_id = %s
        ''', (quote_id, user_id), 'one')
        
        if not original_quote_result['success'] or not original_quote_result['data']:
            return jsonify('Original quote not found'), 404
        
        customer_id, product_type, quote_data_str, reseller_id = original_quote_result['data']
        original_quote_data = json.loads(quote_data_str) if quote_data_str else {}
        
        # Merge original data with any modifications
        new_quote_data = {**original_quote_data}
        if 'modifications' in data:
            new_quote_data.update(data['modifications'])
        
        # Generate new quote using the original parameters
        # This would call the same quote generation logic as before
        # For simplicity, we'll create a basic duplicate
        
        new_quote_id = f"QTE-DUP-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        
        # Get commission rate
        commission_result = execute_query('''
            SELECT commission_rate FROM resellers WHERE user_id = %s
        ''', (reseller_id,), 'one')
        
        commission_rate = commission_result['data'][0] if commission_result['success'] else 0.05
        total_price = original_quote_data.get('pricing_breakdown', {}).get('total_price', 0)
        commission_amount = total_price * float(commission_rate)
        
        # Create duplicate quote
        duplicate_result = execute_query('''
            INSERT INTO quotes (
                quote_id, customer_id, reseller_id, product_type, quote_data,
                total_price, commission_amount, status, created_by, expires_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            new_quote_id, customer_id, reseller_id, product_type, json.dumps(new_quote_data),
            total_price, commission_amount, 'active', user_id, expires_at
        ), 'one')
        
        if duplicate_result['success']:
            quote_uuid = duplicate_result['data'][0]
            
            # Log duplication activity
            execute_query('''
                INSERT INTO quote_activities (quote_id, activity_type, actor_type, actor_id, description)
                VALUES (%s, %s, %s, %s, %s)
            ''', (
                quote_uuid, 'created', 'reseller', user_id,
                f'Quote duplicated from {quote_id}'
            ), 'none')
            
            return jsonify({
                'success': True,
                'new_quote_id': new_quote_id,
                'message': 'Quote duplicated successfully'
            })
        
        return jsonify('Failed to duplicate quote'), 500
        
    except Exception as e:
        return jsonify(f'Failed to duplicate quote: {str(e)}'), 500


@reseller_bp.route('/sales/commissions', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def get_commission_history():
    """Get commission payment history"""
    try:
        user_id = request.current_user.get('user_id')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'all')
        
        offset = (page - 1) * limit
        
        # Build query
        status_condition = ""
        params = [user_id, limit, offset]
        
        if status != 'all':
            status_condition = "AND commission_status = %s"
            params.insert(1, status)
        
        commissions_result = execute_query(f'''
            SELECT rs.sale_date, rs.product_type, rs.gross_amount, rs.commission_amount,
                   rs.commission_status, rs.payment_date, rs.sale_type,
                   c.personal_info->>'first_name' as customer_first_name,
                   c.personal_info->>'last_name' as customer_last_name,
                   q.quote_id
            FROM reseller_sales rs
            JOIN customers c ON rs.customer_id = c.id
            LEFT JOIN quotes q ON rs.quote_id = q.id
            WHERE rs.reseller_id = %s {status_condition}
            ORDER BY rs.sale_date DESC
            LIMIT %s OFFSET %s
        ''', tuple(params), 'all')
        
        # Get summary
        summary_result = execute_query(f'''
            SELECT 
                COUNT(*) as total_sales,
                SUM(commission_amount) as total_commission,
                SUM(CASE WHEN commission_status = 'paid' THEN commission_amount ELSE 0 END) as paid_commission,
                SUM(CASE WHEN commission_status = 'pending' THEN commission_amount ELSE 0 END) as pending_commission
            FROM reseller_sales 
            WHERE reseller_id = %s {status_condition.replace('AND ', 'AND ')}
        ''', [user_id] + ([status] if status != 'all' else []), 'one')
        
        return jsonify({
            'success': True,
            'commissions': commissions_result['data'] or [],
            'summary': summary_result['data'] if summary_result['success'] else {},
            'pagination': {
                'current_page': page,
                'items_per_page': limit
            }
        })
        
    except Exception as e:
        return jsonify(f'Failed to fetch commission history: {str(e)}'), 500
    


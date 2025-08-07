"""
Admin Management Endpoints
User management, system settings, and administrative functions
"""

import json
from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
import uuid
import os
from utils.database import get_db_manager, execute_query
from utils.service_availability import ServiceChecker

# Initialize blueprint
admin_bp = Blueprint('admin', __name__)

# Import admin services with error handling
try:
    from auth.user_auth import DatabaseUserAuth as UserAuth, token_required, role_required, DatabaseSecurityUtils as SecurityUtils
    admin_services_available = True
    
except ImportError as e:
    print(f"Warning: Admin services not available: {e}")
    admin_services_available = False
    
    # Create fallback classes
    class UserAuth:
        @staticmethod
        def hash_password(password):
            import bcrypt
            return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    class SecurityUtils:
        @staticmethod
        def log_security_event(user_id, event, data):
            print(f"Security Event: {user_id} - {event} - {data}")
    
    def token_required(f):
        def decorated(*args, **kwargs):
            return jsonify({'error': 'Authentication not available'}), 503
        return decorated
    
    def role_required(role):
        def decorator(f):
            def decorated(*args, **kwargs):
                return jsonify({'error': 'Authorization not available'}), 503
            return decorated
        return decorator

@admin_bp.route('/health')
def admin_health():
    """Admin panel health check"""
    try:
        service_checker = ServiceChecker()
        
        return jsonify({
            'service': 'Admin Management API',
            'status': 'healthy' if admin_services_available else 'degraded',
            'admin_services_available': admin_services_available,
            'features': {
                'user_management': admin_services_available,
                'system_settings': service_checker.database_settings_available,
                'product_management': True,
                'analytics': True,
                'security_monitoring': True
            },
            'database_integration': service_checker.database_settings_available,
            'timestamp': datetime.now(timezone.utc).isoformat() + "Z"
        })
    except Exception as e:
        return jsonify({
            'service': 'Admin Management API',
            'status': 'error',
            'error': str(e)
        }), 500

@admin_bp.route('/users', methods=['GET'])
@token_required
@role_required('admin')
def get_all_users():
    """Get all users with filtering and pagination"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)  # Limit max per_page
        role_filter = request.args.get('role')
        status_filter = request.args.get('status')
        search_term = request.args.get('search', '')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Build query with filters
            where_conditions = []
            params = []
            
            if role_filter and role_filter in ['admin', 'wholesale_reseller', 'customer']:
                where_conditions.append("role = %s")
                params.append(role_filter)
            
            if status_filter and status_filter in ['active', 'inactive', 'suspended', 'deleted']:
                where_conditions.append("status = %s")
                params.append(status_filter)
            
            if search_term:
                where_conditions.append("""
                    (LOWER(email) LIKE LOWER(%s) 
                     OR LOWER(profile::text) LIKE LOWER(%s))
                """)
                search_pattern = f'%{search_term}%'
                params.extend([search_pattern, search_pattern])
            
            where_clause = ' AND '.join(where_conditions) if where_conditions else '1=1'
            
            # Get total count first
            count_query = f"SELECT COUNT(*) as total FROM users WHERE {where_clause}"
            count_result = execute_query(count_query, tuple(params), 'one')
            
            total_count = 0
            if count_result['success'] and count_result['data']:
                total_count = int(count_result['data']['total']) if 'total' in count_result['data'] else int(count_result['data'][0])
            
            # Get paginated users
            offset = (page - 1) * per_page
            query = f'''
                SELECT 
                    id, email, role, status, profile, created_at, 
                    updated_at, last_login, login_count
                FROM users 
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            '''
            
            result = execute_query(query, tuple(params + [per_page, offset]))
            
            if result['success']:
                users = []
                for user in result['data']:
                    user_dict = dict(user)
                    # Convert UUID to string
                    user_dict['id'] = str(user_dict['id'])
                    # Handle datetime fields
                    for field in ['created_at', 'updated_at', 'last_login']:
                        if user_dict.get(field):
                            user_dict[field] = user_dict[field].isoformat()
                        else:
                            user_dict[field] = None
                    # Ensure profile is not None
                    user_dict['profile'] = user_dict.get('profile') or {}
                    users.append(user_dict)
                
                total_pages = (total_count + per_page - 1) // per_page
                
                return jsonify({
                    'users': users,
                    'pagination': {
                        'page': page,
                        'per_page': per_page,
                        'total': total_count,
                        'pages': total_pages
                    },
                    'filters': {
                        'role': role_filter,
                        'status': status_filter,
                        'search': search_term
                    }
                })
            else:
                print(f"Database query failed: {result}")
                return jsonify({'error': 'Failed to fetch users from database', 'details': result.get('error')}), 500
        else:
            # Database not available
            return jsonify({'error': 'Database not available'}), 503

    except Exception as e:
        print(f"Error in get_all_users: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to get users: {str(e)}'}), 500

@admin_bp.route('/users/<user_id>', methods=['GET'])
@token_required
@role_required('admin')
def get_user_details(user_id):
    """Get detailed information about a specific user"""
    try:
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get user from database with left joins to avoid requiring related data
            result = execute_query('''
                SELECT u.id, u.email, u.role, u.status, u.profile, 
                       u.created_at, u.updated_at, u.last_login, u.login_count
                FROM users u
                WHERE u.id = %s
            ''', (user_id,), 'one')
            
            if result['success'] and result['data']:
                user = dict(result['data'])
                
                # Convert UUID to string
                user['id'] = str(user['id'])
                
                # Format dates
                for field in ['created_at', 'updated_at', 'last_login']:
                    if user.get(field):
                        user[field] = user[field].isoformat()
                    else:
                        user[field] = None
                
                # Ensure profile is not None
                user['profile'] = user.get('profile') or {}
                
                # Try to get additional user data (customers/resellers tables)
                try:
                    # Get customer data if exists
                    customer_result = execute_query('''
                        SELECT personal_info, contact_info, customer_type, status
                        FROM customers 
                        WHERE user_id = %s
                    ''', (user_id,), 'one')
                    
                    if customer_result['success'] and customer_result['data']:
                        user['customer_profile'] = dict(customer_result['data'])
                    
                    # Get reseller data if exists
                    reseller_result = execute_query('''
                        SELECT business_name, license_number, license_state, business_type, tier, status
                        FROM resellers 
                        WHERE user_id = %s
                    ''', (user_id,), 'one')
                    
                    if reseller_result['success'] and reseller_result['data']:
                        user['reseller_profile'] = dict(reseller_result['data'])
                
                except Exception as profile_error:
                    print(f"Error getting additional profile data: {profile_error}")
                    # Continue without additional profile data
                
                return jsonify(user)
            else:
                return jsonify({'error': 'User not found'}), 404
        else:
            return jsonify({'error': 'Database not available'}), 503

    except Exception as e:
        print(f"Error in get_user_details: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to get user details: {str(e)}'}), 500

@admin_bp.route('/users/<user_id>/status', methods=['PUT'])
@token_required
@role_required('admin')
def update_user_status(user_id):
    """Update user status (activate/deactivate/suspend)"""
    try:
        data = request.get_json()
        new_status = data.get('status')
        reason = data.get('reason', '')
        
        if new_status not in ['active', 'inactive', 'suspended']:
            return jsonify({'error': 'Invalid status. Must be: active, inactive, or suspended'}), 400
        
        admin_id = request.current_user.get('user_id')
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Update in database
            result = db_manager.update_record(
                'users',
                {
                    'status': new_status,
                    'updated_at': datetime.now(timezone.utc)
                },
                'id = %s',
                (user_id,)
            )
            
            if result['success'] and result.get('updated_rows', 0) > 0:
                # Log admin action
                SecurityUtils.log_security_event(admin_id, 'user_status_changed', {
                    'target_user': user_id,
                    'new_status': new_status,
                    'reason': reason
                })
                
                return jsonify({
                    'message': f'User status updated to {new_status}',
                    'user_id': user_id,
                    'new_status': new_status,
                    'updated_by': admin_id,
                    'reason': reason
                })
            else:
                return jsonify({'error': 'User not found or update failed'}), 404
        else:
            return jsonify({'error': 'Database not available'}), 503

    except Exception as e:
        print(f"Error in update_user_status: {e}")
        return jsonify({'error': f'Failed to update user status: {str(e)}'}), 500

@admin_bp.route('/users/<user_id>/role', methods=['PUT'])
@token_required
@role_required('admin')
def update_user_role(user_id):
    """Update user role"""
    try:
        data = request.get_json()
        new_role = data.get('role')
        
        valid_roles = ['customer', 'wholesale_reseller', 'admin']
        if new_role not in valid_roles:
            return jsonify({'error': f'Invalid role. Must be one of: {", ".join(valid_roles)}'}), 400
        
        admin_id = request.current_user.get('user_id')
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Update role in database
            result = db_manager.update_record(
                'users',
                {
                    'role': new_role,
                    'updated_at': datetime.now(timezone.utc)
                },
                'id = %s',
                (user_id,)
            )
            
            if result['success'] and result.get('updated_rows', 0) > 0:
                # Log admin action
                SecurityUtils.log_security_event(admin_id, 'user_role_changed', {
                    'target_user': user_id,
                    'new_role': new_role
                })
                
                return jsonify({
                    'message': f'User role updated to {new_role}',
                    'user_id': user_id,
                    'new_role': new_role,
                    'updated_by': admin_id
                })
            else:
                return jsonify({'error': 'User not found or update failed'}), 404
        else:
            return jsonify({'error': 'Database not available'}), 503

    except Exception as e:
        print(f"Error in update_user_role: {e}")
        return jsonify({'error': f'Failed to update user role: {str(e)}'}), 500

@admin_bp.route('/users', methods=['POST'])
@token_required
@role_required('admin')
def create_user():
    """Create new user (admin only)"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['email', 'password', 'role']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({'error': f"Missing fields: {', '.join(missing_fields)}"}), 400
        
        email = data.get('email').lower().strip()
        password = data.get('password')
        role = data.get('role')
        
        # Validate role
        valid_roles = ['customer', 'wholesale_reseller', 'admin']
        if role not in valid_roles:
            return jsonify({'error': f'Invalid role. Must be one of: {", ".join(valid_roles)}'}), 400
        
        db_manager = get_db_manager()
        admin_id = request.current_user.get('user_id')
        
        if db_manager.available:
            # Check if user already exists
            existing_user = execute_query(
                'SELECT id FROM users WHERE email = %s',
                (email,),
                'one'
            )
            
            if existing_user['success'] and existing_user['data']:
                return jsonify({'error': 'User already exists with this email'}), 409
            
            # Create new user
            user_data = {
                'id': str(uuid.uuid4()),
                'email': email,
                'password_hash': UserAuth.hash_password(password),
                'role': role,
                'status': 'active',
                'profile': data.get('profile', {}),
                'login_count': 0,
                'created_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc)
            }
            
            result = db_manager.insert_record('users', user_data)
            
            if result['success']:
                # Log admin action
                SecurityUtils.log_security_event(admin_id, 'user_created', {
                    'new_user_id': user_data['id'],
                    'new_user_email': email,
                    'new_user_role': role
                })
                
                return jsonify({
                    'message': 'User created successfully',
                    'user': {
                        'id': user_data['id'],
                        'email': email,
                        'role': role,
                        'status': 'active',
                        'created_by': admin_id
                    }
                }), 201
            else:
                return jsonify({'error': f'Failed to create user: {result.get("error")}'}), 500
        else:
            return jsonify({'error': 'Database not available for user creation'}), 503

    except Exception as e:
        print(f"Error in create_user: {e}")
        return jsonify({'error': f'Failed to create user: {str(e)}'}), 500

@admin_bp.route('/users/<user_id>', methods=['DELETE'])
@token_required
@role_required('admin')
def delete_user(user_id):
    """Delete user (soft delete by setting status to deleted)"""
    try:
        admin_id = request.current_user.get('user_id')
        
        # Prevent self-deletion
        if user_id == admin_id:
            return jsonify({'error': 'Cannot delete your own account'}), 400
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get user info before deletion
            user_result = execute_query(
                'SELECT email, role FROM users WHERE id = %s',
                (user_id,),
                'one'
            )
            
            if not user_result['success'] or not user_result['data']:
                return jsonify({'error': 'User not found'}), 404
            
            user_info = user_result['data']
            
            # Soft delete (set status to deleted)
            result = db_manager.update_record(
                'users',
                {
                    'status': 'deleted',
                    'updated_at': datetime.now(timezone.utc)
                },
                'id = %s',
                (user_id,)
            )
            
            if result['success']:
                # Log admin action
                SecurityUtils.log_security_event(admin_id, 'user_deleted', {
                    'deleted_user_id': user_id,
                    'deleted_user_email': user_info['email'],
                    'deleted_user_role': user_info['role']
                })
                
                return jsonify({
                    'message': f'User {user_info["email"]} deleted successfully',
                    'deleted_user_id': user_id,
                    'deleted_by': admin_id
                })
            else:
                return jsonify({'error': 'Failed to delete user'}), 500
        else:
            return jsonify({'error': 'Database not available for user deletion'}), 503

    except Exception as e:
        print(f"Error in delete_user: {e}")
        return jsonify({'error': f'Failed to delete user: {str(e)}'}), 500

@admin_bp.route('/system-info')
@token_required
@role_required('admin')
def get_system_info():
    """Get comprehensive system information"""
    try:
        service_checker = ServiceChecker()
        system_info = service_checker.get_system_info()
        
        # Add database info
        db_manager = get_db_manager()
        if db_manager.available:
            db_test = db_manager.test_connection()
            system_info['database'] = db_test
        else:
            system_info['database'] = {'status': 'not_available'}
        
        # Add service status
        system_info['services'] = {
            'hero_service': service_checker.check_hero_service(),
            'vsc_service': service_checker.check_vsc_service(),
            'vin_service': service_checker.check_vin_service(),
            'payment_service': service_checker.check_payment_service()
        }
        
        return jsonify(system_info)
        
    except Exception as e:
        print(f"Error in get_system_info: {e}")
        return jsonify({'error': f'Failed to get system info: {str(e)}'}), 500

# ================================
# MISSING ENDPOINTS FROM index.py
# ================================

@admin_bp.route('/system-settings', methods=['GET'])
@token_required
@role_required('admin')
def get_system_settings_for_products():
    """Get current system settings for product management"""
    try:
        # Import settings functions
        try:
            from services.database_settings_service import (
                get_admin_fee, get_wholesale_discount, get_tax_rate,
                get_processing_fee, get_dealer_fee, settings_service
            )
            settings_service_available = True
        except ImportError:
            settings_service_available = False
            
        if settings_service_available:
            # Get all relevant settings for product management
            settings = {
                'fees': {
                    'admin_fee': get_admin_fee('hero'),
                    'vsc_admin_fee': get_admin_fee('vsc'),
                    'processing_fee': get_processing_fee(),
                    'dealer_fee': get_dealer_fee()
                },
                'discounts': {
                    'wholesale_discount_rate': get_wholesale_discount()
                },
                'taxes': {
                    'default_tax_rate': get_tax_rate(),
                    'fl_tax_rate': get_tax_rate('FL'),
                    'ca_tax_rate': get_tax_rate('CA'),
                    'ny_tax_rate': get_tax_rate('NY'),
                    'tx_tax_rate': get_tax_rate('TX')
                },
                'hero_settings': {}
            }

            # Get Hero-specific settings if available
            if hasattr(settings_service, 'get_admin_setting'):
                settings['hero_settings'] = {
                    'coverage_multiplier_1000': settings_service.get_admin_setting('hero', 'coverage_multiplier_1000', 1.2),
                    'coverage_multiplier_500': settings_service.get_admin_setting('hero', 'coverage_multiplier_500', 1.0),
                    'default_coverage_limit': settings_service.get_admin_setting('hero', 'default_coverage_limit', 500)
                }
        else:
            # Fallback settings
            settings = {
                'fees': {
                    'admin_fee': 25.00,
                    'vsc_admin_fee': 50.00,
                    'processing_fee': 15.00,
                    'dealer_fee': 50.00
                },
                'discounts': {
                    'wholesale_discount_rate': 0.15
                },
                'taxes': {
                    'default_tax_rate': 0.08,
                    'fl_tax_rate': 0.07,
                    'ca_tax_rate': 0.0875,
                    'ny_tax_rate': 0.08,
                    'tx_tax_rate': 0.0625
                },
                'hero_settings': {
                    'coverage_multiplier_1000': 1.2,
                    'coverage_multiplier_500': 1.0,
                    'default_coverage_limit': 500
                }
            }

        return jsonify(success_response({
            'settings': settings,
            'database_driven': settings_service_available,
            'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
        }))

    except Exception as e:
        print(f"Get system settings error: {e}")
        return jsonify({'error': f'Failed to get system settings: {str(e)}'}), 500

@admin_bp.route('/products', methods=['GET'])
@token_required
@role_required('admin')
def get_admin_products():
    """Get all products with database-driven pricing info"""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Get products with pricing information
        cursor.execute('''
            SELECT
                p.id,
                p.product_code,
                p.product_name,
                p.base_price,
                p.active,
                p.created_at,
                COUNT(pr.id) as pricing_count,
                MIN(p.base_price * pr.multiplier) as min_price,
                MAX(p.base_price * pr.multiplier) as max_price,
                ARRAY_AGG(DISTINCT pr.term_years ORDER BY pr.term_years) as terms_available
            FROM products p
            LEFT JOIN pricing pr ON p.product_code = pr.product_code
            GROUP BY p.id, p.product_code, p.product_name, p.base_price, p.active, p.created_at
            ORDER BY p.product_name;
        ''')

        products = []
        for row in cursor.fetchall():
            id, product_code, product_name, base_price, active, created_at, pricing_count, min_price, max_price, terms = row

            products.append({
                'id': id,
                'product_code': product_code,
                'product_name': product_name,
                'base_price': float(base_price) if base_price else 0,
                'min_price': float(min_price) if min_price else 0,
                'max_price': float(max_price) if max_price else 0,
                'active': active,
                'created_at': created_at.isoformat() if created_at else None,
                'pricing_count': pricing_count,
                'terms_available': [t for t in (terms or []) if t is not None]
            })

        # Get current system settings for frontend
        try:
            from services.database_settings_service import (
                get_admin_fee, get_wholesale_discount, get_tax_rate,
                get_processing_fee, settings_service
            )
            system_settings = {
                'hero_admin_fee': get_admin_fee('hero'),
                'wholesale_discount_rate': get_wholesale_discount(),
                'default_tax_rate': get_tax_rate(),
                'fl_tax_rate': get_tax_rate('FL'),
                'ca_tax_rate': get_tax_rate('CA'),
                'ny_tax_rate': get_tax_rate('NY'),
                'processing_fee': get_processing_fee(),
                'database_driven': True
            }
        except ImportError:
            system_settings = {
                'hero_admin_fee': 25.00,
                'wholesale_discount_rate': 0.15,
                'default_tax_rate': 0.08,
                'fl_tax_rate': 0.07,
                'ca_tax_rate': 0.0875,
                'ny_tax_rate': 0.08,
                'processing_fee': 15.00,
                'database_driven': False
            }

        cursor.close()
        conn.close()

        return jsonify(success_response({
            'products': products,
            'system_settings': system_settings,
            'total_products': len(products)
        }))

    except Exception as e:
        print(f"Get products error: {e}")
        return jsonify({'error': f'Failed to get products: {str(e)}'}), 500

@admin_bp.route('/products', methods=['POST'])
@token_required
@role_required('admin')
def create_product():
    """Create new product in database (admin only)"""
    try:
        data = request.get_json()
        import psycopg2

        # Validate required fields
        required_fields = ['product_code', 'product_name', 'base_price']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({'error': f"Missing fields: {', '.join(missing_fields)}"}), 400

        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Check if product already exists
        cursor.execute('SELECT id FROM products WHERE product_code = %s;', (data['product_code'],))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'error': 'Product already exists'}), 409

        # Insert new product
        cursor.execute('''
            INSERT INTO products (product_code, product_name, base_price, active)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
        ''', (
            data['product_code'],
            data['product_name'],
            data['base_price'],
            data.get('active', True)
        ))

        product_id = cursor.fetchone()[0]

        # Insert default pricing if provided
        if 'pricing' in data:
            for term_years, multiplier in data['pricing'].items():
                term = int(term_years)

                # Insert retail pricing
                cursor.execute('''
                    INSERT INTO pricing (product_code, term_years, multiplier, customer_type)
                    VALUES (%s, %s, %s, %s);
                ''', (data['product_code'], term, multiplier, 'retail'))

                # Insert wholesale pricing (15% discount)
                wholesale_multiplier = multiplier * 0.85
                cursor.execute('''
                    INSERT INTO pricing (product_code, term_years, multiplier, customer_type)
                    VALUES (%s, %s, %s, %s);
                ''', (data['product_code'], term, wholesale_multiplier, 'wholesale'))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': 'Product created successfully',
            'product': {
                'id': product_id,
                **data
            }
        })), 201

    except Exception as e:
        print(f"Create product error: {e}")
        return jsonify({'error': f"Failed to create product: {str(e)}"}), 500

@admin_bp.route('/products/<product_code>', methods=['PUT'])
@token_required
@role_required('admin')
def update_product_by_code(product_code):
    """Update existing product by product code"""
    try:
        data = request.get_json()
        import psycopg2
        
        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Check if product exists
        cursor.execute('SELECT id, base_price FROM products WHERE product_code = %s;', (product_code,))
        product_result = cursor.fetchone()
        if not product_result:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Product not found'}), 404

        product_id, current_base_price = product_result

        # Update base price if provided
        new_base_price = data.get('base_price', current_base_price)
        if new_base_price != current_base_price:
            cursor.execute('''
                UPDATE products
                SET base_price = %s, updated_at = CURRENT_TIMESTAMP
                WHERE product_code = %s;
            ''', (new_base_price, product_code))

        # Update other product fields
        update_fields = []
        params = []
        
        allowed_fields = ['product_name', 'active']
        for field in allowed_fields:
            if field in data:
                update_fields.append(f"{field} = %s")
                params.append(data[field])

        if update_fields:
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            params.append(product_code)
            query = f"UPDATE products SET {', '.join(update_fields)} WHERE product_code = %s;"
            cursor.execute(query, params)

        # Update pricing multipliers if provided
        if 'pricing' in data:
            for term_years, customer_prices in data['pricing'].items():
                term = int(term_years)

                for customer_type, multiplier in customer_prices.items():
                    cursor.execute('''
                        INSERT INTO pricing (product_code, term_years, multiplier, customer_type)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (product_code, term_years, customer_type)
                        DO UPDATE SET
                            multiplier = EXCLUDED.multiplier,
                            updated_at = CURRENT_TIMESTAMP;
                    ''', (product_code, term, float(multiplier), customer_type))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': 'Product updated successfully',
            'product_code': product_code,
            'base_price': float(new_base_price),
            'updated_fields': list(data.keys())
        }))

    except Exception as e:
        print(f"Update product error: {e}")
        if 'conn' in locals():
            conn.rollback()
        return jsonify({'error': f"Failed to update product: {str(e)}"}), 500

@admin_bp.route('/products/<product_code>', methods=['DELETE'])
@token_required
@role_required('admin')
def delete_product_by_code(product_code):
    """Delete product and its pricing by product code"""
    try:
        import psycopg2
        
        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Check if product exists
        cursor.execute('SELECT product_name FROM products WHERE product_code = %s;', (product_code,))
        product = cursor.fetchone()
        if not product:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Product not found'}), 404

        product_name = product[0]

        # Delete pricing first (foreign key constraint)
        cursor.execute('DELETE FROM pricing WHERE product_code = %s;', (product_code,))

        # Delete product
        cursor.execute('DELETE FROM products WHERE product_code = %s;', (product_code,))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': f'Product "{product_name}" and its pricing deleted successfully'
        }))

    except Exception as e:
        print(f"Delete product error: {e}")
        return jsonify({'error': f"Failed to delete product: {str(e)}"}), 500

@admin_bp.route('/products/<product_code>/pricing', methods=['GET'])
@token_required
@role_required('admin')
def get_admin_product_pricing(product_code):
    """Get detailed pricing for a specific product with current system settings"""
    try:
        import psycopg2
        
        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Get product base info
        cursor.execute('''
            SELECT product_name, base_price, active
            FROM products
            WHERE product_code = %s;
        ''', (product_code,))

        product_result = cursor.fetchone()
        if not product_result:
            cursor.close()
            conn.close()
            return jsonify({'error': "Product not found"}), 404

        product_name, base_price, active = product_result

        # Get pricing data
        cursor.execute('''
            SELECT term_years, multiplier, customer_type
            FROM pricing
            WHERE product_code = %s
            ORDER BY term_years, customer_type;
        ''', (product_code,))

        pricing_data = {}
        for term_years, multiplier, customer_type in cursor.fetchall():
            if term_years not in pricing_data:
                pricing_data[term_years] = {}
            pricing_data[term_years][customer_type] = {
                'multiplier': float(multiplier),
                'price': float(base_price * multiplier)
            }

        # Get current system settings
        try:
            from services.database_settings_service import (
                get_admin_fee, get_wholesale_discount, get_tax_rate,
                get_processing_fee
            )
            system_settings = {
                'admin_fee': get_admin_fee('hero'),
                'wholesale_discount_rate': get_wholesale_discount(),
                'tax_rate': get_tax_rate(),
                'processing_fee': get_processing_fee(),
                'database_driven': True
            }
        except ImportError:
            system_settings = {
                'admin_fee': 25.00,
                'wholesale_discount_rate': 0.15,
                'tax_rate': 0.08,
                'processing_fee': 15.00,
                'database_driven': False
            }

        cursor.close()
        conn.close()

        return jsonify(success_response({
            'product_code': product_code,
            'product_name': product_name,
            'base_price': float(base_price),
            'active': active,
            'pricing': pricing_data,
            'system_settings': system_settings
        }))

    except Exception as e:
        print(f"Get pricing error: {e}")
        return jsonify({'error': f"Failed to get pricing: {str(e)}"}), 500

@admin_bp.route('/settings', methods=['GET'])
@token_required
@role_required('admin')
def get_admin_settings():
    """Get admin configurable settings from database"""
    try:
        import psycopg2
        
        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT category, key, value
            FROM admin_settings
            ORDER BY category, key;
        ''')

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # Organize settings by category
        settings = {}
        for category, key, value in rows:
            if category not in settings:
                settings[category] = {}

            # Parse JSON values properly
            if value:
                try:
                    import json
                    parsed_value = json.loads(value) if isinstance(value, str) else value
                    settings[category][key] = parsed_value
                except (json.JSONDecodeError, TypeError):
                    # If not valid JSON, handle as string/number
                    if isinstance(value, str):
                        try:
                            # Try to parse as number first
                            if '.' in value:
                                settings[category][key] = float(value)
                            else:
                                settings[category][key] = int(value)
                        except ValueError:
                            # If not a number, keep as string (remove quotes if present)
                            settings[category][key] = value.strip('"')
                    else:
                        settings[category][key] = value
            else:
                settings[category][key] = ''

        return jsonify(success_response(settings))

    except Exception as e:
        import traceback
        print(f"Get settings error: {e}")
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({'error': f"Failed to get settings: {str(e)}"}), 500

@admin_bp.route('/settings', methods=['PUT'])
@token_required
@role_required('admin')
def update_admin_settings():
    """Update admin settings in database"""
    try:
        data = request.get_json()
        import psycopg2
        import json

        # Add validation for the incoming data
        if not data or not isinstance(data, dict):
            return jsonify({'error': "Invalid data format"}), 400

        print(f"Received data: {data}")  # Debug logging

        # Get user ID with proper validation
        user_id = request.current_user.get('user_id')

        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Validate user_id exists in database
        if user_id:
            cursor.execute("SELECT id FROM users WHERE id = %s;", (user_id,))
            if not cursor.fetchone():
                user_id = None
                print(f"Invalid user_id from token, setting to NULL")

        # If user_id is still invalid, get a valid admin user
        if not user_id:
            cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1;")
            result = cursor.fetchone()
            if result:
                user_id = result[0]
                print(f"Using fallback admin user: {user_id}")
            else:
                print("No admin user found, proceeding with NULL")

        # Update each setting category
        for category, settings in data.items():
            print(f"Processing category: {category}, settings: {settings}, type: {type(settings)}")

            # Validate that settings is a dictionary
            if not isinstance(settings, dict):
                print(f"Warning: Expected dict for category '{category}', got {type(settings)}. Skipping.")
                continue

            for key, value in settings.items():
                print(f"Processing: {category}.{key} = {value}")

                # Convert value to proper JSON format
                json_value = json.dumps(value)

                cursor.execute('''
                    INSERT INTO admin_settings (category, key, value, updated_by)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (category, key)
                    DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = CURRENT_TIMESTAMP,
                        updated_by = EXCLUDED.updated_by;
                ''', (category, key, json_value, user_id))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': 'Settings updated successfully',
            'updated_settings': data,
            'updated_by': user_id
        }))

    except Exception as e:
        import traceback
        print(f"Settings update error: {e}")
        print(f"Full traceback: {traceback.format_exc()}")
        if 'conn' in locals():
            conn.rollback()
            print("🔄 Changes rolled back")
        return jsonify({'error': f"Failed to update settings: {str(e)}"}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

# Helper functions
def success_response(data):
    """Create success response format"""
    return {
        'success': True,
        'data': data
    }

def error_response(message):
    """Create error response format"""
    return {
        'success': False,
        'error': message
    }

@admin_bp.route('/security/events', methods=['GET'])
@token_required
@role_required('admin')
def get_security_events():
    """Get security events and audit log"""
    try:
        # In production, this would fetch from security_events table
        # For now, return placeholder data
        
        security_events = [
            {
                'id': str(uuid.uuid4()),
                'event_type': 'user_login',
                'user_id': 'user-123',
                'timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
                'details': {'ip_address': '192.168.1.100', 'user_agent': 'Mozilla/5.0...'},
                'severity': 'info'
            },
            {
                'id': str(uuid.uuid4()),
                'event_type': 'failed_login',
                'user_id': None,
                'timestamp': (datetime.now(timezone.utc)).isoformat() + 'Z',
                'details': {'ip_address': '192.168.1.200', 'email': 'attacker@example.com'},
                'severity': 'warning'
            }
        ]
        
        return jsonify({
            'security_events': security_events,
            'total_events': len(security_events),
            'last_updated': datetime.now(timezone.utc).isoformat() + 'Z'
        })
        
    except Exception as e:
        print(f"Error in get_security_events: {e}")
        return jsonify({'error': f'Failed to get security events: {str(e)}'}), 500

@admin_bp.route('/maintenance', methods=['POST'])
@token_required
@role_required('admin')
def trigger_maintenance():
    """Trigger maintenance tasks"""
    try:
        data = request.get_json()
        task = data.get('task')
        admin_id = request.current_user.get('user_id')
        
        valid_tasks = ['clear_cache', 'cleanup_logs', 'backup_database', 'refresh_settings']
        
        if task not in valid_tasks:
            return jsonify({'error': f'Invalid task. Must be one of: {", ".join(valid_tasks)}'}), 400
        
        maintenance_result = {'task': task, 'status': 'completed', 'details': {}}
        
        if task == 'clear_cache':
            # Clear application cache
            try:
                from services.database_settings_service import settings_service
                if hasattr(settings_service, 'clear_cache'):
                    settings_service.clear_cache()
                maintenance_result['details']['cache_cleared'] = True
            except:
                maintenance_result['details']['cache_cleared'] = False
        
        elif task == 'cleanup_logs':
            # Clean up old log entries
            db_manager = get_db_manager()
            if db_manager.available:
                try:
                    cleanup_result = db_manager.cleanup_old_records('security_events', 'created_at', 90)
                    maintenance_result['details'] = cleanup_result
                except:
                    maintenance_result['details']['message'] = 'Cleanup method not available'
            else:
                maintenance_result['details']['message'] = 'Database not available for cleanup'
        
        elif task == 'backup_database':
            # Create database backup
            maintenance_result['details']['message'] = 'Backup functionality would be implemented here'
        
        elif task == 'refresh_settings':
            # Refresh system settings
            try:
                from services.database_settings_service import settings_service
                if hasattr(settings_service, 'clear_cache'):
                    settings_service.clear_cache()
                maintenance_result['details']['settings_refreshed'] = True
            except:
                maintenance_result['details']['settings_refreshed'] = False
        
        # Log maintenance action
        SecurityUtils.log_security_event(admin_id, 'maintenance_task', {
            'task': task,
            'result': maintenance_result
        })
        
        return jsonify(maintenance_result)
        
    except Exception as e:
        print(f"Error in trigger_maintenance: {e}")
        return jsonify({'error': f'Maintenance task failed: {str(e)}'}), 500


@admin_bp.route('/pricing/<product_code>', methods=['PUT'])
@token_required
@role_required('admin')
def update_product_pricing(product_code):
    """Update product pricing with database-driven calculations"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': "Pricing data is required"}), 400

        import psycopg2
        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Verify product exists
        cursor.execute("SELECT id, base_price FROM products WHERE product_code = %s;", (product_code,))
        product_result = cursor.fetchone()
        
        if not product_result:
            cursor.close()
            conn.close()
            return jsonify({'error': "Product not found"}), 404

        product_id, current_base_price = product_result

        # Update base price if provided
        new_base_price = data.get('base_price', current_base_price)
        if float(new_base_price) != float(current_base_price):
            cursor.execute('''
                UPDATE products 
                SET base_price = %s, updated_at = CURRENT_TIMESTAMP 
                WHERE product_code = %s;
            ''', (new_base_price, product_code))

        # Update other product fields if provided
        update_fields = []
        params = []
        
        allowed_fields = ['product_name', 'active', 'description']
        for field in allowed_fields:
            if field in data:
                update_fields.append(f"{field} = %s")
                params.append(data[field])

        if update_fields:
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            params.append(product_code)
            query = f"UPDATE products SET {', '.join(update_fields)} WHERE product_code = %s;"
            cursor.execute(query, params)

        # Update pricing multipliers if provided
        if 'pricing' in data:
            for term_years, customer_prices in data['pricing'].items():
                term = int(term_years)

                for customer_type, multiplier in customer_prices.items():
                    cursor.execute('''
                        INSERT INTO pricing (product_code, term_years, multiplier, customer_type, updated_at)
                        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (product_code, term_years, customer_type)
                        DO UPDATE SET
                            multiplier = EXCLUDED.multiplier,
                            updated_at = CURRENT_TIMESTAMP;
                    ''', (product_code, term, float(multiplier), customer_type))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': 'Product pricing updated successfully',
            'product_code': product_code,
            'base_price': float(new_base_price),
            'updated_at': datetime.now(timezone.utc).isoformat() + 'Z'
        }))

    except Exception as e:
        print(f"Update pricing error: {e}")
        if 'conn' in locals():
            conn.rollback()
            cursor.close()
            conn.close()
        return jsonify({'error': f"Failed to update pricing: {str(e)}"}), 500


# Add these VSC admin endpoints to your admin_endpoints.py file

# ================================
# VSC ADMIN ENDPOINTS
# ================================

@admin_bp.route('/vsc/coverage-levels', methods=['GET'])
@token_required
@role_required('admin')
def get_admin_coverage_levels():
    """Get all coverage levels for admin management"""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute('''
            SELECT id, level_code, level_name, description, display_order,
                   active, created_at, updated_at
            FROM vsc_coverage_levels
            ORDER BY display_order, level_code;
        ''')

        coverage_levels = cursor.fetchall()

        # Convert to proper format
        levels_list = []
        for level in coverage_levels:
            level_dict = dict(level)
            level_dict['created_at'] = level_dict['created_at'].isoformat() if level_dict['created_at'] else None
            level_dict['updated_at'] = level_dict['updated_at'].isoformat() if level_dict['updated_at'] else None
            levels_list.append(level_dict)

        cursor.close()
        conn.close()

        return jsonify(success_response({
            'coverage_levels': levels_list,
            'total': len(levels_list)
        }))

    except Exception as e:
        print(f"Get coverage levels error: {e}")
        return jsonify({'error': f"Failed to get coverage levels: {str(e)}"}), 500

@admin_bp.route('/vsc/vehicle-classes', methods=['GET'])
@token_required
@role_required('admin')
def get_admin_vehicle_classes():
    """Get all vehicle classifications for admin management"""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute('''
            SELECT id, make, vehicle_class, active, created_at, updated_at
            FROM vsc_vehicle_classes
            ORDER BY vehicle_class, make;
        ''')

        classifications = cursor.fetchall()

        # Convert to proper format
        classifications_list = []
        for classification in classifications:
            class_dict = dict(classification)
            class_dict['created_at'] = class_dict['created_at'].isoformat() if class_dict['created_at'] else None
            class_dict['updated_at'] = class_dict['updated_at'].isoformat() if class_dict['updated_at'] else None
            classifications_list.append(class_dict)

        cursor.close()
        conn.close()

        return jsonify(success_response({
            'vehicle_classifications': classifications_list,
            'total': len(classifications_list)
        }))

    except Exception as e:
        print(f"Get vehicle classes error: {e}")
        return jsonify({'error': f"Failed to get vehicle classes: {str(e)}"}), 500

@admin_bp.route('/vsc/base-rates', methods=['GET'])
@token_required
@role_required('admin')
def get_admin_base_rates():
    """Get all base rates for admin management"""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute('''
            SELECT id, vehicle_class, coverage_level, base_rate,
                   effective_date, active, created_at, updated_at
            FROM vsc_base_rates
            ORDER BY vehicle_class, coverage_level;
        ''')

        base_rates = cursor.fetchall()

        # Convert to proper format
        rates_list = []
        for rate in base_rates:
            rate_dict = dict(rate)
            rate_dict['base_rate'] = float(rate_dict['base_rate'])
            rate_dict['effective_date'] = rate_dict['effective_date'].isoformat() if rate_dict['effective_date'] else None
            rate_dict['created_at'] = rate_dict['created_at'].isoformat() if rate_dict['created_at'] else None
            rate_dict['updated_at'] = rate_dict['updated_at'].isoformat() if rate_dict['updated_at'] else None
            rates_list.append(rate_dict)

        cursor.close()
        conn.close()

        return jsonify(success_response({
            'base_rates': rates_list,
            'total': len(rates_list)
        }))

    except Exception as e:
        print(f"Get base rates error: {e}")
        return jsonify({'error': f"Failed to get base rates: {str(e)}"}), 500

@admin_bp.route('/vsc/base-rates/<int:rate_id>', methods=['PUT'])
@token_required
@role_required('admin')
def update_base_rate(rate_id):
    """Update an existing base rate"""
    try:
        data = request.get_json()
        import psycopg2

        # Validate required fields
        if not data:
            return jsonify({'error': "No data provided for update"}), 400

        allowed_fields = ['vehicle_class', 'coverage_level', 'base_rate', 'effective_date', 'active']
        update_fields = {k: v for k, v in data.items() if k in allowed_fields}
        
        if not update_fields:
            return jsonify({'error': f"No valid fields to update. Allowed fields: {', '.join(allowed_fields)}"}), 400

        # Validate base_rate is numeric if provided
        if 'base_rate' in update_fields:
            try:
                update_fields['base_rate'] = float(update_fields['base_rate'])
            except (ValueError, TypeError):
                return jsonify({'error': 'base_rate must be a numeric value'}), 400

        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # First check if base rate exists
        cursor.execute('''
            SELECT id, vehicle_class, coverage_level 
            FROM vsc_base_rates 
            WHERE id = %s;
        ''', (rate_id,))
        
        existing_rate = cursor.fetchone()
        if not existing_rate:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Base rate not found'}), 404

        # Check if we're changing vehicle_class or coverage_level to values that would create a duplicate
        if ('vehicle_class' in update_fields or 'coverage_level' in update_fields):
            new_vehicle_class = update_fields.get('vehicle_class', existing_rate[1])
            new_coverage_level = update_fields.get('coverage_level', existing_rate[2])
            
            cursor.execute('''
                SELECT id 
                FROM vsc_base_rates 
                WHERE vehicle_class = %s 
                  AND coverage_level = %s 
                  AND id != %s;
            ''', (new_vehicle_class, new_coverage_level, rate_id))
            
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return jsonify({'error': 'A base rate already exists for this vehicle class and coverage level combination'}), 409

        # Build the update query
        set_clauses = []
        params = []
        
        for field, value in update_fields.items():
            set_clauses.append(f"{field} = %s")
            params.append(value)
        
        params.append(rate_id)
        
        query = f'''
            UPDATE vsc_base_rates
            SET {', '.join(set_clauses)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, vehicle_class, coverage_level, base_rate,
                      effective_date, active, created_at, updated_at;
        '''
        
        cursor.execute(query, params)
        updated_rate = cursor.fetchone()
        
        if not updated_rate:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'error': 'Failed to update base rate'}), 500
            
        conn.commit()
        
        # Convert to dictionary format
        rate_data = {
            'id': updated_rate[0],
            'vehicle_class': updated_rate[1],
            'coverage_level': updated_rate[2],
            'base_rate': float(updated_rate[3]),
            'effective_date': updated_rate[4].isoformat() if updated_rate[4] else None,
            'active': updated_rate[5],
            'created_at': updated_rate[6].isoformat() if updated_rate[6] else None,
            'updated_at': updated_rate[7].isoformat() if updated_rate[7] else None
        }
        
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': 'Base rate updated successfully',
            'base_rate': rate_data,
            'updated_fields': list(update_fields.keys())
        }))

    except Exception as e:
        print(f"Update base rate error: {e}")
        if 'conn' in locals():
            conn.rollback()
        return jsonify({'error': f"Failed to update base rate: {str(e)}"}), 500

@admin_bp.route('/vsc/rates', methods=['GET'])
@token_required
@role_required('admin')
def get_all_vsc_rates():
    """Get all VSC rates for admin management"""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)
        vehicle_class = request.args.get('vehicle_class')
        coverage_level = request.args.get('coverage_level')

        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Build WHERE clause
        where_conditions = ['active = TRUE']
        params = []

        if vehicle_class:
            where_conditions.append('vehicle_class = %s')
            params.append(vehicle_class)

        if coverage_level:
            where_conditions.append('coverage_level = %s')
            params.append(coverage_level)

        where_clause = ' AND '.join(where_conditions)

        # Get total count
        cursor.execute(f'''
            SELECT COUNT(*)
            FROM vsc_rate_matrix
            WHERE {where_clause};
        ''', params)
        total_count = cursor.fetchone()['count']

        # Get paginated results
        offset = (page - 1) * per_page
        cursor.execute(f'''
            SELECT id, vehicle_class, coverage_level, term_months,
                   mileage_range_key, min_mileage, max_mileage, rate_amount,
                   effective_date, created_at, updated_at
            FROM vsc_rate_matrix
            WHERE {where_clause}
            ORDER BY vehicle_class, coverage_level, term_months, min_mileage
            LIMIT %s OFFSET %s;
        ''', params + [per_page, offset])

        rates = cursor.fetchall()

        # Convert to proper format
        rates_list = []
        for rate in rates:
            rate_dict = dict(rate)
            rate_dict['rate_amount'] = float(rate_dict['rate_amount'])
            rate_dict['effective_date'] = rate_dict['effective_date'].isoformat() if rate_dict['effective_date'] else None
            rate_dict['created_at'] = rate_dict['created_at'].isoformat() if rate_dict['created_at'] else None
            rate_dict['updated_at'] = rate_dict['updated_at'].isoformat() if rate_dict['updated_at'] else None
            rates_list.append(rate_dict)

        cursor.close()
        conn.close()

        return jsonify(success_response({
            'rates': rates_list,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_count,
                'pages': (total_count + per_page - 1) // per_page
            },
            'filters': {
                'vehicle_class': vehicle_class,
                'coverage_level': coverage_level
            }
        }))

    except Exception as e:
        print(f"Get VSC rates error: {e}")
        return jsonify({'error': f"Failed to get VSC rates: {str(e)}"}), 500
    

@admin_bp.route('/vsc/multipliers/<multiplier_type>', methods=['GET'])
@token_required
@role_required('admin')
def get_admin_multipliers(multiplier_type):
    """Get multipliers for admin management"""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        valid_types = ['term', 'deductible', 'mileage', 'age']
        if multiplier_type not in valid_types:
            return jsonify({'error': f"Invalid multiplier type. Must be one of: {', '.join(valid_types)}"}), 400

        table_name = f"vsc_{multiplier_type}_multipliers"

        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute(f'''
            SELECT * FROM {table_name}
            ORDER BY display_order, id;
        ''')

        multipliers = cursor.fetchall()

        # Convert to proper format
        multipliers_list = []
        for multiplier in multipliers:
            mult_dict = dict(multiplier)
            mult_dict['multiplier'] = float(mult_dict['multiplier'])
            mult_dict['created_at'] = mult_dict['created_at'].isoformat() if mult_dict.get('created_at') else None
            mult_dict['updated_at'] = mult_dict['updated_at'].isoformat() if mult_dict.get('updated_at') else None
            multipliers_list.append(mult_dict)

        cursor.close()
        conn.close()

        return jsonify(success_response({
            'multiplier_type': multiplier_type,
            'multipliers': multipliers_list,
            'total': len(multipliers_list)
        }))

    except Exception as e:
        print(f"Get {multiplier_type} multipliers error: {e}")
        return jsonify({'error': f"Failed to get {multiplier_type} multipliers: {str(e)}"}), 500

@admin_bp.route('/vsc/analytics/rates-summary', methods=['GET'])
@token_required
@role_required('admin')
def get_vsc_rates_analytics():
    """Get VSC rates analytics summary"""
    try:
        import psycopg2
        
        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Get overall statistics
        cursor.execute('''
            SELECT
                COUNT(*) as total_rates,
                COUNT(DISTINCT vehicle_class) as vehicle_classes,
                COUNT(DISTINCT coverage_level) as coverage_levels,
                COUNT(DISTINCT term_months) as term_options,
                MIN(rate_amount) as min_rate,
                MAX(rate_amount) as max_rate,
                AVG(rate_amount) as avg_rate
            FROM vsc_rate_matrix
            WHERE active = TRUE;
        ''')

        summary = cursor.fetchone()

        # Get rates by vehicle class
        cursor.execute('''
            SELECT vehicle_class,
                   COUNT(*) as rate_count,
                   MIN(rate_amount) as min_rate,
                   MAX(rate_amount) as max_rate,
                   AVG(rate_amount) as avg_rate
            FROM vsc_rate_matrix
            WHERE active = TRUE
            GROUP BY vehicle_class
            ORDER BY vehicle_class;
        ''')

        class_breakdown = cursor.fetchall()

        # Get rates by coverage level
        cursor.execute('''
            SELECT coverage_level,
                   COUNT(*) as rate_count,
                   MIN(rate_amount) as min_rate,
                   MAX(rate_amount) as max_rate,
                   AVG(rate_amount) as avg_rate
            FROM vsc_rate_matrix
            WHERE active = TRUE
            GROUP BY coverage_level
            ORDER BY coverage_level;
        ''')

        coverage_breakdown = cursor.fetchall()

        cursor.close()
        conn.close()

        analytics_data = {
            'summary': {
                'total_rates': summary[0],
                'vehicle_classes': summary[1],
                'coverage_levels': summary[2],
                'term_options': summary[3],
                'rate_range': {
                    'min': float(summary[4]) if summary[4] else 0,
                    'max': float(summary[5]) if summary[5] else 0,
                    'average': round(float(summary[6]), 2) if summary[6] else 0
                }
            },
            'by_vehicle_class': [
                {
                    'class': row[0],
                    'rate_count': row[1],
                    'min_rate': float(row[2]),
                    'max_rate': float(row[3]),
                    'avg_rate': round(float(row[4]), 2)
                } for row in class_breakdown
            ],
            'by_coverage_level': [
                {
                    'level': row[0],
                    'rate_count': row[1],
                    'min_rate': float(row[2]),
                    'max_rate': float(row[3]),
                    'avg_rate': round(float(row[4]), 2)
                } for row in coverage_breakdown
            ]
        }

        return jsonify(success_response(analytics_data))

    except Exception as e:
        print(f"Get VSC analytics error: {e}")
        return jsonify({'error': f"Failed to get VSC analytics: {str(e)}"}), 500

# Additional VSC management endpoints

@admin_bp.route('/vsc/coverage-levels', methods=['POST'])
@token_required
@role_required('admin')
def create_coverage_level():
    """Create new coverage level"""
    try:
        data = request.get_json()
        import psycopg2

        required_fields = ['level_code', 'level_name', 'description']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({'error': f"Missing fields: {', '.join(missing_fields)}"}), 400

        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Check for duplicate
        cursor.execute('''
            SELECT id FROM vsc_coverage_levels WHERE level_code = %s;
        ''', (data['level_code'],))

        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'error': 'Coverage level code already exists'}), 409

        # Insert new coverage level
        cursor.execute('''
            INSERT INTO vsc_coverage_levels
            (level_code, level_name, description, display_order, active)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, created_at;
        ''', (
            data['level_code'], data['level_name'], data['description'],
            data.get('display_order', 999), data.get('active', True)
        ))

        level_id, created_at = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': 'Coverage level created successfully',
            'coverage_level': {
                'id': level_id,
                'created_at': created_at.isoformat(),
                **data
            }
        })), 201

    except Exception as e:
        print(f"Create coverage level error: {e}")
        return jsonify({'error': f"Failed to create coverage level: {str(e)}"}), 500

@admin_bp.route('/vsc/coverage-levels/<int:level_id>', methods=['PUT'])
@token_required
@role_required('admin')
def update_coverage_level(level_id):
    """Update an existing coverage level"""
    try:
        data = request.get_json()
        import psycopg2

        # Validate required fields
        if not data:
            return jsonify({'error': "No data provided for update"}), 400

        allowed_fields = ['level_code', 'level_name', 'description', 'display_order', 'active']
        update_fields = {k: v for k, v in data.items() if k in allowed_fields}
        
        if not update_fields:
            return jsonify({'error': f"No valid fields to update. Allowed fields: {', '.join(allowed_fields)}"}), 400

        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # First check if coverage level exists
        cursor.execute('''
            SELECT id, level_code FROM vsc_coverage_levels WHERE id = %s;
        ''', (level_id,))
        
        existing_level = cursor.fetchone()
        if not existing_level:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Coverage level not found'}), 404

        # Check if level_code is being updated to a value that already exists
        if 'level_code' in update_fields and update_fields['level_code'] != existing_level[1]:
            cursor.execute('''
                SELECT id FROM vsc_coverage_levels WHERE level_code = %s AND id != %s;
            ''', (update_fields['level_code'], level_id))
            
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return jsonify({'error': 'Another coverage level already uses this level code'}), 409

        # Build the update query
        set_clauses = []
        params = []
        
        for field, value in update_fields.items():
            set_clauses.append(f"{field} = %s")
            params.append(value)
        
        params.append(level_id)
        
        query = f'''
            UPDATE vsc_coverage_levels
            SET {', '.join(set_clauses)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, level_code, level_name, description, 
                      display_order, active, created_at, updated_at;
        '''
        
        cursor.execute(query, params)
        updated_level = cursor.fetchone()
        
        if not updated_level:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'error': 'Failed to update coverage level'}), 500
            
        conn.commit()
        
        # Convert to dictionary format
        level_data = {
            'id': updated_level[0],
            'level_code': updated_level[1],
            'level_name': updated_level[2],
            'description': updated_level[3],
            'display_order': updated_level[4],
            'active': updated_level[5],
            'created_at': updated_level[6].isoformat() if updated_level[6] else None,
            'updated_at': updated_level[7].isoformat() if updated_level[7] else None
        }
        
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': 'Coverage level updated successfully',
            'coverage_level': level_data,
            'updated_fields': list(update_fields.keys())
        }))

    except Exception as e:
        print(f"Update coverage level error: {e}")
        if 'conn' in locals():
            conn.rollback()
        return jsonify({'error': f"Failed to update coverage level: {str(e)}"}), 500

@admin_bp.route('/vsc/vehicle-classes', methods=['POST'])
@token_required
@role_required('admin')
def create_vehicle_classification():
    """Create new vehicle classification"""
    try:
        data = request.get_json()
        import psycopg2

        required_fields = ['make', 'vehicle_class']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({'error': f"Missing fields: {', '.join(missing_fields)}"}), 400

        if data['vehicle_class'] not in ['A', 'B', 'C']:
            return jsonify({'error': 'vehicle_class must be A, B, or C'}), 400

        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Check for duplicate
        cursor.execute('''
            SELECT id FROM vsc_vehicle_classes WHERE make = %s;
        ''', (data['make'],))

        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'error': 'Vehicle make already classified'}), 409

        # Insert new classification
        cursor.execute('''
            INSERT INTO vsc_vehicle_classes (make, vehicle_class, active)
            VALUES (%s, %s, %s)
            RETURNING id, created_at;
        ''', (data['make'], data['vehicle_class'], data.get('active', True)))

        class_id, created_at = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': 'Vehicle classification created successfully',
            'classification': {
                'id': class_id,
                'created_at': created_at.isoformat(),
                **data
            }
        })), 201

    except Exception as e:
        print(f"Create vehicle classification error: {e}")
        return jsonify({'error': f"Failed to create classification: {str(e)}"}), 500 


@admin_bp.route('/vsc/rates/<int:rate_id>', methods=['PUT'])
@token_required
@role_required('admin')
def update_vsc_rate(rate_id):
    """Update an existing VSC rate in the rate matrix"""
    try:
        data = request.get_json()
        import psycopg2

        # Validate required fields
        if not data:
            return jsonify({'error': "No data provided for update"}), 400

        allowed_fields = [
            'vehicle_class', 
            'coverage_level', 
            'term_months', 
            'mileage_range_key',
            'min_mileage',
            'max_mileage',
            'rate_amount',
            'effective_date',
            'active'
        ]
        
        update_fields = {k: v for k, v in data.items() if k in allowed_fields}
        
        if not update_fields:
            return jsonify({'error': f"No valid fields to update. Allowed fields: {', '.join(allowed_fields)}"}), 400

        # Validate numeric fields
        numeric_fields = ['term_months', 'min_mileage', 'max_mileage', 'rate_amount']
        for field in numeric_fields:
            if field in update_fields:
                try:
                    update_fields[field] = float(update_fields[field])
                except (ValueError, TypeError):
                    return jsonify({'error': f'{field} must be a numeric value'}), 400

        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # First check if rate exists
        cursor.execute('''
            SELECT id, vehicle_class, coverage_level, term_months, mileage_range_key
            FROM vsc_rate_matrix 
            WHERE id = %s;
        ''', (rate_id,))
        
        existing_rate = cursor.fetchone()
        if not existing_rate:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Rate not found'}), 404

        # Check if we're changing fields that would create a duplicate rate
        if any(field in update_fields for field in ['vehicle_class', 'coverage_level', 'term_months', 'mileage_range_key']):
            new_vehicle_class = update_fields.get('vehicle_class', existing_rate[1])
            new_coverage_level = update_fields.get('coverage_level', existing_rate[2])
            new_term_months = update_fields.get('term_months', existing_rate[3])
            new_mileage_range_key = update_fields.get('mileage_range_key', existing_rate[4])
            
            cursor.execute('''
                SELECT id 
                FROM vsc_rate_matrix 
                WHERE vehicle_class = %s 
                  AND coverage_level = %s 
                  AND term_months = %s
                  AND mileage_range_key = %s
                  AND id != %s;
            ''', (new_vehicle_class, new_coverage_level, new_term_months, new_mileage_range_key, rate_id))
            
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return jsonify({
                    'error': 'A rate already exists for this vehicle class, coverage level, term, and mileage combination'
                }), 409

        # Validate mileage range if updating min/max
        if 'min_mileage' in update_fields or 'max_mileage' in update_fields:
            min_mileage = update_fields.get('min_mileage', existing_rate[5] if len(existing_rate) > 5 else None)
            max_mileage = update_fields.get('max_mileage', existing_rate[6] if len(existing_rate) > 6 else None)
            
            if min_mileage is not None and max_mileage is not None and min_mileage >= max_mileage:
                cursor.close()
                conn.close()
                return jsonify({'error': 'min_mileage must be less than max_mileage'}), 400

        # Build the update query
        set_clauses = []
        params = []
        
        for field, value in update_fields.items():
            set_clauses.append(f"{field} = %s")
            params.append(value)
        
        params.append(rate_id)
        
        query = f'''
            UPDATE vsc_rate_matrix
            SET {', '.join(set_clauses)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, vehicle_class, coverage_level, term_months,
                      mileage_range_key, min_mileage, max_mileage, rate_amount,
                      effective_date, active, created_at, updated_at;
        '''
        
        cursor.execute(query, params)
        updated_rate = cursor.fetchone()
        
        if not updated_rate:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'error': 'Failed to update rate'}), 500
            
        conn.commit()
        
        # Convert to dictionary format
        rate_data = {
            'id': updated_rate[0],
            'vehicle_class': updated_rate[1],
            'coverage_level': updated_rate[2],
            'term_months': int(updated_rate[3]),
            'mileage_range_key': updated_rate[4],
            'min_mileage': int(updated_rate[5]) if updated_rate[5] is not None else None,
            'max_mileage': int(updated_rate[6]) if updated_rate[6] is not None else None,
            'rate_amount': float(updated_rate[7]),
            'effective_date': updated_rate[8].isoformat() if updated_rate[8] else None,
            'active': updated_rate[9],
            'created_at': updated_rate[10].isoformat() if updated_rate[10] else None,
            'updated_at': updated_rate[11].isoformat() if updated_rate[11] else None
        }
        
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': 'VSC rate updated successfully',
            'rate': rate_data,
            'updated_fields': list(update_fields.keys())
        }))

    except Exception as e:
        print(f"Update VSC rate error: {e}")
        if 'conn' in locals():
            conn.rollback()
        return jsonify({'error': f"Failed to update VSC rate: {str(e)}"}), 500
    
@admin_bp.route('/vsc/multipliers/term/<int:multiplier_id>', methods=['PUT'])
@token_required
@role_required('admin')
def update_term_multiplier(multiplier_id):
    """Update an existing term multiplier"""
    try:
        data = request.get_json()
        import psycopg2

        # Validate required fields
        if not data:
            return jsonify({'error': "No data provided for update"}), 400

        allowed_fields = ['term_months', 'multiplier', 'description', 'display_order', 'active']
        update_fields = {k: v for k, v in data.items() if k in allowed_fields}
        
        if not update_fields:
            return jsonify({'error': f"No valid fields to update. Allowed fields: {', '.join(allowed_fields)}"}), 400

        # Validate numeric fields
        if 'term_months' in update_fields:
            try:
                update_fields['term_months'] = int(update_fields['term_months'])
            except (ValueError, TypeError):
                return jsonify({'error': 'term_months must be an integer value'}), 400

        if 'multiplier' in update_fields:
            try:
                update_fields['multiplier'] = float(update_fields['multiplier'])
            except (ValueError, TypeError):
                return jsonify({'error': 'multiplier must be a numeric value'}), 400

        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # First check if multiplier exists
        cursor.execute('''
            SELECT id, term_months 
            FROM vsc_term_multipliers 
            WHERE id = %s;
        ''', (multiplier_id,))
        
        existing_multiplier = cursor.fetchone()
        if not existing_multiplier:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Term multiplier not found'}), 404

        # Check if we're changing term_months to a value that already exists
        if 'term_months' in update_fields and update_fields['term_months'] != existing_multiplier[1]:
            cursor.execute('''
                SELECT id 
                FROM vsc_term_multipliers 
                WHERE term_months = %s 
                  AND id != %s;
            ''', (update_fields['term_months'], multiplier_id))
            
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return jsonify({'error': 'A multiplier already exists for this term length'}), 409

        # Build the update query
        set_clauses = []
        params = []
        
        for field, value in update_fields.items():
            set_clauses.append(f"{field} = %s")
            params.append(value)
        
        params.append(multiplier_id)
        
        query = f'''
            UPDATE vsc_term_multipliers
            SET {', '.join(set_clauses)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, term_months, multiplier, description,
                      display_order, active, created_at, updated_at;
        '''
        
        cursor.execute(query, params)
        updated_multiplier = cursor.fetchone()
        
        if not updated_multiplier:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'error': 'Failed to update term multiplier'}), 500
            
        conn.commit()
        
        # Convert to dictionary format
        multiplier_data = {
            'id': updated_multiplier[0],
            'term_months': int(updated_multiplier[1]),
            'multiplier': float(updated_multiplier[2]),
            'description': updated_multiplier[3],
            'display_order': updated_multiplier[4],
            'active': updated_multiplier[5],
            'created_at': updated_multiplier[6].isoformat() if updated_multiplier[6] else None,
            'updated_at': updated_multiplier[7].isoformat() if updated_multiplier[7] else None
        }
        
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': 'Term multiplier updated successfully',
            'multiplier': multiplier_data,
            'updated_fields': list(update_fields.keys())
        }))

    except Exception as e:
        print(f"Update term multiplier error: {e}")
        if 'conn' in locals():
            conn.rollback()
        return jsonify({'error': f"Failed to update term multiplier: {str(e)}"}), 500
    
@admin_bp.route('/vsc/vehicle-classes/<int:class_id>', methods=['PUT'])
@token_required
@role_required('admin')
def update_vehicle_class(class_id):
    """Update an existing vehicle classification"""
    try:
        data = request.get_json()
        import psycopg2

        # Validate required fields
        if not data:
            return jsonify({'error': "No data provided for update"}), 400

        allowed_fields = ['make', 'vehicle_class', 'active']
        update_fields = {k: v for k, v in data.items() if k in allowed_fields}
        
        if not update_fields:
            return jsonify({'error': f"No valid fields to update. Allowed fields: {', '.join(allowed_fields)}"}), 400

        # Validate vehicle_class is A, B, or C if provided
        if 'vehicle_class' in update_fields and update_fields['vehicle_class'] not in ['A', 'B', 'C']:
            return jsonify({'error': 'vehicle_class must be A, B, or C'}), 400

        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            return jsonify({'error': 'Database not configured'}), 500
            
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # First check if vehicle class exists
        cursor.execute('''
            SELECT id, make, vehicle_class 
            FROM vsc_vehicle_classes 
            WHERE id = %s;
        ''', (class_id,))
        
        existing_class = cursor.fetchone()
        if not existing_class:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Vehicle classification not found'}), 404

        # Check if we're changing make to a value that already exists
        if 'make' in update_fields and update_fields['make'].lower() != existing_class[1].lower():
            cursor.execute('''
                SELECT id 
                FROM vsc_vehicle_classes 
                WHERE LOWER(make) = LOWER(%s) 
                  AND id != %s;
            ''', (update_fields['make'], class_id))
            
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return jsonify({'error': 'A classification already exists for this vehicle make'}), 409

        # Build the update query
        set_clauses = []
        params = []
        
        for field, value in update_fields.items():
            set_clauses.append(f"{field} = %s")
            params.append(value)
        
        params.append(class_id)
        
        query = f'''
            UPDATE vsc_vehicle_classes
            SET {', '.join(set_clauses)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, make, vehicle_class, active, created_at, updated_at;
        '''
        
        cursor.execute(query, params)
        updated_class = cursor.fetchone()
        
        if not updated_class:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'error': 'Failed to update vehicle classification'}), 500
            
        conn.commit()
        
        # Convert to dictionary format
        class_data = {
            'id': updated_class[0],
            'make': updated_class[1],
            'vehicle_class': updated_class[2],
            'active': updated_class[3],
            'created_at': updated_class[4].isoformat() if updated_class[4] else None,
            'updated_at': updated_class[5].isoformat() if updated_class[5] else None
        }
        
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': 'Vehicle classification updated successfully',
            'vehicle_class': class_data,
            'updated_fields': list(update_fields.keys())
        }))

    except Exception as e:
        print(f"Update vehicle classification error: {e}")
        if 'conn' in locals():
            conn.rollback()
        return jsonify({'error': f"Failed to update vehicle classification: {str(e)}"}), 500


@admin_bp.route('/resellers/<reseller_id>/commissions/calculate', methods=['POST'])
@token_required
@role_required('admin')
def calculate_reseller_commission(reseller_id):
    """Calculate commission for a specific period"""
    try:
        data = request.get_json()
        period_start = datetime.fromisoformat(data['period_start'].replace('Z', '+00:00'))
        period_end = datetime.fromisoformat(data['period_end'].replace('Z', '+00:00'))
        
        # Get all sales for the period
        sales_result = execute_query('''
            SELECT id, gross_amount, commission_amount, commission_status
            FROM reseller_sales
            WHERE reseller_id = %s 
            AND sale_date >= %s 
            AND sale_date <= %s
            ORDER BY sale_date
        ''', (reseller_id, period_start.date(), period_end.date()), 'all')
        
        if not sales_result['success']:
            return jsonify('Failed to fetch sales data'), 500
        
        sales_data = sales_result['data'] or []
        total_sales = sum(sale[1] for sale in sales_data)
        total_commission = sum(sale[2] for sale in sales_data)
        
        # Create or update commission record
        commission_result = execute_query('''
            INSERT INTO reseller_commissions (
                reseller_id, period_start, period_end, total_sales_amount,
                total_commission_amount, status, commission_details
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (reseller_id, period_start, period_end) 
            DO UPDATE SET
                total_sales_amount = EXCLUDED.total_sales_amount,
                total_commission_amount = EXCLUDED.total_commission_amount,
                commission_details = EXCLUDED.commission_details,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        ''', (
            reseller_id, period_start.date(), period_end.date(),
            total_sales, total_commission, 'ready',
            json.dumps([{
                'sale_id': str(sale[0]),
                'gross_amount': float(sale[1]),
                'commission_amount': float(sale[2]),
                'status': sale[3]
            } for sale in sales_data])
        ), 'one')
        
        return jsonify({
            'success': True,
            'total_sales': float(total_sales),
            'total_commission': float(total_commission),
            'sales_count': len(sales_data),
            'commission_id': str(commission_result['data'][0]) if commission_result['success'] else None
        })
        
    except Exception as e:
        return jsonify(f'Failed to calculate commission: {str(e)}'), 500


@admin_bp.route('/resellers/<reseller_id>/commissions/<commission_id>/pay', methods=['POST'])
@token_required
@role_required('admin')
def mark_commission_paid(reseller_id, commission_id):
    """Mark commission as paid"""
    try:
        data = request.get_json()
        payment_method = data.get('payment_method', {})
        
        # Update commission record
        update_result = execute_query('''
            UPDATE reseller_commissions
            SET status = 'paid', paid_at = CURRENT_TIMESTAMP, payment_method = %s
            WHERE id = %s AND reseller_id = %s
            RETURNING total_commission_amount
        ''', (json.dumps(payment_method), commission_id, reseller_id), 'one')
        
        if not update_result['success']:
            return jsonify('Commission record not found'), 404
        
        commission_amount = update_result['data'][0]
        
        # Update individual sales records
        execute_query('''
            UPDATE reseller_sales
            SET commission_status = 'paid', payment_date = CURRENT_DATE
            WHERE reseller_id = %s 
            AND sale_date >= (SELECT period_start FROM reseller_commissions WHERE id = %s)
            AND sale_date <= (SELECT period_end FROM reseller_commissions WHERE id = %s)
            AND commission_status = 'pending'
        ''', (reseller_id, commission_id, commission_id), 'none')
        
        return jsonify({
            'success': True,
            'commission_amount': float(commission_amount),
            'message': 'Commission marked as paid'
        })
        
    except Exception as e:
        return jsonify(f'Failed to mark commission as paid: {str(e)}'), 500
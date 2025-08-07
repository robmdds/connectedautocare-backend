"""
Admin Management Endpoints
User management, system settings, and administrative functions
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
import uuid
from utils.database import get_db_manager, execute_query
from utils.service_availability import ServiceChecker

# Initialize blueprint
admin_bp = Blueprint('admin', __name__)

# Import admin services with error handling
try:
    from auth.user_auth import token_required, role_required, SecurityUtils
    from models.database_models import UserModel
    admin_services_available = True
    
    # Initialize models (in production, these would be persistent)
    user_model = UserModel()
    users_db = {}
    sessions_db = {}
    
except ImportError as e:
    print(f"Warning: Admin services not available: {e}")
    admin_services_available = False
    
    # Create fallback classes
    class UserAuth:
        @staticmethod
        def hash_password(password):
            return "dummy_hash"
    
    class SecurityUtils:
        @staticmethod
        def log_security_event(user_id, event, data):
            pass
    
    class UserModel:
        def create_user(self, data):
            return data
    
    class DatabaseUtils:
        @staticmethod
        def get_customer_metrics(customer_id, transactions, policies):
            return {}
    
    user_model = UserModel()
    users_db = {}
    sessions_db = {}

@admin_bp.route('/health')
@token_required
@role_required('admin')
def admin_health():
    """Admin panel health check"""
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

@admin_bp.route('/users', methods=['GET'])
@token_required
@role_required('admin')
def get_all_users():
    """Get all users with filtering and pagination"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        role_filter = request.args.get('role')
        status_filter = request.args.get('status')
        search_term = request.args.get('search', '')
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Build query with filters
            where_conditions = []
            params = []
            
            if role_filter:
                where_conditions.append("role = %s")
                params.append(role_filter)
            
            if status_filter:
                where_conditions.append("status = %s")
                params.append(status_filter)
            
            if search_term:
                where_conditions.append("(LOWER(email) LIKE LOWER(%s) OR LOWER(profile->>'first_name') LIKE LOWER(%s) OR LOWER(profile->>'last_name') LIKE LOWER(%s))")
                search_pattern = f'%{search_term}%'
                params.extend([search_pattern, search_pattern, search_pattern])
            
            where_clause = ' AND '.join(where_conditions) if where_conditions else 'TRUE'
            
            # Get total count
            count_result = execute_query(f"SELECT COUNT(*) FROM users WHERE {where_clause}", tuple(params), 'one')
            total_count = count_result['data'][0] if count_result['success'] else 0
            
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
                    user_dict['created_at'] = user_dict['created_at'].isoformat() if user_dict['created_at'] else None
                    user_dict['updated_at'] = user_dict['updated_at'].isoformat() if user_dict['updated_at'] else None
                    user_dict['last_login'] = user_dict['last_login'].isoformat() if user_dict['last_login'] else None
                    users.append(user_dict)
                
                return jsonify({
                    'users': users,
                    'pagination': {
                        'page': page,
                        'per_page': per_page,
                        'total': total_count,
                        'pages': (total_count + per_page - 1) // per_page
                    },
                    'filters': {
                        'role': role_filter,
                        'status': status_filter,
                        'search': search_term
                    }
                })
            else:
                return jsonify('Failed to fetch users from database'), 500
        else:
            # Fallback to in-memory users
            users_list = []
            for user in users_db.values():
                user_data = {
                    'id': user.get('id'),
                    'email': user.get('email'),
                    'role': user.get('role'),
                    'status': user.get('status'),
                    'created_at': user.get('created_at'),
                    'last_login': user.get('last_login'),
                    'login_count': user.get('login_count', 0)
                }
                users_list.append(user_data)
            
            return jsonify({
                'users': users_list,
                'total': len(users_list),
                'source': 'in_memory'
            })

    except Exception as e:
        return jsonify(f'Failed to get users: {str(e)}'), 500

@admin_bp.route('/users/<user_id>', methods=['GET'])
@token_required
@role_required('admin')
def get_user_details(user_id):
    """Get detailed information about a specific user"""
    try:
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get user from database
            result = execute_query('''
                SELECT u.*, 
                       c.first_name as customer_first_name,
                       c.last_name as customer_last_name,
                       c.phone as customer_phone,
                       COUNT(t.id) as transaction_count,
                       COALESCE(SUM(CASE WHEN t.status = 'completed' THEN t.amount ELSE 0 END), 0) as total_spent
                FROM users u
                LEFT JOIN customers c ON u.id = c.user_id
                LEFT JOIN transactions t ON c.customer_id = t.customer_id
                WHERE u.id = %s
                GROUP BY u.id, c.first_name, c.last_name, c.phone
            ''', (user_id,), 'one')
            
            if result['success'] and result['data']:
                user = dict(result['data'])
                
                # Format dates
                user['created_at'] = user['created_at'].isoformat() if user['created_at'] else None
                user['updated_at'] = user['updated_at'].isoformat() if user['updated_at'] else None
                user['last_login'] = user['last_login'].isoformat() if user['last_login'] else None
                
                # Get recent transactions
                transactions_result = execute_query('''
                    SELECT t.transaction_number, t.amount, t.status, t.created_at, t.type
                    FROM transactions t
                    JOIN customers c ON t.customer_id = c.customer_id
                    WHERE c.user_id = %s
                    ORDER BY t.created_at DESC
                    LIMIT 10
                ''', (user_id,))
                
                recent_transactions = []
                if transactions_result['success']:
                    for txn in transactions_result['data']:
                        txn_dict = dict(txn)
                        txn_dict['created_at'] = txn_dict['created_at'].isoformat() if txn_dict['created_at'] else None
                        txn_dict['amount'] = float(txn_dict['amount'])
                        recent_transactions.append(txn_dict)
                
                user['recent_transactions'] = recent_transactions
                user['total_spent'] = float(user['total_spent'])
                
                return jsonify(user)
            else:
                return jsonify('User not found'), 404
        else:
            # Fallback to in-memory
            user = users_db.get(user_id)
            if user:
                return jsonify(user)
            else:
                return jsonify('User not found'), 404

    except Exception as e:
        return jsonify(f'Failed to get user details: {str(e)}'), 500

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
            return jsonify('Invalid status. Must be: active, inactive, or suspended'), 400
        
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
            
            if result['success'] and result['updated_rows'] > 0:
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
                return jsonify('User not found or update failed'), 404
        else:
            # Fallback to in-memory
            if user_id in users_db:
                users_db[user_id]['status'] = new_status
                users_db[user_id]['updated_at'] = datetime.now(timezone.utc).isoformat()
                
                return jsonify({
                    'message': f'User status updated to {new_status}',
                    'user_id': user_id,
                    'new_status': new_status
                })
            else:
                return jsonify('User not found'), 404

    except Exception as e:
        return jsonify(f'Failed to update user status: {str(e)}'), 500

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
            return jsonify(f'Invalid role. Must be one of: {", ".join(valid_roles)}'), 400
        
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
            
            if result['success'] and result['updated_rows'] > 0:
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
                return jsonify('User not found or update failed'), 404
        else:
            # Fallback to in-memory
            if user_id in users_db:
                users_db[user_id]['role'] = new_role
                users_db[user_id]['updated_at'] = datetime.now(timezone.utc).isoformat()
                
                return jsonify({
                    'message': f'User role updated to {new_role}',
                    'user_id': user_id,
                    'new_role': new_role
                })
            else:
                return jsonify('User not found'), 404

    except Exception as e:
        return jsonify(f'Failed to update user role: {str(e)}'), 500

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
            return jsonify(f"Missing fields: {', '.join(missing_fields)}"), 400
        
        email = data.get('email').lower().strip()
        password = data.get('password')
        role = data.get('role')
        
        # Validate role
        valid_roles = ['customer', 'wholesale_reseller', 'admin']
        if role not in valid_roles:
            return jsonify(f'Invalid role. Must be one of: {", ".join(valid_roles)}'), 400
        
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
                return jsonify('User already exists with this email'), 409
            
            # Create new user
            user_data = {
                'email': email,
                'password_hash': UserAuth.hash_password(password),
                'role': role,
                'status': 'active',
                'profile': data.get('profile', {}),
                'created_at': datetime.now(timezone.utc)
            }
            
            result = db_manager.insert_record('users', user_data)
            
            if result['success']:
                # Log admin action
                SecurityUtils.log_security_event(admin_id, 'user_created', {
                    'new_user_id': result['inserted_id'],
                    'new_user_email': email,
                    'new_user_role': role
                })
                
                return jsonify({
                    'message': 'User created successfully',
                    'user': {
                        'id': result['inserted_id'],
                        'email': email,
                        'role': role,
                        'status': 'active',
                        'created_by': admin_id
                    }
                }), 201
            else:
                return jsonify(f'Failed to create user: {result.get("error")}'), 500
        else:
            return jsonify('Database not available for user creation'), 503

    except Exception as e:
        return jsonify(f'Failed to create user: {str(e)}'), 500

@admin_bp.route('/users/<user_id>', methods=['DELETE'])
@token_required
@role_required('admin')
def delete_user(user_id):
    """Delete user (soft delete by setting status to deleted)"""
    try:
        admin_id = request.current_user.get('user_id')
        
        # Prevent self-deletion
        if user_id == admin_id:
            return jsonify('Cannot delete your own account'), 400
        
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Get user info before deletion
            user_result = execute_query(
                'SELECT email, role FROM users WHERE id = %s',
                (user_id,),
                'one'
            )
            
            if not user_result['success'] or not user_result['data']:
                return jsonify('User not found'), 404
            
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
                return jsonify('Failed to delete user'), 500
        else:
            return jsonify('Database not available for user deletion'), 503

    except Exception as e:
        return jsonify(f'Failed to delete user: {str(e)}'), 500

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
        return jsonify(f'Failed to get system info: {str(e)}'), 500

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
        return jsonify(f'Failed to get security events: {str(e)}'), 500

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
            return jsonify(f'Invalid task. Must be one of: {", ".join(valid_tasks)}'), 400
        
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
                cleanup_result = db_manager.cleanup_old_records('security_events', 'created_at', 90)
                maintenance_result['details'] = cleanup_result
            else:
                maintenance_result['details']['message'] = 'Database not available for cleanup'
        
        elif task == 'backup_database':
            # Create database backup
            db_manager = get_db_manager()
            if db_manager.available:
                backup_result = db_manager.backup_table('users')
                maintenance_result['details'] = backup_result
            else:
                maintenance_result['details']['message'] = 'Database not available for backup'
        
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
        return jsonify(f'Maintenance task failed: {str(e)}'), 500
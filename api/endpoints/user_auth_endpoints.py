"""
User Authentication Endpoints
User registration, login, profile management - Updated with Database Integration
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
import uuid
from utils.database import get_db_manager, execute_query
from utils.response_helpers import success_response, error_response

# Initialize blueprint
user_auth_bp = Blueprint('user_auth', __name__)

# Import updated authentication system
try:
    from auth.user_auth import UserAuth, SessionManager, SecurityUtils
    user_management_available = True
except ImportError as e:
    print(f"Warning: User management not available: {e}")
    user_management_available = False
    
    # Create fallback classes (same as your existing code)
    class UserAuth:
        ROLES = ['admin', 'wholesale_reseller', 'customer']

        @staticmethod
        def hash_password(password):
            import bcrypt
            return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        @staticmethod
        def verify_password(password, hash):
            import bcrypt
            return bcrypt.checkpw(password.encode('utf-8'), hash.encode('utf-8'))

        @staticmethod
        def validate_email(email):
            import re
            pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            return re.match(pattern, email) is not None

        @staticmethod
        def validate_password(password):
            if len(password) < 8:
                return False, "Password must be at least 8 characters long"
            return True, "Valid"

        @staticmethod
        def generate_token(data):
            import jwt
            from flask import current_app
            payload = {
                'user_id': data['id'],
                'email': data['email'],
                'role': data['role'],
                'exp': datetime.utcnow() + datetime.timedelta(hours=24),
                'iat': datetime.utcnow()
            }
            return jwt.encode(payload, current_app.config.get('SECRET_KEY', 'default-secret'), algorithm='HS256')

    class SessionManager:
        @staticmethod
        def create_session(user_id, token):
            return {
                "user_id": user_id, 
                "token": token,
                "created_at": datetime.now(timezone.utc).isoformat()
            }

    class SecurityUtils:
        @staticmethod
        def log_security_event(user_id, event, data):
            log_entry = {
                'user_id': user_id,
                'event_type': event,
                'details': data,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'ip_address': request.remote_addr if request else 'unknown'
            }
            print(f"Security Event: {log_entry}")

# Token verification decorator
def token_required(f):
    """Decorator to require valid JWT token"""
    from functools import wraps
    import jwt
    from flask import current_app
    
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Check for token in Authorization header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]  # Bearer <token>
            except IndexError:
                return jsonify({'error': 'Invalid token format'}), 401
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            # Verify token
            payload = jwt.decode(token, current_app.config.get('SECRET_KEY', 'default-secret'), algorithms=['HS256'])
            request.current_user = payload
            return f(*args, **kwargs)
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
    
    return decorated

def role_required(required_role):
    """Decorator to require specific role or higher"""
    from functools import wraps
    
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(request, 'current_user'):
                return jsonify({'error': 'Authentication required'}), 401
            
            user_role = request.current_user.get('role')
            
            # Role hierarchy
            role_levels = {
                'customer': 10,
                'wholesale_reseller': 50,
                'admin': 100
            }
            
            user_level = role_levels.get(user_role, 0)
            required_level = role_levels.get(required_role, 0)
            
            if user_level < required_level:
                return jsonify({'error': 'Insufficient permissions'}), 403
            
            return f(*args, **kwargs)
        return decorated
    return decorator

@user_auth_bp.route('/register', methods=['POST'])
def register():
    """Register new user with database integration"""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['email', 'password', 'role']
        for field in required_fields:
            if not data.get(field):
                return jsonify(error_response(f'{field} is required')), 400

        email = data.get('email').lower().strip()
        password = data.get('password')
        role = data.get('role')

        # Validate email format
        if not UserAuth.validate_email(email):
            return jsonify(error_response('Invalid email format')), 400

        # Validate password strength
        valid_password, password_message = UserAuth.validate_password(password)
        if not valid_password:
            return jsonify(error_response(password_message)), 400

        # Validate role
        if role not in ['customer', 'wholesale_reseller']:  # Admin created separately
            return jsonify(error_response('Invalid role')), 400

        # Database operations
        db_manager = get_db_manager()
        
        if db_manager.available:
            # Check if user already exists
            existing_user = execute_query(
                'SELECT id FROM users WHERE email = %s',
                (email,),
                'one'
            )
            
            if existing_user['success'] and existing_user['data']:
                return jsonify(error_response('User already exists')), 409

            # Create new user in database
            user_id = str(uuid.uuid4())
            password_hash = UserAuth.hash_password(password)

            user_data = {
                'id': user_id,
                'email': email,
                'password_hash': password_hash,
                'role': role,
                'status': 'active',
                'profile': data.get('profile', {}),
                'created_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc)
            }

            user_result = db_manager.insert_record('users', user_data)
            
            if not user_result['success']:
                return jsonify(error_response('Failed to create user')), 500

            # Create role-specific profiles
            if role == 'wholesale_reseller':
                reseller_data = {
                    'id': str(uuid.uuid4()),
                    'user_id': user_id,
                    'business_name': data.get('business_name', ''),
                    'license_number': data.get('license_number', ''),
                    'license_state': data.get('license_state', ''),
                    'business_type': data.get('business_type', 'insurance_agency'),
                    'contact_info': {
                        'phone': data.get('phone', ''),
                        'email': email
                    },
                    'status': 'pending',
                    'created_at': datetime.now(timezone.utc),
                    'updated_at': datetime.now(timezone.utc)
                }
                db_manager.insert_record('resellers', reseller_data)

            elif role == 'customer':
                customer_data = {
                    'id': str(uuid.uuid4()),
                    'user_id': user_id,
                    'customer_type': 'individual',
                    'personal_info': {
                        'first_name': data.get('first_name', ''),
                        'last_name': data.get('last_name', '')
                    },
                    'contact_info': {
                        'email': email,
                        'phone': data.get('phone', '')
                    },
                    'status': 'active',
                    'created_at': datetime.now(timezone.utc),
                    'updated_at': datetime.now(timezone.utc)
                }
                db_manager.insert_record('customers', customer_data)

        else:
            return jsonify(error_response('Database not available')), 503

        # Generate token
        token = UserAuth.generate_token({
            'id': user_id,
            'email': email,
            'role': role
        })

        # Log security event
        SecurityUtils.log_security_event(user_id, 'user_registered', {'role': role})

        return jsonify(success_response({
            'message': 'User registered successfully',
            'user': {
                'id': user_id,
                'email': email,
                'role': role,
                'profile': data.get('profile', {})
            },
            'token': token
        })), 201

    except Exception as e:
        return jsonify(error_response(f'Registration failed: {str(e)}')), 500

@user_auth_bp.route('/login', methods=['POST'])
def login():
    """User login with database validation"""
    try:
        data = request.get_json()

        email = data.get('email', '').lower().strip()
        password = data.get('password', '')

        if not email or not password:
            return jsonify(error_response('Email and password are required')), 400

        # Database authentication
        db_manager = get_db_manager()
        
        if not db_manager.available:
            return jsonify(error_response('Database not available')), 503

        # Find user by email
        user_result = execute_query('''
            SELECT id, email, password_hash, role, status, profile, 
                   last_login, login_count
            FROM users 
            WHERE email = %s AND status = 'active'
        ''', (email,), 'one')

        if not user_result['success'] or not user_result['data']:
            SecurityUtils.log_security_event(None, 'login_failed', {
                'email': email, 
                'reason': 'user_not_found'
            })
            return jsonify(error_response('Invalid credentials')), 401

        user = user_result['data']

        # Verify password
        if not UserAuth.verify_password(password, user['password_hash']):
            SecurityUtils.log_security_event(user['id'], 'login_failed', {
                'reason': 'invalid_password'
            })
            return jsonify(error_response('Invalid credentials')), 401

        # Update login statistics
        db_manager.update_record(
            'users',
            {
                'last_login': datetime.now(timezone.utc),
                'login_count': user.get('login_count', 0) + 1,
                'updated_at': datetime.now(timezone.utc)
            },
            'id = %s',
            (user['id'],)
        )

        # Generate token
        token = UserAuth.generate_token({
            'id': str(user['id']),
            'email': user['email'],
            'role': user['role']
        })

        # Log successful login
        SecurityUtils.log_security_event(user['id'], 'login_success', {
            'role': user['role']
        })

        return jsonify(success_response({
            'message': 'Login successful',
            'user': {
                'id': str(user['id']),
                'email': user['email'],
                'role': user['role'],
                'profile': user.get('profile', {}),
                'last_login': user['last_login'].isoformat() if user['last_login'] else None
            },
            'token': token
        }))

    except Exception as e:
        return jsonify(error_response(f'Login failed: {str(e)}')), 500

@user_auth_bp.route('/logout', methods=['POST'])
@token_required
def logout():
    """User logout"""
    try:
        user_id = request.current_user.get('user_id')
        SecurityUtils.log_security_event(user_id, 'logout', {})
        return jsonify(success_response({'message': 'Logout successful'}))
    except Exception as e:
        return jsonify(error_response(f'Logout failed: {str(e)}')), 500

@user_auth_bp.route('/profile', methods=['GET'])
@token_required
def get_profile():
    """Get user profile from database"""
    try:
        user_id = request.current_user.get('user_id')
        
        # Get user with role-specific data
        user_result = execute_query('''
            SELECT u.id, u.email, u.role, u.status, u.profile, 
                   u.created_at, u.updated_at, u.last_login, u.login_count,
                   c.id as customer_id, c.customer_type, c.personal_info, c.contact_info as customer_contact,
                   r.id as reseller_id, r.business_name, r.license_number, r.tier, r.status as reseller_status
            FROM users u
            LEFT JOIN customers c ON u.id = c.user_id
            LEFT JOIN resellers r ON u.id = r.user_id
            WHERE u.id = %s
        ''', (user_id,), 'one')

        if not user_result['success'] or not user_result['data']:
            return jsonify(error_response('User not found')), 404

        user = user_result['data']
        
        profile_data = {
            'user': {
                'id': str(user['id']),
                'email': user['email'],
                'role': user['role'],
                'status': user['status'],
                'profile': user.get('profile', {}),
                'created_at': user['created_at'].isoformat() if user['created_at'] else None,
                'last_login': user['last_login'].isoformat() if user['last_login'] else None,
                'login_count': user.get('login_count', 0)
            }
        }

        # Add role-specific data
        if user.get('customer_id'):
            profile_data['customer_profile'] = {
                'id': str(user['customer_id']),
                'customer_type': user['customer_type'],
                'personal_info': user.get('personal_info', {}),
                'contact_info': user.get('customer_contact', {})
            }

        if user.get('reseller_id'):
            profile_data['reseller_profile'] = {
                'id': str(user['reseller_id']),
                'business_name': user['business_name'],
                'license_number': user['license_number'],
                'tier': user['tier'],
                'status': user['reseller_status']
            }

        return jsonify(success_response(profile_data))

    except Exception as e:
        return jsonify(error_response(f'Failed to get profile: {str(e)}')), 500

@user_auth_bp.route('/profile', methods=['PUT'])
@token_required
def update_profile():
    """Update user profile in database"""
    try:
        user_id = request.current_user.get('user_id')
        data = request.get_json()
        
        if not data:
            return jsonify(error_response('Profile data is required')), 400

        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify(error_response('Database not available')), 503

        # Update user profile
        if 'profile' in data:
            db_manager.update_record(
                'users',
                {
                    'profile': data['profile'],
                    'updated_at': datetime.now(timezone.utc)
                },
                'id = %s',
                (user_id,)
            )

        # Update role-specific profiles
        user_role = request.current_user.get('role')
        
        if user_role == 'customer' and 'customer_profile' in data:
            customer_data = data['customer_profile']
            db_manager.update_record(
                'customers',
                {
                    'personal_info': customer_data.get('personal_info', {}),
                    'contact_info': customer_data.get('contact_info', {}),
                    'updated_at': datetime.now(timezone.utc)
                },
                'user_id = %s',
                (user_id,)
            )

        elif user_role == 'wholesale_reseller' and 'reseller_profile' in data:
            reseller_data = data['reseller_profile']
            db_manager.update_record(
                'resellers',
                {
                    'business_name': reseller_data.get('business_name'),
                    'license_number': reseller_data.get('license_number'),
                    'license_state': reseller_data.get('license_state'),
                    'updated_at': datetime.now(timezone.utc)
                },
                'user_id = %s',
                (user_id,)
            )

        SecurityUtils.log_security_event(user_id, 'profile_updated', {
            'fields_updated': list(data.keys())
        })

        return jsonify(success_response({
            'message': 'Profile updated successfully',
            'updated_fields': list(data.keys())
        }))

    except Exception as e:
        return jsonify(error_response(f'Failed to update profile: {str(e)}')), 500

@user_auth_bp.route('/change-password', methods=['PUT'])
@token_required
def change_password():
    """Change user password in database"""
    try:
        user_id = request.current_user.get('user_id')
        data = request.get_json()
        
        if not data:
            return jsonify(error_response('Password data is required')), 400

        current_password = data.get('current_password')
        new_password = data.get('new_password')

        if not current_password or not new_password:
            return jsonify(error_response('Current and new password required')), 400

        # Get current password hash from database
        user_result = execute_query(
            'SELECT password_hash FROM users WHERE id = %s',
            (user_id,),
            'one'
        )

        if not user_result['success'] or not user_result['data']:
            return jsonify(error_response('User not found')), 404

        # Verify current password
        if not UserAuth.verify_password(current_password, user_result['data']['password_hash']):
            SecurityUtils.log_security_event(user_id, 'password_change_failed', {
                'reason': 'invalid_current_password'
            })
            return jsonify(error_response('Current password is incorrect')), 401

        # Validate new password
        valid_password, password_message = UserAuth.validate_password(new_password)
        if not valid_password:
            return jsonify(error_response(password_message)), 400

        # Update password in database
        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify(error_response('Database not available')), 503

        db_manager.update_record(
            'users',
            {
                'password_hash': UserAuth.hash_password(new_password),
                'updated_at': datetime.now(timezone.utc)
            },
            'id = %s',
            (user_id,)
        )

        SecurityUtils.log_security_event(user_id, 'password_changed', {})
        return jsonify(success_response({'message': 'Password changed successfully'}))

    except Exception as e:
        return jsonify(error_response(f'Failed to change password: {str(e)}')), 500

@user_auth_bp.route('/verify-token', methods=['POST'])
def verify_token():
    """Verify if a token is valid"""
    try:
        data = request.get_json()
        token = data.get('token') if data else None
        
        if not token:
            # Try to get token from Authorization header
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
            else:
                return jsonify(error_response('Token is required')), 400

        # Verify JWT token
        import jwt
        from flask import current_app
        
        try:
            payload = jwt.decode(token, current_app.config.get('SECRET_KEY', 'default-secret'), algorithms=['HS256'])
            
            # Check if user still exists and is active
            user_result = execute_query(
                'SELECT id, email, role, status FROM users WHERE id = %s AND status = %s',
                (payload['user_id'], 'active'),
                'one'
            )
            
            if user_result['success'] and user_result['data']:
                user = user_result['data']
                return jsonify(success_response({
                    'valid': True,
                    'user': {
                        'id': str(user['id']),
                        'email': user['email'],
                        'role': user['role']
                    }
                }))
            else:
                return jsonify(error_response('User not found or inactive')), 401
                
        except jwt.ExpiredSignatureError:
            return jsonify(error_response('Token has expired')), 401
        except jwt.InvalidTokenError:
            return jsonify(error_response('Invalid token')), 401

    except Exception as e:
        return jsonify(error_response(f'Token verification failed: {str(e)}')), 500

@user_auth_bp.route('/health')
def auth_health():
    """Authentication service health check"""
    try:
        db_manager = get_db_manager()
        
        return jsonify({
            'service': 'User Authentication API',
            'status': 'healthy',
            'database_connected': db_manager.available,
            'user_management_available': user_management_available,
            'features': [
                'User Registration/Login',
                'Profile Management',
                'Password Management', 
                'Token Authentication',
                'Database Integration'
            ]
        })
    except Exception as e:
        return jsonify({
            'service': 'User Authentication API',
            'status': 'degraded',
            'error': str(e)
        }), 500

# Keep the admin-only endpoints for backward compatibility
@user_auth_bp.route('/sessions', methods=['GET'])
@token_required
@role_required('admin')
def get_active_sessions():
    """Get active user sessions from database (admin only)"""
    try:
        # Get recently logged in users (last 24 hours)
        sessions_result = execute_query('''
            SELECT id, email, role, last_login, login_count
            FROM users 
            WHERE last_login > %s
            ORDER BY last_login DESC
        ''', (datetime.now(timezone.utc) - datetime.timedelta(hours=24),))

        active_sessions = []
        if sessions_result['success']:
            for user in sessions_result['data']:
                active_sessions.append({
                    'user_id': str(user['id']),
                    'email': user['email'],
                    'role': user['role'],
                    'last_login': user['last_login'].isoformat() if user['last_login'] else None,
                    'login_count': user['login_count']
                })

        return jsonify(success_response({
            'active_sessions': active_sessions,
            'total_sessions': len(active_sessions)
        }))

    except Exception as e:
        return jsonify(error_response(f'Failed to get sessions: {str(e)}')), 500
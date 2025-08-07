"""
User Authentication Endpoints
User registration, login, profile management - Updated with Database Integration
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
import uuid
from utils.database import get_db_manager, execute_query

# Initialize blueprint
user_auth_bp = Blueprint('user_auth', __name__)

# Import updated authentication system
try:
    # Now uses your DatabaseAuth system
    from auth.user_auth import DatabaseUserAuth as UserAuth, DatabaseSecurityUtils as SecurityUtils, token_required, role_required
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
    """Register new user with database integration using DatabaseAuth"""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['email', 'password', 'role']
        for field in required_fields:
            if not data.get(field):
                return jsonify(f'{field} is required'), 400

        email = data.get('email').lower().strip()
        password = data.get('password')
        role = data.get('role')

        # Validate role
        if role not in ['customer', 'wholesale_reseller']:  # Admin created separately
            return jsonify('Invalid role'), 400

        # Use DatabaseAuth to create user (this handles validation internally)
        user_data, error_msg = UserAuth.create_user(
            email=email,
            password=password,
            role=role,
            profile=data.get('profile', {})
        )
        
        if not user_data:
            return jsonify(error_msg), 400

        user_id = user_data['id']

        # Create role-specific profiles
        db_manager = get_db_manager()
        
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

        # Generate token using DatabaseAuth
        token = UserAuth.generate_token({
            'id': user_id,
            'email': email,
            'role': role
        })

        # Log security event
        SecurityUtils.log_security_event(user_id, 'user_registered', {'role': role})

        return jsonify({
            'message': 'User registered successfully',
            'user': {
                'id': user_id,
                'email': email,
                'role': role,
                'profile': data.get('profile', {})
            },
            'token': token
        }), 201

    except Exception as e:
        return jsonify(f'Registration failed: {str(e)}'), 500

@user_auth_bp.route('/login', methods=['POST'])
def login():
    """User login with database validation using DatabaseAuth"""
    try:
        data = request.get_json()

        email = data.get('email', '').lower().strip()
        password = data.get('password', '')

        if not email or not password:
            return jsonify('Email and password are required'), 400

        # Use DatabaseAuth to authenticate (this handles all the database logic)
        auth_result, error_msg = UserAuth.authenticate_user(email, password)
        
        if not auth_result:
            return jsonify(error_msg or 'Invalid credentials'), 401

        return jsonify({
            'message': 'Login successful',
            'user': auth_result['user'],
            'token': auth_result['token']
        })

    except Exception as e:
        return jsonify(f'Login failed: {str(e)}'), 500

@user_auth_bp.route('/logout', methods=['POST'])
@token_required
def logout():
    """User logout"""
    try:
        user_id = request.current_user.get('user_id')
        SecurityUtils.log_security_event(user_id, 'logout', {})
        return jsonify({'message': 'Logout successful'})
    except Exception as e:
        return jsonify(f'Logout failed: {str(e)}'), 500

@user_auth_bp.route('/profile', methods=['GET'])
@token_required
def get_profile():
    """Get user profile from database using DatabaseAuth"""
    try:
        user_id = request.current_user.get('user_id')
        
        # Use DatabaseAuth to get user data
        user_data = UserAuth.get_user_by_id(user_id)
        
        if not user_data:
            return jsonify('User not found'), 404

        profile_data = {
            'user': {
                'id': user_data['id'],
                'email': user_data['email'],
                'role': user_data['role'],
                'status': user_data['status'],
                'profile': user_data.get('profile', {}),
                'created_at': user_data['created_at'].isoformat() if user_data.get('created_at') else None,
                'last_login': user_data['last_login'].isoformat() if user_data.get('last_login') else None,
                'login_count': user_data.get('login_count', 0)
            }
        }

        # Add role-specific data
        if user_data.get('customer_id'):
            profile_data['customer_profile'] = {
                'id': user_data['customer_id'],
                'customer_type': user_data['customer_type']
            }

        if user_data.get('reseller_id'):
            profile_data['reseller_profile'] = {
                'id': user_data['reseller_id'],
                'business_name': user_data['business_name'],
                'tier': user_data['tier']
            }

        return jsonify(profile_data)

    except Exception as e:
        return jsonify(f'Failed to get profile: {str(e)}'), 500

@user_auth_bp.route('/profile', methods=['PUT'])
@token_required
def update_profile():
    """Update user profile in database"""
    try:
        user_id = request.current_user.get('user_id')
        data = request.get_json()
        
        if not data:
            return jsonify('Profile data is required'), 400

        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify('Database not available'), 503

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

        return jsonify({
            'message': 'Profile updated successfully',
            'updated_fields': list(data.keys())
        })

    except Exception as e:
        return jsonify(f'Failed to update profile: {str(e)}'), 500

@user_auth_bp.route('/change-password', methods=['PUT'])
@token_required
def change_password():
    """Change user password in database"""
    try:
        user_id = request.current_user.get('user_id')
        data = request.get_json()
        
        if not data:
            return jsonify('Password data is required'), 400

        current_password = data.get('current_password')
        new_password = data.get('new_password')

        if not current_password or not new_password:
            return jsonify('Current and new password required'), 400

        # Get current password hash from database
        user_result = execute_query(
            'SELECT password_hash FROM users WHERE id = %s',
            (user_id,),
            'one'
        )

        if not user_result['success'] or not user_result['data']:
            return jsonify('User not found'), 404

        # Verify current password using DatabaseAuth
        if not UserAuth.verify_password(current_password, user_result['data']['password_hash']):
            SecurityUtils.log_security_event(user_id, 'password_change_failed', {
                'reason': 'invalid_current_password'
            })
            return jsonify('Current password is incorrect'), 401

        # Update password in database using DatabaseAuth
        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify('Database not available'), 503

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
        return jsonify({'message': 'Password changed successfully'})

    except Exception as e:
        return jsonify(f'Failed to change password: {str(e)}'), 500

@user_auth_bp.route('/verify-token', methods=['POST'])
def verify_token():
    """Verify if a token is valid using DatabaseAuth"""
    try:
        data = request.get_json()
        token = data.get('token') if data else None
        
        if not token:
            # Try to get token from Authorization header
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
            else:
                return jsonify('Token is required'), 400

        # Use DatabaseAuth to verify token (this includes database validation)
        valid, result = UserAuth.verify_token(token)
        
        if not valid:
            return jsonify(result), 401

        return jsonify({
            'valid': True,
            'user': {
                'id': result['user_id'],
                'email': result['email'],
                'role': result['role']
            }
        })

    except Exception as e:
        return jsonify(f'Token verification failed: {str(e)}'), 500

@user_auth_bp.route('/health')
def auth_health():
    """Authentication service health check"""
    try:
        db_manager = get_db_manager()
        
        return jsonify({
            'service': 'User Authentication API',
            'status': 'healthy',
            'database_connected': db_manager.available,
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

# Additional endpoints for admin functionality
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

        return jsonify({
            'active_sessions': active_sessions,
            'total_sessions': len(active_sessions)
        })

    except Exception as e:
        return jsonify(f'Failed to get sessions: {str(e)}'), 500
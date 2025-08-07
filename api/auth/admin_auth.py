"""
Database-Integrated Authentication System
Uses your actual Neon PostgreSQL database structure
"""

import jwt
import bcrypt
import datetime
import uuid
from functools import wraps
from flask import request, jsonify, current_app
from utils.database import get_db_manager, execute_query

class DatabaseUserAuth:
    """Authentication system integrated with your actual database"""
    
    # Role hierarchy matching your database
    ROLES = {
        'admin': {
            'level': 100,
            'permissions': ['all']
        },
        'wholesale_reseller': {
            'level': 50,
            'permissions': ['view_wholesale_pricing', 'create_quotes', 'manage_customers', 'view_analytics', 'reseller_dashboard']
        },
        'customer': {
            'level': 10,
            'permissions': ['view_retail_pricing', 'create_quotes', 'view_own_policies', 'customer_dashboard']
        }
    }
    
    @staticmethod
    def hash_password(password):
        """Hash password using bcrypt"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    @staticmethod
    def verify_password(password, hashed):
        """Verify password against hash with detailed logging"""
        try:            
            # Handle both string and bytes
            if isinstance(password, str):
                password_bytes = password.encode('utf-8')
            else:
                password_bytes = password
                
            if isinstance(hashed, str):
                hashed_bytes = hashed.encode('utf-8')
            else:
                hashed_bytes = hashed
            
            result = bcrypt.checkpw(password_bytes, hashed_bytes)
            return result
            
        except Exception as e:
            print(f"Password verification error: {e}")
            print(f"  - Exception type: {type(e)}")
            return False
    
    @staticmethod
    def authenticate_user(email, password):
        """Authenticate user against database with enhanced debugging"""
        try:            
            db_manager = get_db_manager()
            if not db_manager.available:
                print("Database not available")
                return None, "Database not available"
            
            # Get user from database
            result = execute_query('''
                SELECT id, email, password_hash, role, status, profile, 
                       last_login, login_count
                FROM users 
                WHERE email = %s AND status = 'active'
            ''', (email.lower().strip(),), 'one')
            
            if not result['success'] or not result['data']:
                print("User not found or query failed")
                return None, "Invalid credentials"
            
            user = result['data']
            
            # Verify password with detailed logging
            password_valid = DatabaseUserAuth.verify_password(password, user['password_hash'])
            
            if not password_valid:
                print("Password verification failed")
                return None, "Invalid credentials"
            
            # Update login statistics
            DatabaseUserAuth._update_login_stats(user['id'])
            
            # Generate token
            user_data = {
                'id': str(user['id']),
                'email': user['email'],
                'role': user['role'],
                'profile': user['profile'] or {}
            }
            
            token = DatabaseUserAuth.generate_token(user_data)
            return {
                'token': token,
                'user': user_data
            }, None
            
        except Exception as e:
            print(f"Authentication error: {e}")
            import traceback
            traceback.print_exc()
            return None, f"Authentication failed: {str(e)}"
    
    @staticmethod
    def _update_login_stats(user_id):
        """Update user login statistics"""
        try:
            db_manager = get_db_manager()
            if db_manager.available:
                # Use raw SQL execution for PostgreSQL expressions
                result = execute_query('''
                    UPDATE users 
                    SET last_login = %s, 
                        login_count = COALESCE(login_count, 0) + 1,
                        updated_at = %s
                    WHERE id = %s
                ''', (
                    datetime.datetime.utcnow(),
                    datetime.datetime.utcnow(), 
                    user_id
                ))
                print(f"Login stats update result: {result}")
        except Exception as e:
            print(f"Login stats update error: {e}")
    
    @staticmethod
    def generate_token(user_data):
        """Generate JWT token"""
        payload = {
            'user_id': user_data['id'],
            'email': user_data['email'],
            'role': user_data['role'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24),
            'iat': datetime.datetime.utcnow()
        }
        
        return jwt.encode(payload, current_app.config.get('SECRET_KEY', 'default-secret'), algorithm='HS256')
    
    @staticmethod
    def verify_token(token):
        """Verify JWT token and check user still exists"""
        try:
            payload = jwt.decode(token, current_app.config.get('SECRET_KEY', 'default-secret'), algorithms=['HS256'])
            
            # Check if user still exists and is active
            user_id = payload.get('user_id')
            if user_id:
                db_manager = get_db_manager()
                if db_manager.available:
                    result = execute_query('''
                        SELECT id, email, role, status 
                        FROM users 
                        WHERE id = %s AND status = 'active'
                    ''', (user_id,), 'one')
                    
                    if result['success'] and result['data']:
                        # Update payload with fresh data from database
                        user = result['data']
                        payload['email'] = user['email']
                        payload['role'] = user['role']
                        return True, payload
                    else:
                        return False, "User not found or inactive"
            
            return True, payload
            
        except jwt.ExpiredSignatureError:
            return False, "Token has expired"
        except jwt.InvalidTokenError:
            return False, "Invalid token"
    
    @staticmethod
    def has_permission(user_role, required_permission):
        """Check if user role has required permission"""
        if user_role not in DatabaseUserAuth.ROLES:
            return False
        
        user_permissions = DatabaseUserAuth.ROLES[user_role]['permissions']
        return 'all' in user_permissions or required_permission in user_permissions
    
    @staticmethod
    def get_role_level(role):
        """Get numeric level for role comparison"""
        return DatabaseUserAuth.ROLES.get(role, {}).get('level', 0)
    
    @staticmethod
    def create_user(email, password, role='customer', profile=None):
        """Create new user in database"""
        try:
            db_manager = get_db_manager()
            if not db_manager.available:
                return None, "Database not available"
            
            # Validate email format
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, email):
                return None, "Invalid email format"
            
            # Validate password strength
            if len(password) < 8:
                return None, "Password must be at least 8 characters long"
            
            # Validate role
            if role not in DatabaseUserAuth.ROLES:
                return None, "Invalid role"
            
            # Check if user already exists
            existing = execute_query(
                'SELECT id FROM users WHERE email = %s',
                (email.lower().strip(),),
                'one'
            )
            
            if existing['success'] and existing['data']:
                return None, "User already exists"
            
            # Create user
            user_data = {
                'id': str(uuid.uuid4()),
                'email': email.lower().strip(),
                'password_hash': DatabaseUserAuth.hash_password(password),
                'role': role,
                'status': 'active',
                'profile': profile or {},
                'login_count': 0,
                'created_at': datetime.datetime.utcnow(),
                'updated_at': datetime.datetime.utcnow()
            }
            
            result = db_manager.insert_record('users', user_data)
            
            if result['success']:
                return user_data, None
            else:
                return None, f"Failed to create user: {result.get('error')}"
                
        except Exception as e:
            return None, f"User creation error: {str(e)}"
    
    @staticmethod
    def get_user_by_id(user_id):
        """Get user by ID from database"""
        try:
            result = execute_query('''
                SELECT u.id, u.email, u.role, u.status, u.profile, 
                       u.created_at, u.updated_at, u.last_login, u.login_count,
                       c.id as customer_id, c.customer_type,
                       r.id as reseller_id, r.business_name, r.tier
                FROM users u
                LEFT JOIN customers c ON u.id = c.user_id
                LEFT JOIN resellers r ON u.id = r.user_id
                WHERE u.id = %s
            ''', (user_id,), 'one')
            
            if result['success'] and result['data']:
                user = dict(result['data'])
                # Convert UUIDs to strings for JSON serialization
                for key in ['id', 'customer_id', 'reseller_id']:
                    if user.get(key):
                        user[key] = str(user[key])
                return user
            return None
            
        except Exception as e:
            print(f"Get user error: {e}")
            return None

def token_required(f):
    """Decorator to require valid JWT token with database validation"""
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
        
        # Verify token with database validation
        valid, result = DatabaseUserAuth.verify_token(token)
        if not valid:
            return jsonify({'error': result}), 401
        
        # Add user data to request context
        request.current_user = result
        return f(*args, **kwargs)
    
    return decorated

def role_required(required_role):
    """Decorator to require specific role or higher"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(request, 'current_user'):
                return jsonify({'error': 'Authentication required'}), 401
            
            user_role = request.current_user.get('role')
            user_level = DatabaseUserAuth.get_role_level(user_role)
            required_level = DatabaseUserAuth.get_role_level(required_role)
            
            if user_level < required_level:
                return jsonify({'error': 'Insufficient permissions'}), 403
            
            return f(*args, **kwargs)
        return decorated
    return decorator

def permission_required(permission):
    """Decorator to require specific permission"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(request, 'current_user'):
                return jsonify({'error': 'Authentication required'}), 401
            
            user_role = request.current_user.get('role')
            if not DatabaseUserAuth.has_permission(user_role, permission):
                return jsonify({'error': f'Permission {permission} required'}), 403
            
            return f(*args, **kwargs)
        return decorated
    return decorator

class DatabaseSecurityUtils:
    """Security utilities with database logging"""
    
    @staticmethod
    def log_security_event(user_id, event_type, details):
        """Log security events to database"""
        try:
            # In production, you might create a security_events table
            log_entry = {
                'user_id': user_id,
                'event_type': event_type,
                'details': details,
                'timestamp': datetime.datetime.utcnow(),
                'ip_address': request.remote_addr if request else 'unknown',
                'user_agent': request.headers.get('User-Agent', '') if request else ''
            }
            
            # For now, just print (you can extend this to database logging)
            print(f"Security Event: {log_entry}")
            return log_entry
            
        except Exception as e:
            print(f"Security logging error: {e}")
            return None

# Aliases for backward compatibility
SecurityUtils = DatabaseSecurityUtils
UserAuth = DatabaseUserAuth
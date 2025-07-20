"""
ConnectedAutoCare User Authentication System
Multi-tier authentication with role-based access control
"""

import jwt
import bcrypt
import datetime
from functools import wraps
from flask import request, jsonify, current_app
import re

class UserAuth:
    """Comprehensive user authentication and authorization system"""
    
    # User roles hierarchy
    ROLES = {
        'admin': {
            'level': 100,
            'permissions': ['all']
        },
        'wholesale_reseller': {
            'level': 50,
            'permissions': ['view_wholesale_pricing', 'create_quotes', 'manage_customers', 'view_analytics']
        },
        'customer': {
            'level': 10,
            'permissions': ['view_retail_pricing', 'create_quotes', 'view_own_policies']
        }
    }
    
    @staticmethod
    def hash_password(password):
        """Hash password using bcrypt"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    @staticmethod
    def verify_password(password, hashed):
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    
    @staticmethod
    def validate_password(password):
        """Validate password strength"""
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        
        if not re.search(r"[A-Z]", password):
            return False, "Password must contain at least one uppercase letter"
        
        if not re.search(r"[a-z]", password):
            return False, "Password must contain at least one lowercase letter"
        
        if not re.search(r"\d", password):
            return False, "Password must contain at least one number"
        
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            return False, "Password must contain at least one special character"
        
        return True, "Password is valid"
    
    @staticmethod
    def validate_email(email):
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def generate_token(user_data):
        """Generate JWT token for user"""
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
        """Verify JWT token and return user data"""
        try:
            payload = jwt.decode(token, current_app.config.get('SECRET_KEY', 'default-secret'), algorithms=['HS256'])
            return True, payload
        except jwt.ExpiredSignatureError:
            return False, "Token has expired"
        except jwt.InvalidTokenError:
            return False, "Invalid token"
    
    @staticmethod
    def has_permission(user_role, required_permission):
        """Check if user role has required permission"""
        if user_role not in UserAuth.ROLES:
            return False
        
        user_permissions = UserAuth.ROLES[user_role]['permissions']
        return 'all' in user_permissions or required_permission in user_permissions
    
    @staticmethod
    def get_role_level(role):
        """Get numeric level for role comparison"""
        return UserAuth.ROLES.get(role, {}).get('level', 0)

def token_required(f):
    """Decorator to require valid JWT token"""
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
        
        # Verify token
        valid, result = UserAuth.verify_token(token)
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
            user_level = UserAuth.get_role_level(user_role)
            required_level = UserAuth.get_role_level(required_role)
            
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
            if not UserAuth.has_permission(user_role, permission):
                return jsonify({'error': f'Permission {permission} required'}), 403
            
            return f(*args, **kwargs)
        return decorated
    return decorator

class SessionManager:
    """Manage user sessions and security"""
    
    @staticmethod
    def create_session(user_id, token):
        """Create user session record"""
        session_data = {
            'user_id': user_id,
            'token': token,
            'created_at': datetime.datetime.utcnow(),
            'last_activity': datetime.datetime.utcnow(),
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', '')
        }
        return session_data
    
    @staticmethod
    def update_activity(user_id):
        """Update last activity timestamp"""
        return {
            'user_id': user_id,
            'last_activity': datetime.datetime.utcnow()
        }
    
    @staticmethod
    def is_session_valid(session_data, max_inactive_hours=24):
        """Check if session is still valid"""
        if not session_data:
            return False
        
        last_activity = session_data.get('last_activity')
        if not last_activity:
            return False
        
        # Convert string to datetime if needed
        if isinstance(last_activity, str):
            last_activity = datetime.datetime.fromisoformat(last_activity)
        
        inactive_time = datetime.datetime.utcnow() - last_activity
        return inactive_time.total_seconds() < (max_inactive_hours * 3600)

class SecurityUtils:
    """Security utilities and helpers"""
    
    @staticmethod
    def sanitize_input(data):
        """Sanitize user input to prevent injection attacks"""
        if isinstance(data, str):
            # Remove potentially dangerous characters
            dangerous_chars = ['<', '>', '"', "'", '&', 'script', 'javascript']
            for char in dangerous_chars:
                data = data.replace(char, '')
        return data
    
    @staticmethod
    def rate_limit_check(user_id, action, max_attempts=5, window_minutes=15):
        """Check rate limiting for user actions"""
        # This would typically use Redis or database
        # For now, return True (no rate limiting)
        return True
    
    @staticmethod
    def log_security_event(user_id, event_type, details):
        """Log security-related events"""
        log_entry = {
            'user_id': user_id,
            'event_type': event_type,
            'details': details,
            'timestamp': datetime.datetime.utcnow(),
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', '')
        }
        # In production, this would write to a security log
        print(f"Security Event: {log_entry}")
        return log_entry


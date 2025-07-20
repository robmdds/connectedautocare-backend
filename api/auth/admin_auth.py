#!/usr/bin/env python3
"""
ConnectedAutoCare.com - Admin Authentication System
Secure authentication and authorization for admin panel access
"""

import jwt
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify

# Create blueprint for admin auth
auth_bp = Blueprint('admin_auth', __name__)

# Admin user configuration (in production, store in secure database)
ADMIN_USERS = {
    "admin": {
        "password_hash": "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8",  # 'password'
        "email": "admin@connectedautocare.com",
        "role": "super_admin",
        "permissions": ["all"]
    }
}

# JWT Configuration
JWT_SECRET_KEY = "your-super-secret-jwt-key-change-in-production"
JWT_EXPIRATION_HOURS = 24


class AdminAuth:
    """Admin authentication and authorization handler"""

    @staticmethod
    def hash_password(password):
        """Hash password using SHA-256"""
        return hashlib.sha256(password.encode()).hexdigest()

    @staticmethod
    def verify_password(password, password_hash):
        """Verify password against hash"""
        return AdminAuth.hash_password(password) == password_hash

    @staticmethod
    def generate_token(username, role="admin"):
        """Generate JWT token for authenticated admin"""
        payload = {
            'username': username,
            'role': role,
            'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')

    @staticmethod
    def verify_token(token):
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    @staticmethod
    def authenticate_admin(username, password):
        """Authenticate admin user"""
        if username not in ADMIN_USERS:
            return None

        user = ADMIN_USERS[username]
        if AdminAuth.verify_password(password, user['password_hash']):
            token = AdminAuth.generate_token(username, user['role'])
            return {
                'token': token,
                'username': username,
                'email': user['email'],
                'role': user['role'],
                'permissions': user['permissions']
            }
        return None


def require_admin_auth(f):
    """Decorator to require admin authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None

        # Get token from Authorization header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]  # Bearer <token>
            except IndexError:
                return jsonify({'error': 'Invalid authorization header format'}), 401

        if not token:
            return jsonify({'error': 'Authentication token required'}), 401

        # Verify token
        payload = AdminAuth.verify_token(token)
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401

        # Add user info to request context
        request.admin_user = payload
        return f(*args, **kwargs)

    return decorated_function


def require_permission(permission):
    """Decorator to require specific permission"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not hasattr(request, 'admin_user'):
                return jsonify({'error': 'Authentication required'}), 401

            username = request.admin_user['username']
            if username not in ADMIN_USERS:
                return jsonify({'error': 'User not found'}), 401

            user_permissions = ADMIN_USERS[username]['permissions']
            if 'all' not in user_permissions and permission not in user_permissions:
                return jsonify({'error': 'Insufficient permissions'}), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Admin authentication routes


@auth_bp.route('/login', methods=['POST'])
def admin_login():
    """Admin login endpoint"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return jsonify({
                'success': False,
                'error': 'Username and password required'
            }), 400

        # Authenticate admin
        auth_result = AdminAuth.authenticate_admin(username, password)
        if not auth_result:
            return jsonify({
                'success': False,
                'error': 'Invalid credentials'
            }), 401

        return jsonify({
            'success': True,
            'data': auth_result
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Login failed: {str(e)}'
        }), 500


@auth_bp.route('/verify', methods=['GET'])
@require_admin_auth
def verify_admin_token():
    """Verify admin token validity"""
    return jsonify({
        'success': True,
        'data': {
            'username': request.admin_user['username'],
            'role': request.admin_user['role'],
            'valid': True
        }
    })


@auth_bp.route('/logout', methods=['POST'])
@require_admin_auth
def admin_logout():
    """Admin logout endpoint"""
    # In a production system, you might want to blacklist the token
    return jsonify({
        'success': True,
        'message': 'Logged out successfully'
    })


@auth_bp.route('/change-password', methods=['POST'])
@require_admin_auth
def change_admin_password():
    """Change admin password"""
    try:
        data = request.get_json()
        current_password = data.get('current_password')
        new_password = data.get('new_password')

        if not current_password or not new_password:
            return jsonify({
                'success': False,
                'error': 'Current and new password required'
            }), 400

        username = request.admin_user['username']
        user = ADMIN_USERS[username]

        # Verify current password
        if not AdminAuth.verify_password(current_password, user['password_hash']):
            return jsonify({
                'success': False,
                'error': 'Current password incorrect'
            }), 401

        # Update password (in production, update database)
        ADMIN_USERS[username]['password_hash'] = AdminAuth.hash_password(
            new_password)

        return jsonify({
            'success': True,
            'message': 'Password changed successfully'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Password change failed: {str(e)}'
        }), 500


@auth_bp.route('/health', methods=['GET'])
def admin_auth_health():
    """Admin auth health check"""
    return jsonify({
        'success': True,
        'message': 'Admin authentication is operational',
        'features': ['JWT Authentication', 'Role-based Access', 'Password Management']
    })

# Session management


class AdminSession:
    """Admin session management"""

    active_sessions = {}

    @staticmethod
    def create_session(username, token):
        """Create admin session"""
        session_id = secrets.token_urlsafe(32)
        AdminSession.active_sessions[session_id] = {
            'username': username,
            'token': token,
            'created_at': datetime.utcnow(),
            'last_activity': datetime.utcnow()
        }
        return session_id

    @staticmethod
    def update_activity(session_id):
        """Update session last activity"""
        if session_id in AdminSession.active_sessions:
            AdminSession.active_sessions[session_id]['last_activity'] = datetime.utcnow(
            )

    @staticmethod
    def cleanup_expired_sessions():
        """Remove expired sessions"""
        current_time = datetime.utcnow()
        expired_sessions = []

        for session_id, session in AdminSession.active_sessions.items():
            # 24 hours
            if (current_time - session['last_activity']).total_seconds() > 86400:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            del AdminSession.active_sessions[session_id]

# Security utilities


class AdminSecurity:
    """Admin security utilities"""

    @staticmethod
    def log_admin_action(username, action, details=None):
        """Log admin actions for audit trail"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'username': username,
            'action': action,
            'details': details or {},
            'ip_address': request.remote_addr if request else 'unknown'
        }

        # In production, store in database or log file
        print(f"ADMIN ACTION: {log_entry}")
        return log_entry

    @staticmethod
    def validate_admin_request():
        """Validate admin request for security"""
        # Check for common security issues
        if request.content_length and request.content_length > 10 * 1024 * 1024:  # 10MB limit
            return False, "Request too large"

        # Add more security validations as needed
        return True, "Valid"

# Default admin setup


def setup_default_admin():
    """Setup default admin user"""
    # In production, this should be done through a secure setup process
    default_password = "admin123"  # Change this!
    ADMIN_USERS["admin"]["password_hash"] = AdminAuth.hash_password(
        default_password)

    print("=" * 50)
    print("ADMIN SETUP COMPLETE")
    print("=" * 50)
    print(f"Default admin username: admin")
    print(f"Default admin password: {default_password}")
    print("IMPORTANT: Change the default password immediately!")
    print("=" * 50)


if __name__ == "__main__":
    # Test authentication system
    setup_default_admin()

    # Test login
    result = AdminAuth.authenticate_admin("admin", "admin123")
    if result:
        print("Authentication test: PASSED")
        print(f"Token: {result['token'][:50]}...")

        # Test token verification
        payload = AdminAuth.verify_token(result['token'])
        if payload:
            print("Token verification test: PASSED")
        else:
            print("Token verification test: FAILED")
    else:
        print("Authentication test: FAILED")

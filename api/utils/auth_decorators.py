"""
Authentication and Authorization Decorators
JWT token validation, role checking, and permission management
"""

from functools import wraps
from flask import request, jsonify
import jwt
import os
from datetime import datetime, timezone

# JWT Configuration
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'connectedautocare-jwt-secret-2025')
JWT_ALGORITHM = 'HS256'

def token_required(f):
    """Require valid authentication token"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        
        # Extract token from Authorization header
        if auth_header:
            try:
                token = auth_header.split(' ')[1]  # Bearer <token>
            except IndexError:
                return jsonify({'error': 'Invalid token format'}), 401
        
        # Also check for token in request body or query params as fallback
        if not token:
            token = request.args.get('token') or (request.get_json() or {}).get('token')
        
        if not token:
            return jsonify({'error': 'Authentication token is missing'}), 401
        
        try:
            # Decode JWT token
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            
            # Check token expiration
            if 'exp' in payload and payload['exp'] < datetime.now(timezone.utc).timestamp():
                return jsonify({'error': 'Token has expired'}), 401
            
            # Add user info to request context
            request.current_user = {
                'user_id': payload.get('id') or payload.get('user_id'),
                'email': payload.get('email'),
                'role': payload.get('role'),
                'permissions': payload.get('permissions', []),
                'token_issued_at': payload.get('iat'),
                'token_expires_at': payload.get('exp')
            }
            
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid authentication token'}), 401
        except Exception as e:
            return jsonify({'error': f'Token validation failed: {str(e)}'}), 401
        
        return f(*args, **kwargs)
    
    return wrapper

def role_required(required_role):
    """Require specific user role"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # This decorator should be used after @token_required
            if not hasattr(request, 'current_user') or not request.current_user:
                return jsonify({'error': 'Authentication required before role check'}), 401
            
            user_role = request.current_user.get('role')
            
            if not user_role:
                return jsonify({'error': 'User role not found in token'}), 403
            
            # Define role hierarchy
            role_hierarchy = {
                'customer': 1,
                'wholesale_reseller': 2,
                'admin': 3
            }
            
            required_level = role_hierarchy.get(required_role, 0)
            user_level = role_hierarchy.get(user_role, 0)
            
            # Check if user has required role level or higher
            if user_level < required_level:
                return jsonify({
                    'error': f'Insufficient permissions. Role "{required_role}" or higher required',
                    'user_role': user_role,
                    'required_role': required_role
                }), 403
            
            return f(*args, **kwargs)
        
        return wrapper
    return decorator

def permission_required(permission):
    """Require specific permission"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # This decorator should be used after @token_required
            if not hasattr(request, 'current_user') or not request.current_user:
                return jsonify({'error': 'Authentication required before permission check'}), 401
            
            user_permissions = request.current_user.get('permissions', [])
            user_role = request.current_user.get('role')
            
            # Admin has all permissions
            if user_role == 'admin':
                return f(*args, **kwargs)
            
            # Check if user has the specific permission
            if permission not in user_permissions:
                return jsonify({
                    'error': f'Permission "{permission}" required',
                    'user_permissions': user_permissions
                }), 403
            
            return f(*args, **kwargs)
        
        return wrapper
    return decorator

def optional_auth(f):
    """Optional authentication - adds user info if token is provided"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        
        # Extract token if present
        if auth_header and auth_header.startswith('Bearer '):
            try:
                token = auth_header.split(' ')[1]
                
                # Try to decode token
                payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
                
                # Add user info to request context if token is valid
                request.current_user = {
                    'user_id': payload.get('id') or payload.get('user_id'),
                    'email': payload.get('email'),
                    'role': payload.get('role'),
                    'permissions': payload.get('permissions', []),
                    'authenticated': True
                }
            except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
                # Invalid token - continue without authentication
                request.current_user = {'authenticated': False}
        else:
            # No token provided
            request.current_user = {'authenticated': False}
        
        return f(*args, **kwargs)
    
    return wrapper

def rate_limit(max_requests_per_minute=60):
    """Basic rate limiting decorator"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Get client IP
            client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            
            # In production, implement proper rate limiting with Redis
            # For now, this is a placeholder
            
            # TODO: Implement actual rate limiting logic
            # - Store request counts per IP in Redis/database
            # - Check if client has exceeded rate limit
            # - Return 429 Too Many Requests if limit exceeded
            
            return f(*args, **kwargs)
        
        return wrapper
    return decorator

def admin_required(f):
    """Shorthand for admin role requirement"""
    @wraps(f)
    @token_required
    @role_required('admin')
    def wrapper(*args, **kwargs):
        return f(*args, **kwargs)
    
    return wrapper

def reseller_or_admin_required(f):
    """Require wholesale reseller role or higher"""
    @wraps(f)
    @token_required
    @role_required('wholesale_reseller')
    def wrapper(*args, **kwargs):
        return f(*args, **kwargs)
    
    return wrapper

def validate_api_key(f):
    """Validate API key for external integrations"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        # In production, validate against database of valid API keys
        valid_api_keys = [
            os.environ.get('INTERNAL_API_KEY', 'dev-api-key-12345'),
            os.environ.get('PARTNER_API_KEY', 'partner-api-key-67890')
        ]
        
        if api_key not in valid_api_keys:
            return jsonify({'error': 'Invalid API key'}), 403
        
        # Add API key info to request context
        request.api_key_info = {
            'api_key': api_key,
            'validated': True,
            'key_type': 'internal' if api_key == valid_api_keys[0] else 'partner'
        }
        
        return f(*args, **kwargs)
    
    return wrapper

def cors_preflight_handler(f):
    """Handle CORS preflight requests"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.method == 'OPTIONS':
            response = jsonify({'message': 'CORS preflight'})
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key'
            return response
        
        return f(*args, **kwargs)
    
    return wrapper

def log_api_access(f):
    """Log API access for monitoring"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        # Get request info
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        user_agent = request.headers.get('User-Agent', 'Unknown')
        endpoint = request.endpoint
        method = request.method
        
        # Get user info if authenticated
        user_info = {}
        if hasattr(request, 'current_user') and request.current_user.get('authenticated'):
            user_info = {
                'user_id': request.current_user.get('user_id'),
                'role': request.current_user.get('role')
            }
        
        # Log access (in production, use proper logging system)
        print(f"API Access: {method} {endpoint} from {client_ip} - {user_info}")
        
        # Execute the actual function
        result = f(*args, **kwargs)
        
        # Log response status if needed
        if hasattr(result, 'status_code'):
            print(f"API Response: {endpoint} returned {result.status_code}")
        
        return result
    
    return wrapper

# Utility functions for token management
def generate_jwt_token(user_data, expires_in_hours=24):
    """Generate JWT token for user"""
    from datetime import timedelta
    
    payload = {
        'id': user_data.get('id'),
        'user_id': user_data.get('id'),  # Duplicate for compatibility
        'email': user_data.get('email'),
        'role': user_data.get('role'),
        'permissions': user_data.get('permissions', []),
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)
    }
    
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def decode_jwt_token(token):
    """Decode and validate JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return {'success': True, 'payload': payload}
    except jwt.ExpiredSignatureError:
        return {'success': False, 'error': 'Token has expired'}
    except jwt.InvalidTokenError:
        return {'success': False, 'error': 'Invalid token'}

def refresh_jwt_token(token):
    """Refresh JWT token if it's close to expiration"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        
        # Check if token expires within next hour
        exp_time = datetime.fromtimestamp(payload['exp'], tz=timezone.utc)
        current_time = datetime.now(timezone.utc)
        time_until_expiry = exp_time - current_time
        
        if time_until_expiry.total_seconds() < 3600:  # Less than 1 hour
            # Generate new token
            user_data = {
                'id': payload.get('id'),
                'email': payload.get('email'),
                'role': payload.get('role'),
                'permissions': payload.get('permissions', [])
            }
            new_token = generate_jwt_token(user_data)
            return {'success': True, 'token': new_token, 'refreshed': True}
        else:
            return {'success': True, 'token': token, 'refreshed': False}
            
    except jwt.ExpiredSignatureError:
        return {'success': False, 'error': 'Token has expired and cannot be refreshed'}
    except jwt.InvalidTokenError:
        return {'success': False, 'error': 'Invalid token'}
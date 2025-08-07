"""
User Authentication Endpoints
User registration, login, profile management
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
import uuid
from utils.auth_decorators import token_required, role_required
from utils.service_availability import ServiceChecker

# Initialize blueprint
user_auth_bp = Blueprint('user_auth', __name__)

# Import user management services with error handling
try:
    from auth.user_auth import UserAuth, SessionManager, SecurityUtils
    from models.database_models import UserModel, CustomerModel, ResellerModel
    user_management_available = True
    
    # Initialize user management components
    user_model = UserModel()
    customer_model = CustomerModel()
    reseller_model = ResellerModel()
    
    # Initialize in-memory databases (in production, this would be persistent storage)
    users_db = {}
    customers_db = {}
    resellers_db = {}
    sessions_db = {}
    
    def initialize_sample_data():
        """Initialize sample data for testing"""
        global users_db, customers_db, resellers_db

        # Create admin user
        admin_id = str(uuid.uuid4())
        admin_user = user_model.create_user({
            'id': admin_id,
            'email': 'admin@connectedautocare.com',
            'password_hash': UserAuth.hash_password('Admin123!'),
            'role': 'admin',
            'profile': {
                'first_name': 'System',
                'last_name': 'Administrator',
                'company': 'ConnectedAutoCare'
            }
        })
        users_db[admin_id] = admin_user

        # Create sample wholesale reseller
        reseller_user_id = str(uuid.uuid4())
        reseller_user = user_model.create_user({
            'id': reseller_user_id,
            'email': 'reseller@example.com',
            'password_hash': UserAuth.hash_password('Reseller123!'),
            'role': 'wholesale_reseller',
            'profile': {
                'first_name': 'John',
                'last_name': 'Smith',
                'company': 'ABC Insurance Agency'
            }
        })
        users_db[reseller_user_id] = reseller_user

        # Create reseller profile
        reseller_id = str(uuid.uuid4())
        reseller_profile = reseller_model.create_reseller({
            'id': reseller_id,
            'user_id': reseller_user_id,
            'business_name': 'ABC Insurance Agency',
            'license_number': 'INS-12345',
            'license_state': 'CA',
            'business_type': 'insurance_agency',
            'phone': '555-123-4567',
            'email': 'reseller@example.com'
        })
        resellers_db[reseller_id] = reseller_profile

        # Create sample customer
        customer_user_id = str(uuid.uuid4())
        customer_user = user_model.create_user({
            'id': customer_user_id,
            'email': 'customer@example.com',
            'password_hash': UserAuth.hash_password('Customer123!'),
            'role': 'customer',
            'profile': {
                'first_name': 'Jane',
                'last_name': 'Doe'
            }
        })
        users_db[customer_user_id] = customer_user

        # Create customer profile
        customer_id = str(uuid.uuid4())
        customer_profile = customer_model.create_customer({
            'id': customer_id,
            'user_id': customer_user_id,
            'first_name': 'Jane',
            'last_name': 'Doe',
            'email': 'customer@example.com',
            'phone': '555-987-6543'
        })
        customers_db[customer_id] = customer_profile

    # Initialize sample data
    try:
        initialize_sample_data()
    except Exception as e:
        print(f"Warning: Could not initialize sample data: {e}")

except ImportError as e:
    print(f"Warning: User management not available: {e}")
    user_management_available = False
    
    # Create fallback classes
    class UserAuth:
        ROLES = ['admin', 'wholesale_reseller', 'customer']

        @staticmethod
        def hash_password(password):
            return "dummy_hash"

        @staticmethod
        def verify_password(password, hash):
            return False

        @staticmethod
        def validate_email(email):
            return "@" in email

        @staticmethod
        def validate_password(password):
            return True, "Valid"

        @staticmethod
        def generate_token(data):
            return "dummy_token"

    class SessionManager:
        @staticmethod
        def create_session(user_id, token):
            return {"user_id": user_id, "token": token}

    class SecurityUtils:
        @staticmethod
        def log_security_event(user_id, event, data):
            pass

    class UserModel:
        def create_user(self, data):
            return data

        def update_login(self, user_id):
            return {"last_login": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}

    class CustomerModel:
        def create_customer(self, data):
            return data

    class ResellerModel:
        def create_reseller(self, data):
            return data

    # Initialize dummy objects
    user_model = UserModel()
    customer_model = CustomerModel()
    reseller_model = ResellerModel()
    users_db = {}
    customers_db = {}
    resellers_db = {}
    sessions_db = {}

@user_auth_bp.route('/register', methods=['POST'])
def register():
    """Register new user"""
    service_checker = ServiceChecker()
    
    if not service_checker.user_management_available:
        return jsonify({'error': 'User management not available'}), 503

    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['email', 'password', 'role']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400

        email = data.get('email').lower().strip()
        password = data.get('password')
        role = data.get('role')

        # Validate email format
        if not UserAuth.validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400

        # Validate password strength
        valid_password, password_message = UserAuth.validate_password(password)
        if not valid_password:
            return jsonify({'error': password_message}), 400

        # Validate role
        if role not in UserAuth.ROLES:
            return jsonify({'error': 'Invalid role'}), 400

        # Check if user already exists
        existing_user = next((u for u in users_db.values()
                             if u.get('email') == email), None)
        if existing_user:
            return jsonify({'error': 'User already exists'}), 409

        # Create new user
        user_id = str(uuid.uuid4())
        password_hash = UserAuth.hash_password(password)

        user_data = {
            'id': user_id,
            'email': email,
            'password_hash': password_hash,
            'role': role,
            'profile': data.get('profile', {})
        }

        new_user = user_model.create_user(user_data)
        users_db[user_id] = new_user

        # Create additional profiles based on role
        if role == 'wholesale_reseller':
            reseller_id = str(uuid.uuid4())
            reseller_data = {
                'id': reseller_id,
                'user_id': user_id,
                'business_name': data.get('business_name', ''),
                'license_number': data.get('license_number', ''),
                'license_state': data.get('license_state', ''),
                'phone': data.get('phone', ''),
                'email': email
            }
            reseller_profile = reseller_model.create_reseller(reseller_data)
            resellers_db[reseller_id] = reseller_profile

        elif role == 'customer':
            customer_id = str(uuid.uuid4())
            customer_data = {
                'id': customer_id,
                'user_id': user_id,
                'first_name': data.get('first_name', ''),
                'last_name': data.get('last_name', ''),
                'email': email,
                'phone': data.get('phone', '')
            }
            customer_profile = customer_model.create_customer(customer_data)
            customers_db[customer_id] = customer_profile

        # Generate token
        token = UserAuth.generate_token({
            'id': user_id,
            'email': email,
            'role': role
        })

        # Create session
        session_data = SessionManager.create_session(user_id, token)
        sessions_db[user_id] = session_data

        # Log security event
        SecurityUtils.log_security_event(
            user_id, 'user_registered', {'role': role})

        return jsonify({
            'message': 'User registered successfully',
            'user': {
                'id': user_id,
                'email': email,
                'role': role,
                'profile': new_user.get('profile', {})
            },
            'token': token
        }), 201

    except Exception as e:
        return jsonify({'error': f'Registration failed: {str(e)}'}), 500

@user_auth_bp.route('/login', methods=['POST'])
def login():
    """User login"""
    service_checker = ServiceChecker()
    
    if not service_checker.user_management_available:
        return jsonify({'error': 'User management not available'}), 503

    try:
        data = request.get_json()

        email = data.get('email', '').lower().strip()
        password = data.get('password', '')

        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400

        # Find user by email
        user = next((u for u in users_db.values()
                    if u.get('email') == email), None)
        if not user:
            SecurityUtils.log_security_event(
                None, 'login_failed', {'email': email, 'reason': 'user_not_found'})
            return jsonify({'error': 'Invalid credentials'}), 401

        # Verify password
        if not UserAuth.verify_password(password, user.get('password_hash')):
            SecurityUtils.log_security_event(user.get('id'), 'login_failed', {
                                             'reason': 'invalid_password'})
            return jsonify({'error': 'Invalid credentials'}), 401

        # Check user status
        if user.get('status') != 'active':
            return jsonify({'error': 'Account is not active'}), 403

        # Update login information
        user_id = user.get('id')
        login_update = user_model.update_login(user_id)
        users_db[user_id].update({
            'last_login': login_update['last_login'],
            'updated_at': login_update['updated_at']
        })

        # Generate token
        token = UserAuth.generate_token({
            'id': user_id,
            'email': email,
            'role': user.get('role')
        })

        # Create/update session
        session_data = SessionManager.create_session(user_id, token)
        sessions_db[user_id] = session_data

        # Log successful login
        SecurityUtils.log_security_event(user_id, 'login_success', {
                                         'role': user.get('role')})

        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': user_id,
                'email': email,
                'role': user.get('role'),
                'profile': user.get('profile', {}),
                'last_login': user.get('last_login')
            },
            'token': token
        })

    except Exception as e:
        return jsonify({'error': f'Login failed: {str(e)}'}), 500

@user_auth_bp.route('/logout', methods=['POST'])
@token_required
def logout():
    """User logout"""
    try:
        user_id = request.current_user.get('user_id')

        # Remove session
        if user_id in sessions_db:
            del sessions_db[user_id]

        # Log logout
        SecurityUtils.log_security_event(user_id, 'logout', {})

        return jsonify({'message': 'Logout successful'})

    except Exception as e:
        return jsonify({'error': f'Logout failed: {str(e)}'}), 500

@user_auth_bp.route('/profile', methods=['GET'])
@token_required
def get_profile():
    """Get user profile"""
    try:
        user_id = request.current_user.get('user_id')
        user = users_db.get(user_id)

        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Get additional profile data based on role
        additional_data = {}
        role = user.get('role')

        if role == 'wholesale_reseller':
            reseller = next((r for r in resellers_db.values()
                            if r.get('user_id') == user_id), None)
            if reseller:
                additional_data['reseller_profile'] = reseller

        elif role == 'customer':
            customer = next((c for c in customers_db.values()
                            if c.get('user_id') == user_id), None)
            if customer:
                additional_data['customer_profile'] = customer

        print(f"User profile accessed: {user_id} ({role})")
        return jsonify({
            'user': {
                'id': user_id,
                'email': user.get('email'),
                'role': role,
                'profile': user.get('profile', {}),
                'status': user.get('status'),
                'created_at': user.get('created_at'),
                'last_login': user.get('last_login')
            },
            **additional_data
        })

    except Exception as e:
        return jsonify({'error': f'Failed to get profile: {str(e)}'}), 500

@user_auth_bp.route('/profile', methods=['PUT'])
@token_required
def update_profile():
    """Update user profile"""
    try:
        user_id = request.current_user.get('user_id')
        user = users_db.get(user_id)

        if not user:
            return jsonify({'error': 'User not found'}), 404

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Profile data is required'}), 400

        # Update basic profile information
        profile_updates = {}
        allowed_fields = ['first_name', 'last_name', 'phone', 'company', 'address']
        
        for field in allowed_fields:
            if field in data:
                profile_updates[field] = data[field]

        if profile_updates:
            # Update user profile
            if 'profile' not in users_db[user_id]:
                users_db[user_id]['profile'] = {}
            users_db[user_id]['profile'].update(profile_updates)
            users_db[user_id]['updated_at'] = datetime.now(timezone.utc).isoformat()

        # Update role-specific profiles
        role = user.get('role')
        
        if role == 'wholesale_reseller':
            reseller = next((r for r in resellers_db.values()
                            if r.get('user_id') == user_id), None)
            if reseller:
                reseller_updates = {}
                reseller_fields = ['business_name', 'license_number', 'license_state', 'business_type']
                
                for field in reseller_fields:
                    if field in data:
                        reseller_updates[field] = data[field]
                
                if reseller_updates:
                    reseller_id = reseller['id']
                    resellers_db[reseller_id].update(reseller_updates)
                    resellers_db[reseller_id]['updated_at'] = datetime.now(timezone.utc).isoformat()

        elif role == 'customer':
            customer = next((c for c in customers_db.values()
                            if c.get('user_id') == user_id), None)
            if customer:
                customer_updates = {}
                customer_fields = ['first_name', 'last_name', 'phone']
                
                for field in customer_fields:
                    if field in data:
                        customer_updates[field] = data[field]
                
                if customer_updates:
                    customer_id = customer['id']
                    customers_db[customer_id].update(customer_updates)
                    customers_db[customer_id]['updated_at'] = datetime.now(timezone.utc).isoformat()

        # Log profile update
        SecurityUtils.log_security_event(user_id, 'profile_updated', {
            'fields_updated': list(profile_updates.keys())
        })

        return jsonify({
            'message': 'Profile updated successfully',
            'updated_fields': list(profile_updates.keys())
        })

    except Exception as e:
        return jsonify({'error': f'Failed to update profile: {str(e)}'}), 500

@user_auth_bp.route('/change-password', methods=['PUT'])
@token_required
def change_password():
    """Change user password"""
    try:
        user_id = request.current_user.get('user_id')
        user = users_db.get(user_id)

        if not user:
            return jsonify({'error': 'User not found'}), 404

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Password data is required'}), 400

        current_password = data.get('current_password')
        new_password = data.get('new_password')

        if not current_password or not new_password:
            return jsonify({'error': 'Current password and new password are required'}), 400

        # Verify current password
        if not UserAuth.verify_password(current_password, user.get('password_hash')):
            SecurityUtils.log_security_event(user_id, 'password_change_failed', {
                'reason': 'invalid_current_password'
            })
            return jsonify({'error': 'Current password is incorrect'}), 401

        # Validate new password
        valid_password, password_message = UserAuth.validate_password(new_password)
        if not valid_password:
            return jsonify({'error': password_message}), 400

        # Update password
        new_password_hash = UserAuth.hash_password(new_password)
        users_db[user_id]['password_hash'] = new_password_hash
        users_db[user_id]['updated_at'] = datetime.now(timezone.utc).isoformat()

        # Log password change
        SecurityUtils.log_security_event(user_id, 'password_changed', {})

        return jsonify({
            'message': 'Password changed successfully'
        })

    except Exception as e:
        return jsonify({'error': f'Failed to change password: {str(e)}'}), 500

@user_auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    """Initiate password reset process"""
    try:
        data = request.get_json()
        if not data or not data.get('email'):
            return jsonify({'error': 'Email is required'}), 400

        email = data.get('email').lower().strip()

        # Find user by email
        user = next((u for u in users_db.values()
                    if u.get('email') == email), None)
        
        # Always return success to prevent email enumeration
        if user:
            # In production, send reset email here
            SecurityUtils.log_security_event(user.get('id'), 'password_reset_requested', {
                'email': email
            })
            
            # Generate reset token (in production, store this securely)
            reset_token = str(uuid.uuid4())
            
            # Store reset token with expiration (in production, use database)
            # For now, just log it for testing
            print(f"Password reset token for {email}: {reset_token}")

        return jsonify({
            'message': 'If an account exists with that email, a password reset link has been sent'
        })

    except Exception as e:
        return jsonify({'error': f'Password reset request failed: {str(e)}'}), 500

@user_auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """Reset password with token"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Reset data is required'}), 400

        reset_token = data.get('reset_token')
        new_password = data.get('new_password')
        email = data.get('email', '').lower().strip()

        if not all([reset_token, new_password, email]):
            return jsonify({'error': 'Reset token, new password, and email are required'}), 400

        # Validate new password
        valid_password, password_message = UserAuth.validate_password(new_password)
        if not valid_password:
            return jsonify({'error': password_message}), 400

        # Find user by email
        user = next((u for u in users_db.values()
                    if u.get('email') == email), None)
        
        if not user:
            return jsonify({'error': 'Invalid reset token'}), 400

        # In production, verify reset token validity and expiration
        # For now, accept any token for testing
        
        # Update password
        new_password_hash = UserAuth.hash_password(new_password)
        user_id = user.get('id')
        users_db[user_id]['password_hash'] = new_password_hash
        users_db[user_id]['updated_at'] = datetime.now(timezone.utc).isoformat()

        # Log password reset
        SecurityUtils.log_security_event(user_id, 'password_reset_completed', {})

        return jsonify({
            'message': 'Password reset successfully'
        })

    except Exception as e:
        return jsonify({'error': f'Password reset failed: {str(e)}'}), 500

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
                return jsonify({'error': 'Token is required'}), 400

        # In production, verify JWT token
        # For now, just check if it's in our sessions
        user_session = next((session for session in sessions_db.values()
                            if session.get('token') == token), None)
        
        if user_session:
            user_id = user_session.get('user_id')
            user = users_db.get(user_id)
            
            if user and user.get('status') == 'active':
                return jsonify({
                    'valid': True,
                    'user': {
                        'id': user_id,
                        'email': user.get('email'),
                        'role': user.get('role'),
                        'profile': user.get('profile', {})
                    }
                })

        return jsonify({'valid': False, 'error': 'Invalid or expired token'}), 401

    except Exception as e:
        return jsonify({'error': f'Token verification failed: {str(e)}'}), 500

@user_auth_bp.route('/sessions', methods=['GET'])
@token_required
@role_required('admin')
def get_active_sessions():
    """Get active user sessions (admin only)"""
    try:
        active_sessions = []
        
        for session in sessions_db.values():
            user_id = session.get('user_id')
            user = users_db.get(user_id)
            
            if user:
                active_sessions.append({
                    'user_id': user_id,
                    'email': user.get('email'),
                    'role': user.get('role'),
                    'last_login': user.get('last_login'),
                    'session_created': session.get('created_at', 'unknown')
                })

        return jsonify({
            'active_sessions': active_sessions,
            'total_sessions': len(active_sessions)
        })

    except Exception as e:
        return jsonify({'error': f'Failed to get sessions: {str(e)}'}), 500

@user_auth_bp.route('/sessions/<user_id>', methods=['DELETE'])
@token_required
@role_required('admin')
def terminate_user_session(user_id):
    """Terminate user session (admin only)"""
    try:
        if user_id in sessions_db:
            user = users_db.get(user_id)
            user_email = user.get('email', 'unknown') if user else 'unknown'
            
            del sessions_db[user_id]
            
            # Log session termination
            admin_id = request.current_user.get('user_id')
            SecurityUtils.log_security_event(admin_id, 'session_terminated', {
                'target_user': user_id,
                'target_email': user_email
            })
            
            return jsonify({
                'message': f'Session terminated for user {user_email}'
            })
        else:
            return jsonify({'error': 'No active session found for user'}), 404

    except Exception as e:
        return jsonify({'error': f'Failed to terminate session: {str(e)}'}), 500
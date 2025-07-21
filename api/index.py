#!/usr/bin/env python3
"""
ConnectedAutoCare.com - Unified Platform API (Vercel Compatible)
Complete insurance platform with customer API, admin panel, and user management
"""

import os
import sys
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS

# Add the current directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Initialize Flask app at module level for Vercel
app = Flask(__name__)

# Initialize global availability flags
admin_modules_available = False
customer_services_available = False
user_management_available = False

# Import customer-facing services with error handling
try:
    from services.hero_rating_service import HeroRatingService
    from services.vsc_rating_service import VSCRatingService
    from services.vin_decoder_service import VINDecoderService
    from data.hero_products_data import get_hero_products
    from data.vsc_rates_data import get_vsc_coverage_options
    from utils.response_helpers import success_response, error_response
    customer_services_available = True
except ImportError as e:
    customer_services_available = False
    # Create fallback classes to prevent crashes

    class HeroRatingService:
        def generate_quote(self, *args, **kwargs):
            return {"success": False, "error": "Service temporarily unavailable"}

    class VSCRatingService:
        def generate_quote(self, *args, **kwargs):
            return {"success": False, "error": "Service temporarily unavailable"}

    class VINDecoderService:
        def decode_vin(self, *args, **kwargs):
            return {"success": False, "error": "Service temporarily unavailable"}

    def get_hero_products():
        return {}

    def get_vsc_coverage_options():
        return {}

    def success_response(data):
        return {"success": True, "data": data}

    def error_response(message, code=400):
        return {"success": False, "error": message}

# Import admin modules with corrected paths
try:
    from admin.analytics_dashboard import analytics_bp
    from admin.product_management import product_bp
    from admin.contract_management import contract_bp
    from auth.admin_auth import auth_bp
    admin_modules_available = True
except ImportError as e:
    print(f"Admin modules import error: {e}")
    admin_modules_available = False
    # Create dummy blueprints to prevent crashes
    from flask import Blueprint
    auth_bp = Blueprint('auth', __name__)
    product_bp = Blueprint('product', __name__)
    analytics_bp = Blueprint('analytics', __name__)
    contract_bp = Blueprint('contract', __name__)

# Import user management modules with error handling
try:
    from auth.user_auth import UserAuth, token_required, role_required, permission_required, SessionManager, SecurityUtils
    from models.database_models import UserModel, CustomerModel, PolicyModel, TransactionModel, ResellerModel, DatabaseUtils
    from analytics.kpi_system import KPISystem, ReportExporter
    user_management_available = True
except ImportError as e:
    print(f"User management import warning: {e}")
    user_management_available = False
    # Create dummy classes

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

    def token_required(f):
        def wrapper(*args, **kwargs):
            return jsonify({"error": "User management not available"}), 503
        return wrapper

    def role_required(role):
        def decorator(f):
            def wrapper(*args, **kwargs):
                return jsonify({"error": "User management not available"}), 503
            return wrapper
        return decorator

    def permission_required(permission):
        def decorator(f):
            def wrapper(*args, **kwargs):
                return jsonify({"error": "User management not available"}), 503
            return wrapper
        return decorator

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
            return {"last_login": datetime.utcnow().isoformat(), "updated_at": datetime.utcnow().isoformat()}

    class CustomerModel:
        def create_customer(self, data):
            return data

    class PolicyModel:
        pass

    class TransactionModel:
        pass

    class ResellerModel:
        def create_reseller(self, data):
            return data

    class DatabaseUtils:
        @staticmethod
        def get_customer_metrics(customer_id, transactions, policies):
            return {}

    class KPISystem:
        def generate_dashboard_data(self, data):
            return {"message": "KPI system not available"}

        def generate_report(self, report_type, data, date_range=None):
            return {"message": "Report generation not available"}

    class ReportExporter:
        def export_to_csv(self, data, filename):
            return "CSV export not available"

        def export_to_json(self, data):
            return {"message": "JSON export not available"}

# App configuration
app.config.update(
    SECRET_KEY=os.environ.get(
        'SECRET_KEY', 'connectedautocare-unified-secret-2025'),
    DEBUG=False,
    TESTING=False,
    MAX_CONTENT_LENGTH=16 * 1024 * 1024  # 16MB max file size
)

# CORS configuration for all components
ALLOWED_ORIGINS = [
    "https://www.connectedautocare.com",
    "https://connectedautocare.com",
    "https://api.connectedautocare.com",
    "https://admin.connectedautocare.com",
    "https://portal.connectedautocare.com",
    "http://localhost:5173",  # Local development
    "http://127.0.0.1:5173",  # Local development
]

# Configure CORS
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True,
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

# Enhanced CORS handling for production


@app.after_request
def after_request(response):
    origin = request.headers.get('Origin')

    if origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
    elif origin is None:
        response.headers['Access-Control-Allow-Origin'] = '*'

    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,X-Requested-With'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Max-Age'] = '3600'

    return response


@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = make_response()
        origin = request.headers.get('Origin')

        if origin in ALLOWED_ORIGINS:
            response.headers['Access-Control-Allow-Origin'] = origin
        else:
            response.headers['Access-Control-Allow-Origin'] = '*'

        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,X-Requested-With'
        response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age'] = '3600'

        return response


# Initialize services
if customer_services_available:
    hero_service = HeroRatingService()
    vsc_service = VSCRatingService()
    vin_service = VINDecoderService()
else:
    hero_service = HeroRatingService()
    vsc_service = VSCRatingService()
    vin_service = VINDecoderService()

# Initialize user management components if available
if user_management_available:
    user_model = UserModel()
    customer_model = CustomerModel()
    policy_model = PolicyModel()
    transaction_model = TransactionModel()
    reseller_model = ResellerModel()
    kpi_system = KPISystem()
    report_exporter = ReportExporter()

    # Initialize in-memory databases
    users_db = {}
    customers_db = {}
    policies_db = {}
    transactions_db = {}
    resellers_db = {}
    sessions_db = {}

    # Initialize sample data for user management
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
else:
    # Initialize dummy objects for when user management is not available
    user_model = UserModel()
    customer_model = CustomerModel()
    policy_model = PolicyModel()
    transaction_model = TransactionModel()
    reseller_model = ResellerModel()
    kpi_system = KPISystem()
    report_exporter = ReportExporter()

    users_db = {}
    customers_db = {}
    policies_db = {}
    transactions_db = {}
    resellers_db = {}
    sessions_db = {}

# ================================
# HEALTH CHECK ENDPOINTS
# ================================


@app.route('/')
@app.route('/health')
def health_check():
    """Main health check endpoint"""
    return jsonify({
        "service": "ConnectedAutoCare Unified Platform",
        "status": "healthy",
        "version": "3.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "environment": "production",
        "components": {
            "customer_api": "available" if customer_services_available else "unavailable",
            "admin_panel": "available" if admin_modules_available else "unavailable",
            "user_management": "available" if user_management_available else "unavailable"
        },
        "features": [
            "Hero Products & Quotes",
            "VSC Rating Engine",
            "VIN Decoder",
            "Multi-tier Authentication",
            "Customer Database",
            "Wholesale Reseller Portal",
            "KPI Analytics",
            "Admin Panel"
        ]
    })


@app.route('/api/health')
def api_health():
    """Comprehensive API health check"""
    return jsonify({
        "api_status": "healthy",
        "customer_services": {
            "hero_products": "available" if customer_services_available else "unavailable",
            "vsc_rating": "available" if customer_services_available else "unavailable",
            "vin_decoder": "available" if customer_services_available else "unavailable"
        },
        "admin_services": {
            "authentication": "available" if admin_modules_available else "unavailable",
            "product_management": "available" if admin_modules_available else "unavailable",
            "analytics": "available" if admin_modules_available else "unavailable",
            "contracts": "available" if admin_modules_available else "unavailable"
        },
        "user_management": {
            "authentication": "available" if user_management_available else "unavailable",
            "customer_portal": "available" if user_management_available else "unavailable",
            "reseller_portal": "available" if user_management_available else "unavailable",
            "analytics": "available" if user_management_available else "unavailable"
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })

# ================================
# CUSTOMER API ENDPOINTS
# ================================

# Hero Products API


@app.route('/api/hero/health')
def hero_health():
    """Hero products service health check"""
    if not customer_services_available:
        return jsonify({"error": "Hero products service not available"}), 503

    try:
        products = get_hero_products()
        return jsonify({
            "service": "Hero Products API",
            "status": "healthy",
            "products_available": len(products),
            "categories": list(products.keys()) if products else [],
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
    except Exception as e:
        return jsonify({"error": f"Hero service error: {str(e)}"}), 500


@app.route('/api/hero/products')
def get_all_hero_products():
    """Get all Hero products with pricing information"""
    if not customer_services_available:
        return jsonify({"error": "Hero products service not available"}), 503

    try:
        products = get_hero_products()
        return jsonify(success_response(products))
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve products: {str(e)}"}), 500


@app.route('/api/hero/products/<category>')
def get_hero_products_by_category(category):
    """Get Hero products by category"""
    if not customer_services_available:
        return jsonify({"error": "Hero products service not available"}), 503

    try:
        all_products = get_hero_products()
        if category not in all_products:
            return jsonify({"error": f"Category '{category}' not found"}), 404

        return jsonify(success_response({
            "category": category,
            "products": all_products[category]
        }))
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve category: {str(e)}"}), 500


@app.route('/api/hero/quote', methods=['POST'])
def generate_hero_quote():
    """Generate quote for Hero products"""
    if not customer_services_available:
        return jsonify({"error": "Hero products service not available"}), 503

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400

        # Validate required fields
        required_fields = ['product_type', 'term_years']
        missing_fields = [
            field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

        # Generate quote
        quote_result = hero_service.generate_quote(
            product_type=data['product_type'],
            term_years=data['term_years'],
            coverage_limit=data.get('coverage_limit', 500),
            customer_type=data.get('customer_type', 'retail'),
            state=data.get('state', 'FL'),
            zip_code=data.get('zip_code', '33101')
        )

        if quote_result.get('success'):
            return jsonify(success_response(quote_result))
        else:
            return jsonify({"error": quote_result.get('error', 'Quote generation failed')}), 400

    except Exception as e:
        return jsonify({"error": f"Quote generation error: {str(e)}"}), 500

# VSC Rating API


@app.route('/api/vsc/health')
def vsc_health():
    """VSC rating service health check"""
    if not customer_services_available:
        return jsonify({"error": "VSC rating service not available"}), 503

    try:
        coverage_options = get_vsc_coverage_options()
        return jsonify({
            "service": "VSC Rating API",
            "status": "healthy",
            "coverage_levels": list(coverage_options.keys()) if coverage_options else [],
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
    except Exception as e:
        return jsonify({"error": f"VSC service error: {str(e)}"}), 500


@app.route('/api/vsc/coverage-options')
def get_vsc_coverage():
    """Get available VSC coverage options"""
    if not customer_services_available:
        return jsonify({"error": "VSC rating service not available"}), 503

    try:
        options = get_vsc_coverage_options()
        return jsonify(success_response(options))
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve coverage options: {str(e)}"}), 500


@app.route('/api/vsc/quote', methods=['POST'])
def generate_vsc_quote():
    """Generate VSC quote based on vehicle information"""
    if not customer_services_available:
        return jsonify({"error": "VSC rating service not available"}), 503

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400

        # Validate required fields
        required_fields = ['make', 'year', 'mileage']
        missing_fields = [
            field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

        # Generate quote
        quote_result = vsc_service.generate_quote(
            make=data['make'],
            model=data.get('model', ''),
            year=int(data['year']),
            mileage=int(data['mileage']),
            coverage_level=data.get('coverage_level', 'gold'),
            term_months=data.get('term_months', 36),
            deductible=data.get('deductible', 100),
            customer_type=data.get('customer_type', 'retail')
        )

        if quote_result.get('success'):
            return jsonify(success_response(quote_result))
        else:
            return jsonify({"error": quote_result.get('error', 'VSC quote generation failed')}), 400

    except ValueError as e:
        return jsonify({"error": f"Invalid input data: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": f"VSC quote error: {str(e)}"}), 500

# VIN Decoder API


@app.route('/api/vin/health')
def vin_health():
    """VIN decoder service health check"""
    return jsonify({
        "service": "VIN Decoder API",
        "status": "healthy" if customer_services_available else "unavailable",
        "supported_formats": ["17-character VIN"],
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })


@app.route('/api/vin/validate', methods=['POST'])
def validate_vin():
    """Validate VIN format"""
    try:
        data = request.get_json()
        if not data or 'vin' not in data:
            return jsonify({"error": "VIN is required"}), 400

        vin = data['vin'].strip().upper()

        # Basic VIN validation
        if len(vin) != 17:
            return jsonify({"error": "VIN must be exactly 17 characters"}), 400

        if not vin.isalnum():
            return jsonify({"error": "VIN must contain only letters and numbers"}), 400

        # Check for invalid characters (I, O, Q not allowed in VIN)
        invalid_chars = set('IOQ') & set(vin)
        if invalid_chars:
            return jsonify({"error": f"VIN contains invalid characters: {', '.join(invalid_chars)}"}), 400

        return jsonify(success_response({
            "vin": vin,
            "valid": True,
            "format": "valid"
        }))

    except Exception as e:
        return jsonify({"error": f"VIN validation error: {str(e)}"}), 500


@app.route('/api/vin/decode', methods=['POST'])
def decode_vin():
    """Decode VIN to extract vehicle information"""
    if not customer_services_available:
        return jsonify({"error": "VIN decoder service not available"}), 503

    try:
        data = request.get_json()
        if not data or 'vin' not in data:
            return jsonify({"error": "VIN is required"}), 400

        vin = data['vin'].strip().upper()

        # Validate VIN first
        if len(vin) != 17:
            return jsonify({"error": "Invalid VIN length"}), 400

        # Decode VIN
        decode_result = vin_service.decode_vin(vin)

        if decode_result.get('success'):
            return jsonify(success_response(decode_result['vehicle_info']))
        else:
            return jsonify({"error": decode_result.get('error', 'VIN decode failed')}), 400

    except Exception as e:
        return jsonify({"error": f"VIN decode error: {str(e)}"}), 500

# Payment and Contract Endpoints (always available)


@app.route('/api/payments/methods')
def get_payment_methods():
    """Get available payment methods"""
    return jsonify(success_response({
        "credit_card": {
            "enabled": True,
            "providers": ["Helcim"],
            "accepted_cards": ["Visa", "MasterCard", "American Express", "Discover"]
        },
        "financing": {
            "enabled": True,
            "provider": "Supplemental Payment Program",
            "terms": ["0% for 12 months", "0% for 24 months"]
        }
    }))


@app.route('/api/contracts/generate', methods=['POST'])
def generate_contract():
    """Generate contract for purchased product"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Contract data is required"}), 400

        # Placeholder response
        return jsonify(success_response({
            "contract_id": f"CAC-{datetime.utcnow().strftime('%Y%m%d')}-001",
            "status": "generated",
            "message": "Contract generation feature coming soon"
        }))

    except Exception as e:
        return jsonify({"error": f"Contract generation error: {str(e)}"}), 500

# ================================
# USER MANAGEMENT ENDPOINTS
# ================================

# Authentication Endpoints


@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register new user"""
    if not user_management_available:
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


@app.route('/api/auth/login', methods=['POST'])
def login():
    """User login"""
    if not user_management_available:
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


@app.route('/api/auth/logout', methods=['POST'])
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


@app.route('/api/auth/profile', methods=['GET'])
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

# Customer Management Endpoints


@app.route('/api/customers', methods=['GET'])
@token_required
@permission_required('manage_customers')
def get_customers():
    """Get all customers (admin and resellers only)"""
    try:
        user_role = request.current_user.get('role')
        user_id = request.current_user.get('user_id')

        customers_list = list(customers_db.values())

        # If reseller, only show their customers
        if user_role == 'wholesale_reseller':
            # In a real system, you'd filter by assigned agent or created_by
            pass

        # Add user information to each customer
        for customer in customers_list:
            customer_user_id = customer.get('user_id')
            user_info = users_db.get(customer_user_id, {})
            customer['user_info'] = {
                'email': user_info.get('email'),
                'status': user_info.get('status'),
                'last_login': user_info.get('last_login')
            }

        return jsonify({
            'customers': customers_list,
            'total': len(customers_list)
        })

    except Exception as e:
        return jsonify({'error': f'Failed to get customers: {str(e)}'}), 500


@app.route('/api/customers/<customer_id>', methods=['GET'])
@token_required
@permission_required('manage_customers')
def get_customer(customer_id):
    """Get specific customer details"""
    try:
        customer = customers_db.get(customer_id)
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404

        # Get user information
        user_info = users_db.get(customer.get('user_id'), {})
        customer['user_info'] = user_info

        # Get customer policies
        customer_policies = [p for p in policies_db.values() if p.get(
            'customer_id') == customer_id]
        customer['policies'] = customer_policies

        # Get customer transactions
        customer_transactions = [
            t for t in transactions_db.values() if t.get('customer_id') == customer_id]
        customer['transactions'] = customer_transactions

        # Calculate metrics
        metrics = DatabaseUtils.get_customer_metrics(
            customer_id, customer_transactions, customer_policies)
        customer['metrics'] = metrics

        return jsonify({'customer': customer})

    except Exception as e:
        return jsonify({'error': f'Failed to get customer: {str(e)}'}), 500

# Analytics and Reporting Endpoints


@app.route('/api/analytics/dashboard', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def get_dashboard():
    """Get analytics dashboard data"""
    try:
        # Prepare data for analytics
        data = {
            'transactions': list(transactions_db.values()),
            'customers': list(customers_db.values()),
            'policies': list(policies_db.values()),
            'resellers': list(resellers_db.values())
        }

        # Generate dashboard data
        dashboard_data = kpi_system.generate_dashboard_data(data)

        return jsonify(dashboard_data)

    except Exception as e:
        return jsonify({'error': f'Failed to generate dashboard: {str(e)}'}), 500


@app.route('/api/analytics/customer-dashboard', methods=['GET'])
@token_required
@role_required('customer')  # Allows customers and above
def get_customer_dashboard():
    """Customer-specific dashboard with limited data"""
    try:
        customer_user_id = request.current_user.get('user_id')
        
        # Filter data to only show customer's own information
        customer_transactions = [t for t in transactions_db.values() 
                               if t.get('customer_id') == customer_user_id]
        customer_policies = [p for p in policies_db.values() 
                           if p.get('customer_id') == customer_user_id]
        
        # Return limited dashboard data
        return jsonify({
            'customer_metrics': {
                'total_policies': len(customer_policies),
                'active_policies': len([p for p in customer_policies if p.get('status') == 'active']),
                'total_spent': sum(t.get('amount', 0) for t in customer_transactions if t.get('status') == 'completed')
            }
        })
    except Exception as e:
        return jsonify({'error': f'Failed to generate customer dashboard: {str(e)}'}), 500


@app.route('/api/analytics/reports/<report_type>', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def generate_report(report_type):
    """Generate specific business report"""
    try:
        # Get date range from query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        date_range = None
        if start_date and end_date:
            date_range = {'start': start_date, 'end': end_date}

        # Prepare data for analytics
        data = {
            'transactions': list(transactions_db.values()),
            'customers': list(customers_db.values()),
            'policies': list(policies_db.values()),
            'resellers': list(resellers_db.values())
        }

        # Generate report
        report_data = kpi_system.generate_report(report_type, data, date_range)

        return jsonify(report_data)

    except Exception as e:
        return jsonify({'error': f'Failed to generate report: {str(e)}'}), 500


@app.route('/api/analytics/export/<report_type>', methods=['GET'])
@token_required
@role_required('wholesale_reseller')
def export_report(report_type):
    """Export report in specified format"""
    try:
        export_format = request.args.get('format', 'json')

        # Generate report data
        data = {
            'transactions': list(transactions_db.values()),
            'customers': list(customers_db.values()),
            'policies': list(policies_db.values()),
            'resellers': list(resellers_db.values())
        }

        report_data = kpi_system.generate_report(report_type, data)

        # Export in requested format
        if export_format == 'csv':
            csv_content = report_exporter.export_to_csv(
                report_data, f'{report_type}_report.csv')
            return csv_content, 200, {'Content-Type': 'text/csv'}
        elif export_format == 'json':
            json_content = report_exporter.export_to_json(report_data)
            return json_content, 200, {'Content-Type': 'application/json'}
        else:
            return jsonify({'error': 'Unsupported export format'}), 400

    except Exception as e:
        return jsonify({'error': f'Failed to export report: {str(e)}'}), 500

# Admin Endpoints


@app.route('/api/admin/users', methods=['GET'])
@token_required
@role_required('admin')
def get_all_users():
    """Get all users (admin only)"""
    try:
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
            'total': len(users_list)
        })

    except Exception as e:
        return jsonify({'error': f'Failed to get users: {str(e)}'}), 500


@app.route('/api/admin/users/<user_id>/status', methods=['PUT'])
@token_required
@role_required('admin')
def update_user_status(user_id):
    """Update user status (admin only)"""
    try:
        data = request.get_json()
        new_status = data.get('status')

        if new_status not in ['active', 'inactive', 'suspended']:
            return jsonify({'error': 'Invalid status'}), 400

        user = users_db.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        user['status'] = new_status
        user['updated_at'] = datetime.utcnow().isoformat()

        # Log admin action
        admin_id = request.current_user.get('user_id')
        SecurityUtils.log_security_event(admin_id, 'user_status_changed', {
            'target_user': user_id,
            'new_status': new_status
        })

        return jsonify({
            'message': f'User status updated to {new_status}',
            'user': {
                'id': user_id,
                'status': new_status,
                'updated_at': user['updated_at']
            }
        })

    except Exception as e:
        return jsonify({'error': f'Failed to update user status: {str(e)}'}), 500

# ================================
# ADMIN API REGISTRATION
# ================================


# Register admin blueprints if available
if admin_modules_available:
    try:
        app.register_blueprint(auth_bp, url_prefix='/api/admin/auth')
        app.register_blueprint(product_bp, url_prefix='/api/admin/products')
        app.register_blueprint(analytics_bp, url_prefix='/api/admin/analytics')
        app.register_blueprint(contract_bp, url_prefix='/api/admin/contracts')
    except Exception as e:
        print(f"Error registering admin blueprints: {e}")
        admin_modules_available = False

# Admin health check endpoints


@app.route('/api/admin/health', methods=['GET'])
def admin_health():
    """Admin-specific health check"""
    if not admin_modules_available:
        return jsonify({
            'success': False,
            'error': 'Admin modules not available'
        }), 503

    return jsonify({
        'success': True,
        'message': 'Admin panel is operational',
        'features': [
            'Product Management',
            'Pricing Control',
            'Contract Templates',
            'Analytics Dashboard',
            'User Management',
            'System Settings'
        ]
    })

# ================================
# ERROR HANDLERS
# ================================


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    available_endpoints = {
        'customer_api': [
            '/api/hero/products',
            '/api/vsc/quote',
            '/api/vin/decode',
            '/api/payments/methods'
        ] if customer_services_available else ['Customer API not available'],
        'admin_api': [
            '/api/admin/auth/login',
            '/api/admin/products',
            '/api/admin/analytics',
            '/api/admin/contracts'
        ] if admin_modules_available else ['Admin API not available'],
        'user_management': [
            '/api/auth/login',
            '/api/auth/register',
            '/api/customers',
            '/api/analytics/dashboard'
        ] if user_management_available else ['User management not available']
    }

    return jsonify({
        'success': False,
        'error': 'Endpoint not found',
        'available_endpoints': available_endpoints
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors"""
    return jsonify({"success": False, "error": "Method not allowed"}), 405


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({"success": False, "error": "Internal server error"}), 500


# For local development only
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

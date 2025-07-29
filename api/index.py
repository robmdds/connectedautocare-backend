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
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.utils import secure_filename
from PIL import Image
import io
import requests
import json

# Database configuration
DATABASE_URL = os.environ.get(
    'DATABASE_URL', 'postgres://neondb_owner:npg_qH6nhmdrSFL1@ep-tiny-water-adje4r08-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require')

VERCEL_BLOB_READ_WRITE_TOKEN = os.environ.get(
    'BLOB_READ_WRITE_TOKEN', "vercel_blob_rw_NyJGOwmGasD868JR_SRRTKZEvjyrFPjJKXt8v4HwARx9Qmy")

# Add the current directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Configure upload settings
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'webm', 'mov', 'avi'}
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
MAX_VIDEO_SIZE = 100 * 1024 * 1024  # 100MB
MAX_IMAGE_SIZE = 10 * 1024 * 1024   # 10MB


def allowed_file(filename, file_type='video'):
    """Check if file type is allowed"""
    if not filename or '.' not in filename:
        return False

    extension = filename.rsplit('.', 1)[1].lower()

    if file_type == 'video':
        return extension in ALLOWED_VIDEO_EXTENSIONS
    elif file_type == 'image':
        return extension in ALLOWED_IMAGE_EXTENSIONS
    return False


def validate_file_size(file, file_type):
    """Validate file size"""
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    max_size = MAX_VIDEO_SIZE if file_type == 'video' else MAX_IMAGE_SIZE

    if file_size > max_size:
        max_mb = max_size / (1024 * 1024)
        return False, f"File too large. Maximum size: {max_mb}MB"

    return True, "File size OK"


def optimize_image(file):
    """Optimize image for web delivery"""
    try:
        image = Image.open(file)

        # Convert to RGB if necessary
        if image.mode in ('RGBA', 'P'):
            image = image.convert('RGB')

        # Resize if too large (max 1920x1080 for thumbnails)
        max_width, max_height = 1920, 1080
        if image.width > max_width or image.height > max_height:
            image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

        # Save optimized version
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)

        return output
    except Exception as e:
        print(f"Image optimization failed: {e}")
        file.seek(0)
        return file


def upload_to_vercel_blob(file, file_type, filename_prefix="hero"):
    """Upload file to Vercel Blob Storage"""
    try:
        if not VERCEL_BLOB_READ_WRITE_TOKEN:
            return {'success': False, 'error': 'Vercel Blob token not configured'}

        # Generate unique filename
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]

        # Get file extension safely
        if hasattr(file, 'filename') and file.filename and '.' in file.filename:
            file_extension = file.filename.rsplit('.', 1)[1].lower()
        else:
            file_extension = 'mp4' if file_type == 'video' else 'jpg'

        filename = f"{filename_prefix}_{file_type}_{timestamp}_{unique_id}.{file_extension}"

        # Vercel Blob API endpoint
        url = f"https://blob.vercel-storage.com/{filename}"

        # Get content type
        content_type = getattr(file, 'content_type', None)
        if not content_type:
            if file_type == 'video':
                content_type = f'video/{file_extension}'
            else:
                content_type = f'image/{file_extension}'

        # Prepare headers
        headers = {
            'Authorization': f'Bearer {VERCEL_BLOB_READ_WRITE_TOKEN}',
            'X-Content-Type': content_type
        }

        # Read file content
        file_content = file.read()
        file.seek(0)  # Reset file pointer

        # Upload to Vercel Blob
        response = requests.put(url, data=file_content,
                                headers=headers, timeout=60)

        if response.status_code in [200, 201]:
            result = response.json()
            return {
                'success': True,
                'url': result.get('url', url),
                'filename': filename,
                'size': len(file_content)
            }
        else:
            return {
                'success': False,
                'error': f'Upload failed: HTTP {response.status_code} - {response.text}'
            }

    except Exception as e:
        import traceback
        print(f"Vercel Blob upload error: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return {'success': False, 'error': f'Upload error: {str(e)}'}


def delete_from_vercel_blob(file_url):
    """Delete file from Vercel Blob Storage"""
    try:
        if not VERCEL_BLOB_READ_WRITE_TOKEN:
            return {'success': False, 'error': 'Vercel Blob token not configured'}

        headers = {
            'Authorization': f'Bearer {VERCEL_BLOB_READ_WRITE_TOKEN}'
        }

        response = requests.delete(file_url, headers=headers)

        return {
            'success': response.status_code in [200, 204],
            'status_code': response.status_code
        }

    except Exception as e:
        return {'success': False, 'error': str(e)}


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

try:
    from services.enhanced_vin_decoder_service import EnhancedVINDecoderService
    enhanced_vin_service = EnhancedVINDecoderService()
    enhanced_vin_available = True
except ImportError as e:
    print(f"Enhanced VIN service not available: {e}")
    enhanced_vin_available = False

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
        "service": "ConnectedAutoCare Unified Platform with VIN Auto-Detection",
        "status": "healthy",
        "version": "4.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "environment": "production",
        "components": {
            "customer_api": "available" if customer_services_available else "unavailable",
            "admin_panel": "available" if admin_modules_available else "unavailable",
            "user_management": "available" if user_management_available else "unavailable",
            "enhanced_vin_decoder": "available" if enhanced_vin_available else "basic_only"
        },
        "features": [
            "Hero Products & Quotes",
            "VSC Rating Engine with VIN Auto-Detection",
            "Enhanced VIN Decoder with Eligibility Rules",
            "Vehicle Auto-Population",
            "Real-time Eligibility Checking",
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
            "service": "VSC Rating API with VIN Auto-Detection",
            "status": "healthy",
            "coverage_levels": list(coverage_options.keys()) if coverage_options else [],
            "enhanced_features": {
                "vin_auto_detection": enhanced_vin_available,
                "eligibility_checking": enhanced_vin_available,
                "auto_population": enhanced_vin_available
            },
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
    """Generate VSC quote based on vehicle information (enhanced with VIN support)"""
    if not customer_services_available:
        return jsonify({"error": "VSC rating service not available"}), 503

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400

        # Check if this is a VIN-based quote request
        vin = data.get('vin', '').strip().upper()

        # If VIN provided and enhanced service available, try VIN-based approach first
        if vin and enhanced_vin_available:
            try:
                # Decode VIN and populate missing fields
                vin_result = enhanced_vin_service.decode_vin(vin)
                if vin_result.get('success'):
                    vehicle_info = vin_result['vehicle_info']

                    # Use VIN data to fill missing fields
                    if not data.get('make'):
                        data['make'] = vehicle_info.get('make', '')
                    if not data.get('model'):
                        data['model'] = vehicle_info.get('model', '')
                    if not data.get('year'):
                        data['year'] = vehicle_info.get('year', 0)

                    # Mark as auto-populated
                    data['auto_populated'] = True
                    data['vin_decoded'] = vehicle_info
            except Exception as e:
                print(f"VIN decode failed, continuing with manual data: {e}")

        # Validate required fields
        required_fields = ['make', 'year', 'mileage']
        missing_fields = [
            field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

        # Ensure proper data types before sending
        quote_data = {
            'make': data['make'],
            'model': data.get('model', ''),
            'year': int(data['year']),
            'mileage': int(data['mileage']),
            'coverage_level': data.get('coverage_level', 'gold'),
            'term_months': int(data.get('term_months', 36)),
            'deductible': int(data.get('deductible', 100)),
            'customer_type': data.get('customer_type', 'retail')
        }

        response = vsc_service.generate_quote(**quote_data)
        response_data = response if isinstance(
            response, dict) else response[0] if isinstance(response, list) else response

        if response_data.get('success'):
            # Enhance response with VIN information if available
            enhanced_response = response_data.copy()
            if vin:
                enhanced_response['vin_info'] = {
                    'vin': vin,
                    'auto_populated': data.get('auto_populated', False),
                    'vin_decoded': data.get('vin_decoded', {})
                }

            return jsonify(success_response(enhanced_response))
        else:
            return jsonify({"error": response_data.get('error', 'VSC quote generation failed')}), 400

    except ValueError as e:
        return jsonify({"error": f"Invalid input data: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": f"VSC quote error: {str(e)}"}), 500


@app.route('/api/vsc/eligibility', methods=['POST'])
def check_vsc_eligibility():
    """Check VSC eligibility for a vehicle"""
    try:
        data = request.get_json()
        if not data:
            return jsonify(error_response("Vehicle data is required")), 400

        vin = data.get('vin', '').strip().upper()
        make = data.get('make', '').strip()
        year = data.get('year')
        mileage = data.get('mileage')

        try:
            year = int(year) if year else None
            mileage = int(mileage) if mileage else None
        except (ValueError, TypeError):
            return jsonify(error_response("Invalid year or mileage values")), 400

        if not vin and (not make or not year):
            return jsonify(error_response("Either VIN or make/year is required")), 400

        if enhanced_vin_available:
            if vin:
                result = enhanced_vin_service.check_vsc_eligibility(
                    vin=vin, mileage=mileage)
            else:
                result = enhanced_vin_service.check_vsc_eligibility(
                    make=make, year=year, mileage=mileage)
        else:
            # Basic eligibility check fallback
            current_year = datetime.now().year
            vehicle_age = current_year - year if year else 0

            eligible = True
            warnings = []
            restrictions = []

            if vehicle_age > 15:
                eligible = False
                restrictions.append(
                    f"Vehicle is {vehicle_age} years old (maximum 15 years)")
            elif vehicle_age > 10:
                warnings.append(
                    f"Vehicle is {vehicle_age} years old - limited options")

            if mileage and mileage > 150000:
                eligible = False
                restrictions.append(
                    f"Vehicle has {mileage:,} miles (maximum 150,000)")
            elif mileage and mileage > 125000:
                warnings.append(f"High mileage vehicle - premium rates apply")

            result = {
                'success': True,
                'eligible': eligible,
                'warnings': warnings,
                'restrictions': restrictions,
                'vehicle_info': {'make': make, 'year': year, 'mileage': mileage, 'vehicle_age': vehicle_age}
            }

        if result.get('success'):
            return jsonify(success_response(result))
        else:
            return jsonify(error_response(result.get('error', 'Eligibility check failed'))), 400

    except Exception as e:
        return jsonify(error_response(f"Eligibility check error: {str(e)}")), 500


@app.route('/api/vsc/quote/vin', methods=['POST'])
def generate_vsc_quote_from_vin():
    """Generate VSC quote using VIN auto-detection"""
    try:
        data = request.get_json()
        if not data:
            return jsonify(error_response("Quote data is required")), 400

        vin = data.get('vin', '').strip().upper()
        if not vin:
            return jsonify(error_response("VIN is required for VIN-based quoting")), 400

        mileage = data.get('mileage')
        coverage_level = data.get('coverage_level', 'gold')
        term_months = data.get('term_months', 36)
        customer_type = data.get('customer_type', 'retail')
        deductible = data.get('deductible', 100)

        if not mileage:
            return jsonify(error_response("Mileage is required")), 400

        try:
            mileage = int(mileage)
            term_months = int(term_months)
            deductible = int(deductible)
        except (ValueError, TypeError):
            return jsonify(error_response("Invalid numeric values provided")), 400

        # Decode VIN and check eligibility
        if enhanced_vin_available:
            vin_result = enhanced_vin_service.get_vin_info_with_eligibility(
                vin, mileage)

            if not vin_result.get('success'):
                return jsonify(error_response(vin_result.get('error', 'VIN decode failed'))), 400

            vehicle_info = vin_result['vehicle_info']
            eligibility = vin_result['eligibility']

            if not eligibility.get('eligible'):
                restrictions = eligibility.get('restrictions', [])
                return jsonify(error_response(f"Vehicle not eligible: {'; '.join(restrictions)}")), 400

            make = vehicle_info.get('make', '')
            model = vehicle_info.get('model', '')
            year = vehicle_info.get('year', 0)
        else:
            # Fallback to basic VIN decode
            decode_result = vin_service.decode_vin(vin)
            if not decode_result.get('success'):
                return jsonify(error_response("Failed to decode VIN")), 400

            vehicle_info = decode_result.get('vehicle_info', {})
            make = vehicle_info.get('make', '')
            model = vehicle_info.get('model', '')
            year = vehicle_info.get('year', 0)

            # Basic eligibility check
            current_year = datetime.now().year
            vehicle_age = current_year - year if year else 0
            if vehicle_age > 15 or mileage > 150000:
                return jsonify(error_response("Vehicle not eligible for VSC coverage")), 400

        # Generate VSC quote
        quote_result = vsc_service.generate_quote(
            make=make, model=model, year=year, mileage=mileage,
            coverage_level=coverage_level, term_months=term_months,
            deductible=deductible, customer_type=customer_type
        )

        if quote_result.get('success'):
            # Enhance quote with VIN information
            quote_data = quote_result.copy()
            quote_data['vin_info'] = {
                'vin': vin,
                'vehicle_info': vehicle_info,
                'auto_populated': True,
                'decode_method': vehicle_info.get('decode_method', 'enhanced')
            }

            if enhanced_vin_available and 'eligibility' in vin_result:
                quote_data['eligibility_details'] = eligibility

            return jsonify(success_response(quote_data))
        else:
            return jsonify(error_response(quote_result.get('error', 'Quote generation failed'))), 400

    except Exception as e:
        return jsonify(error_response(f"VIN quote generation error: {str(e)}")), 500

# VIN Decoder API


@app.route('/api/vin/health')
def vin_health():
    """VIN decoder service health check"""
    return jsonify({
        "service": "VIN Decoder API",
        "status": "healthy" if customer_services_available else "unavailable",
        "enhanced_features": "available" if enhanced_vin_available else "basic_only",
        "supported_formats": ["17-character VIN"],
        "features": {
            "basic_decode": customer_services_available,
            "enhanced_decode": enhanced_vin_available,
            "eligibility_checking": enhanced_vin_available,
            "external_api_integration": enhanced_vin_available
        },
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
    """Decode VIN to extract vehicle information (enhanced version)"""
    try:
        data = request.get_json()
        if not data or 'vin' not in data:
            return jsonify({"error": "VIN is required"}), 400

        vin = data['vin'].strip().upper()
        include_eligibility = data.get('include_eligibility', True)
        mileage = data.get('mileage', 0)

        # Validate VIN first
        if len(vin) != 17:
            return jsonify({"error": "Invalid VIN length"}), 400

        # Use enhanced service if available
        if enhanced_vin_available and include_eligibility:
            result = enhanced_vin_service.get_vin_info_with_eligibility(
                vin, mileage)
        elif enhanced_vin_available:
            result = enhanced_vin_service.decode_vin(vin)
        else:
            # Fallback to basic service
            if not customer_services_available:
                return jsonify({"error": "VIN decoder service not available"}), 503
            result = vin_service.decode_vin(vin)

        if result.get('success'):
            return jsonify(success_response(result))
        else:
            return jsonify({"error": result.get('error', 'VIN decode failed')}), 400

    except Exception as e:
        return jsonify({"error": f"VIN decode error: {str(e)}"}), 500


@app.route('/api/vin/enhanced/validate', methods=['POST'])
def enhanced_validate_vin():
    """Enhanced VIN validation with detailed feedback"""
    try:
        data = request.get_json()
        if not data or 'vin' not in data:
            return jsonify(error_response("VIN is required")), 400

        vin = data['vin'].strip().upper()

        if enhanced_vin_available:
            result = enhanced_vin_service.validate_vin(vin)
        else:
            # Fallback to basic validation
            result = vin_service.validate_vin(vin)

        if result.get('success'):
            return jsonify(success_response(result))
        else:
            return jsonify(error_response(result.get('error', 'VIN validation failed'))), 400

    except Exception as e:
        return jsonify(error_response(f"VIN validation error: {str(e)}")), 500


@app.route('/api/vin/enhanced/decode', methods=['POST'])
def enhanced_decode_vin():
    """Enhanced VIN decoding with eligibility checking"""
    try:
        data = request.get_json()
        if not data or 'vin' not in data:
            return jsonify(error_response("VIN is required")), 400

        vin = data['vin'].strip().upper()
        mileage = data.get('mileage', 0)

        if enhanced_vin_available:
            result = enhanced_vin_service.get_vin_info_with_eligibility(
                vin, mileage)
        else:
            # Fallback to basic decoding
            result = vin_service.decode_vin(vin)

        if result.get('success'):
            return jsonify(success_response(result))
        else:
            return jsonify(error_response(result.get('error', 'VIN decode failed'))), 400

    except Exception as e:
        return jsonify(error_response(f"VIN decode error: {str(e)}")), 500

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
# MISSING ENDPOINTS TO ADD TO index.py
# ================================

# 1. PRICING MANAGEMENT ENDPOINTS - DATABASE VERSION
@app.route('/api/pricing/<product_code>', methods=['GET'])
def get_product_pricing(product_code):
    """Get pricing for specific product - uses your database system"""
    try:
        from data.hero_products_data import get_price_from_db_or_fallback

        term_years = request.args.get('term_years', 1, type=int)
        customer_type = request.args.get('customer_type', 'retail')

        result = get_price_from_db_or_fallback(
            product_code, term_years, customer_type)

        if result['success']:
            return jsonify(success_response(result))
        else:
            return jsonify(error_response(result['error'])), 400

    except Exception as e:
        return jsonify(error_response(f"Pricing error: {str(e)}")), 500


# Changed from /all to /products for consistency
@app.route('/api/pricing/products', methods=['GET'])
def get_all_products():
    """Get all product pricing - uses your database system"""
    try:
        from data.hero_products_data import get_all_products_pricing

        result = get_all_products_pricing()
        return jsonify(success_response(result))

    except Exception as e:
        return jsonify(error_response(f"Failed to get pricing: {str(e)}")), 500


@app.route('/api/pricing/quote', methods=['POST'])
def generate_pricing_quote():
    """Generate quote using database pricing"""
    try:
        from data.hero_products_data import calculate_hero_price

        data = request.get_json()
        if not data:
            return jsonify(error_response("Request body is required")), 400

        # Validate required fields
        required_fields = ['product_code', 'term_years']
        missing_fields = [
            field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify(error_response(f"Missing required fields: {', '.join(missing_fields)}")), 400

        # Convert product_code to product_type for the calculate_hero_price function
        code_to_type_mapping = {
            'HOME_PROTECTION_PLAN': 'home_protection',
            'COMPREHENSIVE_AUTO_PROTECTION': 'comprehensive_auto_protection',
            'HOME_DEDUCTIBLE_REIMBURSEMENT': 'home_deductible_reimbursement',
            'AUTO_ADVANTAGE_DEDUCTIBLE_REIMBURSEMENT': 'auto_advantage_deductible_reimbursement',
            'MULTI_VEHICLE_DEDUCTIBLE_REIMBURSEMENT': 'multi_vehicle_deductible_reimbursement',
            'ALL_VEHICLE_DEDUCTIBLE_REIMBURSEMENT': 'all_vehicle_deductible_reimbursement',
            'AUTO_RV_DEDUCTIBLE_REIMBURSEMENT': 'auto_rv_deductible_reimbursement',
            'HERO_LEVEL_HOME_PROTECTION': 'hero_level_protection_home'
        }

        product_type = code_to_type_mapping.get(
            data['product_code'], data.get('product_type', data['product_code'].lower()))

        result = calculate_hero_price(
            product_type=product_type,
            term_years=data['term_years'],
            coverage_limit=data.get('coverage_limit', 500),
            customer_type=data.get('customer_type', 'retail')
        )

        if result['success']:
            return jsonify(success_response(result))
        else:
            return jsonify(error_response(result['error'])), 400

    except Exception as e:
        return jsonify(error_response(f"Quote generation error: {str(e)}")), 500


# 2. ADMIN PRICING CONTROL ENDPOINTS - DATABASE VERSION
@app.route('/api/admin/pricing/<product_code>', methods=['PUT'])
@token_required
@role_required('admin')
def update_product_pricing(product_code):
    """Update product pricing in database (admin only)"""
    try:
        data = request.get_json()

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Check if product exists
        cursor.execute(
            'SELECT id FROM products WHERE product_code = %s;', (product_code,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify(error_response('Product not found')), 404

        # Update base price if provided
        if 'base_price' in data:
            cursor.execute('''
                UPDATE products 
                SET base_price = %s 
                WHERE product_code = %s;
            ''', (data['base_price'], product_code))

        # Update pricing multipliers if provided
        if 'pricing' in data:
            for term_years, pricing_info in data['pricing'].items():
                term = int(term_years)
                multiplier = pricing_info.get('multiplier', pricing_info)

                # Update retail pricing
                cursor.execute('''
                    INSERT INTO pricing (product_code, term_years, multiplier, customer_type) 
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (product_code, term_years, customer_type) 
                    DO UPDATE SET multiplier = %s;
                ''', (product_code, term, multiplier, 'retail', multiplier))

                # Update wholesale pricing (15% discount)
                wholesale_multiplier = multiplier * 0.85
                cursor.execute('''
                    INSERT INTO pricing (product_code, term_years, multiplier, customer_type) 
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (product_code, term_years, customer_type) 
                    DO UPDATE SET multiplier = %s;
                ''', (product_code, term, wholesale_multiplier, 'wholesale', wholesale_multiplier))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': f'Pricing updated for {product_code}',
            'updated_data': data
        }))

    except Exception as e:
        return jsonify(error_response(f"Failed to update pricing: {str(e)}")), 500


@app.route('/api/admin/products', methods=['POST'])
@token_required
@role_required('admin')
def create_product():
    """Create new product in database (admin only)"""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['product_code', 'product_name', 'base_price']
        missing_fields = [
            field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify(error_response(f"Missing fields: {', '.join(missing_fields)}")), 400

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Check if product already exists
        cursor.execute(
            'SELECT id FROM products WHERE product_code = %s;', (data['product_code'],))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify(error_response('Product already exists')), 409

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
        return jsonify(error_response(f"Failed to create product: {str(e)}")), 500


@app.route('/api/admin/products', methods=['GET'])
@token_required
@role_required('admin')
def get_all_admin_products():
    """Get all products with complete pricing data for admin management"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Get products with their complete pricing data
        cursor.execute('''
            SELECT 
                p.id,
                p.product_code,
                p.product_name,
                p.base_price,
                p.active,
                p.created_at,
                -- Get retail pricing as JSON
                COALESCE(
                    JSON_OBJECT_AGG(
                        pr.term_years::text, 
                        JSON_BUILD_OBJECT(
                            'price', ROUND(p.base_price * pr.multiplier, 2),
                            'base_price', p.base_price,
                            'multiplier', pr.multiplier,
                            'term_years', pr.term_years
                        )
                    ) FILTER (WHERE pr.customer_type = 'retail'),
                    '{}'::json
                ) as pricing,
                -- Get available terms
                COALESCE(
                    ARRAY_AGG(DISTINCT pr.term_years ORDER BY pr.term_years) 
                    FILTER (WHERE pr.customer_type = 'retail'),
                    ARRAY[]::integer[]
                ) as terms_available,
                -- Calculate min/max prices for retail
                COALESCE(
                    MIN(ROUND(p.base_price * pr.multiplier, 2)) 
                    FILTER (WHERE pr.customer_type = 'retail'),
                    p.base_price
                ) as min_price,
                COALESCE(
                    MAX(ROUND(p.base_price * pr.multiplier, 2)) 
                    FILTER (WHERE pr.customer_type = 'retail'),
                    p.base_price
                ) as max_price,
                COUNT(pr.id) as pricing_count
            FROM products p
            LEFT JOIN pricing pr ON p.product_code = pr.product_code
            WHERE p.active = true
            GROUP BY p.id, p.product_code, p.product_name, p.base_price, p.active, p.created_at
            ORDER BY p.created_at DESC;
        ''')

        products = cursor.fetchall()

        # Convert to proper format for frontend
        processed_products = []
        for product in products:
            # Convert to dict and handle data types
            product_dict = dict(product)
            product_dict['base_price'] = float(product_dict['base_price'])
            product_dict['min_price'] = float(product_dict['min_price'])
            product_dict['max_price'] = float(product_dict['max_price'])

            # Convert pricing values to floats
            if product_dict['pricing']:
                for term, pricing_info in product_dict['pricing'].items():
                    pricing_info['price'] = float(pricing_info['price'])
                    pricing_info['base_price'] = float(
                        pricing_info['base_price'])
                    pricing_info['multiplier'] = float(
                        pricing_info['multiplier'])

            # Add product_type for compatibility
            code_to_type_mapping = {
                'HOME_PROTECTION_PLAN': 'home_protection',
                'COMPREHENSIVE_AUTO_PROTECTION': 'comprehensive_auto_protection',
                'HOME_DEDUCTIBLE_REIMBURSEMENT': 'home_deductible_reimbursement',
                'AUTO_ADVANTAGE_DEDUCTIBLE_REIMBURSEMENT': 'auto_advantage_deductible_reimbursement',
                'MULTI_VEHICLE_DEDUCTIBLE_REIMBURSEMENT': 'multi_vehicle_deductible_reimbursement',
                'ALL_VEHICLE_DEDUCTIBLE_REIMBURSEMENT': 'all_vehicle_deductible_reimbursement',
                'AUTO_RV_DEDUCTIBLE_REIMBURSEMENT': 'auto_rv_deductible_reimbursement',
                'HERO_LEVEL_HOME_PROTECTION': 'hero_level_protection_home'
            }

            product_dict['product_type'] = code_to_type_mapping.get(
                product_dict['product_code'],
                product_dict['product_code'].lower()
            )

            processed_products.append(product_dict)

        cursor.close()
        conn.close()

        response_data = {
            'success': True,
            'data': {
                'products': processed_products,
                'total': len(processed_products),
                'data_source': 'database'
            },
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }

        return jsonify(response_data), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }), 500


@app.route('/api/admin/products/<product_code>', methods=['DELETE'])
@token_required
@role_required('admin')
def delete_product(product_code):
    """Delete product and its pricing (admin only)"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Check if product exists
        cursor.execute(
            'SELECT product_name FROM products WHERE product_code = %s;', (product_code,))
        product = cursor.fetchone()
        if not product:
            cursor.close()
            conn.close()
            return jsonify(error_response('Product not found')), 404

        product_name = product[0]

        # Delete pricing first (foreign key constraint)
        cursor.execute(
            'DELETE FROM pricing WHERE product_code = %s;', (product_code,))

        # Delete product
        cursor.execute(
            'DELETE FROM products WHERE product_code = %s;', (product_code,))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': f'Product "{product_name}" and its pricing deleted successfully'
        }))

    except Exception as e:
        return jsonify(error_response(f"Failed to delete product: {str(e)}")), 500


# 3. TPA (THIRD PARTY ADMINISTRATOR) ENDPOINTS - DATABASE VERSION
@app.route('/api/admin/tpas', methods=['GET'])
@token_required
@role_required('admin')
def get_tpas():
    """Get all Third Party Administrators from database"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, name, api_endpoint, contact_email, contact_phone, 
                   status, supported_products, commission_rate, created_at, updated_at
            FROM tpas 
            ORDER BY created_at DESC;
        ''')

        rows = cursor.fetchall()
        tpas = []

        for row in rows:
            tpa = {
                'id': str(row[0]),
                'name': row[1],
                'api_endpoint': row[2],
                'contact_email': row[3],
                'contact_phone': row[4],
                'status': row[5],
                'supported_products': row[6] or [],
                'commission_rate': float(row[7]) if row[7] else 0.0,
                'created_at': row[8].isoformat() if row[8] else None,
                'updated_at': row[9].isoformat() if row[9] else None
            }
            tpas.append(tpa)

        cursor.close()
        conn.close()

        return jsonify(success_response({'tpas': tpas}))

    except Exception as e:
        return jsonify(error_response(f"Failed to get TPAs: {str(e)}")), 500


@app.route('/api/admin/tpas', methods=['POST'])
@token_required
@role_required('admin')
def create_tpa():
    """Add new TPA provider to database"""
    try:
        data = request.get_json()

        required_fields = ['name', 'api_endpoint', 'contact_email']
        missing_fields = [
            field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify(error_response(f"Missing fields: {', '.join(missing_fields)}")), 400

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Insert new TPA
        cursor.execute('''
            INSERT INTO tpas (name, api_endpoint, contact_email, contact_phone, 
                            status, supported_products, commission_rate) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at;
        ''', (
            data['name'],
            data['api_endpoint'],
            data['contact_email'],
            data.get('contact_phone', ''),
            data.get('status', 'active'),
            data.get('supported_products', []),
            data.get('commission_rate', 0.15)
        ))

        tpa_id, created_at = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': 'TPA created successfully',
            'tpa': {
                'id': str(tpa_id),
                'created_at': created_at.isoformat(),
                **data
            }
        })), 201

    except Exception as e:
        return jsonify(error_response(f"Failed to create TPA: {str(e)}")), 500


@app.route('/api/admin/tpas/<tpa_id>', methods=['PUT'])
@token_required
@role_required('admin')
def update_tpa(tpa_id):
    """Update existing TPA in database"""
    try:
        data = request.get_json()

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Check if TPA exists
        cursor.execute('SELECT id FROM tpas WHERE id = %s;', (tpa_id,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify(error_response('TPA not found')), 404

        # Build dynamic UPDATE query based on provided fields
        update_fields = []
        values = []

        allowed_fields = ['name', 'api_endpoint', 'contact_email', 'contact_phone',
                          'status', 'supported_products', 'commission_rate']

        for field in allowed_fields:
            if field in data:
                update_fields.append(f"{field} = %s")
                values.append(data[field])

        if not update_fields:
            cursor.close()
            conn.close()
            return jsonify(error_response('No valid fields to update')), 400

        # Add updated_at
        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        values.append(tpa_id)

        query = f"UPDATE tpas SET {', '.join(update_fields)} WHERE id = %s RETURNING updated_at;"
        cursor.execute(query, values)

        updated_at = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': f'TPA {tpa_id} updated successfully',
            'tpa': {
                'id': tpa_id,
                'updated_at': updated_at.isoformat(),
                **data
            }
        }))

    except Exception as e:
        return jsonify(error_response(f"Failed to update TPA: {str(e)}")), 500


@app.route('/api/admin/tpas/<tpa_id>', methods=['DELETE'])
@token_required
@role_required('admin')
def delete_tpa(tpa_id):
    """Delete TPA from database"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Check if TPA exists
        cursor.execute('SELECT name FROM tpas WHERE id = %s;', (tpa_id,))
        tpa = cursor.fetchone()
        if not tpa:
            cursor.close()
            conn.close()
            return jsonify(error_response('TPA not found')), 404

        tpa_name = tpa[0]

        # Delete TPA
        cursor.execute('DELETE FROM tpas WHERE id = %s;', (tpa_id,))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': f'TPA "{tpa_name}" deleted successfully'
        }))

    except Exception as e:
        return jsonify(error_response(f"Failed to delete TPA: {str(e)}")), 500


# 4. QUOTE ROUTING TO TPA ENDPOINTS - DATABASE VERSION
@app.route('/api/quotes/route/<tpa_id>', methods=['POST'])
def route_quote_to_tpa(tpa_id):
    """Route quote to specific TPA using database"""
    try:
        data = request.get_json()

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Verify TPA exists and is active
        cursor.execute('''
            SELECT id, name, api_endpoint, status 
            FROM tpas 
            WHERE id = %s;
        ''', (tpa_id,))

        tpa = cursor.fetchone()
        if not tpa:
            cursor.close()
            conn.close()
            return jsonify(error_response('TPA not found')), 404

        if tpa[3] != 'active':
            cursor.close()
            conn.close()
            return jsonify(error_response('TPA is not active')), 400

        tpa_name = tpa[1]
        api_endpoint = tpa[2]

        # Generate quote routing record (you could add a quotes table later)
        quote_id = f'Q-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}-{tpa_id[:8]}'

        cursor.close()
        conn.close()

        # In a real system, you would make an HTTP request to the TPA's API endpoint here
        # For now, return success response
        return jsonify(success_response({
            'message': f'Quote routed to TPA "{tpa_name}"',
            'quote_id': quote_id,
            'tpa_reference': f'TPA-{tpa_id}-REF',
            'tpa_endpoint': api_endpoint,
            'quote_data': data
        }))

    except Exception as e:
        return jsonify(error_response(f"Failed to route quote: {str(e)}")), 500


# 5. ADMIN SETTINGS ENDPOINTS - DATABASE VERSION
@app.route('/api/admin/settings', methods=['GET'])
@token_required
@role_required('admin')
def get_admin_settings():
    """Get admin configurable settings from database"""
    try:
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
                    # Try to parse as JSON first
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
        print(f"Get settings error: {str(e)}")
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify(error_response(f"Failed to get settings: {str(e)}")), 500


@app.route('/api/admin/settings', methods=['PUT'])
@token_required
@role_required('admin')
def update_admin_settings():
    """Update admin settings in database"""
    try:
        data = request.get_json()
        
        # Add validation for the incoming data
        if not data or not isinstance(data, dict):
            return jsonify(error_response("Invalid data format")), 400
            
        print(f"Received data: {data}")  # Debug logging
        
        # Get user ID with proper validation
        user_id = request.current_user.get('user_id')
        
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
                import json
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
        print(f"Settings update error: {str(e)}")
        print(f"Full traceback: {traceback.format_exc()}")
        if 'conn' in locals():
            conn.rollback()
            print("🔄 Changes rolled back")
        return jsonify(error_response(f"Failed to update settings: {str(e)}")), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


# Optional: Add a utility function for user validation that can be reused
def get_valid_user_id(cursor, token_user_id):
    """
    Get a valid user ID, falling back to any admin user if the token user_id is invalid
    Returns: (user_id, is_fallback)
    """
    # First try the user_id from token
    if token_user_id:
        cursor.execute("SELECT id FROM users WHERE id = %s;", (token_user_id,))
        if cursor.fetchone():
            return token_user_id, False
    
    # Fallback to any admin user
    cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1;")
    result = cursor.fetchone()
    if result:
        return result[0], True
    
    # No valid user found
    return None, True


# 6. VIDEO MANAGEMENT ENDPOINTS - DATABASE VERSION
@app.route('/api/admin/video', methods=['GET'])
@token_required
@role_required('admin')
def get_landing_video():
    """Get current landing page video from database"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT key, value 
            FROM admin_settings 
            WHERE category = 'video';
        ''')

        video_settings = {}
        for key, value in cursor.fetchall():
            # Parse JSON values properly
            if value:
                try:
                    # Try to parse as JSON first
                    parsed_value = json.loads(value) if isinstance(value, str) else value
                    video_settings[key] = parsed_value
                except (json.JSONDecodeError, TypeError):
                    # If not valid JSON, use as string (remove quotes if present)
                    video_settings[key] = value.strip('"') if isinstance(value, str) else value
            else:
                video_settings[key] = ''

        cursor.close()
        conn.close()

        # Provide defaults if not in database
        video_info = {
            'video_url': video_settings.get('landing_page_url', ''),
            'thumbnail_url': video_settings.get('landing_page_thumbnail', ''),
            'title': video_settings.get('landing_page_title', 'ConnectedAutoCare Hero Protection 2025'),
            'description': video_settings.get('landing_page_description', 'Showcase of our comprehensive protection plans'),
            'duration': video_settings.get('landing_page_duration', '2:30'),
            'updated_at': video_settings.get('last_updated', datetime.utcnow().isoformat() + 'Z')
        }

        return jsonify(success_response(video_info))

    except Exception as e:
        print(f"Get video error: {str(e)}")
        return jsonify(error_response(f"Failed to get video: {str(e)}")), 500


@app.route('/api/admin/video', methods=['PUT'])
@token_required
@role_required('admin')
def update_landing_video():
    """Update landing page video in database"""
    try:
        data = request.get_json()
        
        # Get user ID with fallback to a valid admin user
        user_id = request.current_user.get('user_id')
        
        # If user_id is invalid, get a valid admin user from database
        if not user_id:
            conn_temp = psycopg2.connect(DATABASE_URL)
            cursor_temp = conn_temp.cursor()
            cursor_temp.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1;")
            result = cursor_temp.fetchone()
            if result:
                user_id = result[0]
            cursor_temp.close()
            conn_temp.close()
        
        # Validate user_id exists in database
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM users WHERE id = %s;", (user_id,))
        if not cursor.fetchone():
            # Get any valid admin user
            cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1;")
            result = cursor.fetchone()
            if result:
                user_id = result[0]
                print(f"Using fallback admin user: {user_id}")
            else:
                # Set to NULL if no admin user found
                user_id = None
                print("No admin user found, setting updated_by to NULL")

        # Map form fields to database keys
        field_mapping = {
            'video_url': 'landing_page_url',
            'thumbnail_url': 'landing_page_thumbnail',
            'title': 'landing_page_title',
            'description': 'landing_page_description',
            'duration': 'landing_page_duration'
        }

        # Update each video setting
        for form_field, db_key in field_mapping.items():
            if form_field in data:
                # Format as JSON
                json_value = json.dumps(data[form_field])

                cursor.execute('''
                    INSERT INTO admin_settings (category, key, value, updated_by) 
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (category, key) 
                    DO UPDATE SET 
                        value = EXCLUDED.value, 
                        updated_at = CURRENT_TIMESTAMP, 
                        updated_by = EXCLUDED.updated_by;
                ''', ('video', db_key, json_value, user_id))

        # Update last_updated timestamp
        timestamp_value = json.dumps(datetime.utcnow().isoformat() + 'Z')
        cursor.execute('''
            INSERT INTO admin_settings (category, key, value, updated_by) 
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (category, key) 
            DO UPDATE SET 
                value = EXCLUDED.value, 
                updated_at = CURRENT_TIMESTAMP, 
                updated_by = EXCLUDED.updated_by;
        ''', ('video', 'last_updated', timestamp_value, user_id))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': 'Landing page video updated successfully',
            'video_info': data
        }))

    except Exception as e:
        import traceback
        print(f"Video update error: {str(e)}")
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify(error_response(f"Failed to update video: {str(e)}")), 500


# 7. CONTACT INFO MANAGEMENT - DATABASE VERSION
@app.route('/api/contact', methods=['GET'])
def get_contact_info():
    """Get current contact information from database"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Get contact info from settings table
        cursor.execute('''
            SELECT key, value 
            FROM settings 
            WHERE key IN ('contact_phone', 'contact_email')
            UNION ALL
            SELECT key, value 
            FROM admin_settings 
            WHERE category = 'contact';
        ''')

        contact_data = {}
        for key, value in cursor.fetchall():
            # Remove quotes from JSON strings
            contact_data[key] = value.strip(
                '"') if isinstance(value, str) else value

        cursor.close()
        conn.close()

        contact_info = {
            'phone': contact_data.get('contact_phone', '1-(866) 660-7003'),
            'email': contact_data.get('contact_email', 'support@connectedautocare.com'),
            'support_hours': contact_data.get('support_hours', '24/7'),
            'data_source': 'database'
        }

        return jsonify(success_response(contact_info))

    except Exception as e:
        return jsonify(error_response(f"Failed to get contact info: {str(e)}")), 500


@app.route('/api/admin/contact', methods=['PUT'])
@token_required
@role_required('admin')
def update_contact_info():
    """Update contact information in database"""
    try:
        data = request.get_json()
        user_id = request.current_user.get('user_id')

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Update contact info in both tables for compatibility
        if 'phone' in data:
            # Update in settings table
            cursor.execute('''
                INSERT INTO settings (key, value) 
                VALUES (%s, %s)
                ON CONFLICT (key) 
                DO UPDATE SET value = %s, updated_at = CURRENT_TIMESTAMP;
            ''', ('contact_phone', f'"{data["phone"]}"', f'"{data["phone"]}"'))

            # Update in admin_settings table
            cursor.execute('''
                INSERT INTO admin_settings (category, key, value, updated_by) 
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (category, key) 
                DO UPDATE SET 
                    value = %s, 
                    updated_at = CURRENT_TIMESTAMP, 
                    updated_by = %s;
            ''', ('contact', 'phone', f'"{data["phone"]}"', user_id, f'"{data["phone"]}"', user_id))

        if 'email' in data:
            # Update in settings table
            cursor.execute('''
                INSERT INTO settings (key, value) 
                VALUES (%s, %s)
                ON CONFLICT (key) 
                DO UPDATE SET value = %s, updated_at = CURRENT_TIMESTAMP;
            ''', ('contact_email', f'"{data["email"]}"', f'"{data["email"]}"'))

            # Update in admin_settings table
            cursor.execute('''
                INSERT INTO admin_settings (category, key, value, updated_by) 
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (category, key) 
                DO UPDATE SET 
                    value = %s, 
                    updated_at = CURRENT_TIMESTAMP, 
                    updated_by = %s;
            ''', ('contact', 'email', f'"{data["email"]}"', user_id, f'"{data["email"]}"', user_id))

        if 'support_hours' in data:
            cursor.execute('''
                INSERT INTO admin_settings (category, key, value, updated_by) 
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (category, key) 
                DO UPDATE SET 
                    value = %s, 
                    updated_at = CURRENT_TIMESTAMP, 
                    updated_by = %s;
            ''', ('contact', 'support_hours', f'"{data["support_hours"]}"', user_id, f'"{data["support_hours"]}"', user_id))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': 'Contact information updated successfully',
            'updated_contact': data
        }))

    except Exception as e:
        return jsonify(error_response(f"Failed to update contact info: {str(e)}")), 500


# 8. DEALER-SPECIFIC PRICING - DATABASE VERSION
@app.route('/api/admin/dealer-pricing/<dealer_id>', methods=['GET'])
@token_required
@role_required('admin')
def get_dealer_pricing(dealer_id):
    """Get dealer-specific pricing overrides from database"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT name, pricing_overrides, volume_discounts 
            FROM dealers 
            WHERE id = %s;
        ''', (dealer_id,))

        dealer = cursor.fetchone()
        if not dealer:
            cursor.close()
            conn.close()
            return jsonify(error_response('Dealer not found')), 404

        name, pricing_overrides, volume_discounts = dealer

        cursor.close()
        conn.close()

        dealer_pricing = {
            'dealer_id': dealer_id,
            'dealer_name': name,
            'overrides': pricing_overrides or {},
            'volume_discounts': volume_discounts or {}
        }

        return jsonify(success_response(dealer_pricing))

    except Exception as e:
        return jsonify(error_response(f"Failed to get dealer pricing: {str(e)}")), 500


@app.route('/api/admin/dealer-pricing/<dealer_id>', methods=['PUT'])
@token_required
@role_required('admin')
def update_dealer_pricing(dealer_id):
    """Update dealer-specific pricing in database"""
    try:
        data = request.get_json()

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Check if dealer exists
        cursor.execute('SELECT id FROM dealers WHERE id = %s;', (dealer_id,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify(error_response('Dealer not found')), 404

        # Update dealer pricing
        update_fields = []
        values = []

        if 'overrides' in data:
            update_fields.append('pricing_overrides = %s')
            values.append(data['overrides'])

        if 'volume_discounts' in data:
            update_fields.append('volume_discounts = %s')
            values.append(data['volume_discounts'])

        if update_fields:
            update_fields.append('updated_at = CURRENT_TIMESTAMP')
            values.append(dealer_id)

            query = f"UPDATE dealers SET {', '.join(update_fields)} WHERE id = %s;"
            cursor.execute(query, values)
            conn.commit()

        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': f'Dealer pricing updated for {dealer_id}',
            'updated_pricing': data
        }))

    except Exception as e:
        return jsonify(error_response(f"Failed to update dealer pricing: {str(e)}")), 500


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


# ================================
# Video Management
# ================================
@app.route('/api/admin/video/upload', methods=['POST'])
@token_required
@role_required('admin')
def upload_video():
    """Upload video file and thumbnail to Vercel Blob Storage"""
    import json  # Move import to the top of the function
    
    try:
        # Check Vercel Blob configuration
        if not VERCEL_BLOB_READ_WRITE_TOKEN:
            return jsonify(error_response('Vercel Blob storage not configured. Please set VERCEL_BLOB_READ_WRITE_TOKEN environment variable.')), 500
        
        # Check if files are present
        if 'video' not in request.files and 'thumbnail' not in request.files:
            return jsonify(error_response('No files provided')), 400

        video_file = request.files.get('video')
        thumbnail_file = request.files.get('thumbnail')
        
        uploaded_files = {}
        old_files_to_delete = []
        
        # Handle video upload
        if video_file and video_file.filename != '':
            if not allowed_file(video_file.filename, 'video'):
                return jsonify(error_response('Invalid video file type. Allowed: mp4, webm, mov, avi')), 400
            
            # Validate file size
            size_valid, size_message = validate_file_size(video_file, 'video')
            if not size_valid:
                return jsonify(error_response(size_message)), 400
            
            # Upload to Vercel Blob
            upload_result = upload_to_vercel_blob(video_file, 'video')
            
            if upload_result['success']:
                uploaded_files['video_url'] = upload_result['url']
                uploaded_files['video_filename'] = upload_result['filename']
                uploaded_files['video_size'] = upload_result['size']
            else:
                return jsonify(error_response(f"Video upload failed: {upload_result['error']}")), 500
        
        # Handle thumbnail upload
        if thumbnail_file and thumbnail_file.filename != '':
            if not allowed_file(thumbnail_file.filename, 'image'):
                return jsonify(error_response('Invalid thumbnail file type. Allowed: jpg, jpeg, png, gif, webp')), 400
            
            # Validate file size
            size_valid, size_message = validate_file_size(thumbnail_file, 'image')
            if not size_valid:
                return jsonify(error_response(size_message)), 400
            
            # Optimize image
            optimized_file = optimize_image(thumbnail_file)
            
            # Create FileWrapper for upload
            class FileWrapper:
                def __init__(self, file_obj, filename, content_type):
                    self.file_obj = file_obj
                    self.filename = filename
                    self.content_type = content_type
                
                def read(self):
                    return self.file_obj.read()
                
                def seek(self, pos):
                    return self.file_obj.seek(pos)
            
            wrapped_file = FileWrapper(optimized_file, thumbnail_file.filename, 'image/jpeg')
            upload_result = upload_to_vercel_blob(wrapped_file, 'thumbnail')
            
            if upload_result['success']:
                uploaded_files['thumbnail_url'] = upload_result['url']
                uploaded_files['thumbnail_filename'] = upload_result['filename']
                uploaded_files['thumbnail_size'] = upload_result['size']
            else:
                return jsonify(error_response(f"Thumbnail upload failed: {upload_result['error']}")), 500
        
        # Update database with new URLs
        if uploaded_files:
            # Get user ID with proper validation
            user_id = request.current_user.get('user_id')
            
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            
            try:
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
                
                # Get current video URLs for cleanup (get old files before updating)
                cursor.execute('''
                    SELECT key, value 
                    FROM admin_settings 
                    WHERE category = 'video' AND key IN ('landing_page_url', 'landing_page_thumbnail');
                ''')
                
                for key, value in cursor.fetchall():
                    if value:
                        # Parse JSON value - json is now available in function scope
                        try:
                            url_value = json.loads(value) if isinstance(value, str) else value
                            if url_value and 'blob.vercel-storage.com' in str(url_value):
                                old_files_to_delete.append(str(url_value))
                        except (json.JSONDecodeError, TypeError):
                            # Handle non-JSON values
                            if isinstance(value, str) and 'blob.vercel-storage.com' in value:
                                old_files_to_delete.append(value.strip('"'))
                
                # Get form metadata
                title = request.form.get('title', 'ConnectedAutoCare Hero Video')
                description = request.form.get('description', 'Hero protection video')
                duration = request.form.get('duration', '0:00')
                
                # Prepare updates with proper JSON formatting
                updates = [
                    ('landing_page_title', title),
                    ('landing_page_description', description),
                    ('landing_page_duration', duration),
                    ('last_updated', datetime.utcnow().isoformat() + 'Z')
                ]
                
                if 'video_url' in uploaded_files:
                    updates.append(('landing_page_url', uploaded_files['video_url']))
                    updates.append(('video_filename', uploaded_files['video_filename']))
                
                if 'thumbnail_url' in uploaded_files:
                    updates.append(('landing_page_thumbnail', uploaded_files['thumbnail_url']))
                    updates.append(('thumbnail_filename', uploaded_files['thumbnail_filename']))
                
                # Insert/update each setting
                for key, value in updates:
                    # Format value as JSON string - json is now available
                    json_value = json.dumps(value)
                    
                    # Use UPSERT with proper handling of updated_by
                    cursor.execute('''
                        INSERT INTO admin_settings (category, key, value, updated_by) 
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (category, key) 
                        DO UPDATE SET 
                            value = EXCLUDED.value, 
                            updated_at = CURRENT_TIMESTAMP, 
                            updated_by = EXCLUDED.updated_by;
                    ''', ('video', key, json_value, user_id))
                
                conn.commit()
                print(f"✅ Successfully updated database with new video settings")
                
            except Exception as db_error:
                print(f"Database update error: {db_error}")
                conn.rollback()
                # If database update fails but files were uploaded, we should clean them up
                for file_key in ['video_url', 'thumbnail_url']:
                    if file_key in uploaded_files:
                        try:
                            delete_from_vercel_blob(uploaded_files[file_key])
                        except:
                            pass
                raise db_error
            finally:
                cursor.close()
                conn.close()
            
            # Clean up old files after successful database update
            for old_file_url in old_files_to_delete:
                try:
                    delete_result = delete_from_vercel_blob(old_file_url)
                    if delete_result['success']:
                        print(f"Deleted old file: {old_file_url}")
                    else:
                        print(f"Failed to delete old file: {old_file_url}")
                except Exception as e:
                    print(f"Error deleting old file {old_file_url}: {e}")
        
        return jsonify(success_response({
            'message': 'Upload successful',
            'uploaded_files': uploaded_files,
            'video_info': {
                'video_url': uploaded_files.get('video_url'),
                'thumbnail_url': uploaded_files.get('thumbnail_url'),
                'title': request.form.get('title', 'ConnectedAutoCare Hero Video'),
                'description': request.form.get('description', 'Hero protection video'),
                'duration': request.form.get('duration', '0:00'),
                'updated_at': datetime.utcnow().isoformat() + 'Z',
                'storage_provider': 'Vercel Blob',
                'file_sizes': {
                    'video_size_mb': round(uploaded_files.get('video_size', 0) / (1024 * 1024), 2) if 'video_size' in uploaded_files else None,
                    'thumbnail_size_kb': round(uploaded_files.get('thumbnail_size', 0) / 1024, 2) if 'thumbnail_size' in uploaded_files else None
                }
            }
        })), 201
        
    except Exception as e:
        # Add more detailed error logging
        import traceback
        error_details = traceback.format_exc()
        print(f"Video upload error: {str(e)}")
        print(f"Full traceback: {error_details}")
        
        return jsonify(error_response(f"Upload failed: {str(e)}")), 500


@app.route('/api/admin/video/delete', methods=['DELETE'])
@token_required
@role_required('admin')
def delete_video():
    """Delete current video and thumbnail from Vercel Blob"""
    try:
        if not VERCEL_BLOB_READ_WRITE_TOKEN:
            return jsonify(error_response('Vercel Blob storage not configured')), 500

        # Get current video URLs
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Get user ID with proper validation
        user_id = request.current_user.get('user_id')
        
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
        
        cursor.execute('''
            SELECT key, value 
            FROM admin_settings 
            WHERE category = 'video' AND key IN ('landing_page_url', 'landing_page_thumbnail');
        ''')

        files_to_delete = []
        for key, value in cursor.fetchall():
            if value:
                try:
                    # Parse JSON value
                    url_value = json.loads(value) if isinstance(value, str) else value
                    if url_value and 'blob.vercel-storage.com' in str(url_value):
                        files_to_delete.append(str(url_value))
                except (json.JSONDecodeError, TypeError):
                    # Handle non-JSON values
                    if isinstance(value, str) and 'blob.vercel-storage.com' in value:
                        files_to_delete.append(value.strip('"'))

        # Delete files from Vercel Blob
        deletion_results = []
        for file_url in files_to_delete:
            result = delete_from_vercel_blob(file_url)
            deletion_results.append({
                'url': file_url,
                'success': result['success'],
                'error': result.get('error')
            })

        # Clear database entries
        for key in ['landing_page_url', 'landing_page_thumbnail', 'video_filename', 'thumbnail_filename']:
            cursor.execute('''
                UPDATE admin_settings 
                SET value = %s, updated_at = CURRENT_TIMESTAMP, updated_by = %s
                WHERE category = 'video' AND key = %s;
            ''', ('""', user_id, key))

        # Update last_updated timestamp
        timestamp_json = json.dumps(datetime.utcnow().isoformat() + 'Z')
        cursor.execute('''
            INSERT INTO admin_settings (category, key, value, updated_by) 
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (category, key) 
            DO UPDATE SET 
                value = EXCLUDED.value, 
                updated_at = CURRENT_TIMESTAMP, 
                updated_by = EXCLUDED.updated_by;
        ''', ('video', 'last_updated', timestamp_json, user_id))

        conn.commit()
        cursor.close()
        conn.close()

        successful_deletions = [r for r in deletion_results if r['success']]

        return jsonify(success_response({
            'message': f'Deleted {len(successful_deletions)} files successfully',
            'deletion_results': deletion_results,
            'cleared_database': True
        }))

    except Exception as e:
        import traceback
        print(f"Video deletion error: {str(e)}")
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify(error_response(f"Deletion failed: {str(e)}")), 500


@app.route('/api/admin/video/health')
@token_required
@role_required('admin')
def video_service_health():
    """Check video upload service health"""
    try:
        # Test Vercel Blob connection
        blob_configured = bool(VERCEL_BLOB_READ_WRITE_TOKEN)

        health_status = {
            'status': 'healthy' if blob_configured else 'not_configured',
            'storage_provider': 'Vercel Blob',
            'blob_configured': blob_configured,
            'max_video_size_mb': MAX_VIDEO_SIZE / (1024 * 1024),
            'max_image_size_mb': MAX_IMAGE_SIZE / (1024 * 1024),
            'allowed_video_formats': list(ALLOWED_VIDEO_EXTENSIONS),
            'allowed_image_formats': list(ALLOWED_IMAGE_EXTENSIONS),
            'features': {
                'image_optimization': True,
                'automatic_cleanup': False,  # Can be enabled
                'global_cdn': True,
                'secure_upload': True
            }
        }

        if not blob_configured:
            health_status['error'] = 'VERCEL_BLOB_READ_WRITE_TOKEN environment variable not set'
            return jsonify(health_status), 503

        return jsonify(success_response(health_status))

    except Exception as e:
        return jsonify(error_response(f"Health check failed: {str(e)}")), 500


@app.route('/api/landing/video')
def get_current_landing_video():
    """Get current landing page video for public display"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT key, value 
            FROM admin_settings 
            WHERE category = 'video';
        ''')

        video_settings = {}
        for key, value in cursor.fetchall():
            video_settings[key] = value.strip(
                '"') if isinstance(value, str) else value

        cursor.close()
        conn.close()

        video_info = {
            'video_url': video_settings.get('landing_page_url', ''),
            'thumbnail_url': video_settings.get('landing_page_thumbnail', ''),
            'title': video_settings.get('landing_page_title', 'ConnectedAutoCare Hero Protection'),
            'description': video_settings.get('landing_page_description', 'Comprehensive protection plans'),
            'duration': video_settings.get('landing_page_duration', '2:30'),
            'updated_at': video_settings.get('last_updated', datetime.utcnow().isoformat() + 'Z')
        }

        return jsonify(success_response(video_info))

    except Exception as e:
        return jsonify(success_response({
            'video_url': '',
            'thumbnail_url': '',
            'title': 'ConnectedAutoCare Hero Protection',
            'description': 'Comprehensive protection plans',
            'duration': '2:30',
            'updated_at': datetime.utcnow().isoformat() + 'Z'
        }))


# For local development only
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

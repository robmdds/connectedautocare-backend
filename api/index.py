#!/usr/bin/env python3
"""
ConnectedAutoCare.com - Unified Platform API (Vercel Compatible)
Complete insurance platform with customer API, admin panel, and user management
"""

import os
import sys
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from PIL import Image
import io
import requests
import json

try:
    from services.database_settings_service import (
        get_admin_fee, get_wholesale_discount, get_tax_rate, 
        get_processing_fee, get_dealer_fee, settings_service
    )
except ImportError as e:
    print(f"Warning: Failed to import database_settings_service: {e}")
    class DummySettingsService:
        def is_database_available(self): return False
        def clear_cache(self): pass
    settings_service = DummySettingsService()
    def get_admin_fee(product_type: str = 'default') -> float: return 25.00
    def get_wholesale_discount() -> float: return 0.15
    def get_tax_rate(state: str = 'FL') -> float: return 0.07
    def get_processing_fee() -> float: return 15.00
    def get_dealer_fee() -> float: return 50.00


# Database configuration
DATABASE_URL = os.environ.get('DATABASE_URL')

VERCEL_BLOB_READ_WRITE_TOKEN = os.environ.get('BLOB_READ_WRITE_TOKEN')

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
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
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
    from services.vsc_rating_service import VSCRatingService  # This now uses database
    from services.vin_decoder_service import VINDecoderService
    from data.hero_products_data import get_hero_products
    from data.vsc_rates_data import get_vsc_coverage_options  # Updated imports
    from utils.response_helpers import success_response, error_response
    customer_services_available = True
    HERO_SERVICE_AVAILABLE = True
except ImportError as e:
    customer_services_available = False
    HERO_SERVICE_AVAILABLE = False
    # Create fallback classes to prevent crashes
    class HeroRatingService:
        def generate_quote(self, *args, **kwargs):
            return {"success": False, "error": "Service temporarily unavailable"}

    class VSCRatingService:
        def generate_quote(self, *args, **kwargs):
            return {"success": False, "error": "Service temporarily unavailable"}
        
        def generate_quote_from_vin(self, *args, **kwargs):
            return {"success": False, "error": "Service temporarily unavailable"}

    class VINDecoderService:
        def decode_vin(self, *args, **kwargs):
            return {"success": False, "error": "Service temporarily unavailable"}

    def get_hero_products():
        return {}

    def get_vsc_coverage_options():
        return {}
    
    def calculate_vsc_price(*args, **kwargs):
        return {"success": False, "error": "Service temporarily unavailable"}
    
    def get_vehicle_class(make):
        return 'B'

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
            return {"last_login": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}

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
    # Create fallback
    class EnhancedVINDecoderService:
        def decode_vin(self, vin, model_year=None):
            return {"success": False, "error": "Enhanced VIN service not available"}
        
        def validate_vin(self, vin):
            return {"success": False, "error": "Enhanced VIN service not available"}
        
        def check_vsc_eligibility(self, **kwargs):
            return {"success": False, "error": "Enhanced VIN service not available"}
        
        def get_vin_info_with_eligibility(self, vin, mileage=None):
            return {"success": False, "error": "Enhanced VIN service not available"}
    
    enhanced_vin_service = EnhancedVINDecoderService()

try:
    from data.vsc_rates_data import calculate_vsc_price
    VSC_PRICING_AVAILABLE = True
except ImportError:
    VSC_PRICING_AVAILABLE = False
    print("Warning: VSC pricing system not available")


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
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
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
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
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
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
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
    if not customer_services_available or not HERO_SERVICE_AVAILABLE:
        return jsonify({"error": "Hero products service not available"}), 503
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        required_fields = ['product_type', 'term_years']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400
        
        try:
            hero_service = HeroRatingService()
            quote_result = hero_service.generate_quote(
                product_type=data['product_type'],
                term_years=data['term_years'],
                coverage_limit=data.get('coverage_limit', 500),
                customer_type=data.get('customer_type', 'retail'),
                state=data.get('state', 'FL'),
                zip_code=data.get('zip_code', '33101')
            )
            
            if quote_result.get('success'):
                quote_result['database_integration'] = True
                quote_result['database_settings_used'] = settings_service.connection_available
                quote_result['system_info'] = {
                    'settings_source': 'database' if settings_service.connection_available else 'fallback',
                    'admin_fee_source': 'database' if settings_service.connection_available else 'hardcoded',
                    'discount_source': 'database' if settings_service.connection_available else 'hardcoded',
                    'tax_source': 'database' if settings_service.connection_available else 'hardcoded'
                }
                return jsonify(success_response(quote_result))
            else:
                return jsonify({"error": quote_result.get('error', 'Quote generation failed')}), 400
        except Exception as hero_error:
            print(f"Hero service error: {hero_error}")
            return jsonify({"error": f"Hero quote generation failed: {str(hero_error)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Hero quote error: {str(e)}"}), 500

# VSC Rating API


@app.route('/api/vsc/health')
def vsc_health():
    """VSC rating service health check with database integration status"""
    if not customer_services_available:
        return jsonify({"error": "VSC rating service not available"}), 503

    try:
        coverage_options = get_vsc_coverage_options()
        
        # Check database connectivity
        database_status = "unknown"
        try:
            from data.vsc_rates_data import rate_manager
            test_classification = rate_manager.get_vehicle_classification()
            database_status = "connected" if test_classification else "unavailable"
        except Exception as db_error:
            database_status = f"error: {str(db_error)}"
        
        return jsonify({
            "service": "VSC Rating API with Database Integration",
            "status": "healthy",
            "database_integration": {
                "status": database_status,
                "pdf_rates_available": database_status == "connected",
                "exact_rate_lookup": database_status == "connected"
            },
            "coverage_levels": list(coverage_options.get('coverage_levels', {}).keys()) if coverage_options else [],
            "enhanced_features": {
                "vin_auto_detection": enhanced_vin_available,
                "eligibility_checking": enhanced_vin_available,
                "auto_population": enhanced_vin_available,
                "database_rates": database_status == "connected"
            },
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
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
    """Generate VSC quote with database-driven pricing and updated eligibility rules"""
    if not customer_services_available:
        return jsonify({"error": "VSC rating service not available"}), 503

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400

        # Handle VIN-based auto-population
        vin = data.get('vin', '').strip().upper()
        if vin and enhanced_vin_available:
            try:
                vin_result = enhanced_vin_service.decode_vin(vin)
                if vin_result.get('success'):
                    vehicle_info = vin_result['vehicle_info']
                    
                    # Auto-populate missing fields from VIN
                    if not data.get('make'):
                        data['make'] = vehicle_info.get('make', '')
                    if not data.get('model'):
                        data['model'] = vehicle_info.get('model', '')
                    if not data.get('year'):
                        data['year'] = vehicle_info.get('year', 0)
                    
                    data['auto_populated'] = True
                    data['vin_decoded'] = vehicle_info
            except Exception as e:
                print(f"VIN decode failed, continuing with manual data: {e}")

        # Validate required fields
        required_fields = ['make', 'year', 'mileage']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

        # Parse and validate input data
        try:
            make = data['make'].strip()
            model = data.get('model', '').strip()
            year = int(data['year'])
            mileage = int(data['mileage'])
            coverage_level = data.get('coverage_level', 'gold').lower()
            term_months = int(data.get('term_months', 36))
            deductible = int(data.get('deductible', 100))
            customer_type = data.get('customer_type', 'retail').lower()
        except (ValueError, TypeError) as e:
            return jsonify({"error": f"Invalid input data: {str(e)}"}), 400

        # Use database-driven VSC price calculation
        if VSC_PRICING_AVAILABLE:
            try:
                price_result = calculate_vsc_price(
                    make=make,
                    year=year,
                    mileage=mileage,
                    coverage_level=coverage_level,
                    term_months=term_months,
                    deductible=deductible,
                    customer_type=customer_type
                )
                
                if not price_result.get('success'):
                    # Handle ineligible vehicles
                    if not price_result.get('eligible', True):
                        ineligible_response = {
                            'success': False,
                            'eligible': False,
                            'message': "Vehicle doesn't qualify. Make sure you entered the correct current mileage. Vehicle must be 20 model years or newer and less than 200,000 miles at time of quote",
                            'vehicle_info': price_result.get('vehicle_info', {}),
                            'eligibility_details': price_result.get('eligibility_details', {}),
                            'eligibility_requirements': {
                                'max_age': '20 model years or newer',
                                'max_mileage': 'Less than 200,000 miles'
                            }
                        }
                        
                        if vin:
                            ineligible_response['vin_info'] = {
                                'vin': vin,
                                'auto_populated': data.get('auto_populated', False),
                                'vin_decoded': data.get('vin_decoded', {})
                            }
                        
                        return jsonify(ineligible_response), 400
                    
                    return jsonify({"error": price_result.get('error', 'Price calculation failed')}), 400
                
                # Get dynamic fees and tax rates from database
                if settings_service.connection_available:
                    admin_fee = get_admin_fee('vsc')
                    tax_rate = get_tax_rate(data.get('state', 'FL'))  # Use dynamic state
                    processing_fee = get_processing_fee()
                    dealer_fee = get_dealer_fee()
                    fee_source = 'database'
                else:
                    # Fallback values
                    admin_fee = 50.00
                    tax_rate = 0.07
                    processing_fee = 15.00
                    dealer_fee = 50.00
                    fee_source = 'hardcoded_fallback'
                
                # Calculate final pricing
                base_price = price_result['calculated_price']
                subtotal = base_price + admin_fee
                tax_amount = subtotal * tax_rate
                total_price = subtotal + tax_amount
                monthly_payment = total_price / term_months if term_months > 0 else total_price
                
                # Generate quote ID
                quote_id = f"VSC-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
                
                # Build comprehensive response
                quote_response = {
                    'success': True,
                    'eligible': True,
                    'quote_id': quote_id,
                    'pricing_method': price_result.get('pricing_method', 'calculated'),
                    'database_integration': True,
                    'database_settings_used': settings_service.connection_available,
                    
                    # Vehicle information
                    'vehicle_info': {
                        'make': make.title(),
                        'model': model.title() if model else 'Not Specified',
                        'year': year,
                        'mileage': mileage,
                        'vehicle_class': price_result.get('vehicle_info', {}).get('vehicle_class', 'B'),
                        'age_years': datetime.now().year - year
                    },
                    
                    # Coverage details
                    'coverage_details': {
                        'level': coverage_level.title(),
                        'term_months': term_months,
                        'term_years': round(term_months / 12, 1),
                        'deductible': deductible,
                        'customer_type': customer_type.title()
                    },
                    
                    # Pricing breakdown
                    'pricing_breakdown': {
                        'base_calculation': round(base_price, 2),
                        'admin_fee': round(admin_fee, 2),
                        'subtotal': round(subtotal, 2),
                        'tax_amount': round(tax_amount, 2),
                        'total_price': round(total_price, 2),
                        'monthly_payment': round(monthly_payment, 2)
                    },
                    
                    # Fee sources and multipliers
                    'fee_sources': {
                        'admin_fee_source': fee_source,
                        'tax_rate_source': fee_source,
                        'processing_fee': round(processing_fee, 2),
                        'dealer_fee': round(dealer_fee, 2)
                    },
                    'rating_factors': price_result.get('multipliers', {}),
                    
                    # Payment and financing options
                    'payment_options': {
                        'full_payment': round(total_price, 2),
                        'monthly_payment': round(monthly_payment, 2),
                        'financing_available': True,
                        'financing_terms': ['12 months 0% APR', '24 months 0% APR']
                    },
                    
                    # Quote metadata
                    'quote_details': {
                        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
                        'valid_until': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat() + 'Z',
                        'tax_rate': tax_rate,
                        'currency': 'USD'
                    }
                }
                
                # Add VIN information if available
                if vin:
                    quote_response['vin_info'] = {
                        'vin': vin,
                        'auto_populated': data.get('auto_populated', False),
                        'vin_decoded': data.get('vin_decoded', {})
                    }
                
                return jsonify(success_response(quote_response))
                
            except Exception as calc_error:
                print(f"Database VSC calculation failed: {calc_error}")
                return jsonify({"error": f"VSC price calculation error: {str(calc_error)}"}), 500
        
        else:
            return jsonify({"error": "VSC pricing system not available"}), 503

    except Exception as e:
        return jsonify({"error": f"VSC quote error: {str(e)}"}), 500


@app.route('/api/vsc/eligibility', methods=['POST'])
def check_vsc_eligibility():
    """Check VSC eligibility with updated rules (20 years, 200k miles)"""
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
                result = enhanced_vin_service.check_vsc_eligibility(vin=vin, mileage=mileage)
            else:
                result = enhanced_vin_service.check_vsc_eligibility(make=make, year=year, mileage=mileage)
        else:
            # Basic eligibility check with updated rules
            current_year = datetime.now().year
            vehicle_age = current_year - year if year else 0

            eligible = True
            warnings = []
            restrictions = []

            # UPDATED: New age limit (20 years instead of 15)
            if vehicle_age > 20:
                eligible = False
                restrictions.append(
                    f"Vehicle is {vehicle_age} years old (must be 20 model years or newer)")
            elif vehicle_age > 15:
                warnings.append(
                    f"Vehicle is {vehicle_age} years old - limited options may apply")

            # UPDATED: New mileage limit (200k instead of 150k)
            if mileage and mileage >= 200000:
                eligible = False
                restrictions.append(
                    f"Vehicle has {mileage:,} miles (must be less than 200,000 miles)")
            elif mileage and mileage > 150000:
                warnings.append(f"High mileage vehicle - premium rates may apply")

            # Return client's specific message for ineligible vehicles
            if not eligible:
                result = {
                    'success': True,
                    'eligible': False,
                    'message': "Vehicle doesn't qualify. Make sure you entered the correct current mileage. Vehicle must be 20 model years or newer and less than 200,000 miles at time of quote",
                    'vehicle_info': {
                        'make': make, 
                        'year': year, 
                        'mileage': mileage, 
                        'vehicle_age': vehicle_age
                    },
                    'eligibility_requirements': {
                        'max_age': '20 model years or newer',
                        'max_mileage': 'Less than 200,000 miles'
                    },
                    'restrictions': restrictions
                }
            else:
                result = {
                    'success': True,
                    'eligible': True,
                    'warnings': warnings,
                    'restrictions': restrictions,
                    'vehicle_info': {
                        'make': make, 
                        'year': year, 
                        'mileage': mileage, 
                        'vehicle_age': vehicle_age
                    },
                    'eligibility_requirements': {
                        'max_age': '20 model years or newer',
                        'max_mileage': 'Less than 200,000 miles'
                    }
                }

        if result.get('success'):
            return jsonify(success_response(result))
        else:
            return jsonify(error_response(result.get('error', 'Eligibility check failed'))), 400

    except Exception as e:
        return jsonify(error_response(f"Eligibility check error: {str(e)}")), 500


@app.route('/api/vsc/quote/vin', methods=['POST'])
def generate_vsc_quote_from_vin():
    """Generate VSC quote using VIN auto-detection with database integration"""
    try:
        data = request.get_json()
        if not data:
            return jsonify(error_response("Quote data is required")), 400

        # Validate required fields
        vin = data.get('vin', '').strip().upper()
        if not vin:
            return jsonify(error_response("VIN is required for VIN-based quoting")), 400

        mileage = data.get('mileage')
        if not mileage:
            return jsonify(error_response("Mileage is required")), 400

        # Parse optional parameters
        coverage_level = data.get('coverage_level', 'gold').lower()
        term_months = int(data.get('term_months', 36))
        customer_type = data.get('customer_type', 'retail').lower()
        deductible = int(data.get('deductible', 100))

        try:
            mileage = int(mileage)
        except (ValueError, TypeError):
            return jsonify(error_response("Invalid mileage value provided")), 400

        # Decode VIN to get vehicle information
        if enhanced_vin_available:
            vin_result = enhanced_vin_service.decode_vin(vin)
        else:
            return jsonify(error_response("VIN decoding service not available")), 503

        if not vin_result.get('success'):
            return jsonify(error_response("Failed to decode VIN")), 400

        vehicle_info = vin_result.get('vehicle_info', {})
        make = vehicle_info.get('make', '')
        model = vehicle_info.get('model', '')
        year = vehicle_info.get('year', 0)

        if not make or not year:
            return jsonify(error_response("Could not extract vehicle make/year from VIN")), 400

        # Use database-driven VSC price calculation
        if VSC_PRICING_AVAILABLE:
            try:
                price_result = calculate_vsc_price(
                    make=make,
                    year=year,
                    mileage=mileage,
                    coverage_level=coverage_level,
                    term_months=term_months,
                    deductible=deductible,
                    customer_type=customer_type
                )
                
                if not price_result.get('success'):
                    # Handle eligibility issues
                    if not price_result.get('eligible', True):
                        return jsonify(error_response(
                            "Vehicle doesn't qualify. Make sure you entered the correct current mileage. Vehicle must be 20 model years or newer and less than 200,000 miles at time of quote"
                        )), 400
                    else:
                        return jsonify(error_response(f"Price calculation failed: {price_result.get('error', 'Unknown error')}")), 400
                
                # Get dynamic fees from database
                if settings_service.connection_available:
                    admin_fee = get_admin_fee('vsc')
                    tax_rate = get_tax_rate('FL')
                    processing_fee = get_processing_fee()
                    dealer_fee = get_dealer_fee()
                    fee_source = 'database'
                else:
                    admin_fee = 50.00
                    tax_rate = 0.07
                    processing_fee = 15.00
                    dealer_fee = 50.00
                    fee_source = 'hardcoded_fallback'
                
                # Calculate final pricing
                base_price = price_result['calculated_price']
                subtotal = base_price + admin_fee
                tax_amount = subtotal * tax_rate
                total_price = subtotal + tax_amount
                monthly_payment = total_price / term_months if term_months > 0 else total_price
                
                # Build comprehensive quote response
                quote_data = {
                    'success': True,
                    'eligible': True,
                    'quote_id': f"VSC-VIN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                    'pricing_method': price_result.get('pricing_method', 'database_calculated'),
                    'database_integration': True,
                    'database_settings_used': settings_service.connection_available,
                    
                    # Vehicle information from VIN
                    'vehicle_info': {
                        'make': make.title(),
                        'model': model.title() if model else 'Not Specified',
                        'year': year,
                        'mileage': mileage,
                        'vehicle_class': price_result.get('vehicle_info', {}).get('vehicle_class', 'B'),
                        'age_years': datetime.now().year - year
                    },
                    
                    # Coverage details
                    'coverage_details': {
                        'level': coverage_level.title(),
                        'term_months': term_months,
                        'term_years': round(term_months / 12, 1),
                        'deductible': deductible,
                        'customer_type': customer_type.title()
                    },
                    
                    # Pricing breakdown  
                    'pricing_breakdown': {
                        'base_calculation': round(base_price, 2),
                        'admin_fee': round(admin_fee, 2),
                        'subtotal': round(subtotal, 2),
                        'tax_amount': round(tax_amount, 2),
                        'total_price': round(total_price, 2),
                        'monthly_payment': round(monthly_payment, 2)
                    },
                    
                    # Fee sources
                    'fee_sources': {
                        'admin_fee_source': fee_source,
                        'tax_rate_source': fee_source,
                        'processing_fee': round(processing_fee, 2),
                        'dealer_fee': round(dealer_fee, 2)
                    },
                    'rating_factors': price_result.get('multipliers', {}),
                    
                    # VIN-specific information
                    'vin_info': {
                        'vin': vin,
                        'vehicle_info': vehicle_info,
                        'auto_populated': True,
                        'decode_method': vehicle_info.get('decode_method', 'enhanced')
                    },
                    
                    # Quote metadata
                    'quote_details': {
                        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
                        'valid_until': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat() + 'Z',
                        'tax_rate': tax_rate,
                        'currency': 'USD'
                    }
                }

                return jsonify(success_response(quote_data))
                
            except Exception as db_error:
                print(f"Database calculation failed for VIN quote: {db_error}")
                return jsonify(error_response(f"VSC calculation error: {str(db_error)}")), 500
        
        else:
            return jsonify(error_response("VSC pricing system not available")), 503

    except Exception as e:
        return jsonify(error_response(f"VIN quote generation error: {str(e)}")), 500

@app.route('/api/vsc/database/status', methods=['GET'])
def get_vsc_database_status():
    """Get VSC database integration status"""
    try:
        status_info = {
            'database_integration': False,
            'pdf_rates_loaded': False,
            'exact_rate_lookup': False,
            'vehicle_classification_count': 0,
            'coverage_levels': [],
            'error': None
        }
        
        try:
            from data.vsc_rates_data import rate_manager
            
            # Test database connectivity
            vehicle_classification = rate_manager.get_vehicle_classification()
            coverage_levels = rate_manager.get_coverage_levels()
            
            if vehicle_classification and coverage_levels:
                status_info.update({
                    'database_integration': True,
                    'pdf_rates_loaded': True,
                    'exact_rate_lookup': True,
                    'vehicle_classification_count': len(vehicle_classification),
                    'coverage_levels': list(coverage_levels.keys()),
                    'sample_rates_available': True
                })
                
                # Test exact rate lookup
                try:
                    test_rate = rate_manager.get_exact_rate('A', 'gold', 36, 50000)
                    status_info['sample_exact_rate'] = test_rate
                except Exception as rate_error:
                    status_info['exact_rate_lookup'] = False
                    status_info['rate_lookup_error'] = str(rate_error)
            
        except Exception as db_error:
            status_info['error'] = f"Database connection failed: {str(db_error)}"
        
        return jsonify(success_response(status_info))
        
    except Exception as e:
        return jsonify(error_response(f"Status check failed: {str(e)}")), 500

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
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
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

@app.route('/api/vsc/eligibility/requirements', methods=['GET'])
def get_vsc_eligibility_requirements():
    """Get current VSC eligibility requirements"""
    return jsonify(success_response({
        'eligibility_requirements': {
            'max_vehicle_age': '20 model years or newer',
            'max_mileage': 'Less than 200,000 miles',
            'message_for_ineligible': "Vehicle doesn't qualify. Make sure you entered the correct current mileage. Vehicle must be 20 model years or newer and less than 200,000 miles at time of quote"
        },
        'coverage_levels': ['silver', 'gold', 'platinum'],
        'available_terms': [12, 24, 36, 48, 60],
        'available_deductibles': [0, 50, 100, 200, 500, 1000],
        'updated': datetime.now(timezone.utc).isoformat() + 'Z'
    }))
    

@app.route('/api/vsc/eligibility/test', methods=['POST'])
def test_vsc_eligibility():
    """Test VSC eligibility with different vehicle scenarios"""
    try:
        data = request.get_json()
        if not data:
            return jsonify(error_response("Test data is required")), 400

        test_scenarios = data.get('scenarios', [data])  # Allow single scenario or multiple
        results = []

        for scenario in test_scenarios:
            make = scenario.get('make', 'Honda')
            year = scenario.get('year', 2020)
            mileage = scenario.get('mileage', 50000)
            
            try:
                year = int(year)
                mileage = int(mileage)
            except (ValueError, TypeError):
                results.append({
                    'scenario': scenario,
                    'error': 'Invalid year or mileage values'
                })
                continue

            current_year = datetime.now().year
            vehicle_age = current_year - year

            # Apply updated eligibility rules
            eligible = True
            issues = []

            if vehicle_age > 20:
                eligible = False
                issues.append(f"Vehicle is {vehicle_age} years old (must be 20 model years or newer)")

            if mileage >= 200000:
                eligible = False
                issues.append(f"Vehicle has {mileage:,} miles (must be less than 200,000 miles)")

            result = {
                'scenario': {
                    'make': make,
                    'year': year,
                    'mileage': mileage,
                    'vehicle_age': vehicle_age
                },
                'eligible': eligible,
                'issues': issues if not eligible else [],
                'message': "Vehicle qualifies for VSC coverage" if eligible else "Vehicle doesn't qualify. Make sure you entered the correct current mileage. Vehicle must be 20 model years or newer and less than 200,000 miles at time of quote"
            }
            
            results.append(result)

        return jsonify(success_response({
            'test_results': results,
            'total_scenarios': len(results),
            'eligible_count': len([r for r in results if r.get('eligible')]),
            'ineligible_count': len([r for r in results if not r.get('eligible')])
        }))

    except Exception as e:
        return jsonify(error_response(f"Eligibility test error: {str(e)}")), 500


@app.route('/api/vin/decode', methods=['POST'])
def decode_vin():
    """Enhanced VIN decoding with improved NHTSA integration"""
    try:
        data = request.get_json()
        if not data or 'vin' not in data:
            return jsonify({"error": "VIN is required"}), 400

        vin = data['vin'].strip().upper()
        include_eligibility = data.get('include_eligibility', True)
        mileage = data.get('mileage', 0)
        model_year = data.get('model_year')  # NEW: Accept model_year for better NHTSA accuracy

        # Validate VIN first
        if len(vin) != 17:
            return jsonify({"error": "Invalid VIN length"}), 400

        print(f"🔍 Decoding VIN: {vin}")
        if model_year:
            print(f"📅 Using model year: {model_year}")

        # Use enhanced service if available
        if enhanced_vin_available and include_eligibility:
            result = enhanced_vin_service.get_vin_info_with_eligibility(vin, mileage)
        elif enhanced_vin_available:
            # UPDATED: Pass model_year to enhanced service
            result = enhanced_vin_service.decode_vin(vin, model_year)
        else:
            # Fallback to basic service
            if not customer_services_available:
                return jsonify({"error": "VIN decoder service not available"}), 503
            result = vin_service.decode_vin(vin)

        if result.get('success'):
            # Add NHTSA-specific metadata if available
            if result.get('vehicle_info', {}).get('decode_method') == 'nhtsa_api_enhanced':
                result['nhtsa_integration'] = {
                    'api_used': True,
                    'data_source': 'NHTSA vPIC Database',
                    'api_fields_returned': result.get('vehicle_info', {}).get('api_fields_returned', 0),
                    'model_year_provided': model_year is not None
                }
            
            return jsonify(success_response(result))
        else:
            return jsonify({"error": result.get('error', 'VIN decode failed')}), 400

    except Exception as e:
        print(f"❌ VIN decode error: {str(e)}")
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
        model_year = data.get('model_year')  # NEW: Accept model_year

        if enhanced_vin_available:
            # UPDATED: Pass model_year to enhanced service
            result = enhanced_vin_service.get_vin_info_with_eligibility(vin, mileage)
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
            "contract_id": f"CAC-{datetime.now(timezone.utc).strftime('%Y%m%d')}-001",
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
        user['updated_at'] = datetime.now(timezone.utc).isoformat()

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
    """Update product pricing with database-driven calculations"""
    try:
        data = request.get_json()
        if not data:
            return jsonify(error_response("Pricing data is required")), 400

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Verify product exists
        cursor.execute("SELECT id, base_price FROM products WHERE product_code = %s;", (product_code,))
        product_result = cursor.fetchone()
        if not product_result:
            return jsonify(error_response("Product not found")), 404

        product_id, current_base_price = product_result

        # Update base price if provided
        new_base_price = data.get('base_price', current_base_price)
        if new_base_price != current_base_price:
            cursor.execute('''
                UPDATE products 
                SET base_price = %s, updated_at = CURRENT_TIMESTAMP
                WHERE product_code = %s;
            ''', (new_base_price, product_code))

        # Update pricing multipliers
        if 'pricing' in data:
            for term_years, customer_prices in data['pricing'].items():
                term = int(term_years)
                
                for customer_type, multiplier in customer_prices.items():
                    cursor.execute('''
                        INSERT INTO pricing (product_code, term_years, multiplier, customer_type)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (product_code, term_years, customer_type)
                        DO UPDATE SET 
                            multiplier = EXCLUDED.multiplier,
                            updated_at = CURRENT_TIMESTAMP;
                    ''', (product_code, term, float(multiplier), customer_type))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(success_response({
            'message': 'Pricing updated successfully',
            'product_code': product_code,
            'base_price': float(new_base_price)
        }))

    except Exception as e:
        print(f"Update pricing error: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
        return jsonify(error_response(f"Failed to update pricing: {str(e)}")), 500


@app.route('/api/admin/pricing/calculate', methods=['POST'])
@token_required
@role_required('admin')
def calculate_pricing_preview():
    """Calculate pricing preview with database-driven fees and taxes"""
    try:
        data = request.get_json()
        if not data:
            return jsonify(error_response("Calculation data is required")), 400

        base_price = float(data.get('base_price', 0))
        term_years = int(data.get('term_years', 1))
        customer_type = data.get('customer_type', 'retail')
        state = data.get('state', 'FL')

        # Get dynamic settings from database
        if settings_service.connection_available:
            admin_fee = get_admin_fee('hero')
            wholesale_discount_rate = get_wholesale_discount()
            tax_rate = get_tax_rate(state)
            processing_fee = get_processing_fee()
        else:
            admin_fee = 25.00
            wholesale_discount_rate = 0.15
            tax_rate = 0.08
            processing_fee = 15.00

        # Apply customer type discount
        if customer_type == 'wholesale':
            discounted_price = base_price * (1 - wholesale_discount_rate)
            discount_amount = base_price - discounted_price
        else:
            discounted_price = base_price
            discount_amount = 0

        # Calculate final pricing
        subtotal = discounted_price + admin_fee
        tax_amount = subtotal * tax_rate
        total_price = subtotal + tax_amount
        monthly_payment = total_price / (term_years * 12)

        return jsonify(success_response({
            'calculation': {
                'base_price': round(base_price, 2),
                'discount_rate': wholesale_discount_rate if customer_type == 'wholesale' else 0,
                'discount_amount': round(discount_amount, 2),
                'discounted_price': round(discounted_price, 2),
                'admin_fee': round(admin_fee, 2),
                'subtotal': round(subtotal, 2),
                'tax_rate': tax_rate,
                'tax_amount': round(tax_amount, 2),
                'total_price': round(total_price, 2),
                'monthly_payment': round(monthly_payment, 2),
                'term_years': term_years,
                'customer_type': customer_type
            },
            'settings_used': {
                'admin_fee_source': 'database' if settings_service.connection_available else 'fallback',
                'tax_rate_source': 'database' if settings_service.connection_available else 'fallback',
                'discount_source': 'database' if settings_service.connection_available else 'fallback',
                'state': state
            }
        }))

    except Exception as e:
        print(f"Calculate pricing error: {str(e)}")
        return jsonify(error_response(f"Failed to calculate pricing: {str(e)}")), 500


@app.route('/api/admin/hero/test-quote', methods=['POST'])
@token_required
@role_required('admin')
def test_hero_quote():
    """Test Hero quote generation with current database settings"""
    try:
        data = request.get_json()
        if not data:
            return jsonify(error_response("Quote test data is required")), 400

        if not HERO_SERVICE_AVAILABLE:
            return jsonify(error_response("Hero service not available")), 503

        # Create Hero service instance (uses database settings)
        hero_service = HeroRatingService()

        # Generate test quote
        quote_result = hero_service.generate_quote(
            product_type=data.get('product_type', 'home_protection'),
            term_years=data.get('term_years', 1),
            coverage_limit=data.get('coverage_limit', 500),
            customer_type=data.get('customer_type', 'retail'),
            state=data.get('state', 'FL'),
            zip_code=data.get('zip_code', '33101')
        )

        if quote_result.get('success'):
            # Add test metadata
            quote_result['test_quote'] = True
            quote_result['test_timestamp'] = datetime.utcnow().isoformat() + 'Z'
            quote_result['database_settings_used'] = settings_service.connection_available

            return jsonify(success_response(quote_result))
        else:
            return jsonify(error_response(quote_result.get('error', 'Quote generation failed')), 400)

    except Exception as e:
        print(f"Test quote error: {str(e)}")
        return jsonify(error_response(f"Failed to generate test quote: {str(e)}")), 500


@app.route('/api/admin/system-settings', methods=['GET'])
@token_required
@role_required('admin')
def get_system_settings_for_products():
    """Get current system settings for product management"""
    try:
        if settings_service.connection_available:
            # Get all relevant settings for product management
            settings = {
                'fees': {
                    'admin_fee': get_admin_fee('hero'),
                    'vsc_admin_fee': get_admin_fee('vsc'),
                    'processing_fee': get_processing_fee()
                },
                'discounts': {
                    'wholesale_discount_rate': get_wholesale_discount()
                },
                'taxes': {
                    'default_tax_rate': get_tax_rate(),
                    'fl_tax_rate': get_tax_rate('FL'),
                    'ca_tax_rate': get_tax_rate('CA'),
                    'ny_tax_rate': get_tax_rate('NY'),
                    'tx_tax_rate': get_tax_rate('TX')
                },
                'hero_settings': {}
            }

            # Get Hero-specific settings if available
            if settings_service:
                settings_service.clear_cache()
                settings['hero_settings'] = {
                    'coverage_multiplier_1000': settings_service.get_admin_setting('hero', 'coverage_multiplier_1000', 1.2),
                    'coverage_multiplier_500': settings_service.get_admin_setting('hero', 'coverage_multiplier_500', 1.0),
                    'default_coverage_limit': settings_service.get_admin_setting('hero', 'default_coverage_limit', 500)
                }
        else:
            # Fallback settings
            settings = {
                'fees': {
                    'admin_fee': 25.00,
                    'vsc_admin_fee': 50.00,
                    'processing_fee': 15.00
                },
                'discounts': {
                    'wholesale_discount_rate': 0.15
                },
                'taxes': {
                    'default_tax_rate': 0.08,
                    'fl_tax_rate': 0.07,
                    'ca_tax_rate': 0.0875,
                    'ny_tax_rate': 0.08,
                    'tx_tax_rate': 0.0625
                },
                'hero_settings': {
                    'coverage_multiplier_1000': 1.2,
                    'coverage_multiplier_500': 1.0,
                    'default_coverage_limit': 500
                }
            }

        return jsonify(success_response({
            'settings': settings,
            'database_driven': settings_service.connection_available,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }))

    except Exception as e:
        print(f"Get system settings error: {str(e)}")
        return jsonify(error_response(f"Failed to get system settings: {str(e)}")), 500


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
def get_admin_products():
    """Get all products with database-driven pricing info"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Get products with pricing information
        cursor.execute('''
            SELECT 
                p.id,
                p.product_code,
                p.product_name,
                p.base_price,
                p.active,
                p.created_at,
                COUNT(pr.id) as pricing_count,
                MIN(p.base_price * pr.multiplier) as min_price,
                MAX(p.base_price * pr.multiplier) as max_price,
                ARRAY_AGG(DISTINCT pr.term_years ORDER BY pr.term_years) as terms_available
            FROM products p
            LEFT JOIN pricing pr ON p.product_code = pr.product_code
            GROUP BY p.id, p.product_code, p.product_name, p.base_price, p.active, p.created_at
            ORDER BY p.product_name;
        ''')

        products = []
        for row in cursor.fetchall():
            id, product_code, product_name, base_price, active, created_at, pricing_count, min_price, max_price, terms = row
            
            products.append({
                'id': id,
                'product_code': product_code,
                'product_name': product_name,
                'base_price': float(base_price) if base_price else 0,
                'min_price': float(min_price) if min_price else 0,
                'max_price': float(max_price) if max_price else 0,
                'active': active,
                'created_at': created_at.isoformat() if created_at else None,
                'pricing_count': pricing_count,
                'terms_available': [t for t in terms if t is not None] if terms else []
            })

        # Get current system settings for frontend
        if settings_service.connection_available:
            system_settings = {
                'hero_admin_fee': get_admin_fee('hero'),
                'wholesale_discount_rate': get_wholesale_discount(),
                'default_tax_rate': get_tax_rate(),
                'fl_tax_rate': get_tax_rate('FL'),
                'ca_tax_rate': get_tax_rate('CA'),
                'ny_tax_rate': get_tax_rate('NY'),
                'processing_fee': get_processing_fee(),
                'database_driven': True
            }
        else:
            system_settings = {
                'hero_admin_fee': 25.00,
                'wholesale_discount_rate': 0.15,
                'default_tax_rate': 0.08,
                'fl_tax_rate': 0.07,
                'ca_tax_rate': 0.0875,
                'ny_tax_rate': 0.08,
                'processing_fee': 15.00,
                'database_driven': False
            }

        cursor.close()
        conn.close()

        return jsonify(success_response({
            'products': products,
            'system_settings': system_settings,
            'total_products': len(products)
        }))

    except Exception as e:
        print(f"Get products error: {str(e)}")
        return jsonify(error_response(f"Failed to get products: {str(e)}")), 500



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
        quote_id = f'Q-{datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")}-{tpa_id[:8]}'

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
            'updated_at': video_settings.get('last_updated', datetime.now(timezone.utc).isoformat() + 'Z')
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
        timestamp_value = json.dumps(datetime.now(timezone.utc).isoformat() + 'Z')
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
                    ('last_updated', datetime.now(timezone.utc).isoformat() + 'Z')
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
                'updated_at': datetime.now(timezone.utc).isoformat() + 'Z',
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
        timestamp_json = json.dumps(datetime.now(timezone.utc).isoformat() + 'Z')
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
            'updated_at': video_settings.get('last_updated', datetime.now(timezone.utc).isoformat() + 'Z')
        }

        return jsonify(success_response(video_info))

    except Exception as e:
        return jsonify(success_response({
            'video_url': '',
            'thumbnail_url': '',
            'title': 'ConnectedAutoCare Hero Protection',
            'description': 'Comprehensive protection plans',
            'duration': '2:30',
            'updated_at': datetime.now(timezone.utc).isoformat() + 'Z'
        }))

@app.route('/api/vin/decode/batch', methods=['POST'])
def decode_vins_batch():
    """Batch VIN decoding using NHTSA API (max 50 VINs)"""
    try:
        data = request.get_json()
        if not data or 'vins' not in data:
            return jsonify({"error": "VINs array is required"}), 400

        vins_data = data['vins']
        if not isinstance(vins_data, list):
            return jsonify({"error": "VINs must be an array"}), 400

        if len(vins_data) > 50:
            return jsonify({"error": "Maximum 50 VINs allowed per batch"}), 400

        print(f"🔍 Batch decoding {len(vins_data)} VINs")

        # Process VINs - can be strings or objects with vin/model_year
        processed_vins = []
        for item in vins_data:
            if isinstance(item, str):
                processed_vins.append({'vin': item.strip().upper(), 'model_year': None})
            elif isinstance(item, dict) and 'vin' in item:
                processed_vins.append({
                    'vin': item['vin'].strip().upper(),
                    'model_year': item.get('model_year')
                })
            else:
                return jsonify({"error": "Invalid VIN format in batch"}), 400

        # Validate all VINs
        for item in processed_vins:
            if len(item['vin']) != 17:
                return jsonify({"error": f"Invalid VIN length: {item['vin']}"}), 400

        # Process each VIN
        results = []
        for item in processed_vins:
            vin = item['vin']
            model_year = item['model_year']
            
            if enhanced_vin_available:
                result = enhanced_vin_service.decode_vin(vin, model_year)
            else:
                result = vin_service.decode_vin(vin)
            
            if result.get('success'):
                results.append({
                    'vin': vin,
                    'success': True,
                    'vehicle_info': result['vehicle_info']
                })
            else:
                results.append({
                    'vin': vin,
                    'success': False,
                    'error': result.get('error', 'Decode failed')
                })

        return jsonify(success_response({
            'batch_results': results,
            'total_processed': len(results),
            'successful_decodes': len([r for r in results if r['success']]),
            'decode_method': 'enhanced_with_nhtsa'
        }))

    except Exception as e:
        print(f"❌ Batch VIN decode error: {str(e)}")
        return jsonify({"error": f"Batch decode error: {str(e)}"}), 500
    

@app.route('/api/vin/test', methods=['POST'])
def test_vin_decode():
    """Test endpoint for VIN decoding with detailed debugging"""
    try:
        data = request.get_json()
        if not data or 'vin' not in data:
            return jsonify({"error": "VIN is required"}), 400

        vin = data['vin'].strip().upper()
        model_year = data.get('model_year')
        debug_mode = data.get('debug', False)

        print(f"🧪 Testing VIN: {vin}")

        results = {
            'vin': vin,
            'test_results': {},
            'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
        }

        # Test NHTSA API directly
        try:
            print("🌐 Testing NHTSA API...")
            import requests
            
            url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{vin}"
            params = {'format': 'json'}
            if model_year:
                params['modelyear'] = model_year

            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                nhtsa_data = response.json()
                nhtsa_results = nhtsa_data.get('Results', [])
                
                # Extract key fields
                key_info = {}
                for result in nhtsa_results:
                    variable = result.get('Variable', '')
                    value = result.get('Value', '')
                    
                    if variable in ['Make', 'Model', 'Model Year', 'Body Class'] and value not in ['Not Applicable', '', 'N/A']:
                        key_info[variable] = value

                results['test_results']['nhtsa_api'] = {
                    'status': 'success',
                    'response_code': 200,
                    'fields_returned': len(nhtsa_results),
                    'key_info': key_info,
                    'url_used': url
                }
                    
            else:
                results['test_results']['nhtsa_api'] = {
                    'status': 'failed',
                    'response_code': response.status_code,
                    'error': f"HTTP {response.status_code}"
                }
                
        except Exception as nhtsa_error:
            results['test_results']['nhtsa_api'] = {
                'status': 'error',
                'error': str(nhtsa_error)
            }

        # Test enhanced VIN service
        if enhanced_vin_available:
            try:
                print("🔧 Testing Enhanced VIN Service...")
                enhanced_result = enhanced_vin_service.decode_vin(vin, model_year)
                
                results['test_results']['enhanced_service'] = {
                    'status': 'success' if enhanced_result.get('success') else 'failed',
                    'decode_method': enhanced_result.get('vehicle_info', {}).get('decode_method'),
                    'fields_extracted': len(enhanced_result.get('vehicle_info', {})),
                    'vehicle_info': {
                        'make': enhanced_result.get('vehicle_info', {}).get('make'),
                        'model': enhanced_result.get('vehicle_info', {}).get('model'),
                        'year': enhanced_result.get('vehicle_info', {}).get('year')
                    } if enhanced_result.get('success') else None,
                    'error': enhanced_result.get('error') if not enhanced_result.get('success') else None
                }
                
            except Exception as enhanced_error:
                results['test_results']['enhanced_service'] = {
                    'status': 'error',
                    'error': str(enhanced_error)
                }
        else:
            results['test_results']['enhanced_service'] = {
                'status': 'unavailable',
                'message': 'Enhanced VIN service not loaded'
            }

        return jsonify(success_response(results))

    except Exception as e:
        return jsonify({"error": f"Test error: {str(e)}"}), 500


# ================================
# VSC USER-FACING DATA ENDPOINTS
# ================================

@app.route('/api/vsc/rates', methods=['GET'])
def get_vsc_rates():
    """Get VSC rates for public consumption (filtered for frontend)"""
    try:
        vehicle_class = request.args.get('vehicle_class')
        coverage_level = request.args.get('coverage_level')
        term_months = request.args.get('term_months', type=int)
        mileage = request.args.get('mileage', type=int)
        
        from data.vsc_rates_data import rate_manager
        
        # If specific parameters provided, get targeted rates
        if all([vehicle_class, coverage_level, term_months, mileage]):
            exact_rate = rate_manager.get_exact_rate(vehicle_class, coverage_level, term_months, mileage)
            if exact_rate:
                return jsonify(success_response({
                    'rate': exact_rate,
                    'vehicle_class': vehicle_class,
                    'coverage_level': coverage_level,
                    'term_months': term_months,
                    'mileage_range': f"Applicable for {mileage:,} miles"
                }))
        
        # Get all available options for frontend
        coverage_options = get_vsc_coverage_options()
        
        return jsonify(success_response({
            'coverage_levels': coverage_options.get('coverage_levels', {}),
            'term_options': coverage_options.get('term_options', {}),
            'deductible_options': coverage_options.get('deductible_options', {}),
            'vehicle_classes': coverage_options.get('vehicle_classes', {}),
            'data_source': 'database'
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to get VSC rates: {str(e)}")), 500


@app.route('/api/vsc/vehicle-classes', methods=['GET'])
def get_vsc_vehicle_classes():
    """Get vehicle classification data"""
    try:
        from data.vsc_rates_data import rate_manager
        
        classification = rate_manager.get_vehicle_classification()
        
        # Organize by class
        classes = {'A': [], 'B': [], 'C': []}
        for make, vehicle_class in classification.items():
            if vehicle_class in classes:
                classes[vehicle_class].append(make.title())
        
        return jsonify(success_response({
            'vehicle_classes': {
                'A': {
                    'name': 'Class A - Most Reliable',
                    'description': 'Lowest rates - typically Japanese and Korean brands',
                    'makes': sorted(classes['A'])
                },
                'B': {
                    'name': 'Class B - Moderate Risk', 
                    'description': 'Medium rates - typically American brands',
                    'makes': sorted(classes['B'])
                },
                'C': {
                    'name': 'Class C - Higher Risk',
                    'description': 'Highest rates - typically luxury and European brands', 
                    'makes': sorted(classes['C'])
                }
            },
            'total_makes': len(classification)
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to get vehicle classes: {str(e)}")), 500


@app.route('/api/vsc/multipliers', methods=['GET'])
def get_vsc_multipliers():
    """Get all VSC pricing multipliers"""
    try:
        from data.vsc_rates_data import rate_manager
        
        multipliers = {
            'term_multipliers': rate_manager.get_term_multipliers(),
            'deductible_multipliers': rate_manager.get_deductible_multipliers(), 
            'mileage_multipliers': rate_manager.get_mileage_multipliers(),
            'age_multipliers': rate_manager.get_age_multipliers()
        }
        
        return jsonify(success_response(multipliers))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to get multipliers: {str(e)}")), 500


@app.route('/api/vsc/coverage/<coverage_level>', methods=['GET'])
def get_vsc_coverage_details(coverage_level):
    """Get detailed information about a specific coverage level"""
    try:
        from data.vsc_rates_data import rate_manager
        
        coverage_levels = rate_manager.get_coverage_levels()
        
        if coverage_level not in coverage_levels:
            return jsonify(error_response(f"Coverage level '{coverage_level}' not found")), 404
        
        coverage_info = coverage_levels[coverage_level]
        
        # Get sample rates for this coverage level
        sample_rates = {}
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT vehicle_class, term_months, mileage_range_key, rate_amount
                FROM vsc_rate_matrix 
                WHERE coverage_level = %s 
                AND active = TRUE
                ORDER BY vehicle_class, term_months, min_mileage
                LIMIT 20;
            ''', (coverage_level,))
            
            rates_data = cursor.fetchall()
            for vehicle_class, term_months, mileage_key, rate_amount in rates_data:
                if vehicle_class not in sample_rates:
                    sample_rates[vehicle_class] = {}
                if term_months not in sample_rates[vehicle_class]:
                    sample_rates[vehicle_class][term_months] = {}
                sample_rates[vehicle_class][term_months][mileage_key] = float(rate_amount)
            
            cursor.close()
            conn.close()
            
        except Exception as rate_error:
            print(f"Could not get sample rates: {rate_error}")
        
        return jsonify(success_response({
            'coverage_level': coverage_level,
            'details': coverage_info,
            'sample_rates': sample_rates
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to get coverage details: {str(e)}")), 500


@app.route('/api/vsc/rate-lookup', methods=['POST'])
def lookup_vsc_rate():
    """Look up specific VSC rate"""
    try:
        data = request.get_json()
        
        required_fields = ['vehicle_class', 'coverage_level', 'term_months', 'mileage']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify(error_response(f"Missing fields: {', '.join(missing_fields)}")), 400
        
        from data.vsc_rates_data import rate_manager
        
        exact_rate = rate_manager.get_exact_rate(
            data['vehicle_class'],
            data['coverage_level'], 
            data['term_months'],
            data['mileage']
        )
        
        if exact_rate:
            return jsonify(success_response({
                'rate_found': True,
                'rate_amount': exact_rate,
                'lookup_criteria': data,
                'rate_type': 'exact_pdf_rate'
            }))
        else:
            # Try to get base rate and calculate
            base_rate = rate_manager.get_base_rate(data['vehicle_class'], data['coverage_level'])
            
            return jsonify(success_response({
                'rate_found': False,
                'base_rate': base_rate,
                'lookup_criteria': data,
                'rate_type': 'calculated_fallback',
                'message': 'Exact rate not found, base rate provided'
            }))
        
    except Exception as e:
        return jsonify(error_response(f"Rate lookup failed: {str(e)}")), 500


# Utility endpoint to check database settings status
@app.route('/api/admin/settings/status', methods=['GET'])
def get_settings_status():
    """Get status of database settings integration"""
    try:
        if settings_service.connection_available:
            
            # Get sample settings to verify database connectivity
            admin_fee = get_admin_fee()
            wholesale_discount = get_wholesale_discount()
            tax_rate = get_tax_rate()
            
            return jsonify({
                'success': True,
                'settings_service.connection_available': True,
                'sample_settings': {
                    'admin_fee': admin_fee,
                    'wholesale_discount': wholesale_discount,
                    'tax_rate': tax_rate
                },
                'message': 'Database settings service is operational'
            })
        else:
            return jsonify({
                'success': False,
                'settings_service.connection_available': False,
                'message': 'Database settings service not available - using hardcoded fallback values'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'settings_service.connection_available': False,
            'error': f"Settings service error: {str(e)}",
            'message': 'Database settings service encountered an error'
        }), 500


# Utility endpoint to refresh settings cache
@app.route('/api/admin/settings/refresh', methods=['POST'])
def refresh_settings_cache():
    """Refresh the database settings cache"""
    try:
        if settings_service.connection_available:            
            # Clear settings cache
            if settings_service:
                settings_service.clear_cache()
            
            # Refresh hero service settings
            hero_service_instance = HeroRatingService()
            hero_service_instance.refresh_settings()
            
            return jsonify({
                'success': True,
                'message': 'Settings cache refreshed successfully',
                'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Database settings service not available'
            }), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f"Cache refresh error: {str(e)}"
        }), 500


# ================================
# VSC ADMIN CRUD ENDPOINTS
# ================================

@app.route('/api/admin/vsc/rates', methods=['GET'])
@token_required
@role_required('admin')
def get_all_vsc_rates():
    """Get all VSC rates for admin management"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        vehicle_class = request.args.get('vehicle_class')
        coverage_level = request.args.get('coverage_level')
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Build WHERE clause
        where_conditions = ['active = TRUE']
        params = []
        
        if vehicle_class:
            where_conditions.append('vehicle_class = %s')
            params.append(vehicle_class)
            
        if coverage_level:
            where_conditions.append('coverage_level = %s')
            params.append(coverage_level)
        
        where_clause = ' AND '.join(where_conditions)
        
        # Get total count
        cursor.execute(f'''
            SELECT COUNT(*) 
            FROM vsc_rate_matrix 
            WHERE {where_clause};
        ''', params)
        total_count = cursor.fetchone()['count']
        
        # Get paginated results
        offset = (page - 1) * per_page
        cursor.execute(f'''
            SELECT id, vehicle_class, coverage_level, term_months,
                   mileage_range_key, min_mileage, max_mileage, rate_amount,
                   effective_date, created_at, updated_at
            FROM vsc_rate_matrix 
            WHERE {where_clause}
            ORDER BY vehicle_class, coverage_level, term_months, min_mileage
            LIMIT %s OFFSET %s;
        ''', params + [per_page, offset])
        
        rates = cursor.fetchall()
        
        # Convert to proper format
        rates_list = []
        for rate in rates:
            rate_dict = dict(rate)
            rate_dict['rate_amount'] = float(rate_dict['rate_amount'])
            rate_dict['effective_date'] = rate_dict['effective_date'].isoformat() if rate_dict['effective_date'] else None
            rate_dict['created_at'] = rate_dict['created_at'].isoformat() if rate_dict['created_at'] else None
            rate_dict['updated_at'] = rate_dict['updated_at'].isoformat() if rate_dict['updated_at'] else None
            rates_list.append(rate_dict)
        
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'rates': rates_list,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_count,
                'pages': (total_count + per_page - 1) // per_page
            },
            'filters': {
                'vehicle_class': vehicle_class,
                'coverage_level': coverage_level
            }
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to get VSC rates: {str(e)}")), 500


@app.route('/api/admin/vsc/rates/<int:rate_id>', methods=['GET'])
@token_required
@role_required('admin')
def get_vsc_rate(rate_id):
    """Get specific VSC rate by ID"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('''
            SELECT * FROM vsc_rate_matrix WHERE id = %s;
        ''', (rate_id,))
        
        rate = cursor.fetchone()
        if not rate:
            cursor.close()
            conn.close()
            return jsonify(error_response('Rate not found')), 404
        
        rate_dict = dict(rate)
        rate_dict['rate_amount'] = float(rate_dict['rate_amount'])
        rate_dict['effective_date'] = rate_dict['effective_date'].isoformat() if rate_dict['effective_date'] else None
        rate_dict['created_at'] = rate_dict['created_at'].isoformat() if rate_dict['created_at'] else None
        rate_dict['updated_at'] = rate_dict['updated_at'].isoformat() if rate_dict['updated_at'] else None
        
        cursor.close()
        conn.close()
        
        return jsonify(success_response({'rate': rate_dict}))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to get rate: {str(e)}")), 500


@app.route('/api/admin/vsc/rates', methods=['POST'])
@token_required
@role_required('admin')
def create_vsc_rate():
    """Create new VSC rate"""
    try:
        data = request.get_json()
        
        required_fields = ['vehicle_class', 'coverage_level', 'term_months', 
                          'mileage_range_key', 'min_mileage', 'max_mileage', 'rate_amount']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify(error_response(f"Missing fields: {', '.join(missing_fields)}")), 400
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check for duplicate
        cursor.execute('''
            SELECT id FROM vsc_rate_matrix 
            WHERE vehicle_class = %s AND coverage_level = %s 
            AND term_months = %s AND mileage_range_key = %s 
            AND effective_date = CURRENT_DATE;
        ''', (data['vehicle_class'], data['coverage_level'], 
              data['term_months'], data['mileage_range_key']))
        
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify(error_response('Rate already exists for this combination')), 409
        
        # Insert new rate
        cursor.execute('''
            INSERT INTO vsc_rate_matrix 
            (vehicle_class, coverage_level, term_months, mileage_range_key,
             min_mileage, max_mileage, rate_amount, effective_date, active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at;
        ''', (
            data['vehicle_class'], data['coverage_level'], data['term_months'],
            data['mileage_range_key'], data['min_mileage'], data['max_mileage'],
            data['rate_amount'], data.get('effective_date', 'CURRENT_DATE'),
            data.get('active', True)
        ))
        
        rate_id, created_at = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'message': 'VSC rate created successfully',
            'rate': {
                'id': rate_id,
                'created_at': created_at.isoformat(),
                **data
            }
        })), 201
        
    except Exception as e:
        return jsonify(error_response(f"Failed to create rate: {str(e)}")), 500


@app.route('/api/admin/vsc/rates/<int:rate_id>', methods=['PUT'])
@token_required
@role_required('admin')
def update_vsc_rate(rate_id):
    """Update existing VSC rate"""
    try:
        data = request.get_json()
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if rate exists
        cursor.execute('SELECT id FROM vsc_rate_matrix WHERE id = %s;', (rate_id,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify(error_response('Rate not found')), 404
        
        # Build dynamic UPDATE query
        update_fields = []
        params = []
        
        allowed_fields = ['vehicle_class', 'coverage_level', 'term_months', 
                         'mileage_range_key', 'min_mileage', 'max_mileage', 
                         'rate_amount', 'effective_date', 'active']
        
        for field in allowed_fields:
            if field in data:
                value = data[field]
                # Replace null with 0 for mileage fields
                if value is None and field in ['min_mileage', 'max_mileage']:
                    value = 0
                update_fields.append(f"{field} = %s")
                params.append(value)
        
        if not update_fields:
            cursor.close()
            conn.close()
            return jsonify(error_response('No valid fields to update')), 400
        
        # Add updated_at and rate_id
        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(rate_id)
        
        query = f"UPDATE vsc_rate_matrix SET {', '.join(update_fields)} WHERE id = %s RETURNING updated_at;"
        cursor.execute(query, params)
        
        updated_at = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'message': f'VSC rate {rate_id} updated successfully',
            'rate': {
                'id': rate_id,
                'updated_at': updated_at.isoformat(),
                **data
            }
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to update rate: {str(e)}")), 500


@app.route('/api/admin/vsc/rates/<int:rate_id>', methods=['DELETE'])
@token_required
@role_required('admin')
def delete_vsc_rate(rate_id):
    """Delete VSC rate (soft delete by setting active = false)"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if rate exists
        cursor.execute('''
            SELECT vehicle_class, coverage_level, term_months, mileage_range_key
            FROM vsc_rate_matrix WHERE id = %s;
        ''', (rate_id,))
        
        rate = cursor.fetchone()
        if not rate:
            cursor.close()
            conn.close()
            return jsonify(error_response('Rate not found')), 404
        
        # Soft delete (set active = false)
        cursor.execute('''
            UPDATE vsc_rate_matrix 
            SET active = FALSE, updated_at = CURRENT_TIMESTAMP 
            WHERE id = %s;
        ''', (rate_id,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'message': f'VSC rate {rate_id} deleted successfully',
            'deleted_rate': {
                'id': rate_id,
                'vehicle_class': rate[0],
                'coverage_level': rate[1], 
                'term_months': rate[2],
                'mileage_range_key': rate[3]
            }
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to delete rate: {str(e)}")), 500


@app.route('/api/admin/vsc/rates/bulk', methods=['POST'])
@token_required
@role_required('admin')
def bulk_import_vsc_rates():
    """Bulk import VSC rates from CSV or JSON data"""
    try:
        data = request.get_json()
        
        if 'rates' not in data or not isinstance(data['rates'], list):
            return jsonify(error_response('rates array is required')), 400
        
        rates_data = data['rates']
        if len(rates_data) > 1000:
            return jsonify(error_response('Maximum 1000 rates per bulk import')), 400
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Validate all rates first
        required_fields = ['vehicle_class', 'coverage_level', 'term_months', 
                          'mileage_range_key', 'min_mileage', 'max_mileage', 'rate_amount']
        
        for i, rate in enumerate(rates_data):
            missing_fields = [field for field in required_fields if field not in rate]
            if missing_fields:
                cursor.close()
                conn.close()
                return jsonify(error_response(f"Rate {i+1}: Missing fields: {', '.join(missing_fields)}")), 400
        
        # Prepare bulk insert data
        insert_data = []
        for rate in rates_data:
            insert_data.append((
                rate['vehicle_class'], rate['coverage_level'], rate['term_months'],
                rate['mileage_range_key'], rate['min_mileage'], rate['max_mileage'],
                rate['rate_amount'], rate.get('effective_date', 'CURRENT_DATE'),
                rate.get('active', True)
            ))
        
        # Bulk insert with conflict handling
        from psycopg2.extras import execute_values
        
        execute_values(cursor, '''
            INSERT INTO vsc_rate_matrix 
            (vehicle_class, coverage_level, term_months, mileage_range_key,
             min_mileage, max_mileage, rate_amount, effective_date, active)
            VALUES %s
            ON CONFLICT (vehicle_class, coverage_level, term_months, mileage_range_key, effective_date)
            DO UPDATE SET 
                rate_amount = EXCLUDED.rate_amount,
                updated_at = CURRENT_TIMESTAMP;
        ''', insert_data)
        
        imported_count = cursor.rowcount
        conn.commit()
        cursor.close() 
        conn.close()
        
        return jsonify(success_response({
            'message': f'Bulk import completed: {imported_count} rates processed',
            'imported_count': imported_count,
            'total_submitted': len(rates_data)
        })), 201
        
    except Exception as e:
        return jsonify(error_response(f"Bulk import failed: {str(e)}")), 500


@app.route('/api/admin/vsc/vehicle-classes', methods=['GET'])
@token_required  
@role_required('admin')
def get_admin_vehicle_classes():
    """Get all vehicle classifications for admin management"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('''
            SELECT id, make, vehicle_class, active, created_at, updated_at
            FROM vsc_vehicle_classes 
            ORDER BY vehicle_class, make;
        ''')
        
        classifications = cursor.fetchall()
        
        # Convert to proper format
        classifications_list = []
        for classification in classifications:
            class_dict = dict(classification)
            class_dict['created_at'] = class_dict['created_at'].isoformat() if class_dict['created_at'] else None
            class_dict['updated_at'] = class_dict['updated_at'].isoformat() if class_dict['updated_at'] else None
            classifications_list.append(class_dict)
        
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'vehicle_classifications': classifications_list,
            'total': len(classifications_list)
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to get vehicle classes: {str(e)}")), 500


@app.route('/api/admin/vsc/vehicle-classes', methods=['POST'])
@token_required
@role_required('admin') 
def create_vehicle_classification():
    """Create new vehicle classification"""
    try:
        data = request.get_json()
        
        required_fields = ['make', 'vehicle_class']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify(error_response(f"Missing fields: {', '.join(missing_fields)}")), 400
        
        if data['vehicle_class'] not in ['A', 'B', 'C']:
            return jsonify(error_response('vehicle_class must be A, B, or C')), 400
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check for duplicate
        cursor.execute('''
            SELECT id FROM vsc_vehicle_classes WHERE make = %s;
        ''', (data['make'],))
        
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify(error_response('Vehicle make already classified')), 409
        
        # Insert new classification
        cursor.execute('''
            INSERT INTO vsc_vehicle_classes (make, vehicle_class, active)
            VALUES (%s, %s, %s)
            RETURNING id, created_at;
        ''', (data['make'], data['vehicle_class'], data.get('active', True)))
        
        class_id, created_at = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'message': 'Vehicle classification created successfully',
            'classification': {
                'id': class_id,
                'created_at': created_at.isoformat(),
                **data
            }
        })), 201
        
    except Exception as e:
        return jsonify(error_response(f"Failed to create classification: {str(e)}")), 500


@app.route('/api/admin/vsc/vehicle-classes/<int:class_id>', methods=['PUT'])
@token_required
@role_required('admin')
def update_vehicle_classification(class_id):
    """Update vehicle classification"""
    try:
        data = request.get_json()
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if classification exists
        cursor.execute('SELECT id FROM vsc_vehicle_classes WHERE id = %s;', (class_id,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify(error_response('Classification not found')), 404
        
        # Build update query
        update_fields = []
        params = []
        
        allowed_fields = ['make', 'vehicle_class', 'active']
        
        for field in allowed_fields:
            if field in data:
                if field == 'vehicle_class' and data[field] not in ['A', 'B', 'C']:
                    cursor.close()
                    conn.close()
                    return jsonify(error_response('vehicle_class must be A, B, or C')), 400
                    
                update_fields.append(f"{field} = %s")
                params.append(data[field])
        
        if not update_fields:
            cursor.close()
            conn.close()
            return jsonify(error_response('No valid fields to update')), 400
        
        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(class_id)
        
        query = f"UPDATE vsc_vehicle_classes SET {', '.join(update_fields)} WHERE id = %s RETURNING updated_at;"
        cursor.execute(query, params)
        
        updated_at = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'message': f'Vehicle classification {class_id} updated successfully',
            'classification': {
                'id': class_id,
                'updated_at': updated_at.isoformat(),
                **data
            }
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to update classification: {str(e)}")), 500


@app.route('/api/admin/vsc/multipliers/<multiplier_type>', methods=['GET'])
@token_required
@role_required('admin')
def get_admin_multipliers(multiplier_type):
    """Get multipliers for admin management"""
    try:
        valid_types = ['term', 'deductible', 'mileage', 'age']
        if multiplier_type not in valid_types:
            return jsonify(error_response(f"Invalid multiplier type. Must be one of: {', '.join(valid_types)}")), 400
        
        table_name = f"vsc_{multiplier_type}_multipliers"
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(f'''
            SELECT * FROM {table_name} 
            ORDER BY display_order, id;
        ''')
        
        multipliers = cursor.fetchall()
        
        # Convert to proper format
        multipliers_list = []
        for multiplier in multipliers:
            mult_dict = dict(multiplier)
            mult_dict['multiplier'] = float(mult_dict['multiplier'])
            mult_dict['created_at'] = mult_dict['created_at'].isoformat() if mult_dict['created_at'] else None
            mult_dict['updated_at'] = mult_dict['updated_at'].isoformat() if mult_dict['updated_at'] else None
            multipliers_list.append(mult_dict)
        
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'multiplier_type': multiplier_type,
            'multipliers': multipliers_list,
            'total': len(multipliers_list)
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to get {multiplier_type} multipliers: {str(e)}")), 500


@app.route('/api/admin/vsc/multipliers/<multiplier_type>/<int:multiplier_id>', methods=['PUT'])
@token_required
@role_required('admin')
def update_multiplier(multiplier_type, multiplier_id):
    """Update specific multiplier"""
    try:
        valid_types = ['term', 'deductible', 'mileage', 'age']
        if multiplier_type not in valid_types:
            return jsonify(error_response(f"Invalid multiplier type. Must be one of: {', '.join(valid_types)}")), 400
        
        data = request.get_json()
        table_name = f"vsc_{multiplier_type}_multipliers"
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if multiplier exists
        cursor.execute(f'SELECT id FROM {table_name} WHERE id = %s;', (multiplier_id,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify(error_response('Multiplier not found')), 404
        
        # Build update query based on multiplier type
        update_fields = []
        params = []
        
        common_fields = ['multiplier', 'description', 'display_order', 'active']
        type_specific_fields = {
            'term': ['term_months'],
            'deductible': ['deductible_amount'],
            'mileage': ['category', 'min_mileage', 'max_mileage'],
            'age': ['category', 'min_age', 'max_age']
        }
        
        allowed_fields = common_fields + type_specific_fields.get(multiplier_type, [])
        
        for field in allowed_fields:
            if field in data:
                update_fields.append(f"{field} = %s")
                params.append(data[field])
        
        if not update_fields:
            cursor.close()
            conn.close()
            return jsonify(error_response('No valid fields to update')), 400
        
        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(multiplier_id)
        
        query = f"UPDATE {table_name} SET {', '.join(update_fields)} WHERE id = %s RETURNING updated_at;"
        cursor.execute(query, params)
        
        updated_at = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'message': f'{multiplier_type.title()} multiplier {multiplier_id} updated successfully',
            'multiplier': {
                'id': multiplier_id,
                'type': multiplier_type,
                'updated_at': updated_at.isoformat(),
                **data
            }
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to update {multiplier_type} multiplier: {str(e)}")), 500


@app.route('/api/admin/vsc/coverage-levels', methods=['GET'])
@token_required
@role_required('admin')
def get_admin_coverage_levels():
    """Get all coverage levels for admin management"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('''
            SELECT id, level_code, level_name, description, display_order, 
                   active, created_at, updated_at
            FROM vsc_coverage_levels 
            ORDER BY display_order, level_code;
        ''')
        
        coverage_levels = cursor.fetchall()
        
        # Convert to proper format
        levels_list = []
        for level in coverage_levels:
            level_dict = dict(level)
            level_dict['created_at'] = level_dict['created_at'].isoformat() if level_dict['created_at'] else None
            level_dict['updated_at'] = level_dict['updated_at'].isoformat() if level_dict['updated_at'] else None
            levels_list.append(level_dict)
        
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'coverage_levels': levels_list,
            'total': len(levels_list)
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to get coverage levels: {str(e)}")), 500


@app.route('/api/admin/vsc/coverage-levels', methods=['POST'])
@token_required
@role_required('admin')
def create_coverage_level():
    """Create new coverage level"""
    try:
        data = request.get_json()
        
        required_fields = ['level_code', 'level_name', 'description']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify(error_response(f"Missing fields: {', '.join(missing_fields)}")), 400
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check for duplicate
        cursor.execute('''
            SELECT id FROM vsc_coverage_levels WHERE level_code = %s;
        ''', (data['level_code'],))
        
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify(error_response('Coverage level code already exists')), 409
        
        # Insert new coverage level
        cursor.execute('''
            INSERT INTO vsc_coverage_levels 
            (level_code, level_name, description, display_order, active)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, created_at;
        ''', (
            data['level_code'], data['level_name'], data['description'],
            data.get('display_order', 999), data.get('active', True)
        ))
        
        level_id, created_at = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'message': 'Coverage level created successfully',
            'coverage_level': {
                'id': level_id,
                'created_at': created_at.isoformat(),
                **data
            }
        })), 201
        
    except Exception as e:
        return jsonify(error_response(f"Failed to create coverage level: {str(e)}")), 500


@app.route('/api/admin/vsc/coverage-levels/<int:level_id>', methods=['PUT'])
@token_required
@role_required('admin')
def update_coverage_level(level_id):
    """Update coverage level"""
    try:
        data = request.get_json()
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if level exists
        cursor.execute('SELECT id FROM vsc_coverage_levels WHERE id = %s;', (level_id,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify(error_response('Coverage level not found')), 404
        
        # Build update query
        update_fields = []
        params = []
        
        allowed_fields = ['level_code', 'level_name', 'description', 'display_order', 'active']
        
        for field in allowed_fields:
            if field in data:
                update_fields.append(f"{field} = %s")
                params.append(data[field])
        
        if not update_fields:
            cursor.close()
            conn.close()
            return jsonify(error_response('No valid fields to update')), 400
        
        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(level_id)
        
        query = f"UPDATE vsc_coverage_levels SET {', '.join(update_fields)} WHERE id = %s RETURNING updated_at;"
        cursor.execute(query, params)
        
        updated_at = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'message': f'Coverage level {level_id} updated successfully',
            'coverage_level': {
                'id': level_id,
                'updated_at': updated_at.isoformat(),
                **data
            }
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to update coverage level: {str(e)}")), 500


@app.route('/api/admin/vsc/base-rates', methods=['GET'])
@token_required
@role_required('admin')
def get_admin_base_rates():
    """Get all base rates for admin management"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('''
            SELECT id, vehicle_class, coverage_level, base_rate, 
                   effective_date, active, created_at, updated_at
            FROM vsc_base_rates 
            ORDER BY vehicle_class, coverage_level;
        ''')
        
        base_rates = cursor.fetchall()
        
        # Convert to proper format
        rates_list = []
        for rate in base_rates:
            rate_dict = dict(rate)
            rate_dict['base_rate'] = float(rate_dict['base_rate'])
            rate_dict['effective_date'] = rate_dict['effective_date'].isoformat() if rate_dict['effective_date'] else None
            rate_dict['created_at'] = rate_dict['created_at'].isoformat() if rate_dict['created_at'] else None
            rate_dict['updated_at'] = rate_dict['updated_at'].isoformat() if rate_dict['updated_at'] else None
            rates_list.append(rate_dict)
        
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'base_rates': rates_list,
            'total': len(rates_list)
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to get base rates: {str(e)}")), 500


@app.route('/api/admin/vsc/base-rates', methods=['POST'])
@token_required
@role_required('admin')
def create_base_rate():
    """Create new base rate"""
    try:
        data = request.get_json()
        
        required_fields = ['vehicle_class', 'coverage_level', 'base_rate']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify(error_response(f"Missing fields: {', '.join(missing_fields)}")), 400
        
        if data['vehicle_class'] not in ['A', 'B', 'C']:
            return jsonify(error_response('vehicle_class must be A, B, or C')), 400
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check for duplicate (same class, level, and effective date)
        effective_date = data.get('effective_date', 'CURRENT_DATE')
        cursor.execute('''
            SELECT id FROM vsc_base_rates 
            WHERE vehicle_class = %s AND coverage_level = %s AND effective_date = %s;
        ''', (data['vehicle_class'], data['coverage_level'], effective_date))
        
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify(error_response('Base rate already exists for this combination and date')), 409
        
        # Insert new base rate
        cursor.execute('''
            INSERT INTO vsc_base_rates 
            (vehicle_class, coverage_level, base_rate, effective_date, active)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, created_at;
        ''', (
            data['vehicle_class'], data['coverage_level'], data['base_rate'],
            effective_date, data.get('active', True)
        ))
        
        rate_id, created_at = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'message': 'Base rate created successfully',
            'base_rate': {
                'id': rate_id,
                'created_at': created_at.isoformat(),
                **data
            }
        })), 201
        
    except Exception as e:
        return jsonify(error_response(f"Failed to create base rate: {str(e)}")), 500


@app.route('/api/admin/vsc/base-rates/<int:rate_id>', methods=['PUT'])
@token_required
@role_required('admin')
def update_base_rate(rate_id):
    """Update base rate"""
    try:
        data = request.get_json()
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if rate exists
        cursor.execute('SELECT id FROM vsc_base_rates WHERE id = %s;', (rate_id,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify(error_response('Base rate not found')), 404
        
        # Build update query
        update_fields = []
        params = []
        
        allowed_fields = ['vehicle_class', 'coverage_level', 'base_rate', 'effective_date', 'active']
        
        for field in allowed_fields:
            if field in data:
                if field == 'vehicle_class' and data[field] not in ['A', 'B', 'C']:
                    cursor.close()
                    conn.close()
                    return jsonify(error_response('vehicle_class must be A, B, or C')), 400
                    
                update_fields.append(f"{field} = %s")
                params.append(data[field])
        
        if not update_fields:
            cursor.close()
            conn.close()
            return jsonify(error_response('No valid fields to update')), 400
        
        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(rate_id)
        
        query = f"UPDATE vsc_base_rates SET {', '.join(update_fields)} WHERE id = %s RETURNING updated_at;"
        cursor.execute(query, params)
        
        updated_at = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'message': f'Base rate {rate_id} updated successfully',
            'base_rate': {
                'id': rate_id,
                'updated_at': updated_at.isoformat(),
                **data
            }
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to update base rate: {str(e)}")), 500


# ================================
# VSC ANALYTICS & REPORTING ENDPOINTS
# ================================

@app.route('/api/admin/vsc/analytics/rates-summary', methods=['GET'])
@token_required
@role_required('admin')
def get_vsc_rates_analytics():
    """Get VSC rates analytics summary"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Get overall statistics
        cursor.execute('''
            SELECT 
                COUNT(*) as total_rates,
                COUNT(DISTINCT vehicle_class) as vehicle_classes,
                COUNT(DISTINCT coverage_level) as coverage_levels,
                COUNT(DISTINCT term_months) as term_options,
                MIN(rate_amount) as min_rate,
                MAX(rate_amount) as max_rate,
                AVG(rate_amount) as avg_rate
            FROM vsc_rate_matrix 
            WHERE active = TRUE;
        ''')
        
        summary = cursor.fetchone()
        
        # Get rates by vehicle class
        cursor.execute('''
            SELECT vehicle_class, 
                   COUNT(*) as rate_count,
                   MIN(rate_amount) as min_rate,
                   MAX(rate_amount) as max_rate,
                   AVG(rate_amount) as avg_rate
            FROM vsc_rate_matrix 
            WHERE active = TRUE
            GROUP BY vehicle_class
            ORDER BY vehicle_class;
        ''')
        
        class_breakdown = cursor.fetchall()
        
        # Get rates by coverage level
        cursor.execute('''
            SELECT coverage_level,
                   COUNT(*) as rate_count,
                   MIN(rate_amount) as min_rate,
                   MAX(rate_amount) as max_rate,
                   AVG(rate_amount) as avg_rate
            FROM vsc_rate_matrix 
            WHERE active = TRUE
            GROUP BY coverage_level
            ORDER BY coverage_level;
        ''')
        
        coverage_breakdown = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        analytics_data = {
            'summary': {
                'total_rates': summary[0],
                'vehicle_classes': summary[1],
                'coverage_levels': summary[2], 
                'term_options': summary[3],
                'rate_range': {
                    'min': float(summary[4]) if summary[4] else 0,
                    'max': float(summary[5]) if summary[5] else 0,
                    'average': round(float(summary[6]), 2) if summary[6] else 0
                }
            },
            'by_vehicle_class': [
                {
                    'class': row[0],
                    'rate_count': row[1],
                    'min_rate': float(row[2]),
                    'max_rate': float(row[3]),
                    'avg_rate': round(float(row[4]), 2)
                } for row in class_breakdown
            ],
            'by_coverage_level': [
                {
                    'level': row[0],
                    'rate_count': row[1],
                    'min_rate': float(row[2]),
                    'max_rate': float(row[3]),
                    'avg_rate': round(float(row[4]), 2)
                } for row in coverage_breakdown
            ]
        }
        
        return jsonify(success_response(analytics_data))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to get VSC analytics: {str(e)}")), 500


@app.route('/api/admin/vsc/export/rates', methods=['GET'])
@token_required
@role_required('admin')
def export_vsc_rates():
    """Export VSC rates in CSV format"""
    try:
        export_format = request.args.get('format', 'csv')
        vehicle_class = request.args.get('vehicle_class')
        coverage_level = request.args.get('coverage_level')
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Build WHERE clause
        where_conditions = ['active = TRUE']
        params = []
        
        if vehicle_class:
            where_conditions.append('vehicle_class = %s')
            params.append(vehicle_class)
            
        if coverage_level:
            where_conditions.append('coverage_level = %s')
            params.append(coverage_level)
        
        where_clause = ' AND '.join(where_conditions)
        
        cursor.execute(f'''
            SELECT vehicle_class, coverage_level, term_months, mileage_range_key,
                   min_mileage, max_mileage, rate_amount, effective_date
            FROM vsc_rate_matrix 
            WHERE {where_clause}
            ORDER BY vehicle_class, coverage_level, term_months, min_mileage;
        ''', params)
        
        rates = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if export_format == 'csv':
            import csv
            from io import StringIO
            
            output = StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow([
                'Vehicle Class', 'Coverage Level', 'Term (Months)', 'Mileage Range',
                'Min Mileage', 'Max Mileage', 'Rate Amount', 'Effective Date'
            ])
            
            # Write data
            for rate in rates:
                writer.writerow([
                    rate[0], rate[1], rate[2], rate[3],
                    rate[4], rate[5], float(rate[6]),
                    rate[7].isoformat() if rate[7] else ''
                ])
            
            csv_content = output.getvalue()
            output.close()
            
            response = make_response(csv_content)
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = f'attachment; filename=vsc_rates_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}.csv'
            return response
            
        else:  # JSON format
            rates_data = []
            for rate in rates:
                rates_data.append({
                    'vehicle_class': rate[0],
                    'coverage_level': rate[1],
                    'term_months': rate[2],
                    'mileage_range_key': rate[3],
                    'min_mileage': rate[4],
                    'max_mileage': rate[5],
                    'rate_amount': float(rate[6]),
                    'effective_date': rate[7].isoformat() if rate[7] else None
                })
            
            return jsonify(success_response({
                'rates': rates_data,
                'export_info': {
                    'total_records': len(rates_data),
                    'filters': {
                        'vehicle_class': vehicle_class,
                        'coverage_level': coverage_level
                    },
                    'exported_at': datetime.now(timezone.utc).isoformat() + 'Z'
                }
            }))
            
    except Exception as e:
        return jsonify(error_response(f"Export failed: {str(e)}")), 500


@app.route('/api/admin/vsc/import/rates', methods=['POST'])
@token_required
@role_required('admin')
def import_vsc_rates_csv():
    """Import VSC rates from uploaded CSV file"""
    try:
        if 'file' not in request.files:
            return jsonify(error_response('No file uploaded')), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify(error_response('No file selected')), 400
        
        if not file.filename.lower().endswith('.csv'):
            return jsonify(error_response('File must be CSV format')), 400
        
        import csv
        from io import StringIO
        
        # Read and parse CSV
        csv_content = file.read().decode('utf-8')
        csv_reader = csv.DictReader(StringIO(csv_content))
        
        rates_data = []
        errors = []
        
        required_columns = ['vehicle_class', 'coverage_level', 'term_months', 
                           'mileage_range_key', 'min_mileage', 'max_mileage', 'rate_amount']
        
        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 because row 1 is header
            # Validate required columns
            missing_cols = [col for col in required_columns if not row.get(col)]
            if missing_cols:
                errors.append(f"Row {row_num}: Missing columns: {', '.join(missing_cols)}")
                continue
            
            # Validate data types and values
            try:
                rate_data = {
                    'vehicle_class': row['vehicle_class'].strip().upper(),
                    'coverage_level': row['coverage_level'].strip().lower(),
                    'term_months': int(row['term_months']),
                    'mileage_range_key': row['mileage_range_key'].strip(),
                    'min_mileage': int(row['min_mileage']),
                    'max_mileage': int(row['max_mileage']),
                    'rate_amount': float(row['rate_amount']),
                    'effective_date': row.get('effective_date', 'CURRENT_DATE'),
                    'active': row.get('active', 'true').lower() in ['true', '1', 'yes']
                }
                
                # Validate vehicle class
                if rate_data['vehicle_class'] not in ['A', 'B', 'C']:
                    errors.append(f"Row {row_num}: Invalid vehicle_class '{rate_data['vehicle_class']}' (must be A, B, or C)")
                    continue
                
                rates_data.append(rate_data)
                
            except (ValueError, TypeError) as e:
                errors.append(f"Row {row_num}: Data validation error - {str(e)}")
                continue
        
        if errors:
            return jsonify(error_response({
                'message': 'CSV validation failed',
                'errors': errors[:10],  # Limit to first 10 errors
                'total_errors': len(errors)
            })), 400
        
        if not rates_data:
            return jsonify(error_response('No valid data found in CSV')), 400
        
        # Import data to database
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Prepare bulk insert
        insert_data = []
        for rate in rates_data:
            insert_data.append((
                rate['vehicle_class'], rate['coverage_level'], rate['term_months'],
                rate['mileage_range_key'], rate['min_mileage'], rate['max_mileage'],
                rate['rate_amount'], rate['effective_date'], rate['active']
            ))
        
        from psycopg2.extras import execute_values
        
        execute_values(cursor, '''
            INSERT INTO vsc_rate_matrix 
            (vehicle_class, coverage_level, term_months, mileage_range_key,
             min_mileage, max_mileage, rate_amount, effective_date, active)
            VALUES %s
            ON CONFLICT (vehicle_class, coverage_level, term_months, mileage_range_key, effective_date)
            DO UPDATE SET 
                rate_amount = EXCLUDED.rate_amount,
                updated_at = CURRENT_TIMESTAMP;
        ''', insert_data)
        
        imported_count = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'message': f'CSV import completed successfully',
            'imported_count': imported_count,
            'total_rows_processed': len(rates_data),
            'import_summary': {
                'successful_imports': imported_count,
                'validation_errors': len(errors)
            }
        })), 201
        
    except Exception as e:
        return jsonify(error_response(f"CSV import failed: {str(e)}")), 500


# ================================
# VSC CACHE MANAGEMENT ENDPOINTS  
# ================================

@app.route('/api/admin/vsc/cache/clear', methods=['POST'])
@token_required
@role_required('admin')
def clear_vsc_cache():
    """Clear VSC rate manager cache"""
    try:
        from data.vsc_rates_data import rate_manager
        
        # Clear all cached data
        cache_methods = [
            'get_vehicle_classification',
            'get_coverage_levels', 
            'get_term_multipliers',
            'get_deductible_multipliers',
            'get_mileage_multipliers',
            'get_age_multipliers'
        ]
        
        cleared_caches = []
        for method_name in cache_methods:
            method = getattr(rate_manager, method_name, None)
            if method and hasattr(method, 'cache_clear'):
                method.cache_clear()
                cleared_caches.append(method_name)
        
        return jsonify(success_response({
            'message': 'VSC cache cleared successfully',
            'cleared_caches': cleared_caches,
            'cache_clear_time': datetime.now(timezone.utc).isoformat() + 'Z'
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to clear cache: {str(e)}")), 500


@app.route('/api/admin/vsc/cache/status', methods=['GET'])
@token_required
@role_required('admin')
def get_vsc_cache_status():
    """Get VSC cache status information"""
    try:
        from data.vsc_rates_data import rate_manager
        
        cache_info = {}
        cache_methods = [
            'get_vehicle_classification',
            'get_coverage_levels',
            'get_term_multipliers', 
            'get_deductible_multipliers',
            'get_mileage_multipliers',
            'get_age_multipliers'
        ]
        
        for method_name in cache_methods:
            method = getattr(rate_manager, method_name, None)
            if method and hasattr(method, 'cache_info'):
                info = method.cache_info()
                cache_info[method_name] = {
                    'hits': info.hits,
                    'misses': info.misses,
                    'current_size': info.currsize,
                    'max_size': info.maxsize
                }
        
        return jsonify(success_response({
            'cache_status': cache_info,
            'database_integration': True,
            'status_check_time': datetime.now(timezone.utc).isoformat() + 'Z'
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to get cache status: {str(e)}")), 500
    
# ================================
# ENHANCED PRODUCT MANAGEMENT ENDPOINTS
# ================================

@app.route('/api/admin/products/<product_code>', methods=['PUT'])
@token_required
@role_required('admin')
def update_product_by_code(product_code):
    """Update existing product by product code"""
    try:
        data = request.get_json()
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if product exists
        cursor.execute('SELECT id FROM products WHERE product_code = %s;', (product_code,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify(error_response('Product not found')), 404
        
        # Build dynamic UPDATE query
        update_fields = []
        params = []
        # Only include fields that actually exist in the products table
        allowed_fields = ['product_name', 'base_price', 'active']
        
        for field in allowed_fields:
            if field in data:
                update_fields.append(f"{field} = %s")
                params.append(data[field])
        
        if not update_fields:
            cursor.close()
            conn.close()
            return jsonify(error_response('No valid fields to update')), 400
        
        # Add product_code for WHERE clause
        params.append(product_code)
        
        query = f"UPDATE products SET {', '.join(update_fields)} WHERE product_code = %s;"
        cursor.execute(query, params)
        
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify(success_response({
            'message': f'Product {product_code} updated successfully',
            'product': {
                'product_code': product_code,
                **data
            }
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to update product: {str(e)}")), 500


@app.route('/api/admin/products/<product_code>', methods=['DELETE'])
@token_required
@role_required('admin')
def delete_product_by_code(product_code):
    """Delete product and its pricing by product code"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if product exists
        cursor.execute('SELECT product_name FROM products WHERE product_code = %s;', (product_code,))
        product = cursor.fetchone()
        if not product:
            cursor.close()
            conn.close()
            return jsonify(error_response('Product not found')), 404
        
        product_name = product[0]
        
        # Delete pricing first (foreign key constraint)
        cursor.execute('DELETE FROM pricing WHERE product_code = %s;', (product_code,))
        
        # Delete product
        cursor.execute('DELETE FROM products WHERE product_code = %s;', (product_code,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'message': f'Product "{product_name}" and its pricing deleted successfully'
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to delete product: {str(e)}")), 500


@app.route('/api/admin/products/<product_code>/pricing', methods=['GET'])
@token_required
@role_required('admin')
def get_admin_product_pricing(product_code):
    """Get detailed pricing for a specific product with current system settings"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Get product base info
        cursor.execute('''
            SELECT product_name, base_price, active
            FROM products 
            WHERE product_code = %s;
        ''', (product_code,))
        
        product_result = cursor.fetchone()
        if not product_result:
            return jsonify(error_response("Product not found")), 404

        product_name, base_price, active = product_result

        # Get pricing data
        cursor.execute('''
            SELECT term_years, multiplier, customer_type
            FROM pricing 
            WHERE product_code = %s
            ORDER BY term_years, customer_type;
        ''', (product_code,))

        pricing_data = {}
        for term_years, multiplier, customer_type in cursor.fetchall():
            if term_years not in pricing_data:
                pricing_data[term_years] = {}
            pricing_data[term_years][customer_type] = {
                'multiplier': float(multiplier),
                'price': float(base_price * multiplier)
            }

        # Get current system settings
        if settings_service.connection_available:
            system_settings = {
                'admin_fee': get_admin_fee('hero'),
                'wholesale_discount_rate': get_wholesale_discount(),
                'tax_rate': get_tax_rate(),
                'processing_fee': get_processing_fee(),
                'database_driven': True
            }
        else:
            system_settings = {
                'admin_fee': 25.00,
                'wholesale_discount_rate': 0.15,
                'tax_rate': 0.08,
                'processing_fee': 15.00,
                'database_driven': False
            }

        cursor.close()
        conn.close()

        return jsonify(success_response({
            'product_code': product_code,
            'product_name': product_name,
            'base_price': float(base_price),
            'active': active,
            'pricing': pricing_data,
            'system_settings': system_settings
        }))

    except Exception as e:
        print(f"Get pricing error: {str(e)}")
        return jsonify(error_response(f"Failed to get pricing: {str(e)}")), 500


@app.route('/api/admin/products/<product_code>/pricing/bulk', methods=['PUT'])
@token_required
@role_required('admin')
def bulk_update_product_pricing(product_code):
    """Bulk update all pricing for a specific product"""
    try:
        data = request.get_json()
        
        if 'base_price' not in data or 'pricing' not in data:
            return jsonify(error_response('base_price and pricing are required')), 400
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if product exists and update base price
        cursor.execute('''
            UPDATE products 
            SET base_price = %s, updated_at = CURRENT_TIMESTAMP 
            WHERE product_code = %s
            RETURNING id;
        ''', (data['base_price'], product_code))
        
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify(error_response('Product not found')), 404
        
        # Delete existing pricing for this product
        cursor.execute('DELETE FROM pricing WHERE product_code = %s;', (product_code,))
        
        # Insert new pricing
        pricing_data = []
        for term_str, customer_types in data['pricing'].items():
            term = int(term_str)
            for customer_type, multiplier in customer_types.items():
                pricing_data.append((product_code, term, float(multiplier), customer_type))
        
        if pricing_data:
            from psycopg2.extras import execute_values
            execute_values(cursor, '''
                INSERT INTO pricing (product_code, term_years, multiplier, customer_type)
                VALUES %s;
            ''', pricing_data)
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'message': f'Pricing updated for {product_code}',
            'updated_base_price': data['base_price'],
            'updated_pricing_records': len(pricing_data)
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to bulk update pricing: {str(e)}")), 500


@app.route('/api/admin/products/search', methods=['GET'])
@token_required
@role_required('admin')
def search_products():
    """Search products by name, code, or category"""
    try:
        search_term = request.args.get('q', '').strip()
        category = request.args.get('category', '')
        active_only = request.args.get('active_only', 'false').lower() == 'true'
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Build WHERE clause
        where_conditions = []
        params = []
        
        if search_term:
            where_conditions.append('''
                (LOWER(product_name) LIKE %s OR 
                 LOWER(product_code) LIKE %s OR 
                 LOWER(description) LIKE %s)
            ''')
            search_pattern = f'%{search_term.lower()}%'
            params.extend([search_pattern, search_pattern, search_pattern])
        
        if category:
            # Map category to product code patterns
            category_patterns = {
                'home_protection': '%HOME%',
                'auto_protection': '%AUTO%',
                'deductible_reimbursement': '%DEDUCTIBLE%'
            }
            if category in category_patterns:
                where_conditions.append('product_code LIKE %s')
                params.append(category_patterns[category])
        
        if active_only:
            where_conditions.append('active = true')
        
        where_clause = ' AND '.join(where_conditions) if where_conditions else 'TRUE'
        
        cursor.execute(f'''
            SELECT 
                p.id,
                p.product_code,
                p.product_name,
                p.description,
                p.base_price,
                p.active,
                p.created_at,
                COUNT(pr.id) as pricing_count,
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
                COALESCE(
                    ARRAY_AGG(DISTINCT pr.term_years ORDER BY pr.term_years) 
                    FILTER (WHERE pr.customer_type = 'retail'),
                    ARRAY[]::integer[]
                ) as terms_available
            FROM products p
            LEFT JOIN pricing pr ON p.product_code = pr.product_code
            WHERE {where_clause}
            GROUP BY p.id, p.product_code, p.product_name, p.description, p.base_price, p.active, p.created_at
            ORDER BY p.product_name;
        ''', params)
        
        products = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Convert to proper format
        products_list = []
        for product in products:
            product_dict = dict(product)
            product_dict['base_price'] = float(product_dict['base_price'])
            product_dict['min_price'] = float(product_dict['min_price'])
            product_dict['max_price'] = float(product_dict['max_price'])
            product_dict['created_at'] = product_dict['created_at'].isoformat() if product_dict['created_at'] else None
            products_list.append(product_dict)
        
        return jsonify(success_response({
            'products': products_list,
            'total': len(products_list),
            'search_criteria': {
                'search_term': search_term,
                'category': category,
                'active_only': active_only
            }
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Search failed: {str(e)}")), 500


@app.route('/api/admin/products/categories', methods=['GET'])
def get_product_categories():
    """Get available product categories"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                CASE 
                    WHEN product_code LIKE '%HOME%' THEN 'home_protection'
                    WHEN product_code LIKE '%AUTO%' AND product_code NOT LIKE '%DEDUCTIBLE%' THEN 'auto_protection'
                    WHEN product_code LIKE '%DEDUCTIBLE%' THEN 'deductible_reimbursement'
                    ELSE 'other'
                END as category,
                COUNT(*) as product_count
            FROM products 
            WHERE active = true
            GROUP BY category
            ORDER BY category;
        ''')
        
        categories = cursor.fetchall()
        cursor.close()
        conn.close()
        
        category_data = {
            'categories': [
                {
                    'code': cat[0],
                    'name': cat[0].replace('_', ' ').title(),
                    'product_count': cat[1]
                }
                for cat in categories
            ],
            'total_categories': len(categories)
        }
        
        return jsonify(success_response(category_data))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to get categories: {str(e)}")), 500


@app.route('/api/admin/products/stats', methods=['GET'])
@token_required
@role_required('admin')
def get_product_stats():
    """Get product management statistics"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Get overall stats
        cursor.execute('''
            SELECT 
                COUNT(*) as total_products,
                COUNT(*) FILTER (WHERE active = true) as active_products,
                COUNT(*) FILTER (WHERE active = false) as inactive_products,
                AVG(base_price) as avg_base_price,
                MIN(base_price) as min_base_price,
                MAX(base_price) as max_base_price
            FROM products;
        ''')
        
        overall_stats = cursor.fetchone()
        
        # Get pricing stats
        cursor.execute('''
            SELECT 
                COUNT(DISTINCT product_code) as products_with_pricing,
                COUNT(*) as total_pricing_records,
                COUNT(DISTINCT term_years) as unique_terms,
                COUNT(DISTINCT customer_type) as customer_types
            FROM pricing;
        ''')
        
        pricing_stats = cursor.fetchone()
        
        # Get recent activity
        cursor.execute('''
            SELECT 
                product_code,
                product_name,
                updated_at
            FROM products 
            WHERE updated_at IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 5;
        ''')
        
        recent_updates = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        stats = {
            'overview': {
                'total_products': overall_stats[0] or 0,
                'active_products': overall_stats[1] or 0,
                'inactive_products': overall_stats[2] or 0,
                'avg_base_price': round(float(overall_stats[3]), 2) if overall_stats[3] else 0,
                'price_range': {
                    'min': float(overall_stats[4]) if overall_stats[4] else 0,
                    'max': float(overall_stats[5]) if overall_stats[5] else 0
                }
            },
            'pricing': {
                'products_with_pricing': pricing_stats[0] or 0,
                'total_pricing_records': pricing_stats[1] or 0,
                'unique_terms': pricing_stats[2] or 0,
                'customer_types': pricing_stats[3] or 0
            },
            'recent_activity': [
                {
                    'product_code': update[0],
                    'product_name': update[1],
                    'updated_at': update[2].isoformat() if update[2] else None
                }
                for update in recent_updates
            ]
        }
        
        return jsonify(success_response(stats))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to get stats: {str(e)}")), 500


@app.route('/api/admin/products/export', methods=['GET'])
@token_required
@role_required('admin')
def export_products():
    """Export products and pricing data"""
    try:
        export_format = request.args.get('format', 'csv')
        include_pricing = request.args.get('include_pricing', 'true').lower() == 'true'
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        if include_pricing:
            cursor.execute('''
                SELECT 
                    p.product_code,
                    p.product_name,
                    p.description,
                    p.base_price,
                    p.active,
                    pr.term_years,
                    pr.customer_type,
                    pr.multiplier,
                    ROUND(p.base_price * pr.multiplier, 2) as calculated_price,
                    p.created_at
                FROM products p
                LEFT JOIN pricing pr ON p.product_code = pr.product_code
                ORDER BY p.product_code, pr.term_years, pr.customer_type;
            ''')
        else:
            cursor.execute('''
                SELECT 
                    product_code,
                    product_name,
                    description,
                    base_price,
                    active,
                    created_at
                FROM products
                ORDER BY product_code;
            ''')
        
        data = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if export_format == 'csv':
            import csv
            from io import StringIO
            
            output = StringIO()
            writer = csv.writer(output)
            
            # Write header
            if include_pricing:
                writer.writerow([
                    'Product Code', 'Product Name', 'Description', 'Base Price', 'Active',
                    'Term Years', 'Customer Type', 'Multiplier', 'Calculated Price', 'Created At'
                ])
            else:
                writer.writerow([
                    'Product Code', 'Product Name', 'Description', 'Base Price', 'Active', 'Created At'
                ])
            
            # Write data
            for row in data:
                if include_pricing:
                    writer.writerow([
                        row[0], row[1], row[2], float(row[3]), row[4],
                        row[5] if row[5] else '', row[6] if row[6] else '',
                        float(row[7]) if row[7] else '', float(row[8]) if row[8] else '',
                        row[9].isoformat() if row[9] else ''
                    ])
                else:
                    writer.writerow([
                        row[0], row[1], row[2], float(row[3]), row[4],
                        row[5].isoformat() if row[5] else ''
                    ])
            
            csv_content = output.getvalue()
            output.close()
            
            response = make_response(csv_content)
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = f'attachment; filename=products_export_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}.csv'
            return response
            
        else:  # JSON format
            export_data = []
            if include_pricing:
                # Group by product for better JSON structure
                products = {}
                for row in data:
                    product_code = row[0]
                    if product_code not in products:
                        products[product_code] = {
                            'product_code': row[0],
                            'product_name': row[1],
                            'description': row[2],
                            'base_price': float(row[3]),
                            'active': row[4],
                            'created_at': row[9].isoformat() if row[9] else None,
                            'pricing': []
                        }
                    
                    if row[5]:  # Has pricing data
                        products[product_code]['pricing'].append({
                            'term_years': row[5],
                            'customer_type': row[6],
                            'multiplier': float(row[7]),
                            'calculated_price': float(row[8])
                        })
                
                export_data = list(products.values())
            else:
                export_data = [
                    {
                        'product_code': row[0],
                        'product_name': row[1],
                        'description': row[2],
                        'base_price': float(row[3]),
                        'active': row[4],
                        'created_at': row[5].isoformat() if row[5] else None
                    }
                    for row in data
                ]
            
            return jsonify(success_response({
                'products': export_data,
                'export_info': {
                    'total_records': len(export_data),
                    'include_pricing': include_pricing,
                    'exported_at': datetime.now(timezone.utc).isoformat() + 'Z'
                }
            }))
            
    except Exception as e:
        return jsonify(error_response(f"Export failed: {str(e)}")), 500


@app.route('/api/admin/products/import', methods=['POST'])
@token_required
@role_required('admin')
def import_products():
    """Import products from CSV file"""
    try:
        if 'file' not in request.files:
            return jsonify(error_response('No file uploaded')), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify(error_response('No file selected')), 400
        
        if not file.filename.lower().endswith('.csv'):
            return jsonify(error_response('File must be CSV format')), 400
        
        import csv
        from io import StringIO
        
        # Read and parse CSV
        csv_content = file.read().decode('utf-8')
        csv_reader = csv.DictReader(StringIO(csv_content))
        
        products_data = []
        pricing_data = []
        errors = []
        
        required_product_columns = ['product_code', 'product_name', 'base_price']
        
        for row_num, row in enumerate(csv_reader, start=2):
            # Validate required columns
            missing_cols = [col for col in required_product_columns if not row.get(col)]
            if missing_cols:
                errors.append(f"Row {row_num}: Missing columns: {', '.join(missing_cols)}")
                continue
            
            try:
                # Process product data
                product_data = {
                    'product_code': row['product_code'].strip().upper(),
                    'product_name': row['product_name'].strip(),
                    'description': row.get('description', '').strip(),
                    'base_price': float(row['base_price']),
                    'active': row.get('active', 'true').lower() in ['true', '1', 'yes']
                }
                
                # Check if this product is already in our list
                existing_product = next((p for p in products_data if p['product_code'] == product_data['product_code']), None)
                if not existing_product:
                    products_data.append(product_data)
                
                # Process pricing data if available
                if row.get('term_years') and row.get('customer_type') and row.get('multiplier'):
                    pricing_item = {
                        'product_code': product_data['product_code'],
                        'term_years': int(row['term_years']),
                        'customer_type': row['customer_type'].strip().lower(),
                        'multiplier': float(row['multiplier'])
                    }
                    pricing_data.append(pricing_item)
                
            except (ValueError, TypeError) as e:
                errors.append(f"Row {row_num}: Data validation error - {str(e)}")
                continue
        
        if errors:
            return jsonify(error_response({
                'message': 'CSV validation failed',
                'errors': errors[:10],  # Limit to first 10 errors
                'total_errors': len(errors)
            })), 400
        
        if not products_data:
            return jsonify(error_response('No valid product data found in CSV')), 400
        
        # Import data to database
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        try:
            # Import products
            product_count = 0
            for product in products_data:
                cursor.execute('''
                    INSERT INTO products (product_code, product_name, description, base_price, active)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (product_code) 
                    DO UPDATE SET 
                        product_name = EXCLUDED.product_name,
                        description = EXCLUDED.description,
                        base_price = EXCLUDED.base_price,
                        active = EXCLUDED.active,
                        updated_at = CURRENT_TIMESTAMP;
                ''', (
                    product['product_code'], product['product_name'],
                    product['description'], product['base_price'], product['active']
                ))
                product_count += 1
            
            # Import pricing if available
            pricing_count = 0
            if pricing_data:
                for pricing in pricing_data:
                    cursor.execute('''
                        INSERT INTO pricing (product_code, term_years, customer_type, multiplier)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (product_code, term_years, customer_type)
                        DO UPDATE SET 
                            multiplier = EXCLUDED.multiplier,
                            updated_at = CURRENT_TIMESTAMP;
                    ''', (
                        pricing['product_code'], pricing['term_years'],
                        pricing['customer_type'], pricing['multiplier']
                    ))
                    pricing_count += 1
            
            conn.commit()
            
            return jsonify(success_response({
                'message': 'CSV import completed successfully',
                'import_summary': {
                    'products_imported': product_count,
                    'pricing_records_imported': pricing_count,
                    'total_rows_processed': len(products_data),
                    'validation_errors': len(errors)
                }
            })), 201
            
        except Exception as db_error:
            conn.rollback()
            raise db_error
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        return jsonify(error_response(f"CSV import failed: {str(e)}")), 500


@app.route('/api/admin/products/validate', methods=['POST'])
@token_required
@role_required('admin')
def validate_product_data():
    """Validate product data before saving"""
    try:
        data = request.get_json()
        
        errors = []
        warnings = []
        
        # Validate product code
        if not data.get('product_code'):
            errors.append('Product code is required')
        elif len(data['product_code']) < 3:
            errors.append('Product code must be at least 3 characters')
        else:
            # Check if product code already exists (for new products)
            if not data.get('is_edit', False):
                conn = psycopg2.connect(DATABASE_URL)
                cursor = conn.cursor()
                cursor.execute('SELECT product_code FROM products WHERE product_code = %s;', (data['product_code'],))
                if cursor.fetchone():
                    errors.append('Product code already exists')
                cursor.close()
                conn.close()
        
        # Validate product name
        if not data.get('product_name'):
            errors.append('Product name is required')
        elif len(data['product_name']) < 3:
            errors.append('Product name must be at least 3 characters')
        
        # Validate base price
        try:
            base_price = float(data.get('base_price', 0))
            if base_price <= 0:
                errors.append('Base price must be greater than 0')
            elif base_price > 10000:
                warnings.append('Base price is unusually high (over $10,000)')
        except (ValueError, TypeError):
            errors.append('Base price must be a valid number')
        
        # Validate pricing structure if provided
        if data.get('pricing'):
            for term, customer_types in data['pricing'].items():
                try:
                    term_int = int(term)
                    if term_int < 1 or term_int > 10:
                        warnings.append(f'Unusual term length: {term_int} years')
                except ValueError:
                    errors.append(f'Invalid term: {term}')
                
                for customer_type, multiplier in customer_types.items():
                    if customer_type not in ['retail', 'wholesale']:
                        warnings.append(f'Unusual customer type: {customer_type}')
                    
                    try:
                        mult_float = float(multiplier)
                        if mult_float <= 0:
                            errors.append(f'Multiplier must be positive for {term} year {customer_type}')
                        elif mult_float > 10:
                            warnings.append(f'High multiplier ({mult_float}) for {term} year {customer_type}')
                    except (ValueError, TypeError):
                        errors.append(f'Invalid multiplier for {term} year {customer_type}')
        
        validation_result = {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'suggestions': []
        }
        
        # Add suggestions
        if not errors:
            if data.get('product_code') and not data['product_code'].isupper():
                validation_result['suggestions'].append('Consider using uppercase for product code')
            
            if data.get('pricing') and 'wholesale' not in str(data['pricing']):
                validation_result['suggestions'].append('Consider adding wholesale pricing')
        
        return jsonify(success_response(validation_result))
        
    except Exception as e:
        return jsonify(error_response(f"Validation failed: {str(e)}")), 500


# ================================
# PRODUCT CLONING AND TEMPLATES
# ================================

@app.route('/api/admin/products/<product_code>/clone', methods=['POST'])
@token_required
@role_required('admin')
def clone_product(product_code):
    """Clone an existing product with new product code"""
    try:
        data = request.get_json()
        new_product_code = data.get('new_product_code')
        
        if not new_product_code:
            return jsonify(error_response('new_product_code is required')), 400
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if source product exists
        cursor.execute('''
            SELECT product_name, description, base_price, active 
            FROM products 
            WHERE product_code = %s;
        ''', (product_code,))
        
        source_product = cursor.fetchone()
        if not source_product:
            cursor.close()
            conn.close()
            return jsonify(error_response('Source product not found')), 404
        
        # Check if new product code already exists
        cursor.execute('SELECT product_code FROM products WHERE product_code = %s;', (new_product_code,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify(error_response('New product code already exists')), 409
        
        # Clone the product
        new_name = data.get('new_name', f"{source_product[0]} (Copy)")
        cursor.execute('''
            INSERT INTO products (product_code, product_name, description, base_price, active)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        ''', (new_product_code, new_name, source_product[2], source_product[3], source_product[4]))
        
        new_product_id = cursor.fetchone()[0]
        
        # Clone pricing if requested
        if data.get('clone_pricing', True):
            cursor.execute('''
                INSERT INTO pricing (product_code, term_years, customer_type, multiplier)
                SELECT %s, term_years, customer_type, multiplier
                FROM pricing 
                WHERE product_code = %s;
            ''', (new_product_code, product_code))
            
            cloned_pricing_count = cursor.rowcount
        else:
            cloned_pricing_count = 0
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'message': f'Product cloned successfully',
            'cloned_product': {
                'id': new_product_id,
                'product_code': new_product_code,
                'product_name': new_name,
                'source_product_code': product_code
            },
            'cloned_pricing_records': cloned_pricing_count
        })), 201
        
    except Exception as e:
        return jsonify(error_response(f"Failed to clone product: {str(e)}")), 500


@app.route('/api/admin/products/templates', methods=['GET'])
@token_required
@role_required('admin')
def get_product_templates():
    """Get predefined product templates"""
    templates = {
        'home_protection_basic': {
            'product_name': 'Basic Home Protection Plan',
            'description': 'Essential home protection coverage for major systems',
            'base_price': 199,
            'suggested_pricing': {
                1: {'retail': 1.0, 'wholesale': 0.85},
                2: {'retail': 1.8, 'wholesale': 1.53},
                3: {'retail': 2.5, 'wholesale': 2.13}
            },
            'suggested_features': [
                'HVAC coverage',
                'Plumbing protection',
                '24/7 support'
            ]
        },
        'auto_protection_comprehensive': {
            'product_name': 'Comprehensive Auto Protection',
            'description': 'Complete auto protection with roadside assistance',
            'base_price': 339,
            'suggested_pricing': {
                1: {'retail': 1.0, 'wholesale': 0.85},
                2: {'retail': 1.77, 'wholesale': 1.50},
                3: {'retail': 2.36, 'wholesale': 2.01},
                4: {'retail': 2.95, 'wholesale': 2.51},
                5: {'retail': 3.24, 'wholesale': 2.75}
            },
            'suggested_features': [
                'Auto deductible coverage',
                'Roadside assistance',
                'Rental car coverage',
                'Towing service'
            ]
        },
        'deductible_reimbursement_basic': {
            'product_name': 'Deductible Reimbursement Plan',
            'description': 'Insurance deductible coverage and protection',
            'base_price': 150,
            'suggested_pricing': {
                1: {'retail': 1.0, 'wholesale': 0.85},
                2: {'retail': 1.5, 'wholesale': 1.28},
                3: {'retail': 1.83, 'wholesale': 1.56}
            },
            'suggested_features': [
                'Deductible coverage',
                'Identity theft protection',
                'Fast claims processing'
            ]
        }
    }
    
    return jsonify(success_response({
        'templates': templates,
        'template_count': len(templates)
    }))


@app.route('/api/admin/products/from-template', methods=['POST'])
@token_required
@role_required('admin')
def create_product_from_template():
    """Create a new product from a template"""
    try:
        data = request.get_json()
        template_id = data.get('template_id')
        product_code = data.get('product_code')
        
        if not template_id or not product_code:
            return jsonify(error_response('template_id and product_code are required')), 400
        
        # Get template (this would typically fetch from a templates table)
        templates_response = get_product_templates()
        templates_data = json.loads(templates_response.data)
        
        if template_id not in templates_data['data']['templates']:
            return jsonify(error_response('Template not found')), 404
        
        template = templates_data['data']['templates'][template_id]
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Check if product code already exists
        cursor.execute('SELECT product_code FROM products WHERE product_code = %s;', (product_code,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify(error_response('Product code already exists')), 409
        
        # Create product from template
        cursor.execute('''
            INSERT INTO products (product_code, product_name, description, base_price, active)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        ''', (
            product_code,
            data.get('product_name', template['product_name']),
            data.get('description', template['description']),
            data.get('base_price', template['base_price']),
            data.get('active', True)
        ))
        
        product_id = cursor.fetchone()[0]
        
        # Add suggested pricing
        pricing_count = 0
        for term, customer_types in template['suggested_pricing'].items():
            for customer_type, multiplier in customer_types.items():
                cursor.execute('''
                    INSERT INTO pricing (product_code, term_years, customer_type, multiplier)
                    VALUES (%s, %s, %s, %s);
                ''', (product_code, int(term), customer_type, multiplier))
                pricing_count += 1
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'message': 'Product created from template successfully',
            'product': {
                'id': product_id,
                'product_code': product_code,
                'template_used': template_id
            },
            'pricing_records_created': pricing_count,
            'suggested_features': template.get('suggested_features', [])
        })), 201
        
    except Exception as e:
        return jsonify(error_response(f"Failed to create product from template: {str(e)}")), 500


# ================================
# PAYMENT PROCESSING ENDPOINTS
# ================================

@app.route('/api/payments/process', methods=['POST'])
def process_payment():
    """Updated payment processing with HelcimJS integration"""
    try:
        data = request.get_json()
        
        # Check if this is a transaction save request (after HelcimJS success)
        if data.get('action') == 'save_transaction':
            return save_helcim_transaction(data.get('transaction_data', {}))
        
        # Original payment processing for financing and other methods
        # Validate required fields
        required_fields = ['amount', 'customer_info', 'payment_method']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400
        
        payment_method = data['payment_method']
        amount = float(data['amount'])
        customer_info = data['customer_info']
        
        # For credit card payments, redirect to HelcimJS
        if payment_method == 'credit_card':
            return jsonify({
                'success': False,
                'error': 'Credit card payments must be processed through HelcimJS on the frontend',
                'redirect_to_helcim': True
            }), 400
        
        # Get client IP address
        client_ip = request.headers.get('X-Forwarded-For', 
                                      request.headers.get('X-Real-IP', 
                                                        request.remote_addr))
        if not client_ip or client_ip == '127.0.0.1':
            client_ip = '192.168.1.1'  # Default for testing
        
        # Generate transaction number
        quote_id = data.get('quote_id', f'QUOTE-{int(time.time())}')
        transaction_number = f"TXN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{quote_id.split('-')[-1]}"
        
        # Prepare enhanced payment data
        enhanced_data = {
            **data,
            'ip_address': client_ip,
            'currency': data.get('currency', 'USD'),
            'customer_id': f"CUST-{customer_info.get('email', '').replace('@', '-').replace('.', '-')}",
            'transaction_number': transaction_number,
            'description': f"ConnectedAutoCare - {data.get('payment_details', {}).get('product_type', 'Protection Plan')}"
        }
        
        # Create initial transaction record
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO transactions (
                    transaction_number, customer_id, type, amount, 
                    currency, status, payment_method, metadata, created_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            ''', (
                transaction_number,
                enhanced_data.get('customer_id'),
                'payment',
                amount,
                enhanced_data.get('currency', 'USD'),
                'processing',
                json.dumps({
                    'method': payment_method,
                    'quote_id': quote_id,
                    **data.get('payment_details', {})
                }),
                json.dumps({
                    'quote_id': quote_id,
                    'payment_method': payment_method,
                    'initiated_at': datetime.now(timezone.utc).isoformat(),
                    'ip_address': client_ip
                }),
                data.get('user_id')
            ))
            
            transaction_id = cursor.fetchone()[0]
            
            # Process payment based on method (only financing supported here)
            if payment_method == 'financing':
                payment_result = setup_financing_plan(enhanced_data, amount, transaction_number)
            else:
                cursor.execute('''
                    UPDATE transactions 
                    SET status = 'failed', processor_response = %s 
                    WHERE id = %s;
                ''', (json.dumps({'error': 'Invalid payment method'}), transaction_id))
                conn.commit()
                cursor.close()
                conn.close()
                return jsonify({
                    'success': False,
                    'error': f'Unsupported payment method: {payment_method}'
                }), 400
            
            # Update transaction with payment result
            if payment_result['success']:
                cursor.execute('''
                    UPDATE transactions 
                    SET status = %s, processed_at = CURRENT_TIMESTAMP, 
                        processor_response = %s, fees = %s, taxes = %s
                    WHERE id = %s;
                ''', (
                    payment_result['status'],
                    json.dumps(payment_result.get('processor_data', {})),
                    json.dumps(payment_result.get('fees', {})),
                    json.dumps(payment_result.get('taxes', {})),
                    transaction_id
                ))
                
                conn.commit()
                cursor.close()
                conn.close()
                
                return jsonify({
                    'success': True,
                    'data': {
                        'transaction_id': str(transaction_id),
                        'transaction_number': transaction_number,
                        'status': payment_result['status'],
                        'processor_transaction_id': payment_result.get('processor_transaction_id'),
                        'confirmation_number': f"CAC-{transaction_number}",
                        'amount': amount,
                        'currency': enhanced_data.get('currency', 'USD'),
                        'next_steps': payment_result.get('next_steps', []),
                        'contract_generation': {
                            'will_generate': True,
                            'estimated_time': '2-3 business days'
                        }
                    }
                })
            else:
                # Payment failed
                cursor.execute('''
                    UPDATE transactions 
                    SET status = 'failed', processor_response = %s 
                    WHERE id = %s;
                ''', (json.dumps({'error': payment_result.get('error')}), transaction_id))
                conn.commit()
                cursor.close()
                conn.close()
                
                return jsonify({
                    'success': False,
                    'error': payment_result.get('error', 'Payment processing failed'),
                    'details': payment_result.get('processor_data', {}),
                    'solution': payment_result.get('solution', 'Please check your payment information and try again.')
                }), 400
                
        except Exception as db_error:
            conn.rollback()
            cursor.close()
            conn.close()
            raise db_error
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Payment processing failed: {str(e)}'
        }), 500


def save_helcim_transaction(transaction_data):
    """Save HelcimJS transaction data to database after successful payment"""
    try:
        # Extract data from HelcimJS response
        helcim_response = transaction_data.get('helcim_response', {})
        quote_data = transaction_data.get('quote_data', {})
        customer_info = transaction_data.get('customer_info', {})
        billing_info = transaction_data.get('billing_info', {})
        amount = float(transaction_data.get('amount', 0))
        
        # Validate required data
        if not helcim_response:
            return jsonify({
                'success': False,
                'error': 'HelcimJS response data required'
            }), 400
        
        if not customer_info.get('email'):
            return jsonify({
                'success': False,
                'error': 'Customer email required'
            }), 400
        
        # Generate transaction identifiers
        quote_id = quote_data.get('quote_id', f'QUOTE-{int(time.time())}')
        transaction_number = f"TXN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{quote_id.split('-')[-1]}"
        customer_id = f"CUST-{customer_info.get('email', '').replace('@', '-').replace('.', '-')}"
        
        # Extract key information from HelcimJS response
        processor_transaction_id = (
            helcim_response.get('transactionId') or 
            helcim_response.get('cardBatchId') or 
            helcim_response.get('id') or 
            f"HELCIM-{int(time.time())}"
        )
        
        payment_status = 'approved' if helcim_response.get('approved') else 'completed'
        
        # Get client IP address
        client_ip = request.headers.get('X-Forwarded-For', 
                                      request.headers.get('X-Real-IP', 
                                                        request.remote_addr))
        if not client_ip or client_ip == '127.0.0.1':
            client_ip = '192.168.1.1'
        
        # Connect to database
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        try:
            # Insert transaction record
            cursor.execute('''
                INSERT INTO transactions (
                    transaction_number, customer_id, type, amount, 
                    currency, status, payment_method, metadata, 
                    processed_at, processor_response, created_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            ''', (
                transaction_number,
                customer_id,
                'payment',
                amount,
                transaction_data.get('currency', 'USD'),
                payment_status,
                json.dumps({
                    'method': 'credit_card',
                    'processor': 'helcim',
                    'quote_id': quote_id,
                    'processor_transaction_id': processor_transaction_id
                }),
                json.dumps({
                    'quote_id': quote_id,
                    'quote_data': quote_data,
                    'customer_info': customer_info,
                    'billing_info': billing_info,
                    'payment_method': 'credit_card',
                    'product_type': transaction_data.get('product_type', 'unknown'),
                    'vehicle_info': transaction_data.get('vehicle_info'),
                    'processed_at': datetime.now(timezone.utc).isoformat(),
                    'ip_address': client_ip,
                    'user_agent': request.headers.get('User-Agent', '')
                }),
                datetime.now(timezone.utc),
                json.dumps({
                    'helcim_response': helcim_response,
                    'processor': 'helcim',
                    'transaction_id': processor_transaction_id,
                    'success': True,
                    'payment_date': datetime.now(timezone.utc).isoformat()
                }),
                transaction_data.get('user_id')
            ))
            
            transaction_id = cursor.fetchone()[0]
            
            # Insert customer record if doesn't exist
            cursor.execute('''
                INSERT INTO customers (
                    customer_id, first_name, last_name, email, phone,
                    billing_address, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (email) DO UPDATE SET
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    phone = EXCLUDED.phone,
                    billing_address = EXCLUDED.billing_address,
                    updated_at = CURRENT_TIMESTAMP;
            ''', (
                customer_id,
                customer_info.get('first_name', ''),
                customer_info.get('last_name', ''),
                customer_info.get('email', ''),
                customer_info.get('phone', ''),
                json.dumps(billing_info),
                datetime.now(timezone.utc)
            ))
            
            # Create protection plan record
            if quote_data:
                protection_plan_id = create_protection_plan_record(
                    cursor, transaction_id, quote_data, customer_info, 
                    transaction_data.get('vehicle_info')
                )
            
            # Commit all changes
            conn.commit()
            cursor.close()
            conn.close()
            
            # Return success response
            return jsonify({
                'success': True,
                'data': {
                    'transaction_id': str(transaction_id),
                    'transaction_number': transaction_number,
                    'confirmation_number': f"CAC-{transaction_number}",
                    'processor_transaction_id': processor_transaction_id,
                    'status': payment_status,
                    'amount': amount,
                    'currency': transaction_data.get('currency', 'USD'),
                    'customer_id': customer_id,
                    'next_steps': [
                        'Payment has been processed successfully',
                        'You will receive a confirmation email shortly',
                        'Your protection plan is now active',
                        'Contract documents will be generated within 2-3 business days'
                    ],
                    'contract_generation': {
                        'will_generate': True,
                        'estimated_time': '2-3 business days',
                        'protection_plan_id': protection_plan_id if 'protection_plan_id' in locals() else None
                    }
                }
            })
            
        except Exception as db_error:
            conn.rollback()
            cursor.close()
            conn.close()
            raise db_error
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to save transaction: {str(e)}'
        }), 500


def create_protection_plan_record(cursor, transaction_id, quote_data, customer_info, vehicle_info):
    """Create a protection plan record linked to the transaction"""
    try:
        # Generate protection plan ID
        plan_id = f"PLAN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{transaction_id}"
        
        # Determine plan type and details
        coverage_details = quote_data.get('coverage_details', {})
        product_info = quote_data.get('product_info', {})
        
        plan_type = 'vsc' if vehicle_info else 'hero'
        plan_name = coverage_details.get('coverage_level', product_info.get('product_type', 'Protection Plan'))
        
        # Calculate plan dates
        start_date = datetime.now(timezone.utc).date()
        
        # Determine end date based on plan type
        if plan_type == 'vsc':
            term_months = coverage_details.get('term_months', product_info.get('term_months', 12))
            if isinstance(term_months, str):
                term_months = int(term_months)
            end_date = start_date + timedelta(days=term_months * 30)
        else:
            term_years = coverage_details.get('term_years', product_info.get('term_years', 1))
            if isinstance(term_years, str):
                term_years = int(term_years)
            end_date = start_date + timedelta(days=term_years * 365)
        
        # Insert protection plan record
        cursor.execute('''
            INSERT INTO protection_plans (
                plan_id, transaction_id, customer_email, plan_type, 
                plan_name, coverage_details, vehicle_info, 
                start_date, end_date, status, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        ''', (
            plan_id,
            transaction_id,
            customer_info.get('email'),
            plan_type,
            plan_name,
            json.dumps({
                **coverage_details,
                **product_info,
                'quote_data': quote_data
            }),
            json.dumps(vehicle_info) if vehicle_info else None,
            start_date,
            end_date,
            'active',
            datetime.now(timezone.utc)
        ))
        
        protection_plan_db_id = cursor.fetchone()[0]
        
        return {
            'plan_id': plan_id,
            'db_id': protection_plan_db_id,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat()
        }
        
    except Exception as e:
        print(f"Error creating protection plan record: {str(e)}")
        return None


def process_credit_card_payment(data, amount, transaction_number):
    """Updated process credit card payment via Helcim API with proper IP handling"""
    try:
        # Validate Helcim configuration
        from helcim_integration import HelcimPaymentProcessor
        
        # Initialize Helcim processor
        helcim = HelcimPaymentProcessor()
        
        # Get client IP address from request
        client_ip = request.headers.get('X-Forwarded-For', 
                                      request.headers.get('X-Real-IP', 
                                                        request.remote_addr))
        if not client_ip or client_ip == '127.0.0.1':
            client_ip = '192.168.1.1'  # Default for testing
        
        # Prepare payment data with required IP address
        payment_data = {
            **data,
            'amount': amount,
            'transaction_number': transaction_number,
            'ip_address': client_ip,  # Required by Helcim API
            'currency': data.get('currency', 'USD'),
            'description': data.get('description', 'ConnectedAutoCare Payment')
        }
        
        # Process payment
        result = helcim.process_credit_card_payment(payment_data)
        
        # Add sales tax if successful
        if result.get('success'):
            tax_rate = 0.07
            tax_amount = round(amount * tax_rate, 2)
            result['taxes'] = {
                'sales_tax': tax_amount,
                'tax_rate': tax_rate
            }
        
        return result
        
    except Exception as e:
        import traceback
        print(f"Payment processing error: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return {
            'success': False,
            'error': 'Payment processing temporarily unavailable',
            'technical_error': str(e)
        }


def setup_financing_plan(data, amount, transaction_number):
    """Setup financing plan via Supplemental Payment Program"""
    try:
        financing_terms = data.get('financing_terms', '12')  # months
        customer_info = data.get('customer_info', {})
        
        # Validate customer info for financing
        required_fields = ['first_name', 'last_name', 'email', 'phone', 'ssn_last_4']
        missing_fields = [field for field in required_fields if not customer_info.get(field)]
        if missing_fields:
            return {'success': False, 'error': f"Missing customer info: {', '.join(missing_fields)}"}
        
        # Calculate monthly payment
        if financing_terms in ['12', '24']:
            # 0% APR for 12 and 24 months
            monthly_payment = round(amount / int(financing_terms), 2)
            total_amount = amount
        else:
            return {'success': False, 'error': 'Invalid financing terms'}
        
        # Simulate financing approval
        financing_id = f"FIN-{transaction_number}"
        
        return {
            'success': True,
            'status': 'financing_approved',
            'processor_transaction_id': financing_id,
            'processor_data': {
                'provider': 'Supplemental Payment Program',
                'financing_id': financing_id,
                'monthly_payment': monthly_payment,
                'total_amount': total_amount,
                'terms': f"{financing_terms} months at 0% APR",
                'first_payment_due': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
            },
            'fees': {
                'origination_fee': 0.00,  # No fees for 0% APR
                'total_fees': 0.00
            },
            'taxes': {
                'sales_tax': round(amount * 0.07, 2),
                'tax_rate': 0.07
            },
            'next_steps': [
                'Financing application approved',
                f'First payment of ${monthly_payment} due in 30 days',
                'Contract and payment schedule will be sent via email',
                'Setup automatic payments in customer portal'
            ]
        }
        
    except Exception as e:
        return {'success': False, 'error': f'Financing setup failed: {str(e)}'}


@app.route('/api/payments/<transaction_id>/status', methods=['GET'])
def get_payment_status(transaction_id):
    """Get payment status and details from transactions table"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('''
            SELECT 
                t.id,
                t.transaction_number,
                t.customer_id,
                t.policy_id,
                t.type,
                t.amount,
                t.currency,
                t.status,
                t.payment_method,
                t.processor_response,
                t.created_at,
                t.processed_at,
                t.metadata,
                t.fees,
                t.taxes,
                c.first_name,
                c.last_name,
                c.email,
                p.policy_number,
                p.product_type
            FROM transactions t
            LEFT JOIN customers c ON t.customer_id = c.id
            LEFT JOIN policies p ON t.policy_id = p.id
            WHERE t.id = %s OR t.transaction_number = %s;
        ''', (transaction_id, transaction_id))
        
        transaction = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not transaction:
            return jsonify(error_response('Transaction not found')), 404
        
        # Convert to proper format
        transaction_dict = dict(transaction)
        transaction_dict['amount'] = float(transaction_dict['amount'])
        transaction_dict['created_at'] = transaction_dict['created_at'].isoformat() if transaction_dict['created_at'] else None
        transaction_dict['processed_at'] = transaction_dict['processed_at'].isoformat() if transaction_dict['processed_at'] else None
        
        # Parse JSON fields
        for json_field in ['payment_method', 'processor_response', 'metadata', 'fees', 'taxes']:
            if transaction_dict[json_field]:
                transaction_dict[json_field] = transaction_dict[json_field]
            else:
                transaction_dict[json_field] = {}
        
        return jsonify(success_response(transaction_dict))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to get payment status: {str(e)}")), 500


@app.route('/api/payments/history', methods=['GET'])
@token_required
def get_payment_history():
    """Get payment history for logged-in user"""
    try:
        user_id = request.current_user.get('user_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status_filter = request.args.get('status')
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Build WHERE clause
        where_conditions = []
        params = []
        
        # Filter by user's customer record
        cursor.execute('SELECT id FROM customers WHERE user_id = %s;', (user_id,))
        customer_record = cursor.fetchone()
        
        if customer_record:
            where_conditions.append('t.customer_id = %s')
            params.append(customer_record['id'])
        else:
            # If no customer record, show transactions created by this user
            where_conditions.append('t.created_by = %s')
            params.append(user_id)
        
        if status_filter:
            where_conditions.append('t.status = %s')
            params.append(status_filter)
        
        where_clause = ' AND '.join(where_conditions) if where_conditions else 'TRUE'
        
        # Get total count
        cursor.execute(f'''
            SELECT COUNT(*) 
            FROM transactions t 
            WHERE {where_clause};
        ''', params)
        total_count = cursor.fetchone()['count']
        
        # Get paginated results
        offset = (page - 1) * per_page
        cursor.execute(f'''
            SELECT 
                t.id,
                t.transaction_number,
                t.amount,
                t.currency,
                t.status,
                t.payment_method,
                t.created_at,
                t.processed_at,
                t.metadata,
                p.policy_number,
                p.product_type
            FROM transactions t
            LEFT JOIN policies p ON t.policy_id = p.id
            WHERE {where_clause}
            ORDER BY t.created_at DESC
            LIMIT %s OFFSET %s;
        ''', params + [per_page, offset])
        
        transactions = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Convert to proper format
        transactions_list = []
        for txn in transactions:
            txn_dict = dict(txn)
            txn_dict['amount'] = float(txn_dict['amount'])
            txn_dict['created_at'] = txn_dict['created_at'].isoformat() if txn_dict['created_at'] else None
            txn_dict['processed_at'] = txn_dict['processed_at'].isoformat() if txn_dict['processed_at'] else None
            
            # Parse payment_method and metadata
            if txn_dict['payment_method']:
                txn_dict['payment_method'] = txn_dict['payment_method']
            else:
                txn_dict['payment_method'] = {}
                
            if txn_dict['metadata']:
                txn_dict['metadata'] = txn_dict['metadata']
            else:
                txn_dict['metadata'] = {}
            
            transactions_list.append(txn_dict)
        
        return jsonify(success_response({
            'transactions': transactions_list,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_count,
                'pages': (total_count + per_page - 1) // per_page
            }
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to get payment history: {str(e)}")), 500


@app.route('/api/payments/<transaction_id>/refund', methods=['POST'])
@token_required
@role_required('admin')
def process_refund(transaction_id):
    """Process payment refund (admin only)"""
    try:
        data = request.get_json()
        refund_amount = data.get('refund_amount')
        refund_reason = data.get('reason', 'Customer request')
        admin_user_id = request.current_user.get('user_id')
        
        if not refund_amount:
            return jsonify(error_response('refund_amount is required')), 400
        
        refund_amount = float(refund_amount)
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get original transaction
        cursor.execute('''
            SELECT id, transaction_number, amount, status, payment_method, customer_id, policy_id
            FROM transactions 
            WHERE id = %s OR transaction_number = %s;
        ''', (transaction_id, transaction_id))
        
        original_txn = cursor.fetchone()
        if not original_txn:
            cursor.close()
            conn.close()
            return jsonify(error_response('Original transaction not found')), 404
        
        if original_txn['status'] != 'completed':
            cursor.close()
            conn.close()
            return jsonify(error_response('Can only refund completed transactions')), 400
        
        if refund_amount > float(original_txn['amount']):
            cursor.close()
            conn.close()
            return jsonify(error_response('Refund amount cannot exceed original transaction amount')), 400
        
        # Create refund transaction
        refund_transaction_number = f"REF-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        
        cursor.execute('''
            INSERT INTO transactions (
                transaction_number, customer_id, policy_id, type, amount, 
                currency, status, payment_method, metadata, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        ''', (
            refund_transaction_number,
            original_txn['customer_id'],
            original_txn['policy_id'],
            'refund',
            -refund_amount,  # Negative amount for refund
            'USD',
            'processing',
            original_txn['payment_method'],
            json.dumps({
                'refund_reason': refund_reason,
                'original_transaction_id': str(original_txn['id']),
                'original_transaction_number': original_txn['transaction_number'],
                'refund_type': 'partial' if refund_amount < float(original_txn['amount']) else 'full'
            }),
            admin_user_id
        ))
        
        refund_txn_id = cursor.fetchone()[0]
        
        # In production, process refund via payment gateway
        # For now, simulate successful refund
        cursor.execute('''
            UPDATE transactions 
            SET status = 'completed', 
                processed_at = CURRENT_TIMESTAMP,
                processor_response = %s
            WHERE id = %s;
        ''', (
            json.dumps({
                'refund_id': f"HELCIM-REF-{refund_transaction_number}",
                'status': 'processed',
                'estimated_completion': '3-5 business days'
            }),
            refund_txn_id
        ))
        
        # If full refund, update policy status
        if refund_amount == float(original_txn['amount']) and original_txn['policy_id']:
            cursor.execute('''
                UPDATE policies 
                SET status = 'cancelled', payment_status = 'refunded', updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
            ''', (original_txn['policy_id'],))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success_response({
            'refund_transaction_id': str(refund_txn_id),
            'refund_transaction_number': refund_transaction_number,
            'original_transaction_id': str(original_txn['id']),
            'amount': refund_amount,
            'status': 'completed',
            'reason': refund_reason,
            'processed_at': datetime.now(timezone.utc).isoformat() + 'Z',
            'estimated_completion': '3-5 business days'
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Refund processing failed: {str(e)}")), 500


# ================================
# PAYMENT ANALYTICS FOR ADMIN
# ================================

@app.route('/api/admin/payments/analytics', methods=['GET'])
@token_required
@role_required('admin')
def get_payment_analytics():
    """Get payment analytics for admin dashboard"""
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Build date filter
        date_filter = ""
        params = []
        if date_from and date_to:
            date_filter = "WHERE created_at BETWEEN %s AND %s"
            params = [date_from, date_to]
        
        # Get overall stats
        cursor.execute(f'''
            SELECT 
                COUNT(*) as total_transactions,
                COUNT(*) FILTER (WHERE type = 'payment') as payments,
                COUNT(*) FILTER (WHERE type = 'refund') as refunds,
                COUNT(*) FILTER (WHERE status = 'completed') as completed,
                COUNT(*) FILTER (WHERE status = 'failed') as failed,
                COALESCE(SUM(amount) FILTER (WHERE type = 'payment' AND status = 'completed'), 0) as total_revenue,
                COALESCE(SUM(amount) FILTER (WHERE type = 'refund' AND status = 'completed'), 0) as total_refunds,
                COALESCE(AVG(amount) FILTER (WHERE type = 'payment' AND status = 'completed'), 0) as avg_transaction
            FROM transactions 
            {date_filter};
        ''', params)
        
        overall_stats = cursor.fetchone()
        
        # Get payment method breakdown
        cursor.execute(f'''
            SELECT 
                payment_method->>'method' as method,
                COUNT(*) as count,
                COALESCE(SUM(amount) FILTER (WHERE status = 'completed'), 0) as total_amount
            FROM transactions 
            WHERE type = 'payment' {date_filter.replace('WHERE', 'AND') if date_filter else ''}
            GROUP BY payment_method->>'method';
        ''', params)
        
        payment_methods = cursor.fetchall()
        
        # Get daily revenue (last 30 days)
        cursor.execute('''
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as transaction_count,
                COALESCE(SUM(amount) FILTER (WHERE type = 'payment' AND status = 'completed'), 0) as daily_revenue
            FROM transactions 
            WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY DATE(created_at)
            ORDER BY date;
        ''')
        
        daily_stats = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        analytics_data = {
            'overview': {
                'total_transactions': overall_stats[0],
                'payments': overall_stats[1],
                'refunds': overall_stats[2],
                'completed': overall_stats[3],
                'failed': overall_stats[4],
                'total_revenue': float(overall_stats[5]),
                'total_refunds': float(overall_stats[6]),
                'net_revenue': float(overall_stats[5]) + float(overall_stats[6]),  # Adding negative refunds
                'avg_transaction': float(overall_stats[7]),
                'success_rate': round((overall_stats[3] / overall_stats[0] * 100), 2) if overall_stats[0] > 0 else 0
            },
            'payment_methods': [
                {
                    'method': method[0] or 'Unknown',
                    'count': method[1],
                    'total_amount': float(method[2])
                } for method in payment_methods
            ],
            'daily_revenue': [
                {
                    'date': stat[0].isoformat(),
                    'transaction_count': stat[1],
                    'revenue': float(stat[2])
                } for stat in daily_stats
            ]
        }
        
        return jsonify(success_response(analytics_data))
        
    except Exception as e:
        return jsonify(error_response(f"Failed to get payment analytics: {str(e)}")), 500


# ================================
# PAYMENT VALIDATION HELPERS
# ================================

def validate_credit_card(card_number):
    """Basic credit card validation using Luhn algorithm"""
    def luhn_check(card_num):
        def digits_of(n):
            return [int(d) for d in str(n)]
        digits = digits_of(card_num)
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        checksum = sum(odd_digits)
        for d in even_digits:
            checksum += sum(digits_of(d*2))
        return checksum % 10 == 0
    
    # Remove spaces and dashes
    card_number = ''.join(card_number.split()).replace('-', '')
    
    if not card_number.isdigit():
        return False, 'Card number must contain only digits'
    
    if len(card_number) < 13 or len(card_number) > 19:
        return False, 'Invalid card number length'
    
    if not luhn_check(card_number):
        return False, 'Invalid card number'
    
    return True, 'Valid card number'


def get_card_type(card_number):
    """Determine credit card type from number"""
    card_number = ''.join(card_number.split()).replace('-', '')
    
    if card_number.startswith('4'):
        return 'Visa'
    elif card_number.startswith(('51', '52', '53', '54', '55')) or card_number.startswith('22'):
        return 'MasterCard'
    elif card_number.startswith(('34', '37')):
        return 'American Express'
    elif card_number.startswith('6011') or card_number.startswith('65'):
        return 'Discover'
    else:
        return 'Unknown'


@app.route('/api/payments/validate-card', methods=['POST'])
def validate_card_endpoint():
    """Validate credit card information"""
    try:
        data = request.get_json()
        card_number = data.get('card_number', '')
        
        is_valid, message = validate_credit_card(card_number)
        card_type = get_card_type(card_number) if is_valid else None
        
        return jsonify(success_response({
            'valid': is_valid,
            'message': message,
            'card_type': card_type,
            'last_four': card_number[-4:] if is_valid else None
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Card validation failed: {str(e)}")), 500


# ================================
# PAYMENT WEBHOOK HANDLERS
# ================================

@app.route('/api/admin/helcim/status', methods=['GET'])
@token_required
@role_required('admin')
def helcim_status():
    """Check Helcim integration status"""
    try:
        from helcim_integration import test_helcim_connection
        
        # Test connection if config is valid
        connection_result = {'success': False, 'message': 'Configuration invalid'}
        
        return jsonify(success_response({
            'connection': connection_result,
            'integration_status': 'operational' if connection_result['success'] else 'needs_configuration'
        }))
        
    except Exception as e:
        return jsonify(error_response(f"Status check failed: {str(e)}")), 500
    

@app.route('/api/webhooks/helcim', methods=['POST'])
def helcim_webhook():
    """Handle Helcim payment webhooks with proper signature verification"""
    try:
        from helcim_integration import HelcimPaymentProcessor
        
        # Get raw request data for signature verification
        raw_data = request.get_data()
        headers = dict(request.headers)
        
        # Initialize processor for webhook verification
        processor = HelcimPaymentProcessor()
        
        # Verify webhook signature
        if not processor.verify_webhook_signature(headers, raw_data):
            return jsonify({'error': 'Invalid webhook signature'}), 401
        
        # Parse webhook data
        try:
            webhook_data = json.loads(raw_data.decode('utf-8'))
        except json.JSONDecodeError:
            return jsonify({'error': 'Invalid JSON payload'}), 400
        
        transaction_id = webhook_data.get('id')
        webhook_type = webhook_data.get('type')
        
        if not transaction_id:
            return jsonify({'error': 'Missing transaction ID'}), 400
        
        # Update transaction in database
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        try:
            # Find transaction by processor transaction ID
            cursor.execute('''
                SELECT id, transaction_number, status
                FROM transactions 
                WHERE processor_response->>'transaction_id' = %s;
            ''', (transaction_id,))
            
            transaction = cursor.fetchone()
            
            if transaction:
                # Update transaction status based on webhook
                new_status = 'completed' if webhook_type == 'transaction.approved' else 'failed'
                
                cursor.execute('''
                    UPDATE transactions 
                    SET status = %s, 
                        processed_at = CURRENT_TIMESTAMP,
                        processor_response = processor_response || %s
                    WHERE id = %s;
                ''', (
                    new_status,
                    json.dumps({'webhook_received': True, 'webhook_type': webhook_type}),
                    transaction[0]
                ))
                
                conn.commit()
                
                # Log webhook receipt
                print(f"✅ Webhook processed: {webhook_type} for transaction {transaction[1]}")
            else:
                print(f"⚠️ Webhook received for unknown transaction: {transaction_id}")
            
            cursor.close()
            conn.close()
            
            return jsonify({'received': True}), 200
            
        except Exception as db_error:
            conn.rollback()
            cursor.close()
            conn.close()
            raise db_error
        
    except Exception as e:
        print(f"❌ Webhook processing error: {str(e)}")
        return jsonify({'error': 'Webhook processing failed'}), 500


@app.route('/api/webhooks/financing', methods=['POST'])
def financing_webhook():
    """Handle financing company webhooks"""
    try:
        data = request.get_json()
        
        transaction_number = data.get('transaction_number')
        status = data.get('status')
        financing_data = data.get('financing_data', {})
        
        if not transaction_number:
            return jsonify({'error': 'Missing transaction_number'}), 400
        
        # Update transaction status in database
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE transactions 
            SET status = %s, 
                processed_at = CURRENT_TIMESTAMP,
                processor_response = %s
            WHERE transaction_number = %s;
        ''', (status, json.dumps(financing_data), transaction_number))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'received': True}), 200
        
    except Exception as e:
        print(f"Financing webhook error: {str(e)}")
        return jsonify({'error': 'Webhook processing failed'}), 500


@app.route('/api/payments/create-helcim-session', methods=['POST'])
def create_helcim_payment_session():
    """Create HelcimPay.js checkout session - enhanced for verify type with proper province handling"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('amount'):
            return jsonify({
                'success': False,
                'error': 'Amount is required'
            }), 400
        
        from helcim_integration import HelcimPaymentProcessor, CustomerInfo, Address, Currency
        processor = HelcimPaymentProcessor()
        
        # Parse customer information
        customer_info_data = data.get('customer_info', {})
        
        # Create Address object if needed with proper province handling
        billing_address = None
        if customer_info_data.get('address'):
            # Handle province/state mapping for Helcim
            province_input = customer_info_data.get('state', '')
            
            # Log the original input for debugging
            print(f"🔍 Original province/state input: '{province_input}'")
            
            # Create address - the Address class will automatically normalize the province
            billing_address = Address(
                street1=customer_info_data.get('address', ''),
                city=customer_info_data.get('city', ''),
                province=province_input,  # Will be normalized in __post_init__
                postal_code=customer_info_data.get('zip_code', ''),
                country='USA'  # Adjust based on your needs
            )
            
            # Log the normalized province for debugging
            print(f"✅ Normalized province for Helcim Customer API: '{billing_address.province}' (should be code like 'ON', 'CA')")
        
        # Create CustomerInfo object
        customer_info = CustomerInfo(
            contact_name=f"{customer_info_data.get('first_name', 'Guest')} {customer_info_data.get('last_name', 'Customer')}",
            business_name=customer_info_data.get('business_name', f"Customer-{int(time.time())}"),
            email=customer_info_data.get('email'),
            phone=customer_info_data.get('phone'),
            billing_address=billing_address
        )
        
        # Parse currency
        currency_str = data.get('currency', 'USD').upper()
        try:
            currency = Currency(currency_str)
        except ValueError:
            return jsonify({
                'success': False,
                'error': f'Unsupported currency: {currency_str}'
            }), 400
        
        # Check payment type to determine flow
        payment_type = data.get('payment_type', 'purchase')
        
        if payment_type == 'verify':
            # FOR VERIFY (TOKENIZATION) - Create customer and minimal session
            print(f"🔍 Creating VERIFY session for tokenization...")
            
            # Step 1: Create customer only (no invoice needed for tokenization)
            customer_result = processor.create_customer(customer_info)
            if not customer_result['success']:
                return jsonify({
                    'success': False,
                    'error': f'Failed to create customer: {customer_result.get("error", "Unknown error")}'
                }), 400
            
            customer_id = customer_result['customer_id']
            print(f"✅ Customer created successfully: {customer_id}")
            
            # Step 2: Create HelcimPay session for verification (tokenization)
            verify_session_result = processor.create_helcimpay_checkout_session(
                amount=float(data['amount']),  # Usually $1.00 for verification
                currency=currency,
                customer_id=customer_id,
                payment_type='verify'  # This is key!
            )
            
            if verify_session_result['success']:
                print(f"✅ Verify session created: {verify_session_result.get('checkout_token')}")
                return jsonify({
                    'success': True,
                    'data': {
                        'checkoutToken': verify_session_result.get('checkout_token'),
                        'customerId': customer_id,
                        'invoiceId': None,  # No invoice for verify
                        'transactionId': verify_session_result.get('transaction_id'),
                        'session_type': 'verify'
                    }
                })
            else:
                return jsonify({
                    'success': False,
                    'error': verify_session_result.get('error', 'Failed to create verification session')
                }), 400
        
        else:
            # FOR PURCHASE/PREAUTH - Full customer + invoice flow (your existing code)
            print(f"🛒 Creating {payment_type.upper()} session for payment...")
            
            result = processor.create_complete_checkout_flow(
                amount=float(data['amount']),
                currency=currency,
                customer_info=customer_info,
                description=data.get('description', 'ConnectedAutoCare Payment')
            )
            
            if result['success']:
                print(f"✅ Complete checkout flow created: {result.get('checkout_token')}")
                return jsonify({
                    'success': True,
                    'data': {
                        'checkoutToken': result.get('checkout_token'),
                        'customerId': result.get('customer_id'),
                        'invoiceId': result.get('invoice_id'),
                        'transactionId': result.get('transaction_id'),
                        'session_type': payment_type
                    }
                })
            else:
                return jsonify({
                    'success': False,
                    'error': result.get('error', 'Failed to create payment session')
                }), 400
            
    except Exception as e:
        print(f"💥 Session creation error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Session creation failed: {str(e)}'
        }), 500


@app.route('/api/payments/helcim/test', methods=['POST'])
@token_required
@role_required('admin')
def test_helcim_integration():
    """Test Helcim integration with various scenarios"""
    try:
        data = request.get_json()
        test_type = data.get('test_type', 'connection')
        
        from helcim_integration import HelcimPaymentProcessor
        
        results = {
            'test_type': test_type,
            'timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
            'results': {}
        }
        
        processor = HelcimPaymentProcessor()
        
        if test_type == 'connection':
            # Test basic connectivity
            try:
                import requests
                response = requests.get('https://api.helcim.com/v2/connection-test', 
                                      headers={'api-token': processor.api_token}, 
                                      timeout=10)
                
                results['results']['connection'] = {
                    'success': response.status_code == 200,
                    'status_code': response.status_code,
                    'response': response.json() if response.status_code == 200 else response.text
                }
            except Exception as e:
                results['results']['connection'] = {
                    'success': False,
                    'error': str(e)
                }
        
        elif test_type == 'helcimpay_session':
            # Test HelcimPay.js session creation
            session_data = {
                'amount': 1.00,
                'currency': 'USD',
                'payment_type': 'purchase',
                'description': 'Test Session',
                'customer_id': f"TEST-CUST-{int(time.time())}",
                'transaction_number': f"TEST-TXN-{int(time.time())}"
            }
            
            session_result = processor.create_helcimpay_checkout_session(session_data)
            results['results']['helcimpay_session'] = session_result
        
        elif test_type == 'token_payment':
            # Test payment with token (will fail without real token)
            payment_data = {
                'amount': 1.00,
                'currency': 'USD',
                'card_token': data.get('test_token', 'test_token_12345'),
                'description': 'Test Payment with Token',
                'ip_address': '192.168.1.1',
                'customer_id': f"TEST-CUST-{int(time.time())}",
                'transaction_number': f"TEST-TXN-{int(time.time())}"
            }
            
            payment_result = processor.process_credit_card_payment(payment_data)
            results['results']['token_payment'] = payment_result
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Test failed: {str(e)}',
            'results': results if 'results' in locals() else {}
        }), 500


@app.route('/api/payments/helcim/status', methods=['GET'])
@token_required
@role_required('admin')
def get_helcim_integration_status():
    """Get comprehensive Helcim integration status"""
    try:
        from helcim_integration import HelcimPaymentProcessor
        
        
        status_info = {
            'api_connectivity': {'tested': False},
            'features': {
                'purchase_transactions': True,
                'refund_transactions': True,
                'reverse_transactions': True,
                'helcimpay_sessions': True,
                'webhook_verification': True
            },
            'requirements': {
                'ip_address_required': True,
                'idempotency_key_required': True,
                'card_tokens_recommended': True,
                'full_card_data_requires_approval': True
            }
        }
        

        try:
            import requests
            processor = HelcimPaymentProcessor()
            
            response = requests.get('https://api.helcim.com/v2/connection-test', 
                                    headers={'api-token': processor.api_token}, 
                                    timeout=10)
            
            status_info['api_connectivity'] = {
                'tested': True,
                'success': response.status_code == 200,
                'status_code': response.status_code,
                'response_time_ms': response.elapsed.total_seconds() * 1000 if hasattr(response, 'elapsed') else None
            }
            
            if response.status_code == 200:
                status_info['api_connectivity']['message'] = response.json().get('message', 'Connected')
        except Exception as e:
            status_info['api_connectivity'] = {
                'tested': True,
                'success': False,
                'error': str(e)
            }
    
        overall_status = (
            status_info['api_connectivity'].get('success', False)
        )
        
        return jsonify({
            'success': True,
            'overall_status': 'operational' if overall_status else 'needs_configuration',
            'integration_health': status_info,
            'checked_at': datetime.now(timezone.utc).isoformat() + 'Z'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Status check failed: {str(e)}'
        }), 500    


def handle_payment_error(error, transaction_id=None):
    """Enhanced error handling for payment processing"""
    error_mapping = {
        'No access permission': {
            'user_message': 'Payment processor configuration error. Please contact support.',
            'admin_message': 'Helcim API permissions insufficient. Check Transaction Processing permissions.',
            'action': 'contact_admin'
        },
        'Missing required data ip Address': {
            'user_message': 'Payment processing error. Please try again.',
            'admin_message': 'IP address not provided to Helcim API. Check request structure.',
            'action': 'retry'
        },
        'Invalid response from payment processor': {
            'user_message': 'Payment processor temporarily unavailable. Please try again.',
            'admin_message': 'Helcim API returned invalid response. Check API status.',
            'action': 'retry_later'
        }
    }
    
    error_str = str(error)
    error_info = None
    
    for key, info in error_mapping.items():
        if key in error_str:
            error_info = info
            break
    
    if not error_info:
        error_info = {
            'user_message': 'Payment processing failed. Please check your information and try again.',
            'admin_message': f'Unexpected payment error: {error_str}',
            'action': 'contact_support'
        }
    
    # Log detailed error for admin
    print(f"💳 Payment Error: {error_info['admin_message']}")
    if transaction_id:
        print(f"   Transaction ID: {transaction_id}")
    
    return error_info


# For local development only
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

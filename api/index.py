#!/usr/bin/env python3
"""
ConnectedAutoCare.com - Main Application Entry Point
Modular Flask application with organized endpoint blueprints
"""

import os
import sys
from datetime import datetime, timezone
from flask import Flask, jsonify, Blueprint
from flask_cors import CORS

# Add the current directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import configuration and utilities
try:
    from config.app_config import AppConfig
    from utils.response_helpers import error_response
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False

# Import all endpoint blueprints with error handling
try:
    from endpoints.health_endpoints import health_bp
    from endpoints.hero_endpoints import hero_bp
    from endpoints.vsc_endpoints import vsc_bp
    from endpoints.vin_endpoints import vin_bp
    from endpoints.user_auth_endpoints import user_auth_bp
    from endpoints.customer_endpoints import customer_bp
    from endpoints.reseller_endpoints import reseller_bp
    from endpoints.admin_endpoints import admin_bp
    from endpoints.payment_endpoints import payment_bp
    from endpoints.video_endpoints import video_bp
    from endpoints.video_public_endpoints import video_public_bp 
    from endpoints.pricing_endpoints import pricing_bp
    from endpoints.analytics_endpoints import analytics_bp
    ENDPOINTS_AVAILABLE = True
except ImportError:
    ENDPOINTS_AVAILABLE = False
    # Create fallback blueprints
    
    health_bp = Blueprint('health_fallback', __name__)
    hero_bp = Blueprint('hero_fallback', __name__)
    vsc_bp = Blueprint('vsc_fallback', __name__)
    vin_bp = Blueprint('vin_fallback', __name__)
    user_auth_bp = Blueprint('user_auth_fallback', __name__)
    customer_bp = Blueprint('customer_fallback', __name__)
    reseller_bp = Blueprint('reseller_fallback', __name__)
    admin_bp = Blueprint('admin_fallback', __name__)
    payment_bp = Blueprint('payment_fallback', __name__)
    video_bp = Blueprint('video_fallback', __name__)
    video_public_bp = Blueprint('video_public_fallback', __name__)
    pricing_bp = Blueprint('pricing_fallback', __name__)
    analytics_bp = Blueprint('analytics_fallback', __name__)
    
    # Add essential fallback routes
    @health_bp.route('/health')
    def fallback_health():
        return jsonify({
            "status": "fallback", 
            "message": "Endpoints not fully loaded",
            "timestamp": datetime.now(timezone.utc).isoformat() + 'Z'
        })
    
    @video_public_bp.route('/landing/video')
    def fallback_video():
        return jsonify({
            'video_url': '',
            'thumbnail_url': '',
            'title': 'ConnectedAutoCare Hero Protection',
            'description': 'Comprehensive protection plans',
            'duration': '2:30',
            'updated_at': datetime.now(timezone.utc).isoformat() + 'Z'
        })

# Initialize Flask app
app = Flask(__name__)

# Load configuration
if CONFIG_AVAILABLE:
    config = AppConfig()
    app.config.update(config.get_flask_config())
    
    # Configure CORS
    CORS(app, 
         origins=config.ALLOWED_ORIGINS, 
         supports_credentials=True,
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
         
    # Enhanced CORS handling for production
    @app.after_request
    def after_request(response):
        return config.handle_cors_response(response)

    @app.before_request
    def handle_preflight():
        return config.handle_preflight_request()
        
else:
    # Fallback configuration
    app.config.update({
        'SECRET_KEY': os.environ.get('SECRET_KEY', 'fallback-secret-key-2025'),
        'DEBUG': False,
        'TESTING': False,
        'MAX_CONTENT_LENGTH': 16 * 1024 * 1024
    })
    
    # Basic CORS
    CORS(app, origins="*", supports_credentials=True)

# Register all blueprints
def register_blueprints(app):
    """Register all endpoint blueprints"""
    
    try:
        # Core API endpoints
        app.register_blueprint(health_bp, url_prefix='/api')
        app.register_blueprint(hero_bp, url_prefix='/api/hero')
        app.register_blueprint(vsc_bp, url_prefix='/api/vsc')
        app.register_blueprint(vin_bp, url_prefix='/api/vin')
        
        # User management endpoints
        app.register_blueprint(user_auth_bp, url_prefix='/api/auth')
        app.register_blueprint(customer_bp, url_prefix='/api/customers')
        app.register_blueprint(reseller_bp, url_prefix='/api/resellers')
        
        # Admin endpoints
        app.register_blueprint(admin_bp, url_prefix='/api/admin')
        app.register_blueprint(pricing_bp, url_prefix='/api/admin/pricing')
        
        # Analytics endpoints
        app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
        
        # Video endpoints - Admin routes
        app.register_blueprint(video_bp, url_prefix='/api/admin/video')
        
        # Video endpoints - Public routes
        app.register_blueprint(video_public_bp, url_prefix='/api')
        
        # Payment endpoints
        app.register_blueprint(payment_bp, url_prefix='/api/payments')
        
    except Exception as e:
        import traceback
        print(f"Error registering blueprints: {e}")
        print(f"Traceback: {traceback.format_exc()}")

# Register all blueprints
register_blueprints(app)

# Global error handlers
@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    if CONFIG_AVAILABLE:
        return error_response("Endpoint not found", 404)
    else:
        return jsonify({
            "success": False,
            "error": "Endpoint not found",
            "timestamp": datetime.now(timezone.utc).isoformat() + 'Z'
        }), 404

@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors"""
    if CONFIG_AVAILABLE:
        return error_response("Method not allowed", 405)
    else:
        return jsonify({
            "success": False,
            "error": "Method not allowed",
            "timestamp": datetime.now(timezone.utc).isoformat() + 'Z'
        }), 405

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    if CONFIG_AVAILABLE:
        return error_response("Internal server error", 500)
    else:
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "timestamp": datetime.now(timezone.utc).isoformat() + 'Z'
        }), 500

@app.errorhandler(Exception)
def handle_exception(error):
    """Handle unexpected exceptions"""
    import traceback
    print(f"Unexpected error: {str(error)}")
    print(f"Traceback: {traceback.format_exc()}")
    
    if CONFIG_AVAILABLE:
        return error_response("An unexpected error occurred", 500)
    else:
        return jsonify({
            "success": False,
            "error": "An unexpected error occurred",
            "timestamp": datetime.now(timezone.utc).isoformat() + 'Z'
        }), 500

# Root endpoint
@app.route('/')
def root():
    """Root endpoint with API information"""
    return {
        "service": "ConnectedAutoCare Unified Platform",
        "version": "4.0.0",
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "endpoints": {
            "health": "/api/health",
            "hero_products": "/api/hero/products",
            "vsc_quotes": "/api/vsc/quote",
            "vin_decoder": "/api/vin/decode",
            "user_auth": "/api/auth/login",
            "admin": "/api/admin/health",
            "payments": "/api/payments/methods",
            "resellers": "/api/resellers",
            "video_public": "/api/landing/video",
            "video_admin": "/api/admin/video"
        },
        "documentation": "https://api.connectedautocare.com/docs"
    }

# Health check endpoint
@app.route('/health')
def health_check():
    """Simple health check endpoint"""
    return {
        "status": "healthy",
        "service": "ConnectedAutoCare API",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "endpoints_loaded": ENDPOINTS_AVAILABLE,
        "config_loaded": CONFIG_AVAILABLE
    }

# API status endpoint
@app.route('/api/status')
def api_status():
    """API status endpoint with detailed information"""
    return jsonify({
        "api_status": "operational",
        "version": "4.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "services": {
            "core_api": "healthy",
            "video_service": "healthy" if ENDPOINTS_AVAILABLE else "degraded",
            "configuration": "loaded" if CONFIG_AVAILABLE else "fallback"
        },
        "endpoints_available": ENDPOINTS_AVAILABLE
    })

# For local development only
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
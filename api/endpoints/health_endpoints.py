"""
Health Check Endpoints
System health monitoring and status endpoints
"""

from flask import Blueprint, jsonify
from datetime import datetime, timezone
from utils.service_availability import ServiceChecker
from utils.response_helpers import success_response, error_response

health_bp = Blueprint('health', __name__)

@health_bp.route('/health')
def health_check():
    """Main health check endpoint"""
    service_checker = ServiceChecker()
    
    return jsonify({
        "service": "ConnectedAutoCare Unified Platform with VIN Auto-Detection",
        "status": "healthy",
        "version": "4.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "environment": "production",
        "components": {
            "customer_api": "available" if service_checker.customer_services_available else "unavailable",
            "admin_panel": "available" if service_checker.admin_modules_available else "unavailable",
            "user_management": "available" if service_checker.user_management_available else "unavailable",
            "enhanced_vin_decoder": "available" if service_checker.enhanced_vin_available else "basic_only"
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

@health_bp.route('/health/api')
def api_health():
    """Comprehensive API health check"""
    service_checker = ServiceChecker()
    
    return jsonify({
        "api_status": "healthy",
        "customer_services": {
            "hero_products": "available" if service_checker.customer_services_available else "unavailable",
            "vsc_rating": "available" if service_checker.customer_services_available else "unavailable",
            "vin_decoder": "available" if service_checker.customer_services_available else "unavailable"
        },
        "admin_services": {
            "authentication": "available" if service_checker.admin_modules_available else "unavailable",
            "product_management": "available" if service_checker.admin_modules_available else "unavailable",
            "analytics": "available" if service_checker.admin_modules_available else "unavailable",
            "contracts": "available" if service_checker.admin_modules_available else "unavailable"
        },
        "user_management": {
            "authentication": "available" if service_checker.user_management_available else "unavailable",
            "customer_portal": "available" if service_checker.user_management_available else "unavailable",
            "reseller_portal": "available" if service_checker.user_management_available else "unavailable",
            "analytics": "available" if service_checker.user_management_available else "unavailable"
        },
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
    })

@health_bp.route('/health/database')
def database_health():
    """Database connectivity health check"""
    try:
        from utils.database import DatabaseManager
        db_manager = DatabaseManager()
        
        # Test database connection
        connection_test = db_manager.test_connection()
        
        if connection_test['success']:
            return jsonify({
                "database_status": "healthy",
                "connection_time_ms": connection_test.get('connection_time_ms'),
                "database_info": connection_test.get('database_info', {}),
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
            })
        else:
            return jsonify({
                "database_status": "unhealthy",
                "error": connection_test.get('error'),
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
            }), 503
            
    except Exception as e:
        return jsonify({
            "database_status": "error",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
        }), 500

@health_bp.route('/health/services')
def services_health():
    """Individual service health check"""
    service_checker = ServiceChecker()
    
    services_status = {
        "hero_service": service_checker.check_hero_service(),
        "vsc_service": service_checker.check_vsc_service(),
        "vin_service": service_checker.check_vin_service(),
        "payment_service": service_checker.check_payment_service(),
        "email_service": service_checker.check_email_service(),
        "file_storage": service_checker.check_file_storage()
    }
    
    # Determine overall health
    all_healthy = all(status.get('status') == 'healthy' for status in services_status.values())
    
    return jsonify({
        "overall_status": "healthy" if all_healthy else "degraded",
        "services": services_status,
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
    }), 200 if all_healthy else 503

@health_bp.route('/health/detailed')
def detailed_health():
    """Detailed system health check with metrics"""
    try:
        service_checker = ServiceChecker()
        
        # Get detailed metrics
        metrics = {
            "system_info": service_checker.get_system_info(),
            "database_metrics": service_checker.get_database_metrics(),
            "api_metrics": service_checker.get_api_metrics(),
            "error_rates": service_checker.get_error_rates(),
            "response_times": service_checker.get_response_times()
        }
        
        return jsonify({
            "health_check_type": "detailed",
            "overall_status": "operational",
            "metrics": metrics,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
        })
        
    except Exception as e:
        return jsonify({
            "health_check_type": "detailed",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
        }), 500
"""
Hero Products API Endpoints
Home and auto protection plan quotes and products
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
from utils.service_availability import ServiceChecker

# Initialize blueprint
hero_bp = Blueprint('hero', __name__)

# Import services with error handling
try:
    from services.hero_rating_service import HeroRatingService
    from data.hero_products_data import get_hero_products
    from services.database_settings_service import get_admin_fee, get_wholesale_discount, get_tax_rate, get_processing_fee, settings_service
    HERO_SERVICE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Hero service not available: {e}")
    HERO_SERVICE_AVAILABLE = False
    
    # Create fallback classes
    class HeroRatingService:
        def generate_quote(self, *args, **kwargs):
            return {"success": False, "error": "Service temporarily unavailable"}
    
    def get_hero_products():
        return {}
    
    def get_admin_fee(*args): return 25.00
    def get_wholesale_discount(): return 0.15
    def get_tax_rate(*args): return 0.07
    def get_processing_fee(): return 15.00
    
    class DummySettingsService:
        connection_available = False
    settings_service = DummySettingsService()

@hero_bp.route('/health')
def hero_health():
    """Hero products service health check"""
    service_checker = ServiceChecker()
    
    if not service_checker.customer_services_available:
        return jsonify({"error": "Hero products service not available"}), 503

    try:
        products = get_hero_products()
        return jsonify({
            "service": "Hero Products API",
            "status": "healthy",
            "products_available": len(products),
            "categories": list(products.keys()) if products else [],
            "database_integration": settings_service.connection_available,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
        })
    except Exception as e:
        return jsonify({"error": f"Hero service error: {str(e)}"}), 500

@hero_bp.route('/products')
def get_all_hero_products():
    """Get all Hero products with pricing information"""
    service_checker = ServiceChecker()
    
    if not service_checker.customer_services_available:
        return jsonify({"error": "Hero products service not available"}), 503

    try:
        products = get_hero_products()
        return jsonify(products)
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve products: {str(e)}"}), 500

@hero_bp.route('/products/<category>')
def get_hero_products_by_category(category):
    """Get Hero products by category"""
    service_checker = ServiceChecker()
    
    if not service_checker.customer_services_available:
        return jsonify({"error": "Hero products service not available"}), 503

    try:
        all_products = get_hero_products()
        if category not in all_products:
            return jsonify({"error": f"Category '{category}' not found"}), 404

        return jsonify({
            "category": category,
            "products": all_products[category]
        })
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve category: {str(e)}"}), 500

@hero_bp.route('/quote', methods=['POST'])
def generate_hero_quote():
    """Generate Hero product quote with database-driven pricing"""
    service_checker = ServiceChecker()
    
    if not service_checker.customer_services_available or not HERO_SERVICE_AVAILABLE:
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
                # Add system integration info
                quote_result['database_integration'] = True
                quote_result['database_settings_used'] = settings_service.connection_available
                quote_result['system_info'] = {
                    'settings_source': 'database' if settings_service.connection_available else 'fallback',
                    'admin_fee_source': 'database' if settings_service.connection_available else 'hardcoded',
                    'discount_source': 'database' if settings_service.connection_available else 'hardcoded',
                    'tax_source': 'database' if settings_service.connection_available else 'hardcoded'
                }
                return jsonify(quote_result)
            else:
                return jsonify({"error": quote_result.get('error', 'Quote generation failed')}), 400
                
        except Exception as hero_error:
            print(f"Hero service error: {hero_error}")
            return jsonify({"error": f"Hero quote generation failed: {str(hero_error)}"}), 500
            
    except Exception as e:
        return jsonify({"error": f"Hero quote error: {str(e)}"}), 500

@hero_bp.route('/pricing/<product_type>')
def get_hero_pricing(product_type):
    """Get pricing for specific Hero product type"""
    service_checker = ServiceChecker()
    
    if not service_checker.customer_services_available:
        return jsonify({"error": "Hero products service not available"}), 503

    try:
        term_years = request.args.get('term_years', 1, type=int)
        customer_type = request.args.get('customer_type', 'retail')
        coverage_limit = request.args.get('coverage_limit', 500, type=int)
        
        # Use Hero service to get pricing
        hero_service = HeroRatingService()
        pricing_result = hero_service.generate_quote(
            product_type=product_type,
            term_years=term_years,
            coverage_limit=coverage_limit,
            customer_type=customer_type,
            state='FL'  # Default state for pricing
        )
        
        if pricing_result.get('success'):
            return jsonify({
                "product_type": product_type,
                "pricing": pricing_result,
                "parameters": {
                    "term_years": term_years,
                    "customer_type": customer_type,
                    "coverage_limit": coverage_limit
                }
            })
        else:
            return jsonify(f"Failed to get pricing: {pricing_result.get('error')}"), 400
            
    except Exception as e:
        return jsonify(f"Pricing error: {str(e)}"), 500

@hero_bp.route('/coverage-options')
def get_hero_coverage_options():
    """Get available Hero coverage options and limits"""
    service_checker = ServiceChecker()
    
    if not service_checker.customer_services_available:
        return jsonify({"error": "Hero products service not available"}), 503

    try:
        coverage_options = {
            "coverage_limits": {
                "500": {"name": "$500 Coverage", "description": "Basic protection level"},
                "1000": {"name": "$1000 Coverage", "description": "Enhanced protection level"}
            },
            "term_options": {
                "1": {"name": "1 Year", "months": 12},
                "2": {"name": "2 Years", "months": 24},
                "3": {"name": "3 Years", "months": 36}
            },
            "customer_types": {
                "retail": {"name": "Retail Customer", "discount": 0},
                "wholesale": {"name": "Wholesale Partner", "discount": get_wholesale_discount()}
            },
            "product_categories": {
                "home_protection": "Home Protection Plans",
                "auto_protection": "Auto Protection Plans", 
                "deductible_reimbursement": "Deductible Reimbursement"
            }
        }
        
        return jsonify(coverage_options)
        
    except Exception as e:
        return jsonify(f"Failed to get coverage options: {str(e)}"), 500

@hero_bp.route('/states')
def get_available_states():
    """Get states where Hero products are available"""
    try:
        # States where ConnectedAutoCare operates
        available_states = {
            "FL": {"name": "Florida", "tax_rate": get_tax_rate('FL')},
            "CA": {"name": "California", "tax_rate": get_tax_rate('CA')},
            "TX": {"name": "Texas", "tax_rate": get_tax_rate('TX')},
            "NY": {"name": "New York", "tax_rate": get_tax_rate('NY')},
            "GA": {"name": "Georgia", "tax_rate": get_tax_rate('GA')},
            "NC": {"name": "North Carolina", "tax_rate": get_tax_rate('NC')},
            "SC": {"name": "South Carolina", "tax_rate": get_tax_rate('SC')},
            "AL": {"name": "Alabama", "tax_rate": get_tax_rate('AL')},
            "TN": {"name": "Tennessee", "tax_rate": get_tax_rate('TN')},
            "VA": {"name": "Virginia", "tax_rate": get_tax_rate('VA')}
        }
        
        return jsonify({
            "available_states": available_states,
            "total_states": len(available_states),
            "notes": "Tax rates are subject to change. Contact support for current rates in your area."
        })
        
    except Exception as e:
        return jsonify(f"Failed to get state information: {str(e)}"), 500
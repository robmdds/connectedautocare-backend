"""
Pricing Management Endpoints
Database-driven pricing control, product management, and system settings
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
from auth.user_auth import token_required, role_required
from utils.database import get_db_manager, execute_query

# Initialize blueprint
pricing_bp = Blueprint('pricing', __name__)

# Import pricing services with error handling
try:
    from data.hero_products_data import get_price_from_db_or_fallback, get_all_products_pricing, calculate_hero_price
    from services.database_settings_service import get_admin_fee, get_wholesale_discount, get_tax_rate, get_processing_fee, get_dealer_fee, settings_service
    import psycopg2
    pricing_services_available = True
except ImportError as e:
    print(f"Warning: Pricing services not available: {e}")
    pricing_services_available = False
    
    # Create fallback functions
    def get_price_from_db_or_fallback(*args, **kwargs):
        return {'success': False, 'error': 'Pricing service not available'}
    
    def get_all_products_pricing():
        return {}
    
    def calculate_hero_price(*args, **kwargs):
        return {'success': False, 'error': 'Pricing service not available'}
    
    def get_admin_fee(*args): return 25.00
    def get_wholesale_discount(): return 0.15
    def get_tax_rate(*args): return 0.07
    def get_processing_fee(): return 15.00
    def get_dealer_fee(): return 50.00
    
    class DummySettingsService:
        connection_available = False
    settings_service = DummySettingsService()

@pricing_bp.route('/health')
@token_required
@role_required('admin')
def pricing_health():
    """Pricing management service health check"""
    return jsonify({
        'service': 'Pricing Management API',
        'status': 'healthy' if pricing_services_available else 'degraded',
        'pricing_services_available': pricing_services_available,
        'database_integration': settings_service.connection_available if hasattr(settings_service, 'connection_available') else False,
        'features': {
            'product_pricing': pricing_services_available,
            'dynamic_settings': settings_service.connection_available if hasattr(settings_service, 'connection_available') else False,
            'bulk_operations': pricing_services_available,
            'pricing_validation': True,
            'audit_logging': True
        },
        'timestamp': datetime.now(timezone.utc).isoformat() + "Z"
    })

@pricing_bp.route('/<product_code>', methods=['GET'])
@token_required
def get_product_pricing(product_code):
    """Get pricing for specific product - uses database system"""
    try:
        term_years = request.args.get('term_years', 1, type=int)
        customer_type = request.args.get('customer_type', 'retail')
        
        if pricing_services_available:
            result = get_price_from_db_or_fallback(product_code, term_years, customer_type)
            
            if result['success']:
                return jsonify(result)
            else:
                return jsonify(result['error']), 400
        else:
            return jsonify('Pricing service not available'), 503

    except Exception as e:
        return jsonify(f"Pricing error: {str(e)}"), 500

@pricing_bp.route('/products', methods=['GET'])
@token_required
def get_all_products():
    """Get all product pricing - uses database system"""
    try:
        if pricing_services_available:
            result = get_all_products_pricing()
            return jsonify(result)
        else:
            return jsonify('Pricing service not available'), 503

    except Exception as e:
        return jsonify(f"Failed to get pricing: {str(e)}"), 500

@pricing_bp.route('/quote', methods=['POST'])
@token_required
def generate_pricing_quote():
    """Generate quote using database pricing"""
    try:
        data = request.get_json()
        if not data:
            return jsonify("Request body is required"), 400

        # Validate required fields
        required_fields = ['product_code', 'term_years']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify(f"Missing required fields: {', '.join(missing_fields)}"), 400

        if not pricing_services_available:
            return jsonify('Pricing service not available'), 503

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
            customer_type=data.get('customer_type', 'retail'),
            state=data.get('state', 'FL')
        )

        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result['error']), 400

    except Exception as e:
        return jsonify(f"Quote generation error: {str(e)}"), 500

@pricing_bp.route('/<product_code>', methods=['PUT'])
@token_required
@role_required('admin')
def update_product_pricing(product_code):
    """Update product pricing with database-driven calculations"""
    try:
        data = request.get_json()
        if not data:
            return jsonify("Pricing data is required"), 400

        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify("Database not available"), 503

        # Verify product exists
        product_result = execute_query(
            "SELECT id, base_price FROM products WHERE product_code = %s;", 
            (product_code,), 
            'one'
        )
        
        if not product_result['success'] or not product_result['data']:
            return jsonify("Product not found"), 404

        product_id, current_base_price = product_result['data']['id'], product_result['data']['base_price']

        # Update base price if provided
        new_base_price = data.get('base_price', current_base_price)
        if float(new_base_price) != float(current_base_price):
            update_result = db_manager.update_record(
                'products',
                {'base_price': new_base_price, 'updated_at': datetime.now(timezone.utc)},
                'product_code = %s',
                (product_code,)
            )
            
            if not update_result['success']:
                return jsonify("Failed to update base price"), 500

        # Update pricing multipliers
        if 'pricing' in data:
            # Delete existing pricing
            delete_result = execute_query(
                'DELETE FROM pricing WHERE product_code = %s',
                (product_code,)
            )
            
            # Insert new pricing
            for term_years, customer_prices in data['pricing'].items():
                term = int(term_years)
                
                for customer_type, multiplier in customer_prices.items():
                    insert_result = db_manager.insert_record('pricing', {
                        'product_code': product_code,
                        'term_years': term,
                        'multiplier': float(multiplier),
                        'customer_type': customer_type,
                        'created_at': datetime.now(timezone.utc)
                    })
                    
                    if not insert_result['success']:
                        return jsonify(f"Failed to insert pricing for {term} year {customer_type}"), 500

        return jsonify({
            'message': 'Pricing updated successfully',
            'product_code': product_code,
            'base_price': float(new_base_price),
            'updated_at': datetime.now(timezone.utc).isoformat() + 'Z'
        })

    except Exception as e:
        return jsonify(f"Failed to update pricing: {str(e)}"), 500

@pricing_bp.route('/calculate', methods=['POST'])
@token_required
@role_required('admin')
def calculate_pricing_preview():
    """Calculate pricing preview with database-driven fees and taxes"""
    try:
        data = request.get_json()
        if not data:
            return jsonify("Calculation data is required"), 400

        base_price = float(data.get('base_price', 0))
        term_years = int(data.get('term_years', 1))
        customer_type = data.get('customer_type', 'retail')
        state = data.get('state', 'FL')

        # Get dynamic settings from database
        if settings_service.connection_available:
            admin_fee = get_admin_fee('hero')
            wholesale_discount_rate = get_wholesale_discount()
            tax_rate = get_tax_rate()
            processing_fee = get_processing_fee()
            fee_source = 'database'
        else:
            admin_fee = 25.00
            wholesale_discount_rate = 0.15
            tax_rate = 0.08
            processing_fee = 15.00
            fee_source = 'fallback'

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

        return jsonify({
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
                'admin_fee_source': fee_source,
                'tax_rate_source': fee_source,
                'discount_source': fee_source,
                'state': state
            }
        })

    except Exception as e:
        return jsonify(f"Failed to calculate pricing: {str(e)}"), 500

@pricing_bp.route('/settings', methods=['GET'])
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
                    'processing_fee': get_processing_fee(),
                    'dealer_fee': get_dealer_fee()
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
                }
            }

            # Get Hero-specific settings if available
            if hasattr(settings_service, 'get_admin_setting'):
                settings['hero_settings'] = {
                    'coverage_multiplier_1000': settings_service.get_admin_setting('hero', 'coverage_multiplier_1000', 1.2),
                    'coverage_multiplier_500': settings_service.get_admin_setting('hero', 'coverage_multiplier_500', 1.0),
                    'default_coverage_limit': settings_service.get_admin_setting('hero', 'default_coverage_limit', 500)
                }
            else:
                settings['hero_settings'] = {
                    'coverage_multiplier_1000': 1.2,
                    'coverage_multiplier_500': 1.0,
                    'default_coverage_limit': 500
                }
        else:
            # Fallback settings
            settings = {
                'fees': {
                    'admin_fee': 25.00,
                    'vsc_admin_fee': 50.00,
                    'processing_fee': 15.00,
                    'dealer_fee': 50.00
                },
                'discounts': {
                    'wholesale_discount_rate': 0.15
                },
                'taxes': {
                    'default_tax_rate': 0.00,
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

        return jsonify({
            'settings': settings,
            'database_driven': settings_service.connection_available,
            'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
        })

    except Exception as e:
        return jsonify(f"Failed to get system settings: {str(e)}"), 500

@pricing_bp.route('/settings', methods=['PUT'])
@token_required
@role_required('admin')
def update_system_settings():
    """Update system pricing settings"""
    try:
        data = request.get_json()
        if not data:
            return jsonify("Settings data is required"), 400
        
        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify("Database not available for settings update"), 503
        
        admin_id = request.current_user.get('user_id')
        updated_settings = []
        
        # Update fees
        if 'fees' in data:
            for fee_type, value in data['fees'].items():
                result = db_manager.execute_query('''
                    INSERT INTO admin_settings (category, key, value, updated_by, updated_at) 
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (category, key) 
                    DO UPDATE SET 
                        value = EXCLUDED.value, 
                        updated_at = EXCLUDED.updated_at, 
                        updated_by = EXCLUDED.updated_by
                ''', ('fees', fee_type, str(value), admin_id, datetime.now(timezone.utc)))
                
                if result['success']:
                    updated_settings.append(f"fees.{fee_type}")
        
        # Update discounts
        if 'discounts' in data:
            for discount_type, value in data['discounts'].items():
                result = db_manager.execute_query('''
                    INSERT INTO admin_settings (category, key, value, updated_by, updated_at) 
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (category, key) 
                    DO UPDATE SET 
                        value = EXCLUDED.value, 
                        updated_at = EXCLUDED.updated_at, 
                        updated_by = EXCLUDED.updated_by
                ''', ('discounts', discount_type, str(value), admin_id, datetime.now(timezone.utc)))
                
                if result['success']:
                    updated_settings.append(f"discounts.{discount_type}")
        
        # Update taxes
        if 'taxes' in data:
            for tax_type, value in data['taxes'].items():
                result = db_manager.execute_query('''
                    INSERT INTO admin_settings (category, key, value, updated_by, updated_at) 
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (category, key) 
                    DO UPDATE SET 
                        value = EXCLUDED.value, 
                        updated_at = EXCLUDED.updated_at, 
                        updated_by = EXCLUDED.updated_by
                ''', ('taxes', tax_type, str(value), admin_id, datetime.now(timezone.utc)))
                
                if result['success']:
                    updated_settings.append(f"taxes.{tax_type}")
        
        # Clear settings cache if available
        if hasattr(settings_service, 'clear_cache'):
            settings_service.clear_cache()
        
        return jsonify({
            'message': 'System settings updated successfully',
            'updated_settings': updated_settings,
            'updated_by': admin_id,
            'cache_cleared': True
        })
        
    except Exception as e:
        return jsonify(f"Failed to update settings: {str(e)}"), 500

@pricing_bp.route('/products', methods=['POST'])
@token_required
@role_required('admin')
def create_product():
    """Create new product in database (admin only)"""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['product_code', 'product_name', 'base_price']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify(f"Missing fields: {', '.join(missing_fields)}"), 400

        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify("Database not available"), 503

        # Check if product already exists
        existing_product = execute_query(
            'SELECT id FROM products WHERE product_code = %s;', 
            (data['product_code'],), 
            'one'
        )
        
        if existing_product['success'] and existing_product['data']:
            return jsonify('Product already exists'), 409

        # Insert new product
        product_result = db_manager.insert_record('products', {
            'product_code': data['product_code'],
            'product_name': data['product_name'],
            'description': data.get('description', ''),
            'base_price': data['base_price'],
            'active': data.get('active', True),
            'created_at': datetime.now(timezone.utc)
        })
        
        if not product_result['success']:
            return jsonify('Failed to create product'), 500

        product_id = product_result['inserted_id']

        # Insert default pricing if provided
        if 'pricing' in data:
            for term_years, multiplier in data['pricing'].items():
                term = int(term_years)

                # Insert retail pricing
                retail_result = db_manager.insert_record('pricing', {
                    'product_code': data['product_code'],
                    'term_years': term,
                    'multiplier': multiplier,
                    'customer_type': 'retail',
                    'created_at': datetime.now(timezone.utc)
                })

                # Insert wholesale pricing (15% discount)
                wholesale_multiplier = multiplier * 0.85
                wholesale_result = db_manager.insert_record('pricing', {
                    'product_code': data['product_code'],
                    'term_years': term,
                    'multiplier': wholesale_multiplier,
                    'customer_type': 'wholesale',
                    'created_at': datetime.now(timezone.utc)
                })

        return jsonify({
            'message': 'Product created successfully',
            'product': {
                'id': str(product_id),
                'product_code': data['product_code'],
                'product_name': data['product_name'],
                'base_price': data['base_price'],
                'created_at': datetime.now(timezone.utc).isoformat() + 'Z'
            }
        }), 201

    except Exception as e:
        return jsonify(f"Failed to create product: {str(e)}"), 500

@pricing_bp.route('/products', methods=['GET'])
@token_required
@role_required('admin')
def get_admin_products():
    """Get all products with database-driven pricing info"""
    try:
        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify("Database not available"), 503

        # Get products with pricing information
        products_result = execute_query('''
            SELECT 
                p.id,
                p.product_code,
                p.product_name,
                p.description,
                p.base_price,
                p.active,
                p.created_at,
                COUNT(pr.id) as pricing_count,
                MIN(p.base_price * pr.multiplier) as min_price,
                MAX(p.base_price * pr.multiplier) as max_price,
                ARRAY_AGG(DISTINCT pr.term_years ORDER BY pr.term_years) as terms_available
            FROM products p
            LEFT JOIN pricing pr ON p.product_code = pr.product_code
            GROUP BY p.id, p.product_code, p.product_name, p.description, p.base_price, p.active, p.created_at
            ORDER BY p.product_name;
        ''')

        if not products_result['success']:
            return jsonify("Failed to fetch products"), 500

        products = []
        for row in products_result['data']:
            product = dict(row)
            product['base_price'] = float(product['base_price']) if product['base_price'] else 0
            product['min_price'] = float(product['min_price']) if product['min_price'] else 0
            product['max_price'] = float(product['max_price']) if product['max_price'] else 0
            product['created_at'] = product['created_at'].isoformat() if product['created_at'] else None
            product['terms_available'] = [t for t in (product['terms_available'] or []) if t is not None]
            products.append(product)

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
                'default_tax_rate': 0.00,
                'fl_tax_rate': 0.07,
                'ca_tax_rate': 0.0875,
                'ny_tax_rate': 0.08,
                'processing_fee': 15.00,
                'database_driven': False
            }

        return jsonify({
            'products': products,
            'system_settings': system_settings,
            'total_products': len(products)
        })

    except Exception as e:
        return jsonify(f"Failed to get products: {str(e)}"), 500

@pricing_bp.route('/products/<product_code>', methods=['DELETE'])
@token_required
@role_required('admin')
def delete_product(product_code):
    """Delete product and its pricing (admin only)"""
    try:
        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify("Database not available"), 503

        # Check if product exists
        product_result = execute_query(
            'SELECT product_name FROM products WHERE product_code = %s;', 
            (product_code,), 
            'one'
        )
        
        if not product_result['success'] or not product_result['data']:
            return jsonify('Product not found'), 404

        product_name = product_result['data']['product_name']

        # Delete pricing first (foreign key constraint)
        pricing_delete = execute_query('DELETE FROM pricing WHERE product_code = %s;', (product_code,))

        # Delete product
        product_delete = db_manager.delete_record('products', 'product_code = %s', (product_code,))
        
        if product_delete['success']:
            return jsonify({
                'message': f'Product "{product_name}" and its pricing deleted successfully',
                'deleted_product_code': product_code
            })
        else:
            return jsonify('Failed to delete product'), 500

    except Exception as e:
        return jsonify(f"Failed to delete product: {str(e)}"), 500

@pricing_bp.route('/bulk-update', methods=['POST'])
@token_required
@role_required('admin')
def bulk_update_pricing():
    """Bulk update pricing for multiple products"""
    try:
        data = request.get_json()
        if not data or 'updates' not in data:
            return jsonify("Bulk update data is required"), 400
        
        updates = data['updates']
        if not isinstance(updates, list):
            return jsonify("Updates must be a list"), 400
        
        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify("Database not available"), 503
        
        results = []
        
        for update in updates:
            try:
                product_code = update.get('product_code')
                new_base_price = update.get('base_price')
                
                if not product_code:
                    results.append({
                        'product_code': 'unknown',
                        'success': False,
                        'error': 'Product code required'
                    })
                    continue
                
                if new_base_price is not None:
                    # Update base price
                    price_update = db_manager.update_record(
                        'products',
                        {'base_price': new_base_price, 'updated_at': datetime.now(timezone.utc)},
                        'product_code = %s',
                        (product_code,)
                    )
                    
                    if price_update['success']:
                        results.append({
                            'product_code': product_code,
                            'success': True,
                            'message': f'Base price updated to ${new_base_price}'
                        })
                    else:
                        results.append({
                            'product_code': product_code,
                            'success': False,
                            'error': 'Failed to update base price'
                        })
                else:
                    results.append({
                        'product_code': product_code,
                        'success': False,
                        'error': 'No updates provided'
                    })
                    
            except Exception as item_error:
                results.append({
                    'product_code': update.get('product_code', 'unknown'),
                    'success': False,
                    'error': str(item_error)
                })
        
        successful_updates = len([r for r in results if r['success']])
        
        return jsonify({
            'message': f'Bulk update completed: {successful_updates}/{len(results)} successful',
            'results': results,
            'summary': {
                'total': len(results),
                'successful': successful_updates,
                'failed': len(results) - successful_updates
            }
        })
        
    except Exception as e:
        return jsonify(f"Bulk update failed: {str(e)}"), 500

@pricing_bp.route('/validate', methods=['POST'])
@token_required
@role_required('admin')
def validate_pricing_data():
    """Validate pricing data before saving"""
    try:
        data = request.get_json()
        
        validation_results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'suggestions': []
        }
        
        # Validate base price
        if 'base_price' in data:
            try:
                base_price = float(data['base_price'])
                if base_price <= 0:
                    validation_results['errors'].append('Base price must be greater than 0')
                    validation_results['valid'] = False
                elif base_price > 10000:
                    validation_results['warnings'].append('Base price is unusually high (over $10,000)')
            except (ValueError, TypeError):
                validation_results['errors'].append('Base price must be a valid number')
                validation_results['valid'] = False
        
        # Validate pricing structure
        if 'pricing' in data:
            pricing = data['pricing']
            if not isinstance(pricing, dict):
                validation_results['errors'].append('Pricing must be an object')
                validation_results['valid'] = False
            else:
                for term_years, customer_types in pricing.items():
                    try:
                        term = int(term_years)
                        if term < 1 or term > 10:
                            validation_results['warnings'].append(f'Unusual term length: {term} years')
                    except ValueError:
                        validation_results['errors'].append(f'Invalid term: {term_years}')
                        validation_results['valid'] = False
                    
                    if isinstance(customer_types, dict):
                        for customer_type, multiplier in customer_types.items():
                            if customer_type not in ['retail', 'wholesale']:
                                validation_results['warnings'].append(f'Unusual customer type: {customer_type}')
                            
                            try:
                                mult_value = float(multiplier)
                                if mult_value <= 0:
                                    validation_results['errors'].append(f'Multiplier must be positive for {term_years} year {customer_type}')
                                    validation_results['valid'] = False
                                elif mult_value > 5:
                                    validation_results['warnings'].append(f'High multiplier ({mult_value}) for {term_years} year {customer_type}')
                            except (ValueError, TypeError):
                                validation_results['errors'].append(f'Invalid multiplier for {term_years} year {customer_type}')
                                validation_results['valid'] = False
        
        # Add suggestions
        if validation_results['valid'] and not validation_results['errors']:
            if 'pricing' in data and 'wholesale' not in str(data['pricing']):
                validation_results['suggestions'].append('Consider adding wholesale pricing for reseller partners')
        
        return jsonify(validation_results)
        
    except Exception as e:
        return jsonify(f"Validation failed: {str(e)}"), 500
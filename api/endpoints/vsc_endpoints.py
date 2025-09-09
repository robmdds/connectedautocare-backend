"""
VSC (Vehicle Service Contract) Rating Endpoints
Database-driven VSC pricing with VIN auto-detection
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timezone, timedelta
from utils.service_availability import ServiceChecker

# Initialize blueprint
vsc_bp = Blueprint('vsc', __name__)

# Import services with error handling
try:
    from services.vsc_rating_service import VSCRatingService
    from data.vsc_rates_data import get_vsc_coverage_options, calculate_vsc_price
    from services.enhanced_vin_decoder_service import EnhancedVINDecoderService
    from services.database_settings_service import get_admin_fee, get_tax_rate, get_processing_fee, get_dealer_fee, settings_service
    VSC_SERVICE_AVAILABLE = True
    enhanced_vin_service = EnhancedVINDecoderService()
    enhanced_vin_available = True
except ImportError as e:
    print(f"Warning: VSC service not available: {e}")
    VSC_SERVICE_AVAILABLE = False
    enhanced_vin_available = False
    
    # Create fallback classes
    class VSCRatingService:
        def generate_quote(self, *args, **kwargs):
            return {"success": False, "error": "Service temporarily unavailable"}
    
    class EnhancedVINDecoderService:
        def decode_vin(self, vin, model_year=None):
            return {"success": False, "error": "VIN service not available"}
        def check_vsc_eligibility(self, **kwargs):
            return {"success": False, "error": "VIN service not available"}
    
    def get_vsc_coverage_options(): return {}
    def calculate_vsc_price(*args, **kwargs): return {"success": False, "error": "VSC pricing not available"}
    def get_admin_fee(*args): return 50.00
    def get_tax_rate(*args): return 0.00
    def get_processing_fee(): return 15.00
    def get_dealer_fee(): return 50.00
    
    enhanced_vin_service = EnhancedVINDecoderService()
    
    class DummySettingsService:
        connection_available = False
    settings_service = DummySettingsService()

@vsc_bp.route('/health')
def vsc_health():
    """VSC rating service health check with database integration status"""
    service_checker = ServiceChecker()
    
    if not service_checker.customer_services_available:
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

@vsc_bp.route('/coverage-options')
def get_vsc_coverage():
    """Get available VSC coverage options"""
    service_checker = ServiceChecker()
    
    if not service_checker.customer_services_available:
        return jsonify({"error": "VSC rating service not available"}), 503

    try:
        options = get_vsc_coverage_options()
        return jsonify(options)
    except Exception as e:
        return jsonify({"error": f"Failed to retrieve coverage options: {str(e)}"}), 500

@vsc_bp.route('/quote', methods=['POST'])
def generate_vsc_quote():
    """Generate VSC quote with database-driven pricing and updated eligibility rules"""
    service_checker = ServiceChecker()
    
    if not service_checker.customer_services_available:
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
        if VSC_SERVICE_AVAILABLE:
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
                    tax_rate = get_tax_rate()
                    processing_fee = get_processing_fee()
                    dealer_fee = get_dealer_fee()
                    fee_source = 'database'
                else:
                    # Fallback values
                    admin_fee = 50.00
                    tax_rate = 0.00
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
                
                return jsonify(quote_response)
                
            except Exception as calc_error:
                print(f"Database VSC calculation failed: {calc_error}")
                return jsonify({"error": f"VSC price calculation error: {str(calc_error)}"}), 500
        
        else:
            return jsonify({"error": "VSC pricing system not available"}), 503

    except Exception as e:
        return jsonify({"error": f"VSC quote error: {str(e)}"}), 500

@vsc_bp.route('/eligibility', methods=['POST'])
def check_vsc_eligibility():
    """Check VSC eligibility with updated rules (20 years, 200k miles)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify("Vehicle data is required"), 400

        vin = data.get('vin', '').strip().upper()
        make = data.get('make', '').strip()
        year = data.get('year')
        mileage = data.get('mileage')

        try:
            year = int(year) if year else None
            mileage = int(mileage) if mileage else None
        except (ValueError, TypeError):
            return jsonify("Invalid year or mileage values"), 400

        if not vin and (not make or not year):
            return jsonify("Either VIN or make/year is required"), 400

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
            return jsonify(result)
        else:
            return jsonify(result.get('error', 'Eligibility check failed')), 400

    except Exception as e:
        return jsonify(f"Eligibility check error: {str(e)}"), 500

@vsc_bp.route('/eligibility/requirements', methods=['GET'])
def get_vsc_eligibility_requirements():
    """Get current VSC eligibility requirements"""
    return jsonify({
        'eligibility_requirements': {
            'max_vehicle_age': '20 model years or newer',
            'max_mileage': 'Less than 200,000 miles',
            'message_for_ineligible': "Vehicle doesn't qualify. Make sure you entered the correct current mileage. Vehicle must be 20 model years or newer and less than 200,000 miles at time of quote"
        },
        'coverage_levels': ['silver', 'gold', 'platinum'],
        'available_terms': [12, 24, 36, 48, 60],
        'available_deductibles': [0, 50, 100, 200, 500, 1000],
        'updated': datetime.now(timezone.utc).isoformat() + 'Z'
    })

@vsc_bp.route('/quote/vin', methods=['POST'])
def generate_vsc_quote_from_vin():
    """Generate VSC quote using VIN auto-detection with database integration"""
    try:
        data = request.get_json()
        if not data:
            return jsonify("Quote data is required"), 400

        # Validate required fields
        vin = data.get('vin', '').strip().upper()
        if not vin:
            return jsonify("VIN is required for VIN-based quoting"), 400

        mileage = data.get('mileage')
        if not mileage:
            return jsonify("Mileage is required"), 400

        # Parse optional parameters
        coverage_level = data.get('coverage_level', 'gold').lower()
        term_months = int(data.get('term_months', 36))
        customer_type = data.get('customer_type', 'retail').lower()
        deductible = int(data.get('deductible', 100))

        try:
            mileage = int(mileage)
        except (ValueError, TypeError):
            return jsonify("Invalid mileage value provided"), 400

        # Decode VIN to get vehicle information
        if enhanced_vin_available:
            vin_result = enhanced_vin_service.decode_vin(vin)
        else:
            return jsonify("VIN decoding service not available"), 503

        if not vin_result.get('success'):
            return jsonify("Failed to decode VIN"), 400

        vehicle_info = vin_result.get('vehicle_info', {})
        make = vehicle_info.get('make', '')
        model = vehicle_info.get('model', '')
        year = vehicle_info.get('year', 0)

        if not make or not year:
            return jsonify("Could not extract vehicle make/year from VIN"), 400

        # Use database-driven VSC price calculation
        if VSC_SERVICE_AVAILABLE:
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
                        return jsonify(
                            "Vehicle doesn't qualify. Make sure you entered the correct current mileage. Vehicle must be 20 model years or newer and less than 200,000 miles at time of quote"
                        ), 400
                    else:
                        return jsonify(f"Price calculation failed: {price_result.get('error', 'Unknown error')}"), 400
                
                # Get dynamic fees from database
                if settings_service.connection_available:
                    admin_fee = get_admin_fee('vsc')
                    tax_rate = get_tax_rate()
                    processing_fee = get_processing_fee()
                    dealer_fee = get_dealer_fee()
                    fee_source = 'database'
                else:
                    admin_fee = 50.00
                    tax_rate = 0.00
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

                return jsonify(quote_data)
                
            except Exception as db_error:
                print(f"Database calculation failed for VIN quote: {db_error}")
                return jsonify(f"VSC calculation error: {str(db_error)}"), 500
        
        else:
            return jsonify("VSC pricing system not available"), 503

    except Exception as e:
        return jsonify(f"VIN quote generation error: {str(e)}"), 500
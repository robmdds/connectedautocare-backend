"""
VIN Decoder Endpoints
Enhanced VIN decoding with NHTSA integration and eligibility checking
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
from utils.service_availability import ServiceChecker

# Initialize blueprint
vin_bp = Blueprint('vin', __name__)

# Import services with error handling
try:
    from services.vin_decoder_service import VINDecoderService
    from services.enhanced_vin_decoder_service import EnhancedVINDecoderService
    enhanced_vin_service = EnhancedVINDecoderService()
    vin_service = VINDecoderService()
    enhanced_vin_available = True
except ImportError as e:
    print(f"Warning: VIN service not available: {e}")
    enhanced_vin_available = False
    
    # Create fallback classes
    class VINDecoderService:
        def decode_vin(self, vin):
            return {"success": False, "error": "VIN decoder service not available"}
        def validate_vin(self, vin):
            return {"success": False, "error": "VIN decoder service not available"}
    
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
    vin_service = VINDecoderService()

@vin_bp.route('/health')
def vin_health():
    """VIN decoder service health check"""
    service_checker = ServiceChecker()
    
    return jsonify({
        "service": "VIN Decoder API",
        "status": "healthy" if service_checker.customer_services_available else "unavailable",
        "enhanced_features": "available" if enhanced_vin_available else "basic_only",
        "supported_formats": ["17-character VIN"],
        "features": {
            "basic_decode": service_checker.customer_services_available,
            "enhanced_decode": enhanced_vin_available,
            "eligibility_checking": enhanced_vin_available,
            "external_api_integration": enhanced_vin_available,
            "nhtsa_integration": enhanced_vin_available
        },
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
    })

@vin_bp.route('/validate', methods=['POST'])
def validate_vin():
    """Validate VIN format and checksum"""
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

        # Use enhanced validation if available
        if enhanced_vin_available:
            result = enhanced_vin_service.validate_vin(vin)
            if result.get('success'):
                return jsonify(result)
            else:
                return jsonify(result.get('error', 'VIN validation failed')), 400

        # Basic validation response
        return jsonify({
            "vin": vin,
            "valid": True,
            "format": "valid",
            "validation_method": "basic"
        })

    except Exception as e:
        return jsonify({"error": f"VIN validation error: {str(e)}"}), 500

@vin_bp.route('/decode', methods=['POST'])
def decode_vin():
    """Enhanced VIN decoding with improved NHTSA integration"""
    try:
        data = request.get_json()
        if not data or 'vin' not in data:
            return jsonify({"error": "VIN is required"}), 400

        vin = data['vin'].strip().upper()
        include_eligibility = data.get('include_eligibility', True)
        mileage = data.get('mileage', 0)
        model_year = data.get('model_year')

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
            result = enhanced_vin_service.decode_vin(vin, model_year)
        else:
            # Fallback to basic service
            service_checker = ServiceChecker()
            if not service_checker.customer_services_available:
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
            
            return jsonify(result)
        else:
            return jsonify({"error": result.get('error', 'VIN decode failed')}), 400

    except Exception as e:
        print(f"❌ VIN decode error: {str(e)}")
        return jsonify({"error": f"VIN decode error: {str(e)}"}), 500

@vin_bp.route('/enhanced/validate', methods=['POST'])
def enhanced_validate_vin():
    """Enhanced VIN validation with detailed feedback"""
    try:
        data = request.get_json()
        if not data or 'vin' not in data:
            return jsonify("VIN is required"), 400

        vin = data['vin'].strip().upper()

        if enhanced_vin_available:
            result = enhanced_vin_service.validate_vin(vin)
        else:
            # Fallback to basic validation
            result = vin_service.validate_vin(vin)

        if result.get('success'):
            return jsonify(result)
        else:
            return jsonify(result.get('error', 'VIN validation failed')), 400

    except Exception as e:
        return jsonify(f"VIN validation error: {str(e)}"), 500

@vin_bp.route('/enhanced/decode', methods=['POST'])
def enhanced_decode_vin():
    """Enhanced VIN decoding with eligibility checking"""
    try:
        data = request.get_json()
        if not data or 'vin' not in data:
            return jsonify("VIN is required"), 400

        vin = data['vin'].strip().upper()
        mileage = data.get('mileage', 0)
        model_year = data.get('model_year')

        if enhanced_vin_available:
            result = enhanced_vin_service.get_vin_info_with_eligibility(vin, mileage)
        else:
            # Fallback to basic decoding
            result = vin_service.decode_vin(vin)

        if result.get('success'):
            return jsonify(result)
        else:
            return jsonify(result.get('error', 'VIN decode failed')), 400

    except Exception as e:
        return jsonify(f"VIN decode error: {str(e)}"), 500

@vin_bp.route('/decode/batch', methods=['POST'])
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

        return jsonify({
            'batch_results': results,
            'total_processed': len(results),
            'successful_decodes': len([r for r in results if r['success']]),
            'decode_method': 'enhanced_with_nhtsa' if enhanced_vin_available else 'basic'
        })

    except Exception as e:
        print(f"❌ Batch VIN decode error: {str(e)}")
        return jsonify({"error": f"Batch decode error: {str(e)}"}), 500

@vin_bp.route('/test', methods=['POST'])
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

        return jsonify(results)

    except Exception as e:
        return jsonify({"error": f"Test error: {str(e)}"}), 500

@vin_bp.route('/lookup/<vin>')
def lookup_vin(vin):
    """Quick VIN lookup with cached results"""
    try:
        vin = vin.strip().upper()
        
        if len(vin) != 17:
            return jsonify({"error": "Invalid VIN format"}), 400

        # Check if we have cached results for this VIN
        cache_key = f"vin_lookup_{vin}"
        
        # For now, always decode fresh (implement caching later)
        if enhanced_vin_available:
            result = enhanced_vin_service.decode_vin(vin)
        else:
            service_checker = ServiceChecker()
            if not service_checker.customer_services_available:
                return jsonify({"error": "VIN lookup service not available"}), 503
            result = vin_service.decode_vin(vin)

        if result.get('success'):
            return jsonify({
                'vin': vin,
                'vehicle_info': result['vehicle_info'],
                'cached': False,
                'lookup_time': datetime.now(timezone.utc).isoformat() + 'Z'
            })
        else:
            return jsonify(result.get('error', 'VIN lookup failed')), 400

    except Exception as e:
        return jsonify(f"VIN lookup error: {str(e)}"), 500

@vin_bp.route('/capabilities')
def get_vin_capabilities():
    """Get VIN decoder capabilities and supported features"""
    try:
        service_checker = ServiceChecker()
        
        capabilities = {
            'basic_decoding': service_checker.customer_services_available,
            'enhanced_decoding': enhanced_vin_available,
            'nhtsa_integration': enhanced_vin_available,
            'eligibility_checking': enhanced_vin_available,
            'batch_processing': {
                'available': enhanced_vin_available or service_checker.customer_services_available,
                'max_batch_size': 50,
                'supported_formats': ['array of strings', 'array of objects with vin/model_year']
            },
            'supported_data_points': [
                'make', 'model', 'year', 'body_class', 'engine_info', 
                'transmission', 'drive_type', 'fuel_type'
            ],
            'validation_features': {
                'format_validation': True,
                'checksum_validation': enhanced_vin_available,
                'character_validation': True
            },
            'api_integrations': {
                'nhtsa_vpic': enhanced_vin_available,
                'internal_database': service_checker.customer_services_available
            }
        }
        
        return jsonify(capabilities)
        
    except Exception as e:
        return jsonify(f"Failed to get capabilities: {str(e)}"), 500
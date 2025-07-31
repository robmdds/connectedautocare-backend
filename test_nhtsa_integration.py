# Create this as test_nhtsa_integration.py in your root directory

#!/usr/bin/env python3
"""
Test script for NHTSA VIN API integration
Run this after making the changes to verify everything works
"""

import sys
import os

# Add the api directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))

def test_enhanced_vin_service():
    """Test the enhanced VIN decoder service"""
    print("🔧 Testing Enhanced VIN Decoder Service")
    print("=" * 50)
    
    try:
        from api.services.enhanced_vin_decoder_service import EnhancedVINDecoderService
        
        decoder = EnhancedVINDecoderService()
        test_vin = "1HGBH41JXMN109186"
        
        print(f"Testing VIN: {test_vin}")
        
        # Test without model year
        print("\n📋 Test 1: VIN decode without model year")
        result1 = decoder.decode_vin(test_vin)
        
        if result1.get('success'):
            vehicle_info = result1['vehicle_info']
            print(f"✅ Success! Decode method: {vehicle_info.get('decode_method')}")
            print(f"   Make: {vehicle_info.get('make')}")
            print(f"   Model: {vehicle_info.get('model')}")
            print(f"   Year: {vehicle_info.get('year')}")
            print(f"   Body Style: {vehicle_info.get('body_style')}")
        else:
            print(f"❌ Failed: {result1.get('error')}")
        
        # Test with model year
        print("\n📋 Test 2: VIN decode with model year")
        result2 = decoder.decode_vin(test_vin, 2021)
        
        if result2.get('success'):
            vehicle_info = result2['vehicle_info']
            print(f"✅ Success! Decode method: {vehicle_info.get('decode_method')}")
            print(f"   Make: {vehicle_info.get('make')}")
            print(f"   Model: {vehicle_info.get('model')}")
            print(f"   Year: {vehicle_info.get('year')}")
            print(f"   NHTSA fields: {vehicle_info.get('api_fields_returned', 'N/A')}")
        else:
            print(f"❌ Failed: {result2.get('error')}")
        
        # Test eligibility check
        print("\n📋 Test 3: VIN with eligibility check")
        result3 = decoder.get_vin_info_with_eligibility(test_vin, 75000)
        
        if result3.get('success'):
            eligibility = result3.get('eligibility', {})
            print(f"✅ Eligibility check complete")
            print(f"   Eligible: {eligibility.get('eligible')}")
            print(f"   Warnings: {len(eligibility.get('warnings', []))}")
            print(f"   Restrictions: {len(eligibility.get('restrictions', []))}")
        else:
            print(f"❌ Eligibility check failed: {result3.get('error')}")
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure you've updated enhanced_vin_decoder_service.py")
    except Exception as e:
        print(f"❌ Test error: {e}")

def test_vsc_service_integration():
    """Test VSC service with VIN integration"""
    print("\n🚗 Testing VSC Service VIN Integration")
    print("=" * 50)
    
    try:
        from api.services.vsc_rating_service import VSCRatingService
        
        vsc_service = VSCRatingService()
        test_vin = "1HGBH41JXMN109186"
        
        # Test VIN-based quote generation (if you added the method)
        if hasattr(vsc_service, 'generate_quote_from_vin'):
            print(f"Testing VIN-based quote: {test_vin}")
            
            result = vsc_service.generate_quote_from_vin(
                vin=test_vin,
                mileage=75000,
                coverage_level='gold',
                term_months=36
            )
            
            if result.get('success'):
                print(f"✅ VIN-based quote successful!")
                print(f"   Total Price: ${result['pricing_breakdown']['total_price']:,.2f}")
                print(f"   Vehicle: {result['vehicle_info']['year']} {result['vehicle_info']['make']} {result['vehicle_info']['model']}")
                print(f"   VIN Decode Method: {result.get('vin_info', {}).get('decode_method', 'N/A')}")
            else:
                print(f"❌ VIN-based quote failed: {result.get('error')}")
        else:
            print("⚠️ VIN-based quote method not implemented yet")
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
    except Exception as e:
        print(f"❌ Test error: {e}")

def test_nhtsa_api_direct():
    """Test NHTSA API directly"""
    print("\n🌐 Testing NHTSA API Direct Connection")
    print("=" * 50)
    
    try:
        import requests
        
        test_vin = "1HGBH41JXMN109186"
        url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{test_vin}?format=json"
        
        print(f"API URL: {url}")
        
        response = requests.get(url, timeout=15)
        print(f"Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            results = data.get('Results', [])
            print(f"✅ API Response: {len(results)} fields returned")
            
            # Show key fields
            key_fields = ['Make', 'Model', 'Model Year', 'Body Class']
            for result in results:
                variable = result.get('Variable', '')
                value = result.get('Value', '')
                
                if variable in key_fields and value not in ['Not Applicable', '', 'N/A']:
                    print(f"   {variable}: {value}")
        else:
            print(f"❌ API Error: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"❌ Direct API test error: {e}")

def test_api_endpoints():
    """Test if the Flask app can be imported and endpoints exist"""
    print("\n🚀 Testing API Endpoints")
    print("=" * 50)
    
    try:
        from api.index import app
        
        print("✅ Flask app imported successfully")
        
        # Check if new endpoints exist
        routes = []
        for rule in app.url_map.iter_rules():
            if '/vin/' in rule.rule:
                routes.append(f"{rule.methods} {rule.rule}")
        
        print(f"✅ Found {len(routes)} VIN-related endpoints:")
        for route in routes:
            print(f"   {route}")
            
    except ImportError as e:
        print(f"❌ Flask app import error: {e}")
    except Exception as e:
        print(f"❌ Endpoint test error: {e}")

def main():
    """Run all tests"""
    print("🧪 NHTSA VIN Integration Test Suite")
    print("=" * 70)
    
    test_nhtsa_api_direct()
    test_enhanced_vin_service()
    test_vsc_service_integration()
    test_api_endpoints()
    
    print("\n🎯 SUMMARY & NEXT STEPS")
    print("=" * 70)
    print("1. ✅ If all tests pass: Your integration is working!")
    print("2. ⚠️ If NHTSA API fails: Check internet connection")
    print("3. ❌ If imports fail: Make sure you've updated the files")
    print("4. 🚀 Ready to test via HTTP requests to your API")
    
    print("\n📋 Test HTTP Request Examples:")
    print("-" * 40)
    print("POST /api/vin/decode")
    print('{"vin": "1HGBH41JXMN109186", "model_year": 2021}')
    print()
    print("POST /api/vin/test")
    print('{"vin": "1HGBH41JXMN109186", "debug": true}')

if __name__ == "__main__":
    main()
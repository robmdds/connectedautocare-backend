import requests
import json
from typing import Dict, Optional

def decode_vin_nhtsa(vin: str, model_year: Optional[int] = None) -> Dict:
    """
    Decode VIN using NHTSA API with improved error handling and data extraction
    """
    try:
        # Clean and validate VIN
        vin = vin.strip().upper().replace('*', '')
        
        # Build API URL
        url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{vin}"
        params = {'format': 'json'}
        
        if model_year:
            params['modelyear'] = model_year
        
        print(f"🔍 Decoding VIN: {vin}")
        if model_year:
            print(f"📅 Using model year: {model_year}")
        
        # Make API request
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        results = data.get('Results', [])
        
        if not results:
            return {'success': False, 'error': 'No results from NHTSA API'}
        
        # Extract vehicle information
        vehicle_info = {}
        
        # Key fields to extract
        key_fields = {
            'Make': 'make',
            'Model': 'model', 
            'Model Year': 'year',
            'Trim': 'trim',
            'Body Class': 'body_class',
            'Vehicle Type': 'vehicle_type',
            'Fuel Type - Primary': 'fuel_type',
            'Engine Number of Cylinders': 'cylinders',
            'Displacement (L)': 'displacement_l',
            'Engine Brake (hp) From': 'horsepower',
            'Drive Type': 'drive_type',
            'Transmission Style': 'transmission',
            'Doors': 'doors',
            'Plant Country': 'country',
            'Manufacturer Name': 'manufacturer'
        }
        
        # Process API results
        for result in results:
            variable = result.get('Variable', '')
            value = result.get('Value', '')
            
            # Skip empty/null values
            if not value or value in ['Not Applicable', 'N/A', 'null', None]:
                continue
            
            # Extract key information
            if variable in key_fields:
                field_name = key_fields[variable]
                
                # Clean and convert values
                if variable == 'Model Year':
                    try:
                        vehicle_info[field_name] = int(value)
                    except (ValueError, TypeError):
                        continue
                elif variable in ['Engine Number of Cylinders', 'Doors']:
                    try:
                        vehicle_info[field_name] = int(value)
                    except (ValueError, TypeError):
                        vehicle_info[field_name] = value
                elif variable == 'Displacement (L)':
                    try:
                        vehicle_info[field_name] = float(value)
                    except (ValueError, TypeError):
                        vehicle_info[field_name] = value
                else:
                    vehicle_info[field_name] = value.strip()
        
        # Check if we got essential information
        if not vehicle_info.get('make'):
            return {'success': False, 'error': 'Could not extract manufacturer information'}
        
        # Add metadata
        vehicle_info.update({
            'vin': vin,
            'api_source': 'NHTSA',
            'fields_found': len(vehicle_info)
        })
        
        return {
            'success': True,
            'vehicle_info': vehicle_info,
            'raw_response_count': len(results)
        }
        
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': f'API request failed: {str(e)}'}
    except Exception as e:
        return {'success': False, 'error': f'Decode error: {str(e)}'}

def test_vin_decoder():
    """Test the VIN decoder with various examples"""
    
    # Test VINs
    test_vins = [
        ('5UXWX7C59BA298393', 2011),  # Complete BMW VIN
        ('1HGBH41JXMN109186', None),  # Honda VIN
        ('1G1ZT53806F109149', None),  # Chevrolet VIN
    ]
    
    for vin, year in test_vins:
        print(f"\n{'='*50}")
        print(f"Testing VIN: {vin}")
        
        result = decode_vin_nhtsa(vin, year)
        
        if result['success']:
            vehicle_info = result['vehicle_info']
            print(f"✅ Successfully decoded:")
            print(f"   Make: {vehicle_info.get('make', 'N/A')}")
            print(f"   Model: {vehicle_info.get('model', 'N/A')}")
            print(f"   Year: {vehicle_info.get('year', 'N/A')}")
            print(f"   Trim: {vehicle_info.get('trim', 'N/A')}")
            print(f"   Body Class: {vehicle_info.get('body_class', 'N/A')}")
            print(f"   Engine: {vehicle_info.get('cylinders', 'N/A')} cyl, {vehicle_info.get('displacement_l', 'N/A')}L")
            print(f"   Total fields: {vehicle_info.get('fields_found', 0)}")
        else:
            print(f"❌ Failed: {result['error']}")

# Example usage for your specific case
def decode_bmw_example():
    """Decode the BMW example from your data"""
    # Using a complete VIN instead of the partial one
    complete_vin = "5UXWX7C59BA298393"  # Example complete VIN
    
    result = decode_vin_nhtsa(complete_vin, 2011)
    
    print("BMW X3 Example:")
    print(json.dumps(result, indent=2))
    
    return result

if __name__ == "__main__":
    test_vin_decoder()
    print(f"\n{'='*50}")
    decode_bmw_example()
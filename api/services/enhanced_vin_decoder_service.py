#!/usr/bin/env python3
"""
Enhanced VIN Decoder Service with Eligibility Rules
Handles VIN validation, decoding, and VSC eligibility checking
"""

import re
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

class EnhancedVINDecoderService:
    """Enhanced service for VIN validation, decoding, and eligibility checking"""
    
    def __init__(self):
        self.vin_pattern = re.compile(r'^[A-HJ-NPR-Z0-9]{17}$')
        
        # Enhanced WMI mappings with more manufacturers
        self.wmi_mappings = {
            # Honda/Acura
            '1HG': 'Honda', '1HT': 'Honda', '2HG': 'Honda', '3HG': 'Honda',
            'JHM': 'Honda', '19X': 'Honda', '19U': 'Acura', 'JH4': 'Acura',
            
            # Toyota/Lexus
            '4T1': 'Toyota', '4T3': 'Toyota', '5TD': 'Toyota', 'JTD': 'Toyota',
            'JTG': 'Toyota', 'JTH': 'Toyota', 'JTJ': 'Toyota', 'JTK': 'Toyota',
            'JTL': 'Toyota', 'JTM': 'Toyota', 'JTN': 'Toyota', 'JTP': 'Toyota',
            'JTR': 'Toyota', 'JTS': 'Toyota', 'JTT': 'Toyota', 'JTW': 'Toyota',
            'JTX': 'Toyota', 'JTY': 'Toyota', 'JTZ': 'Toyota',
            'JT2': 'Lexus', 'JTH': 'Lexus', 'JTJ': 'Lexus',
            
            # GM Brands
            '1G1': 'Chevrolet', '1G6': 'Cadillac', '1GC': 'Chevrolet', '1GM': 'Chevrolet',
            '2G1': 'Chevrolet', '3G1': 'Chevrolet', '1GT': 'GMC', '3GT': 'GMC',
            '1GB': 'Chevrolet', '2GB': 'Chevrolet', '3GB': 'Chevrolet',
            '1G4': 'Buick', '2G4': 'Buick', '3G4': 'Buick',
            '1G2': 'Pontiac', '2G2': 'Pontiac', '3G2': 'Pontiac',
            '1G8': 'Saturn', '2G8': 'Saturn', '3G8': 'Saturn',
            
            # Ford Motor Company
            '1FA': 'Ford', '1FB': 'Ford', '1FC': 'Ford', '1FD': 'Ford', '1FE': 'Ford',
            '1FF': 'Ford', '1FG': 'Ford', '1FH': 'Ford', '1FJ': 'Ford', '1FK': 'Ford',
            '1FL': 'Ford', '1FM': 'Ford', '1FN': 'Ford', '1FP': 'Ford', '1FR': 'Ford',
            '1FS': 'Ford', '1FT': 'Ford', '1FU': 'Ford', '1FV': 'Ford', '1FW': 'Ford',
            '1FX': 'Ford', '1FY': 'Ford', '1FZ': 'Ford',
            '1LN': 'Lincoln', '5LM': 'Lincoln',
            
            # Chrysler/Stellantis
            '1C3': 'Chrysler', '1C4': 'Chrysler', '1C6': 'Chrysler', '1C8': 'Chrysler',
            '2C3': 'Chrysler', '2C4': 'Chrysler', '2C8': 'Chrysler',
            '3C3': 'Chrysler', '3C4': 'Chrysler', '3C6': 'Chrysler', '3C8': 'Chrysler',
            '1B3': 'Dodge', '1B4': 'Dodge', '1B6': 'Dodge', '1B7': 'Dodge',
            '2B3': 'Dodge', '2B4': 'Dodge', '2B7': 'Dodge',
            '3B3': 'Dodge', '3B4': 'Dodge', '3B6': 'Dodge', '3B7': 'Dodge',
            '1J4': 'Jeep', '1J8': 'Jeep', '3C7': 'Ram',
            
            # Hyundai/Kia
            'KMH': 'Hyundai', 'KM8': 'Hyundai', 'KNA': 'Kia', 'KND': 'Kia',
            
            # Nissan/Infiniti
            '1N4': 'Nissan', '1N6': 'Nissan', 'JN1': 'Nissan', 'JN6': 'Nissan',
            'JN8': 'Nissan', 'JNA': 'Infiniti', 'JNK': 'Infiniti', 'JNR': 'Infiniti',
            
            # German Luxury
            'WBA': 'BMW', 'WBS': 'BMW', 'WBX': 'BMW', '4US': 'BMW', '5UX': 'BMW',
            'WDD': 'Mercedes-Benz', 'WDC': 'Mercedes-Benz', 'WDF': 'Mercedes-Benz',
            'WAU': 'Audi', 'WA1': 'Audi', 'TRU': 'Audi',
            'WVW': 'Volkswagen', 'WV1': 'Volkswagen', '3VW': 'Volkswagen',
            
            # Volvo
            'YV1': 'Volvo', 'YV4': 'Volvo',
            
            # Mazda
            'JM1': 'Mazda', 'JM3': 'Mazda', '4F2': 'Mazda', '4F4': 'Mazda',
            
            # Mitsubishi
            'JA3': 'Mitsubishi', 'JA4': 'Mitsubishi', '4A3': 'Mitsubishi', '4A4': 'Mitsubishi',
            
            # Subaru
            'JF1': 'Subaru', 'JF2': 'Subaru', '4S3': 'Subaru', '4S4': 'Subaru'
        }
        
        # Enhanced model year mappings (10th position) - handles 30-year cycle
        self.year_mappings = {
            'A': 1980, 'B': 1981, 'C': 1982, 'D': 1983, 'E': 1984, 'F': 1985,
            'G': 1986, 'H': 1987, 'J': 1988, 'K': 1989, 'L': 1990, 'M': 1991,
            'N': 1992, 'P': 1993, 'R': 1994, 'S': 1995, 'T': 1996, 'V': 1997,
            'W': 1998, 'X': 1999, 'Y': 2000, '1': 2001, '2': 2002, '3': 2003,
            '4': 2004, '5': 2005, '6': 2006, '7': 2007, '8': 2008, '9': 2009
        }
        
        # VSC Eligibility Rules
        self.eligibility_rules = {
            'max_age_years': 15,
            'max_mileage': 150000,
            'warning_age_years': 10,
            'warning_mileage': 125000,
            'luxury_brands': ['BMW', 'Mercedes-Benz', 'Audi', 'Lexus', 'Cadillac', 'Lincoln', 'Acura', 'Infiniti'],
            'high_maintenance_brands': ['Land Rover', 'Jaguar', 'Porsche', 'Maserati', 'Bentley', 'Rolls-Royce'],
            'excluded_vehicle_types': ['motorcycle', 'recreational_vehicle', 'commercial_truck']
        }
    
    def validate_vin(self, vin: str) -> Dict:
        """
        Enhanced VIN validation with detailed feedback
        """
        try:
            if not vin:
                return self._validation_error('VIN is required')
            
            vin = vin.strip().upper()
            
            # Length check
            if len(vin) != 17:
                return self._validation_error(f'VIN must be exactly 17 characters (received {len(vin)})')
            
            # Format check (no I, O, Q allowed)
            if not self.vin_pattern.match(vin):
                invalid_chars = [char for char in vin if char in 'IOQ']
                if invalid_chars:
                    return self._validation_error(f'VIN contains invalid characters: {", ".join(invalid_chars)} (I, O, Q not allowed)')
                else:
                    return self._validation_error('VIN contains invalid characters')
            
            # Check digit validation
            check_digit_valid = self._validate_check_digit(vin)
            
            return {
                'success': True,
                'valid': True,
                'vin': vin,
                'message': 'VIN is valid',
                'check_digit_valid': check_digit_valid,
                'validation_details': {
                    'length_check': 'passed',
                    'format_check': 'passed',
                    'check_digit': 'passed' if check_digit_valid else 'warning'
                }
            }
            
        except Exception as e:
            return self._validation_error(f'VIN validation error: {str(e)}')
    
    def decode_vin(self, vin: str) -> Dict:
        """Enhanced VIN decoding with eligibility checking"""
        try:
            # First validate the VIN
            validation_result = self.validate_vin(vin)
            if not validation_result.get('valid'):
                return validation_result
            
            vin = vin.strip().upper()
            
            # Extract VIN components
            wmi = vin[:3]  # World Manufacturer Identifier
            vds = vin[3:9]  # Vehicle Descriptor Section
            vis = vin[9:]   # Vehicle Identifier Section
            
            # Try external API for detailed information first
            detailed_info = self._try_external_decode(vin)
            
            if detailed_info and detailed_info.get('success'):
                vehicle_info = detailed_info['vehicle_info']
            else:
                # Fallback to basic decoding
                make = self._decode_manufacturer(wmi)
                year = self._decode_year(vin[9])  # Position 10 (index 9)
                
                vehicle_info = {
                    'vin': vin,
                    'make': make,
                    'year': year,
                    'model': 'Model information not available',
                    'trim': 'Trim information not available',
                    'engine': 'Engine information not available',
                    'transmission': 'Transmission information not available',
                    'body_style': 'Body style not available',
                    'fuel_type': 'Fuel type not available',
                    'plant_code': vin[10],
                    'wmi': wmi,
                    'vds': vds,
                    'vis': vis,
                    'decode_method': 'basic_structure'
                }
            
            # Calculate vehicle age properly
            current_year = datetime.now().year
            year = vehicle_info.get('year')
            if year:
                vehicle_age = current_year - year
                # Validate age is reasonable (not negative, not more than 50 years)
                if vehicle_age < 0:
                    vehicle_age = 0
                elif vehicle_age > 50:
                    # Might be wrong year due to 30-year cycle confusion
                    vehicle_age = current_year - (year + 30) if year + 30 <= current_year else vehicle_age
            else:
                vehicle_age = None
            
            # Add calculated fields
            vehicle_info.update({
                'vehicle_age': vehicle_age,
                'current_year': current_year,
                'decode_timestamp': datetime.utcnow().isoformat() + 'Z'
            })
            
            return {
                'success': True,
                'vehicle_info': vehicle_info,
                'vin': vin,
                'decode_method': vehicle_info.get('decode_method', 'enhanced_structure'),
                'validation_details': validation_result.get('validation_details', {})
            }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'VIN decode error: {str(e)}'
            }
    
    def check_vsc_eligibility(self, vin: str = None, make: str = None, year: int = None, 
                             mileage: int = None, vehicle_info: Dict = None) -> Dict:
        """
        Check VSC eligibility based on vehicle information
        """
        try:
            # If VIN provided, decode it first
            if vin and not vehicle_info:
                decode_result = self.decode_vin(vin)
                if not decode_result.get('success'):
                    return decode_result
                vehicle_info = decode_result['vehicle_info']
                make = vehicle_info.get('make', make)
                year = vehicle_info.get('year', year)
            
            # Use provided parameters if vehicle_info not available
            if not vehicle_info:
                vehicle_info = {
                    'make': make,
                    'year': year,
                    'mileage': mileage
                }
            
            # Calculate vehicle age
            current_year = datetime.now().year
            vehicle_age = current_year - year if year else None
            
            # Initialize eligibility check
            eligible = True
            warnings = []
            restrictions = []
            pricing_factors = {}
            
            # Age eligibility check
            if vehicle_age is not None:
                if vehicle_age > self.eligibility_rules['max_age_years']:
                    eligible = False
                    restrictions.append(
                        f"Vehicle is {vehicle_age} years old (maximum {self.eligibility_rules['max_age_years']} years allowed)"
                    )
                elif vehicle_age > self.eligibility_rules['warning_age_years']:
                    warnings.append(
                        f"Vehicle is {vehicle_age} years old - limited coverage options and higher rates may apply"
                    )
                
                # Age pricing factor
                if vehicle_age <= 3:
                    pricing_factors['age_factor'] = 1.0
                elif vehicle_age <= 6:
                    pricing_factors['age_factor'] = 1.15
                elif vehicle_age <= 10:
                    pricing_factors['age_factor'] = 1.35
                else:
                    pricing_factors['age_factor'] = 1.60
            
            # Mileage eligibility check
            if mileage is not None:
                if mileage > self.eligibility_rules['max_mileage']:
                    eligible = False
                    restrictions.append(
                        f"Vehicle has {mileage:,} miles (maximum {self.eligibility_rules['max_mileage']:,} miles allowed)"
                    )
                elif mileage > self.eligibility_rules['warning_mileage']:
                    warnings.append(
                        f"High mileage vehicle ({mileage:,} miles) - premium rates will apply"
                    )
                
                # Mileage pricing factor
                if mileage <= 50000:
                    pricing_factors['mileage_factor'] = 1.0
                elif mileage <= 75000:
                    pricing_factors['mileage_factor'] = 1.15
                elif mileage <= 100000:
                    pricing_factors['mileage_factor'] = 1.30
                elif mileage <= 125000:
                    pricing_factors['mileage_factor'] = 1.50
                else:
                    pricing_factors['mileage_factor'] = 1.75
            
            # Make-based considerations
            if make:
                make_upper = make.upper()
                
                # Luxury vehicle considerations
                if any(luxury_brand.upper() in make_upper for luxury_brand in self.eligibility_rules['luxury_brands']):
                    warnings.append('Luxury vehicle - specialized coverage options and premium rates apply')
                    pricing_factors['luxury_multiplier'] = 1.25
                
                # High maintenance vehicle considerations
                if any(hm_brand.upper() in make_upper for hm_brand in self.eligibility_rules['high_maintenance_brands']):
                    warnings.append('High-maintenance vehicle - limited coverage options and significantly higher rates')
                    pricing_factors['high_maintenance_multiplier'] = 1.50
                
                # Vehicle class determination for pricing
                vehicle_class = self._determine_vehicle_class(make)
                pricing_factors['vehicle_class'] = vehicle_class
            
            # Additional eligibility factors
            recommendations = self._generate_recommendations(vehicle_info, eligible, warnings)
            coverage_options = self._get_available_coverage_options(vehicle_info, eligible)
            
            return {
                'success': True,
                'eligible': eligible,
                'vehicle_info': vehicle_info,
                'eligibility_details': {
                    'vehicle_age': vehicle_age,
                    'mileage': mileage,
                    'make': make,
                    'year': year
                },
                'warnings': warnings,
                'restrictions': restrictions,
                'pricing_factors': pricing_factors,
                'recommendations': recommendations,
                'coverage_options': coverage_options,
                'assessment_date': datetime.utcnow().isoformat() + 'Z',
                'rules_version': '2025.1'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Eligibility check error: {str(e)}'
            }
    
    def get_vin_info_with_eligibility(self, vin: str, mileage: int = None) -> Dict:
        """
        Get comprehensive VIN information including eligibility check
        """
        try:
            # Decode VIN
            decode_result = self.decode_vin(vin)
            if not decode_result.get('success'):
                return decode_result
            
            vehicle_info = decode_result['vehicle_info']
            
            # Check eligibility
            eligibility_result = self.check_vsc_eligibility(
                vehicle_info=vehicle_info,
                mileage=mileage
            )
            
            if not eligibility_result.get('success'):
                return eligibility_result
            
            # Combine results
            return {
                'success': True,
                'vin': vin,
                'vehicle_info': vehicle_info,
                'eligibility': eligibility_result,
                'decode_method': decode_result.get('decode_method'),
                'validation_details': decode_result.get('validation_details'),
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'VIN analysis error: {str(e)}'
            }
    
    def _validation_error(self, message: str) -> Dict:
        """Helper method for validation errors"""
        return {
            'success': False,
            'valid': False,
            'error': message
        }
    
    def _validate_check_digit(self, vin: str) -> bool:
        """Enhanced VIN check digit validation"""
        try:
            weights = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
            transliteration = {
                'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8,
                'J': 1, 'K': 2, 'L': 3, 'M': 4, 'N': 5, 'P': 7, 'R': 9,
                'S': 2, 'T': 3, 'U': 4, 'V': 5, 'W': 6, 'X': 7, 'Y': 8, 'Z': 9
            }
            
            sum_value = 0
            for i, char in enumerate(vin):
                if char.isdigit():
                    value = int(char)
                else:
                    value = transliteration.get(char, 0)
                sum_value += value * weights[i]
            
            remainder = sum_value % 11
            check_digit = 'X' if remainder == 10 else str(remainder)
            
            return vin[8] == check_digit
            
        except Exception:
            # Return True for international VINs that may not follow US check digit rules
            return True
    
    def _decode_manufacturer(self, wmi: str) -> str:
        """Enhanced manufacturer decoding"""
        # Check exact match first
        if wmi in self.wmi_mappings:
            return self.wmi_mappings[wmi]
        
        # Check partial matches (first 2 characters)
        for key, value in self.wmi_mappings.items():
            if wmi.startswith(key[:2]):
                return value
        
        # Geographic region fallback based on first character
        first_char = wmi[0]
        if first_char in '12345':
            return 'North American Manufacturer'
        elif first_char in 'SABCDEFGH':
            return 'African Manufacturer'
        elif first_char in 'JKLMNPR':
            return 'Asian Manufacturer'
        elif first_char in 'STUVWXYZ':
            return 'European Manufacturer'
        elif first_char in '6789':
            return 'Oceanian Manufacturer'
        
        return 'Unknown Manufacturer'
    
    def _decode_year(self, year_char: str) -> Optional[int]:
        """Enhanced model year decoding with 30-year cycle handling"""
        current_year = datetime.now().year
        
        # Updated year mappings to handle current timeframe properly
        year_mappings = {
            # Letters for 2010-2030
            'A': 2010, 'B': 2011, 'C': 2012, 'D': 2013, 'E': 2014, 'F': 2015,
            'G': 2016, 'H': 2017, 'J': 2018, 'K': 2019, 'L': 2020, 'M': 2021,
            'N': 2022, 'P': 2023, 'R': 2024, 'S': 2025, 'T': 2026, 'V': 2027,
            'W': 2028, 'X': 2029, 'Y': 2030,
            
            # Numbers for 2001-2009 and 2031-2039
            '1': 2001, '2': 2002, '3': 2003, '4': 2004, '5': 2005,
            '6': 2006, '7': 2007, '8': 2008, '9': 2009
        }
        
        if year_char in year_mappings:
            decoded_year = year_mappings[year_char]
            
            # For your VIN: 1HGBH41JXMN109186
            # Position 10 is 'N' which should be 2022
            # But if the car seems too new, it might be from the previous 30-year cycle
            
            # If decoded year is in the future, subtract 30 years
            if decoded_year > current_year + 1:
                decoded_year -= 30
            
            # Validate reasonable year range (1980-2030)
            if 1980 <= decoded_year <= current_year + 2:
                return decoded_year
        
        return None
    
    def _try_external_decode(self, vin: str) -> Optional[Dict]:
        """
        Attempt to decode VIN using external APIs
        Priority: NHTSA (free) -> Commercial APIs (if configured)
        """
        try:
            # Try NHTSA VIN Decoder API (free but limited)
            nhtsa_result = self._try_nhtsa_decode(vin)
            if nhtsa_result and nhtsa_result.get('success'):
                return nhtsa_result
            
            # Add other API attempts here (AutoCheck, Carfax, etc.)
            # These would require API keys and paid subscriptions
            
            return None
            
        except Exception as e:
            print(f"External VIN decode error: {e}")
            return None
    
    def _try_nhtsa_decode(self, vin: str) -> Optional[Dict]:
        """Improved NHTSA API decoding with better data extraction"""
        try:
            url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{vin}?format=json"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('Results', [])
                
                if results:
                    vehicle_info = {}
                    
                    # Extract relevant information from NHTSA response
                    for result in results:
                        variable = result.get('Variable', '')
                        value = result.get('Value', '')
                        
                        if value and value not in ['Not Applicable', '', 'N/A']:
                            if variable == 'Make':
                                vehicle_info['make'] = value
                            elif variable == 'Model':
                                vehicle_info['model'] = value
                            elif variable == 'Model Year':
                                try:
                                    vehicle_info['year'] = int(value)
                                except (ValueError, TypeError):
                                    pass
                            elif variable == 'Trim':
                                vehicle_info['trim'] = value
                            elif variable == 'Engine Number of Cylinders':
                                vehicle_info['engine_cylinders'] = value
                            elif variable == 'Engine Model':
                                vehicle_info['engine'] = value
                            elif variable == 'Transmission Style':
                                vehicle_info['transmission'] = value
                            elif variable == 'Body Class':
                                vehicle_info['body_style'] = value
                            elif variable == 'Fuel Type - Primary':
                                vehicle_info['fuel_type'] = value
                            elif variable == 'Vehicle Type':
                                vehicle_info['vehicle_type'] = value
                    
                    # If NHTSA didn't provide year, decode from VIN position 10
                    if 'year' not in vehicle_info:
                        decoded_year = self._decode_year(vin[9])
                        if decoded_year:
                            vehicle_info['year'] = decoded_year
                    
                    # If NHTSA didn't provide make, decode from WMI
                    if 'make' not in vehicle_info:
                        vehicle_info['make'] = self._decode_manufacturer(vin[:3])
                    
                    # Clean up the model field - sometimes NHTSA returns year as model
                    if 'model' in vehicle_info and vehicle_info['model'].isdigit():
                        year_from_model = int(vehicle_info['model'])
                        if 1980 <= year_from_model <= 2030:
                            # If model is actually a year, use it and clear model
                            if 'year' not in vehicle_info:
                                vehicle_info['year'] = year_from_model
                            vehicle_info['model'] = 'Model information not available'
                    
                    # Add VIN structure info
                    vehicle_info.update({
                        'vin': vin,
                        'wmi': vin[:3],
                        'vds': vin[3:9],
                        'vis': vin[9:],
                        'decode_method': 'nhtsa_api'
                    })
                    
                    return {
                        'success': True,
                        'vehicle_info': vehicle_info
                    }
            
            return None
            
        except Exception as e:
            print(f"NHTSA decode error: {e}")
            return None
    
    def _determine_vehicle_class(self, make: str) -> str:
        """Determine vehicle class for pricing (A, B, C)"""
        if not make:
            return 'B'  # Default
        
        make_upper = make.upper()
        
        # Class A - Most Reliable (Lowest Rates)
        class_a_brands = ['HONDA', 'ACURA', 'TOYOTA', 'LEXUS', 'NISSAN', 'INFINITI', 
                         'HYUNDAI', 'KIA', 'MAZDA', 'MITSUBISHI', 'SUBARU']
        
        # Class C - Higher Risk (Highest Rates)
        class_c_brands = ['BMW', 'MERCEDES', 'AUDI', 'CADILLAC', 'LINCOLN', 'VOLKSWAGEN', 
                         'VOLVO', 'JAGUAR', 'LAND ROVER', 'PORSCHE', 'SAAB', 'MINI']
        
        for brand in class_a_brands:
            if brand in make_upper:
                return 'A'
        
        for brand in class_c_brands:
            if brand in make_upper:
                return 'C'
        
        # Class B - Everything else (Medium Rates)
        return 'B'
    
    def _generate_recommendations(self, vehicle_info: Dict, eligible: bool, warnings: List[str]) -> List[str]:
        """Generate recommendations based on vehicle characteristics"""
        recommendations = []
        
        if not eligible:
            recommendations.append("Consider our Hero Products for alternative protection options")
            recommendations.append("Look into manufacturer extended warranty programs")
            return recommendations
        
        make = vehicle_info.get('make', '').upper()
        year = vehicle_info.get('year')
        vehicle_age = vehicle_info.get('vehicle_age')
        
        # Age-based recommendations
        if vehicle_age and vehicle_age > 8:
            recommendations.append("Consider Gold or Platinum coverage for comprehensive protection")
            recommendations.append("Pre-existing condition inspection may be required")
        
        # Luxury vehicle recommendations
        if any(luxury in make for luxury in ['BMW', 'MERCEDES', 'AUDI', 'LEXUS', 'CADILLAC']):
            recommendations.append("Platinum coverage recommended for luxury vehicles")
            recommendations.append("Consider zero deductible option for premium experience")
        
        # High-reliability vehicle recommendations
        if any(reliable in make for reliable in ['HONDA', 'TOYOTA', 'MAZDA']):
            recommendations.append("Silver coverage may provide excellent value for reliable vehicles")
        
        # General recommendations
        if not recommendations:
            recommendations.append("Gold coverage offers the best balance of protection and value")
            recommendations.append("Consider extended term options for maximum savings")
        
        return recommendations
    
    def _get_available_coverage_options(self, vehicle_info: Dict, eligible: bool) -> Dict:
        """Get available coverage options based on vehicle characteristics"""
        if not eligible:
            return {'available_levels': [], 'message': 'Vehicle not eligible for VSC coverage'}
        
        make = vehicle_info.get('make', '').upper()
        vehicle_age = vehicle_info.get('vehicle_age', 0)
        
        # Base coverage options
        coverage_options = {
            'available_levels': ['silver', 'gold', 'platinum'],
            'recommended_level': 'gold',
            'available_terms': [12, 24, 36, 48, 60, 72],
            'recommended_term': 36,
            'available_deductibles': [0, 50, 100, 200, 500, 1000],
            'recommended_deductible': 100
        }
        
        # Adjust based on vehicle characteristics
        if vehicle_age > 10:
            coverage_options['available_terms'] = [12, 24, 36]  # Shorter terms for older vehicles
            coverage_options['recommended_term'] = 24
        
        if any(luxury in make for luxury in ['BMW', 'MERCEDES', 'AUDI']):
            coverage_options['recommended_level'] = 'platinum'
            coverage_options['recommended_deductible'] = 0
        
        return coverage_options
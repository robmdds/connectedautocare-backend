#!/usr/bin/env python3
"""
Enhanced VIN Decoder Service with Database Integration
Handles VIN validation, decoding, and VSC eligibility checking using database-driven rules
"""

import re
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# Try to import database functions
try:
    import sys
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    sys.path.insert(0, parent_dir)
    
    from data.vsc_rates_data import get_vehicle_class, rate_manager
    DATABASE_INTEGRATION = True
except ImportError:
    DATABASE_INTEGRATION = False

class EnhancedVINDecoderService:
    """Enhanced service for VIN validation, decoding, and eligibility checking with database integration"""
    
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
        
        # VSC Eligibility Rules (will be loaded from database if available)
        self.eligibility_rules = {
            'max_age_years': 20,        # Changed from 15 to 20
            'max_mileage': 200000,      # Changed from 150,000 to 200,000
            'warning_age_years': 15,    # Warning threshold
            'warning_mileage': 150000,  # Warning threshold
        }
        
        # Load database-driven rules if available
        if DATABASE_INTEGRATION:
            try:
                self._load_database_rules()
            except Exception as e:
                print(f"Warning: Could not load rules from database, using defaults: {e}")
        
        # Brand classifications
        self.luxury_brands = ['BMW', 'Mercedes-Benz', 'Audi', 'Lexus', 'Cadillac', 'Lincoln', 'Acura', 'Infiniti']
        self.high_maintenance_brands = ['Land Rover', 'Jaguar', 'Porsche', 'Maserati', 'Bentley', 'Rolls-Royce']
        self.excluded_vehicle_types = ['motorcycle', 'recreational_vehicle', 'commercial_truck']
    
    def _load_database_rules(self):
        """Load eligibility rules from database if available"""
        try:
            if DATABASE_INTEGRATION:
                # Load multiplier data to understand current rules
                age_multipliers = rate_manager.get_age_multipliers()
                mileage_multipliers = rate_manager.get_mileage_multipliers()
                
                # Update rules based on database data
                if age_multipliers:
                    max_age = max(config['max_age'] for config in age_multipliers)
                    if max_age < 999:  # Exclude the catch-all category
                        self.eligibility_rules['max_age_years'] = max_age
                
                if mileage_multipliers:
                    max_mileage = max(config['max_mileage'] for config in mileage_multipliers if config['max_mileage'] < 999999)
                    if max_mileage:
                        self.eligibility_rules['max_mileage'] = max_mileage
                        
        except Exception as e:
            print(f"Could not load database rules: {e}")
    
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
    
    def decode_vin(self, vin: str, model_year: Optional[int] = None) -> Dict:
        """Enhanced VIN decoding with database integration"""
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
            detailed_info = self._try_external_decode(vin, model_year)
            
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
            
            # Add vehicle class from database if available
            if DATABASE_INTEGRATION and vehicle_info.get('make'):
                try:
                    vehicle_class = get_vehicle_class(vehicle_info['make'])
                    vehicle_info['vehicle_class'] = vehicle_class
                except Exception as e:
                    print(f"Could not get vehicle class from database: {e}")
            
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
        Updated VSC eligibility check with database-driven rules
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
            
            # Check eligibility with database-driven rules
            eligible = True
            warnings = []
            restrictions = []
            
            # Age eligibility check
            if vehicle_age is not None:
                if vehicle_age > self.eligibility_rules['max_age_years']:
                    eligible = False
                    restrictions.append(
                        f"Vehicle is {vehicle_age} years old (must be {self.eligibility_rules['max_age_years']} model years or newer)"
                    )
                elif vehicle_age > self.eligibility_rules.get('warning_age_years', 15):
                    warnings.append(
                        f"Vehicle is {vehicle_age} years old - limited coverage options may apply"
                    )
            
            # Mileage eligibility check
            if mileage is not None:
                if mileage >= self.eligibility_rules['max_mileage']:
                    eligible = False
                    restrictions.append(
                        f"Vehicle has {mileage:,} miles (must be less than {self.eligibility_rules['max_mileage']:,} miles)"
                    )
                elif mileage > self.eligibility_rules.get('warning_mileage', 150000):
                    warnings.append(
                        f"High mileage vehicle ({mileage:,} miles) - premium rates may apply"
                    )
            
            # If not eligible, return the specific message
            if not eligible:
                return {
                    'success': True,
                    'eligible': False,
                    'message': "Vehicle doesn't qualify. Make sure you entered the correct current mileage. Vehicle must be 20 model years or newer and less than 200,000 miles at time of quote",
                    'vehicle_info': vehicle_info,
                    'eligibility_details': {
                        'vehicle_age': vehicle_age,
                        'mileage': mileage,
                        'make': make,
                        'year': year
                    },
                    'restrictions': restrictions,
                    'assessment_date': datetime.utcnow().isoformat() + 'Z'
                }
            
            # Calculate pricing factors for eligible vehicles
            pricing_factors = {}
            
            # Get database-driven pricing factors if available
            if DATABASE_INTEGRATION:
                try:
                    from data.vsc_rates_data import get_age_multiplier, get_mileage_multiplier
                    
                    if vehicle_age is not None:
                        pricing_factors['age_factor'] = get_age_multiplier(vehicle_age)
                    
                    if mileage is not None:
                        pricing_factors['mileage_factor'] = get_mileage_multiplier(mileage)
                    
                    if make:
                        pricing_factors['vehicle_class'] = get_vehicle_class(make)
                        
                except Exception as e:
                    print(f"Could not get database pricing factors: {e}")
                    # Fall back to manual calculation
                    pricing_factors = self._calculate_fallback_pricing_factors(vehicle_age, mileage, make)
            else:
                pricing_factors = self._calculate_fallback_pricing_factors(vehicle_age, mileage, make)
            
            # Generate recommendations
            recommendations = self._generate_recommendations_updated(vehicle_info, eligible, warnings)
            coverage_options = self._get_available_coverage_options_updated(vehicle_info, eligible)
            
            return {
                'success': True,
                'eligible': True,
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
                'rules_version': '2025.2_database_integrated'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Eligibility check error: {str(e)}'
            }
    
    def _calculate_fallback_pricing_factors(self, vehicle_age, mileage, make):
        """Calculate pricing factors when database is unavailable"""
        pricing_factors = {}
        
        # Age pricing factor
        if vehicle_age is not None:
            if vehicle_age <= 3:
                pricing_factors['age_factor'] = 1.0
            elif vehicle_age <= 6:
                pricing_factors['age_factor'] = 1.15
            elif vehicle_age <= 10:
                pricing_factors['age_factor'] = 1.35
            elif vehicle_age <= 15:
                pricing_factors['age_factor'] = 1.60
            else:
                pricing_factors['age_factor'] = 1.80
        
        # Mileage pricing factor
        if mileage is not None:
            if mileage <= 50000:
                pricing_factors['mileage_factor'] = 1.0
            elif mileage <= 75000:
                pricing_factors['mileage_factor'] = 1.15
            elif mileage <= 100000:
                pricing_factors['mileage_factor'] = 1.30
            elif mileage <= 150000:
                pricing_factors['mileage_factor'] = 1.50
            else:
                pricing_factors['mileage_factor'] = 1.75
        
        # Vehicle class determination for pricing
        pricing_factors['vehicle_class'] = self._determine_vehicle_class(make) if make else 'B'
        
        return pricing_factors
    
    def get_vin_info_with_eligibility(self, vin: str, mileage: int = None) -> Dict:
        """
        Get comprehensive VIN information including eligibility check with database integration
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
                'database_integration': DATABASE_INTEGRATION,
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
            
            # If decoded year is in the future, subtract 30 years
            if decoded_year > current_year + 1:
                decoded_year -= 30
            
            # Validate reasonable year range (1980-2030)
            if 1980 <= decoded_year <= current_year + 2:
                return decoded_year
        
        return None
    
    def _try_external_decode(self, vin: str, model_year: Optional[int] = None) -> Optional[Dict]:
        """
        Attempt to decode VIN using external APIs
        """
        try:
            # Try NHTSA VIN Decoder API (free but limited)
            nhtsa_result = self._try_nhtsa_decode(vin, model_year)
            if nhtsa_result and nhtsa_result.get('success'):
                return nhtsa_result
            
            return None
            
        except Exception as e:
            print(f"External VIN decode error: {e}")
            return None
    
    def _try_nhtsa_decode(self, vin: str, model_year: Optional[int] = None) -> Optional[Dict]:
        """
        Improved NHTSA API integration with comprehensive data extraction
        """
        try:
            print(f"🔍 Attempting NHTSA decode for VIN: {vin}")
            
            url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{vin}"
            params = {'format': 'json'}
            
            if model_year:
                params['modelyear'] = model_year
                print(f"📅 Using model year: {model_year}")
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code != 200:
                print(f"❌ NHTSA API HTTP error: {response.status_code}")
                return None
            
            try:
                data = response.json()
            except ValueError as e:
                print(f"❌ Invalid JSON from NHTSA: {e}")
                return None
            
            results = data.get('Results', [])
            if not results:
                print("❌ No results from NHTSA API")
                return None
            
            print(f"✅ NHTSA returned {len(results)} data points")
            
            # Enhanced field mapping for better data extraction
            field_mappings = {
                'Make': 'make',
                'Model': 'model',
                'Model Year': 'year',
                'Trim': 'trim',
                'Series': 'series',
                'Body Class': 'body_style',
                'Vehicle Type': 'vehicle_type',
                'Fuel Type - Primary': 'fuel_type',
                'Engine Number of Cylinders': 'engine_cylinders',
                'Engine Model': 'engine_model',
                'Engine Configuration': 'engine_configuration',
                'Displacement (L)': 'engine_displacement',
                'Displacement (CI)': 'engine_displacement_ci',
                'Transmission Style': 'transmission_style',
                'Transmission Speeds': 'transmission_speeds',
                'Drive Type': 'drive_type',
                'Number of Doors': 'doors',
                'Number of Seats': 'seats',
                'Plant Country': 'plant_country',
                'Plant Company Name': 'plant_company',
                'Plant City': 'plant_city',
                'Plant State': 'plant_state',
                'Manufacturer Name': 'manufacturer_name'
            }
            
            vehicle_info = {}
            
            # Extract all available information
            for result in results:
                variable = result.get('Variable', '')
                value = result.get('Value', '')
                
                # Skip empty or placeholder values
                if not value or value in ['Not Applicable', '', 'N/A', 'null']:
                    continue
                
                # Map known fields
                if variable in field_mappings:
                    field_name = field_mappings[variable]
                    cleaned_value = self._clean_nhtsa_value(value)
                    if cleaned_value is not None:
                        vehicle_info[field_name] = cleaned_value
            
            # Post-processing for data consistency
            vehicle_info = self._post_process_nhtsa_data(vehicle_info, vin)
            
            # If we didn't get essential info, try fallback extraction
            if not vehicle_info.get('make') or not vehicle_info.get('year'):
                print("⚠️ Missing essential data, trying fallback extraction")
                fallback_info = self._extract_essential_nhtsa_data(results, vin)
                vehicle_info.update(fallback_info)
            
            # Validate we have minimum required information
            if not vehicle_info.get('make'):
                print("❌ No manufacturer information found")
                return None
            
            # Add metadata
            vehicle_info.update({
                'vin': vin,
                'wmi': vin[:3],
                'vds': vin[3:9],
                'vis': vin[9:],
                'decode_method': 'nhtsa_api_enhanced',
                'decode_timestamp': datetime.utcnow().isoformat() + 'Z',
                'data_source': 'NHTSA vPIC Database',
                'api_fields_returned': len([r for r in results if r.get('Value') not in ['Not Applicable', '', 'N/A']])
            })
            
            print(f"✅ Successfully extracted {len(vehicle_info)} fields from NHTSA")
            return {
                'success': True,
                'vehicle_info': vehicle_info
            }
            
        except requests.exceptions.Timeout:
            print("❌ NHTSA API timeout")
            return None
        except requests.exceptions.ConnectionError:
            print("❌ Cannot connect to NHTSA API")
            return None
        except requests.exceptions.RequestException as e:
            print(f"❌ NHTSA API request error: {e}")
            return None
        except Exception as e:
            print(f"❌ Unexpected NHTSA decode error: {e}")
            return None
    
    def _clean_nhtsa_value(self, value: str) -> Optional[str]:
        """Clean and validate values from NHTSA API"""
        if not isinstance(value, str):
            return value
        
        value = value.strip()
        
        # Handle empty/placeholder values
        if value in ['Not Applicable', 'N/A', 'null', '', '0']:
            return None
        
        # Clean common formatting issues
        value = re.sub(r'\s+', ' ', value)  # Multiple spaces to single space
        
        # Handle numeric values
        if value.replace('.', '').replace('-', '').isdigit():
            try:
                return int(value) if '.' not in value else float(value)
            except ValueError:
                pass
        
        return value

    def _post_process_nhtsa_data(self, vehicle_info: Dict, vin: str) -> Dict:
        """Post-process NHTSA data for consistency"""
        
        # Ensure year is properly formatted
        if 'year' in vehicle_info:
            try:
                year_value = vehicle_info['year']
                if isinstance(year_value, str):
                    vehicle_info['year'] = int(year_value)
                elif isinstance(year_value, (int, float)):
                    vehicle_info['year'] = int(year_value)
            except (ValueError, TypeError):
                # If year conversion fails, try to decode from VIN
                decoded_year = self._decode_year(vin[9])
                if decoded_year:
                    vehicle_info['year'] = decoded_year
        
        # Standardize make names
        if 'make' in vehicle_info:
            make = vehicle_info['make'].strip().title()
            # Handle common variations
            make_mappings = {
                'Mercedes-Benz': 'Mercedes-Benz',
                'Mercedes Benz': 'Mercedes-Benz', 
                'Bmw': 'BMW',
                'Gmc': 'GMC'
            }
            vehicle_info['make'] = make_mappings.get(make, make)
        
        # Clean up model field
        if 'model' in vehicle_info and vehicle_info['model'].isdigit():
            # Sometimes NHTSA returns year as model
            potential_year = int(vehicle_info['model'])
            if 1980 <= potential_year <= 2030:
                if 'year' not in vehicle_info:
                    vehicle_info['year'] = potential_year
                vehicle_info['model'] = 'Model not specified'
        
        # Calculate vehicle age if year is available
        if 'year' in vehicle_info:
            current_year = datetime.now().year
            vehicle_info['vehicle_age'] = current_year - vehicle_info['year']
        
        return vehicle_info

    def _extract_essential_nhtsa_data(self, results: list, vin: str) -> Dict:
        """Extract essential data when standard mapping fails"""
        essential_info = {}
        
        # Look for make information in multiple fields
        make_fields = ['Make', 'Manufacturer Name', 'NCSA Make']
        for result in results:
            variable = result.get('Variable', '')
            value = result.get('Value', '')
            
            if variable in make_fields and value not in ['Not Applicable', '', 'N/A']:
                essential_info['make'] = value.strip().title()
                break
        
        # Look for model information
        model_fields = ['Model', 'NCSA Model', 'Series']
        for result in results:
            variable = result.get('Variable', '')
            value = result.get('Value', '')
            
            if variable in model_fields and value not in ['Not Applicable', '', 'N/A']:
                if not value.isdigit():  # Skip if it's just a year
                    essential_info['model'] = value.strip().title()
                    break
        
        # Look for year information
        year_fields = ['Model Year', 'Year']
        for result in results:
            variable = result.get('Variable', '')
            value = result.get('Value', '')
            
            if variable in year_fields and value not in ['Not Applicable', '', 'N/A']:
                try:
                    year = int(value)
                    if 1980 <= year <= 2030:
                        essential_info['year'] = year
                        break
                except (ValueError, TypeError):
                    continue
        
        # If still no year, decode from VIN
        if 'year' not in essential_info:
            decoded_year = self._decode_year(vin[9])
            if decoded_year:
                essential_info['year'] = decoded_year
        
        # If still no make, decode from WMI
        if 'make' not in essential_info:
            essential_info['make'] = self._decode_manufacturer(vin[:3])
        
        return essential_info
    
    def _determine_vehicle_class(self, make: str) -> str:
        """Determine vehicle class for pricing (A, B, C) - fallback method"""
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
    
    def _generate_recommendations_updated(self, vehicle_info: Dict, eligible: bool, warnings: List[str]) -> List[str]:
        """Generate recommendations based on vehicle characteristics with database integration"""
        recommendations = []
        
        if not eligible:
            recommendations.append("Please verify your vehicle's current mileage and model year")
            recommendations.append("Consider our Hero Products for alternative protection options")
            return recommendations
        
        make = vehicle_info.get('make', '').upper()
        year = vehicle_info.get('year')
        vehicle_age = vehicle_info.get('vehicle_age')
        
        # Age-based recommendations with updated thresholds
        if vehicle_age and vehicle_age > 15:
            recommendations.append("Platinum coverage recommended for older vehicles")
            recommendations.append("Consider shorter term options for maximum value")
        elif vehicle_age and vehicle_age > 10:
            recommendations.append("Gold or Platinum coverage recommended")
        
        # Luxury vehicle recommendations
        if any(luxury in make for luxury in self.luxury_brands):
            recommendations.append("Platinum coverage strongly recommended for luxury vehicles")
            recommendations.append("Consider zero deductible option")
        
        # High-reliability vehicle recommendations
        if any(reliable in make for reliable in ['HONDA', 'TOYOTA', 'MAZDA']):
            recommendations.append("All coverage levels available - Silver may provide excellent value")
        
        # General recommendations
        if not recommendations:
            recommendations.append("Gold coverage offers the best balance of protection and value")
            recommendations.append("All coverage levels (Silver, Gold, Platinum) available for your vehicle")
        
        return recommendations
    
    def _get_available_coverage_options_updated(self, vehicle_info: Dict, eligible: bool) -> Dict:
        """Get available coverage options based on vehicle characteristics with database integration"""
        if not eligible:
            return {
                'available_levels': [],
                'message': 'Vehicle not eligible for VSC coverage',
                'eligibility_requirements': {
                    'max_age': f'{self.eligibility_rules["max_age_years"]} model years or newer',
                    'max_mileage': f'Less than {self.eligibility_rules["max_mileage"]:,} miles'
                }
            }
        
        make = vehicle_info.get('make', '').upper()
        vehicle_age = vehicle_info.get('vehicle_age', 0)
        
        # Get coverage options from database if available
        if DATABASE_INTEGRATION:
            try:
                from data.vsc_rates_data import get_vsc_coverage_options
                db_options = get_vsc_coverage_options()
                
                coverage_options = {
                    'available_levels': list(db_options['coverage_levels'].keys()),
                    'recommended_level': 'gold',
                    'available_terms': db_options['term_options']['available_terms'],
                    'recommended_term': 36,
                    'available_deductibles': db_options['deductible_options']['available_deductibles'],
                    'recommended_deductible': 100
                }
            except Exception as e:
                print(f"Could not get coverage options from database: {e}")
                # Fall back to default options
                coverage_options = self._get_fallback_coverage_options()
        else:
            coverage_options = self._get_fallback_coverage_options()
        
        # Adjust recommendations based on vehicle characteristics
        if vehicle_age > 15:
            # Shorter terms for older vehicles
            available_terms = [t for t in coverage_options['available_terms'] if t <= 36]
            coverage_options['available_terms'] = available_terms if available_terms else [12, 24, 36]
            coverage_options['recommended_term'] = 24
            coverage_options['recommended_level'] = 'platinum'
        
        if any(luxury in make for luxury in self.luxury_brands):
            coverage_options['recommended_level'] = 'platinum'
            coverage_options['recommended_deductible'] = 0
        
        return coverage_options
    
    def _get_fallback_coverage_options(self):
        """Fallback coverage options when database is unavailable"""
        return {
            'available_levels': ['silver', 'gold', 'platinum'],
            'recommended_level': 'gold',
            'available_terms': [12, 24, 36, 48, 60],
            'recommended_term': 36,
            'available_deductibles': [0, 50, 100, 200, 500, 1000],
            'recommended_deductible': 100
        }
    
    def get_database_status(self) -> Dict:
        """Get status of database integration"""
        return {
            'database_integration_enabled': DATABASE_INTEGRATION,
            'eligibility_rules': self.eligibility_rules,
            'last_rules_update': datetime.utcnow().isoformat() + 'Z'
        }
    
    def refresh_database_rules(self):
        """Manually refresh rules from database"""
        if DATABASE_INTEGRATION:
            try:
                self._load_database_rules()
                return {
                    'success': True,
                    'message': 'Database rules refreshed successfully',
                    'updated_rules': self.eligibility_rules
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Failed to refresh database rules: {str(e)}'
                }
        else:
            return {
                'success': False,
                'error': 'Database integration not available'
            }
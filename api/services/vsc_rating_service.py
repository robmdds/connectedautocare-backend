#!/usr/bin/env python3
"""
VSC (Vehicle Service Contract) Rating Service
Handles quote generation for vehicle service contracts using database-driven rates
"""

import os
import sys
from datetime import datetime, timedelta

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from data.vsc_rates_data import (
        calculate_vsc_price, 
        get_vehicle_class, 
        get_base_rate,
        get_vsc_coverage_options,
        rate_manager
    )
    DATABASE_INTEGRATION = True
except ImportError:
    DATABASE_INTEGRATION = False
    # Fallback rate data
    VSC_RATES = {
        'A': {'silver': {'base_rate': 800}, 'gold': {'base_rate': 1200}, 'platinum': {'base_rate': 1600}},
        'B': {'silver': {'base_rate': 1000}, 'gold': {'base_rate': 1500}, 'platinum': {'base_rate': 2000}},
        'C': {'silver': {'base_rate': 1400}, 'gold': {'base_rate': 2100}, 'platinum': {'base_rate': 2800}}
    }
    VEHICLE_CLASSIFICATION = {
        'honda': 'A', 'toyota': 'A', 'nissan': 'A', 'hyundai': 'A',
        'ford': 'B', 'chevrolet': 'B', 'dodge': 'B', 'gmc': 'B',
        'bmw': 'C', 'mercedes': 'C', 'audi': 'C', 'cadillac': 'C'
    }

class VSCRatingService:
    """Service for generating VSC quotes using database-driven rates"""
    
    def __init__(self):
        self.tax_rate = 0.07  # 7% tax rate
        self.admin_fee = 50.00  # VSC administrative fee
        
        self.eligibility_rules = {
            'max_age_years': 20,        # Vehicle must be 20 model years or newer
            'max_mileage': 200000,      # Vehicle must have less than 200,000 miles
        }
        
        # Load data from database if available
        if DATABASE_INTEGRATION:
            self.database_mode = True
            try:
                # Test database connectivity
                coverage_options = get_vsc_coverage_options()
                self.available_terms = coverage_options['term_options']['available_terms']
                self.available_deductibles = coverage_options['deductible_options']['available_deductibles']
                self.coverage_levels = list(coverage_options['coverage_levels'].keys())
            except Exception as e:
                print(f"Warning: Database connection failed, using fallback mode: {e}")
                self.database_mode = False
                self._init_fallback_data()
        else:
            self.database_mode = False
            self._init_fallback_data()
    
    def _init_fallback_data(self):
        """Initialize fallback data when database is unavailable"""
        self.rates = VSC_RATES
        self.vehicle_classes = VEHICLE_CLASSIFICATION
        self.available_terms = [12, 24, 36, 48, 60, 72]
        self.available_deductibles = [0, 50, 100, 200, 500, 1000]
        self.coverage_levels = ['silver', 'gold', 'platinum']
        
    def generate_quote(self, make, year, mileage, model='', coverage_level='gold', 
                      term_months=36, deductible=100, customer_type='retail', **kwargs):
        """
        Generate VSC quote with database-driven pricing
        """
        try:
            # Normalize inputs
            make = make.lower().strip()
            year = int(year)
            mileage = int(mileage)
            coverage_level = coverage_level.lower().strip()
            term_months = int(term_months)
            
            # Check eligibility FIRST
            eligibility_check = self._check_eligibility(make, year, mileage)
            if not eligibility_check['eligible']:
                return {
                    'success': False,
                    'eligible': False,
                    'message': eligibility_check['message'],
                    'vehicle_info': {
                        'make': make.title(),
                        'model': model.title() if model else 'Not Specified',
                        'year': year,
                        'mileage': mileage,
                        'age_years': datetime.now().year - year
                    },
                    'eligibility_details': eligibility_check['details']
                }
            
            # Validate inputs
            validation_errors = self._validate_inputs(make, year, mileage, coverage_level, term_months)
            if validation_errors:
                return {
                    'success': False,
                    'error': '; '.join(validation_errors)
                }
            
            if self.database_mode:
                # Use database-driven pricing
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
                    return {
                        'success': False,
                        'error': f"Price calculation failed: {price_result.get('error', 'Unknown error')}"
                    }
                
                vehicle_class = price_result['vehicle_class']
                adjusted_price = price_result['calculated_price']
                pricing_method = price_result.get('pricing_method', 'calculated')
                
                # Get rating factors from database result
                multipliers = price_result.get('multipliers', {})
                
            else:
                # Fallback to legacy pricing
                vehicle_class = self._get_vehicle_class_fallback(make)
                base_rate = self.rates[vehicle_class][coverage_level]['base_rate']
                
                # Apply adjustments
                age_factor = self._calculate_age_factor(year)
                mileage_factor = self._calculate_mileage_factor(mileage)
                term_factor = self._calculate_term_factor(term_months)
                deductible_factor = self._calculate_deductible_factor(deductible)
                
                # Calculate adjusted price
                adjusted_price = base_rate * age_factor * mileage_factor * term_factor * deductible_factor
                
                # Apply customer discount
                if customer_type == 'wholesale':
                    adjusted_price *= 0.85  # 15% wholesale discount
                
                multipliers = {
                    'age': age_factor,
                    'mileage': mileage_factor,
                    'term': term_factor,
                    'deductible': deductible_factor,
                    'customer_discount': 0.85 if customer_type == 'wholesale' else 1.0
                }
                pricing_method = 'fallback_calculated'
            
            # Add administrative fee and calculate totals
            subtotal = adjusted_price + self.admin_fee
            tax_amount = subtotal * self.tax_rate
            total_price = subtotal + tax_amount
            monthly_payment = total_price / term_months if term_months > 0 else total_price
            
            # Generate quote ID
            quote_id = f"VSC-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            
            return {
                'success': True,
                'eligible': True,
                'quote_id': quote_id,
                'pricing_method': pricing_method,
                'database_mode': self.database_mode,
                'vehicle_info': {
                    'make': make.title(),
                    'model': model.title() if model else 'Not Specified',
                    'year': year,
                    'mileage': mileage,
                    'vehicle_class': vehicle_class,
                    'age_years': datetime.now().year - year
                },
                'coverage_details': {
                    'level': coverage_level.title(),
                    'term_months': term_months,
                    'term_years': round(term_months / 12, 1),
                    'deductible': deductible,
                    'customer_type': customer_type
                },
                'pricing_breakdown': {
                    'base_calculation': round(adjusted_price, 2),
                    'admin_fee': round(self.admin_fee, 2),
                    'subtotal': round(subtotal, 2),
                    'tax_amount': round(tax_amount, 2),
                    'total_price': round(total_price, 2),
                    'monthly_payment': round(monthly_payment, 2)
                },
                'rating_factors': multipliers,
                'payment_options': {
                    'full_payment': round(total_price, 2),
                    'monthly_payment': round(monthly_payment, 2),
                    'financing_available': True,
                    'financing_terms': ['12 months 0% APR', '24 months 0% APR']
                },
                'quote_details': {
                    'timestamp': datetime.utcnow().isoformat() + 'Z',
                    'valid_until': self._calculate_expiry_date(),
                    'tax_rate': self.tax_rate,
                    'currency': 'USD'
                }
            }
            
        except ValueError as e:
            return {
                'success': False,
                'error': f'Invalid input data: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Quote generation failed: {str(e)}'
            }
    
    def _get_vehicle_class_fallback(self, make):
        """Fallback vehicle class determination when database unavailable"""
        make_lower = make.lower()
        
        # Check for exact match first
        if make_lower in self.vehicle_classes:
            return self.vehicle_classes[make_lower]
        
        # Check for partial matches
        for vehicle_make, vehicle_class in self.vehicle_classes.items():
            if vehicle_make in make_lower or make_lower in vehicle_make:
                return vehicle_class
        
        # Default to Class B if not found
        return 'B'
    
    def _calculate_age_factor(self, year):
        """Fallback age factor calculation"""
        current_year = datetime.now().year
        age = current_year - year
        
        if age <= 3:
            return 1.0
        elif age <= 6:
            return 1.15
        elif age <= 10:
            return 1.35
        elif age <= 15:
            return 1.60
        elif age <= 20:
            return 1.85
        else:
            return 2.0
    
    def _calculate_mileage_factor(self, mileage):
        """Fallback mileage factor calculation"""
        if mileage <= 50000:
            return 1.0
        elif mileage <= 75000:
            return 1.15
        elif mileage <= 100000:
            return 1.30
        elif mileage <= 150000:
            return 1.50
        elif mileage < 200000:
            return 1.80
        else:
            return 2.0
    
    def _calculate_term_factor(self, term_months):
        """Fallback term factor calculation"""
        term_factors = {
            12: 0.40, 24: 0.70, 36: 1.00, 48: 1.25, 60: 1.45, 72: 1.60
        }
        return term_factors.get(term_months, 1.0)
    
    def _calculate_deductible_factor(self, deductible):
        """Fallback deductible factor calculation"""
        deductible_factors = {
            0: 1.25, 50: 1.15, 100: 1.00, 200: 0.90, 500: 0.75, 1000: 0.65
        }
        return deductible_factors.get(deductible, 1.0)
    
    def _validate_inputs(self, make, year, mileage, coverage_level, term_months):
        """Input validation with database-aware options"""
        errors = []
        current_year = datetime.now().year
        
        if not make or len(make.strip()) < 2:
            errors.append("Vehicle make is required")
        
        # Year validation
        min_year = current_year - 20
        if year < min_year or year > current_year + 1:
            errors.append(f"Vehicle year must be between {min_year} and {current_year + 1}")
        
        # Mileage validation
        if mileage < 0 or mileage >= 200000:
            errors.append("Mileage must be between 0 and 199,999")
        
        # Coverage level validation
        if coverage_level not in self.coverage_levels:
            errors.append(f"Coverage level must be one of: {', '.join(self.coverage_levels)}")
        
        # Term validation
        if term_months not in self.available_terms:
            errors.append(f"Term must be one of: {self.available_terms}")
        
        return errors
    
    def _calculate_expiry_date(self):
        """Calculate quote expiry date (30 days from now)"""
        expiry = datetime.utcnow() + timedelta(days=30)
        return expiry.isoformat() + 'Z'
    
    def get_coverage_options(self):
        """Get available coverage options from database or fallback"""
        if self.database_mode:
            try:
                return get_vsc_coverage_options()
            except Exception as e:
                print(f"Error getting coverage options from database: {e}")
                # Fall through to fallback
        
        # Fallback options
        return {
            'coverage_levels': self.coverage_levels,
            'term_options': self.available_terms,
            'deductible_options': self.available_deductibles,
            'vehicle_classes': ['A', 'B', 'C']
        }
    
    def get_vehicle_class_info(self, make):
        """Get vehicle class information for a specific make"""
        if self.database_mode:
            try:
                vehicle_class = get_vehicle_class(make)
                base_rates = {}
                for coverage_level in self.coverage_levels:
                    base_rates[coverage_level] = get_base_rate(vehicle_class, coverage_level)
                
                return {
                    'make': make.title(),
                    'class': vehicle_class,
                    'base_rates': base_rates,
                    'data_source': 'database'
                }
            except Exception as e:
                print(f"Error getting vehicle class info from database: {e}")
                # Fall through to fallback
        
        # Fallback
        vehicle_class = self._get_vehicle_class_fallback(make)
        return {
            'make': make.title(),
            'class': vehicle_class,
            'base_rates': self.rates[vehicle_class] if hasattr(self, 'rates') else {},
            'data_source': 'fallback'
        }
        
    def generate_quote_from_vin(self, vin, mileage, coverage_level='gold', 
                               term_months=36, deductible=100, customer_type='retail', **kwargs):
        """
        Generate VSC quote directly from VIN with database integration
        """
        try:
            # Import here to avoid circular imports
            from services.enhanced_vin_decoder_service import EnhancedVINDecoderService
            
            # Decode VIN first
            vin_decoder = EnhancedVINDecoderService()
            vin_result = vin_decoder.decode_vin(vin.strip().upper())
            
            if not vin_result.get('success'):
                return {
                    'success': False,
                    'error': f'VIN decode failed: {vin_result.get("error", "Unknown error")}'
                }
            
            vehicle_info = vin_result['vehicle_info']
            make = vehicle_info.get('make', '')
            model = vehicle_info.get('model', '')
            year = vehicle_info.get('year')
            
            if not make or not year:
                return {
                    'success': False,
                    'error': 'Insufficient vehicle information from VIN decode - missing make or year'
                }
            
            # Check eligibility BEFORE generating quote
            eligibility_check = self._check_eligibility(make, year, mileage)
            if not eligibility_check['eligible']:
                return {
                    'success': False,
                    'eligible': False,
                    'message': eligibility_check['message'],
                    'vin_info': {
                        'vin': vin.strip().upper(),
                        'decode_method': vehicle_info.get('decode_method', 'enhanced'),
                        'auto_populated': True
                    },
                    'vehicle_info': {
                        'make': make,
                        'model': model,
                        'year': year,
                        'mileage': mileage,
                        'age_years': datetime.now().year - year
                    },
                    'eligibility_details': eligibility_check['details']
                }
            
            # Generate quote for eligible vehicle
            quote_result = self.generate_quote(
                make=make,
                model=model,
                year=year,
                mileage=mileage,
                coverage_level=coverage_level,
                term_months=term_months,
                deductible=deductible,
                customer_type=customer_type,
                **kwargs
            )
            
            if quote_result.get('success'):
                # Enhance quote with VIN information
                quote_result['vin_info'] = {
                    'vin': vin.strip().upper(),
                    'decode_method': vehicle_info.get('decode_method', 'enhanced'),
                    'data_source': vehicle_info.get('data_source', 'NHTSA vPIC Database'),
                    'auto_populated': True,
                    'decoded_fields': len(vehicle_info)
                }
                
                # Add additional vehicle details if available
                additional_info = {}
                for field in ['body_style', 'engine_cylinders', 'fuel_type', 'transmission_style']:
                    if field in vehicle_info:
                        additional_info[field] = vehicle_info[field]
                
                if additional_info:
                    quote_result['additional_vehicle_info'] = additional_info
            
            return quote_result
            
        except Exception as e:
            return {
                'success': False,
                'error': f'VIN-based quote generation failed: {str(e)}'
            }
    
    def _check_eligibility(self, make, year, mileage):
        """
        Check VSC eligibility with updated requirements
        """
        current_year = datetime.now().year
        vehicle_age = current_year - year
        
        eligible = True
        details = {
            'vehicle_age': vehicle_age,
            'mileage': mileage,
            'max_age_allowed': self.eligibility_rules['max_age_years'],
            'max_mileage_allowed': self.eligibility_rules['max_mileage']
        }
        
        # Check age requirement: must be 20 model years or newer
        if vehicle_age > self.eligibility_rules['max_age_years']:
            eligible = False
        
        # Check mileage requirement: must be less than 200,000 miles
        if mileage >= self.eligibility_rules['max_mileage']:
            eligible = False
        
        # Return specific message for ineligible vehicles
        if not eligible:
            return {
                'eligible': False,
                'message': "Vehicle doesn't qualify. Make sure you entered the correct current mileage. Vehicle must be 20 model years or newer and less than 200,000 miles at time of quote",
                'details': details
            }
        
        return {
            'eligible': True,
            'message': 'Vehicle qualifies for VSC coverage',
            'details': details
        }
    
    def get_pricing_summary(self, make, year, mileage, coverage_level='gold', term_months=36):
        """
        Get pricing summary for comparison purposes
        """
        try:
            if self.database_mode:
                price_result = calculate_vsc_price(
                    make=make, year=year, mileage=mileage,
                    coverage_level=coverage_level, term_months=term_months
                )
                
                if price_result.get('success'):
                    base_price = price_result['calculated_price']
                    return {
                        'success': True,
                        'base_price': base_price,
                        'pricing_method': price_result.get('pricing_method'),
                        'vehicle_class': price_result['vehicle_class'],
                        'multipliers': price_result.get('multipliers', {})
                    }
            
            # Fallback pricing summary
            vehicle_class = self._get_vehicle_class_fallback(make)
            if hasattr(self, 'rates'):
                base_rate = self.rates[vehicle_class][coverage_level]['base_rate']
                return {
                    'success': True,
                    'base_price': base_rate,
                    'pricing_method': 'fallback',
                    'vehicle_class': vehicle_class
                }
            
            return {'success': False, 'error': 'Pricing data not available'}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
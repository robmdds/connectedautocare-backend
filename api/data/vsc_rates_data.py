#!/usr/bin/env python3
"""
VSC (Vehicle Service Contract) Rates Data - FIXED VERSION
Database-driven rate cards and vehicle classification for VSC pricing
Fixed database connection management issues
"""

import psycopg2
import os
import logging
from datetime import datetime
from typing import Dict, Optional, List, Tuple
from functools import lru_cache
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL", "postgres://neondb_owner:npg_qH6nhmdrSFL1@ep-tiny-water-adje4r08-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require")

# Fallback vehicle classification (kept for backup/offline use)
FALLBACK_VEHICLE_CLASSIFICATION = {
    # Class A - Most Reliable (Lowest Rates)
    'honda': 'A', 'acura': 'A', 'toyota': 'A', 'lexus': 'A', 'nissan': 'A',
    'infiniti': 'A', 'hyundai': 'A', 'kia': 'A', 'mazda': 'A', 'mitsubishi': 'A',
    'scion': 'A', 'subaru': 'A',
    
    # Class B - Moderate Risk (Medium Rates)
    'buick': 'B', 'chevrolet': 'B', 'chrysler': 'B', 'dodge': 'B', 'ford': 'B',
    'gmc': 'B', 'jeep': 'B', 'mercury': 'B', 'oldsmobile': 'B', 'plymouth': 'B',
    'pontiac': 'B', 'saturn': 'B', 'ram': 'B',
    
    # Class C - Higher Risk (Highest Rates)
    'cadillac': 'C', 'lincoln': 'C', 'volkswagen': 'C', 'volvo': 'C', 'bmw': 'C',
    'mercedes-benz': 'C', 'mercedes': 'C', 'audi': 'C', 'jaguar': 'C',
    'land rover': 'C', 'porsche': 'C', 'saab': 'C', 'mini': 'C'
}

class VSCRateManager:
    """Database-driven VSC rate management with proper connection handling"""
    
    def __init__(self, database_url=DATABASE_URL):
        self.database_url = database_url
        self._connection_lock = threading.Lock()
        
        # Remove caching from instance - we'll implement it differently
        self._cached_data = {}
        self._cache_timestamps = {}
        self._cache_ttl = 300  # 5 minutes cache TTL
        
    def _get_fresh_connection(self):
        """Get a fresh database connection for each operation"""
        try:
            connection = psycopg2.connect(self.database_url)
            return connection
        except psycopg2.Error as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached data is still valid"""
        if key not in self._cached_data:
            return False
        
        cache_time = self._cache_timestamps.get(key, 0)
        return (datetime.now().timestamp() - cache_time) < self._cache_ttl
    
    def _set_cache(self, key: str, data):
        """Set cached data with timestamp"""
        self._cached_data[key] = data
        self._cache_timestamps[key] = datetime.now().timestamp()
    
    def _get_cache(self, key: str):
        """Get cached data if valid"""
        if self._is_cache_valid(key):
            return self._cached_data[key]
        return None
    
    def get_vehicle_classification(self) -> Dict[str, str]:
        """
        Get vehicle classification from database with caching
        
        Returns:
            dict: Make to class mapping
        """
        cache_key = 'vehicle_classification'
        cached_result = self._get_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            # Use fresh connection for each operation
            with self._get_fresh_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT make, vehicle_class, active 
                        FROM vsc_vehicle_classes 
                        WHERE active = TRUE
                        ORDER BY make;
                    """)
                    
                    classification = {}
                    for make, vehicle_class, active in cursor.fetchall():
                        classification[make.lower().strip()] = vehicle_class
                    
                    result = classification if classification else FALLBACK_VEHICLE_CLASSIFICATION
                    self._set_cache(cache_key, result)
                    return result
                    
        except psycopg2.Error as e:
            logger.warning(f"Failed to load vehicle classification from database: {e}")
            return FALLBACK_VEHICLE_CLASSIFICATION
    
    def get_coverage_levels(self) -> Dict[str, Dict]:
        """
        Get coverage levels from database with caching
        
        Returns:
            dict: Coverage level information
        """
        cache_key = 'coverage_levels'
        cached_result = self._get_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            with self._get_fresh_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT level_code, level_name, description, active 
                        FROM vsc_coverage_levels 
                        WHERE active = TRUE
                        ORDER BY display_order;
                    """)
                    
                    coverage_levels = {}
                    for level_code, level_name, description, active in cursor.fetchall():
                        coverage_levels[level_code] = {
                            'name': level_name,
                            'description': description
                        }
                    
                    result = coverage_levels if coverage_levels else {
                        'silver': {'name': 'Silver Coverage', 'description': 'Basic powertrain protection'},
                        'gold': {'name': 'Gold Coverage', 'description': 'Enhanced component protection'},
                        'platinum': {'name': 'Platinum Coverage', 'description': 'Comprehensive exclusionary coverage'}
                    }
                    
                    self._set_cache(cache_key, result)
                    return result
                    
        except psycopg2.Error as e:
            logger.warning(f"Failed to load coverage levels from database: {e}")
            return {
                'silver': {'name': 'Silver Coverage', 'description': 'Basic powertrain protection'},
                'gold': {'name': 'Gold Coverage', 'description': 'Enhanced component protection'},
                'platinum': {'name': 'Platinum Coverage', 'description': 'Comprehensive exclusionary coverage'}
            }
    
    def get_term_multipliers(self) -> Dict[int, float]:
        """
        Get term multipliers from database with caching
        
        Returns:
            dict: Term to multiplier mapping
        """
        cache_key = 'term_multipliers'
        cached_result = self._get_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            with self._get_fresh_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT term_months, multiplier 
                        FROM vsc_term_multipliers 
                        WHERE active = TRUE
                        ORDER BY term_months;
                    """)
                    
                    multipliers = {}
                    for term_months, multiplier in cursor.fetchall():
                        multipliers[term_months] = float(multiplier)
                    
                    result = multipliers if multipliers else {
                        12: 0.40, 24: 0.70, 36: 1.00, 48: 1.25, 60: 1.45, 72: 1.60
                    }
                    
                    self._set_cache(cache_key, result)
                    return result
                    
        except psycopg2.Error as e:
            logger.warning(f"Failed to load term multipliers from database: {e}")
            return {12: 0.40, 24: 0.70, 36: 1.00, 48: 1.25, 60: 1.45, 72: 1.60}
    
    def get_deductible_multipliers(self) -> Dict[int, float]:
        """
        Get deductible multipliers from database with caching
        
        Returns:
            dict: Deductible to multiplier mapping
        """
        cache_key = 'deductible_multipliers'
        cached_result = self._get_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            with self._get_fresh_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT deductible_amount, multiplier 
                        FROM vsc_deductible_multipliers 
                        WHERE active = TRUE
                        ORDER BY deductible_amount;
                    """)
                    
                    multipliers = {}
                    for deductible_amount, multiplier in cursor.fetchall():
                        multipliers[deductible_amount] = float(multiplier)
                    
                    result = multipliers if multipliers else {
                        0: 1.25, 50: 1.15, 100: 1.00, 200: 0.90, 500: 0.75, 1000: 0.65
                    }
                    
                    self._set_cache(cache_key, result)
                    return result
                    
        except psycopg2.Error as e:
            logger.warning(f"Failed to load deductible multipliers from database: {e}")
            return {0: 1.25, 50: 1.15, 100: 1.00, 200: 0.90, 500: 0.75, 1000: 0.65}
    
    def get_mileage_multipliers(self) -> List[Dict]:
        """
        Get mileage multipliers from database with caching
        
        Returns:
            list: Mileage multiplier configurations
        """
        cache_key = 'mileage_multipliers'
        cached_result = self._get_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            with self._get_fresh_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT category, min_mileage, max_mileage, multiplier, description
                        FROM vsc_mileage_multipliers 
                        WHERE active = TRUE
                        ORDER BY display_order;
                    """)
                    
                    multipliers = []
                    for category, min_mileage, max_mileage, multiplier, description in cursor.fetchall():
                        multipliers.append({
                            'category': category,
                            'min_mileage': min_mileage,
                            'max_mileage': max_mileage,
                            'multiplier': float(multiplier),
                            'description': description
                        })
                    
                    result = multipliers if multipliers else [
                        {'category': 'low', 'min_mileage': 0, 'max_mileage': 50000, 'multiplier': 1.00, 'description': '0-50k miles'},
                        {'category': 'medium', 'min_mileage': 50001, 'max_mileage': 75000, 'multiplier': 1.15, 'description': '50k-75k miles'},
                        {'category': 'high', 'min_mileage': 75001, 'max_mileage': 100000, 'multiplier': 1.30, 'description': '75k-100k miles'},
                        {'category': 'very_high', 'min_mileage': 100001, 'max_mileage': 125000, 'multiplier': 1.50, 'description': '100k-125k miles'},
                        {'category': 'extreme', 'min_mileage': 125001, 'max_mileage': 999999, 'multiplier': 1.75, 'description': '125k+ miles'}
                    ]
                    
                    self._set_cache(cache_key, result)
                    return result
                    
        except psycopg2.Error as e:
            logger.warning(f"Failed to load mileage multipliers from database: {e}")
            return [
                {'category': 'low', 'min_mileage': 0, 'max_mileage': 50000, 'multiplier': 1.00, 'description': '0-50k miles'},
                {'category': 'medium', 'min_mileage': 50001, 'max_mileage': 75000, 'multiplier': 1.15, 'description': '50k-75k miles'},
                {'category': 'high', 'min_mileage': 75001, 'max_mileage': 100000, 'multiplier': 1.30, 'description': '75k-100k miles'},
                {'category': 'very_high', 'min_mileage': 100001, 'max_mileage': 125000, 'multiplier': 1.50, 'description': '100k-125k miles'},
                {'category': 'extreme', 'min_mileage': 125001, 'max_mileage': 999999, 'multiplier': 1.75, 'description': '125k+ miles'}
            ]
    
    def get_age_multipliers(self) -> List[Dict]:
        """
        Get age multipliers from database with caching
        
        Returns:
            list: Age multiplier configurations
        """
        cache_key = 'age_multipliers'
        cached_result = self._get_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            with self._get_fresh_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT category, min_age, max_age, multiplier, description
                        FROM vsc_age_multipliers 
                        WHERE active = TRUE
                        ORDER BY display_order;
                    """)
                    
                    multipliers = []
                    for category, min_age, max_age, multiplier, description in cursor.fetchall():
                        multipliers.append({
                            'category': category,
                            'min_age': min_age,
                            'max_age': max_age,
                            'multiplier': float(multiplier),
                            'description': description
                        })
                    
                    result = multipliers if multipliers else [
                        {'category': 'new', 'min_age': 0, 'max_age': 3, 'multiplier': 1.00, 'description': '0-3 years'},
                        {'category': 'recent', 'min_age': 4, 'max_age': 6, 'multiplier': 1.15, 'description': '4-6 years'},
                        {'category': 'older', 'min_age': 7, 'max_age': 10, 'multiplier': 1.35, 'description': '7-10 years'},
                        {'category': 'old', 'min_age': 11, 'max_age': 999, 'multiplier': 1.60, 'description': '11+ years'}
                    ]
                    
                    self._set_cache(cache_key, result)
                    return result
                    
        except psycopg2.Error as e:
            logger.warning(f"Failed to load age multipliers from database: {e}")
            return [
                {'category': 'new', 'min_age': 0, 'max_age': 3, 'multiplier': 1.00, 'description': '0-3 years'},
                {'category': 'recent', 'min_age': 4, 'max_age': 6, 'multiplier': 1.15, 'description': '4-6 years'},
                {'category': 'older', 'min_age': 7, 'max_age': 10, 'multiplier': 1.35, 'description': '7-10 years'},
                {'category': 'old', 'min_age': 11, 'max_age': 999, 'multiplier': 1.60, 'description': '11+ years'}
            ]
    
    def get_exact_rate(self, vehicle_class: str, coverage_level: str, term_months: int, mileage: int) -> Optional[float]:
        """
        Get exact rate from the rate matrix table (PDF data)
        
        Args:
            vehicle_class: Vehicle class (A, B, C)
            coverage_level: Coverage level (silver, gold, platinum)
            term_months: Contract term in months
            mileage: Vehicle mileage
            
        Returns:
            float: Exact rate if found, None otherwise
        """
        try:
            with self._get_fresh_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT rate_amount 
                        FROM vsc_rate_matrix 
                        WHERE vehicle_class = %s 
                        AND coverage_level = %s 
                        AND term_months = %s 
                        AND min_mileage <= %s 
                        AND max_mileage >= %s
                        AND active = TRUE
                        ORDER BY effective_date DESC
                        LIMIT 1;
                    """, (vehicle_class, coverage_level, term_months, mileage, mileage))
                    
                    result = cursor.fetchone()
                    return float(result[0]) if result else None
                    
        except psycopg2.Error as e:
            logger.warning(f"Failed to get exact rate from database: {e}")
            return None
    
    def get_base_rate(self, vehicle_class: str, coverage_level: str) -> float:
        """
        Get base rate for vehicle class and coverage level
        
        Args:
            vehicle_class: Vehicle class (A, B, or C)
            coverage_level: Coverage level (silver, gold, platinum)
            
        Returns:
            float: Base rate
        """
        try:
            with self._get_fresh_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT base_rate 
                        FROM vsc_base_rates 
                        WHERE vehicle_class = %s 
                        AND coverage_level = %s 
                        AND active = TRUE
                        ORDER BY effective_date DESC
                        LIMIT 1;
                    """, (vehicle_class, coverage_level))
                    
                    result = cursor.fetchone()
                    if result:
                        return float(result[0])
                    
                    # Fallback to estimated base rates
                    fallback_rates = {
                        'A': {'silver': 1500, 'gold': 1580, 'platinum': 1650},
                        'B': {'silver': 1650, 'gold': 1750, 'platinum': 1900},
                        'C': {'silver': 1850, 'gold': 2000, 'platinum': 2600}
                    }
                    return fallback_rates.get(vehicle_class, {}).get(coverage_level, 1500)
                    
        except psycopg2.Error as e:
            logger.warning(f"Failed to get base rate from database: {e}")
            # Fallback rates
            fallback_rates = {
                'A': {'silver': 1500, 'gold': 1580, 'platinum': 1650},
                'B': {'silver': 1650, 'gold': 1750, 'platinum': 1900},
                'C': {'silver': 1850, 'gold': 2000, 'platinum': 2600}
            }
            return fallback_rates.get(vehicle_class, {}).get(coverage_level, 1500)

# Global rate manager instance
rate_manager = VSCRateManager()

def get_vehicle_class(make: str) -> str:
    """
    Get vehicle class for a given make
    
    Args:
        make: Vehicle make
        
    Returns:
        str: Vehicle class (A, B, or C)
    """
    make_lower = make.lower().strip()
    classification = rate_manager.get_vehicle_classification()
    
    # Direct lookup
    if make_lower in classification:
        return classification[make_lower]
    
    # Partial match for compound names
    for vehicle_make, vehicle_class in classification.items():
        if vehicle_make in make_lower or make_lower in vehicle_make:
            return vehicle_class
    
    # Default to Class B if not found
    return 'B'

def get_base_rate(vehicle_class: str, coverage_level: str) -> float:
    """
    Get base rate for vehicle class and coverage level
    
    Args:
        vehicle_class: Vehicle class (A, B, or C)
        coverage_level: Coverage level (silver, gold, platinum)
        
    Returns:
        float: Base rate
    """
    return rate_manager.get_base_rate(vehicle_class, coverage_level)

def get_mileage_multiplier(mileage: int) -> float:
    """
    Get mileage multiplier based on vehicle mileage
    
    Args:
        mileage: Vehicle mileage
        
    Returns:
        float: Mileage multiplier
    """
    mileage_multipliers = rate_manager.get_mileage_multipliers()
    
    for config in mileage_multipliers:
        if config['min_mileage'] <= mileage <= config['max_mileage']:
            return config['multiplier']
    
    # Fallback to highest multiplier
    return 1.75

def get_age_multiplier(vehicle_age: int) -> float:
    """
    Get age multiplier based on vehicle age
    
    Args:
        vehicle_age: Vehicle age in years
        
    Returns:
        float: Age multiplier
    """
    age_multipliers = rate_manager.get_age_multipliers()
    
    for config in age_multipliers:
        if config['min_age'] <= vehicle_age <= config['max_age']:
            return config['multiplier']
    
    # Fallback to highest multiplier
    return 1.60


def get_vsc_coverage_options() -> Dict:
    """
    Get all available VSC coverage options including mileage allowance options
    
    Returns:
        dict: Complete coverage options including mileage allowance tiers
    """
    coverage_levels = rate_manager.get_coverage_levels()
    term_multipliers = rate_manager.get_term_multipliers()
    deductible_multipliers = rate_manager.get_deductible_multipliers()
    classification = rate_manager.get_vehicle_classification()
    
    # Define standard mileage allowance options
    mileage_allowance_options = [
        {'miles': 8000, 'label': '8,000 Miles', 'annual_equivalent': '8,000/year', 'tier': 'Very Low'},
        {'miles': 10000, 'label': '10,000 Miles', 'annual_equivalent': '10,000/year', 'tier': 'Low'},
        {'miles': 12000, 'label': '12,000 Miles', 'annual_equivalent': '12,000/year', 'tier': 'Standard'},
        {'miles': 15000, 'label': '15,000 Miles', 'annual_equivalent': '15,000/year', 'tier': 'Above Average'},
        {'miles': 18000, 'label': '18,000 Miles', 'annual_equivalent': '18,000/year', 'tier': 'High Usage'},
        {'miles': 21000, 'label': '21,000 Miles', 'annual_equivalent': '21,000/year', 'tier': 'Very High'},
        {'miles': 24000, 'label': '24,000 Miles', 'annual_equivalent': '24,000/year', 'tier': 'Premium'},
        {'miles': 30000, 'label': '30,000 Miles', 'annual_equivalent': '30,000/year', 'tier': 'Maximum'},
        {'miles': None, 'label': 'Unlimited Miles', 'annual_equivalent': 'unlimited', 'tier': 'Unlimited'}
    ]
    
    # Add multipliers to each option (using 36 months as base calculation)
    for option in mileage_allowance_options:
        option['multiplier'] = get_mileage_allowance_multiplier(option['miles'], 36)
        option['pricing_impact'] = f'{((option["multiplier"] - 1.0) * 100):+.0f}% vs base'
    
    return {
        'coverage_levels': coverage_levels,
        'term_options': {
            'available_terms': list(term_multipliers.keys()),
            'multipliers': term_multipliers
        },
        'deductible_options': {
            'available_deductibles': list(deductible_multipliers.keys()),
            'multipliers': deductible_multipliers
        },
        'mileage_allowance_options': {
            'description': 'Miles allowed during contract period',
            'options': mileage_allowance_options,
            'notes': [
                'Mileage allowance affects pricing - higher allowances cost more',
                'Annual equivalents shown are for 36-month contracts',
                'Unlimited option includes 40% premium but no restrictions',
                'Choose based on expected driving during contract period'
            ]
        },
        'vehicle_classes': {
            vehicle_class: {
                'description': f'Class {vehicle_class} vehicles',
                'example_makes': [
                    make.title() for make, cls in classification.items() 
                    if cls == vehicle_class
                ][:5]  # Show first 5 examples
            }
            for vehicle_class in ['A', 'B', 'C']
        },
        'eligibility_requirements': {
            'max_vehicle_age': 20,
            'max_current_mileage': 199999,
            'message': 'Vehicle must be 20 model years or newer with less than 200,000 current miles'
        }
    }

def calculate_vsc_price(make: str, year: int, mileage: int, coverage_level: str = 'gold', 
                       term_months: int = 36, mileage_allowance=None, deductible: int = 100, customer_type: str = 'retail') -> Dict:
    """
    Calculate VSC price based on all factors with exact rate lookup and mileage allowance support
    
    Args:
        make: Vehicle make
        year: Vehicle year
        mileage: Vehicle mileage
        coverage_level: Coverage level
        term_months: Contract term in months
        mileage_allowance: Integer for contract mileage allowance, or None for unlimited
        deductible: Deductible amount
        customer_type: Customer type (retail/wholesale)
        
    Returns:
        dict: Price calculation breakdown
    """
    try:
        current_year = datetime.now().year
        
        # Input validation
        if not make or not isinstance(make, str):
            return {'success': False, 'error': 'Valid vehicle make is required'}
            
        if not year or year < (current_year - 30) or year > (current_year + 1):
            return {'success': False, 'error': f'Vehicle year must be between {current_year - 30} and {current_year + 1}'}
            
        if not isinstance(mileage, int) or mileage < 0 or mileage >= 200000:
            return {'success': False, 'error': 'Current mileage must be between 0 and 199,999'}
            
        if coverage_level not in ['silver', 'gold', 'platinum']:
            return {'success': False, 'error': 'Coverage level must be silver, gold, or platinum'}
            
        if term_months not in [12, 24, 36, 48, 60, 72]:
            return {'success': False, 'error': 'Term must be 12, 24, 36, 48, 60, or 72 months'}
            
        if customer_type not in ['retail', 'wholesale']:
            return {'success': False, 'error': 'Customer type must be retail or wholesale'}
        
        # Validate mileage allowance
        if mileage_allowance is not None:
            if not isinstance(mileage_allowance, int) or mileage_allowance < 0:
                return {'success': False, 'error': 'Mileage allowance must be a positive integer or None for unlimited'}
                
        # Check vehicle eligibility
        vehicle_age = current_year - year
        if vehicle_age > 20:
            return {
                'success': False,
                'eligible': False,
                'error': f'Vehicle is {vehicle_age} years old (must be 20 model years or newer)'
            }
            
        if mileage >= 200000:
            return {
                'success': False,
                'eligible': False,
                'error': f'Vehicle has {mileage:,} miles (must be less than 200,000 miles)'
            }
        
        # Get vehicle class
        vehicle_class = get_vehicle_class(make)
        
        # Try to get exact rate from PDF data first
        exact_rate = rate_manager.get_exact_rate(vehicle_class, coverage_level, term_months, mileage)
        
        if exact_rate:
            # Use exact rate from PDF
            calculated_price = exact_rate
            
            # Apply deductible multiplier
            deductible_multipliers = rate_manager.get_deductible_multipliers()
            deductible_multiplier = deductible_multipliers.get(deductible, 1.0)
            calculated_price *= deductible_multiplier
            
            # NEW: Apply mileage allowance multiplier
            allowance_multiplier = get_mileage_allowance_multiplier(mileage_allowance, term_months)
            calculated_price *= allowance_multiplier
            
            # Apply customer discount
            customer_discount = 0.85 if customer_type == 'wholesale' else 1.0
            calculated_price *= customer_discount
            
            return {
                'success': True,
                'eligible': True,
                'pricing_method': 'exact_pdf_rate_with_mileage_allowance',
                'vehicle_class': vehicle_class,
                'exact_rate': exact_rate,
                'calculated_price': round(calculated_price, 2),
                'vehicle_info': {
                    'make': make.title(),
                    'year': year,
                    'mileage': mileage,
                    'vehicle_class': vehicle_class,
                    'age_years': vehicle_age
                },
                'multipliers': {
                    'deductible': deductible_multiplier,
                    'mileage_allowance': allowance_multiplier,  # NEW
                    'customer_discount': customer_discount
                }
            }
        
        else:
            # Fallback to calculated method with all multipliers
            # Get base rate
            base_rate = get_base_rate(vehicle_class, coverage_level)
            
            # Calculate all multipliers
            age_multiplier = get_age_multiplier(vehicle_age)
            mileage_multiplier = get_mileage_multiplier(mileage)
            
            term_multipliers = rate_manager.get_term_multipliers()
            term_multiplier = term_multipliers.get(term_months, 1.0)
            
            deductible_multipliers = rate_manager.get_deductible_multipliers()
            deductible_multiplier = deductible_multipliers.get(deductible, 1.0)
            
            # NEW: Mileage allowance multiplier
            allowance_multiplier = get_mileage_allowance_multiplier(mileage_allowance, term_months)
            
            # Calculate price with all multipliers
            calculated_price = (base_rate * age_multiplier * mileage_multiplier * 
                              term_multiplier * deductible_multiplier * allowance_multiplier)
            
            # Apply customer discount
            customer_discount = 0.85 if customer_type == 'wholesale' else 1.0
            calculated_price *= customer_discount
            
            return {
                'success': True,
                'eligible': True,
                'pricing_method': 'calculated_with_mileage_allowance',
                'vehicle_class': vehicle_class,
                'base_rate': base_rate,
                'calculated_price': round(calculated_price, 2),
                'vehicle_info': {
                    'make': make.title(),
                    'year': year,
                    'mileage': mileage,
                    'vehicle_class': vehicle_class,
                    'age_years': vehicle_age
                },
                'multipliers': {
                    'age': age_multiplier,
                    'mileage': mileage_multiplier,
                    'term': term_multiplier,
                    'deductible': deductible_multiplier,
                    'mileage_allowance': allowance_multiplier,  # NEW
                    'customer_discount': customer_discount
                }
            }
            
    except Exception as e:
        logger.error(f"Error calculating VSC price: {e}")
        return {
            'success': False,
            'error': str(e)
        }

# Add these new functions to your vsc_rates_data.py file

def get_term_multiplier(term_months: int) -> float:
    """
    Get term multiplier for a specific term
    
    Args:
        term_months: Contract term in months
        
    Returns:
        float: Term multiplier
    """
    term_multipliers = rate_manager.get_term_multipliers()
    return term_multipliers.get(term_months, 1.0)

def get_deductible_multiplier(deductible: int) -> float:
    """
    Get deductible multiplier for a specific deductible amount
    
    Args:
        deductible: Deductible amount
        
    Returns:
        float: Deductible multiplier
    """
    deductible_multipliers = rate_manager.get_deductible_multipliers()
    return deductible_multipliers.get(deductible, 1.0)

def get_mileage_allowance_multiplier(mileage_allowance, term_months: int) -> float:
    """
    Calculate pricing multiplier based on mileage allowance
    
    Args:
        mileage_allowance: Integer miles allowed during contract, or None for unlimited
        term_months: Contract term in months
        
    Returns:
        float: Pricing multiplier (0.80 for low usage to 1.65 for extreme usage, 1.4 for unlimited)
    """
    try:
        # Handle unlimited mileage case
        if mileage_allowance is None or mileage_allowance == 'unlimited':  
            return 1.4  # 40% premium for unlimited mileage
        
        # Validate inputs
        if not isinstance(mileage_allowance, int) or mileage_allowance < 0:
            return 1.0  # Default multiplier for invalid input
            
        if not isinstance(term_months, int) or term_months <= 0:
            return 1.0  # Default multiplier for invalid term
        
        # Calculate annual average allowance
        annual_average = mileage_allowance / (term_months / 12)
        
        # Define mileage tiers and multipliers based on industry standards
        mileage_tiers = [
            (8000, 0.80),    # Very low mileage (under 8k/year) - maximum discount
            (10000, 0.85),   # Low mileage (8k-10k/year) - good discount
            (12000, 1.00),   # Base rate (10k-12k/year) - standard usage
            (15000, 1.10),   # Moderate increase (12k-15k/year) - above average
            (18000, 1.20),   # Higher usage (15k-18k/year) - increased risk
            (21000, 1.30),   # High usage (18k-21k/year) - higher risk
            (24000, 1.35),   # Very high usage (21k-24k/year) - significant risk
            (27000, 1.45),   # Extreme usage (24k-27k/year) - major risk
            (30000, 1.50),   # Maximum standard (27k-30k/year) - highest standard risk
            (float('inf'), 1.65)  # Extreme cases (30k+/year) - maximum multiplier
        ]
        
        # Find appropriate multiplier
        for threshold, multiplier in mileage_tiers:
            if annual_average <= threshold:
                return multiplier
        
        # Fallback (should never reach here due to infinity threshold)
        return 1.65
        
    except Exception as e:
        logger.warning(f"Error calculating mileage allowance multiplier: {e}")
        return 1.0  # Safe default multiplier

def get_mileage_allowance_recommendations(vehicle_age: int, current_mileage: int, term_months: int, vehicle_class: str = 'B') -> Dict:
    """
    Generate recommended mileage allowances based on vehicle characteristics
    
    Args:
        vehicle_age: Age of vehicle in years
        current_mileage: Current odometer reading
        term_months: Contract term in months
        vehicle_class: A, B, or C classification
        
    Returns:
        Dict with recommendations and analysis
    """
    try:
        # Calculate historical annual mileage
        if vehicle_age > 0:
            historical_annual = current_mileage / vehicle_age
        else:
            historical_annual = 12000  # Default assumption for new vehicles
        
        # Adjust for vehicle class behavior patterns
        class_adjustments = {
            'A': 0.9,   # Reliable brands typically driven more conservatively
            'B': 1.0,   # Average driving patterns
            'C': 1.1    # Luxury vehicles often driven more
        }
        
        adjusted_annual = historical_annual * class_adjustments.get(vehicle_class, 1.0)
        
        # Calculate base recommendation for contract term
        base_contract_allowance = int(adjusted_annual * (term_months / 12))
        
        # Generate tiered recommendations
        recommendations = [
            {
                'tier': 'Conservative',
                'allowance': max(int(base_contract_allowance * 0.75), 8000),
                'annual_equivalent': max(int(adjusted_annual * 0.75), 8000),
                'multiplier': get_mileage_allowance_multiplier(max(int(base_contract_allowance * 0.75), 8000), term_months),
                'description': 'Lower than historical usage - best for reduced driving',
                'recommended_for': 'Retirement, work-from-home, urban driving'
            },
            {
                'tier': 'Standard',
                'allowance': max(base_contract_allowance, 12000),
                'annual_equivalent': max(int(adjusted_annual), 12000),
                'multiplier': get_mileage_allowance_multiplier(max(base_contract_allowance, 12000), term_months),
                'description': 'Based on your historical driving pattern',
                'recommended_for': 'Maintaining current driving habits'
            },
            {
                'tier': 'High Usage',
                'allowance': int(base_contract_allowance * 1.25),
                'annual_equivalent': int(adjusted_annual * 1.25),
                'multiplier': get_mileage_allowance_multiplier(int(base_contract_allowance * 1.25), term_months),
                'description': 'Above historical usage - good for lifestyle changes',
                'recommended_for': 'New job, moving, increased travel'
            },
            {
                'tier': 'Premium',
                'allowance': int(base_contract_allowance * 1.5),
                'annual_equivalent': int(adjusted_annual * 1.5),
                'multiplier': get_mileage_allowance_multiplier(int(base_contract_allowance * 1.5), term_months),
                'description': 'Maximum flexibility for heavy drivers',
                'recommended_for': 'Sales, delivery, frequent long trips'
            },
            {
                'tier': 'Unlimited',
                'allowance': None,
                'annual_equivalent': 'unlimited',
                'multiplier': get_mileage_allowance_multiplier(None, term_months),
                'description': 'No mileage restrictions whatsoever',
                'recommended_for': 'Commercial use, extreme driving needs'
            }
        ]
        
        return {
            'success': True,
            'analysis': {
                'historical_annual_miles': int(historical_annual),
                'vehicle_class': vehicle_class,
                'vehicle_age': vehicle_age,
                'current_mileage': current_mileage,
                'class_adjustment_factor': class_adjustments.get(vehicle_class, 1.0),
                'adjusted_annual_estimate': int(adjusted_annual)
            },
            'recommendations': recommendations,
            'notes': [
                'Recommendations based on historical driving patterns',
                'Vehicle class affects typical usage expectations',
                'Choose higher tiers for major lifestyle changes',
                'Unlimited option includes 40% premium but no restrictions'
            ]
        }
        
    except Exception as e:
        logger.error(f"Failed to generate mileage allowance recommendations: {e}")
        return {
            'success': False,
            'error': f'Failed to generate recommendations: {str(e)}'
        }

def validate_mileage_allowance_input(mileage_allowance, term_months: int) -> Dict:
    """
    Validate mileage allowance input and provide feedback
    
    Args:
        mileage_allowance: User input for mileage allowance
        term_months: Contract term in months
        
    Returns:
        Dict with validation results and suggestions
    """
    try:
        if mileage_allowance is None or mileage_allowance == 'unlimited':
            return {
                'valid': True,
                'normalized_value': None,
                'annual_equivalent': 'unlimited',
                'multiplier': get_mileage_allowance_multiplier(None, term_months),
                'warnings': ['Unlimited mileage includes 40% premium pricing']
            }
        
        # Try to convert to integer
        try:
            allowance_int = int(mileage_allowance)
        except (ValueError, TypeError):
            return {
                'valid': False,
                'error': 'Mileage allowance must be a number or "unlimited"'
            }
        
        # Validate range
        if allowance_int < 0:
            return {
                'valid': False,
                'error': 'Mileage allowance cannot be negative'
            }
        
        if allowance_int > 200000:  # Reasonable upper limit
            return {
                'valid': False,
                'error': 'Mileage allowance cannot exceed 200,000 miles'
            }
        
        # Calculate annual equivalent
        annual_equivalent = int(allowance_int / (term_months / 12)) if term_months > 0 else 0
        multiplier = get_mileage_allowance_multiplier(allowance_int, term_months)
        
        # Generate warnings for unusual values
        warnings = []
        if annual_equivalent > 50000:
            warnings.append(f'Very high annual mileage ({annual_equivalent:,}/year) - consider unlimited option')
        elif annual_equivalent < 5000:
            warnings.append(f'Very low annual mileage ({annual_equivalent:,}/year) - ensure this meets your needs')
        elif annual_equivalent > 30000:
            warnings.append(f'High annual mileage ({annual_equivalent:,}/year) - significant premium applies')
        
        return {
            'valid': True,
            'normalized_value': allowance_int,
            'annual_equivalent': annual_equivalent,
            'multiplier': multiplier,
            'warnings': warnings,
            'pricing_impact': f'{((multiplier - 1.0) * 100):+.0f}% vs base rate'
        }
        
    except Exception as e:
        logger.error(f"Mileage allowance validation error: {e}")
        return {
            'valid': False,
            'error': f'Validation error: {str(e)}'
        }
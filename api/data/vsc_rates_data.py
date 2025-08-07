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
    Get all available VSC coverage options
    
    Returns:
        dict: Complete coverage options
    """
    coverage_levels = rate_manager.get_coverage_levels()
    term_multipliers = rate_manager.get_term_multipliers()
    deductible_multipliers = rate_manager.get_deductible_multipliers()
    classification = rate_manager.get_vehicle_classification()
    
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
        'vehicle_classes': {
            vehicle_class: {
                'description': f'Class {vehicle_class} vehicles',
                'example_makes': [
                    make for make, cls in classification.items() 
                    if cls == vehicle_class
                ][:5]  # Show first 5 examples
            }
            for vehicle_class in ['A', 'B', 'C']
        }
    }

def calculate_vsc_price(make: str, year: int, mileage: int, coverage_level: str = 'gold', 
                       term_months: int = 36, deductible: int = 100, customer_type: str = 'retail') -> Dict:
    """
    Calculate VSC price based on all factors with exact rate lookup
    
    Args:
        make: Vehicle make
        year: Vehicle year
        mileage: Vehicle mileage
        coverage_level: Coverage level
        term_months: Contract term in months
        deductible: Deductible amount
        customer_type: Customer type (retail/wholesale)
        
    Returns:
        dict: Price calculation breakdown
    """
    try:
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
            
            # Apply customer discount
            customer_discount = 0.85 if customer_type == 'wholesale' else 1.0
            calculated_price *= customer_discount
            
            return {
                'success': True,
                'pricing_method': 'exact_pdf_rate',
                'vehicle_class': vehicle_class,
                'exact_rate': exact_rate,
                'calculated_price': round(calculated_price, 2),
                'multipliers': {
                    'deductible': deductible_multiplier,
                    'customer_discount': customer_discount
                }
            }
        
        else:
            # Fallback to calculated method
            vehicle_age = datetime.now().year - year
            
            # Get base rate
            base_rate = get_base_rate(vehicle_class, coverage_level)
            
            # Calculate multipliers
            age_multiplier = get_age_multiplier(vehicle_age)
            mileage_multiplier = get_mileage_multiplier(mileage)
            
            term_multipliers = rate_manager.get_term_multipliers()
            term_multiplier = term_multipliers.get(term_months, 1.0)
            
            deductible_multipliers = rate_manager.get_deductible_multipliers()
            deductible_multiplier = deductible_multipliers.get(deductible, 1.0)
            
            # Calculate price
            calculated_price = (base_rate * age_multiplier * mileage_multiplier * 
                              term_multiplier * deductible_multiplier)
            
            # Apply customer discount
            customer_discount = 0.85 if customer_type == 'wholesale' else 1.0
            calculated_price *= customer_discount
            
            return {
                'success': True,
                'pricing_method': 'calculated',
                'vehicle_class': vehicle_class,
                'base_rate': base_rate,
                'calculated_price': round(calculated_price, 2),
                'multipliers': {
                    'age': age_multiplier,
                    'mileage': mileage_multiplier,
                    'term': term_multiplier,
                    'deductible': deductible_multiplier,
                    'customer_discount': customer_discount
                }
            }
            
    except Exception as e:
        logger.error(f"Error calculating VSC price: {e}")
        return {
            'success': False,
            'error': str(e)
        }
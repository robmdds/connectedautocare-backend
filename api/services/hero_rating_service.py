#!/usr/bin/env python3
"""
Database-Driven Hero Products Rating Service
Updated to use dynamic settings from database
"""

import os
import sys
from datetime import datetime, timedelta, timezone

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from services.database_settings_service import (
        settings_service, get_admin_fee, get_wholesale_discount, 
        get_tax_rate, get_processing_fee
    )
except ImportError as e:
    print(f"Warning: Failed to import database_settings_service: {e}")
    class DummySettingsService:
        def is_database_available(self): return False
        def clear_cache(self): pass
    settings_service = DummySettingsService()
    def get_admin_fee(product_type: str = 'default') -> float: return 25.00
    def get_wholesale_discount() -> float: return 0.15
    def get_tax_rate(state: str = 'FL') -> float: return 0.07
    def get_processing_fee() -> float: return 15.00

try:
    from data.hero_products_data import HERO_PRODUCTS_PRICING
except ImportError:
    HERO_PRODUCTS_PRICING = {
        'home_protection': {'base_price': 199, 'multipliers': {1: 1.0, 2: 1.8, 3: 2.5, 4: 3.2, 5: 3.8}},
        'auto_protection': {'base_price': 299, 'multipliers': {1: 1.0, 2: 1.9, 3: 2.7, 4: 3.4, 5: 4.0}},
        'deductible_reimbursement': {'base_price': 150, 'multipliers': {1: 1.0, 2: 1.7, 3: 2.3}}
    }

class HeroRatingService:
    def __init__(self):
        self.pricing_data = HERO_PRODUCTS_PRICING
        self.database_settings_available = settings_service.connection_available
        print("Initializing HeroRatingService with database settings available:", self.database_settings_available)
        self._load_dynamic_settings()
    
    def _load_dynamic_settings(self):
        if self.database_settings_available:
            try:
                self.admin_fee = get_admin_fee('hero')
                self.wholesale_discount_rate = get_wholesale_discount()
                self.processing_fee = get_processing_fee()
                self.default_tax_rate = get_tax_rate(None)
                print(f"✅ Loaded database settings - Admin fee: ${self.admin_fee}, Wholesale discount: {self.wholesale_discount_rate*100}%")
            except Exception as e:
                print(f"⚠️ Error loading database settings, using defaults: {e}")
                self._load_fallback_settings()
        else:
            self._load_fallback_settings()
    
    def _load_fallback_settings(self):
        self.admin_fee = 25.00
        self.wholesale_discount_rate = 0.15
        self.processing_fee = 15.00
        self.default_tax_rate = 0.00
        print("⚠️ Using fallback settings - database not available")
    
    def refresh_settings(self):
        self.database_settings_available = settings_service.connection_available
        if self.database_settings_available:
            settings_service.clear_cache()
            self._load_dynamic_settings()
            return True
        return False
    
    def generate_quote(self, product_type, term_years, coverage_limit=500, 
                      customer_type='retail', state='FL', zip_code='33101', **kwargs):
        try:
            term_years = int(term_years)
            coverage_limit = int(coverage_limit)
        except (ValueError, TypeError) as e:
            return {
                'success': False,
                'error': f'Invalid data types: term_years and coverage_limit must be numeric. Error: {str(e)}'
            }
        
        if product_type not in self.pricing_data:
            return {
                'success': False,
                'error': f'Unknown product type: {product_type}. Available types: {list(self.pricing_data.keys())}'
            }
        
        product_config = self.pricing_data[product_type]
        available_terms = list(product_config['multipliers'].keys())
        if term_years not in available_terms:
            return {
                'success': False,
                'error': f'Invalid term: {term_years}. Available terms: {available_terms}'
            }
        
        base_price = product_config['base_price']
        term_multiplier = product_config['multipliers'][term_years]
        coverage_multiplier = 1.2 if coverage_limit == 1000 else 1.0
        state_multiplier = self._get_state_multiplier(state)
        
        subtotal = base_price * term_multiplier * coverage_multiplier * state_multiplier
        wholesale_multiplier = 1.0
        if customer_type == 'wholesale':
            wholesale_multiplier = 1 - self.wholesale_discount_rate
            subtotal *= wholesale_multiplier
        
        subtotal_with_fee = subtotal + self.admin_fee
        tax_rate = get_tax_rate(state) if self.database_settings_available else self.default_tax_rate
        tax_amount = subtotal_with_fee * tax_rate
        total_price = subtotal_with_fee + tax_amount
        monthly_payment = total_price / (term_years * 12)
        
        quote_id = f"HERO-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        return {
            'success': True,
            'quote_id': quote_id,
            'database_driven': self.database_settings_available,
            'product_info': {
                'type': product_type,
                'term_years': term_years,
                'coverage_limit': coverage_limit,
                'customer_type': customer_type
            },
            'pricing': {
                'base_price': round(base_price, 2),
                'subtotal_before_fees': round(subtotal, 2),
                'admin_fee': round(self.admin_fee, 2),
                'subtotal_with_fee': round(subtotal_with_fee, 2),
                'tax_amount': round(tax_amount, 2),
                'total_price': round(total_price, 2),
                'monthly_payment': round(monthly_payment, 2)
            },
            'multipliers_applied': {
                'term': term_multiplier,
                'coverage': coverage_multiplier,
                'state': state_multiplier,
                'customer_discount': wholesale_multiplier
            },
            'fees_and_discounts': {
                'admin_fee_source': 'database' if self.database_settings_available else 'default',
                'wholesale_discount_rate': self.wholesale_discount_rate,
                'discount_source': 'database' if self.database_settings_available else 'default'
            },
            'location': {
                'state': state,
                'zip_code': zip_code,
                'tax_rate': tax_rate,
                'tax_source': 'database' if self.database_settings_available else 'default'
            },
            'payment_options': {
                'full_payment': round(total_price, 2),
                'monthly_payment': round(monthly_payment, 2),
                'financing_available': True
            },
            'quote_timestamp': datetime.utcnow().isoformat() + 'Z',
            'valid_until': self._calculate_expiry_date()
        }
    
    def _get_state_multiplier(self, state):
        if self.database_settings_available:
            try:
                multiplier = settings_service.get_admin_setting('pricing', f'{state.lower()}_multiplier')
                if multiplier is not None:
                    return float(multiplier)
            except Exception as e:
                print(f"Could not get state multiplier from database: {e}")
        
        state_multipliers = {
            'FL': 1.0, 'CA': 1.15, 'NY': 1.20, 'TX': 1.05, 'IL': 1.10
        }
        return state_multipliers.get(state.upper(), 1.0)
    
    def _calculate_expiry_date(self):
        expiry = datetime.now(timezone.utc) + timedelta(days=30)
        return expiry.isoformat() + 'Z'
    
    def get_available_products(self):
        return list(self.pricing_data.keys())
    
    def get_product_terms(self, product_type):
        if product_type in self.pricing_data:
            return list(self.pricing_data[product_type]['multipliers'].keys())
        return []
    
    def validate_quote_data(self, data):
        required_fields = ['product_type', 'term_years']
        errors = []
        
        for field in required_fields:
            if field not in data:
                errors.append(f'Missing required field: {field}')
        
        if 'product_type' in data and data['product_type'] not in self.pricing_data:
            errors.append(f'Invalid product type: {data["product_type"]}')
        
        if 'term_years' in data:
            try:
                term = int(data['term_years'])
                if 'product_type' in data and data['product_type'] in self.pricing_data:
                    available_terms = list(self.pricing_data[data['product_type']]['multipliers'].keys())
                    if term not in available_terms:
                        errors.append(f'Invalid term for {data["product_type"]}: {term}')
            except (ValueError, TypeError):
                errors.append('term_years must be a valid integer')
        
        return errors
    
    def get_current_settings(self):
        return {
            'admin_fee': self.admin_fee,
            'wholesale_discount_rate': self.wholesale_discount_rate,
            'processing_fee': self.processing_fee,
            'default_tax_rate': self.default_tax_rate,
            'database_settings_available': self.database_settings_available
        }
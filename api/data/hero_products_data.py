#!/usr/bin/env python3
"""
Hero Products Data - July 2025 with Database Integration
Smart fallback from database to hardcoded pricing
"""

import os

# Updated Hero Products Pricing Configuration (July 2025) - FALLBACK DATA
HERO_PRODUCTS_PRICING = {
    'home_protection': {
        'base_price': 199,
        'multipliers': {
            1: 1.0,    # 1 year: $199
            2: 1.51,   # 2 years: $300
            3: 2.01,   # 3 years: $400
            4: 2.51,   # 4 years: $500
            5: 3.01    # 5 years: $599
        }
    },
    'comprehensive_auto_protection': {
        'base_price': 339,
        'multipliers': {
            1: 1.0,    # 1 year: $339
            2: 1.77,   # 2 years: $600
            3: 2.36,   # 3 years: $800
            4: 2.95,   # 4 years: $1000
            5: 3.24    # 5 years: $1099
        }
    },
    'home_deductible_reimbursement': {
        'base_price': 160,
        'multipliers': {
            1: 1.0,    # 1 year: $160
            2: 1.34,   # 2 years: $215
            3: 1.59    # 3 years: $255
        }
    },
    'multi_vehicle_deductible_reimbursement': {
        'base_price': 150,
        'multipliers': {
            1: 1.0,    # 1 year: $150
            2: 1.50,   # 2 years: $225
            3: 1.83    # 3 years: $275
        }
    },
    'auto_advantage_deductible_reimbursement': {
        'base_price': 120,
        'multipliers': {
            1: 1.0,    # 1 year: $120
            2: 1.50,   # 2 years: $180
            3: 1.88    # 3 years: $225
        }
    },
    'all_vehicle_deductible_reimbursement': {
        'base_price': 150,
        'multipliers': {
            1: 1.0,    # 1 year: $150
            2: 1.50,   # 2 years: $225
            3: 1.83    # 3 years: $275
        }
    },
    'auto_rv_deductible_reimbursement': {
        'base_price': 175,
        'multipliers': {
            1: 1.0,    # 1 year: $175
            2: 1.43,   # 2 years: $250
            3: 1.60    # 3 years: $280
        }
    },
    'hero_level_protection_home': {
        'base_price': 789,
        'multipliers': {
            1: 1.0,    # 1 year: $789
            2: 1.39,   # 2 years: $1100
            3: 1.64    # 3 years: $1295
        }
    }
}

# Contact information updated per requirements
CONTACT_INFO = {
    'phone': '1-(866) 660-7003',  # Updated from 1-800-AUTOCARE
    'email': 'support@connectedautocare.com',
    'support_hours': '24/7',
    'updated': 'July 2025'
}


def get_price_from_db_or_fallback(product_code, term_years, customer_type='retail'):
    """
    Smart pricing: Try database first, fallback to hardcoded pricing
    This is the main function to use for all pricing calculations
    """
    try:
        # Try database first
        database_url = os.environ.get('DATABASE_URL')
        if database_url:
            import psycopg2

            conn = psycopg2.connect(database_url)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT p.base_price, pr.multiplier 
                FROM products p 
                JOIN pricing pr ON p.product_code = pr.product_code 
                WHERE p.product_code = %s AND pr.term_years = %s AND pr.customer_type = %s
            ''', (product_code, term_years, customer_type))

            result = cursor.fetchone()
            cursor.close()
            conn.close()

            if result:
                base_price, multiplier = result
                final_price = float(base_price) * float(multiplier)
                return {
                    'success': True,
                    'base_price': float(base_price),
                    'multiplier': float(multiplier),
                    'final_price': round(final_price, 2),
                    'data_source': 'database',
                    'customer_type': customer_type,
                    'term_years': term_years
                }
    except Exception as e:
        print(f"Database error (falling back to hardcoded): {e}")

    # Fallback to hardcoded pricing
    return get_hardcoded_price(product_code, term_years, customer_type)


def get_hardcoded_price(product_code, term_years, customer_type='retail'):
    """Get pricing from hardcoded data (fallback)"""
    # Map product codes to pricing keys
    code_mapping = {
        'HOME_PROTECTION_PLAN': 'home_protection',
        'COMPREHENSIVE_AUTO_PROTECTION': 'comprehensive_auto_protection',
        'HOME_DEDUCTIBLE_REIMBURSEMENT': 'home_deductible_reimbursement',
        'AUTO_ADVANTAGE_DEDUCTIBLE_REIMBURSEMENT': 'auto_advantage_deductible_reimbursement',
        'MULTI_VEHICLE_DEDUCTIBLE_REIMBURSEMENT': 'multi_vehicle_deductible_reimbursement',
        'ALL_VEHICLE_DEDUCTIBLE_REIMBURSEMENT': 'all_vehicle_deductible_reimbursement',
        'AUTO_RV_DEDUCTIBLE_REIMBURSEMENT': 'auto_rv_deductible_reimbursement',
        'HERO_LEVEL_HOME_PROTECTION': 'hero_level_protection_home'
    }

    pricing_key = code_mapping.get(product_code)
    if not pricing_key or pricing_key not in HERO_PRODUCTS_PRICING:
        return {'success': False, 'error': 'Product not found'}

    config = HERO_PRODUCTS_PRICING[pricing_key]
    if term_years not in config['multipliers']:
        return {'success': False, 'error': 'Invalid term'}

    base_price = config['base_price']
    multiplier = config['multipliers'][term_years]

    if customer_type == 'wholesale':
        multiplier *= 0.85  # 15% wholesale discount

    final_price = base_price * multiplier

    return {
        'success': True,
        'base_price': base_price,
        'multiplier': multiplier,
        'final_price': round(final_price, 2),
        'data_source': 'hardcoded',
        'customer_type': customer_type,
        'term_years': term_years
    }


def calculate_hero_price(product_type, term_years, coverage_limit=500, customer_type='retail'):
    """
    Updated main pricing function - uses database-first approach
    This maintains backward compatibility with existing API calls
    """
    try:
        # Convert product_type to product_code format
        type_to_code_mapping = {
            'home_protection': 'HOME_PROTECTION_PLAN',
            'comprehensive_auto_protection': 'COMPREHENSIVE_AUTO_PROTECTION',
            'home_deductible_reimbursement': 'HOME_DEDUCTIBLE_REIMBURSEMENT',
            'auto_advantage_deductible_reimbursement': 'AUTO_ADVANTAGE_DEDUCTIBLE_REIMBURSEMENT',
            'multi_vehicle_deductible_reimbursement': 'MULTI_VEHICLE_DEDUCTIBLE_REIMBURSEMENT',
            'all_vehicle_deductible_reimbursement': 'ALL_VEHICLE_DEDUCTIBLE_REIMBURSEMENT',
            'auto_rv_deductible_reimbursement': 'AUTO_RV_DEDUCTIBLE_REIMBURSEMENT',
            'hero_level_protection_home': 'HERO_LEVEL_HOME_PROTECTION'
        }

        product_code = type_to_code_mapping.get(product_type)
        if not product_code:
            return {'success': False, 'error': f'Unknown product type: {product_type}'}

        # Get base pricing
        pricing_result = get_price_from_db_or_fallback(
            product_code, term_years, customer_type)

        if not pricing_result['success']:
            return pricing_result

        # Apply coverage limit multiplier
        coverage_multiplier = 1.2 if coverage_limit == 1000 else 1.0
        final_price = pricing_result['final_price'] * coverage_multiplier

        return {
            'success': True,
            'base_price': pricing_result['base_price'],
            'term_multiplier': pricing_result['multiplier'],
            'coverage_multiplier': coverage_multiplier,
            'subtotal': round(final_price, 2),
            'customer_type': customer_type,
            'data_source': pricing_result['data_source'],
            'pricing_updated': 'July 2025'
        }

    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_all_products_pricing():
    """Get pricing for all products - tries database first"""
    try:
        database_url = os.environ.get('DATABASE_URL')
        if database_url:
            import psycopg2

            conn = psycopg2.connect(database_url)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT p.product_code, p.product_name, p.base_price, 
                       pr.term_years, pr.multiplier, pr.customer_type,
                       ROUND(p.base_price * pr.multiplier, 2) as final_price
                FROM products p 
                JOIN pricing pr ON p.product_code = pr.product_code 
                WHERE pr.customer_type = 'retail'
                ORDER BY p.product_code, pr.term_years;
            ''')

            results = cursor.fetchall()
            cursor.close()
            conn.close()

            # Group results by product
            products = {}
            for row in results:
                code, name, base_price, term, multiplier, cust_type, final_price = row
                if code not in products:
                    products[code] = {
                        'product_code': code,
                        'product_name': name,
                        'base_price': float(base_price),
                        'pricing': {}
                    }
                products[code]['pricing'][term] = {
                    'multiplier': float(multiplier),
                    'price': float(final_price)
                }

            return {
                'success': True,
                'products': list(products.values()),
                'data_source': 'database'
            }

    except Exception as e:
        print(f"Database error: {e}")

    # Fallback to hardcoded data
    products = []
    for product_type, config in HERO_PRODUCTS_PRICING.items():
        product = {
            'product_type': product_type,
            'base_price': config['base_price'],
            'pricing': {}
        }
        for term, multiplier in config['multipliers'].items():
            product['pricing'][term] = {
                'multiplier': multiplier,
                'price': round(config['base_price'] * multiplier, 2)
            }
        products.append(product)

    return {
        'success': True,
        'products': products,
        'data_source': 'hardcoded'
    }


def get_contact_info():
    """Get updated contact information"""
    try:
        database_url = os.environ.get('POSTGRES_URL')
        if database_url:
            import psycopg2

            conn = psycopg2.connect(database_url)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT key, value FROM settings WHERE key IN ('contact_phone', 'contact_email');")
            results = cursor.fetchall()
            cursor.close()
            conn.close()

            contact_info = {}
            for key, value in results:
                contact_info[key.replace('contact_', '')] = value.strip('"')

            if contact_info:
                return {**contact_info, 'data_source': 'database'}
    except:
        pass

    # Fallback to hardcoded
    return CONTACT_INFO


def get_hero_pricing():
    """Get Hero products pricing configuration"""
    return HERO_PRODUCTS_PRICING

# Backward compatibility functions


def get_hero_products():
    """Maintain backward compatibility"""
    return get_all_products_pricing()


def get_hero_product_by_code(product_code):
    """Get specific product info"""
    result = get_price_from_db_or_fallback(
        product_code, 1, 'retail')  # Get base info
    if result['success']:
        return {
            'product_code': product_code,
            'base_price': result['base_price'],
            'data_source': result['data_source']
        }
    return None

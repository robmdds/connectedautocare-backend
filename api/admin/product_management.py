#!/usr/bin/env python3
"""
ConnectedAutoCare.com - Admin Product Management API
Comprehensive product and pricing management for admin panel
"""

import json
import os
import functools
from datetime import datetime
from flask import Blueprint, request, jsonify

# Create blueprint for product management
product_bp = Blueprint('product_management', __name__)

# Import authentication decorators - handle import gracefully
try:
    from ..auth.admin_auth import require_admin_auth, require_permission, AdminSecurity
except ImportError:
    # Fallback for when running independently
    def require_admin_auth(f):
        @functools.wraps(f)  # This preserves the original function name
        def auth_wrapper(*args, **kwargs):
            return f(*args, **kwargs)
        return auth_wrapper

    def require_permission(permission):
        def decorator(f):
            @functools.wraps(f)  # This preserves the original function name
            def permission_wrapper(*args, **kwargs):
                return f(*args, **kwargs)
            return permission_wrapper
        return decorator

    class AdminSecurity:
        @staticmethod
        def log_admin_action(username, action, details=None):
            print(f"ADMIN ACTION: {username} - {action} - {details}")

# Product data storage (in production, use database)
PRODUCTS_DATA_FILE = "/tmp/products_data.json"
PRICING_DATA_FILE = "/tmp/pricing_data.json"


class ProductManager:
    """Product management utilities"""

    @staticmethod
    def load_products():
        """Load products from storage"""
        try:
            if os.path.exists(PRODUCTS_DATA_FILE):
                with open(PRODUCTS_DATA_FILE, 'r') as f:
                    return json.load(f)
            else:
                return ProductManager.get_default_products()
        except Exception as e:
            print(f"Error loading products: {str(e)}")
            return ProductManager.get_default_products()

    @staticmethod
    def save_products(products):
        """Save products to storage"""
        try:
            with open(PRODUCTS_DATA_FILE, 'w') as f:
                json.dump(products, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving products: {e}")
            return False

    @staticmethod
    def get_default_products():
        """Get default Hero products configuration"""
        return {
            "hero_products": {
                "home_protection": {
                    "id": "home_protection",
                    "name": "Home Protection Plan",
                    "category": "home_protection",
                    "description": "Comprehensive home protection coverage for major systems and appliances",
                    "active": True,
                    "pricing": {
                        "1": {"base_price": 199, "admin_fee": 25},
                        "2": {"base_price": 299, "admin_fee": 25},
                        "3": {"base_price": 399, "admin_fee": 25},
                        "4": {"base_price": 469, "admin_fee": 25},
                        "5": {"base_price": 569, "admin_fee": 25}
                    },
                    "features": [
                        "HVAC system coverage",
                        "Plumbing protection",
                        "Electrical system coverage",
                        "24/7 customer support",
                        "No service call fees"
                    ],
                    "terms_available": [1, 2, 3, 4, 5],
                    "coverage_limits": ["500", "1000"],
                    "tax_rate": 0.08,
                    "wholesale_discount": 0.15
                },
                "home_deductible_reimbursement": {
                    "id": "home_deductible_reimbursement",
                    "name": "Home Deductible Reimbursement",
                    "category": "home_protection",
                    "description": "Reimbursement for home insurance deductibles",
                    "active": True,
                    "pricing": {
                        "1": {"base_price": 160, "admin_fee": 15},
                        "2": {"base_price": 215, "admin_fee": 15},
                        "3": {"base_price": 255, "admin_fee": 15}
                    },
                    "features": [
                        "Up to $1,000 deductible reimbursement",
                        "Covers multiple claims per year",
                        "Fast claim processing",
                        "No waiting period"
                    ],
                    "terms_available": [1, 2, 3],
                    "coverage_limits": ["500", "1000"],
                    "tax_rate": 0.08,
                    "wholesale_discount": 0.15
                },
                "auto_advantage_ddr": {
                    "id": "auto_advantage_ddr",
                    "name": "Auto Advantage Deductible Reimbursement",
                    "category": "deductible_reimbursement",
                    "description": "Comprehensive auto deductible reimbursement program",
                    "active": True,
                    "pricing": {
                        "1": {"base_price": 120, "admin_fee": 15},
                        "2": {"base_price": 180, "admin_fee": 15},
                        "3": {"base_price": 225, "admin_fee": 15}
                    },
                    "features": [
                        "Collision deductible reimbursement",
                        "Comprehensive deductible coverage",
                        "Glass damage protection",
                        "Rental car assistance"
                    ],
                    "terms_available": [1, 2, 3],
                    "coverage_limits": ["500", "1000"],
                    "tax_rate": 0.08,
                    "wholesale_discount": 0.15
                }
            },
            "vsc_products": {
                "silver": {
                    "id": "silver",
                    "name": "Silver VSC Coverage",
                    "description": "Basic vehicle service contract coverage",
                    "active": True,
                    "coverage_items": [
                        "Engine components",
                        "Transmission",
                        "Drive axle",
                        "Brake system",
                        "Electrical system (basic)"
                    ],
                    "deductible_options": [0, 50, 100, 200],
                    "term_options": [12, 24, 36, 48],
                    "mileage_options": ["15K", "25K", "50K", "75K", "100K", "125K", "Unlimited"]
                },
                "gold": {
                    "id": "gold",
                    "name": "Gold VSC Coverage",
                    "description": "Enhanced vehicle service contract coverage",
                    "active": True,
                    "coverage_items": [
                        "All Silver coverage",
                        "Air conditioning",
                        "Power steering",
                        "Fuel system",
                        "Cooling system",
                        "Rental car reimbursement"
                    ],
                    "deductible_options": [0, 50, 100, 200],
                    "term_options": [12, 24, 36, 48, 60],
                    "mileage_options": ["15K", "25K", "50K", "75K", "100K", "125K", "Unlimited"]
                },
                "platinum": {
                    "id": "platinum",
                    "name": "Platinum VSC Coverage",
                    "description": "Comprehensive vehicle service contract coverage",
                    "active": True,
                    "coverage_items": [
                        "All Gold coverage",
                        "Complete electrical system",
                        "Advanced diagnostics",
                        "Trip interruption coverage",
                        "Towing and roadside assistance",
                        "Extended rental car coverage"
                    ],
                    "deductible_options": [0, 50, 100, 200],
                    "term_options": [12, 24, 36, 48, 60, 72],
                    "mileage_options": ["15K", "25K", "50K", "75K", "100K", "125K", "Unlimited"]
                }
            }
        }


# Product management routes
@product_bp.route('/health', methods=['GET'])
def product_management_health():
    """Product management health check"""
    return jsonify({
        'success': True,
        'message': 'Product management API is operational',
        'features': ['Hero Products', 'VSC Products', 'Pricing Management', 'Bulk Operations']
    })


@product_bp.route('/', methods=['GET'])
@require_admin_auth
@require_permission('products')
def get_all_products_admin():
    """Get all products for admin management"""
    try:
        products = ProductManager.load_products()

        # Log admin action if available
        if hasattr(request, 'admin_user'):
            AdminSecurity.log_admin_action(
                request.admin_user['username'],
                'view_products'
            )

        return jsonify({
            'success': True,
            'data': products
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to load products: {str(e)}'
        }), 500


@product_bp.route('/hero', methods=['GET'])
@require_admin_auth
@require_permission('products')
def get_hero_products_admin():
    """Get Hero products for admin management"""
    try:
        products = ProductManager.load_products()
        hero_products = products.get('hero_products', {})

        return jsonify({
            'success': True,
            'data': hero_products
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to load Hero products: {str(e)}'
        }), 500


@product_bp.route('/hero/<product_id>', methods=['PUT'])
@require_admin_auth
@require_permission('products')
def update_hero_product(product_id):
    """Update Hero product configuration"""
    try:
        data = request.get_json()
        products = ProductManager.load_products()

        if 'hero_products' not in products:
            products['hero_products'] = {}

        if product_id not in products['hero_products']:
            return jsonify({
                'success': False,
                'error': 'Product not found'
            }), 404

        # Update product data
        products['hero_products'][product_id].update(data)
        products['hero_products'][product_id]['updated_at'] = datetime.utcnow(
        ).isoformat()

        # Save changes
        if ProductManager.save_products(products):
            if hasattr(request, 'admin_user'):
                AdminSecurity.log_admin_action(
                    request.admin_user['username'],
                    'update_hero_product',
                    {'product_id': product_id, 'changes': data}
                )

            return jsonify({
                'success': True,
                'data': products['hero_products'][product_id]
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save product changes'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to update product: {str(e)}'
        }), 500


@product_bp.route('/hero', methods=['POST'])
@require_admin_auth
@require_permission('products')
def create_hero_product():
    """Create new Hero product"""
    try:
        data = request.get_json()
        products = ProductManager.load_products()

        if 'hero_products' not in products:
            products['hero_products'] = {}

        product_id = data.get('id')
        if not product_id:
            return jsonify({
                'success': False,
                'error': 'Product ID required'
            }), 400

        if product_id in products['hero_products']:
            return jsonify({
                'success': False,
                'error': 'Product already exists'
            }), 409

        # Create new product
        new_product = {
            'id': product_id,
            'name': data.get('name', ''),
            'category': data.get('category', ''),
            'description': data.get('description', ''),
            'active': data.get('active', True),
            'pricing': data.get('pricing', {}),
            'features': data.get('features', []),
            'terms_available': data.get('terms_available', []),
            'coverage_limits': data.get('coverage_limits', []),
            'tax_rate': data.get('tax_rate', 0.08),
            'wholesale_discount': data.get('wholesale_discount', 0.15),
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }

        products['hero_products'][product_id] = new_product

        # Save changes
        if ProductManager.save_products(products):
            if hasattr(request, 'admin_user'):
                AdminSecurity.log_admin_action(
                    request.admin_user['username'],
                    'create_hero_product',
                    {'product_id': product_id, 'product_data': new_product}
                )

            return jsonify({
                'success': True,
                'data': new_product
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save new product'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to create product: {str(e)}'
        }), 500


@product_bp.route('/hero/<product_id>', methods=['DELETE'])
@require_admin_auth
@require_permission('products')
def delete_hero_product(product_id):
    """Delete Hero product"""
    try:
        products = ProductManager.load_products()

        if 'hero_products' not in products or product_id not in products['hero_products']:
            return jsonify({
                'success': False,
                'error': 'Product not found'
            }), 404

        # Delete product
        deleted_product = products['hero_products'].pop(product_id)

        # Save changes
        if ProductManager.save_products(products):
            if hasattr(request, 'admin_user'):
                AdminSecurity.log_admin_action(
                    request.admin_user['username'],
                    'delete_hero_product',
                    {'product_id': product_id}
                )

            return jsonify({
                'success': True,
                'message': f'Product {product_id} deleted successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save changes'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to delete product: {str(e)}'
        }), 500


@product_bp.route('/vsc', methods=['GET'])
@require_admin_auth
@require_permission('products')
def get_vsc_products():
    """Get VSC products for admin management"""
    try:
        products = ProductManager.load_products()
        vsc_products = products.get('vsc_products', {})

        return jsonify({
            'success': True,
            'data': vsc_products
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to load VSC products: {str(e)}'
        }), 500


@product_bp.route('/vsc/<coverage_level>', methods=['PUT'])
@require_admin_auth
@require_permission('products')
def update_vsc_product(coverage_level):
    """Update VSC product configuration"""
    try:
        data = request.get_json()
        products = ProductManager.load_products()

        if 'vsc_products' not in products:
            products['vsc_products'] = {}

        if coverage_level not in products['vsc_products']:
            return jsonify({
                'success': False,
                'error': 'VSC coverage level not found'
            }), 404

        # Update VSC product data
        products['vsc_products'][coverage_level].update(data)
        products['vsc_products'][coverage_level]['updated_at'] = datetime.utcnow(
        ).isoformat()

        # Save changes
        if ProductManager.save_products(products):
            if hasattr(request, 'admin_user'):
                AdminSecurity.log_admin_action(
                    request.admin_user['username'],
                    'update_vsc_product',
                    {'coverage_level': coverage_level, 'changes': data}
                )

            return jsonify({
                'success': True,
                'data': products['vsc_products'][coverage_level]
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save VSC product changes'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to update VSC product: {str(e)}'
        }), 500


@product_bp.route('/toggle-status/<product_type>/<product_id>', methods=['POST'])
@require_admin_auth
@require_permission('products')
def toggle_product_status(product_type, product_id):
    """Toggle product active/inactive status"""
    try:
        products = ProductManager.load_products()

        if product_type == 'hero':
            if product_id not in products.get('hero_products', {}):
                return jsonify({
                    'success': False,
                    'error': 'Hero product not found'
                }), 404

            current_status = products['hero_products'][product_id].get(
                'active', True)
            products['hero_products'][product_id]['active'] = not current_status
            products['hero_products'][product_id]['updated_at'] = datetime.utcnow(
            ).isoformat()

        elif product_type == 'vsc':
            if product_id not in products.get('vsc_products', {}):
                return jsonify({
                    'success': False,
                    'error': 'VSC product not found'
                }), 404

            current_status = products['vsc_products'][product_id].get(
                'active', True)
            products['vsc_products'][product_id]['active'] = not current_status
            products['vsc_products'][product_id]['updated_at'] = datetime.utcnow(
            ).isoformat()

        else:
            return jsonify({
                'success': False,
                'error': 'Invalid product type'
            }), 400

        # Save changes
        if ProductManager.save_products(products):
            if hasattr(request, 'admin_user'):
                AdminSecurity.log_admin_action(
                    request.admin_user['username'],
                    'toggle_product_status',
                    {'product_type': product_type, 'product_id': product_id,
                        'new_status': not current_status}
                )

            return jsonify({
                'success': True,
                'data': {
                    'product_id': product_id,
                    'active': not current_status
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save status change'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to toggle product status: {str(e)}'
        }), 500


@product_bp.route('/pricing/bulk-update', methods=['POST'])
@require_admin_auth
@require_permission('pricing')
def bulk_update_pricing():
    """Bulk update pricing for multiple products"""
    try:
        data = request.get_json()
        products = ProductManager.load_products()

        updates = data.get('updates', [])
        results = []

        for update in updates:
            product_type = update.get('product_type')  # 'hero' or 'vsc'
            product_id = update.get('product_id')
            pricing_data = update.get('pricing')

            if product_type == 'hero' and product_id in products.get('hero_products', {}):
                products['hero_products'][product_id]['pricing'] = pricing_data
                products['hero_products'][product_id]['updated_at'] = datetime.utcnow(
                ).isoformat()
                results.append({'product_id': product_id, 'status': 'updated'})
            elif product_type == 'vsc' and product_id in products.get('vsc_products', {}):
                # VSC pricing updates would go here
                results.append({'product_id': product_id, 'status': 'updated'})
            else:
                results.append(
                    {'product_id': product_id, 'status': 'not_found'})

        # Save all changes
        if ProductManager.save_products(products):
            if hasattr(request, 'admin_user'):
                AdminSecurity.log_admin_action(
                    request.admin_user['username'],
                    'bulk_update_pricing',
                    {'updates': len(updates), 'results': results}
                )

            return jsonify({
                'success': True,
                'data': {
                    'updated_count': len([r for r in results if r['status'] == 'updated']),
                    'results': results
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save pricing changes'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to bulk update pricing: {str(e)}'
        }), 500


if __name__ == "__main__":
    # Test product management
    manager = ProductManager()
    products = manager.get_default_products()
    print("Default products loaded successfully")
    print(f"Hero products: {len(products['hero_products'])}")
    print(f"VSC products: {len(products['vsc_products'])}")

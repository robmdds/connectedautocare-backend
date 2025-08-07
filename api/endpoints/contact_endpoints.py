"""
Contact Information Endpoints
Management of company contact information
"""

from flask import Blueprint, jsonify, request
from datetime import datetime, timezone
from utils.database import get_db_manager, execute_query
from auth.user_auth import token_required, role_required

# Initialize blueprint
contact_bp = Blueprint('contact', __name__)

@contact_bp.route('/', methods=['GET'])
def get_contact_info():
    """Get current contact information"""
    try:
        db_manager = get_db_manager()
        if not db_manager.available:
            # Fallback to default values if database is not available
            return jsonify({
                'phone': '1-(866) 660-7003',
                'email': 'support@connectedautocare.com',
                'support_hours': '24/7',
                'data_source': 'fallback'
            })

        # Get contact info from database
        contact_result = execute_query('''
            SELECT key, value FROM settings 
            WHERE key IN ('contact_phone', 'contact_email', 'support_hours')
        ''')

        if not contact_result['success']:
            return jsonify('Failed to retrieve contact info'), 500

        contact_data = {}
        for setting in contact_result['data']:
            contact_data[setting['key']] = setting['value']

        return jsonify({
            'phone': contact_data.get('contact_phone', '1-(866) 660-7003'),
            'email': contact_data.get('contact_email', 'support@connectedautocare.com'),
            'support_hours': contact_data.get('support_hours', '24/7'),
            'data_source': 'database'
        })

    except Exception as e:
        return jsonify(f'Failed to get contact info: {str(e)}'), 500

@contact_bp.route('/', methods=['PUT'])
@token_required
@role_required('admin')
def update_contact_info():
    """Update contact information"""
    try:
        data = request.get_json()
        if not data:
            return jsonify('Contact data is required'), 400

        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify('Database not available'), 503

        updates = []
        allowed_fields = ['phone', 'email', 'support_hours']
        
        for field in allowed_fields:
            if field in data:
                # Map frontend field names to database keys
                db_key = {
                    'phone': 'contact_phone',
                    'email': 'contact_email',
                    'support_hours': 'support_hours'
                }[field]
                
                updates.append({
                    'key': db_key,
                    'value': data[field],
                    'updated_at': datetime.now(timezone.utc)
                })

        if not updates:
            return jsonify('No valid fields to update'), 400

        # Update each setting
        for update in updates:
            db_manager.upsert_record(
                'settings',
                update,
                'key = %s',
                (update['key'],)
            )

        return jsonify({
            'message': 'Contact information updated successfully',
            'updated_fields': [u['key'] for u in updates]
        })

    except Exception as e:
        return jsonify(f'Failed to update contact info: {str(e)}'), 500

@contact_bp.route('/departments', methods=['GET'])
def get_contact_departments():
    """Get contact information for different departments"""
    try:
        db_manager = get_db_manager()
        if not db_manager.available:
            # Fallback to default values
            return jsonify({
                'departments': [
                    {
                        'name': 'Customer Support',
                        'email': 'support@connectedautocare.com',
                        'phone': '1-(866) 660-7003',
                        'hours': '24/7'
                    },
                    {
                        'name': 'Sales',
                        'email': 'sales@connectedautocare.com',
                        'phone': '1-(866) 660-7004',
                        'hours': 'Mon-Fri 9am-5pm EST'
                    },
                    {
                        'name': 'Claims',
                        'email': 'claims@connectedautocare.com',
                        'phone': '1-(866) 660-7005',
                        'hours': 'Mon-Fri 8am-6pm EST'
                    }
                ],
                'data_source': 'fallback'
            })

        # Get department contacts from database
        dept_result = execute_query('''
            SELECT name, email, phone, hours 
            FROM contact_departments
            WHERE active = TRUE
            ORDER BY display_order
        ''')

        if not dept_result['success']:
            return jsonify('Failed to retrieve department contacts'), 500

        departments = []
        for dept in dept_result['data']:
            departments.append({
                'name': dept['name'],
                'email': dept['email'],
                'phone': dept['phone'],
                'hours': dept['hours']
            })

        return jsonify({
            'departments': departments if departments else [
                {
                    'name': 'Customer Support',
                    'email': 'support@connectedautocare.com',
                    'phone': '1-(866) 660-7003',
                    'hours': '24/7'
                }
            ],
            'data_source': 'database'
        })

    except Exception as e:
        return jsonify(f'Failed to get department contacts: {str(e)}'), 500

@contact_bp.route('/health')
def contact_health():
    """Contact service health check"""
    try:
        db_manager = get_db_manager()
        
        return jsonify({
            'service': 'Contact Information API',
            'status': 'healthy',
            'database_connected': db_manager.available,
            'features': [
                'Company Contact Management',
                'Department Contacts',
                'Support Hours'
            ]
        })
    except Exception as e:
        return jsonify({
            'service': 'Contact Information API',
            'status': 'degraded',
            'error': str(e)
        }), 500
"""
TPA (Third Party Administrator) Endpoints
Management of third-party administrator partners
"""

from flask import Blueprint, jsonify, request
from datetime import datetime, timezone
import uuid
from utils.database import get_db_manager, execute_query
from auth.user_auth import token_required, role_required

# Initialize blueprint
tpa_bp = Blueprint('tpa', __name__)

@tpa_bp.route('/', methods=['GET'])
@token_required
@role_required('admin')
def get_tpas():
    """Get all Third Party Administrators"""
    try:
        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify('Database not available'), 503

        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        offset = (page - 1) * per_page

        # Get total count
        count_result = execute_query(
            'SELECT COUNT(*) FROM tpas WHERE status = %s',
            ('active',)
        )
        total_count = count_result['data'][0]['count'] if count_result['success'] else 0

        # Get paginated results
        tpas_result = execute_query('''
            SELECT id, name, api_endpoint, contact_email, contact_phone,
                   status, supported_products, commission_rate, created_at, updated_at
            FROM tpas
            WHERE status = 'active'
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        ''', (per_page, offset))

        if not tpas_result['success']:
            return jsonify('Failed to retrieve TPAs'), 500

        tpas = []
        for tpa in tpas_result['data']:
            tpas.append({
                'id': str(tpa['id']),
                'name': tpa['name'],
                'api_endpoint': tpa['api_endpoint'],
                'contact_info': {
                    'email': tpa['contact_email'],
                    'phone': tpa['contact_phone']
                },
                'status': tpa['status'],
                'supported_products': tpa['supported_products'] or [],
                'commission_rate': float(tpa['commission_rate']) if tpa['commission_rate'] else 0.0,
                'created_at': tpa['created_at'].isoformat() if tpa['created_at'] else None,
                'updated_at': tpa['updated_at'].isoformat() if tpa['updated_at'] else None
            })

        return jsonify({
            'tpas': tpas,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_count,
                'pages': (total_count + per_page - 1) // per_page
            }
        })

    except Exception as e:
        return jsonify(f'Failed to get TPAs: {str(e)}'), 500

@tpa_bp.route('/', methods=['POST'])
@token_required
@role_required('admin')
def create_tpa():
    """Create new TPA"""
    try:
        data = request.get_json()
        if not data:
            return jsonify('TPA data is required'), 400

        required_fields = ['name', 'api_endpoint', 'contact_email']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify(f'Missing fields: {", ".join(missing_fields)}'), 400

        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify('Database not available'), 503

        tpa_id = str(uuid.uuid4())
        tpa_data = {
            'id': tpa_id,
            'name': data['name'],
            'api_endpoint': data['api_endpoint'],
            'contact_email': data['contact_email'],
            'contact_phone': data.get('contact_phone', ''),
            'status': data.get('status', 'active'),
            'supported_products': data.get('supported_products', []),
            'commission_rate': data.get('commission_rate', 0.15),
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        }

        insert_result = db_manager.insert_record('tpas', tpa_data)
        if not insert_result['success']:
            return jsonify('Failed to create TPA'), 500

        return jsonify({
            'message': 'TPA created successfully',
            'tpa': tpa_data
        }), 201

    except Exception as e:
        return jsonify(f'Failed to create TPA: {str(e)}'), 500

@tpa_bp.route('/<tpa_id>', methods=['PUT'])
@token_required
@role_required('admin')
def update_tpa(tpa_id):
    """Update existing TPA"""
    try:
        data = request.get_json()
        if not data:
            return jsonify('TPA data is required'), 400

        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify('Database not available'), 503

        # Check if TPA exists
        tpa_result = execute_query(
            'SELECT id FROM tpas WHERE id = %s',
            (tpa_id,)
        )
        if not tpa_result['success'] or not tpa_result['data']:
            return jsonify('TPA not found'), 404

        # Build update data
        update_data = {
            'updated_at': datetime.now(timezone.utc)
        }
        
        allowed_fields = ['name', 'api_endpoint', 'contact_email', 'contact_phone',
                         'status', 'supported_products', 'commission_rate']
        
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]

        update_result = db_manager.update_record(
            'tpas',
            update_data,
            'id = %s',
            (tpa_id,)
        )

        if not update_result['success']:
            return jsonify('Failed to update TPA'), 500

        return jsonify({
            'message': 'TPA updated successfully',
            'tpa_id': tpa_id,
            'updated_fields': list(update_data.keys())
        })

    except Exception as e:
        return jsonify(f'Failed to update TPA: {str(e)}'), 500

@tpa_bp.route('/<tpa_id>', methods=['DELETE'])
@token_required
@role_required('admin')
def delete_tpa(tpa_id):
    """Delete TPA (soft delete)"""
    try:
        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify('Database not available'), 503

        # Check if TPA exists
        tpa_result = execute_query(
            'SELECT name FROM tpas WHERE id = %s',
            (tpa_id,)
        )
        if not tpa_result['success'] or not tpa_result['data']:
            return jsonify('TPA not found'), 404

        tpa_name = tpa_result['data'][0]['name']

        # Soft delete by setting status to 'inactive'
        update_result = db_manager.update_record(
            'tpas',
            {
                'status': 'inactive',
                'updated_at': datetime.now(timezone.utc)
            },
            'id = %s',
            (tpa_id,)
        )

        if not update_result['success']:
            return jsonify('Failed to delete TPA'), 500

        return jsonify({
            'message': f'TPA "{tpa_name}" deleted successfully',
            'tpa_id': tpa_id
        })

    except Exception as e:
        return jsonify(f'Failed to delete TPA: {str(e)}'), 500

@tpa_bp.route('/<tpa_id>/test-connection', methods=['POST'])
@token_required
@role_required('admin')
def test_tpa_connection(tpa_id):
    """Test connection to TPA API"""
    try:
        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify('Database not available'), 503

        # Get TPA details
        tpa_result = execute_query(
            'SELECT api_endpoint FROM tpas WHERE id = %s AND status = %s',
            (tpa_id, 'active')
        )
        if not tpa_result['success'] or not tpa_result['data']:
            return jsonify('TPA not found or inactive'), 404

        api_endpoint = tpa_result['data'][0]['api_endpoint']

        # In a real implementation, you would make an actual API call here
        test_response = {
            'success': True,
            'endpoint': api_endpoint,
            'status': 'connection_simulated',
            'message': 'This is a simulated connection test. In production, this would make an actual API call.',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        return jsonify(test_response)

    except Exception as e:
        return jsonify(f'Connection test failed: {str(e)}'), 500

@tpa_bp.route('/health')
def tpa_health():
    """TPA service health check"""
    try:
        db_manager = get_db_manager()
        
        return jsonify({
            'service': 'TPA Management API',
            'status': 'healthy',
            'database_connected': db_manager.available,
            'features': [
                'TPA Management',
                'API Integration',
                'Commission Tracking'
            ]
        })
    except Exception as e:
        return jsonify({
            'service': 'TPA Management API',
            'status': 'degraded',
            'error': str(e)
        }), 500
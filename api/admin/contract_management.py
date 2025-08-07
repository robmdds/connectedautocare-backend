#!/usr/bin/env python3
"""
ConnectedAutoCare.com - Contract Management API (Database Version)
Handles contract templates, document uploads, and automated contract generation
"""

import os
import json
import uuid
from datetime import datetime, date
from flask import Blueprint, request, jsonify, send_file
from werkzeug.utils import secure_filename
import tempfile
import zipfile
from decimal import Decimal

# Import your database utilities
from utils.database import get_db_manager, execute_query
from auth.user_auth import token_required, role_required

# Create blueprint for contract management
contract_bp = Blueprint('contract_management', __name__)

def serialize_datetime(obj):
    """Helper function to serialize datetime objects"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj

def serialize_contract_data(data):
    """Serialize contract data for JSON response"""
    if isinstance(data, dict):
        return {key: serialize_datetime(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [serialize_contract_data(item) for item in data]
    else:
        return serialize_datetime(data)

@contract_bp.route('/health', methods=['GET'])
def contract_management_health():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'message': 'Contract management API is healthy',
        'features': ['Template Management', 'Contract Generation', 'File Upload', 'Bulk Export'],
        'timestamp': datetime.now().isoformat()
    })

@contract_bp.route('/templates', methods=['GET'])
@token_required
def get_contract_templates():
    """Get all contract templates"""
    try:
        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503

        # Get filters from query parameters
        product_type = request.args.get('product_type')
        active_filter = request.args.get('active')  # No default value
        
        query = '''
            SELECT id, template_id, name, product_type, product_id, 
                   template_file, fields, active, created_at, updated_at
            FROM contract_templates 
            WHERE 1=1
        '''
        params = []
        
        if product_type:
            query += ' AND product_type = %s'
            params.append(product_type)
            
        if active_filter is not None:  # Allow explicit filtering by active status
            query += ' AND active = %s'
            params.append(active_filter.lower() == 'true')
            
        query += ' ORDER BY created_at DESC'

        result = execute_query(query, tuple(params))
        print('Get templates query result:', result)  # Debug log
        
        if result['success']:
            templates = []
            for template in result['data']:
                template_dict = {
                    'id': template['id'],
                    'template_id': template['template_id'],
                    'name': template['name'],
                    'product_type': template['product_type'],
                    'product_id': template['product_id'],
                    'template_file': template['template_file'],
                    'fields': json.loads(template['fields']) if isinstance(template['fields'], str) else (template['fields'] or []),
                    'active': template['active'],
                    'created_date': template['created_at'].strftime('%Y-%m-%d') if template['created_at'] else None,
                    'updated_date': template['updated_at'].strftime('%Y-%m-%d') if template['updated_at'] else None
                }
                templates.append(template_dict)

            return jsonify({
                'success': True,
                'data': {
                    'templates': templates,
                    'total_count': len(templates)
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to retrieve templates'
            }), 500

    except Exception as e:
        print('Error:', str(e))  # Debug log
        return jsonify({
            'success': False,
            'error': f'Failed to retrieve templates: {str(e)}'
        }), 500

@contract_bp.route('/templates/<template_id>', methods=['GET'])
@token_required
def get_contract_template(template_id):
    """Get specific contract template"""
    try:
        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503

        result = execute_query('''
            SELECT id, template_id, name, product_type, product_id, 
                   template_file, fields, active, created_at, updated_at
            FROM contract_templates 
            WHERE template_id = %s
        ''', (template_id,), 'one')

        if result['success'] and result['data']:
            template = result['data']
            template_dict = {
                'id': template['id'],
                'template_id': template['template_id'],
                'name': template['name'],
                'product_type': template['product_type'],
                'product_id': template['product_id'],
                'template_file': template['template_file'],
                'fields': template['fields'] if template['fields'] else [],
                'active': template['active'],
                'created_date': template['created_at'].strftime('%Y-%m-%d') if template['created_at'] else None,
                'updated_date': template['updated_at'].strftime('%Y-%m-%d') if template['updated_at'] else None
            }

            return jsonify({
                'success': True,
                'data': template_dict
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Template not found'
            }), 404

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to retrieve template: {str(e)}'
        }), 500

@contract_bp.route('/templates', methods=['POST'])
@token_required
@role_required('admin')
def create_contract_template():
    """Create new contract template"""
    try:
        data = request.get_json()
        user_id = request.current_user.get('user_id')

        # Validate required fields
        required_fields = ['name', 'product_type', 'product_id', 'fields']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400

        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503

        # Generate template ID
        template_id = data.get('template_id') or f"{data['product_type']}_{data['product_id']}"

        # Check if template already exists
        existing_result = execute_query(
            'SELECT id FROM contract_templates WHERE template_id = %s',
            (template_id,), 'one'
        )

        if existing_result['success'] and existing_result['data']:
            return jsonify({
                'success': False,
                'error': 'Template with this ID already exists'
            }), 409

        # Create template
        insert_result = execute_query('''
            INSERT INTO contract_templates 
            (template_id, name, product_type, product_id, template_file, fields, active, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, template_id, name, product_type, product_id, template_file, fields, active, created_at, updated_at
        ''', (
            template_id,
            data['name'],
            data['product_type'],
            data['product_id'],
            data.get('template_file', ''),
            json.dumps(data['fields']),
            data.get('active', True),
            user_id
        ), 'one')

        if insert_result['success'] and insert_result['data']:
            template = insert_result['data']
            template_dict = {
                'id': template['id'],
                'template_id': template['template_id'],
                'name': template['name'],
                'product_type': template['product_type'],
                'product_id': template['product_id'],
                'template_file': template['template_file'],
                'fields': template['fields'] if template['fields'] else [],
                'active': template['active'],
                'created_date': template['created_at'].strftime('%Y-%m-%d'),
                'updated_date': template['updated_at'].strftime('%Y-%m-%d')
            }

            return jsonify({
                'success': True,
                'data': template_dict,
                'message': 'Contract template created successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to create template'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to create template: {str(e)}'
        }), 500

@contract_bp.route('/templates/<template_id>', methods=['PUT'])
@token_required
@role_required('admin')
def update_contract_template(template_id):
    """Update contract template"""
    try:
        data = request.get_json()
        
        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503

        # Check if template exists
        existing_result = execute_query(
            'SELECT id FROM contract_templates WHERE template_id = %s',
            (template_id,), 'one'
        )

        if not existing_result['success'] or not existing_result['data']:
            return jsonify({
                'success': False,
                'error': 'Template not found'
            }), 404

        # Build update query dynamically
        update_fields = []
        params = []
        
        updatable_fields = ['name', 'fields', 'active', 'template_file', 'product_type', 'product_id']
        for field in updatable_fields:
            if field in data:
                if field == 'fields':
                    update_fields.append(f'{field} = %s')
                    params.append(json.dumps(data[field]))
                else:
                    update_fields.append(f'{field} = %s')
                    params.append(data[field])

        if not update_fields:
            return jsonify({
                'success': False,
                'error': 'No valid fields to update'
            }), 400

        update_fields.append('updated_at = CURRENT_TIMESTAMP')
        params.append(template_id)

        query = f'''
            UPDATE contract_templates 
            SET {', '.join(update_fields)}
            WHERE template_id = %s
            RETURNING id, template_id, name, product_type, product_id, template_file, fields, active, created_at, updated_at
        '''

        result = execute_query(query, tuple(params), 'one')

        if result['success'] and result['data']:
            template = result['data']
            template_dict = {
                'id': template['id'],
                'template_id': template['template_id'],
                'name': template['name'],
                'product_type': template['product_type'],
                'product_id': template['product_id'],
                'template_file': template['template_file'],
                'fields': template['fields'] if template['fields'] else [],
                'active': template['active'],
                'created_date': template['created_at'].strftime('%Y-%m-%d'),
                'updated_date': template['updated_at'].strftime('%Y-%m-%d')
            }

            return jsonify({
                'success': True,
                'data': template_dict,
                'message': 'Contract template updated successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update template'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to update template: {str(e)}'
        }), 500

@contract_bp.route('/templates/<template_id>/toggle-status', methods=['POST'])
@token_required
@role_required('admin')
def toggle_template_status(template_id):
    """Toggle template active status"""
    try:
        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503

        result = execute_query('''
            UPDATE contract_templates 
            SET active = NOT active, updated_at = CURRENT_TIMESTAMP
            WHERE template_id = %s
            RETURNING id, template_id, name, product_type, product_id, template_file, fields, active, created_at, updated_at
        ''', (template_id,), 'one')

        if result['success'] and result['data']:
            template = result['data']
            template_dict = {
                'id': template['id'],
                'template_id': template['template_id'],
                'name': template['name'],
                'product_type': template['product_type'],
                'product_id': template['product_id'],
                'template_file': template['template_file'],
                'fields': template['fields'] if template['fields'] else [],
                'active': template['active'],
                'created_date': template['created_at'].strftime('%Y-%m-%d'),
                'updated_date': template['updated_at'].strftime('%Y-%m-%d')
            }

            return jsonify({
                'success': True,
                'data': template_dict,
                'message': f'Template {"activated" if template["active"] else "deactivated"} successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Template not found'
            }), 404

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to toggle template status: {str(e)}'
        }), 500

@contract_bp.route('/upload-template', methods=['POST'])
@token_required
@role_required('admin')
def upload_contract_template():
    """Upload contract template file"""
    try:
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No file provided'
            }), 400

        file = request.files['file']
        template_id = request.form.get('template_id')
        user_id = request.current_user.get('user_id')

        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400

        # Validate file type
        allowed_extensions = {'.pdf', '.docx', '.doc'}
        file_ext = os.path.splitext(file.filename)[1].lower()

        if file_ext not in allowed_extensions:
            return jsonify({
                'success': False,
                'error': 'Invalid file type. Only PDF and Word documents are allowed.'
            }), 400

        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503

        # Secure filename
        filename = secure_filename(file.filename)
        file_content = file.read()
        file_size = len(file_content)

        # Get template UUID if template_id provided
        template_uuid = None
        if template_id:
            template_result = execute_query(
                'SELECT id FROM contract_templates WHERE template_id = %s',
                (template_id,), 'one'
            )
            if template_result['success'] and template_result['data']:
                template_uuid = template_result['data']['id']

        # Insert file record
        insert_result = execute_query('''
            INSERT INTO contract_template_files 
            (template_id, filename, original_filename, file_size, mime_type, uploaded_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, filename, original_filename, file_size, upload_date, status
        ''', (
            template_uuid,
            filename,
            file.filename,
            file_size,
            file.content_type,
            user_id
        ), 'one')

        if insert_result['success'] and insert_result['data']:
            upload_record = insert_result['data']
            upload_dict = {
                'id': upload_record['id'],
                'template_id': template_id,
                'filename': upload_record['filename'],
                'original_filename': upload_record['original_filename'],
                'file_size': upload_record['file_size'],
                'upload_date': upload_record['upload_date'].isoformat(),
                'status': upload_record['status']
            }

            # Update template file reference if template_id provided
            if template_uuid:
                execute_query('''
                    UPDATE contract_templates 
                    SET template_file = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (filename, template_uuid))

            return jsonify({
                'success': True,
                'data': upload_dict,
                'message': 'Template file uploaded successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to record file upload'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to upload file: {str(e)}'
        }), 500

@contract_bp.route('/generate', methods=['POST'])
@token_required
def generate_contract():
    """Generate contract from template with customer data"""
    try:
        data = request.get_json()
        user_id = request.current_user.get('user_id')

        # Validate required fields
        required_fields = ['template_id', 'customer_data']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400

        template_id = data['template_id']
        customer_data = data['customer_data']
        customer_id = data.get('customer_id')

        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503

        # Get template
        template_result = execute_query('''
            SELECT id, template_id, name, fields, active
            FROM contract_templates 
            WHERE template_id = %s
        ''', (template_id,), 'one')

        if not template_result['success'] or not template_result['data']:
            return jsonify({
                'success': False,
                'error': 'Template not found'
            }), 404

        template = template_result['data']
        
        if not template['active']:
            return jsonify({
                'success': False,
                'error': 'Template is not active'
            }), 400

        # Validate customer data against template fields
        template_fields = template['fields'] if template['fields'] else []
        missing_fields = []
        
        for field in template_fields:
            if field.get('required') and field['name'] not in customer_data:
                missing_fields.append(field['name'])

        if missing_fields:
            return jsonify({
                'success': False,
                'error': f'Missing required customer data: {", ".join(missing_fields)}'
            }), 400

        # Get reseller ID if user is a reseller
        reseller_id = None
        reseller_result = execute_query(
            'SELECT user_id FROM resellers WHERE user_id = %s',
            (user_id,), 'one'
        )
        if reseller_result['success'] and reseller_result['data']:
            reseller_id = user_id

        # Generate contract number
        contract_number = f"CON-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        # Insert generated contract
        insert_result = execute_query('''
            INSERT INTO generated_contracts 
            (contract_number, template_id, customer_id, reseller_id, customer_data, status, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, contract_number, generated_date, status
        ''', (
            contract_number,
            template['id'],
            customer_id,
            reseller_id,
            json.dumps(customer_data),
            'generated',
            user_id
        ), 'one')

        if insert_result['success'] and insert_result['data']:
            contract = insert_result['data']
            
            # Log activity
            execute_query('''
                INSERT INTO contract_activities (contract_id, activity_type, description, performed_by)
                VALUES (%s, %s, %s, %s)
            ''', (
                contract['id'],
                'created',
                f'Contract generated from template {template_id}',
                user_id
            ))

            contract_dict = {
                'id': contract['id'],
                'contract_number': contract['contract_number'],
                'template_id': template_id,
                'template_name': template['name'],
                'customer_data': customer_data,
                'generated_date': contract['generated_date'].isoformat(),
                'status': contract['status'],
                'file_path': f'contracts/{contract["id"]}.pdf'
            }

            return jsonify({
                'success': True,
                'data': contract_dict,
                'message': 'Contract generated successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to generate contract'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to generate contract: {str(e)}'
        }), 500

@contract_bp.route('/generated', methods=['GET'])
@token_required
def get_generated_contracts():
    """Get all generated contracts"""
    try:
        user_id = request.current_user.get('user_id')
        user_role = request.current_user.get('role', 'customer')
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status_filter = request.args.get('status')

        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503

        # Build query based on user role
        base_query = '''
            SELECT gc.id, gc.contract_number, gc.template_id, ct.name as template_name,
                   gc.customer_data, gc.status, gc.generated_date, gc.effective_date,
                   gc.file_path, gc.customer_id, gc.reseller_id
            FROM generated_contracts gc
            JOIN contract_templates ct ON gc.template_id = ct.id
        '''
        
        where_conditions = []
        params = []

        # Filter by user role
        if user_role == 'reseller':
            where_conditions.append('gc.reseller_id = %s')
            params.append(user_id)
        elif user_role == 'customer':
            where_conditions.append('gc.customer_id IN (SELECT id FROM customers WHERE user_id = %s)')
            params.append(user_id)
        # Admin can see all contracts

        if status_filter:
            where_conditions.append('gc.status = %s')
            params.append(status_filter)

        if where_conditions:
            base_query += ' WHERE ' + ' AND '.join(where_conditions)

        base_query += ' ORDER BY gc.generated_date DESC'
        base_query += ' LIMIT %s OFFSET %s'
        params.extend([per_page, (page - 1) * per_page])

        result = execute_query(base_query, tuple(params))

        if result['success']:
            contracts = []
            for contract in result['data']:
                contract_dict = {
                    'id': contract['id'],
                    'contract_number': contract['contract_number'],
                    'template_id': contract['template_id'],
                    'template_name': contract['template_name'],
                    'customer_data': contract['customer_data'] if contract['customer_data'] else {},
                    'status': contract['status'],
                    'generated_date': contract['generated_date'].isoformat() if contract['generated_date'] else None,
                    'effective_date': contract['effective_date'].isoformat() if contract['effective_date'] else None,
                    'file_path': contract['file_path'],
                    'customer_id': contract['customer_id'],
                    'reseller_id': contract['reseller_id']
                }
                contracts.append(contract_dict)

            return jsonify({
                'success': True,
                'data': {
                    'contracts': contracts,
                    'total_count': len(contracts),
                    'pagination': {
                        'page': page,
                        'per_page': per_page,
                        'total': len(contracts)
                    }
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to retrieve contracts'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to retrieve contracts: {str(e)}'
        }), 500

@contract_bp.route('/generated/<contract_id>', methods=['GET'])
@token_required
def get_generated_contract(contract_id):
    """Get specific generated contract"""
    try:
        user_id = request.current_user.get('user_id')
        user_role = request.current_user.get('role', 'customer')

        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503

        # Build query with role-based access control
        query = '''
            SELECT gc.id, gc.contract_number, gc.template_id, ct.name as template_name,
                   gc.customer_data, gc.contract_data, gc.status, gc.generated_date, 
                   gc.effective_date, gc.expiration_date, gc.file_path, gc.signed_file_path,
                   gc.customer_id, gc.reseller_id, gc.created_by
            FROM generated_contracts gc
            JOIN contract_templates ct ON gc.template_id = ct.id
            WHERE gc.id = %s
        '''
        params = [contract_id]

        # Add role-based access control
        if user_role == 'reseller':
            query += ' AND gc.reseller_id = %s'
            params.append(user_id)
        elif user_role == 'customer':
            query += ' AND gc.customer_id IN (SELECT id FROM customers WHERE user_id = %s)'
            params.append(user_id)

        result = execute_query(query, tuple(params), 'one')

        if result['success'] and result['data']:
            contract = result['data']
            
            # Get contract signatures
            signatures_result = execute_query('''
                SELECT signer_type, signer_name, signer_email, signed_at, status
                FROM contract_signatures
                WHERE contract_id = %s
                ORDER BY signed_at DESC
            ''', (contract_id,))
            
            signatures = []
            if signatures_result['success']:
                for sig in signatures_result['data']:
                    signatures.append({
                        'signer_type': sig['signer_type'],
                        'signer_name': sig['signer_name'],
                        'signer_email': sig['signer_email'],
                        'signed_at': sig['signed_at'].isoformat() if sig['signed_at'] else None,
                        'status': sig['status']
                    })

            contract_dict = {
                'id': contract['id'],
                'contract_number': contract['contract_number'],
                'template_id': contract['template_id'],
                'template_name': contract['template_name'],
                'customer_data': contract['customer_data'] if contract['customer_data'] else {},
                'contract_data': contract['contract_data'] if contract['contract_data'] else {},
                'status': contract['status'],
                'generated_date': contract['generated_date'].isoformat() if contract['generated_date'] else None,
                'effective_date': contract['effective_date'].isoformat() if contract['effective_date'] else None,
                'expiration_date': contract['expiration_date'].isoformat() if contract['expiration_date'] else None,
                'file_path': contract['file_path'],
                'signed_file_path': contract['signed_file_path'],
                'signatures': signatures
            }

            return jsonify({
                'success': True,
                'data': contract_dict
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Contract not found or access denied'
            }), 404

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to retrieve contract: {str(e)}'
        }), 500

@contract_bp.route('/generated/<contract_id>/download', methods=['GET'])
@token_required
def download_contract(contract_id):
    """Download generated contract file"""
    try:
        user_id = request.current_user.get('user_id')
        user_role = request.current_user.get('role', 'customer')

        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503

        # Get contract with role-based access control
        query = '''
            SELECT gc.id, gc.contract_number, gc.template_id, ct.name as template_name,
                   gc.customer_data, gc.status, gc.generated_date
            FROM generated_contracts gc
            JOIN contract_templates ct ON gc.template_id = ct.id
            WHERE gc.id = %s
        '''
        params = [contract_id]

        if user_role == 'reseller':
            query += ' AND gc.reseller_id = %s'
            params.append(user_id)
        elif user_role == 'customer':
            query += ' AND gc.customer_id IN (SELECT id FROM customers WHERE user_id = %s)'
            params.append(user_id)

        result = execute_query(query, tuple(params), 'one')

        if not result['success'] or not result['data']:
            return jsonify({
                'success': False,
                'error': 'Contract not found or access denied'
            }), 404

        contract = result['data']

        # Log download activity
        execute_query('''
            INSERT INTO contract_activities (contract_id, activity_type, description, performed_by)
            VALUES (%s, %s, %s, %s)
        ''', (
            contract_id,
            'downloaded',
            f'Contract downloaded by user {user_id}',
            user_id
        ))

        # In production, return actual file from storage
        # For demo, create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
            temp_file.write(f"Contract Number: {contract['contract_number']}\n")
            temp_file.write(f"Template: {contract['template_name']}\n")
            temp_file.write(f"Generated: {contract['generated_date']}\n")
            temp_file.write(f"Status: {contract['status']}\n\n")
            temp_file.write("Customer Data:\n")
            customer_data = contract['customer_data'] if contract['customer_data'] else {}
            for key, value in customer_data.items():
                temp_file.write(f"{key}: {value}\n")
            temp_file_path = temp_file.name

        return send_file(
            temp_file_path,
            as_attachment=True,
            download_name=f'contract_{contract["contract_number"]}.txt',
            mimetype='text/plain'
        )

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to download contract: {str(e)}'
        }), 500

@contract_bp.route('/upload-history', methods=['GET'])
@token_required
@role_required('admin')
def get_upload_history():
    """Get file upload history"""
    try:
        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503

        result = execute_query('''
            SELECT ctf.id, ctf.template_id, ct.template_id as template_key, ct.name as template_name,
                   ctf.filename, ctf.original_filename, ctf.file_size, ctf.upload_date, ctf.status
            FROM contract_template_files ctf
            LEFT JOIN contract_templates ct ON ctf.template_id = ct.id
            ORDER BY ctf.upload_date DESC
        ''')

        if result['success']:
            uploads = []
            for upload in result['data']:
                upload_dict = {
                    'id': upload['id'],
                    'template_id': upload['template_key'],
                    'template_name': upload['template_name'],
                    'filename': upload['filename'],
                    'original_filename': upload['original_filename'],
                    'file_size': upload['file_size'],
                    'upload_date': upload['upload_date'].isoformat() if upload['upload_date'] else None,
                    'status': upload['status']
                }
                uploads.append(upload_dict)

            return jsonify({
                'success': True,
                'data': {
                    'uploads': uploads,
                    'total_count': len(uploads)
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to retrieve upload history'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to retrieve upload history: {str(e)}'
        }), 500

@contract_bp.route('/bulk-export', methods=['POST'])
@token_required
def bulk_export_contracts():
    """Export multiple contracts as ZIP file"""
    try:
        data = request.get_json()
        contract_ids = data.get('contract_ids', [])
        user_id = request.current_user.get('user_id')
        user_role = request.current_user.get('role', 'customer')

        if not contract_ids:
            return jsonify({
                'success': False,
                'error': 'No contract IDs provided'
            }), 400

        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503

        # Build query with role-based access control
        placeholders = ','.join(['%s'] * len(contract_ids))
        query = f'''
            SELECT gc.id, gc.contract_number, ct.name as template_name,
                   gc.customer_data, gc.status, gc.generated_date
            FROM generated_contracts gc
            JOIN contract_templates ct ON gc.template_id = ct.id
            WHERE gc.id IN ({placeholders})
        '''
        params = contract_ids[:]

        if user_role == 'reseller':
            query += ' AND gc.reseller_id = %s'
            params.append(user_id)
        elif user_role == 'customer':
            query += ' AND gc.customer_id IN (SELECT id FROM customers WHERE user_id = %s)'
            params.append(user_id)

        result = execute_query(query, tuple(params))

        if not result['success']:
            return jsonify({
                'success': False,
                'error': 'Failed to retrieve contracts'
            }), 500

        contracts = result['data']
        
        # Log bulk export activity
        for contract in contracts:
            execute_query('''
                INSERT INTO contract_activities (contract_id, activity_type, description, performed_by)
                VALUES (%s, %s, %s, %s)
            ''', (
                contract['id'],
                'exported',
                f'Contract included in bulk export by user {user_id}',
                user_id
            ))

        # Create temporary ZIP file
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_zip:
            with zipfile.ZipFile(temp_zip.name, 'w') as zip_file:
                for contract in contracts:
                    # Create contract content
                    content = f"Contract Number: {contract['contract_number']}\n"
                    content += f"Template: {contract['template_name']}\n"
                    content += f"Generated: {contract['generated_date']}\n"
                    content += f"Status: {contract['status']}\n\n"
                    content += "Customer Data:\n"
                    customer_data = contract['customer_data'] if contract['customer_data'] else {}
                    for key, value in customer_data.items():
                        content += f"{key}: {value}\n"

                    # Add to ZIP
                    zip_file.writestr(
                        f'contract_{contract["contract_number"]}.txt', content)

            zip_file_path = temp_zip.name

        return send_file(
            zip_file_path,
            as_attachment=True,
            download_name=f'contracts_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip',
            mimetype='application/zip'
        )

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to export contracts: {str(e)}'
        }), 500

@contract_bp.route('/stats', methods=['GET'])
@token_required
def get_contract_stats():
    """Get contract management statistics"""
    try:
        user_id = request.current_user.get('user_id')
        user_role = request.current_user.get('role', 'customer')

        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503

        # Get template stats
        template_stats_result = execute_query('''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE active = true) as active,
                COUNT(*) FILTER (WHERE active = false) as inactive,
                COUNT(DISTINCT product_type) as product_types
            FROM contract_templates
        ''', (), 'one')

        # Get contract stats with role-based filtering
        contract_query = '''
            SELECT 
                COUNT(*) as total_generated,
                COUNT(*) FILTER (WHERE generated_date >= CURRENT_DATE) as generated_today,
                COUNT(*) FILTER (WHERE status = 'active') as active_contracts,
                COUNT(*) FILTER (WHERE status = 'signed') as signed_contracts
            FROM generated_contracts gc
        '''
        contract_params = []

        if user_role == 'reseller':
            contract_query += ' WHERE gc.reseller_id = %s'
            contract_params.append(user_id)
        elif user_role == 'customer':
            contract_query += ' WHERE gc.customer_id IN (SELECT id FROM customers WHERE user_id = %s)'
            contract_params.append(user_id)

        contract_stats_result = execute_query(contract_query, tuple(contract_params), 'one')

        # Get upload stats (admin/reseller only)
        upload_stats = {'total': 0, 'recent': 0}
        if user_role in ['admin', 'reseller']:
            upload_stats_result = execute_query('''
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE upload_date >= CURRENT_DATE) as recent
                FROM contract_template_files
            ''', (), 'one')
            
            if upload_stats_result['success'] and upload_stats_result['data']:
                upload_stats = {
                    'total': upload_stats_result['data']['total'] or 0,
                    'recent': upload_stats_result['data']['recent'] or 0
                }

        # Get contracts by template
        template_breakdown_query = '''
            SELECT ct.template_id, ct.name, COUNT(gc.id) as contract_count
            FROM contract_templates ct
            LEFT JOIN generated_contracts gc ON ct.id = gc.template_id
        '''
        template_breakdown_params = []

        if user_role == 'reseller':
            template_breakdown_query += ' AND (gc.reseller_id = %s OR gc.reseller_id IS NULL)'
            template_breakdown_params.append(user_id)
        elif user_role == 'customer':
            template_breakdown_query += ' AND (gc.customer_id IN (SELECT id FROM customers WHERE user_id = %s) OR gc.customer_id IS NULL)'
            template_breakdown_params.append(user_id)

        template_breakdown_query += ' GROUP BY ct.template_id, ct.name ORDER BY contract_count DESC'
        
        template_breakdown_result = execute_query(template_breakdown_query, tuple(template_breakdown_params))

        # Build response
        stats = {
            'templates': {
                'total': 0,
                'active': 0,
                'inactive': 0,
                'product_types': 0
            },
            'contracts': {
                'total_generated': 0,
                'generated_today': 0,
                'active_contracts': 0,
                'signed_contracts': 0,
                'by_template': {}
            },
            'uploads': upload_stats
        }

        if template_stats_result['success'] and template_stats_result['data']:
            template_data = template_stats_result['data']
            stats['templates'] = {
                'total': template_data['total'] or 0,
                'active': template_data['active'] or 0,
                'inactive': template_data['inactive'] or 0,
                'product_types': template_data['product_types'] or 0
            }

        if contract_stats_result['success'] and contract_stats_result['data']:
            contract_data = contract_stats_result['data']
            stats['contracts'].update({
                'total_generated': contract_data['total_generated'] or 0,
                'generated_today': contract_data['generated_today'] or 0,
                'active_contracts': contract_data['active_contracts'] or 0,
                'signed_contracts': contract_data['signed_contracts'] or 0
            })

        if template_breakdown_result['success']:
            for row in template_breakdown_result['data']:
                stats['contracts']['by_template'][row['template_id']] = {
                    'name': row['name'],
                    'count': row['contract_count'] or 0
                }

        return jsonify({
            'success': True,
            'data': stats
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to retrieve statistics: {str(e)}'
        }), 500

# Additional endpoints for contract management

@contract_bp.route('/generated/<contract_id>/status', methods=['PUT'])
@token_required
@role_required('admin')
def update_contract_status(contract_id):
    """Update contract status"""
    try:
        data = request.get_json()
        new_status = data.get('status')
        user_id = request.current_user.get('user_id')

        if not new_status:
            return jsonify({
                'success': False,
                'error': 'Status is required'
            }), 400

        valid_statuses = ['draft', 'generated', 'sent', 'signed', 'active', 'cancelled', 'expired']
        if new_status not in valid_statuses:
            return jsonify({
                'success': False,
                'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
            }), 400

        db_manager = get_db_manager()
        if not db_manager.available:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503

        # Update contract status
        result = execute_query('''
            UPDATE generated_contracts 
            SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, contract_number, status
        ''', (new_status, contract_id), 'one')

        if result['success'] and result['data']:
            # Log activity
            execute_query('''
                INSERT INTO contract_activities (contract_id, activity_type, description, performed_by)
                VALUES (%s, %s, %s, %s)
            ''', (
                contract_id,
                'status_changed',
                f'Status changed to {new_status}',
                user_id
            ))

            contract = result['data']
            return jsonify({
                'success': True,
                'data': {
                    'id': contract['id'],
                    'contract_number': contract['contract_number'],
                    'status': contract['status']
                },
                'message': f'Contract status updated to {new_status}'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Contract not found'
            }), 404

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to update contract status: {str(e)}'
        }), 500

# Error handlers
@contract_bp.errorhandler(413)
def file_too_large(error):
    return jsonify({
        'success': False,
        'error': 'File too large. Maximum file size is 10MB.'
    }), 413

@contract_bp.errorhandler(400)
def bad_request(error):
    return jsonify({
        'success': False,
        'error': 'Bad request. Please check your input data.'
    }), 400
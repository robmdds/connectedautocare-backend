#!/usr/bin/env python3
"""
ConnectedAutoCare.com - Contract Management API
Handles contract templates, document uploads, and automated contract generation
"""

import os
import json
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file
from werkzeug.utils import secure_filename
import tempfile
import zipfile

# Create blueprint for contract management
contract_bp = Blueprint('contract_management', __name__)

# Mock database - in production, use a real database
CONTRACTS_DB = {
    'templates': {
        'vsc_silver': {
            'id': 'vsc_silver',
            'name': 'VSC Silver Coverage Contract',
            'product_type': 'vsc',
            'product_id': 'silver',
            'template_file': 'vsc_silver_template.pdf',
            'fields': [
                {'name': 'customer_name', 'type': 'text', 'required': True},
                {'name': 'customer_address', 'type': 'text', 'required': True},
                {'name': 'vehicle_vin', 'type': 'text', 'required': True},
                {'name': 'vehicle_year', 'type': 'number', 'required': True},
                {'name': 'vehicle_make', 'type': 'text', 'required': True},
                {'name': 'vehicle_model', 'type': 'text', 'required': True},
                {'name': 'coverage_term', 'type': 'number', 'required': True},
                {'name': 'deductible_amount', 'type': 'number', 'required': True},
                {'name': 'contract_price', 'type': 'currency', 'required': True},
                {'name': 'effective_date', 'type': 'date', 'required': True}
            ],
            'active': True,
            'created_date': '2024-01-15',
            'updated_date': '2024-01-15'
        },
        'home_protection': {
            'id': 'home_protection',
            'name': 'Home Protection Plan Contract',
            'product_type': 'hero',
            'product_id': 'home_protection',
            'template_file': 'home_protection_template.pdf',
            'fields': [
                {'name': 'customer_name', 'type': 'text', 'required': True},
                {'name': 'customer_address', 'type': 'text', 'required': True},
                {'name': 'property_address', 'type': 'text', 'required': True},
                {'name': 'coverage_term', 'type': 'number', 'required': True},
                {'name': 'contract_price', 'type': 'currency', 'required': True},
                {'name': 'effective_date', 'type': 'date', 'required': True},
                {'name': 'coverage_limits', 'type': 'text', 'required': True}
            ],
            'active': True,
            'created_date': '2024-01-15',
            'updated_date': '2024-01-15'
        }
    },
    'generated_contracts': {},
    'upload_history': []
}


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
def get_contract_templates():
    """Get all contract templates"""
    try:
        templates = list(CONTRACTS_DB['templates'].values())

        return jsonify({
            'success': True,
            'data': {
                'templates': templates,
                'total_count': len(templates)
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to retrieve templates: {str(e)}'
        }), 500


@contract_bp.route('/templates/<template_id>', methods=['GET'])
def get_contract_template(template_id):
    """Get specific contract template"""
    try:
        template = CONTRACTS_DB['templates'].get(template_id)

        if not template:
            return jsonify({
                'success': False,
                'error': 'Template not found'
            }), 404

        return jsonify({
            'success': True,
            'data': template
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to retrieve template: {str(e)}'
        }), 500


@contract_bp.route('/templates', methods=['POST'])
def create_contract_template():
    """Create new contract template"""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['name', 'product_type', 'product_id', 'fields']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400

        # Generate template ID
        template_id = data.get(
            'id') or f"{data['product_type']}_{data['product_id']}"

        # Check if template already exists
        if template_id in CONTRACTS_DB['templates']:
            return jsonify({
                'success': False,
                'error': 'Template with this ID already exists'
            }), 409

        # Create template
        template = {
            'id': template_id,
            'name': data['name'],
            'product_type': data['product_type'],
            'product_id': data['product_id'],
            'template_file': data.get('template_file', ''),
            'fields': data['fields'],
            'active': data.get('active', True),
            'created_date': datetime.now().strftime('%Y-%m-%d'),
            'updated_date': datetime.now().strftime('%Y-%m-%d')
        }

        CONTRACTS_DB['templates'][template_id] = template

        return jsonify({
            'success': True,
            'data': template,
            'message': 'Contract template created successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to create template: {str(e)}'
        }), 500


@contract_bp.route('/templates/<template_id>', methods=['PUT'])
def update_contract_template(template_id):
    """Update contract template"""
    try:
        if template_id not in CONTRACTS_DB['templates']:
            return jsonify({
                'success': False,
                'error': 'Template not found'
            }), 404

        data = request.get_json()
        template = CONTRACTS_DB['templates'][template_id]

        # Update fields
        updatable_fields = ['name', 'fields', 'active', 'template_file']
        for field in updatable_fields:
            if field in data:
                template[field] = data[field]

        template['updated_date'] = datetime.now().strftime('%Y-%m-%d')

        return jsonify({
            'success': True,
            'data': template,
            'message': 'Contract template updated successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to update template: {str(e)}'
        }), 500


@contract_bp.route('/templates/<template_id>', methods=['DELETE'])
def delete_contract_template(template_id):
    """Delete contract template"""
    try:
        if template_id not in CONTRACTS_DB['templates']:
            return jsonify({
                'success': False,
                'error': 'Template not found'
            }), 404

        # Remove template
        deleted_template = CONTRACTS_DB['templates'].pop(template_id)

        return jsonify({
            'success': True,
            'message': f'Template {template_id} deleted successfully',
            'deleted_template': deleted_template
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to delete template: {str(e)}'
        }), 500


@contract_bp.route('/templates/<template_id>/toggle-status', methods=['POST'])
def toggle_template_status(template_id):
    """Toggle template active status"""
    try:
        if template_id not in CONTRACTS_DB['templates']:
            return jsonify({
                'success': False,
                'error': 'Template not found'
            }), 404

        template = CONTRACTS_DB['templates'][template_id]
        template['active'] = not template['active']
        template['updated_date'] = datetime.now().strftime('%Y-%m-%d')

        return jsonify({
            'success': True,
            'data': template,
            'message': f'Template {"activated" if template["active"] else "deactivated"} successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to toggle template status: {str(e)}'
        }), 500


@contract_bp.route('/upload-template', methods=['POST'])
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

        # Secure filename
        filename = secure_filename(file.filename)

        # In production, save to cloud storage or secure file system
        # For demo, we'll just record the upload
        upload_record = {
            'id': str(uuid.uuid4()),
            'template_id': template_id,
            'filename': filename,
            'original_filename': file.filename,
            'file_size': len(file.read()),
            'upload_date': datetime.now().isoformat(),
            'status': 'uploaded'
        }

        CONTRACTS_DB['upload_history'].append(upload_record)

        # Update template if template_id provided
        if template_id and template_id in CONTRACTS_DB['templates']:
            CONTRACTS_DB['templates'][template_id]['template_file'] = filename
            CONTRACTS_DB['templates'][template_id]['updated_date'] = datetime.now(
            ).strftime('%Y-%m-%d')

        return jsonify({
            'success': True,
            'data': upload_record,
            'message': 'Template file uploaded successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to upload file: {str(e)}'
        }), 500


@contract_bp.route('/generate', methods=['POST'])
def generate_contract():
    """Generate contract from template with customer data"""
    try:
        data = request.get_json()

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

        # Get template
        template = CONTRACTS_DB['templates'].get(template_id)
        if not template:
            return jsonify({
                'success': False,
                'error': 'Template not found'
            }), 404

        if not template['active']:
            return jsonify({
                'success': False,
                'error': 'Template is not active'
            }), 400

        # Validate customer data against template fields
        missing_fields = []
        for field in template['fields']:
            if field['required'] and field['name'] not in customer_data:
                missing_fields.append(field['name'])

        if missing_fields:
            return jsonify({
                'success': False,
                'error': f'Missing required customer data: {", ".join(missing_fields)}'
            }), 400

        # Generate contract
        contract_id = str(uuid.uuid4())
        contract = {
            'id': contract_id,
            'template_id': template_id,
            'template_name': template['name'],
            'customer_data': customer_data,
            'generated_date': datetime.now().isoformat(),
            'status': 'generated',
            'file_path': f'contracts/{contract_id}.pdf'
        }

        CONTRACTS_DB['generated_contracts'][contract_id] = contract

        return jsonify({
            'success': True,
            'data': contract,
            'message': 'Contract generated successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to generate contract: {str(e)}'
        }), 500


@contract_bp.route('/generated', methods=['GET'])
def get_generated_contracts():
    """Get all generated contracts"""
    try:
        contracts = list(CONTRACTS_DB['generated_contracts'].values())

        # Sort by generated date (newest first)
        contracts.sort(key=lambda x: x['generated_date'], reverse=True)

        return jsonify({
            'success': True,
            'data': {
                'contracts': contracts,
                'total_count': len(contracts)
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to retrieve contracts: {str(e)}'
        }), 500


@contract_bp.route('/generated/<contract_id>', methods=['GET'])
def get_generated_contract(contract_id):
    """Get specific generated contract"""
    try:
        contract = CONTRACTS_DB['generated_contracts'].get(contract_id)

        if not contract:
            return jsonify({
                'success': False,
                'error': 'Contract not found'
            }), 404

        return jsonify({
            'success': True,
            'data': contract
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to retrieve contract: {str(e)}'
        }), 500


@contract_bp.route('/generated/<contract_id>/download', methods=['GET'])
def download_contract(contract_id):
    """Download generated contract file"""
    try:
        contract = CONTRACTS_DB['generated_contracts'].get(contract_id)

        if not contract:
            return jsonify({
                'success': False,
                'error': 'Contract not found'
            }), 404

        # In production, return actual file from storage
        # For demo, create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
            temp_file.write(f"Contract ID: {contract_id}\n")
            temp_file.write(f"Template: {contract['template_name']}\n")
            temp_file.write(f"Generated: {contract['generated_date']}\n\n")
            temp_file.write("Customer Data:\n")
            for key, value in contract['customer_data'].items():
                temp_file.write(f"{key}: {value}\n")
            temp_file_path = temp_file.name

        return send_file(
            temp_file_path,
            as_attachment=True,
            download_name=f'contract_{contract_id}.txt',
            mimetype='text/plain'
        )
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to download contract: {str(e)}'
        }), 500


@contract_bp.route('/upload-history', methods=['GET'])
def get_upload_history():
    """Get file upload history"""
    try:
        history = CONTRACTS_DB['upload_history']

        # Sort by upload date (newest first)
        history.sort(key=lambda x: x['upload_date'], reverse=True)

        return jsonify({
            'success': True,
            'data': {
                'uploads': history,
                'total_count': len(history)
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to retrieve upload history: {str(e)}'
        }), 500


@contract_bp.route('/bulk-export', methods=['POST'])
def bulk_export_contracts():
    """Export multiple contracts as ZIP file"""
    try:
        data = request.get_json()
        contract_ids = data.get('contract_ids', [])

        if not contract_ids:
            return jsonify({
                'success': False,
                'error': 'No contract IDs provided'
            }), 400

        # Create temporary ZIP file
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_zip:
            with zipfile.ZipFile(temp_zip.name, 'w') as zip_file:
                for contract_id in contract_ids:
                    contract = CONTRACTS_DB['generated_contracts'].get(
                        contract_id)
                    if contract:
                        # Create contract content
                        content = f"Contract ID: {contract_id}\n"
                        content += f"Template: {contract['template_name']}\n"
                        content += f"Generated: {contract['generated_date']}\n\n"
                        content += "Customer Data:\n"
                        for key, value in contract['customer_data'].items():
                            content += f"{key}: {value}\n"

                        # Add to ZIP
                        zip_file.writestr(
                            f'contract_{contract_id}.txt', content)

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
def get_contract_stats():
    """Get contract management statistics"""
    try:
        templates = CONTRACTS_DB['templates']
        contracts = CONTRACTS_DB['generated_contracts']
        uploads = CONTRACTS_DB['upload_history']

        # Calculate statistics
        stats = {
            'templates': {
                'total': len(templates),
                'active': len([t for t in templates.values() if t.get('active', True)]),
                'inactive': len([t for t in templates.values() if not t.get('active', True)])
            },
            'contracts': {
                'total_generated': len(contracts),
                'generated_today': len([c for c in contracts.values()
                                        if c['generated_date'].startswith(datetime.now().strftime('%Y-%m-%d'))]),
                'by_template': {}
            },
            'uploads': {
                'total': len(uploads),
                'recent': len([u for u in uploads
                               if u['upload_date'].startswith(datetime.now().strftime('%Y-%m-%d'))])
            }
        }

        # Count contracts by template
        for contract in contracts.values():
            template_id = contract.get('template_id')
            if template_id:
                if template_id not in stats['contracts']['by_template']:
                    stats['contracts']['by_template'][template_id] = 0
                stats['contracts']['by_template'][template_id] += 1

        return jsonify({
            'success': True,
            'data': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to retrieve statistics: {str(e)}'
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

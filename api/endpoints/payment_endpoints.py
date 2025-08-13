"""
Payment Processing Endpoints
Helcim integration, financing, and payment management
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timezone, timedelta
import json
import time
from auth.user_auth import token_required

# Initialize blueprint
payment_bp = Blueprint('payment', __name__)

# Import payment services with error handling
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from config.app_config import AppConfig
    config = AppConfig()
    DATABASE_URL = config.DATABASE_URL
    PAYMENT_SERVICE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Payment service dependencies not available: {e}")
    PAYMENT_SERVICE_AVAILABLE = False
    DATABASE_URL = None

@payment_bp.route('/methods')
def get_payment_methods():
    """Get available payment methods"""
    return jsonify({
        "credit_card": {
            "enabled": True,
            "providers": ["Helcim"],
            "accepted_cards": ["Visa", "MasterCard", "American Express", "Discover"],
            "features": ["tokenization", "real_time_processing", "secure_checkout"]
        },
        "financing": {
            "enabled": True,
            "provider": "Supplemental Payment Program",
            "terms": ["0% for 12 months", "0% for 24 months"],
            "features": ["instant_approval", "no_fees", "automatic_payments"]
        },
        "payment_security": {
            "pci_compliant": True,
            "encryption": "AES-256",
            "tokenization": True,
            "fraud_protection": True
        }
    })


@payment_bp.route('/process', methods=['POST'])
def process_payment():
    """Updated payment processing with HelcimJS integration"""
    if not PAYMENT_SERVICE_AVAILABLE:
        return jsonify({"error": "Payment processing service not available"}), 503

    try:
        data = request.get_json()

        # Check if this is a transaction save request (after HelcimJS success)
        if data.get('action') == 'save_transaction':
            return save_helcim_transaction(data.get('transaction_data', {}))

        # Original payment processing for financing and other methods
        required_fields = ['amount', 'customer_info', 'payment_method']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400

        payment_method = data['payment_method']
        amount = float(data['amount'])
        customer_info = data['customer_info']

        # For credit card payments, redirect to HelcimJS
        if payment_method == 'credit_card':
            return jsonify({
                'success': False,
                'error': 'Credit card payments must be processed through HelcimJS on the frontend',
                'redirect_to_helcim': True
            }), 400

        # Get client IP address
        client_ip = request.headers.get('X-Forwarded-For',
                                        request.headers.get('X-Real-IP',
                                                            request.remote_addr))
        if not client_ip or client_ip == '127.0.0.1':
            client_ip = '192.168.1.1'  # Default for testing

        # Generate transaction number
        quote_id = data.get('quote_id', f'QUOTE-{int(time.time())}')
        transaction_number = f"TXN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{quote_id.split('-')[-1]}"

        # Prepare enhanced payment data
        enhanced_data = {
            **data,
            'ip_address': client_ip,
            'currency': data.get('currency', 'USD'),
            'customer_id': f"CUST-{customer_info.get('email', '').replace('@', '-').replace('.', '-')}",
            'transaction_number': transaction_number,
            'description': f"ConnectedAutoCare - {data.get('payment_details', {}).get('product_type', 'Protection Plan')}"
        }

        # Create initial transaction record
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                           INSERT INTO transactions (transaction_number, customer_id, type, amount,
                                                     currency, status, payment_method, metadata, created_by)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
                           ''', (
                               transaction_number,
                               enhanced_data.get('customer_id'),
                               'payment',
                               amount,
                               enhanced_data.get('currency', 'USD'),
                               'processing',
                               json.dumps({
                                   'method': payment_method,
                                   'quote_id': quote_id,
                                   **data.get('payment_details', {})
                               }),
                               json.dumps({
                                   'quote_id': quote_id,
                                   'payment_method': payment_method,
                                   'initiated_at': datetime.now(timezone.utc).isoformat(),
                                   'ip_address': client_ip
                               }),
                               data.get('user_id')
                           ))

            transaction_id = cursor.fetchone()[0]

            # Process payment based on method (only financing supported here)
            if payment_method == 'financing':
                payment_result = setup_financing_plan(enhanced_data, amount, transaction_number)
            else:
                cursor.execute('''
                               UPDATE transactions
                               SET status             = 'failed',
                                   processor_response = %s
                               WHERE id = %s;
                               ''', (json.dumps({'error': 'Invalid payment method'}), transaction_id))
                conn.commit()
                cursor.close()
                conn.close()
                return jsonify({
                    'success': False,
                    'error': f'Unsupported payment method: {payment_method}'
                }), 400

            # Update transaction with payment result
            if payment_result['success']:
                cursor.execute('''
                               UPDATE transactions
                               SET status             = %s,
                                   processed_at       = CURRENT_TIMESTAMP,
                                   processor_response = %s,
                                   fees               = %s,
                                   taxes              = %s
                               WHERE id = %s;
                               ''', (
                                   payment_result['status'],
                                   json.dumps(payment_result.get('processor_data', {})),
                                   json.dumps(payment_result.get('fees', {})),
                                   json.dumps(payment_result.get('taxes', {})),
                                   transaction_id
                               ))

                conn.commit()
                cursor.close()
                conn.close()

                return jsonify({
                    'success': True,
                    'data': {
                        'transaction_id': str(transaction_id),
                        'transaction_number': transaction_number,
                        'status': payment_result['status'],
                        'processor_transaction_id': payment_result.get('processor_transaction_id'),
                        'confirmation_number': f"CAC-{transaction_number}",
                        'amount': amount,
                        'currency': enhanced_data.get('currency', 'USD'),
                        'next_steps': payment_result.get('next_steps', []),
                        'contract_generation': {
                            'will_generate': True,
                            'estimated_time': '2-3 business days'
                        }
                    }
                })
            else:
                # Payment failed
                cursor.execute('''
                               UPDATE transactions
                               SET status             = 'failed',
                                   processor_response = %s
                               WHERE id = %s;
                               ''', (json.dumps({'error': payment_result.get('error')}), transaction_id))
                conn.commit()
                cursor.close()
                conn.close()

                return jsonify({
                    'success': False,
                    'error': payment_result.get('error', 'Payment processing failed'),
                    'details': payment_result.get('processor_data', {}),
                    'solution': payment_result.get('solution', 'Please check your payment information and try again.')
                }), 400

        except Exception as db_error:
            conn.rollback()
            cursor.close()
            conn.close()
            raise db_error

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Payment processing failed: {str(e)}'
        }), 500


def save_helcim_transaction(transaction_data):
    """Save HelcimJS transaction data to database after successful payment"""
    try:
        # Extract data from HelcimJS response
        helcim_response = transaction_data.get('helcim_response', {})
        quote_data = transaction_data.get('quote_data', {})
        customer_info = transaction_data.get('customer_info', {})
        billing_info = transaction_data.get('billing_info', {})
        amount = float(transaction_data.get('amount', 0))

        # Validate required data
        if not helcim_response:
            return jsonify({
                'success': False,
                'error': 'HelcimJS response data required'
            }), 400

        if not customer_info.get('email'):
            return jsonify({
                'success': False,
                'error': 'Customer email required'
            }), 400

        if amount <= 0:
            return jsonify({
                'success': False,
                'error': 'Invalid transaction amount'
            }), 400

        # Generate transaction identifiers
        quote_id = quote_data.get('quote_id', f'QUOTE-{int(time.time())}')
        transaction_number = f"TXN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{quote_id.split('-')[-1]}"

        # Extract key information from HelcimJS response
        processor_transaction_id = (
                helcim_response.get('transactionId') or
                helcim_response.get('cardBatchId') or
                helcim_response.get('id') or
                f"HELCIM-{int(time.time())}"
        )

        payment_status = 'approved' if helcim_response.get('approved') else 'completed'

        # Get client IP address
        client_ip = request.headers.get('X-Forwarded-For',
                                        request.headers.get('X-Real-IP',
                                                            request.remote_addr))
        if not client_ip or client_ip == '127.0.0.1':
            client_ip = '192.168.1.1'

        # Connect to database
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        try:
            # First, find or create customer using email
            customer_email = customer_info.get('email', '')

            # Check if customer exists by email
            cursor.execute('''
                           SELECT id
                           FROM customers
                           WHERE contact_info ->>'email' = %s
                               LIMIT 1;
                           ''', (customer_email,))

            existing_customer = cursor.fetchone()

            if existing_customer:
                customer_id = existing_customer[0]

                # Update existing customer info
                cursor.execute('''
                               UPDATE customers
                               SET personal_info = personal_info || %s,
                                   contact_info  = contact_info || %s,
                                   billing_info  = %s,
                                   updated_at    = CURRENT_TIMESTAMP,
                                   last_activity = CURRENT_TIMESTAMP
                               WHERE id = %s;
                               ''', (
                                   json.dumps({
                                       'first_name': customer_info.get('first_name', ''),
                                       'last_name': customer_info.get('last_name', '')
                                   }),
                                   json.dumps({
                                       'email': customer_email,
                                       'phone': customer_info.get('phone', '')
                                   }),
                                   json.dumps(billing_info),
                                   customer_id
                               ))
            else:
                # Create new customer
                cursor.execute('''
                               INSERT INTO customers (customer_type, personal_info, contact_info, billing_info,
                                                      created_at, updated_at, last_activity, status)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
                               ''', (
                                   'individual',  # or determine from customer_info if available
                                   json.dumps({
                                       'first_name': customer_info.get('first_name', ''),
                                       'last_name': customer_info.get('last_name', ''),
                                       'company': customer_info.get('company', '')
                                   }),
                                   json.dumps({
                                       'email': customer_email,
                                       'phone': customer_info.get('phone', '')
                                   }),
                                   json.dumps(billing_info),
                                   datetime.now(timezone.utc),
                                   datetime.now(timezone.utc),
                                   datetime.now(timezone.utc),
                                   'active'
                               ))

                customer_id = cursor.fetchone()[0]

            # Now insert transaction record using the UUID customer_id
            cursor.execute('''
                           INSERT INTO transactions (transaction_number, customer_id, type, amount,
                                                     currency, status, payment_method, metadata,
                                                     processed_at, processor_response, created_by)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
                           ''', (
                               transaction_number,
                               customer_id,  # Now using the actual UUID from customers table
                               'payment',
                               amount,
                               transaction_data.get('currency', 'USD'),
                               payment_status,
                               json.dumps({
                                   'method': 'credit_card',
                                   'processor': 'helcim',
                                   'quote_id': quote_id,
                                   'processor_transaction_id': processor_transaction_id
                               }),
                               json.dumps({
                                   'quote_id': quote_id,
                                   'quote_data': quote_data,
                                   'customer_info': customer_info,
                                   'billing_info': billing_info,
                                   'payment_method': 'credit_card',
                                   'product_type': transaction_data.get('product_type', 'unknown'),
                                   'vehicle_info': transaction_data.get('vehicle_info'),
                                   'processed_at': datetime.now(timezone.utc).isoformat(),
                                   'ip_address': client_ip,
                                   'user_agent': request.headers.get('User-Agent', '')
                               }),
                               datetime.now(timezone.utc),
                               json.dumps({
                                   'helcim_response': helcim_response,
                                   'processor': 'helcim',
                                   'transaction_id': processor_transaction_id,
                                   'success': True,
                                   'payment_date': datetime.now(timezone.utc).isoformat()
                               }),
                               transaction_data.get('user_id')
                           ))

            transaction_id = cursor.fetchone()[0]

            # Create protection plan record if quote data exists
            protection_plan_result = None
            if quote_data:
                protection_plan_result = create_protection_plan_record(
                    cursor, transaction_id, quote_data, customer_id,  # Pass customer_id UUID
                    transaction_data.get('vehicle_info')
                )

            # Commit all changes
            conn.commit()
            cursor.close()
            conn.close()

            # Return success response
            return jsonify({
                'success': True,
                'data': {
                    'transaction_id': str(transaction_id),
                    'transaction_number': transaction_number,
                    'confirmation_number': f"CAC-{transaction_number}",
                    'processor_transaction_id': processor_transaction_id,
                    'status': payment_status,
                    'amount': amount,
                    'currency': transaction_data.get('currency', 'USD'),
                    'customer_id': str(customer_id),
                    'next_steps': [
                        'Payment has been processed successfully',
                        'You will receive a confirmation email shortly',
                        'Your protection plan is now active',
                        'Contract documents will be generated within 2-3 business days'
                    ],
                    'contract_generation': {
                        'will_generate': True,
                        'estimated_time': '2-3 business days',
                        'protection_plan_id': protection_plan_result['plan_id'] if protection_plan_result else None,
                        'protection_plan_db_id': str(
                            protection_plan_result['db_id']) if protection_plan_result else None
                    }
                }
            })

        except Exception as db_error:
            conn.rollback()
            cursor.close()
            conn.close()
            raise db_error

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to save transaction: {str(e)}'
        }), 500


def create_protection_plan_record(cursor, transaction_id, quote_data, customer_id, vehicle_info):
    """Create a protection plan record linked to the transaction"""
    try:
        # Generate protection plan ID
        plan_id = f"PLAN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{transaction_id}"

        # Determine plan type and details
        coverage_details = quote_data.get('coverage_details', {})
        product_info = quote_data.get('product_info', {})

        plan_type = 'vsc' if vehicle_info else 'hero'
        plan_name = coverage_details.get('coverage_level', product_info.get('product_type', 'Protection Plan'))

        # Calculate plan dates
        start_date = datetime.now(timezone.utc).date()

        # Determine end date based on plan type
        if plan_type == 'vsc':
            term_months = coverage_details.get('term_months', product_info.get('term_months', 12))
            if isinstance(term_months, str):
                term_months = int(term_months)
            end_date = start_date + timedelta(days=term_months * 30)
        else:
            term_years = coverage_details.get('term_years', product_info.get('term_years', 1))
            if isinstance(term_years, str):
                term_years = int(term_years)
            end_date = start_date + timedelta(days=term_years * 365)

        # Insert protection plan record
        cursor.execute('''
                       INSERT INTO protection_plans (plan_id, transaction_id, customer_id, plan_type,
                                                     plan_name, coverage_details, vehicle_info,
                                                     start_date, end_date, status, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
                       ''', (
                           plan_id,
                           transaction_id,
                           customer_id,  # Using UUID customer_id instead of customer_email
                           plan_type,
                           plan_name,
                           json.dumps({
                               **coverage_details,
                               **product_info,
                               'quote_data': quote_data
                           }),
                           json.dumps(vehicle_info) if vehicle_info else None,
                           start_date,
                           end_date,
                           'active',
                           datetime.now(timezone.utc)
                       ))

        protection_plan_db_id = cursor.fetchone()[0]

        return {
            'plan_id': plan_id,
            'db_id': protection_plan_db_id,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat()
        }

    except Exception as e:
        print(f"Error creating protection plan record: {str(e)}")
        return None

def setup_financing_plan(data, amount, transaction_number):
    """Setup financing plan via Supplemental Payment Program"""
    try:
        financing_terms = data.get('financing_terms', '12')  # months
        customer_info = data.get('customer_info', {})
        
        # Validate customer info for financing
        required_fields = ['first_name', 'last_name', 'email', 'phone', 'ssn_last_4']
        missing_fields = [field for field in required_fields if not customer_info.get(field)]
        if missing_fields:
            return {'success': False, 'error': f"Missing customer info: {', '.join(missing_fields)}"}
        
        # Calculate monthly payment
        if financing_terms in ['12', '24']:
            # 0% APR for 12 and 24 months
            monthly_payment = round(amount / int(financing_terms), 2)
            total_amount = amount
        else:
            return {'success': False, 'error': 'Invalid financing terms'}
        
        # Simulate financing approval
        financing_id = f"FIN-{transaction_number}"
        
        return {
            'success': True,
            'status': 'financing_approved',
            'processor_transaction_id': financing_id,
            'processor_data': {
                'provider': 'Supplemental Payment Program',
                'financing_id': financing_id,
                'monthly_payment': monthly_payment,
                'total_amount': total_amount,
                'terms': f"{financing_terms} months at 0% APR",
                'first_payment_due': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
            },
            'fees': {
                'origination_fee': 0.00,  # No fees for 0% APR
                'total_fees': 0.00
            },
            'taxes': {
                'sales_tax': round(amount * 0.07, 2),
                'tax_rate': 0.07
            },
            'next_steps': [
                'Financing application approved',
                f'First payment of ${monthly_payment} due in 30 days',
                'Contract and payment schedule will be sent via email',
                'Setup automatic payments in customer portal'
            ]
        }
        
    except Exception as e:
        return {'success': False, 'error': f'Financing setup failed: {str(e)}'}

@payment_bp.route('/<transaction_id>/status', methods=['GET'])
def get_payment_status(transaction_id):
    """Get payment status and details from transactions table"""
    if not PAYMENT_SERVICE_AVAILABLE:
        return jsonify({"error": "Payment service not available"}), 503
        
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('''
            SELECT 
                t.id,
                t.transaction_number,
                t.customer_id,
                t.policy_id,
                t.type,
                t.amount,
                t.currency,
                t.status,
                t.payment_method,
                t.processor_response,
                t.created_at,
                t.processed_at,
                t.metadata,
                t.fees,
                t.taxes,
                c.first_name,
                c.last_name,
                c.email,
                p.policy_number,
                p.product_type
            FROM transactions t
            LEFT JOIN customers c ON t.customer_id = c.id
            LEFT JOIN policies p ON t.policy_id = p.id
            WHERE t.id = %s OR t.transaction_number = %s;
        ''', (transaction_id, transaction_id))
        
        transaction = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not transaction:
            return jsonify('Transaction not found'), 404
        
        # Convert to proper format
        transaction_dict = dict(transaction)
        transaction_dict['amount'] = float(transaction_dict['amount'])
        transaction_dict['created_at'] = transaction_dict['created_at'].isoformat() if transaction_dict['created_at'] else None
        transaction_dict['processed_at'] = transaction_dict['processed_at'].isoformat() if transaction_dict['processed_at'] else None
        
        # Parse JSON fields
        for json_field in ['payment_method', 'processor_response', 'metadata', 'fees', 'taxes']:
            if transaction_dict[json_field]:
                transaction_dict[json_field] = transaction_dict[json_field]
            else:
                transaction_dict[json_field] = {}
        
        return jsonify(transaction_dict)
        
    except Exception as e:
        return jsonify(f"Failed to get payment status: {str(e)}"), 500

@payment_bp.route('/history', methods=['GET'])
@token_required
def get_payment_history():
    """Get payment history for logged-in user"""
    if not PAYMENT_SERVICE_AVAILABLE:
        return jsonify({"error": "Payment service not available"}), 503
        
    try:
        user_id = request.current_user.get('user_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status_filter = request.args.get('status')
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Build WHERE clause
        where_conditions = []
        params = []
        
        # Filter by user's customer record
        cursor.execute('SELECT id FROM customers WHERE user_id = %s;', (user_id,))
        customer_record = cursor.fetchone()
        
        if customer_record:
            where_conditions.append('t.customer_id = %s')
            params.append(customer_record['id'])
        else:
            # If no customer record, show transactions created by this user
            where_conditions.append('t.created_by = %s')
            params.append(user_id)
        
        if status_filter:
            where_conditions.append('t.status = %s')
            params.append(status_filter)
        
        where_clause = ' AND '.join(where_conditions) if where_conditions else 'TRUE'
        
        # Get total count
        cursor.execute(f'''
            SELECT COUNT(*) 
            FROM transactions t 
            WHERE {where_clause};
        ''', params)
        total_count = cursor.fetchone()['count']
        
        # Get paginated results
        offset = (page - 1) * per_page
        cursor.execute(f'''
            SELECT 
                t.id,
                t.transaction_number,
                t.amount,
                t.currency,
                t.status,
                t.payment_method,
                t.created_at,
                t.processed_at,
                t.metadata,
                p.policy_number,
                p.product_type
            FROM transactions t
            LEFT JOIN policies p ON t.policy_id = p.id
            WHERE {where_clause}
            ORDER BY t.created_at DESC
            LIMIT %s OFFSET %s;
        ''', params + [per_page, offset])
        
        transactions = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Convert to proper format
        transactions_list = []
        for txn in transactions:
            txn_dict = dict(txn)
            txn_dict['amount'] = float(txn_dict['amount'])
            txn_dict['created_at'] = txn_dict['created_at'].isoformat() if txn_dict['created_at'] else None
            txn_dict['processed_at'] = txn_dict['processed_at'].isoformat() if txn_dict['processed_at'] else None
            
            # Parse payment_method and metadata
            if txn_dict['payment_method']:
                txn_dict['payment_method'] = txn_dict['payment_method']
            else:
                txn_dict['payment_method'] = {}
                
            if txn_dict['metadata']:
                txn_dict['metadata'] = txn_dict['metadata']
            else:
                txn_dict['metadata'] = {}
            
            transactions_list.append(txn_dict)
        
        return jsonify({
            'transactions': transactions_list,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_count,
                'pages': (total_count + per_page - 1) // per_page
            }
        })
        
    except Exception as e:
        return jsonify(f"Failed to get payment history: {str(e)}"), 500

@payment_bp.route('/create-helcim-session', methods=['POST'])
def create_helcim_payment_session():
    """Create HelcimPay.js checkout session - enhanced for verify type with proper province handling"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('amount'):
            return jsonify({
                'success': False,
                'error': 'Amount is required'
            }), 400
        
        try:
            from helcim_integration import HelcimPaymentProcessor, CustomerInfo, Address, Currency
            processor = HelcimPaymentProcessor()
        except ImportError:
            return jsonify({
                'success': False,
                'error': 'Helcim integration not available'
            }), 503
        
        # Parse customer information
        customer_info_data = data.get('customer_info', {})
        
        # Create Address object if needed with proper province handling
        billing_address = None
        if customer_info_data.get('address'):
            province_input = customer_info_data.get('state', '')
            
            print(f"🔍 Original province/state input: '{province_input}'")
            
            billing_address = Address(
                street1=customer_info_data.get('address', ''),
                city=customer_info_data.get('city', ''),
                province=province_input,
                postal_code=customer_info_data.get('zip_code', ''),
                country='USA'
            )
            
            print(f"✅ Normalized province for Helcim Customer API: '{billing_address.province}'")
        
        # Create CustomerInfo object
        customer_info = CustomerInfo(
            contact_name=f"{customer_info_data.get('first_name', 'Guest')} {customer_info_data.get('last_name', 'Customer')}",
            business_name=customer_info_data.get('business_name', f"Customer-{int(time.time())}"),
            email=customer_info_data.get('email'),
            phone=customer_info_data.get('phone'),
            billing_address=billing_address
        )
        
        # Parse currency
        currency_str = data.get('currency', 'USD').upper()
        try:
            currency = Currency(currency_str)
        except ValueError:
            return jsonify({
                'success': False,
                'error': f'Unsupported currency: {currency_str}'
            }), 400
        
        # Check payment type to determine flow
        payment_type = data.get('payment_type', 'purchase')
        
        if payment_type == 'verify':
            # FOR VERIFY (TOKENIZATION) - Create customer and minimal session
            print(f"🔍 Creating VERIFY session for tokenization...")
            
            customer_result = processor.create_customer(customer_info)
            if not customer_result['success']:
                return jsonify({
                    'success': False,
                    'error': f'Failed to create customer: {customer_result.get("error", "Unknown error")}'
                }), 400
            
            customer_id = customer_result['customer_id']
            print(f"✅ Customer created successfully: {customer_id}")
            
            verify_session_result = processor.create_helcimpay_checkout_session(
                amount=float(data['amount']),
                currency=currency,
                customer_id=customer_id,
                payment_type='verify'
            )
            
            if verify_session_result['success']:
                print(f"✅ Verify session created: {verify_session_result.get('checkout_token')}")
                return jsonify({
                    'success': True,
                    'data': {
                        'checkoutToken': verify_session_result.get('checkout_token'),
                        'customerId': customer_id,
                        'invoiceId': None,
                        'transactionId': verify_session_result.get('transaction_id'),
                        'session_type': 'verify'
                    }
                })
            else:
                return jsonify({
                    'success': False,
                    'error': verify_session_result.get('error', 'Failed to create verification session')
                }), 400
        
        else:
            # FOR PURCHASE/PREAUTH - Full customer + invoice flow
            print(f"🛒 Creating {payment_type.upper()} session for payment...")
            
            result = processor.create_complete_checkout_flow(
                amount=float(data['amount']),
                currency=currency,
                customer_info=customer_info,
                description=data.get('description', 'ConnectedAutoCare Payment')
            )
            
            if result['success']:
                print(f"✅ Complete checkout flow created: {result.get('checkout_token')}")
                return jsonify({
                    'success': True,
                    'data': {
                        'checkoutToken': result.get('checkout_token'),
                        'customerId': result.get('customer_id'),
                        'invoiceId': result.get('invoice_id'),
                        'transactionId': result.get('transaction_id'),
                        'session_type': payment_type
                    }
                })
            else:
                return jsonify({
                    'success': False,
                    'error': result.get('error', 'Failed to create payment session')
                }), 400
            
    except Exception as e:
        print(f"💥 Session creation error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Session creation failed: {str(e)}'
        }), 500

@payment_bp.route('/validate-card', methods=['POST'])
def validate_card_endpoint():
    """Validate credit card information"""
    try:
        data = request.get_json()
        card_number = data.get('card_number', '')
        
        is_valid, message = validate_credit_card(card_number)
        card_type = get_card_type(card_number) if is_valid else None
        
        return jsonify({
            'valid': is_valid,
            'message': message,
            'card_type': card_type,
            'last_four': card_number[-4:] if is_valid else None
        })
        
    except Exception as e:
        return jsonify(f"Card validation failed: {str(e)}"), 500

def validate_credit_card(card_number):
    """Basic credit card validation using Luhn algorithm"""
    def luhn_check(card_num):
        def digits_of(n):
            return [int(d) for d in str(n)]
        digits = digits_of(card_num)
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        checksum = sum(odd_digits)
        for d in even_digits:
            checksum += sum(digits_of(d*2))
        return checksum % 10 == 0
    
    # Remove spaces and dashes
    card_number = ''.join(card_number.split()).replace('-', '')
    
    if not card_number.isdigit():
        return False, 'Card number must contain only digits'
    
    if len(card_number) < 13 or len(card_number) > 19:
        return False, 'Invalid card number length'
    
    if not luhn_check(card_number):
        return False, 'Invalid card number'
    
    return True, 'Valid card number'

def get_card_type(card_number):
    """Determine credit card type from number"""
    card_number = ''.join(card_number.split()).replace('-', '')
    
    if card_number.startswith('4'):
        return 'Visa'
    elif card_number.startswith(('51', '52', '53', '54', '55')) or card_number.startswith('22'):
        return 'MasterCard'
    elif card_number.startswith(('34', '37')):
        return 'American Express'
    elif card_number.startswith('6011') or card_number.startswith('65'):
        return 'Discover'
    else:
        return 'Unknown'

# Webhook endpoints
@payment_bp.route('/webhooks/helcim', methods=['POST'])
def helcim_webhook():
    """Handle Helcim payment webhooks with proper signature verification"""
    if not PAYMENT_SERVICE_AVAILABLE:
        return jsonify({'error': 'Payment service not available'}), 503
        
    try:
        try:
            from helcim_integration import HelcimPaymentProcessor
            processor = HelcimPaymentProcessor()
        except ImportError:
            return jsonify({'error': 'Helcim integration not available'}), 503
        
        # Get raw request data for signature verification
        raw_data = request.get_data()
        headers = dict(request.headers)
        
        # Verify webhook signature
        if not processor.verify_webhook_signature(headers, raw_data):
            return jsonify({'error': 'Invalid webhook signature'}), 401
        
        # Parse webhook data
        try:
            webhook_data = json.loads(raw_data.decode('utf-8'))
        except json.JSONDecodeError:
            return jsonify({'error': 'Invalid JSON payload'}), 400
        
        transaction_id = webhook_data.get('id')
        webhook_type = webhook_data.get('type')
        
        if not transaction_id:
            return jsonify({'error': 'Missing transaction ID'}), 400
        
        # Update transaction in database
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        try:
            # Find transaction by processor transaction ID
            cursor.execute('''
                SELECT id, transaction_number, status
                FROM transactions 
                WHERE processor_response->>'transaction_id' = %s;
            ''', (transaction_id,))
            
            transaction = cursor.fetchone()
            
            if transaction:
                # Update transaction status based on webhook
                new_status = 'completed' if webhook_type == 'transaction.approved' else 'failed'
                
                cursor.execute('''
                    UPDATE transactions 
                    SET status = %s, 
                        processed_at = CURRENT_TIMESTAMP,
                        processor_response = processor_response || %s
                    WHERE id = %s;
                ''', (
                    new_status,
                    json.dumps({'webhook_received': True, 'webhook_type': webhook_type}),
                    transaction[0]
                ))
                
                conn.commit()
                
                print(f"✅ Webhook processed: {webhook_type} for transaction {transaction[1]}")
            else:
                print(f"⚠️ Webhook received for unknown transaction: {transaction_id}")
            
            cursor.close()
            conn.close()
            
            return jsonify({'received': True}), 200
            
        except Exception as db_error:
            conn.rollback()
            cursor.close()
            conn.close()
            raise db_error
        
    except Exception as e:
        print(f"❌ Webhook processing error: {str(e)}")
        return jsonify({'error': 'Webhook processing failed'}), 500
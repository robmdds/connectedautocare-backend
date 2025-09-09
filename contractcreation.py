#!/usr/bin/env python3
"""
Fixed Contract Generation Script
Works with your JSONB customer schema and UUID transaction IDs

Usage:
python contractcreation.py TXN-20250908041348-20250908040634
python contractcreation.py --all
python contractcreation.py --list
"""

import os
import sys
import json
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone
import uuid

# Your Neon database URL
DATABASE_URL = "postgres://neondb_owner:npg_qH6nhmdrSFL1@ep-tiny-water-adje4r08-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"


def get_connection():
    """Get database connection"""
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        sys.exit(1)


def get_transaction_details(transaction_identifier):
    """Get transaction and customer details using transaction_number"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get transaction by transaction_number (not UUID id)
    cursor.execute('''
                   SELECT t.id,
                          t.transaction_number,
                          t.customer_id,
                          t.amount,
                          t.status,
                          t.payment_method,
                          t.processor_response,
                          t.metadata,
                          t.created_at,
                          c.personal_info,
                          c.contact_info,
                          c.billing_info
                   FROM transactions t
                            LEFT JOIN customers c ON t.customer_id = c.id
                   WHERE t.transaction_number = %s
                   ''', (transaction_identifier,))

    transaction = cursor.fetchone()
    cursor.close()
    conn.close()

    return transaction


def extract_customer_data(transaction):
    """Extract customer data from JSONB fields and metadata"""
    customer_data = {
        'first_name': None,
        'last_name': None,
        'email': None,
        'phone': None,
        'address': None
    }

    # Extract from personal_info JSONB
    if transaction.get('personal_info'):
        personal = transaction['personal_info']
        customer_data['first_name'] = personal.get('first_name') or personal.get('firstName')
        customer_data['last_name'] = personal.get('last_name') or personal.get('lastName')

    # Extract from contact_info JSONB
    if transaction.get('contact_info'):
        contact = transaction['contact_info']
        customer_data['email'] = contact.get('email')
        customer_data['phone'] = contact.get('phone') or contact.get('phone_number')
        customer_data['address'] = contact.get('address')

    # Extract from billing_info JSONB
    if transaction.get('billing_info'):
        billing = transaction['billing_info']
        if not customer_data['first_name']:
            customer_data['first_name'] = billing.get('first_name') or billing.get('firstName')
        if not customer_data['last_name']:
            customer_data['last_name'] = billing.get('last_name') or billing.get('lastName')
        if not customer_data['email']:
            customer_data['email'] = billing.get('email')
        if not customer_data['phone']:
            customer_data['phone'] = billing.get('phone')
        if not customer_data['address']:
            customer_data['address'] = billing.get('address')

    # Extract from transaction metadata
    metadata = transaction.get('metadata', {})

    # Try customer_info in metadata
    if metadata.get('customer_info'):
        meta_customer = metadata['customer_info']
        for field in ['first_name', 'last_name', 'email', 'phone']:
            if not customer_data[field] and meta_customer.get(field):
                customer_data[field] = meta_customer[field]

    # Try billing_info in metadata
    if metadata.get('billing_info'):
        meta_billing = metadata['billing_info']
        for field in ['first_name', 'last_name', 'email', 'phone']:
            if not customer_data[field] and meta_billing.get(field):
                customer_data[field] = meta_billing[field]

    return customer_data


def check_existing_contract(transaction_number):
    """Check if contract already exists for transaction"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute('''
                   SELECT id, contract_number, status
                   FROM generated_contracts
                   WHERE transaction_id = %s
                   ''', (transaction_number,))

    contract = cursor.fetchone()
    cursor.close()
    conn.close()

    return contract


def get_contract_template(product_type):
    """Get contract template for product type"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute('''
                   SELECT id, template_id, name
                   FROM contract_templates
                   WHERE product_type = %s
                     AND active = true
                   ORDER BY created_at DESC LIMIT 1
                   ''', (product_type,))

    template = cursor.fetchone()
    cursor.close()
    conn.close()

    return template


def inspect_table_schema(table_name):
    """Inspect table schema to understand column constraints"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
                   SELECT column_name, data_type, is_nullable, column_default
                   FROM information_schema.columns
                   WHERE table_name = %s
                   ORDER BY ordinal_position
                   """, (table_name,))

    columns = cursor.fetchall()
    cursor.close()
    conn.close()

    return columns


def generate_contract(transaction_identifier):
    """Generate contract for a specific transaction"""
    print(f"🔍 Processing transaction: {transaction_identifier}")

    # Get transaction details
    transaction = get_transaction_details(transaction_identifier)
    if not transaction:
        print(f"❌ Transaction not found: {transaction_identifier}")
        return False

    print(f"📊 Transaction: ${float(transaction['amount']):.2f} - Status: {transaction['status']}")

    # Check if contract already exists
    existing = check_existing_contract(transaction['transaction_number'])
    if existing:
        print(f"✅ Contract already exists: {existing['contract_number']}")
        return True

    # Extract metadata
    metadata = transaction['metadata'] if transaction['metadata'] else {}
    product_type = metadata.get('product_type', 'protection_plan')
    print(f"📦 Product type: {product_type}")

    # Generate contract number
    contract_number = f"CAC-{product_type.upper()}-{transaction['transaction_number']}"

    # Get template
    template = get_contract_template(product_type)
    template_id = template['id'] if template else None

    if template:
        print(f"📋 Using template: {template['name']}")
    else:
        print("⚠️  No template found, using default")

    # Extract customer data from JSONB fields and metadata
    customer_data = extract_customer_data(transaction)

    print(f"👤 Customer: {customer_data.get('first_name', 'Unknown')} {customer_data.get('last_name', '')}")
    print(f"📧 Email: {customer_data.get('email', 'Not provided')}")

    # Prepare contract data
    contract_data = {
        'transaction_info': {
            'transaction_number': transaction.get('transaction_number'),
            'amount': float(transaction.get('amount', 0)),
            'payment_method': transaction.get('payment_method'),
            'processor_response': transaction.get('processor_response'),
            'transaction_date': transaction.get('created_at').isoformat() if transaction.get('created_at') else None
        },
        'product_info': {
            'product_type': product_type,
            'metadata': metadata
        },
        'generation_info': {
            'generated_via': 'direct_script',
            'template_used': template.get('template_id') if template else 'default',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'customer_data_sources': ['personal_info', 'contact_info', 'billing_info', 'metadata']
        }
    }

    # Debug: Inspect generated_contracts table schema
    print("🔧 Debugging table schema...")
    schema = inspect_table_schema('generated_contracts')
    for col in schema:
        print(f"   {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']})")

    # Insert contract into database
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        print("🔧 Attempting to insert contract...")

        # Generate a UUID for the contract
        contract_uuid = str(uuid.uuid4())

        # Modified INSERT with explicit UUID and better error handling
        cursor.execute('''
                       INSERT INTO generated_contracts
                       (id, contract_number, transaction_id, template_id, customer_id,
                        customer_data, contract_data, status, generated_date)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                       ''', (
                           contract_uuid,  # Explicitly provide UUID
                           contract_number,
                           transaction['transaction_number'],  # Using transaction_number as string
                           template_id,
                           str(transaction['customer_id']) if transaction['customer_id'] else None,
                           # Ensure UUID is string
                           json.dumps(customer_data),
                           json.dumps(contract_data),
                           'draft',
                           datetime.now(timezone.utc)
                       ))

        result = cursor.fetchone()
        if result:
            contract_id = result['id']
            print(f"✅ Contract inserted with ID: {contract_id}")
        else:
            raise Exception("No result returned from INSERT")

        # Log activity - with better error handling
        try:
            cursor.execute('''
                           INSERT INTO contract_activities
                               (contract_id, activity_type, description, performed_by, performed_at)
                           VALUES (%s, %s, %s, %s, %s)
                           ''', (
                               contract_id,
                               'generated',
                               f'Contract generated via direct script for transaction {transaction["transaction_number"]}',
                               'script',
                               datetime.now(timezone.utc)
                           ))
            print("✅ Activity logged")
        except Exception as activity_error:
            print(f"⚠️  Failed to log activity (contract still created): {activity_error}")

        # Update transaction metadata
        try:
            updated_metadata = metadata.copy()
            updated_metadata.update({
                'contract_generated': True,
                'contract_id': str(contract_id),
                'contract_number': contract_number
            })

            cursor.execute('''
                           UPDATE transactions
                           SET metadata = %s
                           WHERE id = %s
                           ''', (json.dumps(updated_metadata), transaction['id']))
            print("✅ Transaction metadata updated")
        except Exception as metadata_error:
            print(f"⚠️  Failed to update transaction metadata (contract still created): {metadata_error}")

        conn.commit()

        print(f"✅ Contract created successfully!")
        print(f"   Contract ID: {contract_id}")
        print(f"   Contract Number: {contract_number}")
        print(f"   Status: draft")

        cursor.close()
        conn.close()

        return True

    except KeyError as ke:
        conn.rollback()
        cursor.close()
        conn.close()
        print(f"❌ KeyError - missing dictionary key:")
        print(f"   Missing key: {str(ke)}")
        print(f"   Available transaction keys: {list(transaction.keys()) if transaction else 'None'}")
        if template:
            print(f"   Available template keys: {list(template.keys())}")
        return False
    except psycopg2.Error as e:
        conn.rollback()
        cursor.close()
        conn.close()
        print(f"❌ Database error creating contract:")
        print(f"   Error code: {e.pgcode}")
        print(f"   Error message: {e.pgerror}")
        print(f"   Detailed error: {str(e)}")
        return False
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        print(f"❌ Failed to create contract: {str(e)}")
        print(f"   Error type: {type(e).__name__}")
        import traceback
        print(f"   Full traceback:")
        traceback.print_exc()
        return False


def get_all_completed_transactions():
    """Get all completed transactions without contracts"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute('''
                   SELECT transaction_number,
                          amount,
                          status,
                          created_at,
                          metadata ->>'product_type' as product_type
                   FROM transactions
                   WHERE status IN ('completed'
                       , 'approved')
                     AND NOT EXISTS (
                       SELECT 1 FROM generated_contracts gc
                       WHERE gc.transaction_id = transactions.transaction_number
                       )
                   ORDER BY created_at DESC
                   ''')

    transactions = cursor.fetchall()
    cursor.close()
    conn.close()

    return transactions


def show_transaction_details(transaction_number):
    """Show detailed info about a transaction for debugging"""
    print(f"🔍 Detailed analysis of transaction: {transaction_number}")
    print("-" * 50)

    transaction = get_transaction_details(transaction_number)
    if not transaction:
        print("❌ Transaction not found")
        return

    print(f"📊 Transaction Details:")
    print(f"   ID: {transaction['id']}")
    print(f"   Number: {transaction['transaction_number']}")
    print(f"   Amount: ${float(transaction['amount']):.2f}")
    print(f"   Status: {transaction['status']}")
    print(f"   Customer ID: {transaction['customer_id']}")
    print(f"   Created: {transaction['created_at']}")

    print(f"\n👤 Customer Data Sources:")
    print(f"   Personal Info: {transaction.get('personal_info', 'None')}")
    print(f"   Contact Info: {transaction.get('contact_info', 'None')}")
    print(f"   Billing Info: {transaction.get('billing_info', 'None')}")

    print(f"\n📦 Metadata:")
    metadata = transaction.get('metadata', {})
    print(f"   Product Type: {metadata.get('product_type', 'Not specified')}")
    print(f"   Customer Info in Metadata: {metadata.get('customer_info', 'None')}")
    print(f"   Billing Info in Metadata: {metadata.get('billing_info', 'None')}")

    print(f"\n📋 Extracted Customer Data:")
    customer_data = extract_customer_data(transaction)
    for field, value in customer_data.items():
        print(f"   {field}: {value}")


def main():
    parser = argparse.ArgumentParser(description='Generate contracts for transactions')
    parser.add_argument('transaction_id', nargs='?',
                        help='Transaction number (e.g., TXN-20250908041348-20250908040634)')
    parser.add_argument('--all', action='store_true', help='Generate contracts for all completed transactions')
    parser.add_argument('--list', action='store_true', help='List transactions without contracts')
    parser.add_argument('--details', help='Show detailed info about a specific transaction')
    parser.add_argument('--schema', help='Show schema for a specific table')

    args = parser.parse_args()

    print("🏗️  ConnectedAutoCare Contract Generator")
    print("=" * 50)

    if args.schema:
        print(f"🔧 Schema for table: {args.schema}")
        schema = inspect_table_schema(args.schema)
        for col in schema:
            print(
                f"   {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']}, default: {col['column_default']})")

    elif args.details:
        show_transaction_details(args.details)

    elif args.list:
        print("📋 Completed transactions without contracts:")
        transactions = get_all_completed_transactions()

        if not transactions:
            print("✅ All completed transactions have contracts!")
            return

        for txn in transactions:
            print(
                f"  • {txn['transaction_number']} - ${float(txn['amount']):.2f} ({txn['product_type']}) - {txn['created_at']}")

        print(f"\nFound {len(transactions)} transactions needing contracts")

    elif args.all:
        print("🚀 Generating contracts for all completed transactions...")
        transactions = get_all_completed_transactions()

        if not transactions:
            print("✅ All completed transactions already have contracts!")
            return

        print(f"📊 Found {len(transactions)} transactions to process")

        success_count = 0
        for txn in transactions:
            print(f"\n--- Processing {txn['transaction_number']} ---")
            if generate_contract(txn['transaction_number']):
                success_count += 1

        print(f"\n📊 Summary: {success_count}/{len(transactions)} contracts generated successfully")

    elif args.transaction_id:
        print(f"🎯 Generating contract for specific transaction...")
        if generate_contract(args.transaction_id):
            print("\n🎉 Contract generation completed successfully!")
        else:
            print("\n❌ Contract generation failed!")

    else:
        print("❓ No action specified. Use --help for options.")
        print("\nQuick commands:")
        print("  python contractcreation.py TXN-20250908041348-20250908040634")
        print("  python contractcreation.py --details TXN-20250908041348-20250908040634")
        print("  python contractcreation.py --schema generated_contracts")
        print("  python contractcreation.py --list")
        print("  python contractcreation.py --all")


if __name__ == '__main__':
    main()
#!/usr/bin/env python3
"""
Database Transaction Checker and Contract Creation Fixer

This script checks for hanging transactions and provides a robust contract creation
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime, timezone
import uuid

DATABASE_URL = "postgres://neondb_owner:npg_qH6nhmdrSFL1@ep-tiny-water-adje4r08-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"


def check_active_transactions():
    """Check for active/hanging transactions"""
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Check for active transactions
        cursor.execute("""
                       SELECT pid,
                              usename,
                              application_name,
                              client_addr,
                              state,
                              query_start,
                              state_change,
                              query
                       FROM pg_stat_activity
                       WHERE state != 'idle' 
            AND pid != pg_backend_pid()
                       ORDER BY query_start;
                       """)

        active_sessions = cursor.fetchall()

        print("Active Database Sessions:")
        print("-" * 50)

        if active_sessions:
            for session in active_sessions:
                print(f"PID: {session['pid']}")
                print(f"User: {session['usename']}")
                print(f"State: {session['state']}")
                print(f"Query Start: {session['query_start']}")
                print(f"Query: {session['query'][:100]}...")
                print()
        else:
            print("No active transactions found")

        # Check for locks
        cursor.execute("""
                       SELECT l.mode,
                              l.locktype,
                              l.database,
                              l.relation,
                              l.page,
                              l.tuple,
                              l.virtualxid,
                              l.transactionid,
                              l.classid,
                              l.objid,
                              l.objsubid,
                              l.virtualtransaction,
                              l.pid,
                              l.granted
                       FROM pg_locks l
                       WHERE NOT l.granted
                       ORDER BY l.pid;
                       """)

        locks = cursor.fetchall()

        if locks:
            print("\nBlocked Locks:")
            print("-" * 30)
            for lock in locks:
                print(f"PID: {lock['pid']}, Mode: {lock['mode']}, Type: {lock['locktype']}")
        else:
            print("\nNo blocked locks found")

    finally:
        cursor.close()
        conn.close()


def check_contract_exists():
    """Check if any contracts exist"""
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute("SELECT COUNT(*) as count FROM generated_contracts;")
        result = cursor.fetchone()
        print(f"Total contracts in database: {result['count']}")

        if result['count'] > 0:
            cursor.execute("""
                           SELECT contract_number, status, generated_date, transaction_id
                           FROM generated_contracts
                           ORDER BY generated_date DESC LIMIT 5;
                           """)
            contracts = cursor.fetchall()

            print("\nRecent contracts:")
            for contract in contracts:
                print(f"  {contract['contract_number']} - {contract['status']} - {contract['generated_date']}")

    except Exception as e:
        print(f"Error checking contracts: {e}")
    finally:
        cursor.close()
        conn.close()


def create_contract_safely(transaction_number):
    """Create contract with proper transaction handling"""

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False  # Ensure we control the transaction
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        print(f"Creating contract for transaction: {transaction_number}")

        # Get transaction details
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
                       ''', (transaction_number,))

        transaction = cursor.fetchone()
        if not transaction:
            print(f"Transaction not found: {transaction_number}")
            return False

        print(f"Found transaction: ${float(transaction['amount']):.2f}")

        # Check if contract already exists
        cursor.execute('''
                       SELECT id
                       FROM generated_contracts
                       WHERE transaction_id = %s
                       ''', (transaction_number,))

        existing = cursor.fetchone()
        if existing:
            print(f"Contract already exists for this transaction")
            return True

        # Extract customer data
        metadata = transaction['metadata'] if transaction['metadata'] else {}
        product_type = metadata.get('product_type', 'protection_plan')

        # Get customer info from metadata (since customer table fields are JSONB)
        customer_data = {}
        if metadata.get('customer_info'):
            customer_info = metadata['customer_info']
            customer_data.update({
                'first_name': customer_info.get('first_name'),
                'last_name': customer_info.get('last_name'),
                'email': customer_info.get('email'),
                'phone': customer_info.get('phone')
            })

        if metadata.get('billing_info'):
            billing_info = metadata['billing_info']
            for field in ['first_name', 'last_name', 'email', 'phone']:
                if not customer_data.get(field):
                    customer_data[field] = billing_info.get(field)

        contract_number = f"CAC-{product_type.upper()}-{transaction['transaction_number']}"

        # Get template
        cursor.execute('''
                       SELECT id
                       FROM contract_templates
                       WHERE product_type = %s
                         AND active = true
                       ORDER BY created_at DESC LIMIT 1
                       ''', (product_type,))

        template = cursor.fetchone()
        template_id = template['id'] if template else None

        # Prepare contract data
        contract_data = {
            'transaction_info': {
                'transaction_number': transaction['transaction_number'],
                'amount': float(transaction['amount']),
                'payment_method': transaction['payment_method'],
                'transaction_date': transaction['created_at'].isoformat() if transaction['created_at'] else None
            },
            'product_info': {
                'product_type': product_type,
                'metadata': metadata
            },
            'generation_info': {
                'generated_via': 'safe_script',
                'generated_at': datetime.now(timezone.utc).isoformat()
            }
        }

        # Insert contract (simplified - no activity logging that was causing issues)
        cursor.execute('''
                       INSERT INTO generated_contracts
                       (contract_number, transaction_id, template_id, customer_id,
                        customer_data, contract_data, status, generated_date)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                       ''', (
                           contract_number,
                           transaction['transaction_number'],
                           template_id,
                           transaction['customer_id'],
                           json.dumps(customer_data),
                           json.dumps(contract_data),
                           'generated',  # Use 'generated' status
                           datetime.now(timezone.utc)
                       ))

        contract_id = None
        result = cursor.fetchone()
        if result:
            contract_id = result['id']

        # Commit the transaction
        conn.commit()

        print(f"Contract created successfully!")
        print(f"  Contract ID: {contract_id}")
        print(f"  Contract Number: {contract_number}")
        print(f"  Customer: {customer_data.get('first_name', 'Unknown')} {customer_data.get('last_name', '')}")

        return True

    except Exception as e:
        # Rollback on any error
        conn.rollback()
        print(f"Error creating contract: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        cursor.close()
        conn.close()


def verify_contract_creation(transaction_number):
    """Verify contract was actually created and committed"""
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute('''
                       SELECT contract_number,
                              status,
                              generated_date,
                              customer_data ->>'first_name' as first_name, customer_data->>'last_name' as last_name
                       FROM generated_contracts
                       WHERE transaction_id = %s
                       ''', (transaction_number,))

        contract = cursor.fetchone()

        if contract:
            print(f"✓ Contract verified in database:")
            print(f"  Number: {contract['contract_number']}")
            print(f"  Status: {contract['status']}")
            print(f"  Customer: {contract['first_name']} {contract['last_name']}")
            print(f"  Generated: {contract['generated_date']}")
            return True
        else:
            print(f"✗ No contract found for transaction: {transaction_number}")
            return False

    finally:
        cursor.close()
        conn.close()


def main():
    print("Database Transaction Checker and Contract Fixer")
    print("=" * 50)

    print("\n1. Checking active transactions...")
    check_active_transactions()

    print("\n2. Checking existing contracts...")
    check_contract_exists()

    transaction_number = "TXN-20250908041348-20250908040634"

    print(f"\n3. Creating contract for {transaction_number}...")
    if create_contract_safely(transaction_number):
        print("\n4. Verifying contract creation...")
        verify_contract_creation(transaction_number)
    else:
        print("Contract creation failed")


if __name__ == '__main__':
    main()
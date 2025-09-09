import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = "postgres://neondb_owner:npg_qH6nhmdrSFL1@ep-tiny-water-adje4r08-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"

def debug_transaction(transaction_number):
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get transaction details
    cursor.execute('''
        SELECT 
            id, transaction_number, status, amount, created_at, metadata
        FROM transactions 
        WHERE transaction_number = %s
    ''', (transaction_number,))
    
    transaction = cursor.fetchone()
    
    if transaction:
        print(f"✅ Transaction found:")
        print(f"   ID: {transaction['id']}")
        print(f"   Number: {transaction['transaction_number']}")
        print(f"   Status: '{transaction['status']}'")
        print(f"   Status type: {type(transaction['status'])}")
        print(f"   Amount: {transaction['amount']}")
        print(f"   Created: {transaction['created_at']}")
        
        # Check status comparison
        status = transaction['status']
        print(f"\n🔍 Status checks:")
        print(f"   status == 'completed': {status == 'completed'}")
        print(f"   status == 'approved': {status == 'approved'}")
        print(f"   status in ['completed', 'approved']: {status in ['completed', 'approved']}")
        print(f"   status not in ['completed', 'approved']: {status not in ['completed', 'approved']}")
        
        # Check existing contracts
        cursor.execute('''
            SELECT id, contract_number, status 
            FROM generated_contracts 
            WHERE transaction_id = %s
        ''', (transaction['transaction_number'],))
        
        existing = cursor.fetchone()
        if existing:
            print(f"\n⚠️  Contract already exists:")
            print(f"   Contract ID: {existing['id']}")
            print(f"   Contract Number: {existing['contract_number']}")
            print(f"   Contract Status: {existing['status']}")
        else:
            print(f"\n✅ No existing contract found")
            
    else:
        print(f"❌ Transaction not found: {transaction_number}")
    
    cursor.close()
    conn.close()

# Run the debug
debug_transaction('TXN-20250908041348-20250908040634')

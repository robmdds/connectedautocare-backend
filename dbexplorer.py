#!/usr/bin/env python3
"""
Database Explorer Script for ConnectedAutoCare
Explore and analyze the Neon PostgreSQL database structure and data

Usage:
python explore_database.py --tables                    # List all tables
python explore_database.py --schema                    # Show complete schema
python explore_database.py --table transactions        # Analyze specific table
python explore_database.py --sample transactions 5     # Show sample data
python explore_database.py --contracts                 # Check contract status
python explore_database.py --stats                     # Database statistics
"""

import os
import sys
import argparse
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone
from tabulate import tabulate

# Database connection
DATABASE_URL = "postgres://neondb_owner:npg_qH6nhmdrSFL1@ep-tiny-water-adje4r08-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"


def get_connection():
    """Get database connection"""
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)


def list_all_tables():
    """List all tables in the database"""
    print("🗂️  DATABASE TABLES")
    print("=" * 50)

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
                   SELECT schemaname,
                          tablename,
                          tableowner,
                          hasindexes,
                          hasrules,
                          hastriggers
                   FROM pg_tables
                   WHERE schemaname = 'public'
                   ORDER BY tablename;
                   """)

    tables = cursor.fetchall()

    if tables:
        table_data = []
        for table in tables:
            table_data.append([
                table['tablename'],
                table['tableowner'],
                '✓' if table['hasindexes'] else '✗',
                '✓' if table['hasrules'] else '✗',
                '✓' if table['hastriggers'] else '✗'
            ])

        print(tabulate(table_data,
                       headers=['Table Name', 'Owner', 'Indexes', 'Rules', 'Triggers'],
                       tablefmt='grid'))
    else:
        print("No tables found in public schema")

    cursor.close()
    conn.close()


def show_table_schema(table_name=None):
    """Show schema for all tables or specific table"""
    print("📋 DATABASE SCHEMA")
    print("=" * 50)

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    if table_name:
        where_clause = "AND table_name = %s"
        params = (table_name,)
        print(f"Schema for table: {table_name}")
    else:
        where_clause = ""
        params = ()
        print("Complete database schema:")

    cursor.execute(f"""
        SELECT 
            table_name,
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length,
            ordinal_position
        FROM information_schema.columns 
        WHERE table_schema = 'public' {where_clause}
        ORDER BY table_name, ordinal_position;
    """, params)

    columns = cursor.fetchall()

    if columns:
        current_table = None
        for col in columns:
            if col['table_name'] != current_table:
                current_table = col['table_name']
                print(f"\n📊 TABLE: {current_table}")
                print("-" * 40)

            nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
            max_len = f"({col['character_maximum_length']})" if col['character_maximum_length'] else ""
            default = f" DEFAULT {col['column_default']}" if col['column_default'] else ""

            print(f"  {col['column_name']:25} {col['data_type']}{max_len:15} {nullable:10}{default}")
    else:
        print(f"No columns found for table: {table_name}")

    cursor.close()
    conn.close()


def analyze_table(table_name):
    """Analyze specific table structure and data"""
    print(f"🔍 ANALYZING TABLE: {table_name}")
    print("=" * 50)

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Check if table exists
    cursor.execute("""
                   SELECT EXISTS (SELECT
                                  FROM information_schema.tables
                                  WHERE table_schema = 'public'
                                    AND table_name = %s);
                   """, (table_name,))

    if not cursor.fetchone()['exists']:
        print(f"❌ Table '{table_name}' does not exist")
        cursor.close()
        conn.close()
        return

    # Table info
    cursor.execute(f"SELECT COUNT(*) as row_count FROM {table_name};")
    row_count = cursor.fetchone()['row_count']

    # Column info
    cursor.execute("""
                   SELECT column_name,
                          data_type,
                          is_nullable,
                          column_default
                   FROM information_schema.columns
                   WHERE table_schema = 'public'
                     AND table_name = %s
                   ORDER BY ordinal_position;
                   """, (table_name,))

    columns = cursor.fetchall()

    print(f"📊 Rows: {row_count:,}")
    print(f"📋 Columns: {len(columns)}")
    print("\nColumn Details:")

    col_data = []
    for col in columns:
        nullable = "YES" if col['is_nullable'] == 'YES' else "NO"
        default = col['column_default'] or "None"
        col_data.append([
            col['column_name'],
            col['data_type'],
            nullable,
            default
        ])

    print(tabulate(col_data,
                   headers=['Column', 'Type', 'Nullable', 'Default'],
                   tablefmt='grid'))

    # Show indexes
    cursor.execute("""
                   SELECT indexname,
                          indexdef
                   FROM pg_indexes
                   WHERE tablename = %s;
                   """, (table_name,))

    indexes = cursor.fetchall()
    if indexes:
        print(f"\n🔗 Indexes ({len(indexes)}):")
        for idx in indexes:
            print(f"  • {idx['indexname']}")
            print(f"    {idx['indexdef']}")

    cursor.close()
    conn.close()


def show_sample_data(table_name, limit=5):
    """Show sample data from table"""
    print(f"📄 SAMPLE DATA: {table_name} (limit {limit})")
    print("=" * 50)

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Check if table exists
    cursor.execute("""
                   SELECT EXISTS (SELECT
                                  FROM information_schema.tables
                                  WHERE table_schema = 'public'
                                    AND table_name = %s);
                   """, (table_name,))

    if not cursor.fetchone()['exists']:
        print(f"❌ Table '{table_name}' does not exist")
        cursor.close()
        conn.close()
        return

    try:
        cursor.execute(f"SELECT * FROM {table_name} ORDER BY created_at DESC LIMIT %s;", (limit,))
    except:
        try:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT %s;", (limit,))
        except Exception as e:
            print(f"❌ Error querying table: {e}")
            cursor.close()
            conn.close()
            return

    rows = cursor.fetchall()

    if rows:
        # Convert complex types to strings for display
        display_rows = []
        for row in rows:
            display_row = {}
            for key, value in row.items():
                if isinstance(value, (dict, list)):
                    display_row[key] = json.dumps(value, indent=2)[:100] + "..." if len(
                        str(value)) > 100 else json.dumps(value)
                elif isinstance(value, datetime):
                    display_row[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    display_row[key] = str(value)[:100] + "..." if len(str(value)) > 100 else value
            display_rows.append(display_row)

        # Print each row
        for i, row in enumerate(display_rows, 1):
            print(f"\n📝 Row {i}:")
            for key, value in row.items():
                print(f"  {key:20}: {value}")
    else:
        print("No data found in table")

    cursor.close()
    conn.close()


def check_contract_status():
    """Check contract generation status across transactions"""
    print("📋 CONTRACT STATUS ANALYSIS")
    print("=" * 50)

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Check if tables exist
    tables_exist = {}
    for table in ['transactions', 'generated_contracts']:
        cursor.execute("""
                       SELECT EXISTS (SELECT
                                      FROM information_schema.tables
                                      WHERE table_schema = 'public'
                                        AND table_name = %s);
                       """, (table,))
        tables_exist[table] = cursor.fetchone()['exists']

    print(f"📊 Table Status:")
    print(f"  • transactions: {'✓' if tables_exist['transactions'] else '❌'}")
    print(f"  • generated_contracts: {'✓' if tables_exist['generated_contracts'] else '❌'}")

    if not tables_exist['transactions']:
        print("❌ Cannot analyze - transactions table missing")
        cursor.close()
        conn.close()
        return

    # Transaction statistics
    cursor.execute("""
                   SELECT COUNT(*) as total_transactions,
                          COUNT(*)    FILTER (WHERE status = 'completed') as completed_transactions, COUNT(*) FILTER (WHERE status = 'approved') as approved_transactions, COUNT(*) FILTER (WHERE status IN ('completed', 'approved')) as payable_transactions
                   FROM transactions;
                   """)

    txn_stats = cursor.fetchone()

    print(f"\n📈 Transaction Statistics:")
    print(f"  • Total: {txn_stats['total_transactions']:,}")
    print(f"  • Completed: {txn_stats['completed_transactions']:,}")
    print(f"  • Approved: {txn_stats['approved_transactions']:,}")
    print(f"  • Payable: {txn_stats['payable_transactions']:,}")

    # Check if contract_generated column exists
    cursor.execute("""
                   SELECT EXISTS (SELECT
                                  FROM information_schema.columns
                                  WHERE table_schema = 'public'
                                    AND table_name = 'transactions'
                                    AND column_name = 'contract_generated');
                   """)

    has_contract_column = cursor.fetchone()['exists']
    print(f"  • Has contract_generated column: {'✓' if has_contract_column else '❌'}")

    # Contract statistics if table exists
    if tables_exist['generated_contracts']:
        cursor.execute("SELECT COUNT(*) as contract_count FROM generated_contracts;")
        contract_count = cursor.fetchone()['contract_count']
        print(f"  • Generated contracts: {contract_count:,}")

        if has_contract_column:
            cursor.execute("""
                           SELECT COUNT(*) as marked_transactions
                           FROM transactions
                           WHERE contract_generated = true;
                           """)
            marked_count = cursor.fetchone()['marked_transactions']
            print(f"  • Transactions marked with contracts: {marked_count:,}")

    # Show recent transactions that need contracts
    cursor.execute("""
                   SELECT transaction_number,
                          amount,
                          status,
                          created_at,
                          metadata ->>'product_type' as product_type
                   FROM transactions
                   WHERE status IN ('completed', 'approved')
                   ORDER BY created_at DESC
                       LIMIT 10;
                   """)

    recent_txns = cursor.fetchall()

    if recent_txns:
        print(f"\n📋 Recent Completed Transactions:")
        txn_data = []
        for txn in recent_txns:
            txn_data.append([
                txn['transaction_number'],
                f"${float(txn['amount']):.2f}",
                txn['status'],
                txn['product_type'] or 'unknown',
                txn['created_at'].strftime('%Y-%m-%d') if txn['created_at'] else 'N/A'
            ])

        print(tabulate(txn_data,
                       headers=['Transaction', 'Amount', 'Status', 'Product', 'Date'],
                       tablefmt='grid'))

    cursor.close()
    conn.close()


def show_database_stats():
    """Show overall database statistics"""
    print("📊 DATABASE STATISTICS")
    print("=" * 50)

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Database info
    cursor.execute("SELECT current_database(), current_user, version();")
    db_info = cursor.fetchone()

    print(f"🔧 Database: {db_info['current_database']}")
    print(f"👤 User: {db_info['current_user']}")
    print(f"🐘 Version: {db_info['version'].split(',')[0]}")

    # Table sizes
    cursor.execute("""
                   SELECT schemaname,
                          tablename,
                          CASE
                              WHEN schemaname = 'public' THEN
                                  (SELECT COUNT(*)
                                   FROM information_schema.tables
                                   WHERE table_schema = 'public'
                                     AND table_name = t.tablename)
                              ELSE NULL
                              END as exists_check
                   FROM pg_tables t
                   WHERE schemaname = 'public'
                   ORDER BY tablename;
                   """)

    tables = cursor.fetchall()

    print(f"\n📋 Tables in Public Schema:")
    table_stats = []

    for table in tables:
        table_name = table['tablename']
        try:
            cursor.execute(f"SELECT COUNT(*) as row_count FROM {table_name};")
            row_count = cursor.fetchone()['row_count']

            # Get table size
            cursor.execute("""
                SELECT pg_size_pretty(pg_total_relation_size(%s)) as size;
            """, (table_name,))
            size_result = cursor.fetchone()
            table_size = size_result['size'] if size_result else 'Unknown'

            table_stats.append([table_name, f"{row_count:,}", table_size])
        except Exception as e:
            table_stats.append([table_name, "Error", str(e)[:30]])

    print(tabulate(table_stats,
                   headers=['Table', 'Rows', 'Size'],
                   tablefmt='grid'))

    # Recent activity
    cursor.execute("""
                   SELECT schemaname,
                          tablename,
                          n_tup_ins as inserts,
                          n_tup_upd as updates,
                          n_tup_del as deletes
                   FROM pg_stat_user_tables
                   WHERE schemaname = 'public'
                   ORDER BY (n_tup_ins + n_tup_upd + n_tup_del) DESC LIMIT 10;
                   """)

    activity = cursor.fetchall()

    if activity:
        print(f"\n🔄 Table Activity (since last stats reset):")
        activity_data = []
        for row in activity:
            activity_data.append([
                row['tablename'],
                f"{row['inserts']:,}",
                f"{row['updates']:,}",
                f"{row['deletes']:,}"
            ])

        print(tabulate(activity_data,
                       headers=['Table', 'Inserts', 'Updates', 'Deletes'],
                       tablefmt='grid'))

    cursor.close()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description='Explore ConnectedAutoCare Database')
    parser.add_argument('--tables', action='store_true', help='List all tables')
    parser.add_argument('--schema', action='store_true', help='Show complete database schema')
    parser.add_argument('--table', help='Analyze specific table')
    parser.add_argument('--sample', nargs=2, metavar=('TABLE', 'LIMIT'), help='Show sample data from table')
    parser.add_argument('--contracts', action='store_true', help='Check contract generation status')
    parser.add_argument('--stats', action='store_true', help='Show database statistics')

    args = parser.parse_args()

    print("🚀 ConnectedAutoCare Database Explorer")
    print("🔗 Connected to Neon PostgreSQL")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    if args.tables:
        list_all_tables()
    elif args.schema:
        show_table_schema()
    elif args.table:
        analyze_table(args.table)
    elif args.sample:
        table_name, limit = args.sample
        show_sample_data(table_name, int(limit))
    elif args.contracts:
        check_contract_status()
    elif args.stats:
        show_database_stats()
    else:
        print("❓ No action specified. Use --help for options.")
        print()
        print("Quick commands:")
        print("  python explore_database.py --tables")
        print("  python explore_database.py --schema")
        print("  python explore_database.py --contracts")
        print("  python explore_database.py --stats")


if __name__ == '__main__':
    main()
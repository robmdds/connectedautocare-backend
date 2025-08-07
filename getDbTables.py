#!/usr/bin/env python3
"""
Neon PostgreSQL Database Structure Checker
Customized for your Neon database
"""

import psycopg2
from urllib.parse import urlparse
import json
from typing import Dict, List, Any

class NeonPostgreSQLChecker:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.connection = None
        self.parse_connection_string()
    
    def parse_connection_string(self):
        """Parse the PostgreSQL connection string"""
        parsed = urlparse(self.connection_string)
        self.config = {
            'host': parsed.hostname,
            'port': parsed.port or 5432,
            'database': parsed.path[1:],  # Remove leading slash
            'user': parsed.username,
            'password': parsed.password,
            'sslmode': 'require'  # Neon requires SSL
        }
        print(f"Parsed connection: {self.config['user']}@{self.config['host']}:{self.config['port']}/{self.config['database']}")
    
    def connect(self):
        """Establish connection to Neon PostgreSQL"""
        try:
            self.connection = psycopg2.connect(**self.config)
            print("✅ Connected to Neon PostgreSQL database successfully!")
            return True
        except Exception as e:
            print(f"❌ Error connecting to database: {e}")
            return False
    
    def get_database_info(self):
        """Get basic database information"""
        cursor = self.connection.cursor()
        try:
            # Get PostgreSQL version
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            
            # Get database size
            cursor.execute("""
                SELECT pg_size_pretty(pg_database_size(current_database()));
            """)
            db_size = cursor.fetchone()[0]
            
            # Get current schema
            cursor.execute("SELECT current_schema();")
            current_schema = cursor.fetchone()[0]
            
            return {
                'version': version,
                'size': db_size,
                'current_schema': current_schema
            }
        except Exception as e:
            print(f"Error getting database info: {e}")
            return {}
        finally:
            cursor.close()
    
    def get_all_tables(self):
        """Get all tables in the database"""
        cursor = self.connection.cursor()
        try:
            cursor.execute("""
                SELECT 
                    table_schema,
                    table_name,
                    table_type
                FROM information_schema.tables 
                WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
                ORDER BY table_schema, table_name;
            """)
            
            tables = []
            for row in cursor.fetchall():
                tables.append({
                    'schema': row[0],
                    'name': row[1],
                    'type': row[2]
                })
            
            return tables
        except Exception as e:
            print(f"Error getting tables: {e}")
            return []
        finally:
            cursor.close()
    
    def get_table_details(self, schema: str, table_name: str):
        """Get detailed information about a specific table"""
        cursor = self.connection.cursor()
        
        table_info = {
            'schema': schema,
            'table_name': table_name,
            'columns': [],
            'indexes': [],
            'foreign_keys': [],
            'constraints': [],
            'triggers': [],
            'row_count': 0,
            'table_size': None
        }
        
        try:
            # Get column information
            cursor.execute("""
                SELECT 
                    column_name,
                    data_type,
                    is_nullable,
                    column_default,
                    character_maximum_length,
                    numeric_precision,
                    numeric_scale,
                    ordinal_position
                FROM information_schema.columns 
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position;
            """, (schema, table_name))
            
            for row in cursor.fetchall():
                table_info['columns'].append({
                    'name': row[0],
                    'data_type': row[1],
                    'nullable': row[2] == 'YES',
                    'default': row[3],
                    'max_length': row[4],
                    'precision': row[5],
                    'scale': row[6],
                    'position': row[7]
                })
            
            # Get primary key
            cursor.execute("""
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu 
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                WHERE tc.table_schema = %s 
                    AND tc.table_name = %s 
                    AND tc.constraint_type = 'PRIMARY KEY'
                ORDER BY kcu.ordinal_position;
            """, (schema, table_name))
            
            primary_keys = [row[0] for row in cursor.fetchall()]
            table_info['primary_keys'] = primary_keys
            
            # Get foreign keys
            cursor.execute("""
                SELECT
                    kcu.column_name,
                    ccu.table_schema AS foreign_table_schema,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name,
                    rc.constraint_name
                FROM information_schema.referential_constraints rc
                JOIN information_schema.key_column_usage kcu
                    ON rc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage ccu
                    ON rc.unique_constraint_name = ccu.constraint_name
                WHERE kcu.table_schema = %s AND kcu.table_name = %s;
            """, (schema, table_name))
            
            for row in cursor.fetchall():
                table_info['foreign_keys'].append({
                    'column': row[0],
                    'references_schema': row[1],
                    'references_table': row[2],
                    'references_column': row[3],
                    'constraint_name': row[4]
                })
            
            # Get indexes
            cursor.execute("""
                SELECT
                    i.indexname,
                    i.indexdef,
                    am.amname as index_type
                FROM pg_indexes i
                JOIN pg_class c ON c.relname = i.indexname
                JOIN pg_am am ON am.oid = c.relam
                WHERE i.schemaname = %s AND i.tablename = %s;
            """, (schema, table_name))
            
            for row in cursor.fetchall():
                table_info['indexes'].append({
                    'name': row[0],
                    'definition': row[1],
                    'type': row[2]
                })
            
            # Get table size
            cursor.execute("""
                SELECT pg_size_pretty(pg_total_relation_size(%s));
            """, (f"{schema}.{table_name}",))
            
            table_info['table_size'] = cursor.fetchone()[0]
            
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {schema}.{table_name};")
            table_info['row_count'] = cursor.fetchone()[0]
            
            # Get constraints
            cursor.execute("""
                SELECT
                    tc.constraint_name,
                    tc.constraint_type,
                    kcu.column_name,
                    cc.check_clause
                FROM information_schema.table_constraints tc
                LEFT JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                LEFT JOIN information_schema.check_constraints cc
                    ON tc.constraint_name = cc.constraint_name
                WHERE tc.table_schema = %s AND tc.table_name = %s
                    AND tc.constraint_type IN ('CHECK', 'UNIQUE');
            """, (schema, table_name))
            
            for row in cursor.fetchall():
                table_info['constraints'].append({
                    'name': row[0],
                    'type': row[1],
                    'column': row[2],
                    'definition': row[3]
                })
            
        except Exception as e:
            print(f"Error getting details for {schema}.{table_name}: {e}")
        finally:
            cursor.close()
        
        return table_info
    
    def analyze_database(self):
        """Perform complete database analysis"""
        if not self.connect():
            return None
        
        print("\n🔍 Starting database analysis...")
        
        # Get database info
        db_info = self.get_database_info()
        print(f"📊 Database size: {db_info.get('size', 'Unknown')}")
        print(f"🔧 PostgreSQL version: {db_info.get('version', 'Unknown')[:50]}...")
        
        # Get all tables
        tables = self.get_all_tables()
        print(f"📋 Found {len(tables)} tables/views")
        
        analysis = {
            'database_info': db_info,
            'connection_info': {
                'host': self.config['host'],
                'database': self.config['database'],
                'user': self.config['user']
            },
            'summary': {
                'total_tables': len([t for t in tables if t['type'] == 'BASE TABLE']),
                'total_views': len([t for t in tables if t['type'] == 'VIEW']),
                'schemas': list(set(t['schema'] for t in tables))
            },
            'tables': {}
        }
        
        # Analyze each table
        for table in tables:
            print(f"📝 Analyzing {table['schema']}.{table['name']}...")
            table_details = self.get_table_details(table['schema'], table['name'])
            
            # Add table type to details
            table_details['table_type'] = table['type']
            
            analysis['tables'][f"{table['schema']}.{table['name']}"] = table_details
            
            # Print summary
            print(f"   ├─ {len(table_details['columns'])} columns")
            print(f"   ├─ {table_details['row_count']:,} rows")
            print(f"   ├─ {len(table_details['indexes'])} indexes")
            print(f"   ├─ {len(table_details['foreign_keys'])} foreign keys")
            print(f"   └─ Size: {table_details['table_size']}")
        
        return analysis
    
    def generate_summary_report(self, analysis):
        """Generate a human-readable summary report"""
        if not analysis:
            return "No analysis data available"
        
        report = []
        report.append("🗄️  NEON POSTGRESQL DATABASE ANALYSIS REPORT")
        report.append("=" * 60)
        
        # Database info
        db_info = analysis['database_info']
        conn_info = analysis['connection_info']
        report.append(f"📍 Host: {conn_info['host']}")
        report.append(f"🏷️  Database: {conn_info['database']}")
        report.append(f"👤 User: {conn_info['user']}")
        report.append(f"💾 Size: {db_info.get('size', 'Unknown')}")
        report.append("")
        
        # Summary
        summary = analysis['summary']
        report.append("📊 SUMMARY")
        report.append("-" * 20)
        report.append(f"Tables: {summary['total_tables']}")
        report.append(f"Views: {summary['total_views']}")
        report.append(f"Schemas: {', '.join(summary['schemas'])}")
        report.append("")
        
        # Table details
        for table_name, table_info in analysis['tables'].items():
            report.append(f"📋 TABLE: {table_name} ({table_info['table_type']})")
            report.append("-" * 40)
            report.append(f"Rows: {table_info['row_count']:,}")
            report.append(f"Size: {table_info['table_size']}")
            
            if table_info['primary_keys']:
                report.append(f"Primary Key(s): {', '.join(table_info['primary_keys'])}")
            
            report.append("\nColumns:")
            for col in table_info['columns']:
                nullable = "NULL" if col['nullable'] else "NOT NULL"
                default = f" DEFAULT {col['default']}" if col['default'] else ""
                pk_indicator = " 🔑" if col['name'] in table_info['primary_keys'] else ""
                report.append(f"  • {col['name']} - {col['data_type']} {nullable}{default}{pk_indicator}")
            
            if table_info['foreign_keys']:
                report.append("\nForeign Keys:")
                for fk in table_info['foreign_keys']:
                    report.append(f"  • {fk['column']} → {fk['references_schema']}.{fk['references_table']}.{fk['references_column']}")
            
            if table_info['indexes']:
                report.append(f"\nIndexes ({len(table_info['indexes'])}):")
                for idx in table_info['indexes']:
                    report.append(f"  • {idx['name']} ({idx['type']})")
            
            report.append("\n")
        
        return "\n".join(report)
    
    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            print("🔌 Database connection closed")


# Main execution
def main():
    # Your Neon connection string
    connection_string = "postgres://neondb_owner:npg_qH6nhmdrSFL1@ep-tiny-water-adje4r08-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"
    
    checker = NeonPostgreSQLChecker(connection_string)
    
    try:
        # Run the analysis
        analysis = checker.analyze_database()
        
        if analysis:
            # Generate reports
            print("\n" + "="*60)
            print("📄 GENERATING REPORTS...")
            print("="*60)
            
            # Save detailed JSON analysis
            with open('neon_database_analysis.json', 'w') as f:
                json.dump(analysis, f, indent=2, default=str)
            print("💾 Saved detailed analysis to: neon_database_analysis.json")
            
            # Generate and save summary report
            summary_report = checker.generate_summary_report(analysis)
            with open('neon_database_report.txt', 'w') as f:
                f.write(summary_report)
            print("📋 Saved summary report to: neon_database_report.txt")
            
            # Print summary to console
            print("\n" + summary_report)
            
        else:
            print("❌ Failed to analyze database")
            
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
    finally:
        checker.close()


if __name__ == "__main__":
    main()
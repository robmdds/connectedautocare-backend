"""
Database Utilities and Connection Management
PostgreSQL connection pooling, query helpers, and database operations
"""

import os
import time
import json
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
from typing import Dict, List, Optional, Any, Union

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor, Json
    from psycopg2.pool import ThreadedConnectionPool
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    print("Warning: psycopg2 not available. Database functionality will be limited.")

class DatabaseManager:
    """Database connection and utility manager with connection pooling"""
    
    def __init__(self, database_url=None, pool_size_min=1, pool_size_max=10):
        self.database_url = database_url or os.environ.get('DATABASE_URL')
        self.available = bool(self.database_url and PSYCOPG2_AVAILABLE)
        self.pool = None
        
        if self.available:
            try:
                # Initialize connection pool
                self.pool = ThreadedConnectionPool(
                    pool_size_min, 
                    pool_size_max, 
                    self.database_url
                )
                print(f"✅ Database connection pool initialized ({pool_size_min}-{pool_size_max} connections)")
            except Exception as e:
                print(f"❌ Failed to initialize database pool: {e}")
                self.available = False
    
    @contextmanager
    def get_connection(self):
        """Get database connection from pool"""
        if not self.available:
            raise Exception("Database not available")
        
        conn = None
        try:
            conn = self.pool.getconn()
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                self.pool.putconn(conn)
    
    @contextmanager
    def get_cursor(self, cursor_factory=None):
        """Get database cursor with automatic connection management"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=cursor_factory)
            try:
                yield cursor, conn
            finally:
                cursor.close()
    
    def test_connection(self):
        """Test database connection and return performance metrics"""
        if not self.available:
            return {
                'success': False,
                'error': 'Database not configured or dependencies missing'
            }
        
        try:
            start_time = time.time()
            
            with self.get_cursor() as (cursor, conn):
                # Test basic query
                cursor.execute('SELECT version();')
                version = cursor.fetchone()[0]
                
                # Test table existence
                cursor.execute('''
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    LIMIT 5;
                ''')
                tables = cursor.fetchall()
                
                connection_time_ms = round((time.time() - start_time) * 1000, 2)
                
                return {
                    'success': True,
                    'connection_time_ms': connection_time_ms,
                    'database_info': {
                        'version': version,
                        'status': 'connected',
                        'tables_found': len(tables),
                        'pool_status': {
                            'available_connections': self.pool.closed if self.pool else 'no_pool',
                            'pool_size': f"{self.pool.minconn}-{self.pool.maxconn}" if self.pool else 'no_pool'
                        }
                    }
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'connection_time_ms': round((time.time() - start_time) * 1000, 2) if 'start_time' in locals() else None
            }
    
    def execute_query(self, query: str, params: tuple = None, fetch: str = 'all') -> Dict[str, Any]:
        """Execute SQL query with error handling"""
        if not self.available:
            return {'success': False, 'error': 'Database not available'}
        
        try:
            with self.get_cursor(cursor_factory=RealDictCursor) as (cursor, conn):
                cursor.execute(query, params)
                
                if fetch == 'all':
                    result = cursor.fetchall()
                elif fetch == 'one':
                    result = cursor.fetchone()
                elif fetch == 'many':
                    result = cursor.fetchmany()
                else:
                    result = None
                
                # Auto-commit for non-SELECT queries
                if query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER')):
                    conn.commit()
                
                return {
                    'success': True,
                    'data': result,
                    'rowcount': cursor.rowcount
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def insert_record(self, table: str, data: Dict[str, Any], returning: str = 'id') -> Dict[str, Any]:
        """Insert record into table"""
        if not self.available:
            return {'success': False, 'error': 'Database not available'}
        
        try:
            # Prepare columns and values
            columns = list(data.keys())
            placeholders = ['%s'] * len(columns)
            values = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in data.values()]
            
            query = f'''
                INSERT INTO {table} ({', '.join(columns)})
                VALUES ({', '.join(placeholders)})
                RETURNING {returning};
            '''
            
            with self.get_cursor() as (cursor, conn):
                cursor.execute(query, values)
                result = cursor.fetchone()
                conn.commit()
                
                return {
                    'success': True,
                    'data': result,
                    'inserted_id': result[0] if result else None
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def update_record(self, table: str, data: Dict[str, Any], where_condition: str, where_params: tuple = None) -> Dict[str, Any]:
        """Update record in table"""
        if not self.available:
            return {'success': False, 'error': 'Database not available'}
        
        try:
            # Prepare SET clause
            set_clauses = []
            values = []
            
            for column, value in data.items():
                set_clauses.append(f"{column} = %s")
                values.append(json.dumps(value) if isinstance(value, (dict, list)) else value)
            
            # Add WHERE parameters
            if where_params:
                values.extend(where_params)
            
            query = f'''
                UPDATE {table} 
                SET {', '.join(set_clauses)}
                WHERE {where_condition}
                RETURNING *;
            '''
            
            with self.get_cursor(cursor_factory=RealDictCursor) as (cursor, conn):
                cursor.execute(query, values)
                result = cursor.fetchone()
                conn.commit()
                
                return {
                    'success': True,
                    'data': dict(result) if result else None,
                    'updated_rows': cursor.rowcount
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def delete_record(self, table: str, where_condition: str, where_params: tuple = None) -> Dict[str, Any]:
        """Delete record from table"""
        if not self.available:
            return {'success': False, 'error': 'Database not available'}
        
        try:
            query = f'DELETE FROM {table} WHERE {where_condition};'
            
            with self.get_cursor() as (cursor, conn):
                cursor.execute(query, where_params)
                conn.commit()
                
                return {
                    'success': True,
                    'deleted_rows': cursor.rowcount
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """Get table schema information"""
        if not self.available:
            return {'success': False, 'error': 'Database not available'}
        
        try:
            query = '''
                SELECT 
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position;
            '''
            
            result = self.execute_query(query, (table_name,))
            
            if result['success']:
                return {
                    'success': True,
                    'table_name': table_name,
                    'columns': result['data'],
                    'column_count': len(result['data'])
                }
            else:
                return result
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get database performance metrics"""
        if not self.available:
            return {"status": "unavailable", "error": "Database not configured"}
        
        try:
            with self.get_cursor(cursor_factory=RealDictCursor) as (cursor, conn):
                # Get basic database stats
                cursor.execute('''
                    SELECT 
                        pg_database_size(current_database()) as db_size,
                        (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') as active_connections,
                        (SELECT count(*) FROM pg_stat_activity) as total_connections;
                ''')
                
                db_stats = cursor.fetchone()
                
                # Get table statistics
                cursor.execute('''
                    SELECT 
                        schemaname,
                        tablename,
                        n_tup_ins as inserts,
                        n_tup_upd as updates,
                        n_tup_del as deletes
                    FROM pg_stat_user_tables
                    ORDER BY (n_tup_ins + n_tup_upd + n_tup_del) DESC
                    LIMIT 10;
                ''')
                
                table_stats = cursor.fetchall()
                
                return {
                    "status": "available",
                    "database_size_bytes": int(db_stats['db_size']) if db_stats['db_size'] else 0,
                    "database_size_mb": round(int(db_stats['db_size']) / (1024 * 1024), 2) if db_stats['db_size'] else 0,
                    "active_connections": db_stats['active_connections'],
                    "total_connections": db_stats['total_connections'],
                    "connection_pool": {
                        "min_connections": self.pool.minconn if self.pool else 0,
                        "max_connections": self.pool.maxconn if self.pool else 0,
                        "closed_connections": self.pool.closed if self.pool else 0
                    },
                    "top_tables": [dict(row) for row in table_stats] if table_stats else []
                }
                
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    def backup_table(self, table_name: str, backup_name: str = None) -> Dict[str, Any]:
        """Create backup of table"""
        if not self.available:
            return {'success': False, 'error': 'Database not available'}
        
        backup_name = backup_name or f"{table_name}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            with self.get_cursor() as (cursor, conn):
                # Create backup table
                cursor.execute(f'CREATE TABLE {backup_name} AS SELECT * FROM {table_name};')
                
                # Get row count
                cursor.execute(f'SELECT COUNT(*) FROM {backup_name};')
                row_count = cursor.fetchone()[0]
                
                conn.commit()
                
                return {
                    'success': True,
                    'backup_table': backup_name,
                    'rows_backed_up': row_count,
                    'original_table': table_name
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def cleanup_old_records(self, table: str, date_column: str, days_to_keep: int = 30) -> Dict[str, Any]:
        """Clean up old records from table"""
        if not self.available:
            return {'success': False, 'error': 'Database not available'}
        
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            with self.get_cursor() as (cursor, conn):
                # Count records to be deleted
                cursor.execute(f'SELECT COUNT(*) FROM {table} WHERE {date_column} < %s;', (cutoff_date,))
                records_to_delete = cursor.fetchone()[0]
                
                if records_to_delete > 0:
                    # Delete old records
                    cursor.execute(f'DELETE FROM {table} WHERE {date_column} < %s;', (cutoff_date,))
                    conn.commit()
                
                return {
                    'success': True,
                    'records_deleted': records_to_delete,
                    'cutoff_date': cutoff_date.isoformat(),
                    'table': table
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_slow_queries(self, limit: int = 10) -> Dict[str, Any]:
        """Get slow running queries (requires pg_stat_statements extension)"""
        if not self.available:
            return {'success': False, 'error': 'Database not available'}
        
        try:
            with self.get_cursor(cursor_factory=RealDictCursor) as (cursor, conn):
                # Check if pg_stat_statements is available
                cursor.execute('''
                    SELECT EXISTS (
                        SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'
                    );
                ''')
                
                has_pg_stat = cursor.fetchone()[0]
                
                if not has_pg_stat:
                    return {
                        'success': False,
                        'error': 'pg_stat_statements extension not installed'
                    }
                
                # Get slow queries
                cursor.execute(f'''
                    SELECT 
                        query,
                        calls,
                        total_time,
                        mean_time,
                        rows
                    FROM pg_stat_statements
                    ORDER BY mean_time DESC
                    LIMIT {limit};
                ''')
                
                slow_queries = cursor.fetchall()
                
                return {
                    'success': True,
                    'slow_queries': [dict(row) for row in slow_queries]
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def close_pool(self):
        """Close connection pool"""
        if self.pool:
            self.pool.closeall()
            print("🔒 Database connection pool closed")

# Global database manager instance
db_manager = None

def get_db_manager():
    """Get global database manager instance"""
    global db_manager
    if db_manager is None:
        db_manager = DatabaseManager()
    return db_manager

# Convenience functions for common operations
def execute_query(query: str, params: tuple = None, fetch: str = 'all'):
    """Execute query using global database manager"""
    return get_db_manager().execute_query(query, params, fetch)

def insert_record(table: str, data: Dict[str, Any], returning: str = 'id'):
    """Insert record using global database manager"""
    return get_db_manager().insert_record(table, data, returning)

def update_record(table: str, data: Dict[str, Any], where_condition: str, where_params: tuple = None):
    """Update record using global database manager"""
    return get_db_manager().update_record(table, data, where_condition, where_params)

def delete_record(table: str, where_condition: str, where_params: tuple = None):
    """Delete record using global database manager"""
    return get_db_manager().delete_record(table, where_condition, where_params)

def paginate_query(query: str, params: tuple = None, page: int = 1, per_page: int = 20, order_by: str = None) -> Dict[str, Any]:
    """Execute paginated query with total count"""
    if not get_db_manager().available:
        return {'success': False, 'error': 'Database not available'}
    
    try:
        # Calculate offset
        offset = (page - 1) * per_page
        
        # Add ORDER BY clause if specified
        if order_by:
            query = f"{query.rstrip(';')} ORDER BY {order_by}"
        
        # Get total count (without LIMIT/OFFSET)
        count_query = f"SELECT COUNT(*) FROM ({query}) as count_query"
        count_result = execute_query(count_query, params, fetch='one')
        
        if not count_result['success']:
            return count_result
        
        total_count = count_result['data'][0] if count_result['data'] else 0
        
        # Add pagination to original query
        paginated_query = f"{query} LIMIT %s OFFSET %s"
        paginated_params = (params or ()) + (per_page, offset)
        
        # Execute paginated query
        data_result = execute_query(paginated_query, paginated_params)
        
        if not data_result['success']:
            return data_result
        
        # Calculate pagination metadata
        total_pages = (total_count + per_page - 1) // per_page
        has_next = page < total_pages
        has_prev = page > 1
        
        return {
            'success': True,
            'data': data_result['data'],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_next': has_next,
                'has_prev': has_prev,
                'next_page': page + 1 if has_next else None,
                'prev_page': page - 1 if has_prev else None
            }
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# Database initialization and migration helpers
def create_tables_if_not_exist():
    """Create essential tables if they don't exist"""
    db = get_db_manager()
    
    if not db.available:
        print("⚠️  Database not available - skipping table creation")
        return False
    
    tables = {
        'users': '''
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(50) NOT NULL DEFAULT 'customer',
                status VARCHAR(50) DEFAULT 'active',
                profile JSONB DEFAULT '{}',
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP WITHOUT TIME ZONE,
                login_count INTEGER DEFAULT 0,
                email_verified BOOLEAN DEFAULT false,
                phone_verified BOOLEAN DEFAULT false,
                two_factor_enabled BOOLEAN DEFAULT false,
                preferences JSONB DEFAULT '{}',
                metadata JSONB DEFAULT '{}'
            );
        ''',
        'customers': '''
            CREATE TABLE IF NOT EXISTS customers (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                customer_type VARCHAR(50) DEFAULT 'individual',
                personal_info JSONB DEFAULT '{}',
                business_info JSONB DEFAULT '{}',
                contact_info JSONB DEFAULT '{}',
                billing_info JSONB DEFAULT '{}',
                preferences JSONB DEFAULT '{}',
                tags TEXT[] DEFAULT '{}',
                lifetime_value NUMERIC DEFAULT 0.00,
                total_policies INTEGER DEFAULT 0,
                active_policies INTEGER DEFAULT 0,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(50) DEFAULT 'active',
                notes JSONB DEFAULT '[]',
                assigned_agent VARCHAR(255)
            );
        ''',
        'products': '''
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                product_code VARCHAR(255) UNIQUE NOT NULL,
                product_name VARCHAR(255) NOT NULL,
                base_price NUMERIC NOT NULL,
                active BOOLEAN DEFAULT true,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        ''',
        'policies': '''
            CREATE TABLE IF NOT EXISTS policies (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                policy_number VARCHAR(255) UNIQUE NOT NULL,
                customer_id UUID REFERENCES customers(id),
                product_type VARCHAR(255) NOT NULL,
                product_details JSONB DEFAULT '{}',
                coverage_details JSONB DEFAULT '{}',
                pricing JSONB DEFAULT '{}',
                status VARCHAR(50) DEFAULT 'active',
                effective_date DATE,
                expiration_date DATE,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                created_by UUID REFERENCES users(id),
                payment_info JSONB DEFAULT '{}',
                claims JSONB DEFAULT '[]',
                documents JSONB DEFAULT '[]',
                notes JSONB DEFAULT '[]',
                renewal_info JSONB DEFAULT '{}'
            );
        ''',
        'transactions': '''
            CREATE TABLE IF NOT EXISTS transactions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                transaction_number VARCHAR(255) UNIQUE NOT NULL,
                customer_id UUID REFERENCES customers(id),
                policy_id UUID REFERENCES policies(id),
                type VARCHAR(50) NOT NULL,
                amount NUMERIC NOT NULL DEFAULT 0.00,
                currency VARCHAR(3) DEFAULT 'USD',
                status VARCHAR(50) DEFAULT 'pending',
                payment_method JSONB DEFAULT '{}',
                processor_response JSONB DEFAULT '{}',
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP WITHOUT TIME ZONE,
                created_by UUID REFERENCES users(id),
                metadata JSONB DEFAULT '{}',
                fees JSONB DEFAULT '{}',
                taxes JSONB DEFAULT '{}'
            );
        ''',
        'resellers': '''
            CREATE TABLE IF NOT EXISTS resellers (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES users(id),
                business_name VARCHAR(255) NOT NULL,
                license_number VARCHAR(255),
                license_state VARCHAR(2),
                business_type VARCHAR(50) DEFAULT 'insurance_agency',
                contact_info JSONB DEFAULT '{}',
                commission_structure JSONB DEFAULT '{}',
                sales_metrics JSONB DEFAULT '{}',
                status VARCHAR(50) DEFAULT 'pending',
                tier VARCHAR(50) DEFAULT 'bronze',
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP WITHOUT TIME ZONE,
                approved_by UUID REFERENCES users(id),
                documents JSONB DEFAULT '[]',
                territories TEXT[] DEFAULT '{}',
                product_access TEXT[] DEFAULT '{all}'
            );
        ''',
        'protection_plans': '''
            CREATE TABLE IF NOT EXISTS protection_plans (
                id SERIAL PRIMARY KEY,
                plan_id VARCHAR(255) UNIQUE NOT NULL,
                transaction_id UUID REFERENCES transactions(id),
                customer_email VARCHAR(255) NOT NULL,
                plan_type VARCHAR(100) NOT NULL,
                plan_name VARCHAR(255) NOT NULL,
                coverage_details JSONB,
                vehicle_info JSONB,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                status VARCHAR(50) DEFAULT 'active',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        ''',
        'vsc_coverage_levels': '''
            CREATE TABLE IF NOT EXISTS vsc_coverage_levels (
                id SERIAL PRIMARY KEY,
                level_code VARCHAR(50) UNIQUE NOT NULL,
                level_name VARCHAR(255) NOT NULL,
                description TEXT,
                covered_components TEXT[],
                benefits TEXT[],
                exclusions TEXT[],
                active BOOLEAN DEFAULT true,
                display_order INTEGER DEFAULT 0,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        ''',
        'vsc_rate_matrix': '''
            CREATE TABLE IF NOT EXISTS vsc_rate_matrix (
                id SERIAL PRIMARY KEY,
                vehicle_class CHAR(1) NOT NULL,
                coverage_level VARCHAR(50) NOT NULL REFERENCES vsc_coverage_levels(level_code),
                term_months INTEGER NOT NULL,
                mileage_range_key VARCHAR(50) NOT NULL,
                min_mileage INTEGER NOT NULL,
                max_mileage INTEGER NOT NULL,
                rate_amount NUMERIC NOT NULL,
                effective_date DATE NOT NULL DEFAULT CURRENT_DATE,
                active BOOLEAN DEFAULT true,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(vehicle_class, coverage_level, term_months, mileage_range_key, effective_date)
            );
        ''',
        'vsc_vehicle_classes': '''
            CREATE TABLE IF NOT EXISTS vsc_vehicle_classes (
                id SERIAL PRIMARY KEY,
                make VARCHAR(100) UNIQUE NOT NULL,
                vehicle_class CHAR(1) NOT NULL,
                class_description TEXT,
                active BOOLEAN DEFAULT true,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        ''',
        'admin_settings': '''
            CREATE TABLE IF NOT EXISTS admin_settings (
                id SERIAL PRIMARY KEY,
                category VARCHAR(100) NOT NULL,
                key VARCHAR(100) NOT NULL,
                value JSONB NOT NULL,
                description TEXT,
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_by UUID REFERENCES users(id),
                UNIQUE(category, key)
            );
        ''',
        'settings': '''
            CREATE TABLE IF NOT EXISTS settings (
                key VARCHAR(255) PRIMARY KEY,
                value JSONB NOT NULL,
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        ''',
        'pricing': '''
            CREATE TABLE IF NOT EXISTS pricing (
                id SERIAL PRIMARY KEY,
                product_code VARCHAR(255) NOT NULL,
                term_years INTEGER NOT NULL,
                multiplier NUMERIC NOT NULL,
                customer_type VARCHAR(50) DEFAULT 'retail',
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(product_code, term_years, customer_type)
            );
        ''',
        'dealers': '''
            CREATE TABLE IF NOT EXISTS dealers (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                license_number VARCHAR(255),
                contact_info JSONB DEFAULT '{}',
                pricing_overrides JSONB DEFAULT '{}',
                volume_discounts JSONB DEFAULT '{}',
                status VARCHAR(50) DEFAULT 'active',
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        ''',
        'tpas': '''
            CREATE TABLE IF NOT EXISTS tpas (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                api_endpoint VARCHAR(500),
                contact_email VARCHAR(255),
                contact_phone VARCHAR(50),
                status VARCHAR(50) DEFAULT 'active',
                authentication JSONB DEFAULT '{}',
                supported_products TEXT[] DEFAULT '{}',
                commission_rate NUMERIC DEFAULT 0.0000,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        '''
    }
    
    created_tables = []
    failed_tables = []
    
    try:
        with db.get_cursor() as (cursor, conn):
            for table_name, create_sql in tables.items():
                try:
                    cursor.execute(create_sql)
                    created_tables.append(table_name)
                    print(f"✅ Table '{table_name}' created/verified")
                except Exception as e:
                    failed_tables.append((table_name, str(e)))
                    print(f"❌ Failed to create table '{table_name}': {e}")
            
            # Create indexes
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_customers_user_id ON customers(user_id);",
                "CREATE INDEX IF NOT EXISTS idx_policies_customer_id ON policies(customer_id);",
                "CREATE INDEX IF NOT EXISTS idx_policies_status ON policies(status);",
                "CREATE INDEX IF NOT EXISTS idx_transactions_customer_id ON transactions(customer_id);",
                "CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);",
                "CREATE INDEX IF NOT EXISTS idx_protection_plans_customer_email ON protection_plans(customer_email);",
                "CREATE INDEX IF NOT EXISTS idx_protection_plans_status ON protection_plans(status);",
                "CREATE INDEX IF NOT EXISTS idx_vsc_rate_matrix_lookup ON vsc_rate_matrix(vehicle_class, coverage_level, term_months);",
                "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);",
                "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);"
            ]
            
            for index_sql in indexes:
                try:
                    cursor.execute(index_sql)
                except Exception as e:
                    print(f"⚠️  Index creation warning: {e}")
            
            conn.commit()
            
        print(f"🎉 Database initialization complete! Created/verified {len(created_tables)} tables")
        
        if failed_tables:
            print(f"⚠️  {len(failed_tables)} tables failed to create:")
            for table, error in failed_tables:
                print(f"   - {table}: {error}")
        
        return len(failed_tables) == 0
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False

def seed_initial_data():
    """Seed database with initial configuration data"""
    db = get_db_manager()
    
    if not db.available:
        print("⚠️  Database not available - skipping data seeding")
        return False
    
    try:
        # Check if data already exists
        result = db.execute_query("SELECT COUNT(*) FROM vsc_coverage_levels;")
        if result['success'] and result['data'][0][0] > 0:
            print("📋 Database already contains data - skipping seeding")
            return True
        
        # Seed VSC coverage levels
        coverage_levels = [
            {
                'level_code': 'BASIC',
                'level_name': 'Basic Coverage',
                'description': 'Essential powertrain coverage',
                'display_order': 1
            },
            {
                'level_code': 'PREMIUM',
                'level_name': 'Premium Coverage',
                'description': 'Comprehensive coverage with additional benefits',
                'display_order': 2
            },
            {
                'level_code': 'PLATINUM',
                'level_name': 'Platinum Coverage',
                'description': 'Ultimate coverage with maximum benefits',
                'display_order': 3
            }
        ]
        
        for level in coverage_levels:
            db.insert_record('vsc_coverage_levels', level)
        
        # Seed some vehicle classes
        vehicle_classes = [
            {'make': 'Toyota', 'vehicle_class': 'A', 'class_description': 'Reliable domestic vehicles'},
            {'make': 'Honda', 'vehicle_class': 'A', 'class_description': 'Reliable domestic vehicles'},
            {'make': 'Ford', 'vehicle_class': 'B', 'class_description': 'Standard domestic vehicles'},
            {'make': 'Chevrolet', 'vehicle_class': 'B', 'class_description': 'Standard domestic vehicles'},
            {'make': 'BMW', 'vehicle_class': 'C', 'class_description': 'Luxury import vehicles'},
            {'make': 'Mercedes-Benz', 'vehicle_class': 'C', 'class_description': 'Luxury import vehicles'},
            {'make': 'Audi', 'vehicle_class': 'C', 'class_description': 'Luxury import vehicles'},
            {'make': 'Nissan', 'vehicle_class': 'A', 'class_description': 'Reliable domestic vehicles'},
            {'make': 'Hyundai', 'vehicle_class': 'A', 'class_description': 'Economy vehicles'},
            {'make': 'Kia', 'vehicle_class': 'A', 'class_description': 'Economy vehicles'}
        ]
        
        for vehicle in vehicle_classes:
            db.insert_record('vsc_vehicle_classes', vehicle)
        
        # Seed basic settings
        settings_data = [
            {'key': 'company_name', 'value': json.dumps('VSC Insurance Company')},
            {'key': 'default_currency', 'value': json.dumps('USD')},
            {'key': 'max_policy_term_months', 'value': json.dumps(84)},
            {'key': 'min_policy_term_months', 'value': json.dumps(12)},
            {'key': 'system_timezone', 'value': json.dumps('UTC')}
        ]
        
        for setting in settings_data:
            db.insert_record('settings', setting)
        
        # Seed some basic products
        products = [
            {'product_code': 'VSC_BASIC', 'product_name': 'Basic Vehicle Service Contract', 'base_price': 1500.00},
            {'product_code': 'VSC_PREMIUM', 'product_name': 'Premium Vehicle Service Contract', 'base_price': 2500.00},
            {'product_code': 'VSC_PLATINUM', 'product_name': 'Platinum Vehicle Service Contract', 'base_price': 3500.00},
            {'product_code': 'GAP_BASIC', 'product_name': 'Basic GAP Coverage', 'base_price': 800.00},
            {'product_code': 'TIRE_WHEEL', 'product_name': 'Tire & Wheel Protection', 'base_price': 600.00}
        ]
        
        for product in products:
            db.insert_record('products', product)
        
        # Seed term multipliers
        term_multipliers = [
            {'term_months': 12, 'multiplier': 0.60, 'description': '1 Year Term'},
            {'term_months': 24, 'multiplier': 0.80, 'description': '2 Year Term'},
            {'term_months': 36, 'multiplier': 1.00, 'description': '3 Year Term'},
            {'term_months': 48, 'multiplier': 1.15, 'description': '4 Year Term'},
            {'term_months': 60, 'multiplier': 1.30, 'description': '5 Year Term'},
            {'term_months': 84, 'multiplier': 1.50, 'description': '7 Year Term'}
        ]
        
        for multiplier in term_multipliers:
            db.insert_record('vsc_term_multipliers', multiplier)
        
        # Seed mileage multipliers
        mileage_multipliers = [
            {'category': 'LOW', 'min_mileage': 0, 'max_mileage': 36000, 'multiplier': 0.90, 'description': 'Low Mileage (0-36k)'},
            {'category': 'MEDIUM', 'min_mileage': 36001, 'max_mileage': 75000, 'multiplier': 1.00, 'description': 'Medium Mileage (36k-75k)'},
            {'category': 'HIGH', 'min_mileage': 75001, 'max_mileage': 100000, 'multiplier': 1.15, 'description': 'High Mileage (75k-100k)'},
            {'category': 'VERY_HIGH', 'min_mileage': 100001, 'max_mileage': 125000, 'multiplier': 1.30, 'description': 'Very High Mileage (100k-125k)'},
            {'category': 'EXTREME', 'min_mileage': 125001, 'max_mileage': 150000, 'multiplier': 1.50, 'description': 'Extreme Mileage (125k-150k)'},
            {'category': 'MAX', 'min_mileage': 150001, 'max_mileage': 999999, 'multiplier': 2.00, 'description': 'Maximum Mileage (150k+)'}
        ]
        
        for mileage in mileage_multipliers:
            db.insert_record('vsc_mileage_multipliers', mileage)
        
        # Seed some base rates for VSC
        base_rates = [
            {'vehicle_class': 'A', 'coverage_level': 'BASIC', 'base_rate': 800.00},
            {'vehicle_class': 'A', 'coverage_level': 'PREMIUM', 'base_rate': 1200.00},
            {'vehicle_class': 'A', 'coverage_level': 'PLATINUM', 'base_rate': 1600.00},
            {'vehicle_class': 'B', 'coverage_level': 'BASIC', 'base_rate': 900.00},
            {'vehicle_class': 'B', 'coverage_level': 'PREMIUM', 'base_rate': 1350.00},
            {'vehicle_class': 'B', 'coverage_level': 'PLATINUM', 'base_rate': 1800.00},
            {'vehicle_class': 'C', 'coverage_level': 'BASIC', 'base_rate': 1200.00},
            {'vehicle_class': 'C', 'coverage_level': 'PREMIUM', 'base_rate': 1800.00},
            {'vehicle_class': 'C', 'coverage_level': 'PLATINUM', 'base_rate': 2400.00}
        ]
        
        for rate in base_rates:
            db.insert_record('vsc_base_rates', rate)
        
        # Create default admin user (password should be hashed in production)
        admin_user = {
            'email': 'admin@example.com',
            'password_hash': 'temp_password_hash',  # Replace with proper hash
            'role': 'admin',
            'status': 'active',
            'email_verified': True,
            'profile': json.dumps({
                'first_name': 'System',
                'last_name': 'Administrator',
                'created_by': 'system_init'
            })
        }
        
        admin_result = db.insert_record('users', admin_user)
        
        if admin_result['success']:
            # Add admin settings
            admin_settings = [
                {'category': 'system', 'key': 'maintenance_mode', 'value': json.dumps(False), 'description': 'System maintenance mode flag'},
                {'category': 'pricing', 'key': 'default_commission_rate', 'value': json.dumps(0.15), 'description': 'Default commission rate for resellers'},
                {'category': 'notifications', 'key': 'email_enabled', 'value': json.dumps(True), 'description': 'Email notifications enabled'},
                {'category': 'security', 'key': 'password_expiry_days', 'value': json.dumps(90), 'description': 'Password expiry in days'},
                {'category': 'business', 'key': 'max_policy_amount', 'value': json.dumps(10000.00), 'description': 'Maximum policy amount'}
            ]
            
            for setting in admin_settings:
                setting['updated_by'] = admin_result['inserted_id']
                db.insert_record('admin_settings', setting)
        
        print("🌱 Initial data seeded successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Data seeding failed: {e}")
        return False

def migrate_database():
    """Run database migrations"""
    db = get_db_manager()
    
    if not db.available:
        print("⚠️  Database not available - skipping migrations")
        return False
    
    try:
        # Create migration tracking table if it doesn't exist
        migration_table = '''
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id SERIAL PRIMARY KEY,
                version VARCHAR(50) UNIQUE NOT NULL,
                description TEXT,
                applied_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        '''
        
        db.execute_query(migration_table)
        
        # Define migrations
        migrations = [
            {
                'version': '001_add_updated_at_triggers',
                'description': 'Add updated_at triggers for automatic timestamp updates',
                'sql': '''
                    CREATE OR REPLACE FUNCTION update_updated_at_column()
                    RETURNS TRIGGER AS $
                    BEGIN
                        NEW.updated_at = CURRENT_TIMESTAMP;
                        RETURN NEW;
                    END;
                    $ language 'plpgsql';
                    
                    -- Add triggers for tables with updated_at columns
                    DROP TRIGGER IF EXISTS update_users_updated_at ON users;
                    CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
                        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
                    
                    DROP TRIGGER IF EXISTS update_customers_updated_at ON customers;
                    CREATE TRIGGER update_customers_updated_at BEFORE UPDATE ON customers
                        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
                    
                    DROP TRIGGER IF EXISTS update_policies_updated_at ON policies;
                    CREATE TRIGGER update_policies_updated_at BEFORE UPDATE ON policies
                        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
                '''
            },
            {
                'version': '002_add_audit_log_table',
                'description': 'Add audit log table for tracking changes',
                'sql': '''
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        table_name VARCHAR(100) NOT NULL,
                        record_id VARCHAR(100) NOT NULL,
                        action VARCHAR(20) NOT NULL, -- INSERT, UPDATE, DELETE
                        old_values JSONB,
                        new_values JSONB,
                        changed_by UUID REFERENCES users(id),
                        changed_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        ip_address INET,
                        user_agent TEXT
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_audit_log_table_record ON audit_log(table_name, record_id);
                    CREATE INDEX IF NOT EXISTS idx_audit_log_changed_at ON audit_log(changed_at);
                    CREATE INDEX IF NOT EXISTS idx_audit_log_changed_by ON audit_log(changed_by);
                '''
            },
            {
                'version': '003_add_rate_history_tracking',
                'description': 'Add rate history tracking table',
                'sql': '''
                    CREATE TABLE IF NOT EXISTS vsc_rate_history (
                        id SERIAL PRIMARY KEY,
                        table_name VARCHAR(100) NOT NULL,
                        record_id INTEGER NOT NULL,
                        field_name VARCHAR(100) NOT NULL,
                        old_value TEXT,
                        new_value TEXT,
                        changed_by UUID REFERENCES users(id),
                        changed_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        change_reason TEXT
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_vsc_rate_history_table_record ON vsc_rate_history(table_name, record_id);
                '''
            }
        ]
        
        # Check and apply migrations
        applied_migrations = []
        
        for migration in migrations:
            # Check if migration already applied
            check_result = db.execute_query(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = %s;",
                (migration['version'],)
            )
            
            if check_result['success'] and check_result['data'][0][0] == 0:
                try:
                    # Apply migration
                    db.execute_query(migration['sql'])
                    
                    # Record migration
                    db.insert_record('schema_migrations', {
                        'version': migration['version'],
                        'description': migration['description']
                    })
                    
                    applied_migrations.append(migration['version'])
                    print(f"✅ Applied migration: {migration['version']}")
                    
                except Exception as e:
                    print(f"❌ Failed to apply migration {migration['version']}: {e}")
                    return False
            else:
                print(f"⏭️  Migration {migration['version']} already applied")
        
        if applied_migrations:
            print(f"🚀 Applied {len(applied_migrations)} migrations successfully!")
        else:
            print("📋 All migrations up to date")
        
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

def initialize_database():
    """Complete database initialization - creates tables, runs migrations, and seeds data"""
    print("🚀 Starting database initialization...")
    
    # Step 1: Create tables
    if not create_tables_if_not_exist():
        print("❌ Table creation failed")
        return False
    
    # Step 2: Run migrations
    if not migrate_database():
        print("❌ Migrations failed")
        return False
    
    # Step 3: Seed initial data
    if not seed_initial_data():
        print("❌ Data seeding failed")
        return False
    
    print("🎉 Database initialization completed successfully!")
    return True

# Additional utility functions for the insurance/VSC system

def calculate_vsc_price(vehicle_class: str, coverage_level: str, term_months: int, 
                       mileage: int, customer_type: str = 'retail') -> Dict[str, Any]:
    """Calculate VSC pricing based on vehicle and coverage parameters"""
    db = get_db_manager()
    
    if not db.available:
        return {'success': False, 'error': 'Database not available'}
    
    try:
        # Get base rate
        base_rate_query = '''
            SELECT base_rate FROM vsc_base_rates 
            WHERE vehicle_class = %s AND coverage_level = %s AND active = true
            ORDER BY effective_date DESC LIMIT 1;
        '''
        
        base_result = db.execute_query(base_rate_query, (vehicle_class, coverage_level))
        
        if not base_result['success'] or not base_result['data']:
            return {'success': False, 'error': 'Base rate not found'}
        
        base_rate = float(base_result['data'][0][0])
        
        # Get term multiplier
        term_query = '''
            SELECT multiplier FROM vsc_term_multipliers 
            WHERE term_months = %s AND active = true;
        '''
        
        term_result = db.execute_query(term_query, (term_months,))
        term_multiplier = float(term_result['data'][0][0]) if term_result['success'] and term_result['data'] else 1.0
        
        # Get mileage multiplier
        mileage_query = '''
            SELECT multiplier FROM vsc_mileage_multipliers 
            WHERE min_mileage <= %s AND max_mileage >= %s AND active = true;
        '''
        
        mileage_result = db.execute_query(mileage_query, (mileage, mileage))
        mileage_multiplier = float(mileage_result['data'][0][0]) if mileage_result['success'] and mileage_result['data'] else 1.0
        
        # Calculate final price
        calculated_price = base_rate * term_multiplier * mileage_multiplier
        
        # Apply customer type pricing if available
        if customer_type != 'retail':
            pricing_query = '''
                SELECT multiplier FROM pricing 
                WHERE customer_type = %s 
                ORDER BY updated_at DESC LIMIT 1;
            '''
            
            pricing_result = db.execute_query(pricing_query, (customer_type,))
            if pricing_result['success'] and pricing_result['data']:
                customer_multiplier = float(pricing_result['data'][0][0])
                calculated_price *= customer_multiplier
        
        return {
            'success': True,
            'calculated_price': round(calculated_price, 2),
            'calculation_details': {
                'base_rate': base_rate,
                'term_multiplier': term_multiplier,
                'mileage_multiplier': mileage_multiplier,
                'customer_type': customer_type,
                'vehicle_class': vehicle_class,
                'coverage_level': coverage_level,
                'term_months': term_months,
                'mileage': mileage
            }
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def create_vsc_quote(customer_id: str, vehicle_info: Dict[str, Any], 
                    coverage_details: Dict[str, Any], created_by: str = None) -> Dict[str, Any]:
    """Create a new VSC quote"""
    db = get_db_manager()
    
    if not db.available:
        return {'success': False, 'error': 'Database not available'}
    
    try:
        # Generate quote number
        quote_number = f"VSC-{datetime.now().strftime('%Y%m%d')}-{int(time.time() * 1000) % 100000:05d}"
        
        # Calculate pricing
        price_result = calculate_vsc_price(
            vehicle_info.get('vehicle_class'),
            coverage_details.get('coverage_level'),
            coverage_details.get('term_months'),
            vehicle_info.get('mileage'),
            coverage_details.get('customer_type', 'retail')
        )
        
        if not price_result['success']:
            return price_result
        
        # Create quote record
        quote_data = {
            'quote_number': quote_number,
            'customer_id': customer_id,
            'vehicle_make': vehicle_info.get('make'),
            'vehicle_year': vehicle_info.get('year'),
            'vehicle_mileage': vehicle_info.get('mileage'),
            'coverage_level': coverage_details.get('coverage_level'),
            'term_months': coverage_details.get('term_months'),
            'deductible_amount': coverage_details.get('deductible_amount', 100),
            'calculated_price': price_result['calculated_price'],
            'final_price': price_result['calculated_price'],
            'customer_type': coverage_details.get('customer_type', 'retail'),
            'calculation_details': json.dumps(price_result['calculation_details']),
            'status': 'draft',
            'expires_at': datetime.now() + timedelta(days=30),
            'created_by': created_by
        }
        
        result = db.insert_record('vsc_quotes', quote_data)
        
        if result['success']:
            result['quote_number'] = quote_number
            result['calculated_price'] = price_result['calculated_price']
        
        return result
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def get_dashboard_metrics() -> Dict[str, Any]:
    """Get key business metrics for dashboard"""
    db = get_db_manager()
    
    if not db.available:
        return {'success': False, 'error': 'Database not available'}
    
    try:
        metrics = {}
        
        # Customer metrics
        customer_query = '''
            SELECT 
                COUNT(*) as total_customers,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active_customers,
                COUNT(CASE WHEN created_at >= CURRENT_DATE - INTERVAL '30 days' THEN 1 END) as new_customers_30d
            FROM customers;
        '''
        
        customer_result = db.execute_query(customer_query)
        if customer_result['success'] and customer_result['data']:
            row = customer_result['data'][0]
            metrics['customers'] = {
                'total': row[0],
                'active': row[1],
                'new_30_days': row[2]
            }
        
        # Policy metrics
        policy_query = '''
            SELECT 
                COUNT(*) as total_policies,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active_policies,
                COUNT(CASE WHEN created_at >= CURRENT_DATE - INTERVAL '30 days' THEN 1 END) as new_policies_30d,
                AVG(CAST(pricing->>'calculated_price' AS NUMERIC)) as avg_policy_value
            FROM policies;
        '''
        
        policy_result = db.execute_query(policy_query)
        if policy_result['success'] and policy_result['data']:
            row = policy_result['data'][0]
            metrics['policies'] = {
                'total': row[0],
                'active': row[1],
                'new_30_days': row[2],
                'average_value': float(row[3]) if row[3] else 0
            }
        
        # Transaction metrics
        transaction_query = '''
            SELECT 
                COUNT(*) as total_transactions,
                SUM(amount) as total_amount,
                SUM(CASE WHEN created_at >= CURRENT_DATE - INTERVAL '30 days' THEN amount ELSE 0 END) as amount_30d,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_transactions
            FROM transactions;
        '''
        
        transaction_result = db.execute_query(transaction_query)
        if transaction_result['success'] and transaction_result['data']:
            row = transaction_result['data'][0]
            metrics['transactions'] = {
                'total': row[0],
                'total_amount': float(row[1]) if row[1] else 0,
                'amount_30_days': float(row[2]) if row[2] else 0,
                'completed': row[3]
            }
        
        # Quote metrics
        quote_query = '''
            SELECT 
                COUNT(*) as total_quotes,
                COUNT(CASE WHEN status = 'draft' THEN 1 END) as draft_quotes,
                COUNT(CASE WHEN created_at >= CURRENT_DATE - INTERVAL '7 days' THEN 1 END) as quotes_7d,
                AVG(calculated_price) as avg_quote_value
            FROM vsc_quotes;
        '''
        
        quote_result = db.execute_query(quote_query)
        if quote_result['success'] and quote_result['data']:
            row = quote_result['data'][0]
            metrics['quotes'] = {
                'total': row[0],
                'draft': row[1],
                'new_7_days': row[2],
                'average_value': float(row[3]) if row[3] else 0
            }
        
        return {'success': True, 'metrics': metrics}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

# Example usage and testing
if __name__ == "__main__":
    # Initialize database manager
    db = get_db_manager()
    
    if db.available:
        print("🔧 Testing database connection...")
        test_result = db.test_connection()
        print(f"Connection test: {test_result}")
        
        print("\n🏗️  Initializing database...")
        initialize_database()
        
        print("\n📊 Getting dashboard metrics...")
        metrics = get_dashboard_metrics()
        print(f"Metrics: {metrics}")
        
    else:
        print("❌ Database not available for testing")

# Cleanup function for graceful shutdown
def cleanup_database():
    """Clean up database connections"""
    global db_manager
    if db_manager:
        db_manager.close_pool()
        db_manager = None
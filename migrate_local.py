#!/usr/bin/env python3
"""
migrate_local.py - Run this locally to set up your Neon database
FIXED VERSION - Handles duplicates and cursor management
"""

import psycopg2

# Your Neon connection string
DATABASE_URL = "postgres://neondb_owner:npg_qH6nhmdrSFL1@ep-tiny-water-adje4r08-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"


def create_user_tables():
    """Create user management tables"""
    user_tables = [
        # Users table
        '''
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(50) DEFAULT 'customer',
            status VARCHAR(20) DEFAULT 'active',
            profile JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            login_count INTEGER DEFAULT 0,
            email_verified BOOLEAN DEFAULT FALSE,
            phone_verified BOOLEAN DEFAULT FALSE,
            two_factor_enabled BOOLEAN DEFAULT FALSE,
            preferences JSONB DEFAULT '{}',
            metadata JSONB DEFAULT '{}'
        );
        ''',

        # Customers table
        '''
        CREATE TABLE IF NOT EXISTS customers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            customer_type VARCHAR(20) DEFAULT 'individual',
            personal_info JSONB DEFAULT '{}',
            business_info JSONB DEFAULT '{}',
            contact_info JSONB DEFAULT '{}',
            billing_info JSONB DEFAULT '{}',
            preferences JSONB DEFAULT '{}',
            tags TEXT[] DEFAULT '{}',
            lifetime_value DECIMAL(12,2) DEFAULT 0.00,
            total_policies INTEGER DEFAULT 0,
            active_policies INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT 'active',
            notes JSONB DEFAULT '[]',
            assigned_agent VARCHAR(255)
        );
        ''',

        # Resellers table
        '''
        CREATE TABLE IF NOT EXISTS resellers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            business_name VARCHAR(255) NOT NULL,
            license_number VARCHAR(100),
            license_state VARCHAR(2),
            business_type VARCHAR(50) DEFAULT 'insurance_agency',
            contact_info JSONB DEFAULT '{}',
            commission_structure JSONB DEFAULT '{}',
            sales_metrics JSONB DEFAULT '{}',
            status VARCHAR(20) DEFAULT 'pending',
            tier VARCHAR(20) DEFAULT 'bronze',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP,
            approved_by UUID REFERENCES users(id),
            documents JSONB DEFAULT '[]',
            territories TEXT[] DEFAULT '{}',
            product_access TEXT[] DEFAULT '{all}'
        );
        ''',

        # Policies table
        '''
        CREATE TABLE IF NOT EXISTS policies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            policy_number VARCHAR(100) UNIQUE NOT NULL,
            customer_id UUID REFERENCES customers(id),
            product_type VARCHAR(100) NOT NULL,
            product_details JSONB DEFAULT '{}',
            coverage_details JSONB DEFAULT '{}',
            pricing JSONB DEFAULT '{}',
            status VARCHAR(20) DEFAULT 'active',
            effective_date DATE,
            expiration_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by UUID REFERENCES users(id),
            payment_info JSONB DEFAULT '{}',
            claims JSONB DEFAULT '[]',
            documents JSONB DEFAULT '[]',
            notes JSONB DEFAULT '[]',
            renewal_info JSONB DEFAULT '{}'
        );
        ''',

        # Transactions table
        '''
        CREATE TABLE IF NOT EXISTS transactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            transaction_number VARCHAR(100) UNIQUE NOT NULL,
            customer_id UUID REFERENCES customers(id),
            policy_id UUID REFERENCES policies(id),
            type VARCHAR(50) NOT NULL,
            amount DECIMAL(12,2) NOT NULL DEFAULT 0.00,
            currency VARCHAR(3) DEFAULT 'USD',
            status VARCHAR(20) DEFAULT 'pending',
            payment_method JSONB DEFAULT '{}',
            processor_response JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP,
            created_by UUID REFERENCES users(id),
            metadata JSONB DEFAULT '{}',
            fees JSONB DEFAULT '{}',
            taxes JSONB DEFAULT '{}'
        );
        ''',

        # TPAs table
        '''
        CREATE TABLE IF NOT EXISTS tpas (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            api_endpoint VARCHAR(500),
            contact_email VARCHAR(255),
            contact_phone VARCHAR(50),
            status VARCHAR(20) DEFAULT 'active',
            authentication JSONB DEFAULT '{}',
            supported_products TEXT[] DEFAULT '{}',
            commission_rate DECIMAL(5,4) DEFAULT 0.0000,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''',

        # Admin settings table (enhanced)
        '''
        CREATE TABLE IF NOT EXISTS admin_settings (
            id SERIAL PRIMARY KEY,
            category VARCHAR(100) NOT NULL,
            key VARCHAR(100) NOT NULL,
            value JSONB NOT NULL,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by UUID REFERENCES users(id),
            UNIQUE(category, key)
        );
        '''
    ]
    return user_tables


def clear_user_data(cursor):
    """Clear existing user data to avoid duplicates"""
    try:
        print("🧹 Clearing existing user data...")
        # Clear in dependency order
        cursor.execute("DELETE FROM admin_settings;")
        cursor.execute("DELETE FROM transactions;")
        cursor.execute("DELETE FROM policies;")
        cursor.execute("DELETE FROM tpas;")
        cursor.execute("DELETE FROM customers;")
        cursor.execute("DELETE FROM resellers;")
        cursor.execute("DELETE FROM users;")
        print("✅ User data cleared")
    except Exception as e:
        print(f"⚠️ Warning: Could not clear user data: {e}")


def insert_sample_user_data(cursor):
    """Insert sample user data with error handling"""
    
    try:
        # Insert admin user
        cursor.execute('''
            INSERT INTO users (email, password_hash, role, profile, status) 
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        ''', (
            'admin@connectedautocare.com',
            '$2b$12$LQv3c1yqBwlVHpPAHKvhXu.gHfUZLXVj3XnVKgqR8w.NjG1L5/GjW',  # 'admin123'
            'admin',
            '{"first_name": "System", "last_name": "Administrator", "company": "ConnectedAutoCare"}',
            'active'
        ))
        admin_id = cursor.fetchone()[0]
        print("✅ Admin user created")

        # Insert sample wholesale reseller
        cursor.execute('''
            INSERT INTO users (email, password_hash, role, profile, status) 
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        ''', (
            'reseller@example.com',
            '$2b$12$LQv3c1yqBwlVHpPAHKvhXu.gHfUZLXVj3XnVKgqR8w.NjG1L5/GjW',  # 'reseller123'
            'wholesale_reseller',
            '{"first_name": "John", "last_name": "Smith", "company": "ABC Insurance Agency"}',
            'active'
        ))
        reseller_user_id = cursor.fetchone()[0]
        print("✅ Reseller user created")

        # Insert reseller profile
        cursor.execute('''
            INSERT INTO resellers (user_id, business_name, license_number, license_state, contact_info, status) 
            VALUES (%s, %s, %s, %s, %s, %s);
        ''', (
            reseller_user_id,
            'ABC Insurance Agency',
            'INS-12345',
            'CA',
            '{"phone": "555-123-4567", "email": "reseller@example.com"}',
            'active'
        ))
        print("✅ Reseller profile created")

        # Insert sample customer
        cursor.execute('''
            INSERT INTO users (email, password_hash, role, profile, status) 
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        ''', (
            'customer@example.com',
            '$2b$12$LQv3c1yqBwlVHpPAHKvhXu.gHfUZLXVj3XnVKgqR8w.NjG1L5/GjW',  # 'customer123'
            'customer',
            '{"first_name": "Jane", "last_name": "Doe"}',
            'active'
        ))
        customer_user_id = cursor.fetchone()[0]
        print("✅ Customer user created")

        # Insert customer profile
        cursor.execute('''
            INSERT INTO customers (user_id, personal_info, contact_info) 
            VALUES (%s, %s, %s);
        ''', (
            customer_user_id,
            '{"first_name": "Jane", "last_name": "Doe"}',
            '{"email": "customer@example.com", "phone": "555-987-6543"}'
        ))
        print("✅ Customer profile created")

        # Insert sample TPAs
        tpas_data = [
            ('Warranty Solutions Inc', 'https://api.warrantysolutions.com', 'partners@warrantysolutions.com'),
            ('Service Contract Corp', 'https://partners.servicecontract.com', 'api@servicecontract.com'),
            ('AutoGuard Services', 'https://api.autoguard.com', 'integration@autoguard.com')
        ]

        for name, endpoint, email in tpas_data:
            cursor.execute('''
                INSERT INTO tpas (name, api_endpoint, contact_email, supported_products) 
                VALUES (%s, %s, %s, %s);
            ''', (name, endpoint, email, ['vsc', 'hero_home', 'hero_auto']))
        print(f"✅ Inserted {len(tpas_data)} TPAs")

        # Insert admin settings
        settings_data = [
            ('discounts', 'wholesale_discount', '0.15', 'Default wholesale discount rate'),
            ('discounts', 'volume_discount_threshold', '10', 'Minimum policies for volume discount'),
            ('discounts', 'volume_discount_rate', '0.05', 'Volume discount rate'),
            ('fees', 'admin_fee', '25.00', 'Administrative fee'),
            ('fees', 'processing_fee', '15.00', 'Payment processing fee'),
            ('fees', 'dealer_fee', '50.00', 'Dealer commission fee'),
            ('markups', 'retail_markup', '1.0', 'Retail price multiplier'),
            ('markups', 'wholesale_markup', '0.85', 'Wholesale price multiplier'),
            ('video', 'landing_page_url', '"https://cdn.connectedautocare.com/videos/hero-2025.mp4"', 'Landing page video URL'),
            ('video', 'landing_page_thumbnail', '"https://cdn.connectedautocare.com/thumbnails/hero-2025.jpg"', 'Video thumbnail URL')
        ]

        for category, key, value, description in settings_data:
            cursor.execute('''
                INSERT INTO admin_settings (category, key, value, description, updated_by) 
                VALUES (%s, %s, %s, %s, %s);
            ''', (category, key, value, description, admin_id))
        print(f"✅ Inserted {len(settings_data)} admin settings")

        return admin_id

    except Exception as e:
        print(f"❌ Error inserting user data: {e}")
        raise


def run_migration():
    print("🚀 Starting ConnectedAutoCare database migration...")

    try:
        # Connect to Neon
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        print("✅ Connected to Neon database")

        # Create basic tables first
        print("📊 Creating basic tables...")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                product_code VARCHAR(100) UNIQUE NOT NULL,
                product_name VARCHAR(255) NOT NULL,
                base_price DECIMAL(10,2) NOT NULL,
                active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        print("✅ Created products table")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pricing (
                id SERIAL PRIMARY KEY,
                product_code VARCHAR(100) NOT NULL,
                term_years INTEGER NOT NULL,
                multiplier DECIMAL(5,3) NOT NULL,
                customer_type VARCHAR(20) DEFAULT 'retail',
                UNIQUE(product_code, term_years, customer_type)
            );
        ''')
        print("✅ Created pricing table")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key VARCHAR(100) PRIMARY KEY,
                value JSONB NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        print("✅ Created settings table")

        # Clear existing basic data
        print("🧹 Clearing existing basic data...")
        cursor.execute("DELETE FROM pricing;")
        cursor.execute("DELETE FROM products;")
        cursor.execute("DELETE FROM settings;")

        # Insert July 2025 products
        print("📦 Inserting products...")
        products = [
            ('HOME_PROTECTION_PLAN', 'Home Protection Plan', 199),
            ('COMPREHENSIVE_AUTO_PROTECTION', 'Comprehensive Auto Protection', 339),
            ('HOME_DEDUCTIBLE_REIMBURSEMENT', 'Home Deductible Reimbursement', 160),
            ('AUTO_ADVANTAGE_DEDUCTIBLE_REIMBURSEMENT', 'Auto Advantage Deductible Reimbursement', 120),
            ('MULTI_VEHICLE_DEDUCTIBLE_REIMBURSEMENT', 'Multi Vehicle Deductible Reimbursement', 150),
            ('ALL_VEHICLE_DEDUCTIBLE_REIMBURSEMENT', 'All Vehicle Deductible Reimbursement', 150),
            ('AUTO_RV_DEDUCTIBLE_REIMBURSEMENT', 'Auto & RV Deductible Reimbursement', 175),
            ('HERO_LEVEL_HOME_PROTECTION', 'Hero-Level Protection for Your Home', 789)
        ]

        for code, name, price in products:
            cursor.execute(
                "INSERT INTO products (product_code, product_name, base_price) VALUES (%s, %s, %s)",
                (code, name, price)
            )
        print(f"✅ Inserted {len(products)} products")

        # Insert July 2025 pricing data
        print("💰 Inserting pricing data...")
        pricing_data = [
            # Home Protection Plan: $199-$599 (1-5 years)
            ('HOME_PROTECTION_PLAN', 1, 1.0), ('HOME_PROTECTION_PLAN', 2, 1.51),
            ('HOME_PROTECTION_PLAN', 3, 2.01), ('HOME_PROTECTION_PLAN', 4, 2.51),
            ('HOME_PROTECTION_PLAN', 5, 3.01),

            # Comprehensive Auto Protection: $339-$1,099 (1-5 years)
            ('COMPREHENSIVE_AUTO_PROTECTION', 1, 1.0), ('COMPREHENSIVE_AUTO_PROTECTION', 2, 1.77),
            ('COMPREHENSIVE_AUTO_PROTECTION', 3, 2.36), ('COMPREHENSIVE_AUTO_PROTECTION', 4, 2.95),
            ('COMPREHENSIVE_AUTO_PROTECTION', 5, 3.24),

            # Home Deductible Reimbursement: $160-$255 (1-3 years)
            ('HOME_DEDUCTIBLE_REIMBURSEMENT', 1, 1.0), ('HOME_DEDUCTIBLE_REIMBURSEMENT', 2, 1.34),
            ('HOME_DEDUCTIBLE_REIMBURSEMENT', 3, 1.59),

            # Auto Advantage: $120-$225 (1-3 years)
            ('AUTO_ADVANTAGE_DEDUCTIBLE_REIMBURSEMENT', 1, 1.0), ('AUTO_ADVANTAGE_DEDUCTIBLE_REIMBURSEMENT', 2, 1.50),
            ('AUTO_ADVANTAGE_DEDUCTIBLE_REIMBURSEMENT', 3, 1.88),

            # Multi Vehicle: $150-$275 (1-3 years)
            ('MULTI_VEHICLE_DEDUCTIBLE_REIMBURSEMENT', 1, 1.0), ('MULTI_VEHICLE_DEDUCTIBLE_REIMBURSEMENT', 2, 1.50),
            ('MULTI_VEHICLE_DEDUCTIBLE_REIMBURSEMENT', 3, 1.83),

            # All Vehicle: $150-$275 (1-3 years)
            ('ALL_VEHICLE_DEDUCTIBLE_REIMBURSEMENT', 1, 1.0), ('ALL_VEHICLE_DEDUCTIBLE_REIMBURSEMENT', 2, 1.50),
            ('ALL_VEHICLE_DEDUCTIBLE_REIMBURSEMENT', 3, 1.83),

            # Auto & RV: $175-$280 (1-3 years)
            ('AUTO_RV_DEDUCTIBLE_REIMBURSEMENT', 1, 1.0), ('AUTO_RV_DEDUCTIBLE_REIMBURSEMENT', 2, 1.43),
            ('AUTO_RV_DEDUCTIBLE_REIMBURSEMENT', 3, 1.60),

            # Hero-Level Home: $789-$1,295 (1-3 years)
            ('HERO_LEVEL_HOME_PROTECTION', 1, 1.0), ('HERO_LEVEL_HOME_PROTECTION', 2, 1.39),
            ('HERO_LEVEL_HOME_PROTECTION', 3, 1.64),
        ]

        pricing_count = 0
        for code, term, multiplier in pricing_data:
            # Retail pricing
            cursor.execute(
                "INSERT INTO pricing (product_code, term_years, multiplier, customer_type) VALUES (%s, %s, %s, %s)",
                (code, term, multiplier, 'retail')
            )
            pricing_count += 1

            # Wholesale pricing (15% discount)
            wholesale_multiplier = multiplier * 0.85
            cursor.execute(
                "INSERT INTO pricing (product_code, term_years, multiplier, customer_type) VALUES (%s, %s, %s, %s)",
                (code, term, wholesale_multiplier, 'wholesale')
            )
            pricing_count += 1

        print(f"✅ Inserted {pricing_count} pricing records")

        # Insert basic settings
        print("⚙️ Inserting basic settings...")
        cursor.execute("INSERT INTO settings (key, value) VALUES (%s, %s)",
                       ('contact_phone', '"1-(866) 660-7003"'))
        cursor.execute("INSERT INTO settings (key, value) VALUES (%s, %s)",
                       ('contact_email', '"support@connectedautocare.com"'))
        cursor.execute("INSERT INTO settings (key, value) VALUES (%s, %s)",
                       ('pricing_updated', '"July 2025"'))
        cursor.execute("INSERT INTO settings (key, value) VALUES (%s, %s)",
                       ('wholesale_discount', '0.15'))
        print("✅ Inserted basic settings")

        # Create user management tables
        print("👥 Creating user management tables...")
        user_tables = create_user_tables()
        
        for i, table_sql in enumerate(user_tables):
            cursor.execute(table_sql)
            table_names = ['users', 'customers', 'resellers', 'policies', 'transactions', 'tpas', 'admin_settings']
            table_name = table_names[i] if i < len(table_names) else f'table_{i+1}'
            print(f"✅ Created {table_name} table")
        
        # Clear existing user data to avoid duplicates
        clear_user_data(cursor)
        
        # Insert sample user data
        print("📝 Inserting sample user data...")
        admin_id = insert_sample_user_data(cursor)
        
        # Commit all changes
        conn.commit()
        print("💾 All changes committed")

        # Test the data (KEEP CURSOR OPEN!)
        print("🧪 Testing basic data...")
        cursor.execute('''
            SELECT p.product_name, p.base_price, pr.term_years, pr.multiplier, pr.customer_type,
                   ROUND(p.base_price * pr.multiplier, 2) as final_price
            FROM products p 
            JOIN pricing pr ON p.product_code = pr.product_code 
            WHERE p.product_code = 'HOME_PROTECTION_PLAN' 
            AND pr.customer_type = 'retail'
            ORDER BY pr.term_years;
        ''')

        results = cursor.fetchall()
        print("\n📋 Sample pricing for Home Protection Plan (Retail):")
        for row in results:
            name, base_price, term, multiplier, cust_type, final_price = row
            print(f"  {term} year(s): ${final_price} (${base_price} × {multiplier})")

        print("\n🧪 Testing user data...")
        cursor.execute("SELECT COUNT(*) FROM users;")
        user_count = cursor.fetchone()[0]
        print(f"   Users: {user_count}")
        
        cursor.execute("SELECT COUNT(*) FROM customers;")
        customer_count = cursor.fetchone()[0]
        print(f"   Customers: {customer_count}")
        
        cursor.execute("SELECT COUNT(*) FROM resellers;")
        reseller_count = cursor.fetchone()[0]
        print(f"   Resellers: {reseller_count}")
        
        cursor.execute("SELECT COUNT(*) FROM tpas;")
        tpa_count = cursor.fetchone()[0]
        print(f"   TPAs: {tpa_count}")
        
        cursor.execute("SELECT COUNT(*) FROM admin_settings;")
        settings_count = cursor.fetchone()[0]
        print(f"   Admin Settings: {settings_count}")
        
        # Show sample user login credentials
        print("\n🔐 Sample Login Credentials:")
        print("   Admin:    admin@connectedautocare.com / admin123")
        print("   Reseller: reseller@example.com / reseller123")
        print("   Customer: customer@example.com / customer123")
        
        # Close cursor and connection properly
        cursor.close()
        conn.close()
        
        print("\n🎉 Complete migration successful!")
        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except:
            pass
        return False


def create_protection_plans_table():
    """Create protection_plans table if it doesn't exist"""
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS protection_plans (
                id SERIAL PRIMARY KEY,
                plan_id VARCHAR(255) UNIQUE NOT NULL,
                transaction_id UUID REFERENCES transactions(id),
                customer_email VARCHAR(255) NOT NULL,
                plan_type VARCHAR(50) NOT NULL,
                plan_name VARCHAR(255) NOT NULL,
                coverage_details JSONB,
                vehicle_info JSONB,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                status VARCHAR(50) DEFAULT 'active',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_protection_plans_customer_email 
            ON protection_plans(customer_email);
            
            CREATE INDEX IF NOT EXISTS idx_protection_plans_plan_id 
            ON protection_plans(plan_id);
            
            CREATE INDEX IF NOT EXISTS idx_protection_plans_status 
            ON protection_plans(status);
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("✅ Protection plans table created/verified")
        
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        print(f"❌ Error creating protection plans table: {str(e)}")


if __name__ == "__main__":
    create_protection_plans_table()
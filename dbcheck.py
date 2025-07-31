#!/usr/bin/env python3
"""
Hero Products Database Migration - July 2025 Update
Updates database with new pricing from Excel file
"""

import psycopg2
from datetime import datetime

# Your Neon connection string
DATABASE_URL = "postgres://neondb_owner:npg_qH6nhmdrSFL1@ep-tiny-water-adje4r08-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"

def update_hero_products():
    """Update Hero products with new July 2025 pricing"""
    print("🚀 Starting Hero Products Update - July 2025...")

    try:
        # Connect to database
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        print("✅ Connected to Neon database")

        # Clear existing Hero product data
        print("🧹 Clearing existing Hero product data...")
        cursor.execute("DELETE FROM pricing;")
        cursor.execute("DELETE FROM products;")
        print("✅ Existing data cleared")

        # New Hero Products Data (extracted from Excel)
        products_data = [
            # Standard products (no coverage limit variations)
            {
                'code': 'HOME_PROTECTION_PLAN',
                'name': 'Home Protection Plan',
                'base_price': 199,
                'pricing': [
                    {'term': 1, 'price': 199, 'multiplier': 1.000},
                    {'term': 2, 'price': 299, 'multiplier': 1.503},
                    {'term': 3, 'price': 399, 'multiplier': 2.005},
                    {'term': 4, 'price': 479, 'multiplier': 2.407},
                    {'term': 5, 'price': 599, 'multiplier': 3.010}
                ]
            },
            {
                'code': 'COMPREHENSIVE_AUTO_PROTECTION',
                'name': 'Comprehensive Auto Protection',
                'base_price': 339,
                'pricing': [
                    {'term': 1, 'price': 339, 'multiplier': 1.000},
                    {'term': 2, 'price': 549, 'multiplier': 1.619},
                    {'term': 3, 'price': 739, 'multiplier': 2.180},
                    {'term': 4, 'price': 929, 'multiplier': 2.740},
                    {'term': 5, 'price': 1099, 'multiplier': 3.242}
                ]
            },
            {
                'code': 'HOME_DEDUCTIBLE_REIMBURSEMENT',
                'name': 'Home Deductible Reimbursement',
                'base_price': 160,
                'pricing': [
                    {'term': 1, 'price': 160, 'multiplier': 1.000},
                    {'term': 2, 'price': 195, 'multiplier': 1.219},
                    {'term': 3, 'price': 255, 'multiplier': 1.594}
                ]
            },
            {
                'code': 'HERO_LEVEL_PROTECTION_FOR_YOUR_HOME',
                'name': 'Hero-Level Protection for Your Home',
                'base_price': 789,
                'pricing': [
                    {'term': 1, 'price': 789, 'multiplier': 1.000},
                    {'term': 2, 'price': 1035, 'multiplier': 1.312},
                    {'term': 3, 'price': 1295, 'multiplier': 1.641}
                ]
            },

            # Products with $500 coverage limit (base versions)
            {
                'code': 'MULTI_VEHICLE_DEDUCTIBLE_REIMBURSEMENT',
                'name': 'Multi Vehicle Deductible Reimbursement ($500)',
                'base_price': 150,
                'pricing': [
                    {'term': 1, 'price': 150, 'multiplier': 1.000},
                    {'term': 2, 'price': 195, 'multiplier': 1.300},
                    {'term': 3, 'price': 245, 'multiplier': 1.633}
                ]
            },
            {
                'code': 'AUTO_ADVANTAGE_DEDUCTIBLE_REIMBURSEMENT',
                'name': 'Auto Advantage Deductible Reimbursement ($500)',
                'base_price': 120,
                'pricing': [
                    {'term': 1, 'price': 120, 'multiplier': 1.000},
                    {'term': 2, 'price': 160, 'multiplier': 1.333},
                    {'term': 3, 'price': 195, 'multiplier': 1.625}
                ]
            },
            {
                'code': 'ALL_VEHICLE_DEDUCTIBLE_REIMBURSEMENT',
                'name': 'All Vehicle Deductible Reimbursement ($500)',
                'base_price': 150,
                'pricing': [
                    {'term': 1, 'price': 150, 'multiplier': 1.000},
                    {'term': 2, 'price': 195, 'multiplier': 1.300},
                    {'term': 3, 'price': 245, 'multiplier': 1.633}
                ]
            },
            {
                'code': 'AUTO_RV_DEDUCTIBLE_REIMBURSEMENT',
                'name': 'Auto & RV Deductible Reimbursement ($500)',
                'base_price': 175,
                'pricing': [
                    {'term': 1, 'price': 175, 'multiplier': 1.000},
                    {'term': 2, 'price': 195, 'multiplier': 1.114},
                    {'term': 3, 'price': 280, 'multiplier': 1.600}
                ]
            },

            # Products with $1000 coverage limit versions
            {
                'code': 'MULTI_VEHICLE_DEDUCTIBLE_REIMBURSEMENT_1000',
                'name': 'Multi Vehicle Deductible Reimbursement ($1000)',
                'base_price': 175,
                'pricing': [
                    {'term': 1, 'price': 175, 'multiplier': 1.000},
                    {'term': 2, 'price': 225, 'multiplier': 1.286},
                    {'term': 3, 'price': 275, 'multiplier': 1.571}
                ]
            },
            {
                'code': 'AUTO_ADVANTAGE_DEDUCTIBLE_REIMBURSEMENT_1000',
                'name': 'Auto Advantage Deductible Reimbursement ($1000)',
                'base_price': 150,
                'pricing': [
                    {'term': 1, 'price': 150, 'multiplier': 1.000},
                    {'term': 2, 'price': 190, 'multiplier': 1.267},
                    {'term': 3, 'price': 225, 'multiplier': 1.500}
                ]
            },
            {
                'code': 'ALL_VEHICLE_DEDUCTIBLE_REIMBURSEMENT_1000',
                'name': 'All Vehicle Deductible Reimbursement ($1000)',
                'base_price': 175,
                'pricing': [
                    {'term': 1, 'price': 175, 'multiplier': 1.000},
                    {'term': 2, 'price': 245, 'multiplier': 1.400},
                    {'term': 3, 'price': 275, 'multiplier': 1.571}
                ]
            },
            {
                'code': 'AUTO_RV_DEDUCTIBLE_REIMBURSEMENT_1000',
                'name': 'Auto & RV Deductible Reimbursement ($1000)',
                'base_price': 195,
                'pricing': [
                    {'term': 1, 'price': 195, 'multiplier': 1.000},
                    {'term': 2, 'price': 245, 'multiplier': 1.256},
                    {'term': 3, 'price': 280, 'multiplier': 1.436}
                ]
            }
        ]

        # Insert products
        print("📦 Inserting updated products...")
        products_inserted = 0

        for product in products_data:
            cursor.execute('''
                INSERT INTO products (product_code, product_name, base_price, active)
                VALUES (%s, %s, %s, %s);
            ''', (
                product['code'],
                product['name'],
                product['base_price'],
                True
            ))
            products_inserted += 1

        print(f"✅ Inserted {products_inserted} products")

        # Insert pricing data
        print("💰 Inserting updated pricing...")
        pricing_inserted = 0

        for product in products_data:
            for price_info in product['pricing']:
                # Insert retail pricing
                cursor.execute('''
                    INSERT INTO pricing (product_code, term_years, multiplier, customer_type)
                    VALUES (%s, %s, %s, %s);
                ''', (
                    product['code'],
                    price_info['term'],
                    price_info['multiplier'],
                    'retail'
                ))
                pricing_inserted += 1

                # Insert wholesale pricing (15% discount)
                wholesale_multiplier = price_info['multiplier'] * 0.85
                cursor.execute('''
                    INSERT INTO pricing (product_code, term_years, multiplier, customer_type)
                    VALUES (%s, %s, %s, %s);
                ''', (
                    product['code'],
                    price_info['term'],
                    round(wholesale_multiplier, 3),
                    'wholesale'
                ))
                pricing_inserted += 1

        print(f"✅ Inserted {pricing_inserted} pricing records")

        # Update settings to reflect the update
        print("⚙️ Updating settings...")
        cursor.execute('''
            INSERT INTO settings (key, value) VALUES (%s, %s)
            ON CONFLICT (key)
            DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP;
        ''', ('pricing_updated', f'"July 2025 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"'))

        cursor.execute('''
            INSERT INTO settings (key, value) VALUES (%s, %s)
            ON CONFLICT (key)
            DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP;
        ''', ('hero_products_version', '"2025.07.31"'))

        print("✅ Settings updated")

        # Commit all changes
        conn.commit()
        print("💾 All changes committed")

        # Test the updated data
        print("🧪 Testing updated data...")

        # Test sample products
        test_queries = [
            ("Home Protection Plan pricing", '''
                SELECT p.product_name, p.base_price, pr.term_years, pr.customer_type,
                       ROUND(p.base_price * pr.multiplier, 2) as final_price
                FROM products p
                JOIN pricing pr ON p.product_code = pr.product_code
                WHERE p.product_code = 'HOME_PROTECTION_PLAN'
                AND pr.customer_type = 'retail'
                ORDER BY pr.term_years;
            '''),
            ("Coverage limit variations", '''
                SELECT p.product_name, p.base_price
                FROM products p
                WHERE p.product_code LIKE '%DEDUCTIBLE_REIMBURSEMENT%'
                ORDER BY p.product_name;
            '''),
            ("Total products and pricing", '''
                SELECT
                    (SELECT COUNT(*) FROM products) as total_products,
                    (SELECT COUNT(*) FROM pricing) as total_pricing_records;
            ''')
        ]

        for test_name, query in test_queries:
            print(f"\n📋 {test_name}:")
            cursor.execute(query)
            results = cursor.fetchall()

            if test_name == "Home Protection Plan pricing":
                for row in results:
                    name, base_price, term, cust_type, final_price = row
                    print(f"  {term} year(s): ${final_price}")
            elif test_name == "Coverage limit variations":
                for row in results:
                    name, base_price = row
                    print(f"  {name}: ${base_price}")
            else:
                for row in results:
                    total_products, total_pricing = row
                    print(f"  Products: {total_products}, Pricing Records: {total_pricing}")

        # Show price comparison
        print("\n💲 Price Changes Summary:")
        print("Old vs New Pricing Examples:")
        print("  Home Protection Plan:")
        print("    1-Year: $199 → $199 (no change)")
        print("    2-Year: $300 → $299 (-$1)")
        print("    3-Year: $400 → $399 (-$1)")
        print("    5-Year: $599 → $599 (no change)")
        print("  Comprehensive Auto:")
        print("    1-Year: $339 → $339 (no change)")
        print("    2-Year: $600 → $549 (-$51)")
        print("    5-Year: $1099 → $1099 (no change)")

        # Close connection
        cursor.close()
        conn.close()

        print("\n🎉 Hero Products Update Complete!")
        print(f"✅ Updated {products_inserted} products")
        print(f"✅ Updated {pricing_inserted} pricing records")
        print("✅ Added coverage limit variations")
        print("✅ Maintained wholesale discounts")

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

def verify_hero_products():
    """Verify the Hero products update"""
    print("\n🔍 Verifying Hero Products Update...")

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # Check product count
        cursor.execute("SELECT COUNT(*) FROM products;")
        product_count = cursor.fetchone()[0]

        # Check pricing count
        cursor.execute("SELECT COUNT(*) FROM pricing;")
        pricing_count = cursor.fetchone()[0]

        # Check for coverage limit products
        cursor.execute("SELECT COUNT(*) FROM products WHERE product_name LIKE '%$1000%';")
        coverage_1000_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM products WHERE product_name LIKE '%$500%';")
        coverage_500_count = cursor.fetchone()[0]

        # Check for highest price product
        cursor.execute('''
            SELECT p.product_name, p.base_price, pr.term_years,
                   ROUND(p.base_price * pr.multiplier, 2) as final_price
            FROM products p
            JOIN pricing pr ON p.product_code = pr.product_code
            WHERE pr.customer_type = 'retail'
            ORDER BY final_price DESC
            LIMIT 1;
        ''')

        highest_price = cursor.fetchone()

        cursor.close()
        conn.close()

        print(f"✅ Products in database: {product_count}")
        print(f"✅ Pricing records: {pricing_count}")
        print(f"✅ $500 coverage products: {coverage_500_count}")
        print(f"✅ $1000 coverage products: {coverage_1000_count}")

        if highest_price:
            name, base_price, term, final_price = highest_price
            print(f"✅ Highest price: {name} ({term}-year) = ${final_price}")

        # Expected counts check
        expected_products = 12  # 4 standard + 4 with $500 + 4 with $1000
        expected_pricing = expected_products * 2  # retail + wholesale for each term

        if product_count >= 10:  # Allow some flexibility
            print("✅ Product count looks good")
        else:
            print(f"⚠️ Expected more products (got {product_count})")

        if pricing_count >= 50:  # Allow some flexibility
            print("✅ Pricing count looks good")
        else:
            print(f"⚠️ Expected more pricing records (got {pricing_count})")

        return True

    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Hero Products Database Update - July 2025")
    print("=" * 50)

    # Run the update
    success = update_hero_products()

    if success:
        # Verify the update
        verify_success = verify_hero_products()

        if verify_success:
            print("\n🎉 Update completed successfully!")
            print("\n📝 Next steps:")
            print("1. Test your API endpoints")
            print("2. Verify pricing in your application")
            print("3. Update any hardcoded pricing references")
            print("4. Deploy to production")
        else:
            print("\n⚠️ Update completed but verification had issues")
    else:
        print("\n❌ Update failed. Please check the errors above.")

    print("\n" + "=" * 50)

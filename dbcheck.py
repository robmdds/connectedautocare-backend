#!/usr/bin/env python3
"""
Settings Migration Script
Add missing fee, discount, and tax settings to admin_settings table
"""

import psycopg2
import json

# Your Neon connection string
DATABASE_URL = "postgres://neondb_owner:npg_qH6nhmdrSFL1@ep-tiny-water-adje4r08-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"

def add_missing_settings():
    """Add missing settings to admin_settings table"""
    print("🚀 Adding missing settings to admin_settings table...")
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Get admin user ID for updated_by field
        cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1;")
        admin_result = cursor.fetchone()
        admin_id = admin_result[0] if admin_result else None
        
        # Enhanced settings data with VSC-specific and Hero-specific fees
        enhanced_settings = [
            # Fee Settings
            ('fees', 'admin_fee', '25.00', 'Default administrative fee'),
            ('fees', 'vsc_admin_fee', '50.00', 'VSC-specific administrative fee'),
            ('fees', 'hero_admin_fee', '25.00', 'Hero products administrative fee'),
            ('fees', 'processing_fee', '15.00', 'Payment processing fee'),
            ('fees', 'dealer_fee', '50.00', 'Dealer commission fee'),
            
            # Discount Settings
            ('discounts', 'wholesale_discount', '0.15', 'Default wholesale discount rate (15%)'),
            ('discounts', 'volume_discount_threshold', '10', 'Minimum policies for volume discount'),
            ('discounts', 'volume_discount_rate', '0.05', 'Volume discount rate (5%)'),
            ('discounts', 'early_payment_discount', '0.02', 'Early payment discount (2%)'),
            
            # Tax Settings (by state)
            ('taxes', 'default_tax_rate', '0.07', 'Default tax rate (7%)'),
            ('taxes', 'fl_tax_rate', '0.07', 'Florida tax rate'),
            ('taxes', 'ca_tax_rate', '0.0875', 'California tax rate'),
            ('taxes', 'ny_tax_rate', '0.08', 'New York tax rate'),
            ('taxes', 'tx_tax_rate', '0.0625', 'Texas tax rate'),
            ('taxes', 'il_tax_rate', '0.0625', 'Illinois tax rate'),
            
            # Markup Settings
            ('markups', 'retail_markup', '1.0', 'Retail price multiplier'),
            ('markups', 'wholesale_markup', '0.85', 'Wholesale price multiplier'),
            ('markups', 'dealer_markup', '0.90', 'Dealer price multiplier'),
            
            # Pricing Multipliers by State
            ('pricing', 'fl_multiplier', '1.0', 'Florida pricing multiplier (base)'),
            ('pricing', 'ca_multiplier', '1.15', 'California pricing multiplier'),
            ('pricing', 'ny_multiplier', '1.20', 'New York pricing multiplier'),
            ('pricing', 'tx_multiplier', '1.05', 'Texas pricing multiplier'),
            ('pricing', 'il_multiplier', '1.10', 'Illinois pricing multiplier'),
            
            # Business Rules
            ('rules', 'quote_validity_days', '30', 'Quote validity period in days'),
            ('rules', 'max_financing_months', '60', 'Maximum financing term in months'),
            ('rules', 'min_down_payment_percent', '0.1', 'Minimum down payment percentage'),
            
            # System Settings
            ('system', 'maintenance_mode', 'false', 'System maintenance mode flag'),
            ('system', 'max_quote_requests_per_hour', '100', 'Rate limit for quote requests'),
            ('system', 'cache_ttl_minutes', '30', 'Settings cache TTL in minutes'),
            
            # VSC Specific Settings
            ('vsc', 'max_vehicle_age_years', '20', 'Maximum vehicle age for VSC eligibility'),
            ('vsc', 'max_vehicle_mileage', '200000', 'Maximum vehicle mileage for VSC eligibility'),
            ('vsc', 'warning_age_years', '15', 'Age threshold for coverage warnings'),
            ('vsc', 'warning_mileage', '150000', 'Mileage threshold for premium rates'),
            
            # Hero Products Settings
            ('hero', 'coverage_multiplier_1000', '1.2', 'Coverage multiplier for $1000 limit'),
            ('hero', 'coverage_multiplier_500', '1.0', 'Coverage multiplier for $500 limit'),
            ('hero', 'default_coverage_limit', '500', 'Default coverage limit'),
            
            # Commission Settings
            ('commissions', 'agent_commission_rate', '0.10', 'Agent commission rate (10%)'),
            ('commissions', 'dealer_commission_rate', '0.15', 'Dealer commission rate (15%)'),
            ('commissions', 'referral_bonus', '50.00', 'Referral bonus amount'),
        ]
        
        print(f"📝 Preparing to insert {len(enhanced_settings)} settings...")
        
        inserted_count = 0
        updated_count = 0
        
        for category, key, value, description in enhanced_settings:
            try:
                # Check if setting already exists
                cursor.execute(
                    "SELECT id FROM admin_settings WHERE category = %s AND key = %s",
                    (category, key)
                )
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing setting
                    cursor.execute("""
                        UPDATE admin_settings 
                        SET value = %s, description = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE category = %s AND key = %s
                    """, (value, description, admin_id, category, key))
                    updated_count += 1
                    print(f"  ✏️  Updated {category}.{key}")
                else:
                    # Insert new setting
                    cursor.execute("""
                        INSERT INTO admin_settings (category, key, value, description, updated_by, updated_at)
                        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """, (category, key, value, description, admin_id))
                    inserted_count += 1
                    print(f"  ➕ Inserted {category}.{key}")
                    
            except Exception as e:
                print(f"  ❌ Error with {category}.{key}: {e}")
                continue
        
        # Commit all changes
        conn.commit()
        print(f"💾 All changes committed")
        
        # Test some key settings
        print("\n🧪 Testing key settings...")
        test_settings = [
            ('fees', 'vsc_admin_fee'),
            ('fees', 'hero_admin_fee'),
            ('discounts', 'wholesale_discount'),
            ('taxes', 'fl_tax_rate'),
            ('pricing', 'ca_multiplier')
        ]
        
        for category, key in test_settings:
            cursor.execute(
                "SELECT value FROM admin_settings WHERE category = %s AND key = %s",
                (category, key)
            )
            result = cursor.fetchone()
            if result:
                print(f"  ✅ {category}.{key} = {result[0]}")
            else:
                print(f"  ❌ {category}.{key} not found")
        
        # Get summary statistics
        cursor.execute("SELECT category, COUNT(*) FROM admin_settings GROUP BY category ORDER BY category;")
        stats = cursor.fetchall()
        
        print(f"\n📊 Settings Summary:")
        total_settings = 0
        for category, count in stats:
            print(f"  {category}: {count} settings")
            total_settings += count
        print(f"  Total: {total_settings} settings")
        
        cursor.close()
        conn.close()
        
        print(f"\n🎉 Migration completed successfully!")
        print(f"   📈 Inserted: {inserted_count} new settings")
        print(f"   ✏️  Updated: {updated_count} existing settings")
        
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


def verify_settings_integration():
    """Verify that the settings can be accessed properly"""
    print("\n🔍 Verifying settings integration...")
    
    try:
        # Import the settings service to test it
        from api.services.database_settings_service import (
            get_admin_fee, get_wholesale_discount, get_tax_rate
        )
        
        print("✅ Database settings service imported successfully")
        
        # Test key functions
        vsc_admin_fee = get_admin_fee('vsc')
        hero_admin_fee = get_admin_fee('hero')
        wholesale_discount = get_wholesale_discount()
        fl_tax_rate = get_tax_rate('FL')
        ca_tax_rate = get_tax_rate('CA')
        
        print(f"✅ VSC Admin Fee: ${vsc_admin_fee}")
        print(f"✅ Hero Admin Fee: ${hero_admin_fee}")
        print(f"✅ Wholesale Discount: {wholesale_discount*100}%")
        print(f"✅ FL Tax Rate: {fl_tax_rate*100}%")
        print(f"✅ CA Tax Rate: {ca_tax_rate*100}%")
        
        print("\n🎉 Settings integration verification successful!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error - make sure database_settings_service.py is in the right location: {e}")
        return False
    except Exception as e:
        print(f"❌ Settings integration error: {e}")
        return False


if __name__ == "__main__":
    success = add_missing_settings()
    
    if success:
        print("\n" + "="*60)
        verify_settings_integration()
        
        print("\n" + "="*60)
        print("🚀 NEXT STEPS:")
        print("1. Copy database_settings_service.py to your project directory")
        print("2. Update your hero_rating_service.py with the database-driven version")
        print("3. Update your VSC quote endpoints to use database settings")
        print("4. Test the /api/admin/settings/status endpoint")
        print("5. Set up environment variable DATABASE_URL if needed")
        print("\n💡 TIP: Use /api/admin/settings/refresh to reload settings after changes")
    else:
        print("\n❌ Migration failed. Please check the errors above and try again.")
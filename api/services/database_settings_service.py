# services/database_settings_service.py
#!/usr/bin/env python3
"""
Database Settings Service - Fixed Version
Centralized service for fetching admin settings, fees, and discounts from database
"""

import traceback
import psycopg2
import json
from typing import Optional, Dict, Any
from functools import lru_cache
import os


class DatabaseSettingsService:
    def __init__(self, database_url: str = None):
        self.database_url = database_url or os.getenv('DATABASE_URL')
        
        # Fallback URL
        if not self.database_url:
            self.database_url = 'postgres://neondb_owner:npg_qH6nhmdrSFL1@ep-tiny-water-adje4r08-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require'
        
        if not self.database_url:
            self.connection_available = False
        else:
            self.connection_available = self._test_connection()
        
        if not self.connection_available:
            print("⚠️ Database connection failed during initialization")
            print("🔄 Service will use fallback values")
    
    def _test_connection(self) -> bool:
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor()

            cursor.execute("SELECT 1;")
            result = cursor.fetchone()
            
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'admin_settings'
                );
            """)
            table_exists = cursor.fetchone()[0]
            
            if not table_exists:
                self._create_admin_settings_table(cursor)
                conn.commit()
            
            cursor.close()
            conn.close()
            return True
            
        except Exception as e:
            print(f"❌ Database connection test failed: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            return False
    
    def _create_admin_settings_table(self, cursor):
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS admin_settings (
            id SERIAL PRIMARY KEY,
            category VARCHAR(50) NOT NULL,
            key VARCHAR(100) NOT NULL,
            value TEXT,
            description TEXT,
            updated_by VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(category, key)
        );
        """
        
        cursor.execute(create_table_sql)
        
        default_settings = [
            ('fees', 'admin_fee', '25.00', 'Default admin fee for Hero products'),
            ('fees', 'vsc_admin_fee', '50.00', 'Admin fee for VSC products'),
            ('fees', 'processing_fee', '15.00', 'Processing fee'),
            ('fees', 'dealer_fee', '50.00', 'Dealer fee'),
            ('discounts', 'wholesale_discount', '0.15', 'Wholesale discount rate (15%)'),
            ('taxes', 'default_tax_rate', '0.08', 'Default tax rate (8%)'),
            ('taxes', 'fl_tax_rate', '0.07', 'Florida tax rate (7%)'),
            ('taxes', 'ca_tax_rate', '0.0875', 'California tax rate (8.75%)'),
            ('taxes', 'ny_tax_rate', '0.08', 'New York tax rate (8%)'),
            ('taxes', 'tx_tax_rate', '0.0625', 'Texas tax rate (6.25%)'),
            ('contact', 'phone', '"1-(866) 660-7003"', 'Support phone number'),
            ('contact', 'email', '"support@connectedautocare.com"', 'Support email'),
            ('contact', 'support_hours', '"24/7"', 'Support hours'),
            ('video', 'landing_page_title', '"ConnectedAutoCare Hero Protection 2025"', 'Landing page video title'),
            ('video', 'landing_page_description', '"Showcase of our comprehensive protection plans"', 'Landing page video description'),
            ('video', 'landing_page_duration', '"2:30"', 'Landing page video duration'),
            ('video', 'landing_page_url', '""', 'Landing page video URL'),
            ('video', 'landing_page_thumbnail', '""', 'Landing page video thumbnail URL')
        ]
        
        for category, key, value, description in default_settings:
            cursor.execute("""
                INSERT INTO admin_settings (category, key, value, description)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (category, key) DO NOTHING;
            """, (category, key, value, description))
    
    def get_connection(self):
        if not self.connection_available:
            raise Exception("Database connection not available")
        return psycopg2.connect(self.database_url)
    
    @lru_cache(maxsize=128)
    def get_admin_setting(self, category: str, key: str, default_value: Any = None) -> Any:
        if not self.connection_available:
            return default_value
            
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT value FROM admin_settings WHERE category = %s AND key = %s",
                (category, key)
            )
            result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if result:
                value = json.loads(result[0]) if isinstance(result[0], str) else result[0]
                return value
            
            return default_value
            
        except Exception as e:
            print(f"Error fetching admin setting {category}.{key}: {e}")
            return default_value
    
    def get_all_settings_by_category(self, category: str) -> Dict[str, Any]:
        if not self.connection_available:
            return {}
            
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT key, value FROM admin_settings WHERE category = %s",
                (category,)
            )
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            settings = {}
            for key, value in results:
                parsed_value = json.loads(value) if isinstance(value, str) else value
                settings[key] = parsed_value
            
            return settings
            
        except Exception as e:
            print(f"Error fetching settings for category {category}: {e}")
            return {}
    
    def get_fee_settings(self) -> Dict[str, float]:
        return self.get_all_settings_by_category('fees')
    
    def get_discount_settings(self) -> Dict[str, float]:
        return self.get_all_settings_by_category('discounts')
    
    def get_markup_settings(self) -> Dict[str, float]:
        return self.get_all_settings_by_category('markups')
    
    def clear_cache(self):
        self.get_admin_setting.cache_clear()
    
    def update_setting(self, category: str, key: str, value: Any, description: str = None, updated_by: str = None):
        if not self.connection_available:
            print(f"Cannot update setting {category}.{key} - database not available")
            return False
            
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            json_value = json.dumps(value) if not isinstance(value, str) else value
            
            cursor.execute("""
                INSERT INTO admin_settings (category, key, value, description, updated_by, updated_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (category, key) 
                DO UPDATE SET 
                    value = EXCLUDED.value,
                    description = COALESCE(EXCLUDED.description, admin_settings.description),
                    updated_by = EXCLUDED.updated_by,
                    updated_at = CURRENT_TIMESTAMP
            """, (category, key, json_value, description, updated_by))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            self.clear_cache()
            
            return True
            
        except Exception as e:
            print(f"Error updating setting {category}.{key}: {e}")
            return False

# Create global instance with fallback
class DummySettingsService:
    def __init__(self):
        self.connection_available = False
    
    def is_database_available(self):
        return False
    
    def get_admin_setting(self, category: str, key: str, default_value: Any = None) -> Any:
        return default_value
    
    def get_all_settings_by_category(self, category: str) -> Dict[str, Any]:
        return {}
    
    def clear_cache(self):
        pass

try:
    settings_service = DatabaseSettingsService()
    if settings_service.connection_available:
        print("✅ Database settings service initialized successfully")
    else:
        print("⚠️ Database settings service initialized with fallback mode")
        settings_service = DummySettingsService()
except Exception as e:
    print(f"❌ Failed to initialize database settings service: {e}")
    settings_service = DummySettingsService()

def get_admin_fee(product_type: str = 'default') -> float:
    if settings_service.connection_available:
        fee = settings_service.get_admin_setting('fees', f'{product_type}_admin_fee')
        print(f"Admin fee for {product_type}: {fee}")
        if fee is None:
            fee = settings_service.get_admin_setting('fees', 'admin_fee', 25.00)
            print(f"Using default admin fee: {fee}")
        return float(fee)
    return 25.00

def get_wholesale_discount() -> float:
    if settings_service.connection_available:
        discount = settings_service.get_admin_setting('discounts', 'wholesale_discount', 0.15)
        return float(discount)
    return 0.15


def get_tax_rate(state: str = None) -> float:
    """
    Get tax rate from database settings.
    If no state is provided, returns default_tax_rate.
    If state is provided, tries state-specific rate first, then falls back to default.
    """
    if settings_service.connection_available:
        if state is None:
            # No state specified - get default tax rate directly
            tax_rate = settings_service.get_admin_setting('taxes', 'default_tax_rate', 0.07)
        else:
            # State specified - try state-specific rate first
            tax_rate = settings_service.get_admin_setting('taxes', f'{state.lower()}_tax_rate')
            if tax_rate is None:
                # Fall back to default if state-specific rate not found
                tax_rate = settings_service.get_admin_setting('taxes', 'default_tax_rate', 0.07)
        return float(tax_rate)

    # Database not available - return hardcoded fallback
    return 0.00

def get_processing_fee() -> float:
    if settings_service.connection_available:
        fee = settings_service.get_admin_setting('fees', 'processing_fee', 15.00)
        return float(fee)
    return 15.00

def get_dealer_fee() -> float:
    if settings_service.connection_available:
        fee = settings_service.get_admin_setting('fees', 'dealer_fee', 50.00)
        return float(fee)
    return 50.00
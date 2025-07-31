"""
VSC PDF Rate Importer
Import actual VSC rates from PDF data into database
"""

import psycopg2
from datetime import datetime
import json
import logging
import os
from psycopg2.extras import execute_values
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Use environment variable for database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgres://neondb_owner:npg_qH6nhmdrSFL1@ep-tiny-water-adje4r08-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require")

class VSCPDFRateImporter:
    """Import VSC rates from PDF data into database"""
    
    def __init__(self, database_url=DATABASE_URL):
        if not database_url:
            raise ValueError("DATABASE_URL not set")
        self.database_url = database_url
        
        # Real VSC rate data from PDF - PLATINUM Coverage
        self.platinum_rates = {
            'A': {  # Class A - Most Reliable
                12: {
                    'up_to_15000': 1629, '15000_to_50000': 1705, '50000_to_75000': 1757, 
                    '75000_to_100000': 1785, '100000_to_125000': 1826, '125000_to_150000': 1866
                },
                24: {
                    'up_to_15000': 1634, '15000_to_50000': 1708, '50000_to_75000': 1759, 
                    '75000_to_100000': 1788, '100000_to_125000': 1830, '125000_to_150000': 1880
                },
                36: {
                    'up_to_15000': 1639, '15000_to_50000': 1719, '50000_to_75000': 1773, 
                    '75000_to_100000': 1802, '100000_to_125000': 1849, '125000_to_150000': 1899
                },
                48: {
                    'up_to_15000': 1649, '15000_to_50000': 1721, '50000_to_75000': 1775, 
                    '75000_to_100000': 1805, '100000_to_125000': 1852, '125000_to_150000': 1909
                },
                60: {
                    'up_to_15000': 1651, '15000_to_50000': 1723, '50000_to_75000': 1778, 
                    '75000_to_100000': 1809, '100000_to_125000': 1856, '125000_to_150000': 1906
                },
                72: {
                    'up_to_15000': 1664, '15000_to_50000': 1730, '50000_to_75000': 1787, 
                    '75000_to_100000': 1818, '100000_to_125000': 1867
                }
            },
            'B': {  # Class B - Moderate Risk
                12: {
                    'up_to_15000': 1779, '15000_to_50000': 1911, '50000_to_75000': 1960, 
                    '75000_to_100000': 1997, '100000_to_125000': 2083, '125000_to_150000': 2169
                },
                24: {
                    'up_to_15000': 1786, '15000_to_50000': 1918, '50000_to_75000': 1969, 
                    '75000_to_100000': 2006, '100000_to_125000': 2096, '125000_to_150000': 2182
                },
                36: {
                    'up_to_15000': 1872, '15000_to_50000': 1924, '50000_to_75000': 1976, 
                    '75000_to_100000': 2015, '100000_to_125000': 2108, '125000_to_150000': 2202
                },
                48: {
                    'up_to_15000': 1876, '15000_to_50000': 1929, '50000_to_75000': 1982, 
                    '75000_to_100000': 2020, '100000_to_125000': 2117, '125000_to_150000': 2215
                },
                60: {
                    'up_to_15000': 1881, '15000_to_50000': 1932, '50000_to_75000': 1986, 
                    '75000_to_100000': 2025, '100000_to_125000': 2123, '125000_to_150000': 2221
                },
                72: {
                    'up_to_15000': 1886, '15000_to_50000': 1943, '50000_to_75000': 1999, 
                    '75000_to_100000': 2039, '100000_to_125000': 2143
                }
            },
            'C': {  # Class C - Higher Risk
                12: {
                    'up_to_15000': 1956, '15000_to_50000': 2617, '50000_to_75000': 2766, 
                    '75000_to_100000': 2946
                },
                24: {
                    'up_to_15000': 2007, '15000_to_50000': 2672, '50000_to_75000': 2822, 
                    '75000_to_100000': 3053
                },
                36: {
                    'up_to_15000': 2027, '15000_to_50000': 2897, '50000_to_75000': 3078, 
                    '75000_to_100000': 3331
                },
                48: {
                    'up_to_15000': 2052, '15000_to_50000': 2978, '50000_to_75000': 3167, 
                    '75000_to_100000': 3827
                },
                60: {
                    'up_to_15000': 2107, '15000_to_50000': 3243, '50000_to_75000': 3462, 
                    '75000_to_100000': 4032
                },
                72: {
                    'up_to_15000': 2142, '15000_to_50000': 3313, '50000_to_75000': 3538, 
                    '75000_to_100000': 4267
                }
            }
        }
        
        # GOLD Coverage rates
        self.gold_rates = {
            'A': {
                12: {
                    'up_to_15000': 1549, '15000_to_50000': 1574, '50000_to_75000': 1607, 
                    '75000_to_100000': 1625, '100000_to_125000': 1652, '125000_to_150000': 1662
                },
                24: {
                    'up_to_15000': 1555, '15000_to_50000': 1575, '50000_to_75000': 1609, 
                    '75000_to_100000': 1627, '100000_to_125000': 1655, '125000_to_150000': 1675
                },
                36: {
                    'up_to_15000': 1558, '15000_to_50000': 1582, '50000_to_75000': 1618, 
                    '75000_to_100000': 1637, '100000_to_125000': 1667, '125000_to_150000': 1681
                },
                48: {
                    'up_to_15000': 1571, '15000_to_50000': 1584, '50000_to_75000': 1619, 
                    '75000_to_100000': 1639, '100000_to_125000': 1669, '125000_to_150000': 1704
                },
                60: {
                    'up_to_15000': 1574, '15000_to_50000': 1585, '50000_to_75000': 1621, 
                    '75000_to_100000': 1641, '100000_to_125000': 1671, '125000_to_150000': 1707
                },
                72: {
                    'up_to_15000': 1579, '15000_to_50000': 1590, '50000_to_75000': 1626, 
                    '75000_to_100000': 1647, '100000_to_125000': 1679
                }
            },
            'B': {
                12: {
                    'up_to_15000': 1687, '15000_to_50000': 1737, '50000_to_75000': 1771, 
                    '75000_to_100000': 1797, '100000_to_125000': 1857, '125000_to_150000': 1884
                },
                24: {
                    'up_to_15000': 1695, '15000_to_50000': 1741, '50000_to_75000': 1777, 
                    '75000_to_100000': 1803, '100000_to_125000': 1866, '125000_to_150000': 1896
                },
                36: {
                    'up_to_15000': 1716, '15000_to_50000': 1748, '50000_to_75000': 1783, 
                    '75000_to_100000': 1811, '100000_to_125000': 1878, '125000_to_150000': 1900
                },
                48: {
                    'up_to_15000': 1720, '15000_to_50000': 1749, '50000_to_75000': 1786, 
                    '75000_to_100000': 1813, '100000_to_125000': 1881, '125000_to_150000': 1910
                },
                60: {
                    'up_to_15000': 1749, '15000_to_50000': 1751, '50000_to_75000': 1789, 
                    '75000_to_100000': 1816, '100000_to_125000': 1885, '125000_to_150000': 1954
                },
                72: {
                    'up_to_15000': 1755, '15000_to_50000': 1759, '50000_to_75000': 1798, 
                    '75000_to_100000': 1826, '100000_to_125000': 1899
                }
            },
            'C': {
                12: {
                    'up_to_15000': 1881, '15000_to_50000': 1995, '50000_to_75000': 2205, 
                    '75000_to_100000': 2338
                },
                24: {
                    'up_to_15000': 1923, '15000_to_50000': 2081, '50000_to_75000': 2412, 
                    '75000_to_100000': 2596
                },
                36: {
                    'up_to_15000': 1954, '15000_to_50000': 2166, '50000_to_75000': 2619, 
                    '75000_to_100000': 2854
                },
                48: {
                    'up_to_15000': 2025, '15000_to_50000': 2231, '50000_to_75000': 2677, 
                    '75000_to_100000': 3187
                },
                60: {
                    'up_to_15000': 2057, '15000_to_50000': 2263, '50000_to_75000': 2864, 
                    '75000_to_100000': 3324, '100000_to_125000': 3530
                },
                72: {
                    'up_to_15000': 2094, '15000_to_50000': 2316, '50000_to_75000': 2912, 
                    '75000_to_100000': 3482, '100000_to_125000': 3705
                }
            }
        }
        
        # SILVER Coverage rates
        self.silver_rates = {
            'A': {
                12: {
                    'up_to_15000': 1484, '15000_to_50000': 1512, '50000_to_75000': 1538, 
                    '75000_to_100000': 1551, '100000_to_125000': 1571, '125000_to_150000': 1581
                },
                24: {
                    'up_to_15000': 1487, '15000_to_50000': 1514, '50000_to_75000': 1539, 
                    '75000_to_100000': 1553, '100000_to_125000': 1573, '125000_to_150000': 1594
                },
                36: {
                    'up_to_15000': 1492, '15000_to_50000': 1517, '50000_to_75000': 1542, 
                    '75000_to_100000': 1557, '100000_to_125000': 1580, '125000_to_150000': 1589
                },
                48: {
                    'up_to_15000': 1494, '15000_to_50000': 1520, '50000_to_75000': 1546, 
                    '75000_to_100000': 1561, '100000_to_125000': 1584, '125000_to_150000': 1607
                },
                60: {
                    'up_to_15000': 1497, '15000_to_50000': 1521, '50000_to_75000': 1548, 
                    '75000_to_100000': 1563, '100000_to_125000': 1586, '125000_to_150000': 1614
                },
                72: {
                    'up_to_15000': 1501, '15000_to_50000': 1525, '50000_to_75000': 1552, 
                    '75000_to_100000': 1567, '100000_to_125000': 1591
                }
            },
            'B': {
                12: {
                    'up_to_15000': 1604, '15000_to_50000': 1655, '50000_to_75000': 1682, 
                    '75000_to_100000': 1703, '100000_to_125000': 1751, '125000_to_150000': 1787
                },
                24: {
                    'up_to_15000': 1608, '15000_to_50000': 1659, '50000_to_75000': 1687, 
                    '75000_to_100000': 1708, '100000_to_125000': 1759, '125000_to_150000': 1793
                },
                36: {
                    'up_to_15000': 1614, '15000_to_50000': 1662, '50000_to_75000': 1691, 
                    '75000_to_100000': 1713, '100000_to_125000': 1765, '125000_to_150000': 1848
                },
                48: {
                    'up_to_15000': 1626, '15000_to_50000': 1665, '50000_to_75000': 1695, 
                    '75000_to_100000': 1716, '100000_to_125000': 1770, '125000_to_150000': 1883
                },
                60: {
                    'up_to_15000': 1631, '15000_to_50000': 1667, '50000_to_75000': 1697, 
                    '75000_to_100000': 1719, '100000_to_125000': 1773, '125000_to_150000': 1806
                },
                72: {
                    'up_to_15000': 1647, '15000_to_50000': 1673, '50000_to_75000': 1704, 
                    '75000_to_100000': 1727, '100000_to_125000': 1785
                }
            },
            'C': {
                12: {
                    'up_to_15000': 1484, '15000_to_50000': 1755, '50000_to_75000': 2017, 
                    '75000_to_100000': 2173, '100000_to_125000': 2250
                },
                24: {
                    'up_to_15000': 1728, '15000_to_50000': 1887, '50000_to_75000': 2060, 
                    '75000_to_100000': 2221
                },
                36: {
                    'up_to_15000': 1737, '15000_to_50000': 1939, '50000_to_75000': 2392, 
                    '75000_to_100000': 2708, '100000_to_125000': 2845
                },
                48: {
                    'up_to_15000': 1828, '15000_to_50000': 1991, '50000_to_75000': 2437, 
                    '75000_to_100000': 2831, '100000_to_125000': 2981
                },
                60: {
                    'up_to_15000': 1839, '15000_to_50000': 2011, '50000_to_75000': 2587, 
                    '75000_to_100000': 2956, '100000_to_125000': 3119
                },
                72: {
                    'up_to_15000': 1956, '15000_to_50000': 2123, '50000_to_75000': 2625, 
                    '75000_to_100000': 3103, '100000_to_125000': 3284
                }
            }
        }
        
        # Mileage range mappings
        self.mileage_ranges = {
            'up_to_15000': {'min': 0, 'max': 15000, 'display': '0-15k miles'},
            '15000_to_50000': {'min': 15001, 'max': 50000, 'display': '15k-50k miles'},
            '50000_to_75000': {'min': 50001, 'max': 75000, 'display': '50k-75k miles'},
            '75000_to_100000': {'min': 75001, 'max': 100000, 'display': '75k-100k miles'},
            '100000_to_125000': {'min': 100001, 'max': 125000, 'display': '100k-125k miles'},
            '125000_to_150000': {'min': 125001, 'max': 150000, 'display': '125k-150k miles'}
        }

    def get_connection(self):
        """Get database connection with proper error handling"""
        try:
            return psycopg2.connect(self.database_url)
        except psycopg2.OperationalError as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def check_table_exists(self, cursor, table_name):
        """Check if a table exists in the database"""
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = %s
            );
        """, (table_name,))
        return cursor.fetchone()[0]

    def ensure_prerequisites(self):
        """Ensure required tables exist before running import"""
        logger.info("Checking prerequisite tables...")
        required_tables = ['vsc_coverage_levels', 'vsc_vehicle_classes']
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    for table in required_tables:
                        if not self.check_table_exists(cursor, table):
                            logger.error(f"Required table {table} does not exist. Please run the initial migration script first.")
                            raise RuntimeError(f"Missing required table: {table}")
                    logger.info("All prerequisite tables found")
        except psycopg2.Error as e:
            logger.error(f"Error checking prerequisites: {e}")
            raise

    def clear_existing_rates(self):
        """Clear existing VSC rate data"""
        logger.info("Clearing existing VSC rate data...")
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # List of tables to clear, in dependency order
                    tables = [
                        'vsc_quotes',
                        'vsc_rate_history',
                        'vsc_rate_matrix',
                        'vsc_base_rates',
                        'vsc_age_multipliers',
                        'vsc_mileage_multipliers',
                        'vsc_deductible_multipliers',
                        'vsc_term_multipliers'
                    ]
                    
                    for table in tables:
                        if self.check_table_exists(cursor, table):
                            cursor.execute(f"DELETE FROM {table};")
                            logger.info(f"Cleared data from {table}")
                        else:
                            logger.info(f"Table {table} does not exist, skipping deletion")
                    
                    conn.commit()
                    logger.info("Existing rate data cleared")
        except psycopg2.Error as e:
            logger.error(f"Could not clear existing rates: {e}")
            raise
    
    def create_rate_matrix_table(self):
        """Create detailed rate matrix table for exact PDF rates"""
        logger.info("Creating VSC rate matrix table...")
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS vsc_rate_matrix (
                            id SERIAL PRIMARY KEY,
                            vehicle_class CHAR(1) NOT NULL CHECK (vehicle_class IN ('A', 'B', 'C')),
                            coverage_level VARCHAR(20) NOT NULL,
                            term_months INTEGER NOT NULL,
                            mileage_range_key VARCHAR(50) NOT NULL,
                            min_mileage INTEGER NOT NULL,
                            max_mileage INTEGER NOT NULL,
                            rate_amount DECIMAL(10,2) NOT NULL,
                            effective_date DATE NOT NULL DEFAULT CURRENT_DATE,
                            active BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (coverage_level) REFERENCES vsc_coverage_levels(level_code),
                            UNIQUE(vehicle_class, coverage_level, term_months, mileage_range_key, effective_date)
                        );
                        CREATE INDEX IF NOT EXISTS idx_vsc_rate_matrix_lookup 
                        ON vsc_rate_matrix(vehicle_class, coverage_level, term_months, min_mileage, max_mileage);
                    ''')
                    conn.commit()
                    logger.info("VSC rate matrix table created")
        except psycopg2.Error as e:
            logger.error(f"Error creating rate matrix table: {e}")
            raise
    
    def import_pdf_rates(self):
        """Import all rates from PDF data using batch insert"""
        logger.info("Importing VSC rates from PDF data...")
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    total_rates = 0
                    rate_data_to_insert = []
                    
                    coverage_data = [
                        ('platinum', self.platinum_rates),
                        ('gold', self.gold_rates),
                        ('silver', self.silver_rates)
                    ]
                    
                    for coverage_level, rate_data in coverage_data:
                        logger.info(f"Importing {coverage_level.title()} coverage rates...")
                        
                        for vehicle_class in ['A', 'B', 'C']:
                            if vehicle_class not in rate_data:
                                continue
                                
                            class_data = rate_data[vehicle_class]
                            
                            for term_months, mileage_rates in class_data.items():
                                for mileage_key, rate in mileage_rates.items():
                                    mileage_info = self.mileage_ranges[mileage_key]
                                    rate_data_to_insert.append((
                                        vehicle_class,
                                        coverage_level,
                                        term_months,
                                        mileage_key,
                                        mileage_info['min'],
                                        mileage_info['max'],
                                        rate
                                    ))
                                    total_rates += 1
                    
                    execute_values(cursor, '''
                        INSERT INTO vsc_rate_matrix 
                        (vehicle_class, coverage_level, term_months, mileage_range_key,
                         min_mileage, max_mileage, rate_amount)
                        VALUES %s
                        ON CONFLICT (vehicle_class, coverage_level, term_months, mileage_range_key, effective_date)
                        DO NOTHING;
                    ''', rate_data_to_insert)
                    
                    conn.commit()
                    logger.info(f"Imported {total_rates} VSC rates from PDF")
        except psycopg2.Error as e:
            logger.error(f"Error importing PDF rates: {e}")
            raise
    
    def create_simplified_base_rates(self):
        """Create simplified base rates for compatibility"""
        logger.info("Creating simplified base rates for API compatibility...")
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    base_combinations = [
                        ('A', 'silver', 36, '15000_to_50000'),
                        ('A', 'gold', 36, '15000_to_50000'),
                        ('A', 'platinum', 36, '15000_to_50000'),
                        ('B', 'silver', 36, '15000_to_50000'),
                        ('B', 'gold', 36, '15000_to_50000'),
                        ('B', 'platinum', 36, '15000_to_50000'),
                        ('C', 'silver', 36, '15000_to_50000'),
                        ('C', 'gold', 36, '15000_to_50000'),
                        ('C', 'platinum', 36, '15000_to_50000'),
                    ]
                    
                    for vehicle_class, coverage_level, term, mileage_key in base_combinations:
                        cursor.execute('''
                            SELECT rate_amount 
                            FROM vsc_rate_matrix 
                            WHERE vehicle_class = %s AND coverage_level = %s 
                            AND term_months = %s AND mileage_range_key = %s;
                        ''', (vehicle_class, coverage_level, term, mileage_key))
                        
                        result = cursor.fetchone()
                        if result:
                            base_rate = result[0]
                            cursor.execute('''
                                INSERT INTO vsc_base_rates (vehicle_class, coverage_level, base_rate)
                                VALUES (%s, %s, %s)
                                ON CONFLICT (vehicle_class, coverage_level, effective_date)
                                DO UPDATE SET base_rate = EXCLUDED.base_rate;
                            ''', (vehicle_class, coverage_level, base_rate))
                    
                    conn.commit()
                    logger.info("Created simplified base rates")
        except psycopg2.Error as e:
            logger.error(f"Error creating base rates: {e}")
            raise
    
    def update_multipliers_from_pdf(self):
        """Update multipliers based on PDF rate patterns"""
        logger.info("Updating multipliers based on PDF rate analysis...")
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM vsc_term_multipliers;")
                    cursor.execute("DELETE FROM vsc_mileage_multipliers;")
                    
                    base_rate_36_month = 1582
                    term_multiplier_data = [
                        (12, 1574 / base_rate_36_month, '12 months', 1),
                        (24, 1575 / base_rate_36_month, '24 months', 2),
                        (36, 1.000, '36 months (base)', 3),
                        (48, 1584 / base_rate_36_month, '48 months', 4),
                        (60, 1585 / base_rate_36_month, '60 months', 5),
                        (72, 1590 / base_rate_36_month, '72 months', 6)
                    ]
                    
                    execute_values(cursor, '''
                        INSERT INTO vsc_term_multipliers 
                        (term_months, multiplier, description, display_order)
                        VALUES %s;
                    ''', [(t, round(m, 3), d, o) for t, m, d, o in term_multiplier_data])
                    
                    mileage_multiplier_data = [
                        ('up_to_15000', 0, 15000, 1574 / base_rate_36_month, '0-15k miles', 1),
                        ('15000_to_50000', 15001, 50000, 1.000, '15k-50k miles (base)', 2),
                        ('50000_to_75000', 50001, 75000, 1618 / base_rate_36_month, '50k-75k miles', 3),
                        ('75000_to_100000', 75001, 100000, 1637 / base_rate_36_month, '75k-100k miles', 4),
                        ('100000_to_125000', 100001, 125000, 1667 / base_rate_36_month, '100k-125k miles', 5),
                        ('125000_to_150000', 125001, 150000, 1681 / base_rate_36_month, '125k-150k miles', 6)
                    ]
                    
                    execute_values(cursor, '''
                        INSERT INTO vsc_mileage_multipliers 
                        (category, min_mileage, max_mileage, multiplier, description, display_order)
                        VALUES %s;
                    ''', [(c, min_m, max_m, round(m, 3), d, o) for c, min_m, max_m, m, d, o in mileage_multiplier_data])
                    
                    conn.commit()
                    logger.info("Updated multipliers from PDF analysis")
        except psycopg2.Error as e:
            logger.error(f"Error updating multipliers: {e}")
            raise
    
    def verify_import(self):
        """Verify the imported data"""
        logger.info("Verifying imported VSC rate data...")
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Fetch total number of rates in vsc_rate_matrix
                    cursor.execute("SELECT COUNT(*) FROM vsc_rate_matrix;")
                    total_rates = cursor.fetchone()[0]
                    
                    # Calculate expected number of rates
                    expected_rates = sum(
                        len(mileage_rates) * len(class_data) 
                        for _, rate_data in [
                            ('platinum', self.platinum_rates),
                            ('gold', self.gold_rates),
                            ('silver', self.silver_rates)
                        ]
                        for class_data in rate_data.values()
                        for mileage_rates in class_data.values()
                    )
                    
                    if total_rates != expected_rates:
                        logger.warning(f"Expected {expected_rates} rates, found {total_rates}")
                    
                    # Sample checks for specific rates
                    sample_checks = [
                        ('A', 'platinum', 36, '15000_to_50000', 1719),
                        ('B', 'gold', 24, '50000_to_75000', 1777),
                        ('C', 'silver', 48, '75000_to_100000', 2831)
                    ]
                    
                    for vehicle_class, coverage_level, term, mileage_key, expected_rate in sample_checks:
                        cursor.execute('''
                            SELECT rate_amount 
                            FROM vsc_rate_matrix 
                            WHERE vehicle_class = %s AND coverage_level = %s 
                            AND term_months = %s AND mileage_range_key = %s;
                        ''', (vehicle_class, coverage_level, term, mileage_key))
                        
                        result = cursor.fetchone()
                        if result and result[0] == expected_rate:
                            logger.info(f"Sample rate check passed: {vehicle_class}/{coverage_level}/{term} months/{mileage_key} = ${expected_rate}")
                        else:
                            logger.warning(f"Sample rate check failed: {vehicle_class}/{coverage_level}/{term} months/{mileage_key}, expected ${expected_rate}, got {result[0] if result else 'None'}")
                    
                    # Check base rates count
                    cursor.execute("SELECT COUNT(*) FROM vsc_base_rates;")
                    base_rate_count = cursor.fetchone()[0]
                    expected_base_rates = 9
                    if base_rate_count == expected_base_rates:
                        logger.info(f"Base rates count correct: {base_rate_count}")
                    else:
                        logger.warning(f"Expected {expected_base_rates} base rates, found {base_rate_count}")
                    
                    # Check term multipliers count
                    cursor.execute("SELECT COUNT(*) FROM vsc_term_multipliers;")
                    term_count = cursor.fetchone()[0]
                    if term_count == 6:
                        logger.info(f"Term multipliers count correct: {term_count}")
                    else:
                        logger.warning(f"Expected 6 term multipliers, found {term_count}")
                    
                    # Check mileage multipliers count
                    cursor.execute("SELECT COUNT(*) FROM vsc_mileage_multipliers;")
                    mileage_count = cursor.fetchone()[0]
                    if mileage_count == 6:
                        logger.info(f"Mileage multipliers count correct: {mileage_count}")
                    else:
                        logger.warning(f"Expected 6 mileage multipliers, found {mileage_count}")
                    
                    # Check for orphaned records
                    cursor.execute('''
                        SELECT COUNT(*) 
                        FROM vsc_rate_matrix rm
                        LEFT JOIN vsc_coverage_levels cl ON rm.coverage_level = cl.level_code
                        WHERE cl.level_code IS NULL;
                    ''')
                    orphaned_count = cursor.fetchone()[0]
                    if orphaned_count > 0:
                        logger.warning(f"Found {orphaned_count} orphaned rate matrix records without matching coverage levels")
                    else:
                        logger.info("No orphaned rate matrix records found")
                    
                    conn.commit()
                    logger.info("Verification completed")
        except psycopg2.Error as e:
            logger.error(f"Error verifying import: {e}")
            raise
    
    def run_full_import(self):
        """Run complete PDF rate import process"""
        logger.info("Starting complete VSC PDF rate import...")
        
        try:
            # Check prerequisites
            self.ensure_prerequisites()
            
            # Step 1: Clear existing data
            self.clear_existing_rates()
            
            # Step 2: Create rate matrix table
            self.create_rate_matrix_table()
            
            # Step 3: Import PDF rates
            self.import_pdf_rates()
            
            # Step 4: Create simplified base rates
            self.create_simplified_base_rates()
            
            # Step 5: Update multipliers
            self.update_multipliers_from_pdf()
            
            # Step 6: Verify import
            self.verify_import()
            
            logger.info("VSC PDF rate import completed successfully!")
            logger.info("Next steps:")
            logger.info("1. Test rate calculations with actual quotes")
            logger.info("2. Update API to use vsc_rate_matrix for precise pricing")
            logger.info("3. Create admin interface for rate management")
            return True
            
        except Exception as e:
            logger.error(f"PDF rate import failed: {e}")
            return False

if __name__ == "__main__":
    importer = VSCPDFRateImporter()
    success = importer.run_full_import()
    if not success:
        logger.error("Import failed. Please check the logs above.")
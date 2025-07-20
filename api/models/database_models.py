"""
ConnectedAutoCare Database Models
Comprehensive data models for users, customers, transactions, and business analytics
"""

import datetime
import json
from typing import Dict, List, Optional, Any

class DatabaseModels:
    """Database model definitions and utilities"""
    
    @staticmethod
    def get_current_timestamp():
        """Get current timestamp in ISO format"""
        return datetime.datetime.utcnow().isoformat()

class UserModel:
    """User account model for all user types"""
    
    def __init__(self):
        self.schema = {
            'id': str,  # UUID
            'email': str,
            'password_hash': str,
            'role': str,  # admin, wholesale_reseller, customer
            'status': str,  # active, inactive, suspended
            'profile': dict,
            'created_at': str,
            'updated_at': str,
            'last_login': str,
            'login_count': int,
            'email_verified': bool,
            'phone_verified': bool,
            'two_factor_enabled': bool,
            'preferences': dict,
            'metadata': dict
        }
    
    def create_user(self, user_data: Dict) -> Dict:
        """Create new user record"""
        timestamp = DatabaseModels.get_current_timestamp()
        
        user = {
            'id': user_data.get('id'),
            'email': user_data.get('email'),
            'password_hash': user_data.get('password_hash'),
            'role': user_data.get('role', 'customer'),
            'status': 'active',
            'profile': user_data.get('profile', {}),
            'created_at': timestamp,
            'updated_at': timestamp,
            'last_login': None,
            'login_count': 0,
            'email_verified': False,
            'phone_verified': False,
            'two_factor_enabled': False,
            'preferences': {
                'email_notifications': True,
                'sms_notifications': False,
                'marketing_emails': True
            },
            'metadata': {}
        }
        
        return user
    
    def update_login(self, user_id: str) -> Dict:
        """Update user login information"""
        return {
            'id': user_id,
            'last_login': DatabaseModels.get_current_timestamp(),
            'login_count': 'INCREMENT',  # Database would handle increment
            'updated_at': DatabaseModels.get_current_timestamp()
        }

class CustomerModel:
    """Customer information and transaction history"""
    
    def __init__(self):
        self.schema = {
            'id': str,  # UUID
            'user_id': str,  # Link to UserModel
            'customer_type': str,  # individual, business
            'personal_info': dict,
            'business_info': dict,
            'contact_info': dict,
            'billing_info': dict,
            'preferences': dict,
            'tags': list,
            'lifetime_value': float,
            'total_policies': int,
            'active_policies': int,
            'created_at': str,
            'updated_at': str,
            'last_activity': str,
            'status': str,
            'notes': list,
            'assigned_agent': str
        }
    
    def create_customer(self, customer_data: Dict) -> Dict:
        """Create new customer record"""
        timestamp = DatabaseModels.get_current_timestamp()
        
        customer = {
            'id': customer_data.get('id'),
            'user_id': customer_data.get('user_id'),
            'customer_type': customer_data.get('customer_type', 'individual'),
            'personal_info': {
                'first_name': customer_data.get('first_name', ''),
                'last_name': customer_data.get('last_name', ''),
                'date_of_birth': customer_data.get('date_of_birth'),
                'ssn_last_four': customer_data.get('ssn_last_four'),
                'drivers_license': customer_data.get('drivers_license')
            },
            'business_info': {
                'company_name': customer_data.get('company_name'),
                'tax_id': customer_data.get('tax_id'),
                'business_type': customer_data.get('business_type')
            },
            'contact_info': {
                'email': customer_data.get('email'),
                'phone': customer_data.get('phone'),
                'address': customer_data.get('address', {}),
                'preferred_contact': customer_data.get('preferred_contact', 'email')
            },
            'billing_info': {
                'payment_methods': [],
                'billing_address': customer_data.get('billing_address', {}),
                'auto_pay': False
            },
            'preferences': {
                'communication_frequency': 'normal',
                'preferred_language': 'en',
                'timezone': 'UTC'
            },
            'tags': [],
            'lifetime_value': 0.0,
            'total_policies': 0,
            'active_policies': 0,
            'created_at': timestamp,
            'updated_at': timestamp,
            'last_activity': timestamp,
            'status': 'active',
            'notes': [],
            'assigned_agent': customer_data.get('assigned_agent')
        }
        
        return customer

class PolicyModel:
    """Insurance policy and contract model"""
    
    def __init__(self):
        self.schema = {
            'id': str,  # UUID
            'policy_number': str,
            'customer_id': str,
            'product_type': str,  # vsc, hero_home, hero_auto, etc.
            'product_details': dict,
            'coverage_details': dict,
            'pricing': dict,
            'status': str,  # active, expired, cancelled, pending
            'effective_date': str,
            'expiration_date': str,
            'created_at': str,
            'updated_at': str,
            'created_by': str,  # User ID who created
            'payment_info': dict,
            'claims': list,
            'documents': list,
            'notes': list,
            'renewal_info': dict
        }
    
    def create_policy(self, policy_data: Dict) -> Dict:
        """Create new policy record"""
        timestamp = DatabaseModels.get_current_timestamp()
        
        policy = {
            'id': policy_data.get('id'),
            'policy_number': policy_data.get('policy_number'),
            'customer_id': policy_data.get('customer_id'),
            'product_type': policy_data.get('product_type'),
            'product_details': policy_data.get('product_details', {}),
            'coverage_details': policy_data.get('coverage_details', {}),
            'pricing': {
                'premium': policy_data.get('premium', 0),
                'fees': policy_data.get('fees', 0),
                'taxes': policy_data.get('taxes', 0),
                'total': policy_data.get('total', 0),
                'payment_frequency': policy_data.get('payment_frequency', 'annual'),
                'discount_applied': policy_data.get('discount_applied', 0)
            },
            'status': 'active',
            'effective_date': policy_data.get('effective_date'),
            'expiration_date': policy_data.get('expiration_date'),
            'created_at': timestamp,
            'updated_at': timestamp,
            'created_by': policy_data.get('created_by'),
            'payment_info': {
                'payment_method': policy_data.get('payment_method'),
                'payment_schedule': policy_data.get('payment_schedule', []),
                'next_payment_due': policy_data.get('next_payment_due')
            },
            'claims': [],
            'documents': [],
            'notes': [],
            'renewal_info': {
                'auto_renew': policy_data.get('auto_renew', False),
                'renewal_date': policy_data.get('renewal_date'),
                'renewal_premium': policy_data.get('renewal_premium')
            }
        }
        
        return policy

class TransactionModel:
    """Financial transaction model"""
    
    def __init__(self):
        self.schema = {
            'id': str,  # UUID
            'transaction_number': str,
            'customer_id': str,
            'policy_id': str,
            'type': str,  # purchase, payment, refund, commission
            'amount': float,
            'currency': str,
            'status': str,  # pending, completed, failed, cancelled
            'payment_method': dict,
            'processor_response': dict,
            'created_at': str,
            'processed_at': str,
            'created_by': str,
            'metadata': dict,
            'fees': dict,
            'taxes': dict
        }
    
    def create_transaction(self, transaction_data: Dict) -> Dict:
        """Create new transaction record"""
        timestamp = DatabaseModels.get_current_timestamp()
        
        transaction = {
            'id': transaction_data.get('id'),
            'transaction_number': transaction_data.get('transaction_number'),
            'customer_id': transaction_data.get('customer_id'),
            'policy_id': transaction_data.get('policy_id'),
            'type': transaction_data.get('type'),
            'amount': transaction_data.get('amount', 0.0),
            'currency': 'USD',
            'status': 'pending',
            'payment_method': transaction_data.get('payment_method', {}),
            'processor_response': {},
            'created_at': timestamp,
            'processed_at': None,
            'created_by': transaction_data.get('created_by'),
            'metadata': transaction_data.get('metadata', {}),
            'fees': transaction_data.get('fees', {}),
            'taxes': transaction_data.get('taxes', {})
        }
        
        return transaction

class ResellerModel:
    """Wholesale reseller model"""
    
    def __init__(self):
        self.schema = {
            'id': str,  # UUID
            'user_id': str,  # Link to UserModel
            'business_name': str,
            'license_number': str,
            'license_state': str,
            'business_type': str,
            'contact_info': dict,
            'commission_structure': dict,
            'sales_metrics': dict,
            'status': str,  # active, inactive, suspended
            'tier': str,  # bronze, silver, gold, platinum
            'created_at': str,
            'updated_at': str,
            'approved_at': str,
            'approved_by': str,
            'documents': list,
            'territories': list,
            'product_access': list
        }
    
    def create_reseller(self, reseller_data: Dict) -> Dict:
        """Create new reseller record"""
        timestamp = DatabaseModels.get_current_timestamp()
        
        reseller = {
            'id': reseller_data.get('id'),
            'user_id': reseller_data.get('user_id'),
            'business_name': reseller_data.get('business_name'),
            'license_number': reseller_data.get('license_number'),
            'license_state': reseller_data.get('license_state'),
            'business_type': reseller_data.get('business_type', 'insurance_agency'),
            'contact_info': {
                'primary_contact': reseller_data.get('primary_contact', {}),
                'business_address': reseller_data.get('business_address', {}),
                'phone': reseller_data.get('phone'),
                'email': reseller_data.get('email'),
                'website': reseller_data.get('website')
            },
            'commission_structure': {
                'vsc_commission': reseller_data.get('vsc_commission', 0.15),
                'hero_commission': reseller_data.get('hero_commission', 0.20),
                'payment_terms': reseller_data.get('payment_terms', 'net_30'),
                'minimum_volume': reseller_data.get('minimum_volume', 0)
            },
            'sales_metrics': {
                'total_sales': 0.0,
                'monthly_sales': 0.0,
                'policies_sold': 0,
                'conversion_rate': 0.0,
                'average_sale': 0.0
            },
            'status': 'pending',
            'tier': 'bronze',
            'created_at': timestamp,
            'updated_at': timestamp,
            'approved_at': None,
            'approved_by': None,
            'documents': [],
            'territories': reseller_data.get('territories', []),
            'product_access': reseller_data.get('product_access', ['all'])
        }
        
        return reseller

class AnalyticsModel:
    """Business analytics and KPI model"""
    
    def __init__(self):
        self.schema = {
            'id': str,
            'metric_name': str,
            'metric_type': str,  # revenue, conversion, customer, product
            'value': float,
            'period': str,  # daily, weekly, monthly, yearly
            'date': str,
            'dimensions': dict,  # Additional breakdown data
            'created_at': str,
            'metadata': dict
        }
    
    def create_metric(self, metric_data: Dict) -> Dict:
        """Create analytics metric record"""
        timestamp = DatabaseModels.get_current_timestamp()
        
        metric = {
            'id': metric_data.get('id'),
            'metric_name': metric_data.get('metric_name'),
            'metric_type': metric_data.get('metric_type'),
            'value': metric_data.get('value', 0.0),
            'period': metric_data.get('period', 'daily'),
            'date': metric_data.get('date'),
            'dimensions': metric_data.get('dimensions', {}),
            'created_at': timestamp,
            'metadata': metric_data.get('metadata', {})
        }
        
        return metric

class DatabaseUtils:
    """Database utility functions"""
    
    @staticmethod
    def generate_policy_number(product_type: str) -> str:
        """Generate unique policy number"""
        timestamp = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
        prefix = {
            'vsc': 'VSC',
            'hero_home': 'HHP',
            'hero_auto': 'HAP',
            'hero_deductible': 'HDR'
        }.get(product_type, 'POL')
        
        return f"{prefix}-{timestamp}"
    
    @staticmethod
    def generate_transaction_number() -> str:
        """Generate unique transaction number"""
        timestamp = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
        return f"TXN-{timestamp}"
    
    @staticmethod
    def calculate_lifetime_value(transactions: List[Dict]) -> float:
        """Calculate customer lifetime value"""
        total = 0.0
        for transaction in transactions:
            if transaction.get('status') == 'completed' and transaction.get('type') == 'purchase':
                total += transaction.get('amount', 0.0)
        return total
    
    @staticmethod
    def get_customer_metrics(customer_id: str, transactions: List[Dict], policies: List[Dict]) -> Dict:
        """Calculate customer metrics"""
        active_policies = [p for p in policies if p.get('status') == 'active']
        completed_transactions = [t for t in transactions if t.get('status') == 'completed']
        
        return {
            'lifetime_value': DatabaseUtils.calculate_lifetime_value(completed_transactions),
            'total_policies': len(policies),
            'active_policies': len(active_policies),
            'total_transactions': len(completed_transactions),
            'average_transaction': sum(t.get('amount', 0) for t in completed_transactions) / max(len(completed_transactions), 1),
            'last_purchase': max([t.get('created_at') for t in completed_transactions], default=None)
        }


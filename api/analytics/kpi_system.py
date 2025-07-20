"""
ConnectedAutoCare KPI Analytics and Reporting System
Comprehensive business intelligence and performance tracking
"""

import datetime
import json
from typing import Dict, List, Optional, Any
from collections import defaultdict
import statistics

class KPISystem:
    """Key Performance Indicator tracking and analytics system"""
    
    def __init__(self):
        self.metrics_cache = {}
        self.last_calculation = {}
    
    def calculate_revenue_metrics(self, transactions: List[Dict], period: str = 'monthly') -> Dict:
        """Calculate revenue-based KPIs"""
        now = datetime.datetime.utcnow()
        
        # Filter completed transactions
        completed_transactions = [
            t for t in transactions 
            if t.get('status') == 'completed' and t.get('type') == 'purchase'
        ]
        
        # Group by period
        revenue_by_period = defaultdict(float)
        transaction_count_by_period = defaultdict(int)
        
        for transaction in completed_transactions:
            created_at = datetime.datetime.fromisoformat(transaction.get('created_at', ''))
            
            if period == 'daily':
                period_key = created_at.strftime('%Y-%m-%d')
            elif period == 'weekly':
                period_key = created_at.strftime('%Y-W%U')
            elif period == 'monthly':
                period_key = created_at.strftime('%Y-%m')
            else:  # yearly
                period_key = created_at.strftime('%Y')
            
            revenue_by_period[period_key] += transaction.get('amount', 0.0)
            transaction_count_by_period[period_key] += 1
        
        # Calculate metrics
        total_revenue = sum(revenue_by_period.values())
        total_transactions = sum(transaction_count_by_period.values())
        average_transaction_value = total_revenue / max(total_transactions, 1)
        
        # Growth calculations
        periods = sorted(revenue_by_period.keys())
        current_period_revenue = revenue_by_period.get(periods[-1] if periods else '', 0)
        previous_period_revenue = revenue_by_period.get(periods[-2] if len(periods) > 1 else '', 0)
        
        growth_rate = 0
        if previous_period_revenue > 0:
            growth_rate = ((current_period_revenue - previous_period_revenue) / previous_period_revenue) * 100
        
        return {
            'total_revenue': total_revenue,
            'current_period_revenue': current_period_revenue,
            'previous_period_revenue': previous_period_revenue,
            'growth_rate': growth_rate,
            'total_transactions': total_transactions,
            'average_transaction_value': average_transaction_value,
            'revenue_by_period': dict(revenue_by_period),
            'transaction_count_by_period': dict(transaction_count_by_period),
            'calculated_at': now.isoformat()
        }
    
    def calculate_customer_metrics(self, customers: List[Dict], transactions: List[Dict]) -> Dict:
        """Calculate customer-related KPIs"""
        now = datetime.datetime.utcnow()
        
        # Customer acquisition metrics
        customers_by_month = defaultdict(int)
        for customer in customers:
            created_at = datetime.datetime.fromisoformat(customer.get('created_at', ''))
            month_key = created_at.strftime('%Y-%m')
            customers_by_month[month_key] += 1
        
        # Customer lifetime value
        customer_values = {}
        for customer in customers:
            customer_id = customer.get('id')
            customer_transactions = [
                t for t in transactions 
                if t.get('customer_id') == customer_id and t.get('status') == 'completed'
            ]
            customer_values[customer_id] = sum(t.get('amount', 0) for t in customer_transactions)
        
        total_customers = len(customers)
        active_customers = len([c for c in customers if c.get('status') == 'active'])
        average_ltv = statistics.mean(customer_values.values()) if customer_values else 0
        
        # Customer retention (simplified - customers with multiple purchases)
        customer_transactions = defaultdict(list)
        for transaction in transactions:
            if transaction.get('status') == 'completed':
                customer_id = transaction.get('customer_id')
                customer_transactions[customer_id].append(transaction)
        
        repeat_customers = len([
            customer_id for customer_id, trans_list in customer_transactions.items()
            if len(trans_list) > 1
        ])
        
        retention_rate = (repeat_customers / max(total_customers, 1)) * 100
        
        return {
            'total_customers': total_customers,
            'active_customers': active_customers,
            'new_customers_this_month': customers_by_month.get(now.strftime('%Y-%m'), 0),
            'average_lifetime_value': average_ltv,
            'retention_rate': retention_rate,
            'repeat_customers': repeat_customers,
            'customers_by_month': dict(customers_by_month),
            'calculated_at': now.isoformat()
        }
    
    def calculate_product_metrics(self, policies: List[Dict], transactions: List[Dict]) -> Dict:
        """Calculate product performance KPIs"""
        now = datetime.datetime.utcnow()
        
        # Product sales by type
        product_sales = defaultdict(lambda: {'count': 0, 'revenue': 0.0})
        product_policies = defaultdict(int)
        
        for policy in policies:
            product_type = policy.get('product_type', 'unknown')
            product_policies[product_type] += 1
        
        for transaction in transactions:
            if transaction.get('status') == 'completed' and transaction.get('type') == 'purchase':
                policy_id = transaction.get('policy_id')
                policy = next((p for p in policies if p.get('id') == policy_id), None)
                
                if policy:
                    product_type = policy.get('product_type', 'unknown')
                    product_sales[product_type]['count'] += 1
                    product_sales[product_type]['revenue'] += transaction.get('amount', 0.0)
        
        # Calculate conversion rates and averages
        product_metrics = {}
        for product_type, sales_data in product_sales.items():
            policies_count = product_policies.get(product_type, 0)
            conversion_rate = (sales_data['count'] / max(policies_count, 1)) * 100
            average_sale = sales_data['revenue'] / max(sales_data['count'], 1)
            
            product_metrics[product_type] = {
                'policies_issued': policies_count,
                'sales_count': sales_data['count'],
                'total_revenue': sales_data['revenue'],
                'conversion_rate': conversion_rate,
                'average_sale_value': average_sale
            }
        
        # Top performing products
        top_products_by_revenue = sorted(
            product_metrics.items(),
            key=lambda x: x[1]['total_revenue'],
            reverse=True
        )[:5]
        
        top_products_by_volume = sorted(
            product_metrics.items(),
            key=lambda x: x[1]['sales_count'],
            reverse=True
        )[:5]
        
        return {
            'product_metrics': product_metrics,
            'top_products_by_revenue': dict(top_products_by_revenue),
            'top_products_by_volume': dict(top_products_by_volume),
            'total_products': len(product_metrics),
            'calculated_at': now.isoformat()
        }
    
    def calculate_reseller_metrics(self, resellers: List[Dict], transactions: List[Dict]) -> Dict:
        """Calculate reseller performance KPIs"""
        now = datetime.datetime.utcnow()
        
        # Reseller performance
        reseller_performance = defaultdict(lambda: {
            'sales_count': 0,
            'total_revenue': 0.0,
            'commission_earned': 0.0
        })
        
        for transaction in transactions:
            if transaction.get('status') == 'completed' and transaction.get('type') == 'purchase':
                created_by = transaction.get('created_by')
                reseller = next((r for r in resellers if r.get('user_id') == created_by), None)
                
                if reseller:
                    reseller_id = reseller.get('id')
                    amount = transaction.get('amount', 0.0)
                    
                    reseller_performance[reseller_id]['sales_count'] += 1
                    reseller_performance[reseller_id]['total_revenue'] += amount
                    
                    # Calculate commission (simplified)
                    commission_rate = reseller.get('commission_structure', {}).get('vsc_commission', 0.15)
                    reseller_performance[reseller_id]['commission_earned'] += amount * commission_rate
        
        # Top performers
        top_resellers_by_revenue = sorted(
            reseller_performance.items(),
            key=lambda x: x[1]['total_revenue'],
            reverse=True
        )[:10]
        
        total_resellers = len(resellers)
        active_resellers = len([r for r in resellers if r.get('status') == 'active'])
        
        return {
            'total_resellers': total_resellers,
            'active_resellers': active_resellers,
            'reseller_performance': dict(reseller_performance),
            'top_resellers_by_revenue': dict(top_resellers_by_revenue),
            'calculated_at': now.isoformat()
        }
    
    def calculate_operational_metrics(self, policies: List[Dict], customers: List[Dict]) -> Dict:
        """Calculate operational KPIs"""
        now = datetime.datetime.utcnow()
        
        # Policy status distribution
        policy_status = defaultdict(int)
        for policy in policies:
            status = policy.get('status', 'unknown')
            policy_status[status] += 1
        
        # Customer status distribution
        customer_status = defaultdict(int)
        for customer in customers:
            status = customer.get('status', 'unknown')
            customer_status[status] += 1
        
        # Policy expiration tracking
        expiring_soon = 0
        expired = 0
        
        for policy in policies:
            if policy.get('status') == 'active':
                expiration_date = policy.get('expiration_date')
                if expiration_date:
                    exp_date = datetime.datetime.fromisoformat(expiration_date)
                    days_until_expiry = (exp_date - now).days
                    
                    if days_until_expiry < 0:
                        expired += 1
                    elif days_until_expiry <= 30:
                        expiring_soon += 1
        
        return {
            'total_policies': len(policies),
            'active_policies': policy_status.get('active', 0),
            'expired_policies': policy_status.get('expired', 0),
            'cancelled_policies': policy_status.get('cancelled', 0),
            'policies_expiring_soon': expiring_soon,
            'overdue_policies': expired,
            'policy_status_distribution': dict(policy_status),
            'customer_status_distribution': dict(customer_status),
            'calculated_at': now.isoformat()
        }
    
    def generate_dashboard_data(self, data: Dict) -> Dict:
        """Generate comprehensive dashboard data"""
        transactions = data.get('transactions', [])
        customers = data.get('customers', [])
        policies = data.get('policies', [])
        resellers = data.get('resellers', [])
        
        dashboard = {
            'revenue_metrics': self.calculate_revenue_metrics(transactions),
            'customer_metrics': self.calculate_customer_metrics(customers, transactions),
            'product_metrics': self.calculate_product_metrics(policies, transactions),
            'reseller_metrics': self.calculate_reseller_metrics(resellers, transactions),
            'operational_metrics': self.calculate_operational_metrics(policies, customers),
            'generated_at': datetime.datetime.utcnow().isoformat()
        }
        
        return dashboard
    
    def generate_report(self, report_type: str, data: Dict, date_range: Dict = None) -> Dict:
        """Generate specific business reports"""
        if report_type == 'revenue':
            return self._generate_revenue_report(data, date_range)
        elif report_type == 'customer':
            return self._generate_customer_report(data, date_range)
        elif report_type == 'product':
            return self._generate_product_report(data, date_range)
        elif report_type == 'reseller':
            return self._generate_reseller_report(data, date_range)
        else:
            return {'error': f'Unknown report type: {report_type}'}
    
    def _generate_revenue_report(self, data: Dict, date_range: Dict = None) -> Dict:
        """Generate detailed revenue report"""
        transactions = data.get('transactions', [])
        
        # Filter by date range if provided
        if date_range:
            start_date = datetime.datetime.fromisoformat(date_range.get('start'))
            end_date = datetime.datetime.fromisoformat(date_range.get('end'))
            
            transactions = [
                t for t in transactions
                if start_date <= datetime.datetime.fromisoformat(t.get('created_at', '')) <= end_date
            ]
        
        revenue_metrics = self.calculate_revenue_metrics(transactions)
        
        # Additional revenue analysis
        revenue_by_product = defaultdict(float)
        revenue_by_month = defaultdict(float)
        
        for transaction in transactions:
            if transaction.get('status') == 'completed':
                amount = transaction.get('amount', 0.0)
                created_at = datetime.datetime.fromisoformat(transaction.get('created_at', ''))
                month_key = created_at.strftime('%Y-%m')
                
                revenue_by_month[month_key] += amount
                
                # Get product type from policy
                policy_id = transaction.get('policy_id')
                policies = data.get('policies', [])
                policy = next((p for p in policies if p.get('id') == policy_id), None)
                
                if policy:
                    product_type = policy.get('product_type', 'unknown')
                    revenue_by_product[product_type] += amount
        
        return {
            'summary': revenue_metrics,
            'revenue_by_product': dict(revenue_by_product),
            'revenue_by_month': dict(revenue_by_month),
            'report_type': 'revenue',
            'date_range': date_range,
            'generated_at': datetime.datetime.utcnow().isoformat()
        }
    
    def _generate_customer_report(self, data: Dict, date_range: Dict = None) -> Dict:
        """Generate detailed customer report"""
        customers = data.get('customers', [])
        transactions = data.get('transactions', [])
        
        customer_metrics = self.calculate_customer_metrics(customers, transactions)
        
        # Customer segmentation
        customer_segments = {
            'high_value': [],
            'medium_value': [],
            'low_value': []
        }
        
        for customer in customers:
            customer_id = customer.get('id')
            ltv = customer.get('lifetime_value', 0)
            
            if ltv > 1000:
                customer_segments['high_value'].append(customer)
            elif ltv > 500:
                customer_segments['medium_value'].append(customer)
            else:
                customer_segments['low_value'].append(customer)
        
        return {
            'summary': customer_metrics,
            'customer_segments': {
                'high_value': len(customer_segments['high_value']),
                'medium_value': len(customer_segments['medium_value']),
                'low_value': len(customer_segments['low_value'])
            },
            'report_type': 'customer',
            'date_range': date_range,
            'generated_at': datetime.datetime.utcnow().isoformat()
        }
    
    def _generate_product_report(self, data: Dict, date_range: Dict = None) -> Dict:
        """Generate detailed product performance report"""
        policies = data.get('policies', [])
        transactions = data.get('transactions', [])
        
        product_metrics = self.calculate_product_metrics(policies, transactions)
        
        return {
            'summary': product_metrics,
            'report_type': 'product',
            'date_range': date_range,
            'generated_at': datetime.datetime.utcnow().isoformat()
        }
    
    def _generate_reseller_report(self, data: Dict, date_range: Dict = None) -> Dict:
        """Generate detailed reseller performance report"""
        resellers = data.get('resellers', [])
        transactions = data.get('transactions', [])
        
        reseller_metrics = self.calculate_reseller_metrics(resellers, transactions)
        
        return {
            'summary': reseller_metrics,
            'report_type': 'reseller',
            'date_range': date_range,
            'generated_at': datetime.datetime.utcnow().isoformat()
        }

class ReportExporter:
    """Export reports in various formats"""
    
    @staticmethod
    def export_to_csv(data: Dict, filename: str) -> str:
        """Export report data to CSV format"""
        # This would generate CSV content
        csv_content = "Report Type,Metric,Value,Date\n"
        
        # Add sample data structure
        for key, value in data.items():
            if isinstance(value, (int, float)):
                csv_content += f"{data.get('report_type', 'unknown')},{key},{value},{data.get('generated_at', '')}\n"
        
        return csv_content
    
    @staticmethod
    def export_to_json(data: Dict) -> str:
        """Export report data to JSON format"""
        return json.dumps(data, indent=2, default=str)
    
    @staticmethod
    def export_to_excel(data: Dict, filename: str) -> bytes:
        """Export report data to Excel format"""
        # This would use openpyxl or similar to create Excel file
        # For now, return placeholder
        return b"Excel export placeholder"


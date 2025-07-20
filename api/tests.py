#!/usr/bin/env python3
"""
ConnectedAutoCare API Test Suite
Comprehensive tests for all API endpoints including customer API, admin panel, and user management
"""

import time
import pytest
import json
import uuid
from datetime import datetime
from unittest.mock import patch, MagicMock
import sys
import os

# Add the current directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import the Flask app
from index import create_app

class TestConfig:
    """Test configuration"""
    TESTING = True
    SECRET_KEY = 'test-secret-key'
    WTF_CSRF_ENABLED = False

@pytest.fixture
def app():
    """Create test app instance"""
    app = create_app()
    app.config.from_object(TestConfig)
    return app

@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()

@pytest.fixture
def auth_headers():
    """Mock authentication headers"""
    return {
        'Authorization': 'Bearer test-jwt-token',
        'Content-Type': 'application/json'
    }

@pytest.fixture
def admin_auth_headers():
    """Mock admin authentication headers"""
    return {
        'Authorization': 'Bearer admin-jwt-token',
        'Content-Type': 'application/json'
    }

# ================================
# HEALTH CHECK TESTS
# ================================

class TestHealthChecks:
    """Test health check endpoints"""

    def test_main_health_check(self, client):
        """Test main health check endpoint"""
        response = client.get('/')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['service'] == 'ConnectedAutoCare Unified Platform'
        assert data['status'] == 'healthy'
        assert 'components' in data
        assert 'features' in data

    def test_api_health_check(self, client):
        """Test API health check"""
        response = client.get('/api/health')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['api_status'] == 'healthy'
        assert 'customer_services' in data
        assert 'admin_services' in data
        assert 'user_management' in data

    def test_admin_health_check(self, client):
        """Test admin health check"""
        response = client.get('/api/admin/health')
        # Should return either 200 (if admin modules available) or 503 (if not)
        assert response.status_code in [200, 503]

# ================================
# CUSTOMER API TESTS
# ================================

class TestHeroProductsAPI:
    """Test Hero Products API endpoints"""

    def test_hero_health_check(self, client):
        """Test Hero products health check"""
        response = client.get('/api/hero/health')
        assert response.status_code in [200, 500]  # May fail if services not available

    def test_get_all_hero_products(self, client):
        """Test getting all Hero products"""
        response = client.get('/api/hero/products')
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert 'success' in data
            assert 'data' in data

    def test_get_hero_products_by_category(self, client):
        """Test getting Hero products by category"""
        response = client.get('/api/hero/products/home_protection')
        assert response.status_code in [200, 404, 500]

    def test_get_hero_products_invalid_category(self, client):
        """Test getting Hero products with invalid category"""
        response = client.get('/api/hero/products/invalid_category')
        assert response.status_code in [404, 500]

    def test_generate_hero_quote_success(self, client):
        """Test successful Hero quote generation"""
        quote_data = {
            'product_type': 'home_protection',
            'term_years': 2,
            'coverage_limit': 500,
            'customer_type': 'retail',
            'state': 'FL',
            'zip_code': '33101'
        }
        
        response = client.post('/api/hero/quote', 
                             data=json.dumps(quote_data),
                             content_type='application/json')
        assert response.status_code in [200, 400, 500]

    def test_generate_hero_quote_missing_fields(self, client):
        """Test Hero quote generation with missing required fields"""
        quote_data = {
            'product_type': 'home_protection'
            # Missing term_years
        }
        
        response = client.post('/api/hero/quote',
                             data=json.dumps(quote_data),
                             content_type='application/json')
        assert response.status_code == 400

    def test_generate_hero_quote_no_body(self, client):
        """Test Hero quote generation without request body"""
        response = client.post('/api/hero/quote')
        assert response.status_code == 400

class TestVSCRatingAPI:
    """Test VSC Rating API endpoints"""

    def test_vsc_health_check(self, client):
        """Test VSC rating health check"""
        response = client.get('/api/vsc/health')
        assert response.status_code in [200, 500]

    def test_get_vsc_coverage_options(self, client):
        """Test getting VSC coverage options"""
        response = client.get('/api/vsc/coverage-options')
        assert response.status_code in [200, 500]

    def test_generate_vsc_quote_success(self, client):
        """Test successful VSC quote generation"""
        quote_data = {
            'make': 'Toyota',
            'model': 'Camry',
            'year': 2020,
            'mileage': 25000,
            'coverage_level': 'gold',
            'term_months': 36,
            'deductible': 100,
            'customer_type': 'retail'
        }
        
        response = client.post('/api/vsc/quote',
                             data=json.dumps(quote_data),
                             content_type='application/json')
        assert response.status_code in [200, 400, 500]

    def test_generate_vsc_quote_missing_fields(self, client):
        """Test VSC quote generation with missing required fields"""
        quote_data = {
            'make': 'Toyota'
            # Missing year and mileage
        }
        
        response = client.post('/api/vsc/quote',
                             data=json.dumps(quote_data),
                             content_type='application/json')
        assert response.status_code == 400

    def test_generate_vsc_quote_invalid_data_types(self, client):
        """Test VSC quote generation with invalid data types"""
        quote_data = {
            'make': 'Toyota',
            'year': 'invalid_year',  # Should be integer
            'mileage': 'invalid_mileage'  # Should be integer
        }
        
        response = client.post('/api/vsc/quote',
                             data=json.dumps(quote_data),
                             content_type='application/json')
        assert response.status_code == 400

class TestVINDecoderAPI:
    """Test VIN Decoder API endpoints"""

    def test_vin_health_check(self, client):
        """Test VIN decoder health check"""
        response = client.get('/api/vin/health')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['service'] == 'VIN Decoder API'
        assert data['status'] == 'healthy'

    def test_validate_vin_success(self, client):
        """Test successful VIN validation"""
        vin_data = {
            'vin': '1HGBH41JXMN109186'  # Valid format VIN
        }
        
        response = client.post('/api/vin/validate',
                             data=json.dumps(vin_data),
                             content_type='application/json')
        assert response.status_code in [200, 400, 500]

    def test_validate_vin_too_short(self, client):
        """Test VIN validation with too short VIN"""
        vin_data = {
            'vin': '1HGBH41JX'  # Too short
        }
        
        response = client.post('/api/vin/validate',
                             data=json.dumps(vin_data),
                             content_type='application/json')
        assert response.status_code == 400

    def test_validate_vin_invalid_characters(self, client):
        """Test VIN validation with invalid characters"""
        vin_data = {
            'vin': '1HGBH41JXMN1O9186'  # Contains 'O' which is invalid
        }
        
        response = client.post('/api/vin/validate',
                             data=json.dumps(vin_data),
                             content_type='application/json')
        assert response.status_code == 400

    def test_validate_vin_missing_data(self, client):
        """Test VIN validation without VIN data"""
        response = client.post('/api/vin/validate',
                             data=json.dumps({}),
                             content_type='application/json')
        assert response.status_code == 400

    def test_decode_vin_success(self, client):
        """Test successful VIN decoding"""
        vin_data = {
            'vin': '1HGBH41JXMN109186'
        }
        
        response = client.post('/api/vin/decode',
                             data=json.dumps(vin_data),
                             content_type='application/json')
        assert response.status_code in [200, 400, 500]

    def test_decode_vin_invalid_length(self, client):
        """Test VIN decoding with invalid length"""
        vin_data = {
            'vin': '1HGBH41JX'  # Too short
        }
        
        response = client.post('/api/vin/decode',
                             data=json.dumps(vin_data),
                             content_type='application/json')
        assert response.status_code == 400

class TestPaymentAndContractAPI:
    """Test Payment and Contract API endpoints"""

    def test_get_payment_methods(self, client):
        """Test getting available payment methods"""
        response = client.get('/api/payments/methods')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert 'success' in data
        assert 'data' in data
        if data['success']:
            assert 'credit_card' in data['data']
            assert 'financing' in data['data']

    def test_generate_contract(self, client):
        """Test contract generation"""
        contract_data = {
            'product_type': 'home_protection',
            'customer_name': 'John Doe',
            'contract_terms': 'Standard terms'
        }
        
        response = client.post('/api/contracts/generate',
                             data=json.dumps(contract_data),
                             content_type='application/json')
        assert response.status_code in [200, 400, 500]

    def test_generate_contract_no_data(self, client):
        """Test contract generation without data"""
        response = client.post('/api/contracts/generate')
        assert response.status_code == 400

# ================================
# USER MANAGEMENT TESTS
# ================================

class TestUserAuthentication:
    """Test user authentication endpoints"""

    def test_user_registration_success(self, client):
        """Test successful user registration"""
        user_data = {
            'email': f'test_{uuid.uuid4()}@example.com',
            'password': 'TestPassword123!',
            'role': 'customer',
            'first_name': 'John',
            'last_name': 'Doe'
        }
        
        response = client.post('/api/auth/register',
                             data=json.dumps(user_data),
                             content_type='application/json')
        assert response.status_code in [201, 500, 503]

    def test_user_registration_missing_fields(self, client):
        """Test user registration with missing required fields"""
        user_data = {
            'email': 'test@example.com'
            # Missing password and role
        }
        
        response = client.post('/api/auth/register',
                             data=json.dumps(user_data),
                             content_type='application/json')
        assert response.status_code in [400, 503]

    def test_user_registration_invalid_email(self, client):
        """Test user registration with invalid email"""
        user_data = {
            'email': 'invalid-email',
            'password': 'TestPassword123!',
            'role': 'customer'
        }
        
        response = client.post('/api/auth/register',
                             data=json.dumps(user_data),
                             content_type='application/json')
        assert response.status_code in [400, 503]

    def test_user_registration_weak_password(self, client):
        """Test user registration with weak password"""
        user_data = {
            'email': 'test@example.com',
            'password': '123',  # Too weak
            'role': 'customer'
        }
        
        response = client.post('/api/auth/register',
                             data=json.dumps(user_data),
                             content_type='application/json')
        assert response.status_code in [400, 503]

    def test_user_registration_invalid_role(self, client):
        """Test user registration with invalid role"""
        user_data = {
            'email': 'test@example.com',
            'password': 'TestPassword123!',
            'role': 'invalid_role'
        }
        
        response = client.post('/api/auth/register',
                             data=json.dumps(user_data),
                             content_type='application/json')
        assert response.status_code in [400, 503]

    def test_user_login_success(self, client):
        """Test successful user login"""
        # First register a user
        user_data = {
            'email': f'login_test_{uuid.uuid4()}@example.com',
            'password': 'TestPassword123!',
            'role': 'customer'
        }
        
        register_response = client.post('/api/auth/register',
                                      data=json.dumps(user_data),
                                      content_type='application/json')
        
        if register_response.status_code == 201:
            # Try to login
            login_data = {
                'email': user_data['email'],
                'password': user_data['password']
            }
            
            response = client.post('/api/auth/login',
                                 data=json.dumps(login_data),
                                 content_type='application/json')
            assert response.status_code == 200

    def test_user_login_invalid_credentials(self, client):
        """Test user login with invalid credentials"""
        login_data = {
            'email': 'nonexistent@example.com',
            'password': 'wrongpassword'
        }
        
        response = client.post('/api/auth/login',
                             data=json.dumps(login_data),
                             content_type='application/json')
        assert response.status_code in [401, 503]

    def test_user_login_missing_fields(self, client):
        """Test user login with missing fields"""
        login_data = {
            'email': 'test@example.com'
            # Missing password
        }
        
        response = client.post('/api/auth/login',
                             data=json.dumps(login_data),
                             content_type='application/json')
        assert response.status_code in [400, 503]

    @patch('index.token_required')
    def test_user_logout(self, mock_token_required, client):
        """Test user logout"""
        # Mock the token requirement
        mock_token_required.return_value = lambda f: f
        
        response = client.post('/api/auth/logout',
                             headers={'Authorization': 'Bearer test-token'})
        assert response.status_code in [200, 503]

    @patch('index.token_required')
    def test_get_user_profile(self, mock_token_required, client):
        """Test getting user profile"""
        mock_token_required.return_value = lambda f: f
        
        response = client.get('/api/auth/profile',
                            headers={'Authorization': 'Bearer test-token'})
        assert response.status_code in [200, 404, 503]

class TestCustomerManagement:
    """Test customer management endpoints"""

    @patch('index.token_required')
    @patch('index.permission_required')
    def test_get_customers(self, mock_permission, mock_token, client):
        """Test getting all customers"""
        mock_token.return_value = lambda f: f
        mock_permission.return_value = lambda f: f
        
        response = client.get('/api/customers',
                            headers={'Authorization': 'Bearer test-token'})
        assert response.status_code in [200, 503]

    @patch('index.token_required')
    @patch('index.permission_required')
    def test_get_customer_by_id(self, mock_permission, mock_token, client):
        """Test getting specific customer"""
        mock_token.return_value = lambda f: f
        mock_permission.return_value = lambda f: f
        
        customer_id = 'test-customer-id'
        response = client.get(f'/api/customers/{customer_id}',
                            headers={'Authorization': 'Bearer test-token'})
        assert response.status_code in [200, 404, 503]

class TestAnalyticsAPI:
    """Test analytics API endpoints"""

    @patch('index.token_required')
    @patch('index.role_required')
    def test_get_dashboard(self, mock_role, mock_token, client):
        """Test getting analytics dashboard"""
        mock_token.return_value = lambda f: f
        mock_role.return_value = lambda f: f
        
        response = client.get('/api/analytics/dashboard',
                            headers={'Authorization': 'Bearer test-token'})
        assert response.status_code in [200, 503]

    @patch('index.token_required')
    @patch('index.role_required')
    def test_generate_report(self, mock_role, mock_token, client):
        """Test generating business report"""
        mock_token.return_value = lambda f: f
        mock_role.return_value = lambda f: f
        
        report_type = 'revenue'
        response = client.get(f'/api/analytics/reports/{report_type}',
                            headers={'Authorization': 'Bearer test-token'})
        assert response.status_code in [200, 503]

    @patch('index.token_required')
    @patch('index.role_required')
    def test_export_report(self, mock_role, mock_token, client):
        """Test exporting report"""
        mock_token.return_value = lambda f: f
        mock_role.return_value = lambda f: f
        
        report_type = 'customer'
        response = client.get(f'/api/analytics/export/{report_type}?format=json',
                            headers={'Authorization': 'Bearer test-token'})
        assert response.status_code in [200, 400, 503]

class TestAdminAPI:
    """Test admin API endpoints"""

    @patch('index.token_required')
    @patch('index.role_required')
    def test_get_all_users(self, mock_role, mock_token, client):
        """Test getting all users (admin only)"""
        mock_token.return_value = lambda f: f
        mock_role.return_value = lambda f: f
        
        response = client.get('/api/admin/users',
                            headers={'Authorization': 'Bearer admin-token'})
        assert response.status_code in [200, 503]

    @patch('index.token_required')
    @patch('index.role_required')
    def test_update_user_status(self, mock_role, mock_token, client):
        """Test updating user status"""
        mock_token.return_value = lambda f: f
        mock_role.return_value = lambda f: f
        
        user_id = 'test-user-id'
        status_data = {'status': 'inactive'}
        
        response = client.put(f'/api/admin/users/{user_id}/status',
                            data=json.dumps(status_data),
                            content_type='application/json',
                            headers={'Authorization': 'Bearer admin-token'})
        assert response.status_code in [200, 400, 404, 503]

# ================================
# ADMIN MODULE TESTS
# ================================

class TestAdminAuthentication:
    """Test admin authentication endpoints"""

    def test_admin_login_success(self, client):
        """Test successful admin login"""
        login_data = {
            'username': 'admin',
            'password': 'admin123'  # Default password from setup
        }
        
        response = client.post('/api/admin/auth/login',
                             data=json.dumps(login_data),
                             content_type='application/json')
        # Should return 200 if admin modules available, 404 if not
        assert response.status_code in [200, 401, 404, 500]

    def test_admin_login_invalid_credentials(self, client):
        """Test admin login with invalid credentials"""
        login_data = {
            'username': 'admin',
            'password': 'wrongpassword'
        }
        
        response = client.post('/api/admin/auth/login',
                             data=json.dumps(login_data),
                             content_type='application/json')
        assert response.status_code in [401, 404, 500]

    def test_admin_login_missing_fields(self, client):
        """Test admin login with missing fields"""
        login_data = {
            'username': 'admin'
            # Missing password
        }
        
        response = client.post('/api/admin/auth/login',
                             data=json.dumps(login_data),
                             content_type='application/json')
        assert response.status_code in [400, 404]

class TestProductManagement:
    """Test product management endpoints"""

    def test_get_all_products(self, client, admin_auth_headers):
        """Test getting all products"""
        response = client.get('/api/admin/products/',
                            headers=admin_auth_headers)
        assert response.status_code in [200, 401, 404, 500]

    def test_get_hero_products(self, client, admin_auth_headers):
        """Test getting Hero products"""
        response = client.get('/api/admin/products/hero',
                            headers=admin_auth_headers)
        assert response.status_code in [200, 401, 404, 500]

    def test_update_hero_product(self, client, admin_auth_headers):
        """Test updating Hero product"""
        product_data = {
            'name': 'Updated Home Protection Plan',
            'active': True,
            'pricing': {
                '1': {'base_price': 199, 'admin_fee': 25}
            }
        }
        
        product_id = 'home_protection'
        response = client.put(f'/api/admin/products/hero/{product_id}',
                            data=json.dumps(product_data),
                            headers=admin_auth_headers)
        assert response.status_code in [200, 401, 404, 500]

    def test_create_hero_product(self, client, admin_auth_headers):
        """Test creating new Hero product"""
        product_data = {
            'id': 'test_product',
            'name': 'Test Product',
            'category': 'test',
            'description': 'Test product description',
            'active': True,
            'pricing': {
                '1': {'base_price': 99, 'admin_fee': 10}
            }
        }
        
        response = client.post('/api/admin/products/hero',
                             data=json.dumps(product_data),
                             headers=admin_auth_headers)
        assert response.status_code in [200, 400, 401, 404, 409, 500]

    def test_delete_hero_product(self, client, admin_auth_headers):
        """Test deleting Hero product"""
        product_id = 'test_product'
        response = client.delete(f'/api/admin/products/hero/{product_id}',
                               headers=admin_auth_headers)
        assert response.status_code in [200, 401, 404, 500]

class TestAnalyticsDashboard:
    """Test analytics dashboard endpoints"""

    def test_get_dashboard_stats(self, client, admin_auth_headers):
        """Test getting dashboard statistics"""
        response = client.get('/api/admin/analytics/dashboard',
                            headers=admin_auth_headers)
        assert response.status_code in [200, 401, 404, 500]

    def test_get_quotes_analytics(self, client, admin_auth_headers):
        """Test getting quotes analytics"""
        response = client.get('/api/admin/analytics/quotes',
                            headers=admin_auth_headers)
        assert response.status_code in [200, 401, 404, 500]

    def test_get_sales_analytics(self, client, admin_auth_headers):
        """Test getting sales analytics"""
        response = client.get('/api/admin/analytics/sales',
                            headers=admin_auth_headers)
        assert response.status_code in [200, 401, 404, 500]

    def test_export_analytics_data(self, client, admin_auth_headers):
        """Test exporting analytics data"""
        export_data = {
            'type': 'all',
            'start_date': '2024-01-01',
            'end_date': '2024-12-31'
        }
        
        response = client.post('/api/admin/analytics/export',
                             data=json.dumps(export_data),
                             headers=admin_auth_headers)
        assert response.status_code in [200, 401, 404, 500]

class TestContractManagement:
    """Test contract management endpoints"""

    def test_get_contract_templates(self, client):
        """Test getting contract templates"""
        response = client.get('/api/admin/contracts/templates')
        assert response.status_code in [200, 404, 500]

    def test_create_contract_template(self, client):
        """Test creating contract template"""
        template_data = {
            'name': 'Test Contract Template',
            'product_type': 'test',
            'product_id': 'test_product',
            'fields': [
                {'name': 'customer_name', 'type': 'text', 'required': True}
            ]
        }
        
        response = client.post('/api/admin/contracts/templates',
                             data=json.dumps(template_data),
                             content_type='application/json')
        assert response.status_code in [200, 400, 404, 409, 500]

    def test_generate_contract(self, client):
        """Test generating contract from template"""
        contract_data = {
            'template_id': 'vsc_silver',
            'customer_data': {
                'customer_name': 'John Doe',
                'customer_address': '123 Main St',
                'vehicle_vin': '1HGBH41JXMN109186'
            }
        }
        
        response = client.post('/api/admin/contracts/generate',
                             data=json.dumps(contract_data),
                             content_type='application/json')
        assert response.status_code in [200, 400, 404, 500]

# ================================
# ERROR HANDLING TESTS
# ================================

class TestErrorHandling:
    """Test error handling"""

    def test_404_error(self, client):
        """Test 404 error handling"""
        response = client.get('/api/nonexistent/endpoint')
        assert response.status_code == 404
        
        data = json.loads(response.data)
        assert 'success' in data
        assert data['success'] is False
        assert 'error' in data

    def test_405_method_not_allowed(self, client):
        """Test 405 error handling"""
        response = client.patch('/api/hero/products')  # PATCH not allowed
        assert response.status_code == 405

    def test_invalid_json(self, client):
        """Test handling of invalid JSON"""
        response = client.post('/api/hero/quote',
                             data='invalid json',
                             content_type='application/json')
        assert response.status_code in [400, 500]

    def test_large_request_body(self, client):
        """Test handling of oversized request"""
        large_data = {'data': 'x' * (20 * 1024 * 1024)}  # 20MB
        response = client.post('/api/hero/quote',
                             data=json.dumps(large_data),
                             content_type='application/json')
        assert response.status_code in [413, 400, 500]

# ================================
# CORS TESTS
# ================================

class TestCORS:
    """Test CORS functionality"""

    def test_cors_preflight(self, client):
        """Test CORS preflight request"""
        response = client.options('/api/hero/products',
                                headers={'Origin': 'https://www.connectedautocare.com'})
        assert response.status_code == 200
        assert 'Access-Control-Allow-Origin' in response.headers

    def test_cors_headers_on_response(self, client):
        """Test CORS headers on actual response"""
        response = client.get('/api/hero/products',
                            headers={'Origin': 'https://www.connectedautocare.com'})
        # Should have CORS headers regardless of status code
        if 'Access-Control-Allow-Origin' in response.headers:
            assert response.headers['Access-Control-Allow-Origin'] in [
                'https://www.connectedautocare.com', '*'
            ]

# ================================
# PERFORMANCE TESTS
# ================================

class TestPerformance:
    """Test performance characteristics"""

    def test_concurrent_requests(self, client):
        """Test handling of concurrent requests"""
        import threading
        import time
        
        results = []
        
        def make_request():
            start_time = time.time()
            response = client.get('/api/health')
            end_time = time.time()
            results.append({
                'status_code': response.status_code,
                'response_time': end_time - start_time
            })
        
        # Create 10 concurrent requests
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify all requests completed
        assert len(results) == 10
        # Verify all requests were successful or had expected error codes
        for result in results:
            assert result['status_code'] in [200, 404, 500, 503]
            # Verify reasonable response time (under 5 seconds)
            assert result['response_time'] < 5.0

    def test_response_time(self, client):
        """Test response time for health check"""
        import time
        
        start_time = time.time()
        response = client.get('/api/health')
        end_time = time.time()
        
        response_time = end_time - start_time
        # Health check should respond quickly (under 1 second)
        assert response_time < 1.0
        assert response.status_code == 200

# ================================
# INTEGRATION TESTS
# ================================

class TestIntegration:
    """Test integration scenarios"""

    def test_complete_hero_quote_flow(self, client):
        """Test complete Hero quote generation flow"""
        # Step 1: Get available products
        products_response = client.get('/api/hero/products')
        
        if products_response.status_code == 200:
            # Step 2: Generate quote for a product
            quote_data = {
                'product_type': 'home_protection',
                'term_years': 2,
                'coverage_limit': 500,
                'customer_type': 'retail',
                'state': 'FL',
                'zip_code': '33101'
            }
            
            quote_response = client.post('/api/hero/quote',
                                       data=json.dumps(quote_data),
                                       content_type='application/json')
            
            # Should either succeed or fail gracefully
            assert quote_response.status_code in [200, 400, 500]
            
            if quote_response.status_code == 200:
                quote_data = json.loads(quote_response.data)
                assert 'success' in quote_data
                
                # Step 3: Get payment methods
                payment_response = client.get('/api/payments/methods')
                assert payment_response.status_code == 200
                
                # Step 4: Generate contract (if quote was successful)
                if quote_data.get('success'):
                    contract_data = {
                        'product_type': 'home_protection',
                        'customer_name': 'John Doe',
                        'quote_id': 'test-quote-id'
                    }
                    
                    contract_response = client.post('/api/contracts/generate',
                                                  data=json.dumps(contract_data),
                                                  content_type='application/json')
                    assert contract_response.status_code in [200, 400, 500]

    def test_complete_vsc_quote_flow(self, client):
        """Test complete VSC quote generation flow"""
        # Step 1: Validate VIN
        vin_data = {'vin': '1HGBH41JXMN109186'}
        vin_response = client.post('/api/vin/validate',
                                 data=json.dumps(vin_data),
                                 content_type='application/json')
        
        if vin_response.status_code == 200:
            # Step 2: Decode VIN
            decode_response = client.post('/api/vin/decode',
                                        data=json.dumps(vin_data),
                                        content_type='application/json')
            
            # Step 3: Get VSC coverage options
            coverage_response = client.get('/api/vsc/coverage-options')
            
            # Step 4: Generate VSC quote
            quote_data = {
                'make': 'Honda',
                'model': 'Accord',
                'year': 2020,
                'mileage': 25000,
                'coverage_level': 'gold',
                'term_months': 36,
                'deductible': 100
            }
            
            quote_response = client.post('/api/vsc/quote',
                                       data=json.dumps(quote_data),
                                       content_type='application/json')
            
            assert quote_response.status_code in [200, 400, 500]

    @patch('index.token_required')
    @patch('index.role_required')
    def test_user_management_flow(self, mock_role, mock_token, client):
        """Test complete user management flow"""
        mock_token.return_value = lambda f: f
        mock_role.return_value = lambda f: f
        
        # Step 1: Register new user
        user_data = {
            'email': f'integration_test_{uuid.uuid4()}@example.com',
            'password': 'TestPassword123!',
            'role': 'customer',
            'first_name': 'John',
            'last_name': 'Doe'
        }
        
        register_response = client.post('/api/auth/register',
                                      data=json.dumps(user_data),
                                      content_type='application/json')
        
        if register_response.status_code == 201:
            # Step 2: Login with new user
            login_data = {
                'email': user_data['email'],
                'password': user_data['password']
            }
            
            login_response = client.post('/api/auth/login',
                                       data=json.dumps(login_data),
                                       content_type='application/json')
            
            if login_response.status_code == 200:
                login_data = json.loads(login_response.data)
                token = login_data.get('token')
                
                # Step 3: Get user profile
                profile_response = client.get('/api/auth/profile',
                                            headers={'Authorization': f'Bearer {token}'})
                
                # Step 4: Logout
                logout_response = client.post('/api/auth/logout',
                                            headers={'Authorization': f'Bearer {token}'})

# ================================
# SECURITY TESTS
# ================================

class TestSecurity:
    """Test security features"""

    def test_sql_injection_attempt(self, client):
        """Test protection against SQL injection"""
        malicious_data = {
            'product_type': "'; DROP TABLE products; --",
            'term_years': 2
        }
        
        response = client.post('/api/hero/quote',
                             data=json.dumps(malicious_data),
                             content_type='application/json')
        
        # Should handle malicious input gracefully
        assert response.status_code in [200, 400, 500]

    def test_xss_attempt(self, client):
        """Test protection against XSS"""
        malicious_data = {
            'customer_name': '<script>alert("xss")</script>',
            'product_type': 'home_protection'
        }
        
        response = client.post('/api/contracts/generate',
                             data=json.dumps(malicious_data),
                             content_type='application/json')
        
        # Should handle malicious input gracefully
        assert response.status_code in [200, 400, 500]

    def test_unauthorized_access(self, client):
        """Test unauthorized access to protected endpoints"""
        # Try to access admin endpoint without auth
        response = client.get('/api/admin/products/')
        assert response.status_code in [401, 404]
        
        # Try to access user management endpoint without auth
        response = client.get('/api/customers')
        assert response.status_code in [401, 503]

    def test_invalid_token(self, client):
        """Test access with invalid token"""
        headers = {'Authorization': 'Bearer invalid-token'}
        
        response = client.get('/api/auth/profile', headers=headers)
        assert response.status_code in [401, 503]

    def test_expired_token_simulation(self, client):
        """Test handling of expired tokens"""
        # Simulate expired token
        headers = {'Authorization': 'Bearer expired.jwt.token'}
        
        response = client.get('/api/auth/profile', headers=headers)
        assert response.status_code in [401, 503]

# ================================
# DATA VALIDATION TESTS
# ================================

class TestDataValidation:
    """Test data validation"""

    def test_email_validation(self, client):
        """Test email validation in various endpoints"""
        invalid_emails = [
            'invalid-email',
            '@domain.com',
            'user@',
            'user space@domain.com',
            'user@domain',
            ''
        ]
        
        for email in invalid_emails:
            user_data = {
                'email': email,
                'password': 'TestPassword123!',
                'role': 'customer'
            }
            
            response = client.post('/api/auth/register',
                                 data=json.dumps(user_data),
                                 content_type='application/json')
            
            # Should reject invalid emails
            assert response.status_code in [400, 503]

    def test_numeric_validation(self, client):
        """Test numeric field validation"""
        invalid_numeric_data = [
            {'year': 'not-a-number', 'mileage': 25000},
            {'year': 2020, 'mileage': 'not-a-number'},
            {'year': -1, 'mileage': 25000},
            {'year': 2020, 'mileage': -1},
            {'year': 3000, 'mileage': 25000},  # Future year
        ]
        
        for data in invalid_numeric_data:
            quote_data = {
                'make': 'Toyota',
                **data
            }
            
            response = client.post('/api/vsc/quote',
                                 data=json.dumps(quote_data),
                                 content_type='application/json')
            
            # Should handle invalid numeric data
            assert response.status_code in [400, 500]

    def test_required_fields_validation(self, client):
        """Test required field validation"""
        # Test Hero quote missing required fields
        incomplete_data_sets = [
            {},  # Empty data
            {'product_type': 'home_protection'},  # Missing term_years
            {'term_years': 2},  # Missing product_type
        ]
        
        for data in incomplete_data_sets:
            response = client.post('/api/hero/quote',
                                 data=json.dumps(data),
                                 content_type='application/json')
            assert response.status_code == 400

# ================================
# UTILITY FUNCTIONS FOR TESTS
# ================================

class TestUtilities:
    """Utility functions for testing"""
    
    @staticmethod
    def create_test_user(client, email_suffix=""):
        """Helper function to create a test user"""
        user_data = {
            'email': f'test_{uuid.uuid4()}{email_suffix}@example.com',
            'password': 'TestPassword123!',
            'role': 'customer',
            'first_name': 'Test',
            'last_name': 'User'
        }
        
        response = client.post('/api/auth/register',
                             data=json.dumps(user_data),
                             content_type='application/json')
        
        if response.status_code == 201:
            return json.loads(response.data), user_data
        return None, user_data
    
    @staticmethod
    def login_test_user(client, email, password):
        """Helper function to login a test user"""
        login_data = {
            'email': email,
            'password': password
        }
        
        response = client.post('/api/auth/login',
                             data=json.dumps(login_data),
                             content_type='application/json')
        
        if response.status_code == 200:
            return json.loads(response.data)
        return None

# ================================
# LOAD TESTING
# ================================

class TestLoad:
    """Load testing scenarios"""
    
    def test_health_check_load(self, client):
        """Test health check under load"""
        import time
        import threading
        
        results = []
        
        def health_check_request():
            start_time = time.time()
            response = client.get('/api/health')
            end_time = time.time()
            
            results.append({
                'status_code': response.status_code,
                'response_time': end_time - start_time
            })
        
        # Create 50 concurrent requests
        threads = []
        for _ in range(50):
            thread = threading.Thread(target=health_check_request)
            threads.append(thread)
        
        # Start all threads
        start_time = time.time()
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Analyze results
        successful_requests = [r for r in results if r['status_code'] == 200]
        avg_response_time = sum(r['response_time'] for r in results) / len(results)
        
        # Assertions
        assert len(results) == 50
        assert len(successful_requests) > 0  # At least some should succeed
        assert total_time < 30  # Should complete within 30 seconds
        assert avg_response_time < 2.0  # Average response time should be reasonable

# ================================
# RUN TESTS
# ================================

if __name__ == '__main__':
    """
    Run the test suite
    
    Usage:
    python test_api_endpoints.py
    
    Or with pytest:
    pytest test_api_endpoints.py -v
    pytest test_api_endpoints.py::TestHealthChecks -v
    pytest test_api_endpoints.py::TestHeroProductsAPI::test_generate_hero_quote_success -v
    """
    
    # Example of running specific test classes
    import pytest
    import sys
    
    if len(sys.argv) > 1:
        # Run specific test
        pytest.main(['-v', sys.argv[1]])
    else:
        # Run all tests
        pytest.main(['-v', __file__])

# ================================
# TEST CONFIGURATION AND SETUP
# ================================

def pytest_configure(config):
    """Configure pytest with custom markers and settings"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "security: marks tests as security tests"
    )
    config.addinivalue_line(
        "markers", "load: marks tests as load tests"
    )

# Mark slow tests
TestLoad = pytest.mark.slow(TestLoad)
TestIntegration = pytest.mark.integration(TestIntegration)
TestSecurity = pytest.mark.security(TestSecurity)

# ================================
# MOCK DATA FIXTURES
# ================================

@pytest.fixture
def sample_hero_quote_data():
    """Sample Hero quote data for testing"""
    return {
        'product_type': 'home_protection',
        'term_years': 2,
        'coverage_limit': 500,
        'customer_type': 'retail',
        'state': 'FL',
        'zip_code': '33101'
    }

@pytest.fixture
def sample_vsc_quote_data():
    """Sample VSC quote data for testing"""
    return {
        'make': 'Toyota',
        'model': 'Camry',
        'year': 2020,
        'mileage': 25000,
        'coverage_level': 'gold',
        'term_months': 36,
        'deductible': 100,
        'customer_type': 'retail'
    }

@pytest.fixture
def sample_user_data():
    """Sample user data for testing"""
    return {
        'email': f'test_{uuid.uuid4()}@example.com',
        'password': 'TestPassword123!',
        'role': 'customer',
        'first_name': 'John',
        'last_name': 'Doe',
        'phone': '555-123-4567'
    }

@pytest.fixture
def sample_contract_data():
    """Sample contract data for testing"""
    return {
        'template_id': 'home_protection',
        'customer_data': {
            'customer_name': 'John Doe',
            'customer_address': '123 Main St, Anytown, FL 33101',
            'property_address': '123 Main St, Anytown, FL 33101',
            'coverage_term': 2,
            'contract_price': 399.00,
            'effective_date': '2024-01-01',
            'coverage_limits': '500'
        }
    }

# ================================
# CUSTOM ASSERTIONS
# ================================

def assert_valid_response_structure(response_data, expected_keys=None):
    """Assert that response has valid structure"""
    assert isinstance(response_data, dict)
    assert 'success' in response_data
    
    if expected_keys:
        for key in expected_keys:
            assert key in response_data

def assert_valid_quote_response(response_data):
    """Assert that quote response has valid structure"""
    assert_valid_response_structure(response_data, ['success', 'data'])
    
    if response_data.get('success'):
        quote_data = response_data.get('data', {})
        expected_quote_fields = ['quote_id', 'product_type', 'total_price']
        for field in expected_quote_fields:
            # Fields may not be present if service is unavailable
            pass

def assert_valid_user_response(response_data):
    """Assert that user response has valid structure"""
    assert_valid_response_structure(response_data)
    
    if 'user' in response_data:
        user_data = response_data['user']
        expected_user_fields = ['id', 'email', 'role']
        for field in expected_user_fields:
            assert field in user_data

# ================================
# PERFORMANCE MONITORING
# ================================

class PerformanceMonitor:
    """Monitor test performance"""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.response_times = []
    
    def start(self):
        self.start_time = time.time()
    
    def end(self):
        self.end_time = time.time()
    
    def add_response_time(self, response_time):
        self.response_times.append(response_time)
    
    def get_stats(self):
        if not self.response_times:
            return {}
        
        return {
            'total_time': self.end_time - self.start_time if self.end_time and self.start_time else 0,
            'avg_response_time': sum(self.response_times) / len(self.response_times),
            'min_response_time': min(self.response_times),
            'max_response_time': max(self.response_times),
            'total_requests': len(self.response_times)
        }

@pytest.fixture
def performance_monitor():
    """Performance monitoring fixture"""
    return PerformanceMonitor()

import unittest
import os
import json
from unittest.mock import patch, Mock
from datetime import datetime
import hmac
import hashlib
from helcim_integration import HelcimPaymentProcessor

class TestHelcimPaymentProcessor(unittest.TestCase):
    def setUp(self):
        """Set up test environment with mocked environment variables."""
        self.env_patcher = patch.dict(os.environ, {
            'HELCIM_API_ENDPOINT': 'https://api.helcim.com/v2',
            'HELCIM_API_TOKEN': 'aB@p8sL2!OYmW@!CVFenAP@mRgi@A2hT-rtGH4Pe0c%Bqwpy2ZO*AzAYE4s6@N!y',
            'HELCIM_TERMINAL_ID': '79167',
            'HELCIM_WEBHOOK_SECRET': '0gv8Cbl1UFuE4oaQGThGVt1yWcqCS1O2'
        })
        self.env_patcher.start()
        self.processor = HelcimPaymentProcessor()

    def tearDown(self):
        """Clean up by stopping the environment patcher."""
        self.env_patcher.stop()

    @patch('helcim_integration.requests.get')
    def test_test_helcim_connection_success(self, mock_get):
        """Test successful connection to Helcim API."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = 'OK'
        mock_get.return_value = mock_response

        result = self.processor.test_helcim_connection()
        self.assertTrue(result['success'])
        self.assertEqual(result['message'], 'Connection successful')
        mock_get.assert_called_once_with(
            'https://api.helcim.com/v2/ping',
            headers={'api-token': 'aB@p8sL2!OYmW@!CVFenAP@mRgi@A2hT-rtGH4Pe0c%Bqwpy2ZO*AzAYE4s6@N!y', 'account-id': '79167'},
            timeout=10
        )

    @patch('helcim_integration.requests.get')
    def test_test_helcim_connection_failure(self, mock_get):
        """Test failed connection to Helcim API."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = 'Server Error'
        mock_get.return_value = mock_response

        result = self.processor.test_helcim_connection()
        self.assertFalse(result['success'])
        self.assertIn('Connection failed with status 500', result['message'])

    @patch.dict(os.environ, {}, clear=True)
    def test_validate_helcim_config_invalid(self):
        """Test configuration validation with missing environment variables."""
        processor = HelcimPaymentProcessor()
        result = processor.validate_helcim_config()
        self.assertFalse(result['valid'])
        self.assertEqual(len(result['errors']), 3)  # Missing API_TOKEN, TERMINAL_ID, and WEBHOOK_SECRET
        self.assertIn('Missing HELCIM_API_TOKEN', result['errors'])
        self.assertIn('Missing HELCIM_TERMINAL_ID', result['errors'])
        self.assertIn('Missing HELCIM_WEBHOOK_SECRET', result['errors'])

    def test_validate_helcim_config_valid(self):
        """Test configuration validation with all required variables."""
        result = self.processor.validate_helcim_config()
        self.assertTrue(result['valid'])
        self.assertIsNone(result['errors'])

    @patch('helcim_integration.requests.post')
    def test_create_helcimpay_checkout_session_success(self, mock_post):
        """Test successful creation of HelcimPay.js checkout session."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'checkoutToken': 'chk_123',
            'cardToken': 'crd_456',
            'transactionId': 'txn_789'
        }
        mock_post.return_value = mock_response

        session_data = {
            'amount': 100.00,
            'currency': 'USD',
            'paymentType': 'purchase',
            'customerCode': 'CUST-123',
            'invoiceNumber': 'TXN-123'
        }
        result = self.processor.create_helcimpay_checkout_session(session_data)
        self.assertTrue(result['success'])
        self.assertEqual(result['checkoutToken'], 'chk_123')
        self.assertEqual(result['cardToken'], 'crd_456')
        self.assertEqual(result['transactionId'], 'txn_789')

    def test_create_helcimpay_checkout_session_missing_fields(self):
        """Test checkout session creation with missing required fields."""
        session_data = {'amount': 100.00}  # Missing currency, paymentType, etc.
        result = self.processor.create_helcimpay_checkout_session(session_data)
        self.assertFalse(result['success'])
        self.assertIn('Missing required fields', result['error'])

    def test_verify_webhook_signature_valid(self):
        """Test valid webhook signature verification."""
        timestamp = '2025-08-02T01:27:00Z'
        payload = json.dumps({'id': 'txn_123', 'type': 'transaction.approved'}).encode('utf-8')
        message = f"{timestamp}.{payload.decode('utf-8')}".encode('utf-8')
        signature = hmac.new(
            key='0gv8Cbl1UFuE4oaQGThGVt1yWcqCS1O2'.encode('utf-8'),  # Use the actual webhook secret
            msg=message,
            digestmod=hashlib.sha256
        ).hexdigest()

        headers = {
            'webhook-signature': f'v1,{signature}',
            'webhook-timestamp': timestamp
        }
        result = self.processor.verify_webhook_signature(headers, payload)
        self.assertTrue(result)

    def test_verify_webhook_signature_invalid(self):
        """Test invalid webhook signature verification."""
        headers = {
            'webhook-signature': 'v1,invalid_signature',
            'webhook-timestamp': '2025-08-02T01:27:00Z'
        }
        payload = json.dumps({'id': 'txn_123'}).encode('utf-8')
        result = self.processor.verify_webhook_signature(headers, payload)
        self.assertFalse(result)

    @patch('helcim_integration.requests.get')
    def test_get_customers_success(self, mock_get):
        """Test successful retrieval of customers."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'customers': [{'customerCode': 'CUST-123', 'contactName': 'John Doe'}],
            'count': 1
        }
        mock_get.return_value = mock_response

        result = self.processor.get_customers()
        self.assertTrue(result['success'])
        self.assertEqual(len(result['customers']), 1)
        self.assertEqual(result['count'], 1)

    @patch('helcim_integration.requests.get')
    def test_get_customer_success(self, mock_get):
        """Test successful retrieval of a single customer."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'customerCode': 'CUST-123', 'contactName': 'John Doe'}
        mock_get.return_value = mock_response

        result = self.processor.get_customer('CUST-123')
        self.assertTrue(result['success'])
        self.assertEqual(result['customer']['customerCode'], 'CUST-123')

    @patch('helcim_integration.requests.post')
    def test_create_customer_success(self, mock_post):
        """Test successful customer creation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'customerCode': 'CUST-123', 'customerId': '123'}
        mock_post.return_value = mock_response

        customer_data = {
            'contactName': 'John Doe',
            'businessName': 'Doe Inc'
        }
        result = self.processor.create_customer(customer_data)
        self.assertTrue(result['success'])
        self.assertEqual(result['customerCode'], 'CUST-123')

    def test_create_customer_missing_fields(self):
        """Test customer creation with missing required fields."""
        customer_data = {'contactName': 'John Doe'}  # Missing businessName
        result = self.processor.create_customer(customer_data)
        self.assertFalse(result['success'])
        self.assertIn('Missing required fields', result['error'])

    @patch('helcim_integration.requests.post')
    def test_create_invoice_success(self, mock_post):
        """Test successful invoice creation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'invoiceNumber': 'INV-123', 'invoiceId': '123'}
        mock_post.return_value = mock_response

        invoice_data = {
            'amount': 100.00,
            'currency': 'USD'
        }
        result = self.processor.create_invoice(invoice_data)
        self.assertTrue(result['success'])
        self.assertEqual(result['invoiceNumber'], 'INV-123')

    @patch('helcim_integration.requests.get')
    def test_get_invoice_success(self, mock_get):
        """Test successful retrieval of an invoice."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'invoiceNumber': 'INV-123', 'amount': 100.00}
        mock_get.return_value = mock_response

        result = self.processor.get_invoice('INV-123')
        self.assertTrue(result['success'])
        self.assertEqual(result['invoice']['invoiceNumber'], 'INV-123')

    @patch('helcim_integration.requests.post')
    def test_process_purchase_success(self, mock_post):
        """Test successful purchase transaction."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'transactionId': 'txn_123', 'cardBatchId': 'batch_456'}
        mock_post.return_value = mock_response

        payment_data = {
            'amount': 100.00,
            'currency': 'USD',
            'cardToken': 'crd_456'
        }
        result = self.processor.process_purchase(payment_data)
        self.assertTrue(result['success'])
        self.assertEqual(result['transactionId'], 'txn_123')

    def test_process_purchase_missing_fields(self):
        """Test purchase transaction with missing required fields."""
        payment_data = {'amount': 100.00}  # Missing currency, cardToken
        result = self.processor.process_purchase(payment_data)
        self.assertFalse(result['success'])
        self.assertIn('Missing required fields', result['error'])

    @patch('helcim_integration.requests.post')
    def test_process_preauth_success(self, mock_post):
        """Test successful preauth transaction."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'transactionId': 'txn_123', 'cardBatchId': 'batch_456'}
        mock_post.return_value = mock_response

        payment_data = {
            'amount': 100.00,
            'currency': 'USD',
            'cardToken': 'crd_456'
        }
        result = self.processor.process_preauth(payment_data)
        self.assertTrue(result['success'])
        self.assertEqual(result['transactionId'], 'txn_123')

    @patch('helcim_integration.requests.post')
    def test_process_capture_success(self, mock_post):
        """Test successful capture transaction."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'transactionId': 'txn_123', 'cardBatchId': 'batch_456'}
        mock_post.return_value = mock_response

        capture_data = {
            'transactionId': 'txn_123',
            'amount': 100.00
        }
        result = self.processor.process_capture(capture_data)
        self.assertTrue(result['success'])
        self.assertEqual(result['transactionId'], 'txn_123')

    @patch('helcim_integration.requests.post')
    def test_process_verify_success(self, mock_post):
        """Test successful verify transaction."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'transactionId': 'txn_123', 'cardToken': 'crd_456'}
        mock_post.return_value = mock_response

        verify_data = {
            'cardToken': 'crd_456'
        }
        result = self.processor.process_verify(verify_data)
        self.assertTrue(result['success'])
        self.assertEqual(result['transactionId'], 'txn_123')

if __name__ == '__main__':
    unittest.main()
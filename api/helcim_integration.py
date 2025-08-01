import os
import requests
import hashlib
import hmac
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
import logging

class HelcimPaymentProcessor:
    """Complete Helcim payment processing implementation with idempotency support"""
    
    def __init__(self):
        # Helcim API Configuration
        self.api_token = os.environ.get('HELCIM_API_TOKEN')
        self.terminal_id = os.environ.get('HELCIM_TERMINAL_ID')
        self.base_url = "https://api.helcim.com/v2"
        self.webhook_secret = os.environ.get('HELCIM_WEBHOOK_SECRET')
        
        # Validate required configuration
        if not all([self.api_token, self.terminal_id]):
            raise ValueError("Missing required Helcim configuration: HELCIM_API_TOKEN, HELCIM_TERMINAL_ID")
    
    def _generate_idempotency_key(self) -> str:
        """Generate a unique idempotency key for Helcim API requests"""
        return str(uuid.uuid4())
    
    def process_credit_card_payment(self, payment_data: Dict[str, Any], idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Process credit card payment via Helcim API
        
        Args:
            payment_data: Dictionary containing payment information
            idempotency_key: Optional custom idempotency key (will generate if not provided)
            
        Returns:
            Dictionary with payment result
        """
        try:
            # Generate idempotency key if not provided
            if not idempotency_key:
                idempotency_key = self._generate_idempotency_key()
            
            # Extract and validate payment data
            amount = float(payment_data.get('amount', 0))
            card_info = payment_data.get('card_info', {})
            billing_info = payment_data.get('billing_info', {})
            transaction_number = payment_data.get('transaction_number')
            
            # Validate required fields
            required_fields = ['card_number', 'expiry_month', 'expiry_year', 'cvv']
            missing_fields = [field for field in required_fields if not card_info.get(field)]
            if missing_fields:
                return {
                    'success': False,
                    'error': f"Missing card fields: {', '.join(missing_fields)}"
                }
            
            # Prepare Helcim API request with idempotency key
            headers = {
                'Authorization': f'Bearer {self.api_token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'idempotency-key': idempotency_key  # REQUIRED for Helcim Payment API
            }
            
            # Format expiry date (MMYY format for Helcim)
            expiry_month = str(card_info['expiry_month']).zfill(2)
            expiry_year = str(card_info['expiry_year'])[-2:]  # Last 2 digits
            expiry = f"{expiry_month}{expiry_year}"
            
            # Build payment request payload
            payload = {
                'terminalId': self.terminal_id,
                'cardData': {
                    'cardNumber': card_info['card_number'].replace(' ', '').replace('-', ''),
                    'expiryDate': expiry,
                    'cvv': card_info['cvv']
                },
                'amount': round(amount * 100),  # Helcim expects amount in cents
                'currency': 'USD',  # or 'CAD' based on your needs
                'type': 'purchase',
                'customerCode': payment_data.get('customer_id', ''),
                'invoiceNumber': transaction_number,
                'description': payment_data.get('description', 'ConnectedAutoCare Payment'),
                'billingAddress': {
                    'name': f"{billing_info.get('first_name', '')} {billing_info.get('last_name', '')}".strip(),
                    'street1': billing_info.get('address_line1', ''),
                    'street2': billing_info.get('address_line2', ''),
                    'city': billing_info.get('city', ''),
                    'province': billing_info.get('state', ''),
                    'country': billing_info.get('country', 'CA'),
                    'postalCode': billing_info.get('postal_code', ''),
                    'phone': billing_info.get('phone', ''),
                    'email': billing_info.get('email', '')
                }
            }
            
            # Log idempotency key for debugging/tracking
            logging.info(f"Processing payment with idempotency key: {idempotency_key}")
            
            # Make API request to Helcim
            response = requests.post(
                f"{self.base_url}/card-transactions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            response_data = response.json()
            
            # Handle idempotency conflicts (409 status)
            if response.status_code == 409:
                return {
                    'success': False,
                    'error': 'Duplicate transaction detected with different payload',
                    'idempotency_conflict': True,
                    'idempotency_key': idempotency_key
                }
            
            if response.status_code == 200 and response_data.get('status') == 'APPROVED':
                # Successful payment
                result = self._format_success_response(response_data, amount)
                result['idempotency_key'] = idempotency_key
                return result
            else:
                # Failed payment
                result = self._format_error_response(response_data, response.status_code)
                result['idempotency_key'] = idempotency_key
                return result
                
        except requests.exceptions.RequestException as e:
            logging.error(f"Helcim API request failed: {str(e)}")
            return {
                'success': False,
                'error': 'Payment processor temporarily unavailable. Please try again.',
                'technical_error': str(e),
                'idempotency_key': idempotency_key
            }
        except Exception as e:
            logging.error(f"Helcim payment processing error: {str(e)}")
            return {
                'success': False,
                'error': 'Payment processing failed. Please check your information and try again.',
                'technical_error': str(e),
                'idempotency_key': idempotency_key
            }
    
    def process_refund(self, original_transaction_id: str, refund_amount: float, reason: str = "", idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Process refund via Helcim API
        
        Args:
            original_transaction_id: Helcim transaction ID to refund
            refund_amount: Amount to refund
            reason: Reason for refund
            idempotency_key: Optional custom idempotency key
            
        Returns:
            Dictionary with refund result
        """
        try:
            # Generate idempotency key if not provided
            if not idempotency_key:
                idempotency_key = self._generate_idempotency_key()
            
            headers = {
                'Authorization': f'Bearer {self.api_token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'idempotency-key': idempotency_key  # REQUIRED for Helcim Payment API
            }
            
            payload = {
                'terminalId': self.terminal_id,
                'originalTransactionId': original_transaction_id,
                'amount': round(refund_amount * 100),  # Amount in cents
                'type': 'refund',
                'description': f"Refund: {reason}" if reason else "Refund processed"
            }
            
            logging.info(f"Processing refund with idempotency key: {idempotency_key}")
            
            response = requests.post(
                f"{self.base_url}/card-transactions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            response_data = response.json()
            
            # Handle idempotency conflicts
            if response.status_code == 409:
                return {
                    'success': False,
                    'error': 'Duplicate refund request detected with different payload',
                    'idempotency_conflict': True,
                    'idempotency_key': idempotency_key
                }
            
            if response.status_code == 200 and response_data.get('status') == 'APPROVED':
                return {
                    'success': True,
                    'status': 'completed',
                    'refund_transaction_id': response_data.get('transactionId'),
                    'idempotency_key': idempotency_key,
                    'processor_data': {
                        'provider': 'Helcim',
                        'refund_id': response_data.get('transactionId'),
                        'original_transaction_id': original_transaction_id,
                        'amount_refunded': refund_amount,
                        'status': 'processed',
                        'processed_at': datetime.utcnow().isoformat(),
                        'estimated_completion': '3-5 business days'
                    }
                }
            else:
                return {
                    'success': False,
                    'error': response_data.get('responseMessage', 'Refund processing failed'),
                    'processor_data': response_data,
                    'idempotency_key': idempotency_key
                }
                
        except Exception as e:
            logging.error(f"Helcim refund error: {str(e)}")
            return {
                'success': False,
                'error': f'Refund processing failed: {str(e)}',
                'idempotency_key': idempotency_key
            }
    
    def retry_transaction_with_same_key(self, payment_data: Dict[str, Any], original_idempotency_key: str) -> Dict[str, Any]:
        """
        Retry a transaction with the same idempotency key (for network failures)
        
        Args:
            payment_data: Original payment data
            original_idempotency_key: The idempotency key from the original request
            
        Returns:
            Dictionary with payment result
        """
        logging.info(f"Retrying transaction with idempotency key: {original_idempotency_key}")
        return self.process_credit_card_payment(payment_data, original_idempotency_key)
    
    def _format_success_response(self, helcim_response: Dict[str, Any], amount: float) -> Dict[str, Any]:
        """Format successful Helcim response"""
        # Calculate processing fee (typical rate: 2.9% + $0.30)
        processing_fee = round(amount * 0.029 + 0.30, 2)
        
        return {
            'success': True,
            'status': 'completed',
            'processor_transaction_id': helcim_response.get('transactionId'),
            'processor_data': {
                'provider': 'Helcim',
                'transaction_id': helcim_response.get('transactionId'),
                'auth_code': helcim_response.get('authCode'),
                'response_code': helcim_response.get('responseCode'),
                'response_message': helcim_response.get('responseMessage'),
                'card_type': helcim_response.get('cardType'),
                'last_four': helcim_response.get('cardNumber', '')[-4:] if helcim_response.get('cardNumber') else '',
                'processed_at': datetime.utcnow().isoformat(),
                'amount_processed': amount,
                'currency': helcim_response.get('currency', 'USD')
            },
            'fees': {
                'processing_fee': processing_fee,
                'total_fees': processing_fee
            },
            'next_steps': [
                'Payment processed successfully',
                'Confirmation email sent',
                'Contract will be generated within 2-3 business days'
            ]
        }
    
    def _format_error_response(self, helcim_response: Dict[str, Any], status_code: int) -> Dict[str, Any]:
        """Format failed Helcim response"""
        error_message = "Payment processing failed"
        
        # Map common Helcim error codes to user-friendly messages
        response_code = helcim_response.get('responseCode', '')
        if response_code == '100':
            error_message = "Transaction declined by bank"
        elif response_code == '200':
            error_message = "Invalid card number"
        elif response_code == '201':
            error_message = "Card expired"
        elif response_code == '202':
            error_message = "Invalid CVV"
        elif response_code == '300':
            error_message = "Insufficient funds"
        elif helcim_response.get('responseMessage'):
            error_message = helcim_response['responseMessage']
        
        return {
            'success': False,
            'error': error_message,
            'processor_data': {
                'provider': 'Helcim',
                'response_code': response_code,
                'response_message': helcim_response.get('responseMessage', ''),
                'status_code': status_code,
                'transaction_id': helcim_response.get('transactionId'),
                'failed_at': datetime.utcnow().isoformat()
            }
        }
    
    def verify_webhook_signature(self, headers: Dict[str, str], payload: bytes) -> bool:
        """
        Verify Helcim webhook signature
        
        Args:
            headers: Request headers
            payload: Raw request payload
            
        Returns:
            True if signature is valid
        """
        if not self.webhook_secret:
            logging.warning("Helcim webhook secret not configured")
            return False
        
        signature = headers.get('X-Helcim-Signature', '')
        if not signature:
            return False
        
        # Calculate expected signature
        expected_signature = hmac.new(
            self.webhook_secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    
    def get_transaction_details(self, transaction_id: str) -> Dict[str, Any]:
        """
        Get transaction details from Helcim
        
        Args:
            transaction_id: Helcim transaction ID
            
        Returns:
            Transaction details
        """
        try:
            headers = {
                'Authorization': f'Bearer {self.api_token}',
                'Accept': 'application/json'
            }
            
            response = requests.get(
                f"{self.base_url}/card-transactions/{transaction_id}",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'transaction': response.json()
                }
            else:
                return {
                    'success': False,
                    'error': 'Transaction not found'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to retrieve transaction: {str(e)}'
            }


def validate_helcim_config():
    """Validate Helcim configuration"""
    required_vars = [
        'HELCIM_API_TOKEN',
        'HELCIM_TERMINAL_ID'
    ]
    
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        return {
            'valid': False,
            'missing_variables': missing_vars,
            'message': f"Missing required environment variables: {', '.join(missing_vars)}"
        }
    
    return {
        'valid': True,
        'message': 'Helcim configuration is valid'
    }


# Example usage demonstrating idempotency
if __name__ == "__main__":
    processor = HelcimPaymentProcessor()
    
    payment_data = {
        'amount': 100.00,
        'card_info': {
            'card_number': '4111111111111111',
            'expiry_month': '12',
            'expiry_year': '2025',
            'cvv': '123'
        },
        'billing_info': {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john@example.com'
        }
    }
    
    # First attempt
    result1 = processor.process_credit_card_payment(payment_data)
    print(f"First attempt result: {result1}")
    
    # If network failed, retry with same idempotency key
    if not result1['success'] and 'network' in str(result1.get('technical_error', '')).lower():
        result2 = processor.retry_transaction_with_same_key(
            payment_data, 
            result1['idempotency_key']
        )
        print(f"Retry attempt result: {result2}")
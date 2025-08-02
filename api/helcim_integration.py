import requests
import hmac
import hashlib
import json
import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PaymentType(Enum):
    """Enum for payment types."""
    PURCHASE = "purchase"
    PREAUTH = "preauth"
    CAPTURE = "capture"
    REFUND = "refund"
    REVERSE = "reverse"
    VERIFY = "verify"

class Currency(Enum):
    """Enum for supported currencies."""
    USD = "USD"
    CAD = "CAD"

class Country(Enum):
    """Enum for supported countries."""
    USA = "USA"  # United States
    CAN = "CAN"  # Canada

# Province/State mapping - Helcim Customer API expects CODES (AB, ON, CA), not full names
PROVINCE_NAME_TO_CODE_MAPPING = {
    # Canadian Provinces - Full Name to Code
    "Alberta": "AB",
    "British Columbia": "BC", 
    "Manitoba": "MB",
    "New Brunswick": "NB",
    "Newfoundland and Labrador": "NL",
    "Nova Scotia": "NS",
    "Ontario": "ON",
    "Prince Edward Island": "PE",
    "Quebec": "QC",
    "Saskatchewan": "SK",
    "Northwest Territories": "NT",
    "Nunavut": "NU",
    "Yukon": "YT",
    
    # US States - Full Name to Code  
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
    "Washington DC": "DC",
}

# Code to Name mapping (for reverse lookups)
PROVINCE_CODE_TO_NAME_MAPPING = {v: k for k, v in PROVINCE_NAME_TO_CODE_MAPPING.items()}

# Valid province codes that Helcim accepts
VALID_PROVINCE_CODES = set(PROVINCE_NAME_TO_CODE_MAPPING.values())

@dataclass
class Address:
    """Address data structure with province/state validation for Helcim."""
    street1: str = ""
    street2: str = ""
    city: str = ""
    province: str = ""  # Will be normalized to full name for Helcim
    postal_code: str = ""
    country: str = "USA"
    
    def __post_init__(self):
        """Validate and normalize province/state after initialization."""
        if self.province:
            self.province = self._normalize_province_for_helcim(self.province)
    
    @staticmethod
    def _normalize_province_for_helcim(province_input: str) -> str:
        """
        Normalize province/state input to CODE format required by Helcim Customer API.
        Helcim Customer API requires province CODES (AB, ON, CA), not full names.
        """
        if not province_input:
            return ""
            
        province_input = province_input.strip()
        
        # If it's already a valid code, return as-is
        province_upper = province_input.upper()
        if province_upper in VALID_PROVINCE_CODES:
            logger.info(f"Province code '{province_input}' is already valid for Helcim")
            return province_upper
        
        # If it's a full name, convert to code
        for full_name, code in PROVINCE_NAME_TO_CODE_MAPPING.items():
            if province_input.lower() == full_name.lower():
                logger.info(f"Converted province name '{province_input}' to code '{code}' for Helcim")
                return code
        
        # Handle common variations and abbreviations
        province_variations = {
            'british columbia': 'BC',
            'bc': 'BC',
            'ontario': 'ON', 
            'on': 'ON',
            'alberta': 'AB',
            'ab': 'AB',
            'california': 'CA',
            'ca': 'CA',
            'new york': 'NY',
            'ny': 'NY',
            'texas': 'TX',
            'tx': 'TX',
            'florida': 'FL',
            'fl': 'FL',
            'newfoundland': 'NL',
            'newfoundland and labrador': 'NL',
            'nl': 'NL',
            'pei': 'PE',
            'prince edward island': 'PE',
            'pe': 'PE',
            'northwest territories': 'NT',
            'nt': 'NT',
            'washington dc': 'DC',
            'district of columbia': 'DC',
            'dc': 'DC',
        }
        
        province_lower = province_input.lower()
        if province_lower in province_variations:
            code = province_variations[province_lower]
            logger.info(f"Converted province variation '{province_input}' to code '{code}' for Helcim")
            return code
        
        # If no match found, log warning and return original
        logger.warning(f"Could not normalize province/state for Helcim: '{province_input}'. Helcim Customer API requires valid province codes (AB, ON, CA, etc.).")
        return province_input

@dataclass
class CustomerInfo:
    """Customer information data structure."""
    contact_name: str
    business_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    billing_address: Optional[Address] = None
    shipping_address: Optional[Address] = None

class HelcimAPIError(Exception):
    """Custom exception for Helcim API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(self.message)

class HelcimPaymentProcessor:
    """Enhanced Helcim Payment Processor with proper province handling."""
    
    def __init__(self, api_token: Optional[str] = None, terminal_id: Optional[str] = None):
        """Initialize HelcimPaymentProcessor with configuration."""
        self.api_endpoint = "https://api.helcim.com/v2"
        self.api_token = api_token or os.getenv('HELCIM_API_TOKEN', 'aB@p8sL2!OYmW@!CVFenAP@mRgi@A2hT-rtGH4Pe0c%Bqwpy2ZO*AzAYE4s6@N!y')
        self.terminal_id = terminal_id or os.getenv('HELCIM_TERMINAL_ID', '79167') 
        self.webhook_secret = os.getenv('HELCIM_WEBHOOK_SECRET', '0gv8Cbl1UFuE4oaQGThGVt1yWcqCS1O2')
        self.timeout = 30
        
        # Validate configuration on initialization
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate configuration and raise exception if invalid."""
        if not self.api_token:
            raise ValueError("HELCIM_API_TOKEN is required")
        if not self.terminal_id:
            raise ValueError("HELCIM_TERMINAL_ID is required")
        
        logger.info("Helcim configuration validated successfully")

    def _get_headers(self) -> Dict[str, str]:
        """Get standard headers for API requests."""
        return {
            'api-token': self.api_token,
            'Content-Type': 'application/json'
        }

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                     params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make HTTP request to Helcim API with proper error handling."""
        url = f"{self.api_endpoint}{endpoint}"
        headers = self._get_headers()
        
        try:
            logger.info(f"Making {method} request to {endpoint}")
            if data:
                logger.debug(f"Request payload: {json.dumps(data, indent=2)}")
            
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=self.timeout)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=self.timeout)
            elif method.upper() == 'PUT':
                response = requests.put(url, headers=headers, json=data, timeout=self.timeout)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=self.timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # Log response details
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code >= 400:
                error_data = None
                try:
                    error_data = response.json()
                    logger.error(f"Error response: {json.dumps(error_data, indent=2)}")
                except ValueError:
                    logger.error(f"Error response text: {response.text}")
                
                error_msg = f"API request failed with status {response.status_code}"
                if error_data:
                    error_msg += f": {error_data}"
                else:
                    error_msg += f": {response.text}"
                
                raise HelcimAPIError(error_msg, response.status_code, error_data)

            return response.json() if response.content else {}

        except requests.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise HelcimAPIError(f"Request failed: {str(e)}")

    def test_connection(self) -> Dict[str, Any]:
        """Test connection to Helcim API."""
        try:
            # Use the general endpoint to test connectivity
            response = requests.get(
                f"{self.api_endpoint}/general",
                headers=self._get_headers(),
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                logger.info("Helcim API connection successful")
                return {'success': True, 'message': 'Connection successful'}
            else:
                return {
                    'success': False,
                    'message': f'Connection failed with status {response.status_code}'
                }
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return {'success': False, 'message': f'Connection error: {str(e)}'}

    def create_customer(self, customer_info: CustomerInfo) -> Dict[str, Any]:
        """Create a new customer with proper province name handling."""
        try:
            payload = {
                'contactName': customer_info.contact_name,
                'businessName': customer_info.business_name,
            }
            
            if customer_info.email:
                payload['email'] = customer_info.email
            if customer_info.phone:
                payload['phone'] = customer_info.phone
            
            if customer_info.billing_address:
                # Use the normalized province (full name)
                billing_addr = {
                    'name': customer_info.contact_name,
                    'street1': customer_info.billing_address.street1,
                    'city': customer_info.billing_address.city,
                    'province': customer_info.billing_address.province,  # Already normalized to full name
                    'postalCode': customer_info.billing_address.postal_code,
                    'country': customer_info.billing_address.country.upper()
                }
                
                if customer_info.billing_address.street2:
                    billing_addr['street2'] = customer_info.billing_address.street2
                    
                payload['billingAddress'] = billing_addr
                
                # Log the province being sent for debugging
                logger.info(f"Sending province code to Helcim: '{customer_info.billing_address.province}'")
            
            if customer_info.shipping_address:
                shipping_addr = {
                    'name': customer_info.contact_name,
                    'street1': customer_info.shipping_address.street1,
                    'city': customer_info.shipping_address.city,
                    'province': customer_info.shipping_address.province,  # Already normalized to full name
                    'postalCode': customer_info.shipping_address.postal_code,
                    'country': customer_info.shipping_address.country.upper()
                }
                
                if customer_info.shipping_address.street2:
                    shipping_addr['street2'] = customer_info.shipping_address.street2
                    
                payload['shippingAddress'] = shipping_addr

            response_data = self._make_request('POST', '/customers', data=payload)
            
            logger.info(f"Customer created successfully: {response_data.get('customerId')}")
            return {
                'success': True,
                'customer_id': response_data.get('customerId'),
                'customer_code': response_data.get('customerCode')
            }
        except HelcimAPIError as e:
            logger.error(f"Failed to create customer: {e.message}")
            return {'success': False, 'error': e.message}

    # Helper method to validate and convert province codes
    def validate_and_convert_province(self, province: str, country: str = "USA") -> Dict[str, Any]:
        """Validate and convert a province/state to the format required by Helcim."""
        try:
            # Create a temporary address to use the normalization logic
            temp_address = Address(province=province, country=country)
            normalized = temp_address.province
            
            # Check if it's a valid province/state code
            is_valid = normalized.upper() in VALID_PROVINCE_CODES
            
            return {
                'success': True,
                'original': province,
                'normalized': normalized,
                'is_valid': is_valid,
                'format': 'province_code'  # Helcim Customer API requires codes
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'original': province
            }

    # Invoice Management
    def create_invoice(self, amount: float, currency: Currency, 
                      customer_id: Optional[str] = None,
                      items: Optional[List[Dict]] = None,
                      description: Optional[str] = None) -> Dict[str, Any]:
        """Create a new invoice with validation."""
        try:
            if amount <= 0:
                raise ValueError("Amount must be greater than 0")
            
            payload = {
                'amount': amount,
                'currency': currency.value,
            }
            
            if customer_id:
                payload['customerId'] = customer_id
            if items:
                payload['lineItems'] = items
            if description:
                payload['description'] = description

            response_data = self._make_request('POST', '/invoices', data=payload)
            
            logger.info(f"Invoice created successfully: {response_data.get('invoiceId')}")
            return {
                'success': True,
                'invoice_id': response_data.get('invoiceId'),
                'invoice_number': response_data.get('invoiceNumber')
            }
        except (HelcimAPIError, ValueError) as e:
            logger.error(f"Failed to create invoice: {str(e)}")
            return {'success': False, 'error': str(e)}

    # HelcimPay.js Integration
    def create_helcimpay_checkout_session(self, amount: float, currency: Currency,
                                        customer_id: Optional[str] = None,
                                        invoice_id: Optional[str] = None,
                                        payment_type: str = 'purchase') -> Dict[str, Any]:
        """Create a HelcimPay.js checkout session."""
        try:
            if amount <= 0:
                raise ValueError("Amount must be greater than 0")
            
            payload = {
                'amount': amount,
                'currency': currency.value,
                'paymentType': payment_type
            }
            
            if customer_id:
                payload['customerId'] = customer_id
            if invoice_id:
                payload['invoiceId'] = invoice_id

            response_data = self._make_request('POST', '/helcim-pay/initialize', data=payload)
            
            logger.info(f"Checkout session created: {response_data.get('checkoutToken')}")
            return {
                'success': True,
                'checkout_token': response_data.get('checkoutToken'),
                'transaction_id': response_data.get('transactionId')
            }
        except (HelcimAPIError, ValueError) as e:
            logger.error(f"Checkout session creation failed: {str(e)}")
            return {'success': False, 'error': str(e)}

    # Utility Methods
    def create_complete_checkout_flow(self, amount: float, currency: Currency,
                                    customer_info: CustomerInfo,
                                    description: Optional[str] = None) -> Dict[str, Any]:
        """Complete checkout flow: create customer, invoice, and checkout session."""
        try:
            # Step 1: Create customer
            customer_result = self.create_customer(customer_info)
            if not customer_result['success']:
                return customer_result

            customer_id = customer_result['customer_id']

            # Step 2: Create invoice
            invoice_result = self.create_invoice(
                amount=amount,
                currency=currency,
                customer_id=customer_id,
                description=description
            )
            if not invoice_result['success']:
                return invoice_result

            invoice_id = invoice_result['invoice_id']

            # Step 3: Create checkout session
            checkout_result = self.create_helcimpay_checkout_session(
                amount=amount,
                currency=currency,
                customer_id=customer_id,
                invoice_id=invoice_id
            )

            if checkout_result['success']:
                return {
                    'success': True,
                    'customer_id': customer_id,
                    'invoice_id': invoice_id,
                    'checkout_token': checkout_result['checkout_token'],
                    'transaction_id': checkout_result['transaction_id']
                }
            else:
                return checkout_result

        except Exception as e:
            logger.error(f"Complete checkout flow failed: {str(e)}")
            return {'success': False, 'error': str(e)}


# Test the province conversion
if __name__ == "__main__":
    # Test province normalization
    test_cases = [
        ("ON", "Canada"),
        ("Ontario", "Canada"), 
        ("CA", "USA"),
        ("California", "USA"),
        ("BC", "Canada"),
        ("british columbia", "Canada"),
        ("NY", "USA"),
        ("New York", "USA"),
        ("Invalid", "USA")
    ]
    
    processor = HelcimPaymentProcessor()
    
    print("Testing province normalization for Helcim:")
    print("=" * 50)
    
    for province, country in test_cases:
        result = processor.validate_and_convert_province(province, country)
        print(f"Input: '{province}' ({country})")
        print(f"Result: {result}")
        print("-" * 30)
    
    # Test with actual address creation
    print("\nTesting with Address creation:")
    print("=" * 50)
    
    test_address = Address(
        street1="123 Main St",
        city="Toronto", 
        province="Ontario",  # Should be converted to "ON"
        postal_code="M5V 3A8",
        country="CAN"
    )
    
    print(f"Created address with province: '{test_address.province}' (should be 'ON')")
    
    # Test customer creation
    customer_info = CustomerInfo(
        contact_name="John Doe",
        business_name="Test Corp",
        email="john@test.com",
        billing_address=test_address
    )
    
    print(f"Customer billing address province: '{customer_info.billing_address.province}' (should be 'ON')")
    
    # Show mapping examples
    print("\nProvince Mapping Examples:")
    print("=" * 50)
    examples = [
        "Ontario -> ON", 
        "California -> CA",
        "British Columbia -> BC",
        "New York -> NY",
        "Alberta -> AB"
    ]
    for example in examples:
        print(f"✓ {example}")
        
    print(f"\nTotal valid province codes: {len(VALID_PROVINCE_CODES)}")
    print(f"Sample valid codes: {list(VALID_PROVINCE_CODES)[:10]}...")
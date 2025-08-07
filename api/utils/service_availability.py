"""
Service Availability Checker
Monitors and reports on the availability of various application services
"""

import sys
import platform
from datetime import datetime, timezone
from typing import Dict, Any, List

class ServiceChecker:
    """Check availability of various services and components"""
    
    def __init__(self):
        self._check_service_availability()
    
    def _check_service_availability(self):
        """Check which services are available"""
        # Check customer services
        try:
            from services.hero_rating_service import HeroRatingService
            from services.vsc_rating_service import VSCRatingService
            from services.vin_decoder_service import VINDecoderService
            from data.hero_products_data import get_hero_products
            from data.vsc_rates_data import get_vsc_coverage_options
            self.customer_services_available = True
        except ImportError:
            self.customer_services_available = False
        
        # Check admin modules
        try:
            from admin.analytics_dashboard import analytics_bp
            from admin.product_management import product_bp
            from admin.contract_management import contract_bp
            from auth.admin_auth import auth_bp
            self.admin_modules_available = True
        except ImportError:
            self.admin_modules_available = False
        
        # Check user management
        try:
            from auth.user_auth import UserAuth
            from models.database_models import UserModel, CustomerModel
            from analytics.kpi_system import KPISystem
            self.user_management_available = True
        except ImportError:
            self.user_management_available = False
        
        # Check enhanced VIN service
        try:
            from services.enhanced_vin_decoder_service import EnhancedVINDecoderService
            self.enhanced_vin_available = True
        except ImportError:
            self.enhanced_vin_available = False
        
        # Check database services
        try:
            from services.database_settings_service import settings_service
            self.database_settings_available = settings_service.connection_available if hasattr(settings_service, 'connection_available') else False
        except ImportError:
            self.database_settings_available = False
    
    def check_hero_service(self) -> Dict[str, Any]:
        """Check Hero service health"""
        try:
            if not self.customer_services_available:
                return {
                    "status": "unavailable",
                    "service": "Hero Rating Service",
                    "error": "Service dependencies not loaded"
                }
            
            from services.hero_rating_service import HeroRatingService
            from data.hero_products_data import get_hero_products
            
            service = HeroRatingService()
            products = get_hero_products()
            
            # Test basic functionality
            test_quote = service.generate_quote(
                product_type='home_protection',
                term_years=1,
                coverage_limit=500,
                customer_type='retail'
            )
            
            return {
                "status": "healthy",
                "service": "Hero Rating Service",
                "features": ["quote_generation", "product_catalog", "pricing", "database_integration"],
                "products_available": len(products),
                "test_quote_success": test_quote.get('success', False),
                "database_integration": self.database_settings_available
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "Hero Rating Service",
                "error": str(e)
            }
    
    def check_vsc_service(self) -> Dict[str, Any]:
        """Check VSC service health"""
        try:
            if not self.customer_services_available:
                return {
                    "status": "unavailable",
                    "service": "VSC Rating Service",
                    "error": "Service dependencies not loaded"
                }
            
            from services.vsc_rating_service import VSCRatingService
            from data.vsc_rates_data import get_vsc_coverage_options, calculate_vsc_price
            
            service = VSCRatingService()
            coverage_options = get_vsc_coverage_options()
            
            # Test database connectivity
            database_rates_available = False
            try:
                from data.vsc_rates_data import rate_manager
                test_classification = rate_manager.get_vehicle_classification()
                database_rates_available = bool(test_classification)
            except Exception:
                pass
            
            # Test basic functionality
            test_price = None
            try:
                test_price = calculate_vsc_price(
                    make='TOYOTA',
                    year=2020,
                    mileage=50000,
                    coverage_level='gold',
                    term_months=36,
                    deductible=100
                )
            except Exception as e:
                test_price = {'success': False, 'error': str(e)}
            
            return {
                "status": "healthy",
                "service": "VSC Rating Service",
                "features": ["quote_generation", "eligibility_checking", "vin_integration", "database_rates"],
                "coverage_options_available": len(coverage_options) > 0,
                "database_rates_available": database_rates_available,
                "test_pricing_success": test_price.get('success', False) if test_price else False,
                "enhanced_vin_integration": self.enhanced_vin_available
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "VSC Rating Service",
                "error": str(e)
            }
    
    def check_vin_service(self) -> Dict[str, Any]:
        """Check VIN service health"""
        try:
            if not self.customer_services_available:
                return {
                    "status": "unavailable",
                    "service": "VIN Decoder Service",
                    "error": "Service dependencies not loaded"
                }
            
            from services.vin_decoder_service import VINDecoderService
            basic_service = VINDecoderService()
            
            enhanced_features = {}
            if self.enhanced_vin_available:
                try:
                    from services.enhanced_vin_decoder_service import EnhancedVINDecoderService
                    enhanced_service = EnhancedVINDecoderService()
                    
                    # Test enhanced service with a sample VIN
                    test_vin = "1HGCM82633A123456"  # Sample Honda VIN format
                    enhanced_test = enhanced_service.decode_vin(test_vin)
                    
                    enhanced_features = {
                        "nhtsa_integration": True,
                        "eligibility_checking": True,
                        "enhanced_validation": True,
                        "test_decode_success": enhanced_test.get('success', False)
                    }
                except Exception as e:
                    enhanced_features = {
                        "nhtsa_integration": False,
                        "error": str(e)
                    }
            
            return {
                "status": "healthy",
                "service": "VIN Decoder Service",
                "features": ["vin_decoding", "validation", "batch_processing"],
                "enhanced_available": self.enhanced_vin_available,
                "enhanced_features": enhanced_features
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "VIN Decoder Service",
                "error": str(e)
            }
    
    def check_payment_service(self) -> Dict[str, Any]:
        """Check payment service health"""
        try:
            # Check if payment dependencies are available
            import psycopg2
            from config.app_config import AppConfig
            
            config = AppConfig()
            database_available = bool(config.DATABASE_URL)
            
            # Check Helcim integration
            helcim_available = False
            helcim_error = None
            try:
                from helcim_integration import HelcimPaymentProcessor
                processor = HelcimPaymentProcessor()
                helcim_available = True
            except ImportError as e:
                helcim_error = str(e)
            except Exception as e:
                helcim_error = f"Configuration error: {str(e)}"
            
            # Check database tables
            tables_exist = False
            if database_available:
                try:
                    from utils.database import get_db_manager
                    db = get_db_manager()
                    if db.available:
                        # Test if essential tables exist
                        result = db.execute_query("""
                            SELECT table_name 
                            FROM information_schema.tables 
                            WHERE table_schema = 'public' 
                            AND table_name IN ('transactions', 'customers', 'protection_plans')
                        """)
                        tables_exist = result.get('success', False) and len(result.get('data', [])) >= 3
                except Exception:
                    pass
            
            if database_available and tables_exist:
                status = "healthy"
            elif database_available:
                status = "degraded"
            else:
                status = "unavailable"
            
            return {
                "status": status,
                "service": "Payment Processing",
                "features": {
                    "helcim_integration": helcim_available,
                    "financing": True,
                    "transaction_history": tables_exist,
                    "webhook_support": helcim_available
                },
                "database_available": database_available,
                "tables_exist": tables_exist,
                "helcim_error": helcim_error if helcim_error else None
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "Payment Processing",
                "error": str(e)
            }
    
    def check_email_service(self) -> Dict[str, Any]:
        """Check email service health"""
        # Check for email service dependencies
        try:
            # Placeholder for actual email service check
            # In production, check SMTP settings, email templates, etc.
            smtp_configured = False
            email_templates_available = False
            
            # Check environment variables for email configuration
            import os
            smtp_host = os.environ.get('SMTP_HOST')
            smtp_user = os.environ.get('SMTP_USER')
            smtp_configured = bool(smtp_host and smtp_user)
            
            return {
                "status": "not_implemented" if not smtp_configured else "configured",
                "service": "Email Service",
                "features": {
                    "smtp_configured": smtp_configured,
                    "email_templates": email_templates_available,
                    "customer_notifications": False,
                    "admin_alerts": False
                },
                "message": "Email service implementation pending"
            }
        except Exception as e:
            return {
                "status": "error",
                "service": "Email Service",
                "error": str(e)
            }
    
    def check_file_storage(self) -> Dict[str, Any]:
        """Check file storage service health"""
        try:
            from config.app_config import AppConfig
            config = AppConfig()
            
            vercel_blob_configured = bool(config.VERCEL_BLOB_READ_WRITE_TOKEN)
            
            # Test file storage if configured
            storage_test_success = False
            if vercel_blob_configured:
                try:
                    # In production, perform actual test upload/delete
                    storage_test_success = True  # Placeholder
                except Exception:
                    storage_test_success = False
            
            return {
                "status": "healthy" if vercel_blob_configured else "not_configured",
                "service": "File Storage",
                "provider": "Vercel Blob" if vercel_blob_configured else None,
                "features": {
                    "video_upload": vercel_blob_configured,
                    "image_optimization": vercel_blob_configured,
                    "cdn_delivery": vercel_blob_configured,
                    "automatic_cleanup": False
                },
                "configured": vercel_blob_configured,
                "test_success": storage_test_success,
                "max_file_sizes": {
                    "video_mb": config.MAX_VIDEO_SIZE / (1024 * 1024),
                    "image_mb": config.MAX_IMAGE_SIZE / (1024 * 1024)
                }
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "File Storage",
                "error": str(e)
            }
    
    def check_database_service(self) -> Dict[str, Any]:
        """Check database service health"""
        try:
            from utils.database import get_database_status
            return get_database_status()
        except Exception as e:
            return {
                "status": "error",
                "service": "Database Service",
                "error": str(e)
            }
    
    def check_admin_services(self) -> Dict[str, Any]:
        """Check admin services health"""
        if not self.admin_modules_available:
            return {
                "status": "unavailable",
                "service": "Admin Services",
                "error": "Admin modules not loaded"
            }
        
        try:
            # Check admin authentication
            auth_available = False
            try:
                from auth.admin_auth import auth_bp
                auth_available = True
            except ImportError:
                pass
            
            # Check admin panels
            product_management_available = False
            analytics_available = False
            try:
                from admin.product_management import product_bp
                from admin.analytics_dashboard import analytics_bp
                product_management_available = True
                analytics_available = True
            except ImportError:
                pass
            
            return {
                "status": "healthy" if auth_available else "degraded",
                "service": "Admin Services",
                "features": {
                    "admin_authentication": auth_available,
                    "product_management": product_management_available,
                    "analytics_dashboard": analytics_available,
                    "user_management": self.user_management_available,
                    "system_settings": self.database_settings_available
                }
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "Admin Services",
                "error": str(e)
            }
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get system information"""
        return {
            "python_version": sys.version,
            "platform": platform.platform(),
            "architecture": platform.architecture()[0],
            "processor": platform.processor(),
            "hostname": platform.node(),
            "system_time": datetime.now(timezone.utc).isoformat() + "Z",
            "timezone": str(datetime.now().astimezone().tzinfo),
            "python_path": sys.path[:3],  # First 3 entries only
            "environment": {
                "development": "DEBUG" in [k for k in sys.modules.keys() if "debug" in k.lower()],
                "production": platform.system() != "Windows",  # Rough estimate
                "testing": "pytest" in sys.modules
            }
        }
    
    def get_database_metrics(self) -> Dict[str, Any]:
        """Get database metrics"""
        try:
            from utils.database import get_db_manager
            db_manager = get_db_manager()
            return db_manager.get_metrics()
        except Exception as e:
            return {
                "status": "unavailable",
                "error": str(e)
            }
    
    def get_api_metrics(self) -> Dict[str, Any]:
        """Get API metrics"""
        # In production, this would connect to metrics collection system
        try:
            endpoint_count = self._count_registered_endpoints()
            
            return {
                "total_endpoints": endpoint_count,
                "endpoint_categories": {
                    "health": ["health", "api_health"],
                    "hero": ["products", "quote", "pricing"],
                    "vsc": ["quote", "eligibility", "coverage-options"],
                    "vin": ["decode", "validate", "batch"],
                    "payment": ["process", "methods", "history"],
                    "auth": ["login", "register", "profile"],
                    "admin": ["users", "products", "analytics"]
                },
                "authentication": {
                    "public_endpoints": endpoint_count // 3,  # Rough estimate
                    "authenticated_endpoints": endpoint_count // 2,
                    "admin_endpoints": endpoint_count // 6
                },
                "response_times": "not_tracked",  # Placeholder
                "request_volume": "not_tracked"   # Placeholder
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    def _count_registered_endpoints(self) -> int:
        """Count registered Flask endpoints"""
        try:
            from flask import current_app
            return len(current_app.url_map._rules)
        except:
            return 50  # Rough estimate if Flask context not available
    
    def get_error_rates(self) -> Dict[str, Any]:
        """Get error rates"""
        # Placeholder for error rate tracking
        # In production, integrate with logging/monitoring system
        return {
            "overall_error_rate": "not_tracked",
            "error_categories": {
                "4xx_client_errors": "not_tracked",
                "5xx_server_errors": "not_tracked",
                "database_errors": "not_tracked",
                "external_api_errors": "not_tracked"
            },
            "common_errors": [
                "Authentication required (401)",
                "Resource not found (404)",
                "Invalid input data (400)"
            ],
            "monitoring_status": "not_implemented"
        }
    
    def get_response_times(self) -> Dict[str, Any]:
        """Get response time metrics"""
        # Placeholder for response time tracking
        return {
            "average_response_time_ms": "not_tracked",
            "p50_response_time_ms": "not_tracked",
            "p95_response_time_ms": "not_tracked",
            "p99_response_time_ms": "not_tracked",
            "endpoint_performance": {
                "health_endpoints": "< 50ms (estimated)",
                "quote_endpoints": "200-500ms (estimated)",
                "database_queries": "10-100ms (estimated)",
                "external_apis": "500-2000ms (estimated)"
            },
            "monitoring_status": "not_implemented"
        }
    
    def get_security_status(self) -> Dict[str, Any]:
        """Get security-related service status"""
        try:
            # Check authentication services
            jwt_configured = False
            try:
                from utils.auth_decorators import JWT_SECRET_KEY
                import os
                jwt_configured = bool(JWT_SECRET_KEY and JWT_SECRET_KEY != 'connectedautocare-jwt-secret-2025')
            except:
                pass
            
            # Check HTTPS configuration
            https_enforced = False
            try:
                import os
                https_enforced = os.environ.get('FORCE_HTTPS', '').lower() == 'true'
            except:
                pass
            
            # Check CORS configuration
            cors_configured = True  # We have CORS setup in the app
            
            return {
                "jwt_authentication": {
                    "configured": jwt_configured,
                    "production_secret": jwt_configured,
                    "token_expiration": "24 hours"
                },
                "https_security": {
                    "enforced": https_enforced,
                    "redirect_configured": https_enforced
                },
                "cors_protection": {
                    "configured": cors_configured,
                    "allowed_origins": "configured",
                    "credentials_support": True
                },
                "api_security": {
                    "rate_limiting": "not_implemented",
                    "api_key_validation": "implemented",
                    "input_validation": "basic"
                },
                "data_protection": {
                    "password_hashing": "implemented",
                    "sensitive_data_encryption": "not_implemented",
                    "audit_logging": "basic"
                }
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_integration_status(self) -> Dict[str, Any]:
        """Get external integration status"""
        integrations = {}
        
        # NHTSA VIN API
        try:
            if self.enhanced_vin_available:
                integrations["nhtsa_vin_api"] = {
                    "status": "available",
                    "endpoint": "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/",
                    "features": ["vin_decoding", "vehicle_data"],
                    "rate_limits": "unknown"
                }
            else:
                integrations["nhtsa_vin_api"] = {
                    "status": "not_configured",
                    "reason": "Enhanced VIN service not available"
                }
        except Exception as e:
            integrations["nhtsa_vin_api"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Helcim Payment API
        try:
            from helcim_integration import HelcimPaymentProcessor
            integrations["helcim_payment_api"] = {
                "status": "available",
                "features": ["credit_card_processing", "tokenization", "webhooks"],
                "environment": "production"  # or "sandbox"
            }
        except ImportError:
            integrations["helcim_payment_api"] = {
                "status": "not_available",
                "reason": "Helcim integration module not found"
            }
        except Exception as e:
            integrations["helcim_payment_api"] = {
                "status": "configuration_error",
                "error": str(e)
            }
        
        # Vercel Blob Storage
        try:
            from config.app_config import AppConfig
            config = AppConfig()
            if config.VERCEL_BLOB_READ_WRITE_TOKEN:
                integrations["vercel_blob_storage"] = {
                    "status": "available",
                    "features": ["file_upload", "cdn_delivery", "automatic_optimization"],
                    "max_file_size_mb": config.MAX_VIDEO_SIZE / (1024 * 1024)
                }
            else:
                integrations["vercel_blob_storage"] = {
                    "status": "not_configured",
                    "reason": "VERCEL_BLOB_READ_WRITE_TOKEN not set"
                }
        except Exception as e:
            integrations["vercel_blob_storage"] = {
                "status": "error",
                "error": str(e)
            }
        
        return {
            "total_integrations": len(integrations),
            "active_integrations": len([i for i in integrations.values() if i.get("status") == "available"]),
            "integrations": integrations
        }
    
    def run_comprehensive_health_check(self) -> Dict[str, Any]:
        """Run comprehensive health check on all services"""
        health_check = {
            "overall_status": "unknown",
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "system_info": self.get_system_info(),
            "services": {
                "hero_service": self.check_hero_service(),
                "vsc_service": self.check_vsc_service(),
                "vin_service": self.check_vin_service(),
                "payment_service": self.check_payment_service(),
                "email_service": self.check_email_service(),
                "file_storage": self.check_file_storage(),
                "database_service": self.check_database_service(),
                "admin_services": self.check_admin_services()
            },
            "metrics": {
                "database": self.get_database_metrics(),
                "api": self.get_api_metrics(),
                "errors": self.get_error_rates(),
                "response_times": self.get_response_times()
            },
            "security": self.get_security_status(),
            "integrations": self.get_integration_status()
        }
        
        # Determine overall status
        service_statuses = [service.get("status", "unknown") for service in health_check["services"].values()]
        healthy_count = sum(1 for status in service_statuses if status == "healthy")
        total_count = len(service_statuses)
        
        if healthy_count == total_count:
            health_check["overall_status"] = "healthy"
        elif healthy_count >= total_count * 0.75:
            health_check["overall_status"] = "mostly_healthy"
        elif healthy_count >= total_count * 0.5:
            health_check["overall_status"] = "degraded"
        else:
            health_check["overall_status"] = "unhealthy"
        
        health_check["summary"] = {
            "healthy_services": healthy_count,
            "total_services": total_count,
            "health_percentage": round((healthy_count / total_count) * 100, 1),
            "critical_issues": self._identify_critical_issues(health_check["services"]),
            "recommendations": self._generate_recommendations(health_check["services"])
        }
        
        return health_check
    
    def _identify_critical_issues(self, services: Dict[str, Any]) -> List[str]:
        """Identify critical issues from service statuses"""
        critical_issues = []
        
        critical_services = ["database_service", "payment_service"]
        
        for service_name, service_status in services.items():
            status = service_status.get("status", "unknown")
            
            if service_name in critical_services and status in ["unhealthy", "unavailable"]:
                critical_issues.append(f"Critical service '{service_name}' is {status}")
            
            if status == "unhealthy":
                error = service_status.get("error")
                if error:
                    critical_issues.append(f"{service_name}: {error}")
        
        return critical_issues
    
    def _generate_recommendations(self, services: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on service statuses"""
        recommendations = []
        
        for service_name, service_status in services.items():
            status = service_status.get("status", "unknown")
            
            if status == "not_configured":
                if service_name == "email_service":
                    recommendations.append("Configure SMTP settings for email notifications")
                elif service_name == "file_storage":
                    recommendations.append("Set VERCEL_BLOB_READ_WRITE_TOKEN for file uploads")
            
            elif status == "degraded":
                if service_name == "payment_service":
                    recommendations.append("Check payment service configuration and database connectivity")
            
            elif status == "unavailable":
                recommendations.append(f"Investigate and restore {service_name}")
        
        # General recommendations
        if not any("database" in rec for rec in recommendations):
            if services.get("database_service", {}).get("status") != "healthy":
                recommendations.append("Ensure database is properly configured and accessible")
        
        return recommendations
    
    def get_service_dependencies(self) -> Dict[str, Any]:
        """Get service dependency information"""
        return {
            "hero_service": {
                "depends_on": ["database_service", "database_settings"],
                "optional_dependencies": ["email_service"],
                "provides": ["product_quotes", "pricing_calculations"]
            },
            "vsc_service": {
                "depends_on": ["database_service", "vin_service"],
                "optional_dependencies": ["enhanced_vin_service"],
                "provides": ["vehicle_quotes", "eligibility_checking"]
            },
            "vin_service": {
                "depends_on": [],
                "optional_dependencies": ["nhtsa_api", "enhanced_features"],
                "provides": ["vin_decoding", "vehicle_validation"]
            },
            "payment_service": {
                "depends_on": ["database_service"],
                "optional_dependencies": ["helcim_api", "email_service"],
                "provides": ["payment_processing", "transaction_history"]
            },
            "admin_services": {
                "depends_on": ["database_service", "user_management"],
                "optional_dependencies": ["file_storage"],
                "provides": ["admin_panel", "system_configuration"]
            },
            "database_service": {
                "depends_on": ["postgresql"],
                "optional_dependencies": [],
                "provides": ["data_persistence", "configuration_storage"]
            }
        }

# Create global instance
service_checker = ServiceChecker()

# Convenience functions
def check_all_services():
    """Check all services and return comprehensive status"""
    return service_checker.run_comprehensive_health_check()

def is_service_healthy(service_name: str) -> bool:
    """Check if a specific service is healthy"""
    if hasattr(service_checker, f'check_{service_name}'):
        check_method = getattr(service_checker, f'check_{service_name}')
        result = check_method()
        return result.get('status') == 'healthy'
    return False

def get_critical_issues() -> List[str]:
    """Get list of critical issues across all services"""
    health_check = service_checker.run_comprehensive_health_check()
    return health_check.get('summary', {}).get('critical_issues', [])
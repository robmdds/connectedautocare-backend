"""
Application Configuration Management
Centralized configuration for the ConnectedAutoCare platform
"""

import os
from flask import request, make_response
from datetime import datetime, timezone

class AppConfig:
    """Centralized application configuration"""
    
    def __init__(self):
        # Database configuration
        self.DATABASE_URL = os.environ.get('DATABASE_URL')
        
        # Vercel Blob Storage
        self.VERCEL_BLOB_READ_WRITE_TOKEN = os.environ.get('BLOB_READ_WRITE_TOKEN')
        print(f"Vercel Blob Read/Write Token: {self.VERCEL_BLOB_READ_WRITE_TOKEN}")
        
        # File upload settings
        self.ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'webm', 'mov', 'avi'}
        self.ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
        self.MAX_VIDEO_SIZE = 100 * 1024 * 1024  # 100MB
        self.MAX_IMAGE_SIZE = 10 * 1024 * 1024   # 10MB
        
        # CORS configuration
        self.ALLOWED_ORIGINS = [
            "https://www.connectedautocare.com",
            "https://connectedautocare.com",
            "https://api.connectedautocare.com",
            "https://admin.connectedautocare.com",
            "https://portal.connectedautocare.com",
            "http://localhost:5173",  # Local development
            "http://127.0.0.1:5173",  # Local development
        ]
        
        # Flask configuration
        self.SECRET_KEY = os.environ.get(
            'SECRET_KEY', 'connectedautocare-unified-secret-2025')
    
    def get_flask_config(self):
        """Get Flask configuration dictionary"""
        return {
            'SECRET_KEY': self.SECRET_KEY,
            'DEBUG': False,
            'TESTING': False,
            'MAX_CONTENT_LENGTH': 16 * 1024 * 1024  # 16MB max file size
        }
    
    def handle_cors_response(self, response):
        """Handle CORS headers for responses"""
        origin = request.headers.get('Origin')

        if origin in self.ALLOWED_ORIGINS:
            response.headers['Access-Control-Allow-Origin'] = origin
        elif origin is None:
            response.headers['Access-Control-Allow-Origin'] = '*'

        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,X-Requested-With'
        response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age'] = '3600'

        return response
    
    def handle_preflight_request(self):
        """Handle CORS preflight requests"""
        if request.method == "OPTIONS":
            response = make_response()
            origin = request.headers.get('Origin')

            if origin in self.ALLOWED_ORIGINS:
                response.headers['Access-Control-Allow-Origin'] = origin
            else:
                response.headers['Access-Control-Allow-Origin'] = '*'

            response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,X-Requested-With'
            response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Max-Age'] = '3600'

            return response
        return None
    
    def allowed_file(self, filename, file_type='video'):
        """Check if file type is allowed"""
        if not filename or '.' not in filename:
            return False

        extension = filename.rsplit('.', 1)[1].lower()

        if file_type == 'video':
            return extension in self.ALLOWED_VIDEO_EXTENSIONS
        elif file_type == 'image':
            return extension in self.ALLOWED_IMAGE_EXTENSIONS
        return False

    def validate_file_size(self, file, file_type):
        """Validate file size"""
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)

        max_size = self.MAX_VIDEO_SIZE if file_type == 'video' else self.MAX_IMAGE_SIZE

        if file_size > max_size:
            max_mb = max_size / (1024 * 1024)
            return False, f"File too large. Maximum size: {max_mb}MB"

        return True, "File size OK"
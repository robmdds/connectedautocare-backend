"""
Public Video Endpoints
Read-only endpoints for public access to video content
"""
from flask import Blueprint, jsonify
from datetime import datetime, timezone
import json

# Import utilities with proper error handling
try:
    from utils.database import execute_query
    DATABASE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Database utilities not available: {e}")
    DATABASE_AVAILABLE = False

# Initialize public video blueprint
video_public_bp = Blueprint('video_public', __name__)

# ================================
# PUBLIC VIDEO ENDPOINTS
# ================================

@video_public_bp.route('/landing/video', methods=['GET'])
def get_current_landing_video():
    """Get current landing page video for public display"""
    try:
        if not DATABASE_AVAILABLE:
            # Return default values if database not available
            video_info = {
                'video_url': '',
                'thumbnail_url': '',
                'title': 'ConnectedAutoCare Hero Protection',
                'description': 'Comprehensive protection plans',
                'duration': '2:30',
                'updated_at': datetime.now(timezone.utc).isoformat() + 'Z'
            }
            return jsonify(video_info)
            
        # Query to get video settings from database
        get_video_query = '''
            SELECT key, value
            FROM admin_settings
            WHERE category = 'video'
            ORDER BY key;
        '''
        
        video_results = execute_query(get_video_query)
        
        # Debug: Print what we're getting from the database
        print(f"Database query returned: {video_results}")
        print(f"Type: {type(video_results)}")
        
        # Handle different response formats from execute_query
        actual_rows = []
        if isinstance(video_results, dict):
            # If it's a dict with success/data/rowcount structure
            if 'data' in video_results and video_results.get('success'):
                actual_rows = video_results['data']
                print(f"Extracted {len(actual_rows)} rows from data field")
            else:
                print("Warning: Query result dict doesn't have expected structure")
                actual_rows = []
        elif isinstance(video_results, list):
            # If it's already a list of rows
            actual_rows = video_results
        else:
            print(f"Warning: Unexpected query result type: {type(video_results)}")
            actual_rows = []

        # Debug: Print the actual rows
        for i, row in enumerate(actual_rows):
            print(f"Actual Row {i}: {row} (length: {len(row) if hasattr(row, '__len__') else 'unknown'})")

        video_settings = {}
        for row in actual_rows:
            # Handle RealDictRow objects (from psycopg2)
            if hasattr(row, 'get'):
                # It's a dict-like object (RealDictRow)
                key = row.get('key') or row.get(0)
                value = row.get('value') or row.get(1)
            elif hasattr(row, '__len__') and len(row) >= 2:
                # It's a regular tuple/list
                key = row[0]
                value = row[1]
            else:
                print(f"Warning: Unexpected row structure: {row}")
                continue
            
            if key:
                # Parse JSON values properly
                if value is not None:
                    try:
                        # Try to parse as JSON first (if it's a string)
                        if isinstance(value, str):
                            parsed_value = json.loads(value)
                        else:
                            parsed_value = value
                        video_settings[key] = parsed_value
                    except (json.JSONDecodeError, TypeError):
                        # If not valid JSON, use as is
                        video_settings[key] = value
                else:
                    video_settings[key] = ''

        # Build response with defaults
        video_info = {
            'video_url': video_settings.get('landing_page_url', ''),
            'thumbnail_url': video_settings.get('landing_page_thumbnail', ''),
            'title': video_settings.get('landing_page_title', 'ConnectedAutoCare Hero Protection'),
            'description': video_settings.get('landing_page_description', 'Comprehensive protection plans'),
            'duration': video_settings.get('landing_page_duration', '2:30'),
            'updated_at': video_settings.get('last_updated', datetime.now(timezone.utc).isoformat() + 'Z')
        }

        print(f"Returning video info: {video_info}")
        return jsonify(video_info)

    except Exception as e:
        import traceback
        print(f"Error getting landing video: {str(e)}")
        print(f"Full traceback: {traceback.format_exc()}")
        
        # Return default values on error
        video_info = {
            'video_url': '',
            'thumbnail_url': '',
            'title': 'ConnectedAutoCare Hero Protection',
            'description': 'Comprehensive protection plans',
            'duration': '2:30',
            'updated_at': datetime.now(timezone.utc).isoformat() + 'Z'
        }
        return jsonify(video_info)

@video_public_bp.route('/health', methods=['GET'])
def public_video_health():
    """Health check for public video endpoints"""
    return jsonify({
        'status': 'healthy',
        'service': 'Public Video API',
        'database_available': DATABASE_AVAILABLE,
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
    })

# ================================
# ERROR HANDLERS
# ================================

@video_public_bp.errorhandler(404)
def not_found(error):
    """Handle 404 errors for video endpoints"""
    return jsonify({
        'error': 'Video endpoint not found',
        'status_code': 404,
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
    }), 404

@video_public_bp.errorhandler(500)
def internal_server_error(error):
    """Handle internal server errors for video endpoints"""
    return jsonify({
        'error': 'Internal server error in video service',
        'status_code': 500,
        'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'
    }), 500
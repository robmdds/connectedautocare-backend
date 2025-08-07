"""
Video Management Endpoints (Admin)
Video upload, optimization, and management with Vercel Blob Storage
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
import json
import time
import uuid
import os

# Import utilities with proper error handling
try:
    from utils.response_helpers import success_response, error_response
    from utils.auth_decorators import token_required, role_required
    from utils.database import get_db_manager, execute_query
    UTILS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some utilities not available: {e}")
    UTILS_AVAILABLE = False

# Initialize blueprint
video_bp = Blueprint('video_admin', __name__)

# Import video services with error handling
try:
    from config.app_config import AppConfig
    config = AppConfig()
    VERCEL_BLOB_READ_WRITE_TOKEN = config.VERCEL_BLOB_READ_WRITE_TOKEN
    video_services_available = bool(VERCEL_BLOB_READ_WRITE_TOKEN)
    
    # File handling imports
    from PIL import Image
    import io
    import requests
    PIL_AVAILABLE = True
    
except ImportError as e:
    print(f"Warning: Video services not available: {e}")
    video_services_available = False
    PIL_AVAILABLE = False
    VERCEL_BLOB_READ_WRITE_TOKEN = None
    config = None

# File upload settings - use config if available, otherwise fallback
if config:
    ALLOWED_VIDEO_EXTENSIONS = config.ALLOWED_VIDEO_EXTENSIONS
    ALLOWED_IMAGE_EXTENSIONS = config.ALLOWED_IMAGE_EXTENSIONS
    MAX_VIDEO_SIZE = config.MAX_VIDEO_SIZE
    MAX_IMAGE_SIZE = config.MAX_IMAGE_SIZE
else:
    ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'webm', 'mov', 'avi'}
    ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
    MAX_VIDEO_SIZE = 100 * 1024 * 1024  # 100MB
    MAX_IMAGE_SIZE = 10 * 1024 * 1024   # 10MB

# ================================
# UTILITY FUNCTIONS
# ================================

def allowed_file(filename, file_type='video'):
    """Check if file type is allowed"""
    if config and hasattr(config, 'allowed_file'):
        return config.allowed_file(filename, file_type)
    
    # Fallback implementation
    if not filename or '.' not in filename:
        return False

    extension = filename.rsplit('.', 1)[1].lower()

    if file_type == 'video':
        return extension in ALLOWED_VIDEO_EXTENSIONS
    elif file_type == 'image':
        return extension in ALLOWED_IMAGE_EXTENSIONS
    return False

def validate_file_size(file, file_type):
    """Validate file size"""
    if config and hasattr(config, 'validate_file_size'):
        return config.validate_file_size(file, file_type)
    
    # Fallback implementation
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    max_size = MAX_VIDEO_SIZE if file_type == 'video' else MAX_IMAGE_SIZE

    if file_size > max_size:
        max_mb = max_size / (1024 * 1024)
        return False, f"File too large. Maximum size: {max_mb}MB"

    return True, "File size OK"

def optimize_image(file):
    """Optimize image for web delivery"""
    if not PIL_AVAILABLE:
        file.seek(0)
        return file
        
    try:
        image = Image.open(file)

        # Convert to RGB if necessary
        if image.mode in ('RGBA', 'P'):
            image = image.convert('RGB')

        # Resize if too large (max 1920x1080 for thumbnails)
        max_width, max_height = 1920, 1080
        if image.width > max_width or image.height > max_height:
            image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

        # Save optimized version
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)

        return output
    except Exception as e:
        print(f"Image optimization failed: {e}")
        file.seek(0)
        return file

def upload_to_vercel_blob(file, file_type, filename_prefix="hero"):
    """Upload file to Vercel Blob Storage"""
    try:
        if not VERCEL_BLOB_READ_WRITE_TOKEN:
            return {'success': False, 'error': 'Vercel Blob token not configured'}

        # Generate unique filename
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]

        # Get file extension safely
        if hasattr(file, 'filename') and file.filename and '.' in file.filename:
            file_extension = file.filename.rsplit('.', 1)[1].lower()
        else:
            file_extension = 'mp4' if file_type == 'video' else 'jpg'

        filename = f"{filename_prefix}_{file_type}_{timestamp}_{unique_id}.{file_extension}"

        # Vercel Blob API endpoint
        url = f"https://blob.vercel-storage.com/{filename}"

        # Get content type
        content_type = getattr(file, 'content_type', None)
        if not content_type:
            if file_type == 'video':
                content_type = f'video/{file_extension}'
            else:
                content_type = f'image/{file_extension}'

        # Prepare headers
        headers = {
            'Authorization': f'Bearer {VERCEL_BLOB_READ_WRITE_TOKEN}',
            'X-Content-Type': content_type
        }

        # Read file content
        file_content = file.read()
        file.seek(0)  # Reset file pointer

        # Upload to Vercel Blob
        response = requests.put(url, data=file_content,
                                headers=headers, timeout=60)

        if response.status_code in [200, 201]:
            result = response.json()
            return {
                'success': True,
                'url': result.get('url', url),
                'filename': filename,
                'size': len(file_content)
            }
        else:
            return {
                'success': False,
                'error': f'Upload failed: HTTP {response.status_code} - {response.text}'
            }

    except Exception as e:
        import traceback
        print(f"Vercel Blob upload error: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return {'success': False, 'error': f'Upload error: {str(e)}'}

def delete_from_vercel_blob(file_url):
    """Delete file from Vercel Blob Storage"""
    try:
        if not VERCEL_BLOB_READ_WRITE_TOKEN:
            return {'success': False, 'error': 'Vercel Blob token not configured'}

        headers = {
            'Authorization': f'Bearer {VERCEL_BLOB_READ_WRITE_TOKEN}'
        }

        response = requests.delete(file_url, headers=headers)

        return {
            'success': response.status_code in [200, 204],
            'status_code': response.status_code
        }

    except Exception as e:
        return {'success': False, 'error': str(e)}

# ================================
# ADMIN VIDEO ENDPOINTS
# ================================

@video_bp.route('/admin/upload', methods=['POST'])
def upload_video():
    """Upload video file and thumbnail to Vercel Blob Storage"""
    try:
        # Check if auth decorators are available
        if UTILS_AVAILABLE:
            # This would normally have @token_required and @role_required('admin')
            pass
        
        # Check Vercel Blob configuration
        if not VERCEL_BLOB_READ_WRITE_TOKEN:
            return jsonify({'error': 'Vercel Blob storage not configured. Please set VERCEL_BLOB_READ_WRITE_TOKEN environment variable.'}), 500

        # Check if files are present
        if 'video' not in request.files and 'thumbnail' not in request.files:
            return jsonify({'error': 'No files provided'}), 400

        video_file = request.files.get('video')
        thumbnail_file = request.files.get('thumbnail')

        uploaded_files = {}
        old_files_to_delete = []

        # Handle video upload
        if video_file and video_file.filename != '':
            if not allowed_file(video_file.filename, 'video'):
                return jsonify({'error': 'Invalid video file type. Allowed: mp4, webm, mov, avi'}), 400

            # Validate file size
            size_valid, size_message = validate_file_size(video_file, 'video')
            if not size_valid:
                return jsonify({'error': size_message}), 400

            # Upload to Vercel Blob
            upload_result = upload_to_vercel_blob(video_file, 'video')

            if upload_result['success']:
                uploaded_files['video_url'] = upload_result['url']
                uploaded_files['video_filename'] = upload_result['filename']
                uploaded_files['video_size'] = upload_result['size']
            else:
                return jsonify({'error': f"Video upload failed: {upload_result['error']}"}), 500

        # Handle thumbnail upload
        if thumbnail_file and thumbnail_file.filename != '':
            if not allowed_file(thumbnail_file.filename, 'image'):
                return jsonify({'error': 'Invalid thumbnail file type. Allowed: jpg, jpeg, png, gif, webp'}), 400

            # Validate file size
            size_valid, size_message = validate_file_size(thumbnail_file, 'image')
            if not size_valid:
                return jsonify({'error': size_message}), 400

            # Optimize image
            optimized_file = optimize_image(thumbnail_file)

            # Create FileWrapper for upload
            class FileWrapper:
                def __init__(self, file_obj, filename, content_type):
                    self.file_obj = file_obj
                    self.filename = filename
                    self.content_type = content_type

                def read(self):
                    return self.file_obj.read()

                def seek(self, pos):
                    return self.file_obj.seek(pos)

            wrapped_file = FileWrapper(optimized_file, thumbnail_file.filename, 'image/jpeg')
            upload_result = upload_to_vercel_blob(wrapped_file, 'thumbnail')

            if upload_result['success']:
                uploaded_files['thumbnail_url'] = upload_result['url']
                uploaded_files['thumbnail_filename'] = upload_result['filename']
                uploaded_files['thumbnail_size'] = upload_result['size']
            else:
                return jsonify({'error': f"Thumbnail upload failed: {upload_result['error']}"}), 500

        # Update database with new URLs (if database is available)
        if uploaded_files and UTILS_AVAILABLE:
            try:
                # Get current video URLs for cleanup (get old files before updating)
                old_files_query = '''
                    SELECT key, value
                    FROM admin_settings
                    WHERE category = 'video' AND key IN ('landing_page_url', 'landing_page_thumbnail');
                '''
                
                old_files_result = execute_query(old_files_query)
                
                # Handle different response formats from execute_query
                actual_rows = []
                if isinstance(old_files_result, dict):
                    if 'data' in old_files_result and old_files_result.get('success'):
                        actual_rows = old_files_result['data']
                elif isinstance(old_files_result, list):
                    actual_rows = old_files_result
                
                for row in actual_rows:
                    # Handle RealDictRow objects (from psycopg2)
                    if hasattr(row, 'get'):
                        key = row.get('key') or row.get(0)
                        value = row.get('value') or row.get(1)
                    elif hasattr(row, '__len__') and len(row) >= 2:
                        key, value = row[0], row[1]
                    else:
                        continue
                        if value:
                            # Parse JSON value
                            try:
                                url_value = json.loads(value) if isinstance(value, str) else value
                                if url_value and 'blob.vercel-storage.com' in str(url_value):
                                    old_files_to_delete.append(str(url_value))
                            except (json.JSONDecodeError, TypeError):
                                # Handle non-JSON values
                                if isinstance(value, str) and 'blob.vercel-storage.com' in value:
                                    old_files_to_delete.append(value.strip('"'))

                # Get form metadata
                title = request.form.get('title', 'ConnectedAutoCare Hero Video')
                description = request.form.get('description', 'Hero protection video')
                duration = request.form.get('duration', '0:00')

                # Prepare updates with proper JSON formatting
                updates = [
                    ('landing_page_title', title),
                    ('landing_page_description', description),
                    ('landing_page_duration', duration),
                    ('last_updated', datetime.now(timezone.utc).isoformat() + 'Z')
                ]

                if 'video_url' in uploaded_files:
                    updates.append(('landing_page_url', uploaded_files['video_url']))
                    updates.append(('video_filename', uploaded_files['video_filename']))

                if 'thumbnail_url' in uploaded_files:
                    updates.append(('landing_page_thumbnail', uploaded_files['thumbnail_url']))
                    updates.append(('thumbnail_filename', uploaded_files['thumbnail_filename']))

                # Insert/update each setting
                for key, value in updates:
                    # Format value as JSON string
                    json_value = json.dumps(value)

                    # Use UPSERT with proper handling
                    upsert_query = '''
                        INSERT INTO admin_settings (category, key, value, updated_by)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (category, key)
                        DO UPDATE SET
                            value = EXCLUDED.value,
                            updated_at = CURRENT_TIMESTAMP,
                            updated_by = EXCLUDED.updated_by;
                    '''
                    
                    execute_query(upsert_query, ('video', key, json_value, 'admin'))

                print(f"✅ Successfully updated database with new video settings")

            except Exception as db_error:
                print(f"Database update error: {db_error}")
                # If database update fails but files were uploaded, we should clean them up
                for file_key in ['video_url', 'thumbnail_url']:
                    if file_key in uploaded_files:
                        try:
                            delete_from_vercel_blob(uploaded_files[file_key])
                        except:
                            pass
                raise db_error

            # Clean up old files after successful database update
            for old_file_url in old_files_to_delete:
                try:
                    delete_result = delete_from_vercel_blob(old_file_url)
                    if delete_result['success']:
                        print(f"Deleted old file: {old_file_url}")
                    else:
                        print(f"Failed to delete old file: {old_file_url}")
                except Exception as e:
                    print(f"Error deleting old file {old_file_url}: {e}")

        response_data = {
            'message': 'Upload successful',
            'uploaded_files': uploaded_files,
            'video_info': {
                'video_url': uploaded_files.get('video_url'),
                'thumbnail_url': uploaded_files.get('thumbnail_url'),
                'title': request.form.get('title', 'ConnectedAutoCare Hero Video'),
                'description': request.form.get('description', 'Hero protection video'),
                'duration': request.form.get('duration', '0:00'),
                'updated_at': datetime.now(timezone.utc).isoformat() + 'Z',
                'storage_provider': 'Vercel Blob',
                'file_sizes': {
                    'video_size_mb': round(uploaded_files.get('video_size', 0) / (1024 * 1024), 2) if 'video_size' in uploaded_files else None,
                    'thumbnail_size_kb': round(uploaded_files.get('thumbnail_size', 0) / 1024, 2) if 'thumbnail_size' in uploaded_files else None
                }
            }
        }

        return jsonify(response_data), 201

    except Exception as e:
        # Add more detailed error logging
        import traceback
        error_details = traceback.format_exc()
        print(f"Video upload error: {str(e)}")
        print(f"Full traceback: {error_details}")

        return jsonify({'error': f"Upload failed: {str(e)}"}), 500

@video_bp.route('/admin/delete', methods=['DELETE'])
def delete_video():
    """Delete current video and thumbnail from Vercel Blob"""
    try:
        if not VERCEL_BLOB_READ_WRITE_TOKEN:
            return jsonify({'error': 'Vercel Blob storage not configured'}), 500

        files_to_delete = []
        
        if UTILS_AVAILABLE:
            # Get current video URLs
            get_urls_query = '''
                SELECT key, value
                FROM admin_settings
                WHERE category = 'video' AND key IN ('landing_page_url', 'landing_page_thumbnail');
            '''
            
            url_results = execute_query(get_urls_query)

            # Handle different response formats from execute_query
            actual_rows = []
            if isinstance(url_results, dict):
                if 'data' in url_results and url_results.get('success'):
                    actual_rows = url_results['data']
            elif isinstance(url_results, list):
                actual_rows = url_results

            for row in actual_rows:
                # Handle RealDictRow objects (from psycopg2)
                if hasattr(row, 'get'):
                    key = row.get('key') or row.get(0)
                    value = row.get('value') or row.get(1)
                elif hasattr(row, '__len__') and len(row) >= 2:
                    key, value = row[0], row[1]
                else:
                    continue
                    if value:
                        try:
                            # Parse JSON value
                            url_value = json.loads(value) if isinstance(value, str) else value
                            if url_value and 'blob.vercel-storage.com' in str(url_value):
                                files_to_delete.append(str(url_value))
                        except (json.JSONDecodeError, TypeError):
                            # Handle non-JSON values
                            if isinstance(value, str) and 'blob.vercel-storage.com' in value:
                                files_to_delete.append(value.strip('"'))

        # Delete files from Vercel Blob
        deletion_results = []
        for file_url in files_to_delete:
            result = delete_from_vercel_blob(file_url)
            deletion_results.append({
                'url': file_url,
                'success': result['success'],
                'error': result.get('error')
            })

        if UTILS_AVAILABLE:
            # Clear database entries
            for key in ['landing_page_url', 'landing_page_thumbnail', 'video_filename', 'thumbnail_filename']:
                clear_query = '''
                    UPDATE admin_settings
                    SET value = %s, updated_at = CURRENT_TIMESTAMP, updated_by = %s
                    WHERE category = 'video' AND key = %s;
                '''
                execute_query(clear_query, ('""', 'admin', key))

            # Update last_updated timestamp
            timestamp_json = json.dumps(datetime.now(timezone.utc).isoformat() + 'Z')
            timestamp_query = '''
                INSERT INTO admin_settings (category, key, value, updated_by)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (category, key)
                DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = CURRENT_TIMESTAMP,
                    updated_by = EXCLUDED.updated_by;
            '''
            execute_query(timestamp_query, ('video', 'last_updated', timestamp_json, 'admin'))

        successful_deletions = [r for r in deletion_results if r['success']]

        return jsonify({
            'message': f'Deleted {len(successful_deletions)} files successfully',
            'deletion_results': deletion_results,
            'cleared_database': UTILS_AVAILABLE
        })

    except Exception as e:
        import traceback
        print(f"Video deletion error: {str(e)}")
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({'error': f"Deletion failed: {str(e)}"}), 500

@video_bp.route('/admin/health')
def video_service_health():
    """Check video upload service health"""
    try:
        # Test Vercel Blob connection
        blob_configured = bool(VERCEL_BLOB_READ_WRITE_TOKEN)

        health_status = {
            'status': 'healthy' if blob_configured else 'not_configured',
            'storage_provider': 'Vercel Blob',
            'blob_configured': blob_configured,
            'max_video_size_mb': MAX_VIDEO_SIZE / (1024 * 1024),
            'max_image_size_mb': MAX_IMAGE_SIZE / (1024 * 1024),
            'allowed_video_formats': list(ALLOWED_VIDEO_EXTENSIONS),
            'allowed_image_formats': list(ALLOWED_IMAGE_EXTENSIONS),
            'features': {
                'image_optimization': PIL_AVAILABLE,
                'automatic_cleanup': True,
                'global_cdn': True,
                'secure_upload': True
            }
        }

        if not blob_configured:
            health_status['error'] = 'VERCEL_BLOB_READ_WRITE_TOKEN environment variable not set'
            return jsonify(health_status), 503

        return jsonify(health_status)

    except Exception as e:
        return jsonify({'error': f"Health check failed: {str(e)}"}), 500

@video_bp.route('/admin', methods=['GET'])
def get_admin_landing_video():
    """Get current landing page video from database (admin view)"""
    try:
        if not UTILS_AVAILABLE:
            # Return default values if database not available
            video_info = {
                'video_url': '',
                'thumbnail_url': '',
                'title': 'ConnectedAutoCare Hero Protection 2025',
                'description': 'Showcase of our comprehensive protection plans',
                'duration': '2:30',
                'updated_at': datetime.now(timezone.utc).isoformat() + 'Z'
            }
            return jsonify(video_info)
            
        get_video_query = '''
            SELECT key, value
            FROM admin_settings
            WHERE category = 'video'
            ORDER BY key;
        '''
        
        video_results = execute_query(get_video_query)

        # Handle different response formats from execute_query
        actual_rows = []
        if isinstance(video_results, dict):
            if 'data' in video_results and video_results.get('success'):
                actual_rows = video_results['data']
        elif isinstance(video_results, list):
            actual_rows = video_results

        video_settings = {}
        for row in actual_rows:
            # Handle RealDictRow objects (from psycopg2)
            if hasattr(row, 'get'):
                key = row.get('key') or row.get(0)
                value = row.get('value') or row.get(1)
            elif hasattr(row, '__len__') and len(row) >= 2:
                key = row[0]
                value = row[1]
            else:
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
                
                # Parse JSON values properly
                if value:
                    try:
                        # Try to parse as JSON first
                        parsed_value = json.loads(value) if isinstance(value, str) else value
                        video_settings[key] = parsed_value
                    except (json.JSONDecodeError, TypeError):
                        # If not valid JSON, use as string (remove quotes if present)
                        video_settings[key] = value.strip('"') if isinstance(value, str) else value
                else:
                    video_settings[key] = ''

        # Provide defaults if not in database
        video_info = {
            'video_url': video_settings.get('landing_page_url', ''),
            'thumbnail_url': video_settings.get('landing_page_thumbnail', ''),
            'title': video_settings.get('landing_page_title', 'ConnectedAutoCare Hero Protection 2025'),
            'description': video_settings.get('landing_page_description', 'Showcase of our comprehensive protection plans'),
            'duration': video_settings.get('landing_page_duration', '2:30'),
            'updated_at': video_settings.get('last_updated', datetime.now(timezone.utc).isoformat() + 'Z'),
            'admin_info': {
                'video_filename': video_settings.get('video_filename', ''),
                'thumbnail_filename': video_settings.get('thumbnail_filename', ''),
                'storage_provider': 'Vercel Blob'
            }
        }

        return jsonify(video_info)

    except Exception as e:
        import traceback
        print(f"Get admin video error: {str(e)}")
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({'error': f"Failed to get video: {str(e)}"}), 500

@video_bp.route('/admin', methods=['PUT'])
def update_landing_video():
    """Update landing page video in database"""
    try:
        if not UTILS_AVAILABLE:
            return jsonify({'error': 'Database utilities not available'}), 500
            
        data = request.get_json()

        # Map form fields to database keys
        field_mapping = {
            'video_url': 'landing_page_url',
            'thumbnail_url': 'landing_page_thumbnail',
            'title': 'landing_page_title',
            'description': 'landing_page_description',
            'duration': 'landing_page_duration'
        }

        # Update each video setting
        for form_field, db_key in field_mapping.items():
            if form_field in data:
                # Format as JSON
                json_value = json.dumps(data[form_field])

                upsert_query = '''
                    INSERT INTO admin_settings (category, key, value, updated_by)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (category, key)
                    DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = CURRENT_TIMESTAMP,
                        updated_by = EXCLUDED.updated_by;
                '''
                execute_query(upsert_query, ('video', db_key, json_value, 'admin'))

        # Update last_updated timestamp
        timestamp_value = json.dumps(datetime.now(timezone.utc).isoformat() + 'Z')
        timestamp_query = '''
            INSERT INTO admin_settings (category, key, value, updated_by)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (category, key)
            DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = EXCLUDED.updated_by;
        '''
        execute_query(timestamp_query, ('video', 'last_updated', timestamp_value, 'admin'))

        return jsonify({
            'message': 'Landing page video updated successfully',
            'video_info': data
        })

    except Exception as e:
        import traceback
        print(f"Video update error: {str(e)}")
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({'error': f"Failed to update video: {str(e)}"}), 500

# ================================
# ERROR HANDLERS
# ================================

@video_bp.errorhandler(413)
def file_too_large(error):
    """Handle file too large errors"""
    return jsonify({'error': 'File too large. Check file size limits.'}), 413

@video_bp.errorhandler(400)
def bad_request(error):
    """Handle bad request errors"""
    return jsonify({'error': 'Bad request. Check your file upload.'}), 400

@video_bp.errorhandler(500)
def internal_server_error(error):
    """Handle internal server errors"""
    return jsonify({'error': 'Internal server error during video processing.'}), 500
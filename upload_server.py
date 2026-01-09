import os
import traceback
import urllib.parse as urlparse
from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import execute_values, RealDictCursor

# --- Initialize Flask app ---
app = Flask(__name__)

# --- Database Connection Function ---
def get_db_connection():
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if not DATABASE_URL:
        raise Exception("DATABASE_URL environment variable not set")
    
    url = urlparse.urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        dbname=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port,
        sslmode="require"
    )
    return conn


def safe_str(value, default=''):
    """Safely convert value to string, handling None."""
    if value is None:
        return default
    return str(value).strip()


def safe_int(value, default=0):
    """Safely convert value to integer, handling None and invalid values."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def truncate_str(value, max_length=50):
    """Safely truncate a string, handling None."""
    s = safe_str(value)
    if len(s) > max_length:
        return s[:max_length] + '...'
    return s


# --- Endpoint to get existing records ---
@app.route("/records/<work_order_id>", methods=["GET"])
def get_records(work_order_id):
    """
    Fetches all records from the database that match a given work_order_id.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = "SELECT * FROM work_uploads WHERE work_order = %s"
        cursor.execute(query, (work_order_id,))
        
        records = cursor.fetchall()
        cursor.close()
        
        if not records:
            return jsonify([]), 200
            
        return jsonify(records), 200

    except Exception as e:
        traceback_str = traceback.format_exc()
        print("Record fetch failed:", traceback_str)
        return jsonify({"error": str(e), "trace": traceback_str}), 500
    finally:
        if conn:
            conn.close()


# --- Upload endpoint with server-side duplicate prevention ---
@app.route("/upload", methods=["POST"])
def upload():
    conn = None
    try:
        data = request.get_json()
        if not isinstance(data, list) or not data:
            return jsonify({"error": "Expected a non-empty list of records"}), 400

        print(f"Received {len(data)} records")
        if data:
            print(f"Sample record keys: {list(data[0].keys())}")
            print(f"Sample record: {data[0]}")

        conn = get_db_connection()
        cursor = conn.cursor()
        
        print(f"Starting to process {len(data)} records for database insertion")
        
        # First, check for existing records to prevent duplicates
        existing_records = set()
        check_query = """
        SELECT location_id, cu_code, work_request, work_type FROM work_uploads 
        WHERE (location_id, cu_code, work_request, work_type) IN %s
        """
        
        # Create list of tuples to check - use safe_str for all values
        location_cu_work_type_tuples = [
            (
                safe_str(row.get("location_id")),
                safe_str(row.get("cu_code")),
                safe_str(row.get("work_request")),
                safe_str(row.get("work_type"))
            ) 
            for row in data
        ]
        
        if location_cu_work_type_tuples:
            cursor.execute(check_query, (tuple(location_cu_work_type_tuples),))
            existing_records = set(cursor.fetchall())
            print(f"Found {len(existing_records)} existing records in database")
        
        # Process each record and filter out duplicates
        values = []
        duplicates_found = []
        new_records = []
        
        for row in data:
            try:
                # Safely extract all fields with defaults
                location_id = safe_str(row.get("location_id"))
                cu_code = safe_str(row.get("cu_code"))
                work_request = safe_str(row.get("work_request"))
                work_type = safe_str(row.get("work_type"))
                description = safe_str(row.get("description"))
                work_order = safe_str(row.get("work_order"))
                district = safe_str(row.get("district"))
                project_id = safe_str(row.get("project_id"))
                quantity = safe_int(row.get("quantity"), 0)
                
                # Check if this combination already exists
                if (location_id, cu_code, work_request, work_type) in existing_records:
                    duplicates_found.append({
                        "location_id": location_id,
                        "cu_code": cu_code,
                        "work_request": work_request,
                        "work_type": work_type,
                        "reason": "Already exists in database"
                    })
                    print(f"DUPLICATE FOUND: location_id='{location_id}', cu_code='{cu_code}', work_request='{work_request}', work_type='{work_type}' - Already exists in database")
                    continue
                
                # Add to values for insertion
                values.append((
                    project_id,
                    work_order,
                    work_request,
                    district,
                    location_id,
                    cu_code,
                    description,
                    work_type,
                    quantity
                ))
                
                new_records.append({
                    "location_id": location_id,
                    "cu_code": cu_code,
                    "work_request": work_request,
                    "work_type": work_type,
                    "description": description
                })
                
            except Exception as e:
                print(f"Error processing row: {e}")
                return jsonify({"error": f"Error processing row: {e}"}), 400

        # Log processing results
        print(f"PROCESSING SUMMARY:")
        print(f"  Total records received: {len(data)}")
        print(f"  Duplicates found: {len(duplicates_found)}")
        print(f"  New records to insert: {len(values)}")
        
        # Log duplicate details
        if duplicates_found:
            print(f"DUPLICATE DETAILS:")
            for dup in duplicates_found:
                print(f"  - {dup['location_id']} + {dup['cu_code']} + {dup['work_request']} + {dup['work_type']}: {dup['reason']}")
        
        # Log new records to be inserted (with safe truncation)
        if new_records:
            print(f"NEW RECORDS TO INSERT:")
            for record in new_records[:5]:
                desc_preview = truncate_str(record['description'], 50)
                print(f"  - {record['location_id']} + {record['cu_code']} + {record['work_request']} + {record['work_type']}: {desc_preview}")
            if len(new_records) > 5:
                print(f"  - ... and {len(new_records) - 5} more records")
        
        # Only proceed with insertion if there are new records
        if not values:
            print("No new records to insert - all records were duplicates")
            return jsonify({
                "status": "success", 
                "rows_uploaded": 0,
                "uploaded_count": 0,
                "duplicates_found": len(duplicates_found),
                "message": "All records were duplicates"
            })

        insert_query = """
        INSERT INTO work_uploads (
            project_id, work_order, work_request, district, location_id,
            cu_code, description, work_type, quantity
        ) VALUES %s
        """

        execute_values(cursor, insert_query, values)
        rows_affected = cursor.rowcount
        
        print(f"DATABASE INSERTION COMPLETED:")
        print(f"  Records successfully inserted: {rows_affected}")
        print(f"  Duplicates prevented: {len(duplicates_found)}")
        print(f"  Total processing success: {rows_affected}/{len(data)} records")

        conn.commit()
        cursor.close()

        return jsonify({
            "status": "success", 
            "rows_uploaded": rows_affected,
            "uploaded_count": rows_affected,  # Added for compatibility with Flask app
            "duplicates_found": len(duplicates_found),
            "total_received": len(data),
            "message": f"Successfully uploaded {rows_affected} records, prevented {len(duplicates_found)} duplicates"
        })

    except Exception as e:
        traceback_str = traceback.format_exc()
        print("Upload failed:", traceback_str)
        return jsonify({"error": str(e), "trace": traceback_str}), 500
    finally:
        if conn:
            conn.close()


# --- Health check route ---
@app.route("/", methods=["GET"])
def health_check():
    return "✅ Linetec Uploader API is live!"


@app.route("/health", methods=["GET"])
def health_check_json():
    """JSON health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "Linetec Uploader API",
        "version": "1.1.0"
    })


# --- Entry point ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

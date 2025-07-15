import os
import traceback
import urllib.parse as urlparse
from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import execute_values, RealDictCursor

# --- Initialize Flask app ---
app = Flask(__name__)

# --- Database Connection Function ---
# A helper function to avoid repeating connection code.
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

# --- NEW: Endpoint to get existing records ---
@app.route("/records/<work_order_id>", methods=["GET"])
def get_records(work_order_id):
    """
    Fetches all records from the database that match a given work_order_id.
    This is what the Python client will call to check for duplicates.
    """
    conn = None
    try:
        conn = get_db_connection()
        # Using RealDictCursor to get results as dictionaries (like JSON)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = "SELECT * FROM work_uploads WHERE work_order = %s"
        cursor.execute(query, (work_order_id,))
        
        records = cursor.fetchall()
        
        cursor.close()
        
        if not records:
            # It's important to return an empty list if nothing is found,
            # not an error.
            return jsonify([]), 200
            
        return jsonify(records), 200

    except Exception as e:
        traceback_str = traceback.format_exc()
        print("Record fetch failed:", traceback_str)
        return jsonify({"error": str(e), "trace": traceback_str}), 500
    finally:
        if conn:
            conn.close()

# --- MODIFIED: Upload endpoint with server-side duplicate prevention ---
@app.route("/upload", methods=["POST"])
def upload():
    conn = None
    try:
        data = request.get_json()
        if not isinstance(data, list) or not data:
            return jsonify({"error": "Expected a non-empty list of records"}), 400

        # Log the received data structure for debugging
        print(f"Received {len(data)} records")
        if data:
            print(f"Sample record keys: {list(data[0].keys())}")
            print(f"Sample record: {data[0]}")

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Log processing progress
        print(f"Starting to process {len(data)} records for database insertion")
        
        # First, check for existing records to prevent duplicates
        existing_records = set()
        check_query = """
        SELECT location_id, cu_code, work_request, work_type FROM work_uploads 
        WHERE (location_id, cu_code, work_request, work_type) IN %s
        """
        
        # Create list of (location_id, cu_code, work_request, work_type) tuples to check
        location_cu_work_type_tuples = [(row["location_id"], row["cu_code"], row["work_request"], row["work_type"]) for row in data]
        
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
                location_id = row["location_id"]
                cu_code = row["cu_code"]
                work_request = row["work_request"]
                work_type = row["work_type"]
                
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
                
                # Process project_id
                project_id = row.get("project_id", "")
                if project_id and project_id.strip():
                    # Project IDs are strings like "R25P6", store as string
                    project_id_value = project_id.strip()
                else:
                    project_id_value = ""
                
                # Add to values for insertion (removed upload_status)
                values.append((
                    project_id_value,  # Store as string
                    row["work_order"],
                    row["work_request"],  # Add missing work_request field
                    row["district"],      # Add missing district field
                    location_id,
                    cu_code,
                    row["description"],
                    row["work_type"],
                    int(row["quantity"])
                ))
                
                new_records.append({
                    "location_id": location_id,
                    "cu_code": cu_code,
                    "work_request": work_request,
                    "work_type": work_type,
                    "description": row["description"]
                })
                
            except KeyError as e:
                return jsonify({"error": f"Missing required field: {e}"}), 400
            except ValueError as e:
                return jsonify({"error": f"Invalid data format: {e}"}), 400

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
        
        # Log new records to be inserted
        if new_records:
            print(f"NEW RECORDS TO INSERT:")
            for record in new_records[:5]:  # Show first 5 records
                print(f"  - {record['location_id']} + {record['cu_code']} + {record['work_request']} + {record['work_type']}: {record['description'][:50]}...")
            if len(new_records) > 5:
                print(f"  - ... and {len(new_records) - 5} more records")
        
        # Only proceed with insertion if there are new records
        if not values:
            print("No new records to insert - all records were duplicates")
            return jsonify({
                "status": "success", 
                "rows_uploaded": 0,
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
        
        # Get the number of rows that were actually inserted
        rows_affected = cursor.rowcount
        
        # Log successful processing
        print(f"DATABASE INSERTION COMPLETED:")
        print(f"  Records successfully inserted: {rows_affected}")
        print(f"  Duplicates prevented: {len(duplicates_found)}")
        print(f"  Total processing success: {rows_affected}/{len(data)} records")

        conn.commit()
        cursor.close()

        return jsonify({
            "status": "success", 
            "rows_uploaded": rows_affected,
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

# --- Entry point for local testing or gunicorn ---
if __name__ == "__main__":
    # The port Render uses is often set in an environment variable.
    # Defaulting to 10000 for local testing.
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

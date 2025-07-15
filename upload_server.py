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

        # ✅ Build insert values with proper error handling
        values = []
        for row in data:
            try:
                # Handle project_id - it might be empty string or None
                project_id = row.get("project_id", "")
                if project_id and project_id.strip():
                    # If project_id is a string like "R25P6", we need to handle it properly
                    # For now, let's assume it should be stored as string, not int
                    # If you need it as int, you'll need to extract numbers from it
                    project_id_value = project_id.strip()
                else:
                    project_id_value = ""
                
                values.append((
                    project_id_value,  # Store as string for now
                    row["work_type"],
                    int(row["quantity"]),
                    row["description"],
                    row["cu_code"],
                    row["location_id"],
                    row["work_order"]
                ))
            except KeyError as e:
                return jsonify({"error": f"Missing required field: {e}"}), 400
            except ValueError as e:
                return jsonify({"error": f"Invalid data format: {e}"}), 400

        insert_query = """
        INSERT INTO work_uploads (
            project_id, work_type, quantity, description,
            cu_code, location_id, work_order
        ) VALUES %s
        """

        execute_values(cursor, insert_query, values)
        
        # Get the number of rows that were actually inserted
        rows_affected = cursor.rowcount

        conn.commit()
        cursor.close()

        return jsonify({"status": "success", "rows_uploaded": rows_affected})

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

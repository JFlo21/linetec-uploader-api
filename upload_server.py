import os
import traceback
from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import execute_values

# ✅ Create Flask app
app = Flask(__name__)

# ✅ Upload route
@app.route("/upload", methods=["POST"])
def upload():
    try:
        # ✅ Validate input
        data = request.get_json()
        if not isinstance(data, list):
            return jsonify({"error": "Expected a list of records"}), 400

        # ✅ Get and validate DATABASE_URL
        DATABASE_URL = os.environ.get("DATABASE_URL")
        if not DATABASE_URL:
            raise Exception("DATABASE_URL environment variable not set")

        # ✅ Append SSL mode if not already included
        if "sslmode=" not in DATABASE_URL:
            DATABASE_URL += "?sslmode=require"

        # ✅ Connect to PostgreSQL
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # ✅ Prepare values for batch insert
        values = [
            (
                int(row["Project ID"]),
                row["Work Type"],
                int(row["Quantity"]),
                row["Description"],
                row["CU Code"],
                row["Location ID"],
                row["Work Order #"]
            )
            for row in data
        ]

        # ✅ SQL insert query
        insert_query = """
        INSERT INTO work_uploads (
            project_id, work_type, quantity, description,
            cu_code, location_id, work_order
        ) VALUES %s
        """

        execute_values(cursor, insert_query, values)
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"status": "success", "rows_uploaded": len(values)})

    except Exception as e:
        traceback_str = traceback.format_exc()
        print("Upload failed:", traceback_str)
        return jsonify({"error": str(e), "trace": traceback_str}), 500

# ✅ Health check route
@app.route("/", methods=["GET"])
def health_check():
    return "✅ Linetec Uploader API is live!"

# ✅ Entry point for local and gunicorn
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)



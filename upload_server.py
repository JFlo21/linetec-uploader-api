import os
import traceback
from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import execute_values

# ✅ Initialize Flask app at the top
app = Flask(__name__)

# ✅ Route definitions go below the app declaration
@app.route("/upload", methods=["POST"])
def upload():
    try:
        data = request.get_json()
        if not isinstance(data, list):
            return jsonify({"error": "Expected a list of records"}), 400

        DATABASE_URL = os.environ.get("DATABASE_URL")
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")

        cursor = conn.cursor()
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

@app.route("/", methods=["GET"])
def health_check():
    return "Linetec Uploader API is live!"

# ✅ Required for local development and gunicorn compatibility
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)


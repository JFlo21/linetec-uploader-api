import os
import traceback
import urllib.parse as urlparse
from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import execute_values

# ✅ Initialize Flask app
app = Flask(__name__)

# ✅ Upload endpoint
@app.route("/upload", methods=["POST"])
def upload():
    try:
        data = request.get_json()
        if not isinstance(data, list):
            return jsonify({"error": "Expected a list of records"}), 400

        # ✅ Get the DATABASE_URL from environment
        DATABASE_URL = os.environ.get("DATABASE_URL")
        if not DATABASE_URL:
            raise Exception("DATABASE_URL environment variable not set")

        # ✅ Parse the URL to extract connection pieces
        url = urlparse.urlparse(DATABASE_URL)

        # ✅ Connect using individual components + sslmode=require
        conn = psycopg2.connect(
            dbname=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port,
            sslmode="require"
        )

        cursor = conn.cursor()

        # ✅ Build insert values
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

# ✅ Health check route
@app.route("/", methods=["GET"])
def health_check():
    return "✅ Linetec Uploader API is live!"

# ✅ Entry point for local testing or gunicorn
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

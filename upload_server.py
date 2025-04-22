import traceback
import os
import traceback  # ✅ For full error logging
from flask import Flask, request, jsonify
import psycopg2  # ✅ PostgreSQL connection
from psycopg2.extras import execute_values  # ✅ Efficient batch insert


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

        print("Payload:", values)  # ✅ Debug print

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
        print("Upload failed:", traceback_str)  # ✅ Log full stack trace
        return jsonify({"error": str(e), "trace": traceback_str}), 500

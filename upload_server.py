import os
from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import execute_values

Cognos_Database = os.environ.get("postgresql://cognos_database_user:Y6b40zirOK7B0BZCETcruwqcLQXTCibE@dpg-d019vqbuibrs73ahvbhg-a.virginia-postgres.render.com/cognos_database")

app = Flask(__name__)

@app.route("/upload", methods=["POST"])
def upload():
    try:
        data = request.get_json()
        if not isinstance(data, list):
            return jsonify({"error": "Expected a list of records"}), 400

        conn = psycopg2.connect(
    dbname="cognos_database",
    user="cognos_database_user",
    password="Y6b40zirOK7B0BZCETcruwqcLQXTCibE",
    host="dpg-d019vqbuibrs73ahvbhg-a.virginia-postgres.render.com",
    port=5432,
    sslmode="require",
    sslrootcert=None,
    sslcert=None,
    sslkey=None,
)

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
        return jsonify({"error": str(e)}), 500

@app.route("/", methods=["GET"])
def health_check():
    return "Linetec Uploader API is live!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

CREATE TABLE work_uploads (
    id SERIAL PRIMARY KEY,
    project_id TEXT,
    work_type TEXT,
    quantity INTEGER,
    description TEXT,
    cu_code TEXT,
    location_id TEXT,
    work_order TEXT
);

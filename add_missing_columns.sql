-- Add missing columns to work_uploads table
-- Run this SQL on your database to add the missing fields

ALTER TABLE work_uploads 
ADD COLUMN IF NOT EXISTS work_request VARCHAR(255),
ADD COLUMN IF NOT EXISTS district VARCHAR(255),
ADD COLUMN IF NOT EXISTS upload_status VARCHAR(50) DEFAULT 'Ready';

-- Create indexes for better performance on common queries
CREATE INDEX IF NOT EXISTS idx_work_uploads_work_request ON work_uploads(work_request);
CREATE INDEX IF NOT EXISTS idx_work_uploads_district ON work_uploads(district);
CREATE INDEX IF NOT EXISTS idx_work_uploads_work_order ON work_uploads(work_order);

-- Verify the table structure
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'work_uploads' 
ORDER BY ordinal_position;

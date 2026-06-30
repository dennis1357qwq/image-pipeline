DROP TABLE IF EXISTS jobs;

CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY,
    pipeline JSONB NOT NULL,
    input_key TEXT NOT NULL,
    output_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('PENDING', 'PROCESSING', 'DONE', 'FAILED')
    ),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
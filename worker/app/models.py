from dataclasses import dataclass

@dataclass
class Job:
    job_id: str

@dataclass
class JobMetadata:
    job_id: str
    operation: str
    input_key: str
    output_key: str
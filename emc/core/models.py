from dataclasses import dataclass
from typing import Optional


@dataclass
class Project:
    id: Optional[int]
    name: str
    client: str
    created_at: str


@dataclass
class TestItem:
    id: Optional[int]
    project_id: int
    standard_code: str
    status: str
    scheduled_date: Optional[str]
    session_id: Optional[int]


@dataclass
class TestSession:
    id: Optional[int]
    project_id: int
    standard_code: str
    eut_name: str
    eut_serial: str
    operator: str
    level_label: str
    params_json: str
    started_at: Optional[str]
    finished_at: Optional[str]
    result: Optional[str]
    notes: str

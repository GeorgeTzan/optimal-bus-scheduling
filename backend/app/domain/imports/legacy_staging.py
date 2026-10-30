from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from typing import List, Dict, Any, Optional


@dataclass
class StagedRow:
    row_index: int
    raw_data: Dict[str, Any]
    parsed_data: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)
    is_valid: bool = True


@dataclass
class ImportBatch:
    batch_id: str
    tenant_id: int
    file_format: str
    service_date: date
    status: str = "staged"  # staged, validated, committed, failed
    total_rows: int = 0
    valid_rows: int = 0
    error_count: int = 0
    staged_rows: List[StagedRow] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ImportPreview:
    batch_id: str
    total_rows: int
    valid_rows: int
    error_count: int
    is_valid: bool
    sample_rows: List[Dict[str, Any]]
    issues: List[str]


@dataclass(frozen=True)
class ImportResult:
    batch_id: str
    committed_rows: int
    service_date: date

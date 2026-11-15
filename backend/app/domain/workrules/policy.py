from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from app.domain.workrules import legal


class LooserThanLawError(ValueError):
    def __init__(self, rule_id: str, value: int, legal: int):
        super().__init__(f"{rule_id}={value} is looser than legal {legal}")
        self.rule_id = rule_id
        self.value = value
        self.legal = legal


@dataclass(frozen=True)
class WorkRulePolicy:
    limits: Mapping[str, int]
    warning_rules: frozenset[str]
    legal_version: str
    company_version: int

    def value(self, rule_id: str) -> int:
        return self.limits[rule_id]

    def to_dict(self) -> dict[str, Any]:
        return {
            "limits": dict(self.limits),
            "warning_rules": sorted(self.warning_rules),
            "legal_version": self.legal_version,
            "company_version": self.company_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WorkRulePolicy:
        return cls(
            limits=MappingProxyType(dict(data["limits"])),
            warning_rules=frozenset(data["warning_rules"]),
            legal_version=data["legal_version"],
            company_version=data["company_version"],
        )


def build_policy(
    overrides: Mapping[str, int], warning_rules: Iterable[str], company_version: int
) -> WorkRulePolicy:
    limits = {rule_id: limit.value for rule_id, limit in legal.LEGAL_LIMITS.items()}
    for rule_id, value in overrides.items():
        limit = legal.LEGAL_LIMITS[rule_id]
        looser = (
            value != limit.value
            if limit.direction == "fixed"
            else value > limit.value
            if limit.direction == "max"
            else value < limit.value
        )
        if looser:
            raise LooserThanLawError(rule_id, value, limit.value)
        limits[rule_id] = value
    warnings = frozenset(warning_rules)
    unknown = warnings - legal.WARNING_RULES
    if unknown:
        raise KeyError(sorted(unknown)[0])
    return WorkRulePolicy(
        limits=MappingProxyType(limits),
        warning_rules=warnings,
        legal_version=legal.LEGAL_RULES_VERSION,
        company_version=company_version,
    )


from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Literal

@dataclass
class FieldSpec:
    name: str
    description: str = ""
    type: Literal["string","number","date","boolean","integer","object"] = "string"
    format: Optional[str] = None
    examples: List[Any] = field(default_factory=list)
    required: bool = False

@dataclass
class ArraySpec:
    name: str
    description: str = ""
    columns: List[FieldSpec] = field(default_factory=list)

@dataclass
class ExtractionSpec:
    title: str
    description: str = ""
    fields: List[FieldSpec] = field(default_factory=list)
    arrays: List[ArraySpec] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ExtractionSpec":
        fs = [FieldSpec(**f) for f in d.get("fields", [])]
        arrs = []
        for a in d.get("arrays", []):
            cols = [FieldSpec(**c) for c in a.get("columns", [])]
            arrs.append(ArraySpec(name=a["name"], description=a.get("description",""), columns=cols))
        return ExtractionSpec(
            title=d.get("title", "Untitled Spec"),
            description=d.get("description", ""),
            fields=fs,
            arrays=arrs,
        )

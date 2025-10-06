from __future__ import annotations
import json
import ast
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from tqdm import tqdm
import pandas as pd
import numpy as np

from app.config import PipelineConfig
from app.pipeline.providers import make_provider
from app.pipeline.prompts import (
    EXTRACT_SYSTEM_JSON,
    EXTRACT_USER_TEMPLATE_TEXT,
    EXTRACT_USER_TEMPLATE_VISION,
    EXCEL_PREPLAN_SYSTEM,
    EXCEL_PREPLAN_USER,
    EXCEL_CODEGEN_SYSTEM,
    EXCEL_CODEGEN_USER,
)
from app.pipeline.loaders import (
    pdf_text_preview, render_pdf_pages, load_image_bytes,
    excel_overview, excel_load_all, text_preview, detect_doc_type,
    render_powerpoint_pages, csv_overview, csv_load_all
)

# ---------------- Core JSON helpers ----------------

def _coerce_json(s: str) -> Dict[str, Any]:
    s = (s or "").strip()
    if not s:
        return {}
    # remove code fences if any
    if s.startswith("```"):
        s = s.strip("`")
        if s.startswith("json"):
            s = s[len("json"):].lstrip()
    # narrow to the outermost JSON object braces if present
    l, r = s.find("{"), s.rfind("}")
    if l != -1 and r != -1 and r > l:
        s = s[l:r+1]
    try:
        return json.loads(s)
    except Exception:
        # last-resort: try to eval as python literal (risk-controlled: only dict allowed)
        try:
            v = ast.literal_eval(s)
            return v if isinstance(v, dict) else {}
        except Exception:
            return {}

def _strip_code_fences(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```python"):
        s = s[len("```python"):].strip()
    elif s.startswith("```"):
        s = s[len("```"):].strip()
    if s.endswith("```"):
        s = s[:-len("```")].strip()
    return s

# ---------------- Text & Vision extraction ----------------

class DocumentExtractor:
    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg
        self.provider = make_provider(
            provider_name=cfg.llm.provider,
            model=cfg.llm.model,
            temperature=cfg.llm.temperature,
            max_tokens=cfg.llm.max_output_tokens,
        )

    def extract_textual(self, path: str, spec: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        txt = ""
        doc_type = detect_doc_type(path)
        if doc_type == "pdf":
            txt = pdf_text_preview(path)
        elif doc_type == "powerpoint":
            txt = text_preview(path)
        else:  # For docx, html, txt, csv, etc.
            txt = text_preview(path)
            
        if spec:
            # Use spec-driven extraction
            from app.pipeline.prompts import EXTRACT_WITH_SPEC_SYSTEM, EXTRACT_WITH_SPEC_USER_TEXT
            spec_json = json.dumps(spec, indent=2)
            user = EXTRACT_WITH_SPEC_USER_TEXT.format(spec_json=spec_json, text_chunk=(txt or "")[:6000])
            system = EXTRACT_WITH_SPEC_SYSTEM
        else:
            # For "text" type documents (including CSV), return raw text if no spec for now
            user = EXTRACT_USER_TEMPLATE_TEXT.format(text_chunk=(txt or "")[:6000])
            system = EXTRACT_SYSTEM_JSON
            
        out = self.provider.generate(system=system, user=user, json_mode=self.cfg.llm.json_mode)
        return _coerce_json(out)

    def extract_vision_full(self, path: str, spec: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        images = []
        doc_type = detect_doc_type(path)
        if doc_type == "pdf":
            images = render_pdf_pages(path, dpi=self.cfg.vision.dpi)
        elif doc_type == "powerpoint":
            images = render_powerpoint_pages(path, dpi=self.cfg.vision.dpi)
        else:
            images = [load_image_bytes(path)]
        if not images:
            # fallback to text
            return self.extract_textual(path, spec=spec)
        
        # Process in batches of 10 pages to avoid payload size errors
        merged: Dict[str, Any] = {}
        for i in tqdm(range(0, len(images), 10), desc="Processing batches"):
            batch = images[i:i+10]
            
            if spec:
                # Use spec-driven extraction
                from app.pipeline.prompts import EXTRACT_WITH_SPEC_SYSTEM, EXTRACT_WITH_SPEC_USER_VISION
                spec_json = json.dumps(spec, indent=2)
                user = f"{EXTRACT_WITH_SPEC_USER_VISION}\n\nThis is batch {i//10 + 1} of {len(images)//10 + 1} of the document."
                user = user.replace("{spec_json}", spec_json)
                system = EXTRACT_WITH_SPEC_SYSTEM
            else:
                user = f"{EXTRACT_USER_TEMPLATE_VISION}\n\nThis is batch {i//10 + 1} of {len(images)//10 + 1} of the document."
                system = EXTRACT_SYSTEM_JSON
                
            out = self.provider.generate_vision(system=system, user=user, images=batch, json_mode=self.cfg.llm.json_mode)
            js = _coerce_json(out)
            merged.update({k: v for k, v in js.items() if v not in [None, "", [], {}]})
        return merged

    def extract_vision_per_page(self, path: str, spec: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Merge page-level JSONs (later keys override earlier)
        doc_type = detect_doc_type(path)
        if doc_type == "pdf":
            images = render_pdf_pages(path, dpi=self.cfg.vision.dpi)
        elif doc_type == "powerpoint":
            images = render_powerpoint_pages(path, dpi=self.cfg.vision.dpi)
        else:
            images = [load_image_bytes(path)]
        if not images:
            return self.extract_textual(path, spec=spec)
        
        # Process in batches of 10 pages to avoid payload size errors
        merged: Dict[str, Any] = {}
        for i in tqdm(range(0, len(images), 10), desc="Processing batches"):
            batch = images[i:i+10]
            
            if spec:
                # Use spec-driven extraction
                from app.pipeline.prompts import EXTRACT_WITH_SPEC_SYSTEM, EXTRACT_WITH_SPEC_USER_VISION
                spec_json = json.dumps(spec, indent=2)
                user = f"{EXTRACT_WITH_SPEC_USER_VISION}\n\nThis is batch {i//10 + 1} of {len(images)//10 + 1} of the document."
                user = user.replace("{spec_json}", spec_json)
                system = EXTRACT_WITH_SPEC_SYSTEM
            else:
                user = f"{EXTRACT_USER_TEMPLATE_VISION}\n\nThis is batch {i//10 + 1} of {len(images)//10 + 1} of the document."
                system = EXTRACT_SYSTEM_JSON
                
            out = self.provider.generate_vision(system=system, user=user, images=batch, json_mode=self.cfg.llm.json_mode)
            js = _coerce_json(out)
            merged.update({k: v for k, v in js.items() if v not in [None, "", [], {}]})
        return merged

# ---------------- Excel pre-plan & extraction ----------------

@dataclass
class ExcelPlan:
    intents: List[str]
    per_sheet: Dict[str, Dict[str, Any]]
    joins: List[Dict[str, Any]]
    notes: str

class ExcelExtractor:
    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg
        self.provider = make_provider(
            provider_name=cfg.llm.provider,
            model=cfg.llm.model,
            temperature=cfg.llm.temperature,
            max_tokens=cfg.llm.max_output_tokens,
        )

    # Rule-based lightweight pre-plan as a fallback when no LLM
    def _heuristic_preplan(self, overview: Dict[str, List[List[str]]]) -> ExcelPlan:
        per_sheet: Dict[str, Dict[str, Any]] = {}
        intents: List[str] = ["records"]
        joins: List[Dict[str, Any]] = []

        for sheet, grid in overview.items():
            # Find header row as the first row with > 50% non-null-like cells
            header_idx = 0
            if grid:
                best_i, best_score = 0, -1
                for i, row in enumerate(grid[:10]):
                    values = [c for c in row if c not in ["", "None", "nan"]]
                    score = len(values)
                    if score > best_score:
                        best_i, best_score = i, score
                header_idx = best_i
            per_sheet[sheet] = {
                "header_row_index": header_idx,
                "header_span_rows": 1,
                "likely_table_range": None,
                "key_columns": [],
                "dtypes": {},
            }
        return ExcelPlan(intents=intents, per_sheet=per_sheet, joins=joins, notes="heuristic preplan")

    def preplan(self, path: str) -> ExcelPlan:
        ov = excel_overview(path, sample_rows=self.cfg.excel.sample_rows)
        if self.cfg.excel.preplan_with_llm:
            overview_str = json.dumps(ov)[:15000]
            out = self.provider.generate(system=EXCEL_PREPLAN_SYSTEM, user=EXCEL_PREPLAN_USER.format(overview=overview_str), json_mode=True)
            js = _coerce_json(out)
            if js:
                return ExcelPlan(
                    intents=js.get("intents", []),
                    per_sheet=js.get("per_sheet", {}),
                    joins=js.get("joins", []),
                    notes=js.get("notes", ""),
                )
        # Fallback
        return self._heuristic_preplan(ov)

    def _safe_exec(self, code: str, dfs: Dict[str, "pd.DataFrame"]) -> Optional["pd.DataFrame"]:
        # VERY basic safety sandbox: no builtins except a small whitelist
        # import pandas as pd # moved to top
        # import numpy as np # moved to top
        
        # Allow importing pandas, but nothing else
        def limited_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name in ['pandas', 'numpy']:
                return __import__(name, globals, locals, fromlist, level)
            raise ImportError(f"Import of '{name}' is not allowed")

        safe_builtins = {
            "len": len, "range": range, "min": min, "max": max, "sum": sum, "abs": abs, 
            "enumerate": enumerate, "zip": zip, "sorted": sorted, "print": print, "__import__": limited_import, "list": list
        }
        glb = {"__builtins__": safe_builtins, "pd": pd, "np": np}
        loc = {"dfs": dfs}
        try:
            exec(code, glb, loc)
        except Exception as e:
            raise RuntimeError(f"Generated code failed: {e}")
        result = loc.get("result", None)
        return result

    def extract(self, path: str, desired_columns: Optional[List[str]] = None, spec: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        dfs = excel_load_all(path)
        plan = self.preplan(path)

        # If codegen enabled, ask the LLM to emit a pandas program
        if self.cfg.excel.codegen_with_llm:
            plan_json = json.dumps({
                "intents": plan.intents,
                "per_sheet": plan.per_sheet,
                "joins": plan.joins,
                "notes": plan.notes,
            })
            
            # Include spec information if provided
            spec_info = ""
            if spec:
                spec_json = json.dumps(spec, indent=2)
                spec_info = f"\n\nSPECIFICATION (MUST FOLLOW EXACTLY):\n{spec_json}\n\nIMPORTANT: Only extract the fields specified in the spec above. Do not include any other fields."
            
            user = EXCEL_CODEGEN_USER.format(
                plan_json=plan_json,
                desired_columns=desired_columns or []
            ) + spec_info
            raw_code = self.provider.generate(system=EXCEL_CODEGEN_SYSTEM, user=user, json_mode=False)
            code = _strip_code_fences(raw_code)

            if self.cfg.excel.allow_exec_generated_code:
                df = self._safe_exec(code, dfs)
                if df is not None:
                    # Return as a records list
                    try:
                        records = df.to_dict(orient="records")
                    except Exception:
                        records = []
                    return {"plan": plan_json, "program": code, "records": records}
                # If codegen fails, fall through to the simple extractor below
            else:
                # Just return the code for inspection
                return {"plan": plan_json, "program": code, "records": []}

        # Non-codegen fallback: pick the sheet with the most columns/rows and return it
        best_sheet, best_score = None, -1
        for name, df in dfs.items():
            score = df.shape[0] * df.shape[1]
            if score > best_score:
                best_sheet, best_score = name, score
        if best_sheet is None:
            return {"plan": plan.__dict__, "program": None, "records": []}
        df = dfs[best_sheet]
        try:
            records = df.to_dict(orient="records")
        except Exception:
            records = []
        return {"plan": plan.__dict__, "program": None, "records": records}

class CsvExtractor:
    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg
        self.provider = make_provider(
            provider_name=cfg.llm.provider,
            model=cfg.llm.model,
            temperature=cfg.llm.temperature,
            max_tokens=cfg.llm.max_output_tokens,
        )

    def preplan(self, path: str) -> ExcelPlan:
        ov = csv_overview(path, sample_rows=self.cfg.excel.sample_rows)
        if self.cfg.excel.preplan_with_llm:
            overview_str = json.dumps(ov)[:15000]
            out = self.provider.generate(system=EXCEL_PREPLAN_SYSTEM, user=EXCEL_PREPLAN_USER.format(overview=overview_str), json_mode=True)
            js = _coerce_json(out)
            if js:
                # CSVs only have one "sheet" so we can simplify the plan structure
                return ExcelPlan(
                    intents=js.get("intents", []),
                    per_sheet={ "default_sheet": js.get("per_sheet", {}).get("default_sheet", {}) },
                    joins=js.get("joins", []),
                    notes=js.get("notes", ""),
                )
        # Fallback heuristic for CSV - simpler than Excel's since it's a single table
        return ExcelPlan(intents=["records"], per_sheet={
            "default_sheet": {"header_row_index": 0, "header_span_rows": 1, "key_columns": []}
        }, joins=[], notes="heuristic preplan for CSV")

    def _safe_exec(self, code: str, dfs: Dict[str, "pd.DataFrame"]) -> Optional["pd.DataFrame"]:
        import pandas as pd
        import numpy as np
        
        def limited_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name in ['pandas', 'numpy']:
                return __import__(name, globals, locals, fromlist, level)
            raise ImportError(f"Import of '{name}' is not allowed")

        safe_builtins = {
            "len": len, "range": range, "min": min, "max": max, "sum": sum, "abs": abs, 
            "enumerate": enumerate, "zip": zip, "sorted": sorted, "print": print, "__import__": limited_import, "list": list
        }
        glb = {"__builtins__": safe_builtins, "pd": pd, "np": np}
        loc = {"dfs": dfs}
        try:
            exec(code, glb, loc)
        except Exception as e:
            raise RuntimeError(f"Generated code failed: {e}")
        result = loc.get("result", None)
        return result

    def extract(self, path: str, desired_columns: Optional[List[str]] = None, spec: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        dfs = csv_load_all(path)
        plan = self.preplan(path)

        if self.cfg.excel.codegen_with_llm:
            plan_json = json.dumps({
                "intents": plan.intents,
                "per_sheet": plan.per_sheet,
                "joins": plan.joins,
                "notes": plan.notes,
            })
            
            spec_info = ""
            if spec:
                spec_json = json.dumps(spec, indent=2)
                spec_info = f"\n\nSPECIFICATION (MUST FOLLOW EXACTLY):\n{spec_json}\n\nIMPORTANT: Only extract the fields specified in the spec above. Do not include any other fields."
            
            user = EXCEL_CODEGEN_USER.format(
                plan_json=plan_json,
                desired_columns=desired_columns or []
            ) + spec_info
            raw_code = self.provider.generate(system=EXCEL_CODEGEN_SYSTEM, user=user, json_mode=False)
            code = _strip_code_fences(raw_code)

            if self.cfg.excel.allow_exec_generated_code:
                df = self._safe_exec(code, dfs)
                if df is not None:
                    try:
                        records = df.to_dict(orient="records")
                    except Exception:
                        records = []
                    return {"plan": plan_json, "program": code, "records": records}
            else:
                return {"plan": plan_json, "program": code, "records": []}

        # Non-codegen fallback for CSV
        df = dfs["default_sheet"]
        try:
            records = df.to_dict(orient="records")
        except Exception:
            records = []
        return {"plan": plan.__dict__, "program": None, "records": records}
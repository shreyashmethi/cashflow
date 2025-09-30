
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
from app.config import PipelineConfig
from app.pipeline.providers import make_provider
from app.pipeline.prompts import (
    CLASSIFIER_SYSTEM,
    CLASSIFIER_USER_TEMPLATE_TEXT,
    CLASSIFIER_USER_TEMPLATE_VISION,
)
from app.pipeline.loaders import (
    detect_doc_type,
    pdf_text_preview,
    pdf_page_count,
    render_pdf_pages,
    text_preview,
    load_image_bytes,
)
import os, json

@dataclass
class Plan:
    path: str
    doc_type: str                  # pdf, image, excel, word, html, text, other
    category: str                  # invoice, receipt, etc.
    strategy: str                  # vision_full, vision_per_page, text, excel
    confidence: float
    fields: List[str]
    notes: str

class LLMPlanner:
    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg
        self.provider = make_provider(
            provider_name=cfg.llm.provider,
            model=cfg.llm.model,
            temperature=cfg.llm.temperature,
            max_tokens=cfg.llm.max_output_tokens,
        )

    def _classify_textual(self, text_preview: str) -> Dict[str, Any]:
        user = CLASSIFIER_USER_TEMPLATE_TEXT.format(text_preview=text_preview[:4000])
        out = self.provider.generate(system=CLASSIFIER_SYSTEM, user=user, json_mode=True)
        try:
            return json.loads(out)
        except Exception:
            # Fallback
            return {"category": "other", "confidence": 0.2, "strategy": "text", "fields": [], "notes": "fallback"}

    def _classify_visual(self, images: List[bytes], small_doc: bool) -> Dict[str, Any]:
        user = CLASSIFIER_USER_TEMPLATE_VISION
        out = self.provider.generate_vision(system=CLASSIFIER_SYSTEM, user=user, images=images, json_mode=True)
        try:
            res = json.loads(out)
        except Exception:
            res = {"category": "other", "confidence": 0.2, "strategy": "vision_per_page", "fields": [], "notes": "fallback"}
        # If provider didn't set strategy, suggest based on page count
        if small_doc and res.get("strategy") in [None, "vision_per_page"]:
            res["strategy"] = "vision_full"
        return res

    def plan_for_file(self, path: str) -> Plan:
        doc_type = detect_doc_type(path)
        # Excel is a special case
        if doc_type == "excel":
            return Plan(path=path, doc_type=doc_type, category="spreadsheet", strategy="excel",
                        confidence=0.99, fields=[], notes="Excel routing by rule")
        
        # CSV is a special case
        if doc_type == "csv":
            return Plan(path=path, doc_type=doc_type, category="spreadsheet", strategy="csv",
                        confidence=0.99, fields=[], notes="CSV routing by rule")

        # If the user disabled LLM classification, pick a rule-based default
        if not self.cfg.planner.classify_with_llm:
            strategy = "vision_per_page" if doc_type in ["pdf", "image"] else "text"
            return Plan(path, doc_type, "other", strategy, 0.5, [], "LLM classification disabled")

        # Otherwise, attempt LLM-based classification depending on type
        if doc_type == "pdf":
            pages = pdf_page_count(path)
            small_doc = pages > 0 and pages <= self.cfg.vision.max_pages_full #15
            if self.cfg.llm.enable_vision:
                imgs = render_pdf_pages(path, dpi=self.cfg.vision.dpi)
                if imgs:
                    res = self._classify_visual(imgs[:min(len(imgs), 8)], small_doc)
                else:
                    # fallback to text preview
                    txt = pdf_text_preview(path)
                    res = self._classify_textual(txt)
            else:
                txt = pdf_text_preview(path)
                res = self._classify_textual(txt)
        elif doc_type == "image":
            if self.cfg.llm.enable_vision:
                img = load_image_bytes(path)
                res = self._classify_visual([img], small_doc=True)
            else:
                res = {"category":"image_text", "confidence":0.5, "strategy":"text", "fields":[], "notes":"Vision disabled"}
        elif doc_type in ["word", "html", "text"]:
            txt = text_preview(path)
            res = self._classify_textual(txt)
        else:
            # unknown => try text
            txt = text_preview(path)
            res = self._classify_textual(txt)

        category = res.get("category", "other")
        strategy = res.get("strategy", "text")
        confidence = float(res.get("confidence", 0.5))
        fields = res.get("fields", [])
        notes = res.get("notes", "")
        # Guardrail: If doc is PDF/Image but vision disabled, force text
        if doc_type in ["pdf", "image"] and not self.cfg.llm.enable_vision and strategy.startswith("vision"):
            strategy = "text"
        final_plan = Plan(path, doc_type, category, strategy, confidence, fields, notes)
        print(f"DEBUG: Plan for file {path}: doc_type={final_plan.doc_type}, strategy={final_plan.strategy}")
        return final_plan


from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional
import os

@dataclass
class DatabaseConfig:
    # Get database credentials from environment
    user: str = os.getenv("DB_USER", "postgres")
    password: str = os.getenv("DB_PASSWORD", "postgres")
    host: str = os.getenv("DB_HOST", "localhost")
    port: str = os.getenv("DB_PORT", "5432")
    name: str = os.getenv("DB_NAME", "cashflow")
    
    @property
    def url(self) -> str:
        """Construct database URL from components or use DATABASE_URL if provided"""
        return os.getenv(
            "DATABASE_URL",
            f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
        )

@dataclass
class LLMConfig:
    provider: Literal["gpt", "claude"] = "gpt"
    # Default models are left None so provider sets a sensible default (e.g., gpt-4o or claude-3-5-sonnet)
    model: Optional[str] = None
    temperature: float = 0.0
    max_output_tokens: int = 2000
    json_mode: bool = True
    # If True, allow sending images or rendered pages to the model
    enable_vision: bool = True

@dataclass
class VisionConfig:
    strategy: Literal["auto", "full_document", "page_by_page"] = "auto"
    # If the doc has <= this many pages, send as a single batch (when provider supports)
    max_pages_full: int = 15
    dpi: int = 180
    # If True and vision provider isn't available, try OCR fallback (pytesseract) for images/PDFs
    ocr_fallback: bool = False
    mode: str = "auto"  # auto | full_document | page_by_page | off
    max_total_image_bytes: int = 45 * 1024 * 1024  # stay below the 50MB cap
    max_images_per_batch: int = 10                 # conservative default
    long_side_px: int = 1600                       # resize bound
    jpeg_quality: int = 70                         # 60–75 works well
    dpi_narrative: int = 150                       # pages with mostly text
    dpi_tables: int = 220                          # pages with tables/figures

@dataclass
class PlannerConfig:
    classify_with_llm: bool = True
    concurrency: int = 2
    # If True, scan subdirectories
    recursive: bool = True
    # File extensions to scan for
    allowed_extensions: List[str] = field(default_factory=lambda: [".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".xlsx", ".xls", ".docx", ".html", ".htm", ".txt", ".csv", ".pptx"])

@dataclass
class ExcelConfig:
    preplan_with_llm: bool = True
    codegen_with_llm: bool = True
    safe_exec: bool = True
    sample_rows: int = 50
    # When false, we stick to a robust dataframe pipeline without codegen.
    allow_exec_generated_code: bool = True

@dataclass
class PipelineConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    planner: PlannerConfig = field(default_factory=PlannerConfig)
    excel: ExcelConfig = field(default_factory=ExcelConfig)
    db: DatabaseConfig = field(default_factory=DatabaseConfig)

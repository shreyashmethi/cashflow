import os
import shutil
import tempfile
from fastapi import UploadFile
from typing import List, Dict, Any

from app.config import PipelineConfig
from app.pipeline.loaders import detect_doc_type
from app.pipeline.extractors import DocumentExtractor, CsvExtractor, ExcelExtractor

class FileParser:
    def __init__(self, file: UploadFile):
        self.file = file
        self.cfg = PipelineConfig()

    async def parse(self) -> List[Dict[str, Any]]:
        # Create a temporary directory to store the uploaded file
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, self.file.filename)

        # Save the uploaded file to the temporary location
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(self.file.file, buffer)

        try:
            doc_type = detect_doc_type(file_path)
            
            if doc_type == "csv":
                extractor = CsvExtractor(self.cfg)
                result = extractor.extract(file_path)
                return result.get("records", [])
            elif doc_type == "excel":
                extractor = ExcelExtractor(self.cfg)
                result = extractor.extract(file_path)
                return result.get("records", [])
            elif doc_type in ["pdf", "image", "word", "html", "text", "powerpoint"]:
                # For now, we'll use the textual extractor. We can enhance this later.
                extractor = DocumentExtractor(self.cfg)
                result = extractor.extract_textual(file_path)
                # The result from DocumentExtractor is a single dictionary, not a list of records.
                # We need to adapt this to our expected output format.
                # For now, we'll return it as a single-element list if it's not empty.
                return [result] if result else []
            else:
                # Unsupported file type
                return []
        finally:
            # Clean up the temporary directory
            shutil.rmtree(temp_dir)

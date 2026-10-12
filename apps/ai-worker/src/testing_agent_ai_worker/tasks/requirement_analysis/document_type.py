"""Select the material extractor from the original requirement format."""


def extraction_skill(document_type: str) -> str:
    normalized = document_type.strip().lower()
    if normalized in {"word", "docx"}:
        return "extract-docx-enhanced-text"
    if normalized == "richtext":
        return "extract-richtext-enhanced-text"
    raise ValueError("需求材料提取仅支持 Word/DOCX 或富文本，请替换原始需求文档后重试")

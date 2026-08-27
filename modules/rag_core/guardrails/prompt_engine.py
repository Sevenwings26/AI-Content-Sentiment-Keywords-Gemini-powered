# modules/rag_core/guardrails/prompt_engine.py
import re
from typing import Dict, Any

class PromptEngine:
    @staticmethod
    def render_template(template_str: str, variables: Dict[str, Any]) -> str:
        rendered = template_str
        for key, val in variables.items():
            pattern = re.compile(r"\{\{\s*" + re.escape(key) + r"\s*\}\}")
            rendered = pattern.sub(str(val) if val is not None else "", rendered)
        return rendered

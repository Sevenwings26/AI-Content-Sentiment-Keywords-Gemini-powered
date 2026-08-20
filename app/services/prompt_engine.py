# app/services/prompt_engine.py
import re
from typing import Dict, Any

class PromptEngine:
    """
    Template interpolation engine resolving dynamic placeholders like:
    {user_name}, {user_role}, {department_name}, {org_name}, {context}, {query}
    Safely ignores unmatched braces in user text without throwing KeyError formatting exceptions.
    """
    @staticmethod
    def render_template(template_str: str, variables: Dict[str, Any]) -> str:
        if not template_str:
            return ""

        rendered = template_str
        for key, val in variables.items():
            placeholder = "{" + key + "}"
            if placeholder in rendered:
                rendered = rendered.replace(placeholder, str(val or ""))

        return rendered

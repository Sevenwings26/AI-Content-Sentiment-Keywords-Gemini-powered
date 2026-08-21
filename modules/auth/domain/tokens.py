# modules/auth/domain/tokens.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class TokenData:
    user_id: str
    org_id: str
    department_id: Optional[str] = None
    role: str = "MEMBER"
    email: Optional[str] = None

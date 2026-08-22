# modules/auth/domain/tokens.py
from dataclasses import dataclass
from typing import Optional

# @dataclass
# class TokenData:
#     user_id: Optional[str]
#     org_id: str
#     department_id: Optional[str] = None
#     role: str = "MEMBER"
#     email: Optional[str] = None


@dataclass
class TokenData:
    user_id: Optional[str] = None
    org_id: str = "default-org"
    department_id: Optional[str] = None
    role: str = "MEMBER"
    email: Optional[str] = None
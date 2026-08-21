# modules/auth/policies.py
from typing import List, Union
from modules.auth.domain.models import UserRole
from modules.auth.domain.tokens import TokenData

def has_role(user: TokenData, allowed_roles: Union[List[str], List[UserRole]]) -> bool:
    role_strings = [r.value if isinstance(r, UserRole) else str(r) for r in allowed_roles]
    return user.role in role_strings

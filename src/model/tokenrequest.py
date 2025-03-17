from typing import Literal, Annotated, Dict, Optional, List
from typing_extensions import TypedDict
from pydantic import BaseModel, Field

class TokenRequest(BaseModel):
    url: str
    headers: Dict[str, str]
    body: Dict[str, str]

class ToolConfig(BaseModel):
    spec_url: str
    description: str
    headers: Optional[Dict[str, str]] = None
    token_req: Optional[TokenRequest] = None
    header_auth: Optional[Dict[str, str]] = None
    body_auth: Optional[Dict[str, str]] = None
    id: str
    
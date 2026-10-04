from pydantic import BaseModel


class MarketplaceAgentOut(BaseModel):
    slug: str
    name: str
    description: str
    category: str
    version: str
    installed: bool


class InstalledAgentOut(BaseModel):
    slug: str
    name: str
    description: str
    category: str
    version_installed: str
    is_enabled: bool

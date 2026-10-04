from pydantic import BaseModel


class HealthStatus(BaseModel):
    status: str
    database: str
    redis: str
    ai_provider: str

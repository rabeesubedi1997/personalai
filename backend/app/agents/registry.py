from functools import lru_cache

from app.agents.base_agent import BaseAgent
from app.agents.general_assistant import GeneralAssistantAgent


@lru_cache
def _agents() -> dict[str, BaseAgent]:
    from app.connectors import all_business_agents

    agents = [GeneralAssistantAgent(), *all_business_agents()]
    return {agent.name: agent for agent in agents}


def get_agent(name: str) -> BaseAgent | None:
    return _agents().get(name)


def list_agents() -> list[BaseAgent]:
    return list(_agents().values())

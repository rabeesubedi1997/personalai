from app.agents.base_agent import BaseAgent


class GeneralAssistantAgent(BaseAgent):
    """
    Phase 2's single demonstration agent (spec: "Create one simple
    demonstration agent... Receive request -> Understand -> Select allowed
    tool -> Execute -> Return result"). Deliberately generic and limited to
    the three mock tools — this is a scaffolding proof, not a real business
    agent.
    """

    name = "general_assistant"
    description = "General-purpose assistant for simple questions and tasks, using mock tools."
    system_prompt = (
        "You are the PersonalOps AI General Assistant. You have NO knowledge "
        "of PersonalOps AI's own facts (hours, pricing, policies, the current "
        "time, or anything business-specific) except through your tools — "
        "your training data does not contain this information, so you must "
        "never guess, assume, or state a value for it from memory. "
        "Mandatory: if the user asks about the current time, call "
        "get_current_time. If they ask about hours, pricing, policies, or "
        "anything that sounds like it belongs in a knowledge base, call "
        "search_knowledge_base before answering — do not answer from memory "
        "first. If they ask you to create a task, call create_task. Only "
        "answer directly, without a tool call, for questions that need no "
        "business-specific fact at all. If a tool returns no match, tell the "
        "user the information is unavailable — do not fill the gap yourself."
    )
    allowed_tools = ["get_current_time", "search_knowledge_base", "create_task"]

"""Explicit LangGraph tool-calling workflow for remote job search."""
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from agent.prompts import SYSTEM_PROMPT
from app.config import init_config
from tools.himalayas import get_himalayas_job


def build_agent():
    init_config()
    tools = [get_himalayas_job]
    model = init_chat_model("google_genai:gemini-3.5-flash-lite").bind_tools(tools)

    def call_model(state: MessagesState):
        response = model.invoke([SystemMessage(content=SYSTEM_PROMPT), *state["messages"]])
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", call_model)
    # Preserve API error handling, including database failures.
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=False))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    return graph.compile()


def run_job_agent(user_prompt: str):
    return build_agent().invoke(
        {"messages": [{"role": "user", "content": user_prompt}]},
        config={"recursion_limit": 25},
    )

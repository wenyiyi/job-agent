from langchain.agents import create_agent

from agent.prompts import SYSTEM_PROMPT
from app.config import init_config
from tools.himalayas import get_himalayas_job


def build_agent():
    init_config()
    agent = create_agent(
        model="google_genai:gemini-3.5-flash-lite",
        tools=[get_himalayas_job],
        system_prompt=SYSTEM_PROMPT,
    )
    return agent


def run_job_agent(user_prompt: str):
    agent = build_agent()
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": user_prompt,
                }
            ]
        }
    )

    return result

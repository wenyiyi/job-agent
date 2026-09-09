from langchain.agents import create_agent

from agent.workflow import run_job_agent


if __name__ == "__main__":
    result = run_job_agent()
    message = result["messages"][-1]
    print(message.content[0]["text"])

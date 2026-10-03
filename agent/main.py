from agent.workflow import run_job_agent


if __name__ == "__main__":
    result = run_job_agent("Find senior backend engineer jobs that hire worldwide.")
    message = result["messages"][-1]
    print(message.content)

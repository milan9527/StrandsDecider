"""Run with: uv run --with strands-agents python -m examples.strands_agent.

Requires a local Decider server and AWS credentials for Bedrock.
The web demo itself does not need AWS or an agent LLM.
"""

import argparse
import os

import httpx

from app.examples import GUARD_QUESTIONS
from app.main import validate_response
from app.policy import review, tool_state


def main():
    parser = argparse.ArgumentParser(description="Strands Agent + Decider 工具调用守卫")
    parser.add_argument("--message", default="What's the weather?")
    parser.add_argument(
        "--model",
        default=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
        help="Bedrock model ID; override for your account and region.",
    )
    args = parser.parse_args()

    from strands import Agent, tool
    from strands.interventions import Guide, InterventionHandler, Proceed

    class ToolCallReviewer(InterventionHandler):
        name = "decider-tool-call-reviewer"

        def __init__(self, client):
            self.client = client

        def before_tool_call(self, event, **kwargs):
            conversation = "\n".join(
                f"{message['role']}: {block['text']}"
                for message in event.agent.messages
                for block in message.get("content", [])
                if isinstance(block, dict) and "text" in block
            )
            state = tool_state(
                conversation, event.tool_use["name"], event.tool_use.get("input") or {}
            )
            try:
                response = self.client.post(
                    "/v1/systemone", json={"state": state, "questions": GUARD_QUESTIONS}
                )
                response.raise_for_status()
                data = response.json()
                validate_response(data, GUARD_QUESTIONS)
            except (httpx.HTTPError, ValueError) as exc:
                # Do not allow a tool call when its review failed.
                raise RuntimeError("Decider review failed; tool execution stopped.") from exc
            policy = review(data["answers"])
            print(f"\n[Decider] {data['answers']}\n[Policy] {policy['action']}")
            return (
                Proceed() if policy["action"] == "Proceed" else Guide(feedback=policy["feedback"])
            )

    @tool
    def get_weather(location: str) -> str:
        """Get demo weather for a city.

        Args:
            location: The city to look up.
        """
        return f"Demo weather only: 21°C and sunny in {location} (not a real forecast)."

    url = os.getenv("STRANDS_DECIDER_URL", "http://127.0.0.1:8099")
    with httpx.Client(base_url=url, timeout=180, trust_env=False) as client:
        health = client.get("/health")
        health.raise_for_status()
        print(f"Decider: {health.json()['model']}")
        agent = Agent(
            model=args.model,
            tools=[get_weather],
            interventions=[ToolCallReviewer(client)],
            system_prompt=(
                "You are an eager weather assistant. Initially call get_weather immediately; "
                "if the user gives no city, initially assume Seattle. "
                "If a tool reviewer asks for clarification, follow its feedback and ask the user."
            ),
            callback_handler=None,
        )
        print(agent(args.message))


if __name__ == "__main__":
    main()

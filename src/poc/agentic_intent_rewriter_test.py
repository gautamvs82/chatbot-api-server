import json
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage


# -------------------------------------------------------------------
# 1. Structured Output Schema
# -------------------------------------------------------------------

class TransitionType(str, Enum):
    CONTINUATION = "CONTINUATION"
    REFINEMENT = "REFINEMENT"
    HARD_SHIFT = "HARD_SHIFT"
    DIGRESSION_START = "DIGRESSION_START"
    DIGRESSION_END = "DIGRESSION_END"


class IntentAnalysis(BaseModel):
    reasoning: str = Field(description="Step-by-step logic analyzing intent shift.")
    transition_type: TransitionType
    active_intent_label: str = Field(description="Snake_case canonical intent label.")
    canonical_user_goal: str = Field(description="Clean, self-contained current target state.")
    extracted_parameters: Dict[str, Any] = Field(default_factory=dict)
    invalidated_parameters: List[str] = Field(default_factory=list)
    intent_stack: List[str]


# -------------------------------------------------------------------
# 2. Ollama Intent Rewriter Integration
# -------------------------------------------------------------------

SYSTEM_PROMPT = """
You are the Intent Orchestrator for an enterprise conversational system.
Analyze the conversation trajectory and output structured JSON.

### INTENT TRANSITION TYPES:
- CONTINUATION: User is continuing the current active goal naturally.
- REFINEMENT: User is modifying, adding, or removing constraints for the SAME underlying goal.
- HARD_SHIFT: User completely abandons the previous goal and starts a new un-related goal.
- DIGRESSION_START: User temporarily interrupts the main task to resolve a side sub-task.
- DIGRESSION_END: User resolves the side sub-task and returns to a previously paused goal on the stack.
"""


class LocalAgenticIntentRewriter:
    def __init__(self, model_name: str = "llama3.2"):
        # Initialize local LLM via Ollama
        base_llm = ChatOllama(
            model=model_name,
            temperature=0.0,
            validate_model_on_init=True
        )
        # Enforce structured output matching the Pydantic model
        self.structured_llm = base_llm.with_structured_output(IntentAnalysis)

    def process_turn(
            self,
            conversation_history: List[Dict[str, str]],
            current_user_input: str,
            current_stack: Optional[List[str]] = None
    ) -> IntentAnalysis:
        user_payload = {
            "intent_stack_before_turn": current_stack or [],
            "conversation_history": conversation_history,
            "latest_user_input": current_user_input
        }

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(user_payload, indent=2))
        ]

        # Invokes local Ollama model and directly returns an IntentAnalysis instance
        return self.structured_llm.invoke(messages)


# -------------------------------------------------------------------
# 3. Execution Example
# -------------------------------------------------------------------

if __name__ == "__main2__":
    rewriter = LocalAgenticIntentRewriter(model_name="llama3.2")

    history = [
        {"role": "user", "content": "Help me draft a PR description for the user auth feature."},
        {"role": "assistant", "content": "Sure! What key changes were introduced?"}
    ]
    latest_input = "Hold on, what docker command checks if Redis is healthy first?"

    result: IntentAnalysis = rewriter.process_turn(
        conversation_history=history,
        current_user_input=latest_input,
        current_stack=["draft_pr_description"]
    )

    print(f"Transition Detected: {result.transition_type}")
    print(f"Canonical Goal: {result.canonical_user_goal}")

# -------------------------------------------------------------------
# 4. Execution Example II
# -------------------------------------------------------------------

if __name__ == "__main2__":
    rewriter = LocalAgenticIntentRewriter(model_name="llama3.2")

    history = [
        {"role": "user", "content": "Hi, I want to change the delivery address for my last order"},
        {"role": "assistant", "content": "Could you please provide the order ID you would like to update?"}
    ]
    latest_input = "The order id is #00001"

    result: IntentAnalysis = rewriter.process_turn(
        conversation_history=history,
        current_user_input=latest_input,
        current_stack=["change_delivery_address"]
    )

    print(f"Transition Detected: {result.transition_type}")
    print(f"Canonical Goal: {result.canonical_user_goal}")

# -------------------------------------------------------------------
# 4. Execution Example III
# -------------------------------------------------------------------

if __name__ == "__main2__":
    rewriter = LocalAgenticIntentRewriter(model_name="llama3.2")

    history = [
        {"role": "user", "content": "Hi, I want to change the delivery address for my last order"},
        {"role": "assistant", "content": "Could you please provide the order ID you would like to update?"},
        {"role": "user", "content": "The order id is #00001"},
        {"role": "assistant", "content": "Could you please provide the new address you would like to update?"}
    ]
    latest_input = "Ok, before that could you please help me diagnose the promo code error"

    result: IntentAnalysis = rewriter.process_turn(
        conversation_history=history,
        current_user_input=latest_input,
        current_stack=["change_delivery_address"]
    )

    print(f"Transition Detected: {result.transition_type}")
    print(f"Canonical Goal: {result.canonical_user_goal}")

# -------------------------------------------------------------------
# 4. Execution Example IV
# -------------------------------------------------------------------

if __name__ == "__main__":
    rewriter = LocalAgenticIntentRewriter(model_name="llama3.2")

    history = [
        {"role": "user", "content": "Hi, I want to change the delivery address for my last order"},
        {"role": "assistant", "content": "Could you please provide the order ID you would like to update?"},
        {"role": "user", "content": "The order id is #00001"},
        {"role": "assistant", "content": "Could you please provide the new address you would like to update?"}
    ]
    latest_input = "Ok, before that could you please provide the status of my last order ?"

    result: IntentAnalysis = rewriter.process_turn(
        conversation_history=history,
        current_user_input=latest_input,
        current_stack=["change_delivery_address"]
    )

    print(f"Transition Detected: {result.transition_type}")
    print(f"Canonical Goal: {result.canonical_user_goal}")
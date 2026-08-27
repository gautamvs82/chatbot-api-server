from enum import Enum
from typing import Any, Dict, List, Optional

from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field


class SlotAction(str, Enum):
    RETAIN = "RETAIN"
    UPDATE = "UPDATE"
    ADD = "ADD"
    DELETE = "DELETE"


class SlotDelta(BaseModel):
    slot_name: str
    action: SlotAction
    prior_value: Optional[Any] = None
    new_value: Optional[Any] = None
    justification: str


class DialogueStateTrackerOutput(BaseModel):
    utterance_analysis: str
    slot_level_deltas: List[SlotDelta]
    updated_dialogue_state: Dict[str, Any]
    system_intent_trigger: str = Field(
        ...,
        description="Action trigger, e.g., 'EXECUTE_SEARCH', 'COLLECT_MISSING_SLOTS'",
    )

class HotelBookingBackendAPI:
    """Mock backend endpoints for the application."""

    @staticmethod
    def execute_search(state: Dict[str, Any]) -> str:
        destination = state.get("destination", "Unknown")
        date = state.get("date", "Flexible date")
        amenities = ", ".join(state.get("amenities", []))
        return (
            f"[API SUCCESS] Executed search for {destination} on {date}. "
            f"Filters: Amenities=[{amenities}], Party Size={state.get('party_size', 1)}."
        )

    @staticmethod
    def collect_missing_slots(state: Dict[str, Any]) -> str:
        missing = []
        for required in ["destination", "date"]:
            if required not in state:
                missing.append(required)
        return f"[SYSTEM PROMPT] Please ask the user to clarify: {', '.join(missing)}."


def route_backend_action(trigger: str, state: Dict[str, Any]) -> str:
    """Routes the updated dialogue state to the appropriate API tool."""
    if trigger == "EXECUTE_SEARCH":
        return HotelBookingBackendAPI.execute_search(state)
    elif trigger == "COLLECT_MISSING_SLOTS":
        return HotelBookingBackendAPI.collect_missing_slots(state)
    else:
        return f"[WARN] Handled fallback action for unmapped trigger: '{trigger}'"


import json

# --- Response Model Schema ---
class AgentResponse(BaseModel):
    reasoning: str = Field(description="Internal logic for what to communicate to the user.")
    user_message: str = Field(description="Natural language response sent to the user.")
    suggested_actions: list[str] = Field(default_factory=list, description="Optional quick-reply options.")

class ScaffoldedDSTWrapper:

    def __init__(
        self,
        system_prompt: str,
        model_name: str = "llama3.1:8b",
    ):
        self.system_prompt = system_prompt
        self.model_name = model_name

    def process_turn(
        self,
        current_state: Dict[str, Any],
        conversation_history: str,
        user_utterance: str,
    ) -> Dict[str, Any]:
        """Runs one dialogue state tracking turn, parses structural output,

        and triggers downstream APIs.
        """
        # Formulate execution prompt with structural variables injected
        execution_input = f"""
[INPUT CONTEXT]
Prior State:
{{prior_state}}

Conversation History:
{conversation_history}
User Turn: "{user_utterance}"

[OUTPUT]
"""
        prior_state = json.dumps(current_state, indent=2)
        print("EXECUTION INPUT:", execution_input)

        # Force strict JSON output adhering to schema
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            ("human", execution_input)
        ])
        # 2. Initialize Ollama LLM with Structured Output
        llm = ChatOllama(model=self.model_name, temperature=0)

        chain = prompt | llm | JsonOutputParser()
        response = chain.invoke({"prior_state": prior_state})

        # 1. Validate raw output against Pydantic structural scaffold
        parsed_dst: DialogueStateTrackerOutput = (
            DialogueStateTrackerOutput.model_validate(response)
        )

        # 2. Extract updated dialogue state
        updated_state = parsed_dst.updated_dialogue_state

        # 3. Route to backend execution API based on intent trigger
        api_result = route_backend_action(
            trigger=parsed_dst.system_intent_trigger, state=updated_state
        )

        return {
            "analysis": parsed_dst.utterance_analysis,
            "slot_deltas": [d.model_dump() for d in parsed_dst.slot_level_deltas],
            "updated_state": updated_state,
            "system_intent_trigger": parsed_dst.system_intent_trigger,
            "api_execution_result": api_result,
        }

    def generate_response(
                self,
                conversation_history: str,
                user_utterance: str,
                updated_state: Dict[str, Any],
                system_intent: str,
                api_result: str
        ) -> AgentResponse:
            """Generates a natural language response to the user based on the state update

            and API execution outcomes.
            """
            response_system_prompt = """
    You are a helpful customer support agent for a hotel booking platform.
    Your task is to craft a natural, concise, and helpful response to the user.

    You will be provided with:
    1. Current Dialogue State (active parameters)
    2. System Intent Trigger (what action was taken)
    3. API Execution Result (data returned from the backend)
    4. Conversation Context

    Guidelines:
    - If 'system_intent' is 'COLLECT_MISSING_SLOTS', politely ask for the missing details.
    - If 'system_intent' is 'EXECUTE_SEARCH', summarize the API results and present options.
    - Maintain a warm, efficient tone. Do not expose internal JSON keys directly.
    """

            prompt_input = f"""
    [CONVERSATION HISTORY]
    {conversation_history}
    User Turn: "{user_utterance}"

    [SYSTEM STATE & API DATA]
    Updated State: {{updated_state}}
    System Intent: {system_intent}
    API Execution Result: {api_result}
    """
            # Force strict JSON output adhering to schema
            prompt = ChatPromptTemplate.from_messages([
                ("system", response_system_prompt),
                ("human", prompt_input)
            ])
            # 2. Initialize Ollama LLM with Structured Output
            llm = ChatOllama(model=self.model_name, temperature=0.7)

            chain = prompt | llm | StrOutputParser()
            response = chain.invoke({"updated_state": json.dumps(updated_state)})
            return AgentResponse.model_validate_json(response)

    def process_turn_and_respond(
            self,
            current_state: Dict[str, Any],
            conversation_history: str,
            user_utterance: str
    ) -> Dict[str, Any]:
        """Runs DST turn, executes API logic, and generates natural language response."""

        # 1. Run Dialogue State Tracking & API Call (from previous step)
        dst_result = self.process_turn(current_state, conversation_history, user_utterance)

        # 2. Generate Natural Language Response based on API + State Results
        agent_reply = self.generate_response(
            conversation_history=conversation_history,
            user_utterance=user_utterance,
            updated_state=dst_result["updated_state"],
            system_intent=dst_result["system_intent_trigger"],
            api_result=dst_result["api_execution_result"]
        )

        return {
            "dst_analysis": dst_result,
            "final_user_message": agent_reply.user_message,
            "reasoning": agent_reply.reasoning
        }

# System prompt defined in previous step
fpr = open("./resources/scaffolding_dst_test_prompt.txt")
SYSTEM_PROMPT_TEMPLATE = fpr.read()
fpr.close()

# Initialize wrapper
dst_engine = ScaffoldedDSTWrapper(
    system_prompt=SYSTEM_PROMPT_TEMPLATE
)

# Initial State prior to turn
session_state = {
    "destination": "Chicago",
    "date": "2026-09-12",
    "party_size": 2,
}

history = "User: Book a hotel in Chicago for Sept 12 for 2 people.\nSystem: Searching hotels in Chicago..."
"""
user_input = (
    "Can you make that Sept 15th instead and ensure there's free parking?"
)
"""
user_input = (
    "Can you make that Sept 15th instead and ensure there's free parking?"
)

# Run execution turn
result = dst_engine.process_turn_and_respond(
    current_state=session_state,
    conversation_history=history,
    user_utterance=user_input,
)

# Output summary
print("--- Result ---")
print(json.dumps(result, indent=2))


"""
# Run execution turn
result = dst_engine.process_turn(
    current_state=session_state,
    conversation_history=history,
    user_utterance=user_input,
)

# Output summary
print("--- Extracted State Delta ---")
print(json.dumps(result["slot_deltas"], indent=2))

print("\n--- Updated State Payload ---")
print(json.dumps(result["updated_state"], indent=2))

print("\n--- Backend Trigger Result ---")
print(result["api_execution_result"])
"""
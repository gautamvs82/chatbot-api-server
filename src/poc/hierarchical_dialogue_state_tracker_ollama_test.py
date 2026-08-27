import json
from enum import Enum

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator


# -------------------------------------------------------------------
# 1. Enums and Domain States
# -------------------------------------------------------------------

class TaskStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    COLLECTING_SLOTS = "COLLECTING_SLOTS"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    READY_FOR_EXECUTION = "READY_FOR_EXECUTION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TrackDeliveryDelaySlots(BaseModel):
    status: TaskStatus = TaskStatus.NOT_STARTED
    delay_reason: Optional[str] = None
    revised_eta: Optional[str] = None
    compensation_offered: bool = False


class PromoCodeErrorSlots(BaseModel):
    status: TaskStatus = TaskStatus.NOT_STARTED
    promo_code: Optional[str] = None
    error_type: Optional[str] = None  # e.g., "EXPIRED", "MIN_BASKET_NOT_MET"
    manual_override_applied: bool = False


class ChangeDeliveryAddressSlots(BaseModel):
    status: TaskStatus = TaskStatus.NOT_STARTED
    new_street: Optional[str] = None
    new_postal_code: Optional[str] = None
    is_address_eligible_for_change: Optional[bool] = None  # Depends on order shipment status

# -------------------------------------------------------------------
# 2. NonHierarchical State Container
# -------------------------------------------------------------------

class NonHierarchicalGlobalDST(BaseModel):
    # --- Layer 1: Session Meta-State ---
    active_intents: List[str] = Field(default_factory=list)
    primary_focus_intent: Optional[str] = None
    blocked_intents: List[str] = Field(default_factory=list)

    # --- Layer 2: Shared Global Context ---
    global_order_id: Optional[str] = Field(None, description="Shared across all 3 domains")
    user_authenticated: bool = False

    # --- Layer 3: Task-Specific States ---
    track_delivery_delay: TrackDeliveryDelaySlots = Field(default_factory=TrackDeliveryDelaySlots)
    promo_code_errors: PromoCodeErrorSlots = Field(default_factory=PromoCodeErrorSlots)
    change_delivery_address: ChangeDeliveryAddressSlots = Field(default_factory=ChangeDeliveryAddressSlots)

    @model_validator(mode="after")
    def resolve_domain_cross_dependencies(self) -> "NonHierarchicalGlobalDST":
        """
        Executes operational logic across independent domains:
        1. If delivery address change fails (e.g., item already shipped),
           automatically surface promo/compensation options.
        2. Set priority intent dynamically based on task lifecycle.
        """
        # Rule 1: Lock address change if order is already out for delivery
        if self.change_delivery_address.is_address_eligible_for_change is False:
            if "CHANGE_DELIVERY_ADDRESS" in self.active_intents:
                self.active_intents.remove("CHANGE_DELIVERY_ADDRESS")
                self.blocked_intents.append("CHANGE_DELIVERY_ADDRESS")
                self.change_delivery_address.status = TaskStatus.FAILED

        # Rule 2: Automatically prioritize PROMO_CODE_ERRORS if delay compensation is triggered
        if self.track_delivery_delay.compensation_offered and "PROMO_CODE_ERRORS" not in self.active_intents:
            self.active_intents.append("PROMO_CODE_ERRORS")
            self.promo_code_errors.status = TaskStatus.COLLECTING_SLOTS

        return self


def update_dst_state_ollama(
        current_state: NonHierarchicalGlobalDST,
        user_utterance: str,
        system_prompt: str,
        model_name: str = "llama3.1:8b"
) -> NonHierarchicalGlobalDST:
    """
    Executes DST updating locally using an Ollama model via LangChain.
    """
    # 1. Initialize local ChatOllama LLM
    base_llm = ChatOllama(
        model=model_name,
        temperature=0.0,  # Zero temperature for deterministic extraction
        validate_model_on_init=True
    )

    # 2. Bind the Pydantic schema for structured output validation
    structured_llm = base_llm.with_structured_output(NonHierarchicalGlobalDST)

    # 3. Construct input payload matching the prompt design
    payload = {
        "current_state_frame": current_state.model_dump(),
        "latest_user_utterance": user_utterance
    }

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(payload, indent=2))
    ]

    # 4. Invoke local model and return instantiated Pydantic object
    updated_state: NonHierarchicalGlobalDST = structured_llm.invoke(messages)
    return updated_state


def generate_response_from_state(
        state: NonHierarchicalGlobalDST,
        user_utterance: str,
        model_name: str = "llama3.1:8b"
) -> str:
    """
    Generates a user response after backend APIs have updated the state frame.
    """
    llm = ChatOllama(model=model_name, temperature=0.3)

    prompt = f"""
    You are an e-commerce support assistant.

    Current Processed State:
    - Primary Intent: {state.primary_focus_intent}
    - Order ID: {state.global_order_id}
    - Active Tasks: {state.active_intents}
    - Blocked Tasks: {state.blocked_intents}
    - Track Delivery Delay Attributes: {state.track_delivery_delay.model_dump()}
    - Change Delivery Address Attributes: {state.change_delivery_address.model_dump()}
    - Promo Code Errors Attributes: {state.promo_code_errors.model_dump()}

    User Input: "{user_utterance}"

    Write a helpful, concise response to the user explaining what actions are being taken or requested.
    """

    response = llm.invoke(prompt)
    return response.content

# -------------------------------------------------------------------
# Simulation Example with Local Ollama Model
# -------------------------------------------------------------------
if __name__ == "__main__":
    # Initialize empty state frame
    initial_state = NonHierarchicalGlobalDST()

    user_input = "Hi, my order ORD-88392 is delayed. Can I change the address to 100 Main St, 10001?"

    fpr = open("./resources/hierarchical_dialogue_state_tracker_e_comm_system_prompt.txt", "r")
    system_prompt = fpr.read()
    fpr.close()
    """
    print("SYSTEM PROMPT")
    print(system_prompt)
    """

    # Execute state update locally
    updated_state = update_dst_state_ollama(
        current_state=initial_state,
        user_utterance=user_input,
        system_prompt=system_prompt,
        model_name="llama3.1:8b"  # Requires: `ollama pull llama3.2`
    )

    print("Primary Intent:", updated_state.primary_focus_intent)
    print("Order ID:", updated_state.global_order_id)
    print("Change Delivery Address Status:", updated_state.change_delivery_address.status)

    #External API Call Simulation
    updated_state.change_delivery_address.is_address_eligible_for_change = False
    updated_state.change_delivery_address.status = TaskStatus.FAILED
    print("Updated state post API call:", updated_state.model_dump())

    #Response based on the above
    response = generate_response_from_state(updated_state, user_utterance=user_input, model_name="llama3.1:8b")
    print("response:", response)
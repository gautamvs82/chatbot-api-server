import json
import sys
from enum import Enum
from typing import List, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

class TaskStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    COLLECTING_SLOTS = "COLLECTING_SLOTS"
    CHECKING_WITH_BACKEND = "CHECKING_WITH_BACKEND"
    READY_FOR_EXECUTION = "READY_FOR_EXECUTION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TrackDeliveryDelaySlots(BaseModel):
    status: TaskStatus = TaskStatus.NOT_STARTED
    order_id: Optional[str] = None

class ChangeDeliveryAddressSlots(BaseModel):
    status: TaskStatus = TaskStatus.NOT_STARTED
    new_address: Optional[str] = None
    is_address_eligible_for_change: Optional[bool] = None  # Depends on order shipment status

class PromoCodeErrorSlots(BaseModel):
    status: TaskStatus = TaskStatus.NOT_STARTED
    promo_code: Optional[str] = None

class SupportChatBotState(BaseModel):
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

class SupportChatBot(object):
    def __init__(self):
        self.conversation_history = []
        self.current_state = SupportChatBotState()
        self.prev_state = self.current_state.model_copy(deep=True)
        self.model_name = "llama3.1:8b"
        self.base_llm = ChatOllama(
            model=self.model_name,
            temperature=0.0,
            validate_model_on_init=True,
            keep_alive="30m",
        )
        self.UPDATE_STATE_PROMPT_FILE_NAME= "./resources/dst_ecommerce_support_chatbot_prompt.txt"

    def update_state(self, user_message):
        print("Prev state:", self.prev_state.model_dump())
        print("Current state:", self.current_state.model_dump())
        print("Processing message:", user_message)

        structured_llm = self.base_llm.with_structured_output(SupportChatBotState)
        first_response = SupportChatBotState()
        first_response.active_intents.append("PROMO_CODE_ERRORS")
        first_response.primary_focus_intent = "PROMO_CODE_ERRORS"
        first_response.promo_code_errors.status = TaskStatus.COLLECTING_SLOTS

        fpr = open(self.UPDATE_STATE_PROMPT_FILE_NAME, "r")
        system_prompt = fpr.read()
        fpr.close()

        payload = {
            "current_state_frame": self.current_state.model_dump(),
            "latest_user_utterance": user_message
        }

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=json.dumps(payload, indent=2))
        ]

        # 4. Invoke local model and return instantiated Pydantic object
        updated_state: SupportChatBotState = structured_llm.invoke(messages)
        print("Message is processed.")
        print("Updated state:", updated_state.model_dump())
        return updated_state

    def validate_and_correct(self, updated_state):
        if self.current_state.primary_focus_intent == "PROMO_CODE_ERRORS":
            if self.current_state.promo_code_errors.status == TaskStatus.COLLECTING_SLOTS and self.current_state.promo_code_errors.promo_code is not None:
                self.current_state.promo_code_errors.status = TaskStatus.CHECKING_WITH_BACKEND
        self.prev_state = self.current_state
        self.current_state = updated_state
        print("Post validation and correction")
        return None

    def get_promo_code_policy(self, promo_code):
        policy_details = {
            "promo_code": promo_code,
            "expiry_date": "2026-12-31",
            "minimum_cart_value": 1000
        }
        if promo_code == "WINTER10":
            policy_details["minimum_cart_value"] = 1500
        return policy_details

    def get_cart_value(self):
        return 1200

    def generate_responses(self):
        responses = []
        if self.current_state.primary_focus_intent == "PROMO_CODE_ERRORS":
            if self.current_state.promo_code_errors.status == TaskStatus.COLLECTING_SLOTS and self.current_state.promo_code_errors.promo_code is None:
                responses.append("Could you please share the promo code ?")
            if self.current_state.promo_code_errors.status == TaskStatus.CHECKING_WITH_BACKEND:
                responses.append("I'm checking with the backend ...")
                promo_code_policy = self.get_promo_code_policy(self.current_state.promo_code_errors.promo_code)
                print("promo_code_policy:", promo_code_policy)
                cart_value = self.get_cart_value()
                self.current_state.promo_code_errors.status = TaskStatus.READY_FOR_EXECUTION
                print("cart_value:", cart_value)
                if cart_value < promo_code_policy["minimum_cart_value"]:
                    responses.append("Your cart value is lower than the promo code policy. Please add %d rupees worth of more items." % (promo_code_policy["minimum_cart_value"]-cart_value))
                self.current_state.promo_code_errors.status = TaskStatus.COMPLETED
        return responses

    def respond(self, user_message):
        updated_state = self.update_state(user_message)
        self.validate_and_correct(updated_state)
        bot_response = self.generate_responses()
        self.conversation_history.append(bot_response)
        return bot_response

if __name__ == '__main__':
    support_chatbot = SupportChatBot()
    user_message = "I’m getting an error while applying promo code"
    print("User: ", user_message)
    #user_message = sys.stdin.readline().strip()
    bot_responses = support_chatbot.respond(user_message)
    for bot_response in bot_responses:
        print("Bot: ", bot_response)

    user_message = "The promo code is WINTER10"
    print("User: ", user_message)
    bot_responses = support_chatbot.respond(user_message)
    for bot_response in bot_responses:
        print("Bot: ", bot_response)
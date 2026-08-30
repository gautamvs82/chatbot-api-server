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
    order_id: Optional[str] = None
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
        self.model_name = "llama3.1:8b"
        self.base_llm = ChatOllama(
            model=self.model_name,
            temperature=0.0,
            validate_model_on_init=True,
            keep_alive="30m",
        )
        self.UPDATE_STATE_PROMPT_FILE_NAME= "./resources/dst_ecommerce_support_chatbot_prompt.txt"

    def update_state(self, user_message):
        print("Current state:", self.current_state.model_dump_json(indent=2))
        print("Processing message:", user_message)

        structured_llm = self.base_llm.with_structured_output(SupportChatBotState, method="json_mode")

        fpr = open(self.UPDATE_STATE_PROMPT_FILE_NAME, "r")
        system_prompt = fpr.read()
        fpr.close()
        conversation_history = " ".join(map(lambda x: "%s: %s" % (x[0], x[1]), self.conversation_history[:6]))
        state_json = self.current_state.model_dump_json(indent=2)

        # Build formatted text cleanly
        raw_message = (
            f"[PRIOR STATE]:\n{state_json}\n\n"
            f'Conversation History: "{conversation_history}"\n'
            f'User Turn: "{user_message}"'
        )

        # Convert raw newlines into standard escaped sequence or normalize
        human_message = raw_message.encode('utf-8').decode('unicode_escape')
        print("human_message:", human_message)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_message)
        ]

        # 4. Invoke local model and return instantiated Pydantic object
        updated_state: SupportChatBotState = structured_llm.invoke(messages)
        print("Message is processed.")
        print("Updated state:", updated_state.model_dump_json(indent=2))
        return updated_state

    def validate_and_correct(self, updated_state):
        if updated_state.primary_focus_intent == "PROMO_CODE_ERRORS":
            if updated_state.promo_code_errors.status == TaskStatus.NOT_STARTED:
                updated_state.promo_code_errors.status = TaskStatus.COLLECTING_SLOTS
            if (updated_state.promo_code_errors.status == TaskStatus.COLLECTING_SLOTS and
                    updated_state.promo_code_errors.promo_code is not None):
                updated_state.promo_code_errors.status = TaskStatus.CHECKING_WITH_BACKEND
        elif updated_state.primary_focus_intent == "CHANGE_DELIVERY_ADDRESS":
            if updated_state.change_delivery_address.status == TaskStatus.NOT_STARTED:
                updated_state.change_delivery_address.status = TaskStatus.COLLECTING_SLOTS
            if (updated_state.change_delivery_address.status == TaskStatus.COLLECTING_SLOTS and
                    updated_state.change_delivery_address.order_id is not None and
                    updated_state.change_delivery_address.new_address is not None):
                updated_state.change_delivery_address.status = TaskStatus.CHECKING_WITH_BACKEND
        else:
            pass
        self.current_state = updated_state
        print("Post validation and correction")
        print("Current state:", self.current_state.model_dump_json(indent=2))
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

    def is_eligibile_for_address_change(self, order_id):
        return True, None

    def update_delivery_address(self, order_id, new_address):
        return True

    def generate_responses(self):
        responses = []
        if self.current_state.primary_focus_intent == "PROMO_CODE_ERRORS":
            if self.current_state.promo_code_errors.status == TaskStatus.COLLECTING_SLOTS:
                if self.current_state.promo_code_errors.promo_code is None:
                    responses.append("Could you please share the promo code ?")
                else:
                    self.current_state.promo_code_errors.status = TaskStatus.CHECKING_WITH_BACKEND
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
        elif self.current_state.primary_focus_intent == "CHANGE_DELIVERY_ADDRESS":
            if self.current_state.change_delivery_address.status == TaskStatus.COLLECTING_SLOTS:
                missing_fields = []
                if self.current_state.change_delivery_address.order_id is None:
                    missing_fields.append("order id")
                if self.current_state.change_delivery_address.new_address is None:
                    missing_fields.append("delivery address")
                if missing_fields:
                    responses.append("Could you please share %s ?" % " and ".join(missing_fields))
                else:
                    self.current_state.change_delivery_address.status = TaskStatus.CHECKING_WITH_BACKEND

            if self.current_state.change_delivery_address.status == TaskStatus.CHECKING_WITH_BACKEND:
                responses.append("I'm checking with the backend ...")
                (is_eligible, reason) = self.is_eligibile_for_address_change(self.current_state.change_delivery_address.order_id)
                self.current_state.change_delivery_address.is_address_eligible_for_change = is_eligible
                if is_eligible:
                    responses.append("Your order is eligible for the address change.")
                    self.current_state.change_delivery_address.status = TaskStatus.READY_FOR_EXECUTION
                    responses.append("Updating the delivery address...")
                    address_updated = self.update_delivery_address(order_id=self.current_state.change_delivery_address.order_id,
                                                    new_address=self.current_state.change_delivery_address.new_address)
                    if address_updated:
                        responses.append("Your address has been updated.")
                    else:
                        responses.append("Your address updation encountered an error. Backend team is looking into it...")
                    self.current_state.change_delivery_address.status = TaskStatus.COMPLETED
                    self.current_state.active_intents.remove("CHANGE_DELIVERY_ADDRESS")
                else:
                    responses.append("Your order is not eligible for the address change as %s." % reason)
                    self.current_state.change_delivery_address.status = TaskStatus.FAILED
                    self.current_state.active_intents.remove("CHANGE_DELIVERY_ADDRESS")
                    self.current_state.blocked_intents.append("CHANGE_DELIVERY_ADDRESS")

        print("Post generating responses")
        print("Current state:", self.current_state.model_dump_json(indent=2))
        return responses

    def respond(self, user_message):
        updated_state = self.update_state(user_message)
        self.validate_and_correct(updated_state)
        bot_responses = self.generate_responses()
        self.conversation_history.append(("User", user_message))
        for bot_response in bot_responses:
            self.conversation_history.append(("System", bot_response))
        return bot_responses

if __name__ == '__main2__':
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

if __name__ == '__main__':
    support_chatbot = SupportChatBot()
    user_message = "I want to change the delivery address for my last order"
    print("User: ", user_message)
    #user_message = sys.stdin.readline().strip()
    bot_responses = support_chatbot.respond(user_message)
    for bot_response in bot_responses:
        print("Bot: ", bot_response)

    user_message = "My order id is ORD#20260829113300 and the new address is Satyam Park, 80 Feet Road, Rajkot 360003"
    print("User: ", user_message)
    bot_responses = support_chatbot.respond(user_message)
    for bot_response in bot_responses:
        print("Bot: ", bot_response)


if __name__ == '__main3__':
    support_chatbot = SupportChatBot()
    user_message = "I want to change the delivery address for my last order"
    print("User: ", user_message)
    #user_message = sys.stdin.readline().strip()
    bot_responses = support_chatbot.respond(user_message)
    for bot_response in bot_responses:
        print("Bot: ", bot_response)

    user_message = "Could you please help me diagnose promo code errors first ?"
    print("User: ", user_message)
    # user_message = sys.stdin.readline().strip()
    bot_responses = support_chatbot.respond(user_message)
    for bot_response in bot_responses:
        print("Bot: ", bot_response)


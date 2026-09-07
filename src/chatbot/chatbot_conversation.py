import time
from datetime import datetime
from enum import Enum
from typing import List, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

from .relational_database import RelationalDatabase

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


class ChatBotConversation:
    def __init__(self):
        self.relational_database = RelationalDatabase.get_instance()
        self.conversation_history = []
        self.current_state = SupportChatBotState()
        self.model_name = "llama3.1:8b"
        self.base_llm = ChatOllama(
            model=self.model_name,
            temperature=0.0,
            validate_model_on_init=True,
            keep_alive="30m",
        )
        self.UPDATE_STATE_PROMPT_FILE_NAME = "./resources/dst_ecommerce_support_chatbot_prompt.txt"

    def create(self, username):
        now = datetime.now()
        conversation_id = f"CONV#{now.strftime("%Y%m%d%H%M%S")}"
        created_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        if self.relational_database.insert_conversation(username, conversation_id, created_at):
            return conversation_id
        else:
            return None

    def get_status(self, username, conversation_id):
        return self.relational_database.get_conversation_status(username, conversation_id)

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
        self.conversation_history.append(("User", user_message))
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
        if not self.relational_database.update_conversation_state(self.current_state):
            print("Failed to update conversation state.")
        print("Post validation and correction")
        print("Current state:", self.current_state.model_dump_json(indent=2))
        return None

    def generate_message_update(self, username, conversation_id, message):
        time_epoch = int(time.time()*1000000)
        now = datetime.now()
        message_update = {
                            "event": "message-update",
                            "data": {
                                "username": f"{username}",
                                "conversation_id": f"{conversation_id}",
                                "message_id": f"sys-msg-{time_epoch}-0",
                                "message": message,
                                "sent_at": f"{now.strftime("%Y-%m-%dT%H:%M:%SZ")}"
                            }
                        }
        return message_update

    def generate_message_complete(self, username, conversation_id):
        message_complete = {
                            "event": "message-complete",
                            "data": {
                                "username": f"{username}",
                                "conversation_id": f"{conversation_id}",
                                "status": "done"
                            }
                        }
        return message_complete

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

    async def generate_responses(self, username, conversation_id):
        if self.current_state.primary_focus_intent == "PROMO_CODE_ERRORS":
            if self.current_state.promo_code_errors.status == TaskStatus.COLLECTING_SLOTS:
                if self.current_state.promo_code_errors.promo_code is None:
                    response_message = "Could you please share the promo code ?"
                    self.conversation_history.append(("System", response_message))
                    yield self.generate_message_update(username=username,
                                                       conversation_id=conversation_id,
                                                       message=response_message)

                else:
                    self.current_state.promo_code_errors.status = TaskStatus.CHECKING_WITH_BACKEND
                    if not self.relational_database.update_conversation_state(self.current_state):
                        print("Failed to update conversation state.")

            if self.current_state.promo_code_errors.status == TaskStatus.CHECKING_WITH_BACKEND:
                response_message = "I'm checking with the backend ..."
                self.conversation_history.append(("System", response_message))
                yield self.generate_message_update(username=username,
                                                   conversation_id=conversation_id,
                                                   message=response_message)
                promo_code_policy = self.get_promo_code_policy(self.current_state.promo_code_errors.promo_code)
                print("promo_code_policy:", promo_code_policy)
                cart_value = self.get_cart_value()
                self.current_state.promo_code_errors.status = TaskStatus.READY_FOR_EXECUTION
                if not self.relational_database.update_conversation_state(self.current_state):
                    print("Failed to update conversation state.")
                print("cart_value:", cart_value)
                if cart_value < promo_code_policy["minimum_cart_value"]:
                    response_message = "Your cart value is lower than the promo code policy. Please add %d rupees worth of more items." % (promo_code_policy["minimum_cart_value"]-cart_value)
                    self.conversation_history.append(("System", response_message))
                    yield self.generate_message_update(username=username,
                                                       conversation_id=conversation_id,
                                                       message=response_message)
                self.current_state.promo_code_errors.status = TaskStatus.COMPLETED
                if not self.relational_database.update_conversation_state(self.current_state):
                    print("Failed to update conversation state.")
        elif self.current_state.primary_focus_intent == "CHANGE_DELIVERY_ADDRESS":
            if self.current_state.change_delivery_address.status == TaskStatus.COLLECTING_SLOTS:
                missing_fields = []
                if self.current_state.change_delivery_address.order_id is None:
                    missing_fields.append("order id")
                if self.current_state.change_delivery_address.new_address is None:
                    missing_fields.append("delivery address")
                if missing_fields:
                    response_message = "Could you please share %s ?" % " and ".join(missing_fields)
                    self.conversation_history.append(("System", response_message))
                    yield self.generate_message_update(username=username,
                                                       conversation_id=conversation_id,
                                                       message=response_message)
                else:
                    self.current_state.change_delivery_address.status = TaskStatus.CHECKING_WITH_BACKEND
                    if not self.relational_database.update_conversation_state(self.current_state):
                        print("Failed to update conversation state.")

            if self.current_state.change_delivery_address.status == TaskStatus.CHECKING_WITH_BACKEND:
                response_message = "I'm checking with the backend ..."
                self.conversation_history.append(("System", response_message))
                yield self.generate_message_update(username=username,
                                                   conversation_id=conversation_id,
                                                   message=response_message)
                time.sleep(1.0)
                (is_eligible, reason) = self.is_eligibile_for_address_change(self.current_state.change_delivery_address.order_id)
                self.current_state.change_delivery_address.is_address_eligible_for_change = is_eligible
                if not self.relational_database.update_conversation_state(self.current_state):
                    print("Failed to update conversation state.")
                if is_eligible:
                    response_message = "Your address eligible for address change."
                    self.conversation_history.append(("System", response_message))
                    yield self.generate_message_update(username=username,
                                                       conversation_id=conversation_id,
                                                       message=response_message)
                    self.current_state.change_delivery_address.status = TaskStatus.READY_FOR_EXECUTION
                    response_message = "Updating the delivery address..."
                    self.conversation_history.append(("System", response_message))
                    yield self.generate_message_update(username=username,
                                                       conversation_id=conversation_id,
                                                       message=response_message)
                    time.sleep(1.0)
                    address_updated = self.update_delivery_address(order_id=self.current_state.change_delivery_address.order_id,
                                                    new_address=self.current_state.change_delivery_address.new_address)
                    if address_updated:
                        responses_message = "Your address has been updated."
                    else:
                        responses_message = "Your address update encountered an error. Backend team is looking into it..."
                    self.conversation_history.append(("System", responses_message))
                    yield self.generate_message_update(username=username,
                                                       conversation_id=conversation_id,
                                                       message=responses_message)
                    self.current_state.change_delivery_address.status = TaskStatus.COMPLETED
                    self.current_state.active_intents.remove("CHANGE_DELIVERY_ADDRESS")
                    if not self.relational_database.update_conversation_state(self.current_state):
                        print("Failed to update conversation state.")
                else:
                    response_message = "Your order is not eligible for the address change as %s." % reason
                    self.conversation_history.append(("System", response_message))
                    yield self.generate_message_update(username=username,
                                                       conversation_id=conversation_id,
                                                       message=response_message)
                    self.current_state.change_delivery_address.status = TaskStatus.FAILED
                    self.current_state.active_intents.remove("CHANGE_DELIVERY_ADDRESS")
                    self.current_state.blocked_intents.append("CHANGE_DELIVERY_ADDRESS")
                    if not self.relational_database.update_conversation_state(self.current_state):
                        print("Failed to update conversation state.")

        yield self.generate_message_complete(username=username,
                                             conversation_id=conversation_id)

    def update(self, username, conversation_id, message):
        initial_data = self.relational_database.get_conversation_state(username=username,
                                                                       conversation_id=conversation_id)
        state = SupportChatBotState()
        self.current_state = state.model_copy(update=initial_data, deep=True)
        updated_state = self.update_state(message)
        self.validate_and_correct(updated_state)


if __name__ == "__main__":
    conversation = ChatBotConversation()
    username = "jerry.mouse"
    print(conversation.create(username))
import json
import time
from datetime import datetime

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_ollama import ChatOllama

from .data_model import TaskStatus, ChatBotState
from .relational_database import RelationalDatabase

class ChatBotConversation:
    def __init__(self):
        self.relational_database = RelationalDatabase.get_instance()
        self.conversation_history = []
        self.current_chat_bot_state = ChatBotState()
        self.model_name = "llama3.2:3b"
        self.base_llm = ChatOllama(
            model=self.model_name,
            temperature=0.0,
            validate_model_on_init=True,
            keep_alive="30m",
        )
        self.UPDATE_STATE_PROMPT_FILE_NAME = "./resources/dst_ecommerce_support_chatbot_prompt.txt"

    def create(self, username):
        now = datetime.now()
        dt_formatted = now.strftime("%Y%m%d%H%M%S")
        conversation_id = f"CONV#{dt_formatted}"
        created_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        if self.relational_database.insert_conversation(username, conversation_id, created_at):
            return conversation_id
        else:
            return None

    def get_status(self, username, conversation_id):
        return self.relational_database.get_conversation_status(username, conversation_id)

    def update_chat_bot_state(self, username, conversation_id, user_message, message_id, sent_at):
        print("Current state:", self.current_chat_bot_state.model_dump_json(indent=2))
        print("Processing message:", user_message)

        structured_llm = self.base_llm.with_structured_output(ChatBotState, method="json_mode")

        fpr = open(self.UPDATE_STATE_PROMPT_FILE_NAME, "r")
        system_prompt = fpr.read()
        fpr.close()
        conversation_history = " ".join(map(lambda x: "%s: %s" % (x[0], x[1]), self.conversation_history[:6]))
        state_json = self.current_chat_bot_state.model_dump_json(indent=2)

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
        updated_state: ChatBotState = structured_llm.invoke(messages)
        print("Message is processed.")
        self.conversation_history.append(("User", user_message))
        message_data = {
            "message_id": message_id,
            "sender": "User",
            "message": user_message,
            "sent_at": sent_at
        }
        self.relational_database.add_message(username, conversation_id, message_data)
        print("Updated state:", updated_state.model_dump_json(indent=2))
        return updated_state

    def validate_and_correct(self, username, conversation_id, updated_chat_bot_state):
        if updated_chat_bot_state.primary_focus_intent == "PROMO_CODE_ERRORS":
            if updated_chat_bot_state.promo_code_errors.status == TaskStatus.NOT_STARTED:
                updated_chat_bot_state.promo_code_errors.status = TaskStatus.COLLECTING_SLOTS
            if (updated_chat_bot_state.promo_code_errors.status == TaskStatus.COLLECTING_SLOTS and
                    updated_chat_bot_state.promo_code_errors.promo_code is not None):
                updated_chat_bot_state.promo_code_errors.status = TaskStatus.CHECKING_WITH_BACKEND
        elif updated_chat_bot_state.primary_focus_intent == "CHANGE_DELIVERY_ADDRESS":
            if updated_chat_bot_state.change_delivery_address.status == TaskStatus.NOT_STARTED:
                updated_chat_bot_state.change_delivery_address.status = TaskStatus.COLLECTING_SLOTS
            if (updated_chat_bot_state.change_delivery_address.status == TaskStatus.COLLECTING_SLOTS and
                    updated_chat_bot_state.change_delivery_address.order_id is not None and
                    updated_chat_bot_state.change_delivery_address.new_address is not None):
                updated_chat_bot_state.change_delivery_address.status = TaskStatus.CHECKING_WITH_BACKEND
        else:
            pass
        self.current_chat_bot_state = updated_chat_bot_state
        if not self.relational_database.update_chat_bot_state(username, conversation_id, self.current_chat_bot_state):
            print("Failed to update conversation state.")
        print("Post validation and correction")
        print("Current state:", self.current_chat_bot_state.model_dump_json(indent=2))
        return None

    def generate_message_update(self, username, conversation_id, message):
        time_epoch = int(time.time()*1000000)
        now = datetime.now()
        sent_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        message_data = {
            "message_id": f"sys-msg-{time_epoch}-0",
            "message": message,
            "sender": "System",
            "sent_at": sent_at
        }
        self.relational_database.add_message(username, conversation_id, message_data)
        message_update = {
            "event": "message-update",
            "data": {
                "username": username,
                "conversation_id": conversation_id,
                "message_id": f"sys-msg-{time_epoch}-0",
                "message": message,
                "sent_at": sent_at
            }
        }
        return json.dumps(message_update)

    def generate_message_complete(self, username, conversation_id):
        message_complete = {
            "event": "message-complete",
            "data": {
                "username": username,
                "conversation_id": conversation_id,
                "status": "done"
            }
        }
        return json.dumps(message_complete)

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
        if self.current_chat_bot_state.primary_focus_intent == "PROMO_CODE_ERRORS":
            if self.current_chat_bot_state.promo_code_errors.status == TaskStatus.COLLECTING_SLOTS:
                if self.current_chat_bot_state.promo_code_errors.promo_code is None:
                    response_message = "Could you please share the promo code ?"
                    self.conversation_history.append(("System", response_message))
                    yield self.generate_message_update(username=username,
                                                       conversation_id=conversation_id,
                                                       message=response_message)

                else:
                    self.current_chat_bot_state.promo_code_errors.status = TaskStatus.CHECKING_WITH_BACKEND
                    if not self.relational_database.update_chat_bot_state(username, conversation_id, self.current_chat_bot_state):
                        print("Failed to update conversation state.")

            if self.current_chat_bot_state.promo_code_errors.status == TaskStatus.CHECKING_WITH_BACKEND:
                response_message = "I'm checking with the backend ..."
                self.conversation_history.append(("System", response_message))
                yield self.generate_message_update(username=username,
                                                   conversation_id=conversation_id,
                                                   message=response_message)
                promo_code_policy = self.get_promo_code_policy(self.current_chat_bot_state.promo_code_errors.promo_code)
                print("promo_code_policy:", promo_code_policy)
                cart_value = self.get_cart_value()
                self.current_chat_bot_state.promo_code_errors.status = TaskStatus.READY_FOR_EXECUTION
                if not self.relational_database.update_chat_bot_state(username, conversation_id, self.current_chat_bot_state):
                    print("Failed to update conversation state.")
                print("cart_value:", cart_value)
                if cart_value < promo_code_policy["minimum_cart_value"]:
                    response_message = "Your cart value is lower than the promo code policy. Please add %d rupees worth of more items." % (promo_code_policy["minimum_cart_value"]-cart_value)
                    self.conversation_history.append(("System", response_message))
                    yield self.generate_message_update(username=username,
                                                       conversation_id=conversation_id,
                                                       message=response_message)
                self.current_chat_bot_state.promo_code_errors.status = TaskStatus.COMPLETED
                if not self.relational_database.update_chat_bot_state(username, conversation_id, self.current_chat_bot_state):
                    print("Failed to update conversation state.")
        elif self.current_chat_bot_state.primary_focus_intent == "CHANGE_DELIVERY_ADDRESS":
            if self.current_chat_bot_state.change_delivery_address.status == TaskStatus.COLLECTING_SLOTS:
                missing_fields = []
                if self.current_chat_bot_state.change_delivery_address.order_id is None:
                    missing_fields.append("order id")
                if self.current_chat_bot_state.change_delivery_address.new_address is None:
                    missing_fields.append("delivery address")
                if missing_fields:
                    response_message = "Could you please share %s ?" % " and ".join(missing_fields)
                    self.conversation_history.append(("System", response_message))
                    yield self.generate_message_update(username=username,
                                                       conversation_id=conversation_id,
                                                       message=response_message)
                else:
                    self.current_chat_bot_state.change_delivery_address.status = TaskStatus.CHECKING_WITH_BACKEND
                    if not self.relational_database.update_chat_bot_state(username, conversation_id, self.current_chat_bot_state):
                        print("Failed to update conversation state.")

            if self.current_chat_bot_state.change_delivery_address.status == TaskStatus.CHECKING_WITH_BACKEND:
                response_message = "I'm checking with the backend ..."
                self.conversation_history.append(("System", response_message))
                yield self.generate_message_update(username=username,
                                                   conversation_id=conversation_id,
                                                   message=response_message)
                time.sleep(1.0)
                (is_eligible, reason) = self.is_eligibile_for_address_change(self.current_chat_bot_state.change_delivery_address.order_id)
                self.current_chat_bot_state.change_delivery_address.is_address_eligible_for_change = is_eligible
                if not self.relational_database.update_chat_bot_state(username, conversation_id, self.current_chat_bot_state):
                    print("Failed to update conversation state.")
                if is_eligible:
                    response_message = "Your address eligible for address change."
                    self.conversation_history.append(("System", response_message))
                    yield self.generate_message_update(username=username,
                                                       conversation_id=conversation_id,
                                                       message=response_message)
                    self.current_chat_bot_state.change_delivery_address.status = TaskStatus.READY_FOR_EXECUTION
                    response_message = "Updating the delivery address..."
                    self.conversation_history.append(("System", response_message))
                    yield self.generate_message_update(username=username,
                                                       conversation_id=conversation_id,
                                                       message=response_message)
                    time.sleep(1.0)
                    address_updated = self.update_delivery_address(order_id=self.current_chat_bot_state.change_delivery_address.order_id,
                                                                   new_address=self.current_chat_bot_state.change_delivery_address.new_address)
                    if address_updated:
                        responses_message = "Your address has been updated."
                    else:
                        responses_message = "Your address update encountered an error. Backend team is looking into it..."
                    self.conversation_history.append(("System", responses_message))
                    yield self.generate_message_update(username=username,
                                                       conversation_id=conversation_id,
                                                       message=responses_message)
                    self.current_chat_bot_state.change_delivery_address.status = TaskStatus.COMPLETED
                    self.current_chat_bot_state.active_intents.remove("CHANGE_DELIVERY_ADDRESS")
                    if not self.relational_database.update_chat_bot_state(username, conversation_id, self.current_chat_bot_state):
                        print("Failed to update conversation state.")
                else:
                    response_message = "Your order is not eligible for the address change as %s." % reason
                    self.conversation_history.append(("System", response_message))
                    yield self.generate_message_update(username=username,
                                                       conversation_id=conversation_id,
                                                       message=response_message)
                    self.current_chat_bot_state.change_delivery_address.status = TaskStatus.FAILED
                    self.current_chat_bot_state.active_intents.remove("CHANGE_DELIVERY_ADDRESS")
                    self.current_chat_bot_state.blocked_intents.append("CHANGE_DELIVERY_ADDRESS")
                    if not self.relational_database.update_chat_bot_state(username, conversation_id, self.current_chat_bot_state):
                        print("Failed to update conversation state.")

        yield self.generate_message_complete(username=username,
                                             conversation_id=conversation_id)

    def update(self, username, conversation_id, message, message_id, sent_at):
        initial_data = self.relational_database.get_chat_bot_state(username=username,
                                                                       conversation_id=conversation_id)
        chat_bot_state = ChatBotState()
        self.current_chat_bot_state = chat_bot_state.model_copy(update=initial_data, deep=True)
        self.conversation_history = self.relational_database.get_message_history(username=username,
                                                                                 conversation_id=conversation_id)
        updated_state = self.update_chat_bot_state(username, conversation_id, message, message_id, sent_at)
        self.validate_and_correct(username, conversation_id, updated_state)

    def close(self, username, conversation_id, closed_by, close_reason):
        now = datetime.now()
        closed_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        if self.relational_database.add_close_status(username, conversation_id, closed_by, close_reason, closed_at):
            return closed_at
        else:
            return None

    def is_closed(self, username, conversation_id):
        last_status = self.relational_database.get_last_status(username=username, conversation_id=conversation_id)
        if last_status is None or last_status["status"] == "closed":
            return True
        else:
            return False

if __name__ == "__main__":
    conversation = ChatBotConversation()
    username = "jerry.mouse"
    print(conversation.create(username))
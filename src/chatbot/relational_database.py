import threading
from typing import Optional, Annotated, Union, Literal
from urllib.parse import quote_plus
from sqlmodel import create_engine, SQLModel, Field, JSON, Session, select

from chatbot.data_model import ChatBotState
from .config import Settings

class ConversationStatusOpen(SQLModel):
    status: Literal["open"] = "open"
    created_at: str = Field(default=None)

class ConversationStatusClosed(SQLModel):
    status: Literal["closed"] = "closed"
    closed_by: str = Field(default=None)
    close_reason: str = Field(default=None)
    closed_at: str = Field(default=None)

ConversationStatus = Annotated[
    Union[ConversationStatusOpen, ConversationStatusClosed],
    Field(discriminator="status"),
]

class MessageItem(SQLModel):
    message_id: str = Field(default=None)
    sender: str = Field(default=None)
    message: str = Field(default=None)
    sent_at: str = Field(default=None)

class Conversation(SQLModel, table=True):
    username: Optional[str] = Field(primary_key=True)
    conversation_id: Optional[str] = Field(primary_key=True)
    status: Optional[list[ConversationStatus]] = Field(default=[], sa_type=JSON)
    messages: Optional[list[MessageItem]] = Field(default=[], sa_type=JSON)

class ConversationState(SQLModel, table=True):
    username: Optional[str] = Field(primary_key=True)
    conversation_id: Optional[str] = Field(primary_key=True)
    chat_bot_state: Optional[ChatBotState] = Field(default={}, sa_type=JSON)

class RelationalDatabase:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = RelationalDatabase()
        return cls._instance

    def __init__(self):
        settings = Settings()
        encoded_password = quote_plus(settings.password)
        database_url = f"postgresql+psycopg://{settings.user_name}:{encoded_password}@localhost:5432/{settings.database_name}"
        self.engine = create_engine(database_url, echo=True)
        SQLModel.metadata.create_all(self.engine)

    def insert_conversation(self, username, conversation_id, created_at):
        status = [ConversationStatusOpen(created_at=created_at).model_dump()]
        conversation = Conversation(username=username, conversation_id=conversation_id, status=status)
        try:
            with Session(self.engine) as session:
                session.add(conversation)
                session.commit()
                # Refresh to populate auto-generated fields like `id` from Postgres
                session.refresh(conversation)
                print(f"Created Chatbot Conversation with id: {conversation.conversation_id} with username: {conversation.username}")
                return conversation.conversation_id
        except Exception as e:
            print("Failed to insert chatbot conversation:", e)
            return None

    def get_conversation_status(self, username, conversation_id):
        with Session(self.engine) as session:
            statement = select(Conversation).where(Conversation.username == username,
                                                   Conversation.conversation_id == conversation_id)
            results = session.exec(statement).all()
            if len(results) == 0:
                return None
            else:
                return results[0].status[-1]
        return None

    def get_chat_bot_state(self, username, conversation_id):
        with Session(self.engine) as session:
            statement = select(ConversationState).where(ConversationState.username == username,
                                                        ConversationState.conversation_id == conversation_id)
            conversation_state:ConversationState = session.exec(statement).first()
            if conversation_state:
                return conversation_state.chat_bot_state
        return {}

    def update_chat_bot_state(self, username, conversation_id, chat_bot_state):
        with Session(self.engine) as session:
            statement = select(ConversationState).where(ConversationState.username == username,
                                                                    ConversationState.conversation_id == conversation_id)
            conversation_state:ConversationState = session.exec(statement).first()
            if conversation_state:
                conversation_state.chat_bot_state = chat_bot_state.model_dump()
                session.add(conversation_state)
                session.commit()
                session.refresh(conversation_state)
                print(f"\nUpdated {conversation_state.username},{conversation_state.conversation_id}'s state to {conversation_state.chat_bot_state}")
                return True
            else:
                conversation_state_new = ConversationState(username=username,
                                                           conversation_id=conversation_id,
                                                           chat_bot_state=chat_bot_state.model_dump())
                session.add(conversation_state_new)
                session.commit()
                # Refresh to populate auto-generated fields like `id` from Postgres
                session.refresh(conversation_state_new)
                print(
                    f"Created Chatbot Conversation State with username: {conversation_state_new.username} and "
                    f"conversation_id: {conversation_state_new.conversation_id} with chat_bot_state: {conversation_state_new.chat_bot_state}")
                return True
        return False

    def add_message(self, username, conversation_id, message_data):
        with Session(self.engine) as session:
            statement = select(Conversation).where(Conversation.username == username,
                                                   Conversation.conversation_id == conversation_id)
            conversation:Conversation = session.exec(statement).first()
            if conversation:
                new_messages = []
                for message in conversation.messages:
                    new_messages.append(message)
                new_messages.append(message_data)
                conversation.messages = new_messages
                session.add(conversation)
                session.commit()
                session.refresh(conversation)
                print("\nAdded message to conversation:", conversation.conversation_id, " messages: ", conversation.messages)
                return True
        return False

    def add_close_status(self, username, conversation_id, closed_by, close_reason, closed_at):
        with Session(self.engine) as session:
            statement = select(Conversation).where(Conversation.username == username,
                                                   Conversation.conversation_id == conversation_id)
            conversation:Conversation = session.exec(statement).first()
            if conversation:
                new_statuses = []
                for status in conversation.status:
                    new_statuses.append(status)
                close_status = ConversationStatusClosed(closed_by=closed_by, close_reason=close_reason, closed_at=closed_at)
                new_statuses.append(close_status.model_dump())
                conversation.status = new_statuses
                session.add(conversation)
                session.commit()
                session.refresh(conversation)
                print("\nAdded status to the conversation:", conversation.conversation_id, " status: ", conversation.status)
                return True
        return False

    def get_last_status(self, username, conversation_id):
        with Session(self.engine) as session:
            statement = select(Conversation).where(Conversation.username == username,
                                                   Conversation.conversation_id == conversation_id)
            conversation:Conversation = session.exec(statement).first()
            if conversation and conversation.status and len(conversation.status) > 0:
                return conversation.status[-1]
        return None

    def get_message_history(self, username, conversation_id):
        message_history = []
        with Session(self.engine) as session:
            statement = select(Conversation).where(Conversation.username == username,
                                                   Conversation.conversation_id == conversation_id)
            conversation:Conversation = session.exec(statement).first()
            if conversation:
                for message in conversation.messages:
                    message_history.append((message["sender"], message["message"]))
        return message_history

if __name__ == "__main2__":
    relational_database = RelationalDatabase.get_instance()
    conversation_status = relational_database.get_conversation_status(username="jerry.mouse", conversation_id="CONV#20260906172340")
    print("conversation_status", conversation_status)
    print("type(conversation_status):", type(conversation_status))
    initial_data = relational_database.get_chat_bot_state(username="jerry.mouse",
                                                            conversation_id="CONV#20260906172340")
    chat_bot_state = ChatBotState()
    current_chat_bot_state = chat_bot_state.model_copy(update=initial_data, deep=True)
    print("current_chat_bot_state", current_chat_bot_state)
    current_chat_bot_state.primary_focus_intent = "CHANGE_DELIVERY_ADDRESS"
    relational_database.update_chat_bot_state(username="jerry.mouse", conversation_id="CONV#20260906172340",
                                              chat_bot_state=current_chat_bot_state)
    current_data = relational_database.get_chat_bot_state(username="jerry.mouse", conversation_id="CONV#20260906172340")
    print("current_data", current_data)

if __name__ == "__main3__":
    relational_database = RelationalDatabase.get_instance()
    username = "jerry.mouse"
    conversation_id = "CONV#20260906172340"
    message_data = {
        "message_id": "sys-msg-1788855942-0",
        "message": "I'm checking with the backend ...",
        "sender": "System",
        "sent_at": "2026-09-08T11:38:49Z"
    }
    status = relational_database.add_message(username, conversation_id, message_data)
    print("status", status)

if __name__ == "__main__":
    relational_database = RelationalDatabase.get_instance()
    username = "jerry.mouse"
    conversation_id = "CONV#20260906172340"
    message_history = relational_database.get_message_history(username, conversation_id)
    print("message_history:", message_history)

import threading
from typing import Optional, Annotated, Union, Literal
from urllib.parse import quote_plus
from sqlmodel import create_engine, SQLModel, Field, JSON, Session, select

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

if __name__ == "__main__":
    relational_database = RelationalDatabase.get_instance()
    conversation_status = relational_database.get_conversation_status(username="jerry.mouse", conversation_id="CONV#20260906172340")
    print("conversation_status", conversation_status)
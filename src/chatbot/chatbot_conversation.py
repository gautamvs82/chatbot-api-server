from datetime import datetime

from .relational_database import RelationalDatabase

class ChatBotConversation:
    def __init__(self):
        self.relational_database = RelationalDatabase.get_instance()

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

if __name__ == "__main__":
    conversation = ChatBotConversation()
    username = "jerry.mouse"
    print(conversation.create(username))
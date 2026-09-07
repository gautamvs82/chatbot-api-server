from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import uvicorn

from .chatbot_conversation import ChatBotConversation

app = FastAPI(title="Chatbot API")

class CreateConversationRequest(BaseModel):
    username: str
    channel: str

class CreateConversationResponse(BaseModel):
    username: str
    conversation_id: str
    status: str
    created_at: str

class UpdateConversationRequest(BaseModel):
    username: str
    conversation_id: str
    message_id: str
    message: str
    sent_at: str


@app.post("/api/create-conversation", response_model=CreateConversationResponse)
def create_conversation(request_payload: CreateConversationRequest) -> CreateConversationResponse:
    if request_payload is None or request_payload.username is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad Request")
    try:
        chatbot_conversation = ChatBotConversation()
        conversation_id = chatbot_conversation.create(request_payload.username)
        if conversation_id is None or conversation_id=="":
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Internal server error while creating a new conversation")
        conversation_status = chatbot_conversation.get_status(request_payload.username, conversation_id)
        if conversation_status is None or conversation_status["status"] != "open":
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Internal server error while getting conversation status")
        return CreateConversationResponse(
            username=request_payload.username,
            conversation_id=conversation_id,
            status=conversation_status["status"],
            created_at=conversation_status["created_at"],
        )
    except Exception as e:
        print("Exception while creating a new conversation: ", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error while creating a new conversation")

@app.post("/api/update-conversation")
async def update_conversation(request_payload: UpdateConversationRequest):
    if request_payload is None or request_payload.username is None or request_payload.conversation_id is None \
            or request_payload.message_id is None or request_payload.message is None or request_payload.sent_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad Request (Missing parameters)")
    try:
        chatbot_conversation = ChatBotConversation()
        chatbot_conversation.update(request_payload.username, request_payload.conversation_id, request_payload.message)
        return EventSourceResponse(chatbot_conversation.generate_responses(request_payload.username, request_payload.conversation_id))
    except Exception as e:
        print("Exception while updating conversation: ", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error while updating conversation")


if __name__ == "__main__":
    uvicorn.run("chatbot.main:app", host="0.0.0.0", port=5090, reload=True)
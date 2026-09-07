import asyncio
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

async def event_generator():
    for i in range(1, 6):
        await asyncio.sleep(2)  # Simulate task processing
        yield f"data: Update {i} at time t+{i*2}s\n\n"

@app.get("/api/stream-updates")
async def stream_updates():
    return StreamingResponse(event_generator(), media_type="text/event-stream")
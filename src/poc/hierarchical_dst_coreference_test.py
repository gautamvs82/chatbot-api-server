import json
from typing import Optional
from pydantic import BaseModel, Field, model_validator
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate


# 1. Define the Structured Dialogue State Schema
class DialogueState(BaseModel):
    restaurant_name: Optional[str] = Field(
        default=None, description="Name of the restaurant or venue booked."
    )
    restaurant_people: Optional[str] = Field(
        default=None, description="Number of people for the restaurant."
    )
    restaurant_day: Optional[str] = Field(
        default=None, description="Day of the week for restaurant booking."
    )
    taxi_destination: Optional[str] = Field(
        default=None, description="Destination location for the taxi ride."
    )
    taxi_day: Optional[str] = Field(
        default=None, description="Day of the week for the taxi ride."
    )
    taxi_time: Optional[str] = Field(
        default=None, description="Time for the taxi ride."
    )

    @model_validator(mode="after")
    def resolve_generic_terms(self) -> "DialogueState":
        # Fallback 1: If taxi_destination is "that hotel" or "the hotel", map to restaurant_name
        generic_place_terms = ["that hotel", "the hotel", "it", "there", "that place"]
        if self.taxi_destination and self.taxi_destination.lower() in generic_place_terms:
            if self.restaurant_name:
                self.taxi_destination = self.restaurant_name

        # Fallback 2: If taxi_day is "the same day" or "same day", map to restaurant_day
        generic_day_terms = ["the same day", "same day", "that day"]
        if self.taxi_day and self.taxi_day.lower() in generic_day_terms:
            if self.restaurant_day:
                self.taxi_day = self.restaurant_day

        return self

# 2. Initialize Ollama LLM with Structured Output
llm = ChatOllama(model="llama3.1:8b", temperature=0)
dst_tracker = llm.with_structured_output(DialogueState)

# 3. Create System Prompt with Co-reference Resolution Rules
system_prompt = """
You are an expert Dialogue State Tracker (DST).
Your task is to update the dialogue state frame using the user's latest turn and the previous state.

CRITICAL COREFERENCE RESOLUTION RULES:
1. NEVER output vague phrases like "that hotel", "it", "there", "the venue", or "the same day".
2. ALWAYS substitute references with the EXACT values from the previous dialogue state:
   - Example: If previous state has `restaurant_name: "The Grand Palace"` and user says "cab to that hotel", you MUST set `taxi_destination: "The Grand Palace"`.
   - Example: If previous state has `restaurant_day: "Saturday"` and user says "on the same day", you MUST set `taxi_day: "Saturday"`.
3. Retain all existing slot values from the previous state unless explicitly changed.

### EXAMPLE:
Previous State: {{"restaurant_name": "The Grand Palace", "restaurant_day": "Saturday"}}
User Utterance: "Book a cab to that hotel on the same day"
Output State: {{"restaurant_name": "The Grand Palace", "restaurant_day": "Saturday", "taxi_destination": "The Grand Palace", "taxi_day": "Saturday"}}
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human",
     "Previous Dialogue State: {previous_state}\nCurrent User Utterance: '{utterance}'\nUpdate the Dialogue State:")
])

# Combine Prompt and LLM into a Chain
dst_chain = prompt | dst_tracker


# 4. Simulation Engine
def run_dialogue_simulation(dialogue_turns):
    # Initialize empty state
    current_state = DialogueState()

    print("=== STARTING DIALOGUE STATE TRACKING SIMULATION ===\n")

    for idx, utterance in enumerate(dialogue_turns, 1):
        print(f"--- TURN {idx} ---")
        print(f"User: \"{utterance}\"")

        # Invoke DST chain with previous state and current utterance
        current_state = dst_chain.invoke({
            "previous_state": json.dumps(current_state.model_dump(), indent=2),
            "utterance": utterance
        })

        # Display updated state
        print("Updated Dialogue State:")
        print(json.dumps(current_state.model_dump(), indent=2))
        print("\n")


# 5. Run standard multi-turn dialogue with co-references
turns = [
    "I need a table at The Grand Palace for 2 people on Friday.",
    "Actually, change it to Saturday.",
    "Can you book a cab to that hotel for 7 PM on the same day?"
]

if __name__ == "__main__":
    run_dialogue_simulation(turns)
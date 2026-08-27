import re
from typing import Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field
import spacy
from sentence_transformers import SentenceTransformer, util

# Load NLP Models
# Embedding model for Semantic Similarity
embedder = SentenceTransformer("all-MiniLM-L6-v2")
# SpaCy for BIO NER & Syntactic Dependency Parsing
nlp = spacy.load("en_core_web_sm")


# -------------------------------------------------------------------
# 1. DATA STRUCTURES (Pydantic Schema)
# -------------------------------------------------------------------
class ChangeAddressFrame(BaseModel):
    """Semantic Frame for the 'Change Delivery Address' Goal."""

    goal_id: str = "CHANGE_DELIVERY_ADDRESS"
    order_id: Optional[str] = Field(
        None, description="The alphanumeric order identification number"
    )
    new_address: Optional[str] = Field(
        None, description="The complete physical shipping address"
    )
    is_complete: bool = False


# -------------------------------------------------------------------
# 2. INTENT CLASSIFIER (Semantic Similarity)
# -------------------------------------------------------------------
class SemanticIntentClassifier:

    def __init__(self, high_threshold: float = 0.65, low_threshold: float = 0.45):
        self.high_threshold = high_threshold
        self.low_threshold = low_threshold

        # Benchmark reference utterances for "Change Delivery Address"
        self.reference_phrases = [
            "I want to change my delivery address for an order",
            "Update the shipping location for my package",
            "Can I ship my order to a different address?",
            "Change my home address for delivery",
            "Deliver my order to a new location",
            "I entered the wrong shipping address on my purchase",
        ]
        # Pre-compute embeddings for benchmark phrases
        self.reference_embeddings = embedder.encode(
            self.reference_phrases, convert_to_tensor=True
        )

    def classify(self, user_input: str) -> Tuple[str, float]:
        """Calculates cosine similarity between user input and reference intent vectors."""
        input_embedding = embedder.encode(user_input, convert_to_tensor=True)
        similarity_scores = util.cos_sim(input_embedding, self.reference_embeddings)
        max_score = float(similarity_scores.max())

        if max_score >= self.high_threshold:
            return "CHANGE_DELIVERY_ADDRESS", max_score
        elif max_score >= self.low_threshold:
            return "DISAMBIGUATION_REQUIRED", max_score
        else:
            return "OUT_OF_DOMAIN", max_score


# -------------------------------------------------------------------
# 3. HYBRID SLOT EXTRACTION ENGINE
# -------------------------------------------------------------------
class HybridSlotExtractor:

    @staticmethod
    def extract_via_sequence_and_regex(text: str) -> Dict[str, Any]:
        """Technique 1: Regex / Sequence Pattern Matching for structured IDs."""
        slots = {}
        # Pattern for order numbers (e.g., #ORD-102, Order 9921, #002)
        # Comprehensive Regex Engine
        ORDER_REGEX = re.compile(
            r"\b(?:order|ord|pkg|package|id)?\s*[\#\:]?\s*([a-z0-9]*\d[a-z0-9]*)\b",
            re.IGNORECASE
        )
        # Blacklist common false-positive words that accidentally contain numbers or match rules
        INVALID_WORDS = {"STREET", "ADDRESS", "AVENUE", "SUITE", "APT", "ROAD"}

        matches = ORDER_REGEX.findall(text)
        for candidate in matches:
            candidate_clean = candidate.upper().strip()
            # Ensure minimum length and not in word blacklist
            if len(candidate_clean) >= 3 and candidate_clean not in INVALID_WORDS:
                slots["order_id"] = candidate_clean

        return slots

    @staticmethod
    def extract_via_dependency_parsing(text: str) -> Dict[str, Any]:
        """Technique 2: Syntactic Dependency Parsing & Spacy NER for physical addresses."""
        slots = {}
        doc = nlp(text)

        # 2a. Use SpaCy Named Entity Recognition for GPE (Locations) / FAC (Facilities)
        gpe_entities = [ent.text for ent in doc.ents if ent.label_ in ["GPE", "FAC", "LOC"]]

        # 2b. Syntactic Dependency Analysis: Look for prepositional targets following location verbs
        address_tokens = []
        for token in doc:
            # Look for prepositions like "to", "at", "into" attached to location changes
            if token.pos_ in ["ADP", "SCONJ"] and token.text.lower() in ["to", "at"]:
                # Collect the subtree representing the address location
                subtree = [t.text for t in token.subtree if t.text.lower() not in ["to", "at"]]
                if subtree:
                    address_tokens.append(" ".join(subtree))

        if address_tokens:
            slots["new_address"] = address_tokens[0]
        elif gpe_entities:
            slots["new_address"] = ", ".join(gpe_entities)

        return slots

    @staticmethod
    def extract_via_schema_mock_llm(
        text: str, current_frame: ChangeAddressFrame
    ) -> Dict[str, Any]:
        """Technique 3: Schema-Constrained Tool/Function Filling (Simulated).

        Acts as a mock representation of JSON-Schema function binding.
        """
        # In a live production system, this invokes an LLM with Pydantic JSON Schema tools.
        slots = {}
        # Fallback slot filling logic if address contains typical street keywords
        address_keywords = [
            "street",
            "st",
            "avenue",
            "ave",
            "road",
            "rd",
            "blvd",
            "drive",
            "lane",
        ]
        if any(kw in text.lower() for kw in address_keywords):
            # Extract everything following the verb 'to' or 'is' as address
            match = re.search(
                r"(?:to|is)\s+(.+)", text, re.IGNORECASE
            )
            if match:
                slots["new_address"] = match.group(1).strip()
        return slots


# -------------------------------------------------------------------
# 4. ORCHESTRATOR
# -------------------------------------------------------------------
class ChangeAddressOrchestrator:

    def __init__(self):
        self.classifier = SemanticIntentClassifier()
        self.extractor = HybridSlotExtractor()

    def process_turn(
            self, user_input: str, existing_frame: Optional[ChangeAddressFrame] = None
    ) -> Dict[str, Any]:
        frame = existing_frame or ChangeAddressFrame()

        # ------------------------------------------------------------------
        # TECHNIQUE 3: CONTEXTUAL EXPECTATION (SLOT-PROMPT PRIMING)
        # If we are waiting for a specific missing slot, attempt extraction FIRST.
        # ------------------------------------------------------------------
        if existing_frame and not existing_frame.is_complete:
            # 1. Capture snapshot of missing state BEFORE priming
            had_order_id = bool(frame.order_id)
            had_new_address = bool(frame.new_address)

            # 2. Attempt slot extraction for missing fields
            if not frame.order_id:
                regex_slots = self.extractor.extract_via_sequence_and_regex(user_input)
                if regex_slots.get("order_id"):
                    frame.order_id = regex_slots["order_id"]

            if not frame.new_address:
                dep_slots = self.extractor.extract_via_dependency_parsing(user_input)
                if dep_slots.get("new_address"):
                    frame.new_address = dep_slots["new_address"]
                else:
                    schema_slots = self.extractor.extract_via_schema_mock_llm(user_input, frame)
                    if schema_slots.get("new_address"):
                        frame.new_address = schema_slots["new_address"]

            # 3. Check if any newly required slot was filled in this turn
            slot_filled_during_priming = (
                    (not had_order_id and bool(frame.order_id)) or
                    (not had_new_address and bool(frame.new_address))
            )

            # If primed extraction succeeded, skip full intent classification
            if slot_filled_during_priming:
                return self._evaluate_frame_status(frame)

        # ------------------------------------------------------------------
        # STANDARD PIPELINE: INTENT CLASSIFICATION VIA SEMANTIC SIMILARITY
        # ------------------------------------------------------------------
        intent, score = self.classifier.classify(user_input)

        if intent == "OUT_OF_DOMAIN":
            return {
                "status": "FALLBACK",
                "message": "I'm sorry, I couldn't understand your request. Are you trying to update an order address?",
                "frame": frame,
            }

        if intent == "DISAMBIGUATION_REQUIRED":
            return {
                "status": "DISAMBIGUATE",
                "message": "It sounds like you might want to modify your order. Did you want to change your delivery address?",
                "frame": frame,
            }

        # Extract any initial slots present in the main request turn
        regex_slots = self.extractor.extract_via_sequence_and_regex(user_input)
        if regex_slots.get("order_id") and not frame.order_id:
            frame.order_id = regex_slots["order_id"]

        dep_slots = self.extractor.extract_via_dependency_parsing(user_input)
        if dep_slots.get("new_address") and not frame.new_address:
            frame.new_address = dep_slots["new_address"]

        return self._evaluate_frame_status(frame)

    def _evaluate_frame_status(self, frame: ChangeAddressFrame) -> Dict[str, Any]:
        """Helper method to determine next dialogue action."""
        if frame.order_id and frame.new_address:
            frame.is_complete = True
            return {
                "status": "READY_TO_EXECUTE",
                "message": f"Successfully updated order #{frame.order_id} shipping address to '{frame.new_address}'.",
                "frame": frame,
            }
        elif not frame.order_id:
            return {
                "status": "SLOT_PROMPT",
                "message": "Could you please provide the order ID you would like to update?",
                "frame": frame,
            }
        else:
            return {
                "status": "SLOT_PROMPT",
                "message": f"What is the new delivery address for order #{frame.order_id}?",
                "frame": frame,
            }

# -------------------------------------------------------------------
# 5. EXECUTION & TEST SUITE
# -------------------------------------------------------------------
if __name__ == "__main__":
    orchestrator = ChangeAddressOrchestrator()
    """
    print("--- Test Case 1: Complete Input in Single Turn ---")
    res1 = orchestrator.process_turn(
        "Please update the shipping location for order #ORD-9912 to 742 Evergreen Terrace, Springfield"
    )
    print(f"Status : {res1['status']}")
    print(f"Message: {res1['message']}")
    print(f"Frame  : {res1['frame'].dict()}\n")

    print("--- Test Case 2: Partial Input (Missing Address) ---")
    res2 = orchestrator.process_turn("Can I change the address for order #4401?")
    print(f"Status : {res2['status']}")
    print(f"Message: {res2['message']}")
    print(f"Frame  : {res2['frame'].dict()}\n")

    print("--- Test Case 3: Turn 2 Continuation (Slot Prompt Fill) ---")
    # Passing the incomplete frame from res2 back into turn 2
    res3 = orchestrator.process_turn("Change it to 101 Park Avenue", existing_frame=res2["frame"])
    print(f"Status : {res3['status']}")
    print(f"Message: {res3['message']}")
    print(f"Frame  : {res3['frame'].dict()}\n")

    print("--- Test Case 4: Out of Domain / Low Score ---")
    res4 = orchestrator.process_turn("What is the weather like in New York today?")
    print(f"Status : {res4['status']}")
    print(f"Message: {res4['message']}")
    """
    print("--- Test Case 5: Multi turn conversation ---")
    res1 = orchestrator.process_turn(
        "Hi, I want to change the delivery address for my last order"
    )
    print(f"Status : {res1['status']}")
    print(f"Message: {res1['message']}")
    print(f"Frame  : {res1['frame'].model_dump()}\n")

    res2 = orchestrator.process_turn(
        "The order id is #00001", res1["frame"]
    )
    print(f"Status : {res2['status']}")
    print(f"Message: {res2['message']}")
    print(f"Frame  : {res2['frame'].model_dump()}\n")



# -------------------------------------------------------------------
# 6. UNIT TESTS
# -------------------------------------------------------------------
if __name__ == "__main2__":
    hybrid_slot_extractor = HybridSlotExtractor()
    slots = hybrid_slot_extractor.extract_via_dependency_parsing("The order id is #00001")
    print("slots:", slots)
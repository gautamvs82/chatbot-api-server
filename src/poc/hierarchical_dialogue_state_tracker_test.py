import json
from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, model_validator


# -------------------------------------------------------------------
# 1. Domain Slot Models (Hierarchical Structure)
# -------------------------------------------------------------------

class FlightSlots(BaseModel):
    origin: Optional[str] = Field(None, description="Departure city or airport code.")
    destination: Optional[str] = Field(None, description="Arrival city or airport code.")
    departure_date: Optional[str] = Field(None, description="Date in YYYY-MM-DD format.")
    passengers: int = Field(default=1, description="Number of travelers.")


class HotelSlots(BaseModel):
    location: Optional[str] = Field(None, description="City or area for hotel stay.")
    check_in_date: Optional[str] = Field(None, description="Date in YYYY-MM-DD format.")
    duration_nights: Optional[int] = Field(None, description="Number of nights staying.")
    star_rating: Optional[str] = Field(None, description="Desired star rating or tier.")


class CarRentalSlots(BaseModel):
    pick_up_location: Optional[str] = Field(None, description="City or airport for car pickup.")
    pick_up_date: Optional[str] = Field(None, description="Date in YYYY-MM-DD format.")
    car_type: Optional[str] = Field(None, description="Category of vehicle (e.g., SUV, Sedan).")


class DomainType(str, Enum):
    FLIGHT = "flight"
    HOTEL = "hotel"
    CAR_RENTAL = "car_rental"


# -------------------------------------------------------------------
# 2. Global State Frame with Dependency Logic
# -------------------------------------------------------------------

class HierarchicalDialogueState(BaseModel):
    active_domains: List[DomainType] = Field(
        default_factory=list,
        description="List of domains explicitly active in the current conversation turn."
    )
    primary_domain: Optional[DomainType] = Field(
        None,
        description="The primary target domain receiving updates in the current turn."
    )
    flight: FlightSlots = Field(default_factory=FlightSlots)
    hotel: HotelSlots = Field(default_factory=HotelSlots)
    car_rental: CarRentalSlots = Field(default_factory=CarRentalSlots)

    @model_validator(mode="after")
    def resolve_cross_domain_dependencies(self) -> "HierarchicalDialogueState":
        """
        Executes business rules for hierarchical slot inheritance:
        1. If hotel check-in date is missing, inherit from flight departure date.
        2. If hotel location is missing, inherit from flight destination.
        3. If car rental pickup location is missing, inherit from flight destination.
        """
        # Rule 1: Hotel inherits location from flight destination
        if self.hotel.location is None and self.flight.destination is not None:
            self.hotel.location = self.flight.destination

        # Rule 2: Hotel inherits check-in from flight departure date
        if self.hotel.check_in_date is None and self.flight.departure_date is not None:
            self.hotel.check_in_date = self.flight.departure_date

        # Rule 3: Car pickup location inherits from flight destination
        if self.car_rental.pick_up_location is None and self.flight.destination is not None:
            self.car_rental.pick_up_location = self.flight.destination

        return self


# -------------------------------------------------------------------
# 3. DST Update Engine & Operations
# -------------------------------------------------------------------

class StateOperationType(str, Enum):
    UPDATE = "UPDATE"  # Add or overwrite slot values
    RESET = "RESET"  # Clear slots for a specific domain
    INHERIT = "INHERIT"  # Explicitly trigger cross-domain inheritance


class DSTTurnUpdate(BaseModel):
    reasoning: str = Field(..., description="Explanation of intent changes in this turn.")
    operation: StateOperationType = Field(..., description="Action to perform on the state frame.")
    target_domain: DomainType
    slot_updates: Dict[str, Any] = Field(
        default_factory=dict,
        description="Key-value pairs to update in the target domain."
    )


class HierarchicalDSTTracker:
    def __init__(self):
        self.state = HierarchicalDialogueState()

    def apply_turn_update(self, update: DSTTurnUpdate) -> HierarchicalDialogueState:
        domain_key = update.target_domain.value
        domain_model = getattr(self.state, domain_key)

        # 1. Update active domain tracking
        if update.target_domain not in self.state.active_domains:
            self.state.active_domains.append(update.target_domain)
        self.state.primary_domain = update.target_domain

        # 2. Execute requested operation
        if update.operation == StateOperationType.RESET:
            setattr(self.state, domain_key, domain_model.__class__())

        elif update.operation in [StateOperationType.UPDATE, StateOperationType.INHERIT]:
            # Apply slot updates to target domain model
            updated_data = domain_model.model_dump()
            updated_data.update(update.slot_updates)

            # Re-instantiate domain slot model with new values
            setattr(self.state, domain_key, domain_model.__class__(**updated_data))

        # 3. Re-validate state frame (triggers @model_validator for cross-domain inheritance)
        self.state = HierarchicalDialogueState.model_validate(self.state.model_dump())
        return self.state


# -------------------------------------------------------------------
# 4. Simulation Execution
# -------------------------------------------------------------------

if __name__ == "__main__":
    tracker = HierarchicalDSTTracker()

    # --- Turn 1: User books a flight ---
    turn1_llm_output = {
        "reasoning": "User specified flight destination and date.",
        "operation": "UPDATE",
        "target_domain": "flight",
        "slot_updates": {
            "origin": "New York",
            "destination": "London",
            "departure_date": "2026-09-01"
        }
    }

    update1 = DSTTurnUpdate(**turn1_llm_output)
    state_turn1 = tracker.apply_turn_update(update1)

    print("=== State After Turn 1 (Flight Search) ===")
    print(json.dumps(state_turn1.model_dump(), indent=2))

    # --- Turn 2: User adds hotel without specifying location or date ---
    turn2_llm_output = {
        "reasoning": "User requested a 4-star hotel stay for 3 nights. Dates/locations implicit.",
        "operation": "UPDATE",
        "target_domain": "hotel",
        "slot_updates": {
            "star_rating": "4-star",
            "duration_nights": 3
        }
    }

    update2 = DSTTurnUpdate(**turn2_llm_output)
    state_turn2 = tracker.apply_turn_update(update2)

    print("\n=== State After Turn 2 (Hotel added - Automatic Context Inheritance) ===")
    # Note how hotel.location ('London') and hotel.check_in_date ('2026-09-01') automatically populate
    print(json.dumps(state_turn2.model_dump(), indent=2))
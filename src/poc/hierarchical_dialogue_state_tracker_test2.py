from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, model_validator


# -------------------------------------------------------------------
# 1. Enums and Domain States
# -------------------------------------------------------------------

class TaskStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    COLLECTING_SLOTS = "COLLECTING_SLOTS"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    READY_FOR_EXECUTION = "READY_FOR_EXECUTION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TrackDeliveryDelaySlots(BaseModel):
    status: TaskStatus = TaskStatus.NOT_STARTED
    delay_reason: Optional[str] = None
    revised_eta: Optional[str] = None
    compensation_offered: bool = False


class PromoCodeErrorSlots(BaseModel):
    status: TaskStatus = TaskStatus.NOT_STARTED
    promo_code: Optional[str] = None
    error_type: Optional[str] = None  # e.g., "EXPIRED", "MIN_BASKET_NOT_MET"
    manual_override_applied: bool = False


class ChangeDeliveryAddressSlots(BaseModel):
    status: TaskStatus = TaskStatus.NOT_STARTED
    new_street: Optional[str] = None
    new_postal_code: Optional[str] = None
    is_address_eligible_for_change: Optional[bool] = None  # Depends on order shipment status


# -------------------------------------------------------------------
# 2. Hierarchical State Container
# -------------------------------------------------------------------

class NonHierarchicalGlobalDST(BaseModel):
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

    @model_validator(mode="after")
    def resolve_domain_cross_dependencies(self) -> "NonHierarchicalGlobalDST":
        """
        Executes operational logic across independent domains:
        1. If delivery address change fails (e.g., item already shipped),
           automatically surface promo/compensation options.
        2. Set priority intent dynamically based on task lifecycle.
        """
        # Rule 1: Lock address change if order is already out for delivery
        if self.change_delivery_address.is_address_eligible_for_change is False:
            if "CHANGE_DELIVERY_ADDRESS" in self.active_intents:
                self.active_intents.remove("CHANGE_DELIVERY_ADDRESS")
                self.blocked_intents.append("CHANGE_DELIVERY_ADDRESS")
                self.change_delivery_address.status = TaskStatus.FAILED

        # Rule 2: Automatically prioritize PROMO_CODE_ERRORS if delay compensation is triggered
        if self.track_delivery_delay.compensation_offered and "PROMO_CODE_ERRORS" not in self.active_intents:
            self.active_intents.append("PROMO_CODE_ERRORS")
            self.promo_code_errors.status = TaskStatus.COLLECTING_SLOTS

        return self


# -------------------------------------------------------------------
# 3. Simulation Example
# -------------------------------------------------------------------

if __name__ == "__main__":
    # Initialize tracker with shared context
    dst = NonHierarchicalGlobalDST(
        global_order_id="ORD-88392",
        active_intents=["TRACK_DELIVERY_DELAY", "CHANGE_DELIVERY_ADDRESS"],
        primary_focus_intent="CHANGE_DELIVERY_ADDRESS"
    )

    # Simulate turn: System determines address cannot be changed (out for delivery)
    dst.change_delivery_address.is_address_eligible_for_change = False
    dst.track_delivery_delay.compensation_offered = True

    # Re-validate triggers cross-domain adjustments
    updated_dst = NonHierarchicalGlobalDST.model_validate(dst.model_dump())

    print("Active Intents:", updated_dst.active_intents)
    print("Blocked Intents:", updated_dst.blocked_intents)
    print("Promo Task Status:", updated_dst.promo_code_errors.status)
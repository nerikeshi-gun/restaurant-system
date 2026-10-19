from typing import Literal

from pydantic import BaseModel, Field


class ModifierOptionView(BaseModel):
    id: int
    name: str
    price_delta: int
    is_default: bool


class ModifierGroupView(BaseModel):
    id: int
    name: str
    selection_type: str
    required: bool
    options: list[ModifierOptionView]


class MenuItemView(BaseModel):
    id: int
    category: str
    name: str
    short_name: str
    localized_names: dict[str, str] = Field(default_factory=dict)
    price: int
    modifiers: list[ModifierGroupView] = []


class MenuCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    display_order: int = Field(default=0, ge=0, le=9999)


class MenuCategoryUpdate(MenuCategoryCreate):
    pass


class MenuItemCategoryUpdate(BaseModel):
    category_id: int = Field(gt=0)


class AdminMenuModifierLink(BaseModel):
    group_id: int = Field(gt=0)
    required: bool = False
    display_order: int = Field(default=0, ge=0, le=9999)


class AdminMenuItemCreate(BaseModel):
    menu_code: str = Field(min_length=1, max_length=80)
    category_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    short_name: str = Field(default="", max_length=100)
    reading: str = Field(default="", max_length=200)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    localized_names: dict[str, str] = Field(default_factory=dict)
    price: int = Field(ge=0, le=10_000_000)
    display_order: int = Field(default=0, ge=0, le=9999)
    size_label: str = Field(default="", max_length=100)
    set_contents: str = Field(default="", max_length=1000)
    is_available: bool = True
    modifier_groups: list[AdminMenuModifierLink] = Field(default_factory=list, max_length=30)


class AdminMenuItemUpdate(AdminMenuItemCreate):
    pass


class AdminModifierOptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    price_delta: int = Field(default=0, ge=-10_000_000, le=10_000_000)
    is_default: bool = False
    display_order: int = Field(default=0, ge=0, le=9999)
    is_available: bool = True


class AdminModifierOptionUpdate(AdminModifierOptionCreate):
    pass


class AdminModifierGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    selection_type: Literal["single", "multiple"] = "single"
    display_order: int = Field(default=0, ge=0, le=9999)
    is_active: bool = True
    options: list[AdminModifierOptionCreate] = Field(default_factory=list, max_length=30)


class AdminModifierGroupUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    selection_type: Literal["single", "multiple"] = "single"
    display_order: int = Field(default=0, ge=0, le=9999)
    is_active: bool = True


class StoreLayoutUpdate(BaseModel):
    block_order: list[Literal["input", "menu", "service"]] = Field(
        default_factory=lambda: ["input", "menu", "service"]
    )
    order_position: Literal["right", "top", "bottom"] = "right"


class ResponsiveStoreLayoutUpdate(BaseModel):
    desktop: StoreLayoutUpdate = Field(default_factory=StoreLayoutUpdate)
    tablet: StoreLayoutUpdate = Field(default_factory=StoreLayoutUpdate)


class StoreSettingsUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    theme_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    layout: ResponsiveStoreLayoutUpdate


class CandidateItem(BaseModel):
    menu_item_id: int
    quantity: int | None = Field(default=None, ge=1, le=99)
    modifier_option_ids: list[int] = []
    operation: Literal["add", "change", "cancel"] = "add"


class Candidate(BaseModel):
    items: list[CandidateItem]
    label: str


class LlmInterpretation(BaseModel):
    intent: Literal["order", "service_request", "unknown"]
    candidates: list[Candidate] = []
    service_request_type: Literal["water", "spill", "wait_time", "checkout", "call_staff", "other"] | None = None
    question: str | None = None


class InterpretRequest(BaseModel):
    session_id: int
    text: str = Field(min_length=1, max_length=500)
    stt_alternatives: list[str] = Field(default_factory=list, max_length=5)
    input_language: str = Field(default="ja", min_length=2, max_length=20)
    japanese_text: str | None = Field(default=None, max_length=500)


class InterpretResponse(BaseModel):
    interpretation_id: int
    state: Literal["ready_to_confirm", "needs_item_choice", "service_request", "needs_retry"]
    question: str | None = None
    candidates: list[Candidate]
    menu_items: list[MenuItemView]
    service_request_type: str | None = None
    provider: Literal["openai", "local_fallback"]
    model_name: str | None = None


class OrderItemCreate(BaseModel):
    menu_item_id: int
    quantity: int = Field(ge=1, le=99)
    modifier_option_ids: list[int] = []


class OrderCreate(BaseModel):
    session_id: int
    interpretation_id: int | None = None
    client_request_id: str = Field(min_length=8, max_length=64)
    original_text: str | None = Field(default=None, max_length=500)
    confirmation_method: Literal["touch_button"]
    items: list[OrderItemCreate] = Field(min_length=1, max_length=30)


class ServiceRequestCreate(BaseModel):
    session_id: int
    request_type: Literal["water", "spill", "wait_time", "checkout", "call_staff", "other"]
    message: str = Field(default="", max_length=500)


class MessageCreate(BaseModel):
    session_id: int
    sender_type: Literal["customer", "kitchen"]
    text: str = Field(min_length=1, max_length=500)


class TableResetRequest(BaseModel):
    expected_session_id: int


class StatusUpdate(BaseModel):
    status: Literal["confirmed", "preparing", "ready", "served", "rejected", "cancelled"]


class AvailabilityUpdate(BaseModel):
    is_available: bool


class SharedItemCreate(BaseModel):
    menu_item_id: int
    quantity: int = Field(ge=1, le=99)
    modifier_option_ids: list[int] = []
    input_by: Literal["staff", "customer"]
    input_language: str = Field(default="ja", min_length=2, max_length=20)
    original_text: str | None = Field(default=None, max_length=500)
    menu_version: str | None = Field(default=None, max_length=80)
    llm_candidates: list[dict] = []
    selected_candidate: dict | None = None
    notes: str = Field(default="", max_length=500)
    expected_version: int = Field(ge=1)


class SharedItemUpdate(BaseModel):
    quantity: int | None = Field(default=None, ge=1, le=99)
    modifier_option_ids: list[int] | None = None
    notes: str | None = Field(default=None, max_length=500)
    expected_version: int = Field(ge=1)


class SharedItemCancel(BaseModel):
    expected_version: int = Field(ge=1)
    input_by: Literal["staff", "customer"]


class SharedOrderConfirm(BaseModel):
    expected_version: int = Field(ge=1)
    confirmed_by: Literal["staff", "customer"]
    confirmation_method: Literal["touch_button"]


class KitchenItemStatusUpdate(BaseModel):
    status: Literal["not_started", "preparing", "served", "cancelled"]


class DisplayNumberReset(BaseModel):
    next_number: int = Field(default=1, ge=1, le=9999)


class ResolveOrderRequest(BaseModel):
    store_id: str = Field(min_length=1, max_length=40)
    recognized_text: str = Field(min_length=1, max_length=500)
    input_language: str = Field(default="ja", min_length=2, max_length=20)


class ResolvedMenuCandidate(BaseModel):
    menu_id: str
    menu_item_id: int
    name: str
    option_candidates: list[str] = []


class ResolvedOrderItem(BaseModel):
    source_phrase: str
    quantity: int | None = Field(default=None, ge=1, le=99)
    operation: Literal["add", "change", "cancel"] = "add"
    candidates: list[ResolvedMenuCandidate] = []


class ResolveOrderResponse(BaseModel):
    status: Literal["needs_confirmation", "ambiguous", "not_found", "fallback"]
    recognized_text: str
    menu_version: str
    items: list[ResolvedOrderItem] = []
    provider: str
    model_name: str | None = None
    message: str | None = None

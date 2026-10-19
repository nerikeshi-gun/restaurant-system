from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DiningTable(Base):
    __tablename__ = "dining_tables"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True)
    access_token: Mapped[str] = mapped_column(String(64), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    usage_status: Mapped[str] = mapped_column(String(30), default="available")
    current_order_id: Mapped[int | None] = mapped_column(Integer, index=True)


class TableSession(Base):
    __tablename__ = "table_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("dining_tables.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    table: Mapped[DiningTable] = relationship()


class DisplayNumberCounter(Base):
    __tablename__ = "display_number_counters"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_date: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    next_number: Mapped[int] = mapped_column(Integer, default=1)


class Store(Base):
    __tablename__ = "stores"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    monthly_ai_request_limit: Mapped[int] = mapped_column(Integer, default=10000)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    theme_color: Mapped[str] = mapped_column(String(7), default="#b74328")
    ui_layout_json: Mapped[str] = mapped_column(Text, default='{"desktop":{"block_order":["input","menu","service"],"order_position":"right"},"tablet":{"block_order":["input","menu","service"],"order_position":"right"}}')


class MenuVersion(Base):
    __tablename__ = "menu_versions"
    __table_args__ = (UniqueConstraint("store_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"), index=True)
    version: Mapped[str] = mapped_column(String(80), index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    items: Mapped[list["MenuVersionItem"]] = relationship(cascade="all, delete-orphan")


class MenuVersionItem(Base):
    __tablename__ = "menu_version_items"
    __table_args__ = (UniqueConstraint("menu_version_id", "menu_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    menu_version_id: Mapped[int] = mapped_column(ForeignKey("menu_versions.id"), index=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"), index=True)
    menu_id: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(200))
    category_name: Mapped[str] = mapped_column(String(100), default="")
    reading: Mapped[str] = mapped_column(String(200), default="")
    aliases_json: Mapped[str] = mapped_column(Text, default="[]")
    price: Mapped[int] = mapped_column(Integer)
    size_label: Mapped[str] = mapped_column(String(100), default="")
    set_contents: Mapped[str] = mapped_column(Text, default="")
    toppings_json: Mapped[str] = mapped_column(Text, default="[]")
    sold_out: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    localized_names_json: Mapped[str] = mapped_column(Text, default="{}")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class AiResolutionLog(Base):
    __tablename__ = "ai_resolution_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"), index=True)
    menu_version: Mapped[str] = mapped_column(String(80))
    recognized_text: Mapped[str] = mapped_column(Text)
    input_language: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(50))
    model_name: Mapped[str | None] = mapped_column(String(100))
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class MenuCategory(Base):
    __tablename__ = "menu_categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_menu_category: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_option_group: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    selection_type: Mapped[str] = mapped_column(String(20), default="single")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    options: Mapped[list["ModifierOption"]] = relationship(cascade="all, delete-orphan", back_populates="group")


class MenuItem(Base):
    __tablename__ = "menu_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("menu_categories.id"), index=True)
    store_id: Mapped[str] = mapped_column(String(40), default="STORE001", index=True)
    menu_code: Mapped[str | None] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(200))
    reading: Mapped[str] = mapped_column(String(200), default="")
    short_name: Mapped[str] = mapped_column(String(100))
    price: Mapped[int] = mapped_column(Integer)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    size_label: Mapped[str] = mapped_column(String(100), default="")
    set_contents: Mapped[str] = mapped_column(Text, default="")
    localized_names_json: Mapped[str] = mapped_column(Text, default="{}")
    category: Mapped[MenuCategory] = relationship()
    aliases: Mapped[list["MenuAlias"]] = relationship(cascade="all, delete-orphan")
    modifier_groups: Mapped[list["MenuItemModifierGroup"]] = relationship(cascade="all, delete-orphan")


class MenuAlias(Base):
    __tablename__ = "menu_aliases"
    id: Mapped[int] = mapped_column(primary_key=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"), index=True)
    alias: Mapped[str] = mapped_column(String(200), index=True)


class ModifierOption(Base):
    __tablename__ = "modifier_options"
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("menu_categories.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    price_delta: Mapped[int] = mapped_column(Integer, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    group: Mapped[MenuCategory] = relationship(back_populates="options")


class MenuItemModifierGroup(Base):
    __tablename__ = "menu_item_modifier_groups"
    __table_args__ = (UniqueConstraint("menu_item_id", "group_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("menu_categories.id"), index=True)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    group: Mapped[MenuCategory] = relationship()


class Interpretation(Base):
    __tablename__ = "interpretations"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("table_sessions.id"), index=True)
    original_text: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(50))
    model_name: Mapped[str | None] = mapped_column(String(100))
    store_id: Mapped[str | None] = mapped_column(String(40), index=True)
    menu_version: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("table_sessions.id"), index=True)
    interpretation_id: Mapped[int | None] = mapped_column(ForeignKey("interpretations.id"))
    client_request_id: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="submitted", index=True)
    original_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transaction_id: Mapped[str | None] = mapped_column(String(36), unique=True, index=True)
    business_date: Mapped[str | None] = mapped_column(String(10), index=True)
    display_number: Mapped[int | None] = mapped_column(Integer, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)
    confirmation_batches: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_by: Mapped[str | None] = mapped_column(String(20))
    confirmation_method: Mapped[str | None] = mapped_column(String(30))
    items: Mapped[list["OrderItem"]] = relationship(cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"))
    menu_name_snapshot: Mapped[str] = mapped_column(String(200))
    unit_price_snapshot: Mapped[int] = mapped_column(Integer)
    menu_version_snapshot: Mapped[str | None] = mapped_column(String(80))
    llm_candidates_json: Mapped[str] = mapped_column(Text, default="[]")
    selected_candidate_json: Mapped[str] = mapped_column(Text, default="{}")
    quantity: Mapped[int] = mapped_column(Integer)
    line_total: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    kitchen_status: Mapped[str] = mapped_column(String(30), default="not_started", index=True)
    input_by: Mapped[str] = mapped_column(String(20), default="customer")
    input_language: Mapped[str] = mapped_column(String(20), default="ja")
    input_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    original_text: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, default="")
    change_type: Mapped[str] = mapped_column(String(20), default="added")
    previous_quantity: Mapped[int | None] = mapped_column(Integer)
    submission_batch: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    modifiers: Mapped[list["OrderItemModifier"]] = relationship(cascade="all, delete-orphan")


class OrderItemModifier(Base):
    __tablename__ = "order_item_modifiers"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_item_id: Mapped[int] = mapped_column(ForeignKey("order_items.id"), index=True)
    modifier_option_id: Mapped[int] = mapped_column(ForeignKey("modifier_options.id"))
    group_name_snapshot: Mapped[str] = mapped_column(String(100), default="")
    name_snapshot: Mapped[str] = mapped_column(String(100))
    price_delta_snapshot: Mapped[int] = mapped_column(Integer)

    @property
    def display_name(self) -> str:
        return f"{self.group_name_snapshot}：{self.name_snapshot}" if self.group_name_snapshot else self.name_snapshot


class ServiceRequest(Base):
    __tablename__ = "service_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("table_sessions.id"), index=True)
    request_type: Mapped[str] = mapped_column(String(30), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("table_sessions.id"), index=True)
    sender_type: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

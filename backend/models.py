from datetime import datetime
from sqlalchemy import String, Float, DateTime, ForeignKey, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class Building(Base):
    __tablename__ = "buildings"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    building_type: Mapped[str] = mapped_column(String(80), default="Unspecified")
    location: Mapped[str] = mapped_column(String(120), default="")
    floor_area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    records: Mapped[list["ConsumptionRecord"]] = relationship(back_populates="building", cascade="all, delete-orphan")

class ConsumptionRecord(Base):
    __tablename__ = "consumption_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(24), default="kWh")
    source: Mapped[str] = mapped_column(String(120), default="User upload")
    building: Mapped[Building] = relationship(back_populates="records")

class Simulation(Base):
    __tablename__ = "simulations"
    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id"))
    name: Mapped[str] = mapped_column(String(120))
    baseline_kwh: Mapped[float] = mapped_column(Float)
    scenario_kwh: Mapped[float] = mapped_column(Float)
    assumptions: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_text: Mapped[str] = mapped_column(Text)
    assistant_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

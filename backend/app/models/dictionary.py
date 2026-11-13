from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class City(Base):
    __tablename__ = "cities"
    __table_args__ = (
        Index("ix_cities_normalized_name_trgm", "normalized_name", postgresql_using="gin", postgresql_ops={"normalized_name": "gin_trgm_ops"}),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    normalized_name: Mapped[str] = mapped_column(String(120), index=True)
    center_lat: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    center_lon: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    venues: Mapped[list["Venue"]] = relationship(back_populates="city")


class Venue(Base):
    __tablename__ = "venues"
    __table_args__ = (
        Index("ix_venues_normalized_name_trgm", "normalized_name", postgresql_using="gin", postgresql_ops={"normalized_name": "gin_trgm_ops"}),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    address: Mapped[str] = mapped_column(Text)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lon: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    city: Mapped[City] = relationship(back_populates="venues")

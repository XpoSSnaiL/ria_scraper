import os
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import BigInteger
from sqlalchemy.dialects.postgresql import insert

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

class Car(Base):
    __tablename__ = "cars"

    # ID remains as a system primary key (good practice)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Fields according to Technical Task (TZ):
    url: Mapped[str] = mapped_column(unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(nullable=True)
    price_usd: Mapped[int] = mapped_column(nullable=True)
    odometer: Mapped[int] = mapped_column(nullable=True)
    username: Mapped[str] = mapped_column(nullable=True)

    # Using BigInteger for long phone numbers (e.g., 380...)
    phone_number: Mapped[int] = mapped_column(BigInteger, nullable=True)

    image_url: Mapped[str] = mapped_column(nullable=True)
    images_count: Mapped[int] = mapped_column(nullable=True)
    car_number: Mapped[str] = mapped_column(nullable=True)
    car_vin: Mapped[str] = mapped_column(nullable=True)
    datetime_found: Mapped[datetime] = mapped_column(default=datetime.utcnow)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def save_car(car_data: dict):
    async with AsyncSessionLocal() as session:
        stmt = insert(Car).values(**car_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=['url'],
            set_={
                'price_usd': stmt.excluded.price_usd,
                'datetime_found': stmt.excluded.datetime_found
            }
        )
        await session.execute(stmt)
        await session.commit()
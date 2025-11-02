from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import os

engine = create_async_engine(os.getenv("DATABASE_URL", ""), echo=False, future=True)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db():
    async with async_session() as session:
        yield session
import asyncio

from sqlalchemy import text

from control_plane.infrastructure.db.session import get_engine, get_session


async def main() -> None:
    async for session in get_session():
        result = await session.execute(text("select version()"))
        print(result.scalar_one())
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())

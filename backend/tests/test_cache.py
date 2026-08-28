"""缓存服务测试 — 内存模式"""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_cache_set_get():
    async def _run():
        from app.services.cache_service import set, get, delete
        await set("test-key", "hello", ttl_seconds=60)
        val = await get("test-key")
        assert val == "hello"
        await delete("test-key")
        assert await get("test-key") is None
    asyncio.run(_run())


def test_cache_default_memory():
    from app.services.cache_service import is_redis_available
    # 默认无 Redis 时使用内存回退
    assert isinstance(is_redis_available(), bool)


def test_cache_multiple_keys():
    async def _run():
        from app.services.cache_service import set, get, delete
        await set("a", 1)
        await set("b", 2)
        assert await get("a") == 1
        assert await get("b") == 2
        await delete("a")
        await delete("b")
    asyncio.run(_run())

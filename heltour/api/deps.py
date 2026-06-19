from asgiref.sync import sync_to_async


async def in_thread(fn, *args, **kwargs):
    return await sync_to_async(fn, thread_sensitive=True)(*args, **kwargs)

import asyncio

import pytest

from station.events import EventHub, sse_format


async def test_publish_reaches_all_subscribers():
    hub = EventHub()
    q1, q2 = hub.subscribe(), hub.subscribe()
    hub.publish({"kind": "progress", "seq": 1})
    assert (await q1.get())["seq"] == 1
    assert (await q2.get())["seq"] == 1


async def test_full_queue_drops_oldest():
    hub = EventHub(maxsize=2)
    q = hub.subscribe()
    for i in range(3):
        hub.publish({"seq": i})
    assert (await q.get())["seq"] == 1  # seq0 被丢
    assert (await q.get())["seq"] == 2


async def test_unsubscribe_stops_delivery():
    hub = EventHub()
    q = hub.subscribe()
    hub.unsubscribe(q)
    hub.publish({"seq": 1})
    assert q.empty()


def test_sse_format():
    assert sse_format({"a": 1}) == 'data: {"a": 1}\n\n'

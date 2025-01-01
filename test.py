from gi.repository import Gst
import asyncio
import time
from webrtc import *

WEBSOCKET_URL = 'wss://test.antmedia.io/usamatest/websocket'
prefix = "test-"


loop = None


async def publish_test(webrtc_adapter, num_streams):
    for i in range(num_streams):
        webrtc_adapter.publish()


async def play_test(webrtc_adapter, num_streams):
    for i in range(num_streams):
        await webrtc_adapter.play(prefix + str(i))

play_adapter = WebRTCAdapter(WEBSOCKET_URL)
publish_adapter = WebRTCAdapter(WEBSOCKET_URL)


def wait_for_publish(num_streams):
    list = range(num_streams)

    while True:
        for i in range(num_streams):
            pass

        time.sleep(1)
        if (len(list) > 0):
            print("waiting for all the streams to get published")
            wait_for_publish()
    # verify if the stream was published


async def main():
    Gst.init(None)
    if not check_plugins():
        sys.exit(1)

    Gst.init(None)
    if not check_plugins():
        sys.exit(1)

    await play_adapter.connect()
    await publish_adapter.connect()
    publish_adapter.set_main_loop(loop)
    play_adapter.set_main_loop(loop)

    num_test_stream = 1
    # publish_test(num_test_stream)
    # wait_for_publish(num_test_stream)
    # publish_test(num_test_stream)
    await play_test(num_test_stream)

    await publish_adapter.loop()
    await play_adapter.loop()


if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    asyncio.ensure_future(main())
    loop.run_forever()

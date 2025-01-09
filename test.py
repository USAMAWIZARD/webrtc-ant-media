from webrtc import WebRTCAdapter
from webrtc import check_plugins
from gi.repository import Gst
import asyncio
import sys
import time

WEBSOCKET_URL = 'wss://test.antmedia.io/usamatest/websocket'
prefix = "test-"


loop = None


def publish_test(num_streams):

    for i in range(num_streams):
        webrtc_adapter = WebRTCAdapter(WEBSOCKET_URL)
        webrtc_adapter.connect()
        webrtc_adapter.publish(prefix + str(i))


def play_test(num_streams):

    webrtc_adapter = WebRTCAdapter(WEBSOCKET_URL)
    webrtc_adapter.connect()
    for i in range(num_streams):
        webrtc_adapter.play(prefix + str(i))


def wait_for_publish(num_streams):
    list = range(num_streams)

    while True:
        for i in range(num_streams):
            pass

        time.sleep(1)
        if (len(list) > 0):
            print("waiting for all the streams to get published")
            wait_for_publish()


async def main():
    Gst.init(None)
    if not check_plugins():
        sys.exit(1)

    # publish_test(num_streams=1)
    # wait_for_publish(10)
    play_test(1)


if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    asyncio.run(main())
    loop.run_forever()

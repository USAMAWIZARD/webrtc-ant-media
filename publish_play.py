from webrtc import WebRTCAdapter
from webrtc import set_event_loop
from webrtc import check_plugins
from gi.repository import Gst
import asyncio
import sys

appname = "usamatest"
WEBSOCKET_URL = 'wss://ovh36.antmedia.io:5443/' + appname + '/websocket'
WEBSOCKET_URL = 'wss://test.antmedia.io/' + appname + '/websocket'


async def main():
    Gst.init(None)
    if not check_plugins():
        sys.exit(1)

    webrtc_adapter = WebRTCAdapter(WEBSOCKET_URL)
    await webrtc_adapter.connect()
    await webrtc_adapter.publish("test1")

    webrtc_adapter = WebRTCAdapter(WEBSOCKET_URL)
    await webrtc_adapter.connect()
    await webrtc_adapter.publish("test2")


if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    set_event_loop(loop)
    asyncio.run(main())
    loop.run_forever()

from webrtc import WebRTCAdapter, init_gstreamer

appname = "live"
WEBSOCKET_URL = 'wss://test.antmedia.io/' + appname + '/websocket'

init_gstreamer()
webrtc_adapter = WebRTCAdapter(WEBSOCKET_URL)
webrtc_adapter.connect()  # replace publish call with play to play the stream
webrtc_adapter.publish("test1")

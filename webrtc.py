# ulimit -n 65536 run this command to increase socket opening limit
import threading
import gi
import json
import sys
import os
import asyncio
import ssl
import time
import random
from gi.repository import GstVideo
import websocket
from gi.repository import GstSdp
from gi.repository import GstWebRTC
from gi.repository import Gst

gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
gi.require_version('GstSdp', '1.0')

PIPELINE_DESC_SEND = '''
 videotestsrc is-live=true pattern=ball ! videoconvert ! queue ! x264enc  speed-preset=veryfast tune=zerolatency key-int-max=1  ! rtph264pay !
 queue ! application/x-rtp,media=video,encoding-name=H264,payload=96 ! webrtcbin name=sendrecv  bundle-policy=max-bundle'''

PIPELINE_DESC_RECV = '''webrtcbin name=sendrecv  bundle-policy=max-bundle ! queue ! fakesink'''


class WebRTCAdapter:
    webrtc_clients = {}  # idmode stream1play

    def __init__(self, URL):
        self.server = URL
        self.client_id = ""

    def on_message(self, ws, message):
        data = json.loads(message)

        print('Message: ' + data['command'], data)

        if (data['command'] == 'start'):
            self.start_publishing(data["streamId"])
        elif (data['command'] == 'takeCandidate'):
            self.take_candidate(data)
        elif (data['command'] == 'takeConfiguration'):
            self.take_configuration(data)
        elif (data['command'] == 'notification'):
            self.notification(data)
        elif (data['command'] == 'error'):
            print('Message: ' + data['definition'])

    def on_error(self, ws, error):
        print(f"Client {self.client_id} error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print(f"Client {self.client_id} closed: {
              close_status_code}, {close_msg}")

    def on_open(self, ws):
        self.isopen.set()
        print(self.ws_conn)

    def get_websocket(self):
        return self.ws_conn

    def socket_listner_thread(self):
        websocket.enableTrace(True)
        ws = websocket.WebSocketApp(
            self.server,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open,
        )

        self.ws_conn = ws
        ws.run_forever()

    def send_ping(self):
        self.ws_conn.send('{"command": "ping"}')
        pingtimer = threading.Timer(5, self.send_ping)
        pingtimer.start()

    def connect(self):
        self.callback = "test"
        self.isopen = threading.Event()
        thread = threading.Thread(
            target=self.socket_listner_thread, args=())
        thread.daemon = True

        pingtimer = threading.Timer(5, self.send_ping)
        pingtimer.start()

        thread.start()
        self.isopen.wait()

    def play(self, id, on_video_callback=None, on_audio_callback=None):
        print("play request sent for id", id)
        wrtc_client_id = id
        if self.wrtc_client_exist(id):
            pass
        else:
            play_client = WebRTCClient(
                id, "play", self.ws_conn, on_video_callback, on_video_callback)
            WebRTCAdapter.webrtc_clients[wrtc_client_id] = play_client
            play_client.play()

    def start_publishing(self, id):
        if publish_client := self.get_webrtc_client(id):
            publish_client.start_pipeline("publish")
        else:
            print("no client found")

    def publish(self, id):
        wrtc_client_id = id
        if wrtc_client_id in WebRTCAdapter.webrtc_clients:
            pass
        else:
            publish_client = WebRTCClient(id, "publish", self.ws_conn)
            WebRTCAdapter.webrtc_clients[wrtc_client_id] = publish_client
            publish_client.send_publish_request()

    def wrtc_client_exist(self, id):
        if id in WebRTCAdapter.webrtc_clients:
            True
        return False

    def get_webrtc_client(self, id):
        if id in WebRTCAdapter.webrtc_clients:
            return WebRTCAdapter.webrtc_clients[id]
        return None

    def take_candidate(self, candidate):
        stream_id = candidate["streamId"]
        webrtc_client = self.get_webrtc_client(stream_id)
        if webrtc_client:
            webrtc_client.take_candidate(candidate)
        else:
            print("no webrtc client exist for this request", stream_id)

    def take_configuration(self, config):
        wrtc_client_id = config["streamId"]

        wrtc_client = self.get_webrtc_client(wrtc_client_id)
        print(wrtc_client, wrtc_client_id, WebRTCAdapter.webrtc_clients)
        if wrtc_client:
            wrtc_client.take_configuration(config)
        else:
            print("no webrtc client exist for this request",
                  wrtc_client_id)

    def notification(self, data):
        if (data['definition'] == 'publish_started'):
            print('Publish Started')
        else:
            print(data['definition'])


class WebRTCClient():

    def __init__(self, id, mode, ws_client, on_video_callback=None, on_audio_callback=None):
        self.id = id
        self.pipe = None
        self.webrtc = None
        self.peer_id = None
        self.mode = mode
        self.websocket_client = ws_client
        self.on_video_callback = on_video_callback
        self.on_audio_callback = on_audio_callback

    def send_publish_request(self):
        self.websocket_client.send(
            '{"command":"publish","streamId":"' + self.id + '", "token":"null","video":true,"audio":true}')

    def play(self):
        self.websocket_client.send(
            '{"command":"play","streamId":"' + self.id + '", "token":"null"}')

    def send_sdp(self, sdp, type):
        print('Send SDP ' + type, self.id)
        sdp = sdp.as_text()
        self.websocket_client.send(
            '{"command":"takeConfiguration", "streamId": "' + self.id + '", "type": "' + type + '", "sdp": "' + sdp + '"}')

    def on_negotiation_needed(self, element):
        print('Negotiation Needed')
        promise = Gst.Promise.new_with_change_func(
            self.on_offer_created, element, None)
        element.emit('create-offer', None, promise)

    def send_ice_candidate_message(self, _, mlineindex, candidate):
        data = '{"command":"takeCandidate","streamId":"' + self.id + '","label":' + \
            str(mlineindex) + ', "id":"' + str(mlineindex) + \
            '" "candidate":"' + str(candidate) + '"}'
        self.websocket_client.send(data)

    def on_incoming_decodebin_stream(self, _, pad):
        print('Incoming Decodebin Stream')
        if not pad.has_current_caps():
            print(pad, 'has no caps, ignoring')
            return
        caps = pad.get_current_caps()
        s = caps
        name = s.to_string()

        if name.startswith('video'):
            print("video stream recieved", self.id)
            q = Gst.ElementFactory.make('queue')
            conv = Gst.ElementFactory.make('videoconvert')
            sink = Gst.ElementFactory.make('autovideosink')

            self.pipe.add(q)
            self.pipe.add(conv)
            self.pipe.add(sink)
            self.pipe.sync_children_states()
            pad.link(q.get_static_pad('sink'))

            q.link(conv)
            conv.link(sink)

        elif name.startswith('audio'):
            print("audio stream recieved")
            q = Gst.ElementFactory.make('queue')
            conv = Gst.ElementFactory.make('audioconvert')
            resample = Gst.ElementFactory.make('audioresample')
            sink = Gst.ElementFactory.make('autoaudiosink')

            self.pipe.add(q)
            self.pipe.add(conv)
            self.pipe.add(resample)
            self.pipe.add(sink)

            self.pipe.sync_children_states()
            pad.link(q.get_static_pad('sink'))
            q.link(conv)
            conv.link(resample)
            resample.link(sink)

    def handle_media_stream(self, pad, gst_pipe, convert_name, sink_name):
        print(f"Trying to handle stream with {convert_name} ! {sink_name}")

        # Create a queue and sink element
        queue = Gst.ElementFactory.make("queue", None)
        sink = Gst.ElementFactory.make(sink_name, None)
        converter = Gst.ElementFactory.make(convert_name, None)

        if not all([queue, sink, converter]):
            print("Failed to create necessary GStreamer elements.")
            return

    def handle_media_stream(self, pad, gst_pipe, convert_name, sink_name):
        print(f"Trying to handle stream with {convert_name} ! {sink_name}")

        # Create a queue and sink element
        queue = Gst.ElementFactory.make("queue", None)
        sink = Gst.ElementFactory.make(sink_name, None)
        converter = Gst.ElementFactory.make(convert_name, None)

        if not all([queue, sink, converter]):
            print("Failed to create necessary GStreamer elements.")
            return

        # Set sink properties
        sink.set_property("sync", False)

        # Determine if the stream is audio or video
        if convert_name == "audioconvert":
            print("Audio stream detected")
            resample = Gst.ElementFactory.make("audioresample", None)

            if not resample:
                print("Failed to create audioresample element.")
                return

            gst_pipe.add(queue)
            gst_pipe.add(converter)
            gst_pipe.add(resample)
            gst_pipe.add(sink)

            queue.sync_state_with_parent()
            converter.sync_state_with_parent()
            resample.sync_state_with_parent()
            sink.sync_state_with_parent()

            queue.link(converter)
            converter.link(resample)
            resample.link(sink)
            if self.on_audio_callback:
                pad.add_probe(
                    Gst.PadProbeType.BUFFER, self.on_audio_callback, self.id)

        else:
            print("Video stream detected")

            capsfilter = Gst.ElementFactory.make("capsfilter")
            rgbcaps = Gst.caps_from_string("video/x-raw,format=RGB")
            capsfilter.set_property("caps", rgbcaps)

            gst_pipe.add(queue)
            gst_pipe.add(capsfilter)
            gst_pipe.add(converter)
            gst_pipe.add(sink)
            capsfilter.sync_state_with_parent()
            queue.sync_state_with_parent()
            converter.sync_state_with_parent()
            sink.sync_state_with_parent()
            queue.link(converter)
            converter.link(capsfilter)
            capsfilter.link(sink)

            rgb_pad = sink.get_static_pad("sink")
            if self.on_video_callback:
                rgb_pad.add_probe(
                    Gst.PadProbeType.BUFFER, self.on_video_callback, self.id)

            gst_pipe.add(queue)
            gst_pipe.add(converter)
            gst_pipe.add(sink)
            queue.sync_state_with_parent()
            converter.sync_state_with_parent()
            sink.sync_state_with_parent()
            queue.link(converter)
            converter.link(sink)

        queue_sink_pad = queue.get_static_pad("sink")
        if not queue_sink_pad:
            print("Failed to get the sink pad of the queue.")
            return

        ret = pad.link(queue_sink_pad)
        if ret != Gst.PadLinkReturn.OK:
            print(f"Failed to link pad: {ret}")
        else:
            print("Pad successfully linked.")

    def on_incoming_stream(self, webrtc, pad):
        decode = None
        depay = None
        parse = None
        jitterbuffer = None

        caps = pad.get_current_caps()
        structure = caps.get_structure(0)
        mediatype = structure.get_value("media")

        if mediatype.startswith("video"):
            decode = Gst.ElementFactory.make("avdec_h264", None)
            depay = Gst.ElementFactory.make("rtph264depay", None)
            parse = Gst.ElementFactory.make("h264parse", None)
            convert_name = "videoconvert"
            sink_name = "fakesink"

        elif mediatype.startswith("audio"):
            decode = Gst.ElementFactory.make("opusdec", None)
            depay = Gst.ElementFactory.make("rtpopusdepay", None)
            parse = Gst.ElementFactory.make("opusparse", None)
            convert_name = "audioconvert"
            sink_name = "autoaudiosink"
        else:
            print(f"Unknown pad {pad.get_name()}, ignoring")
            return

        jitterbuffer = Gst.ElementFactory.make("rtpjitterbuffer", None)

        pipeline = self.pipe
        pipeline.add(jitterbuffer)
        pipeline.add(depay)
        pipeline.add(parse)
        pipeline.add(decode)

        sinkpad = jitterbuffer.get_static_pad("sink")
        if pad.link(sinkpad) != Gst.PadLinkReturn.OK:
            print("Failed to link incoming pad to jitter buffer sink pad")
            return

        jitterbuffer.link(depay)
        depay.link(parse)
        parse.link(decode)

        for element in [jitterbuffer, depay, parse, decode]:
            element.sync_state_with_parent()

        decoded_pad = decode.get_static_pad("src")
        self.handle_media_stream(
            decoded_pad, pipeline, convert_name, sink_name)

    def start_pipeline(self, mode):
        print('Creating WebRTC Pipeline', mode, self.id)
        if (mode == "publish"):
            self.pipe = Gst.parse_launch(PIPELINE_DESC_SEND)
        elif (mode == "play"):
            self.pipe = Gst.parse_launch(PIPELINE_DESC_RECV)

        self.webrtc = self.pipe.get_by_name('sendrecv')
        if (mode == "publish"):
            self.webrtc.connect('on-negotiation-needed',
                                self.on_negotiation_needed)
        self.webrtc.connect('on-ice-candidate',
                            self.send_ice_candidate_message)
        self.webrtc.connect('pad-added', self.on_incoming_stream)
        self.pipe.set_state(Gst.State.PLAYING)

    def take_candidate(self, data):
        self.webrtc.emit('add-ice-candidate', data['label'], data['candidate'])

    def on_offer_created(self, promise, _, __):

        print('Offer Created')
        promise.wait()
        reply = promise.get_reply()
        # Please check -> https://github.com/centricular/gstwebrtc-demos/issues/42
        offer = reply.get_value('offer')
        promise = Gst.Promise.new()
        self.webrtc.emit('set-local-description', offer, promise)
        promise.interrupt()
        self.send_sdp(offer.sdp, "offer")

    def on_answer_created(self, promise, _, __):

        print("answer created")
        promise.wait()
        reply = promise.get_reply()
        answer = reply.get_value('answer')
        promise = Gst.Promise.new()
        self.webrtc.emit('set-local-description', answer, promise)
        promise.interrupt()
        self.send_sdp(answer.sdp, "answer")

    def take_configuration(self, data):
        if (data['type'] == 'answer'):
            assert (self.webrtc)
            res, sdpmsg = GstSdp.SDPMessage.new()
            GstSdp.sdp_message_parse_buffer(
                bytes(data['sdp'].encode()), sdpmsg)
            answer = GstWebRTC.WebRTCSessionDescription.new(
                GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg)
            promise = Gst.Promise.new()
            self.webrtc.emit('set-remote-description', answer, promise)
            promise.interrupt()

        elif (data['type'] == 'offer'):
            self.start_pipeline("play")
            res, sdpmsg = GstSdp.SDPMessage.new()
            GstSdp.sdp_message_parse_buffer(
                bytes(data['sdp'].encode()), sdpmsg)
            offer = GstWebRTC.WebRTCSessionDescription.new(
                GstWebRTC.WebRTCSDPType.OFFER, sdpmsg)
            promise = Gst.Promise.new()
            self.webrtc.emit('set-remote-description', offer, promise)
            promise.interrupt()

            promise = Gst.Promise.new_with_change_func(
                self.on_answer_created, self.webrtc, None)
            self.webrtc.emit("create-answer", None, promise)

    def close_pipeline(self):
        print('Close Pipeline')
        self.pipe.set_state(Gst.State.NULL)
        self.pipe = None
        self.webrtc = None

    def stop(self):
        if WebRTCClient.ws_conn:
            super.ws_conn.close()
        WebRTCClient.ws_conn = None


def init_gstreamer():
    Gst.init(None)
    if not check_plugins():
        sys.exit(1)


def check_plugins():
    needed = ["opus", "vpx", "nice", "webrtc", "dtls", "srtp", "rtp",
              "rtpmanager", "videotestsrc", "audiotestsrc"]
    missing = list(
        filter(lambda p: Gst.Registry.get().find_plugin(p) is None, needed))
    if len(missing):
        print('Missing gstreamer plugins:', missing)
        return False
    return True

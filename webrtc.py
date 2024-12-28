from websockets.version import version as ws
from gi.repository import GstSdp
from gi.repository import GstWebRTC
from gi.repository import Gst
from gi.repository import GstVideo
import random
import ssl
import websockets
import asyncio
import os
import sys
import json
import argparse
import json
import pathlib
import numpy as np
from PIL import Image, ImageOps
import base64
from io import BytesIO

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
gi.require_version('GstSdp', '1.0')

# Folowwing pipeline is for CSI Live Camera
# PIPELINE_DESC = '''
#  nvarguscamerasrc ! nvvideoconvert ! queue ! vp8enc deadline=1 ! rtpvp8pay !
#  queue ! application/x-rtp,media=video,encoding-name=VP8,payload=96 ! webrtcbin name=sendrecv
# '''

# This one can be used for testing
PIPELINE_DESC = '''
 videotestsrc is-live=true pattern=ball ! videoconvert ! queue ! x264enc  speed-preset=veryfast tune=zerolatency key-int-max=1  ! rtph264pay !
 queue ! application/x-rtp,media=video,encoding-name=H264,payload=96 ! webrtcbin name=sendrecv  bundle-policy=max-bundle'''

PIPELINE_DESC = ''' webrtcbin name=sendrecv  bundle-policy=max-bundle ! fakesink sync=true'''

WEBSOCKET_URL = 'wss://ovh36.antmedia.io:5443/LiveApp/websocket'
print(WEBSOCKET_URL)


class WebRTCClient:
    def __init__(self, id):
        self.id = id
        self.conn = None
        self.pipe = None
        self.webrtc = None
        self.peer_id = None
        self.server = WEBSOCKET_URL

    async def connect(self):
        print('Client Connect')
        self.conn = await websockets.connect(self.server, ssl=True)
        await self.play()

    async def publish(self):
        await self.conn.send('{"command":"publish","streamId":"' + self.id + '", "token":"null","video":true,"audio":true}')

    async def play(self):
        await self.conn.send('{"command":"play","streamId":"' + self.id + '", "token":"null"}')

    def send_sdp(self, sdp, type):
        print('Send SDP ' + type)
        sdp = sdp.as_text()
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.conn.send(
            '{"command":"takeConfiguration", "streamId": "' + self.id + '", "type": "' + type + '", "sdp": "' + sdp + '"}'))
        print(sdp)
        loop.close()

    def on_negotiation_needed(self, element):
        print('Negotiation Needed')
        promise = Gst.Promise.new_with_change_func(
            self.on_offer_created, element, None)
        element.emit('create-offer', None, promise)

    def send_ice_candidate_message(self, _, mlineindex, candidate):
        data = '{"command":"takeCandidate","streamId":"' + self.id + '","label":' + \
            str(mlineindex) + ', "id":"' + str(mlineindex) + \
            '" "candidate":"' + str(candidate) + '"}'
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.conn.send(data))
        loop.close()

    def on_incoming_decodebin_stream(self, _, pad):
        print('Incoming Decodebin Stream')
        if not pad.has_current_caps():
            print(pad, 'has no caps, ignoring')
            return
        caps = pad.get_current_caps()
        s = caps
        name = s.to_string()

        if name.startswith('video'):
            print("video stream recieved")
            q = Gst.ElementFactory.make('queue')
            conv = Gst.ElementFactory.make('videoconvert')
            capsfilter = Gst.ElementFactory.make("capsfilter")
            rgbcaps = Gst.caps_from_string("video/x-raw,format=RGB")
            capsfilter.set_property("caps", rgbcaps)
            sink = Gst.ElementFactory.make('appsink')
            sink.set_property("emit-signals", True)
            sink.connect("new-sample", self.on_decoded_video_buffer)

            self.pipe.add(q)
            self.pipe.add(conv)
            self.pipe.add(capsfilter)
            self.pipe.add(sink)
            self.pipe.sync_children_states()
            pad.link(q.get_static_pad('sink'))

            q.link(conv)
            conv.link(capsfilter)
            capsfilter.link(sink)

        elif name.startswith('audio'):
            print("audio stream recieved")
            q = Gst.ElementFactory.make('queue')
            conv = Gst.ElementFactory.make('audioconvert')
            resample = Gst.ElementFactory.make('audioresample')
            sink = Gst.ElementFactory.make('appsink')
            sink.set_property("emit-signals", True)
            sink.connect("new-sample", self.on_decoded_audio_buffer)

            self.pipe.add(q)
            self.pipe.add(conv)
            self.pipe.add(resample)
            self.pipe.add(sink)

            self.pipe.sync_children_states()
            pad.link(q.get_static_pad('sink'))
            q.link(conv)
            conv.link(resample)
            resample.link(sink)

    def on_decoded_audio_buffer(self, sink):
        print("decoded audio buffer")
        sample = sink.emit("pull-sample")
        gst_buffer = sample.get_buffer()

        if not gst_buffer:
            print("failed to get buffer")
        gst_buffer

        (result, mapinfo) = gst_buffer.map(Gst.MapFlags.READ)

        assert result

        return Gst.PadProbeReturn.OK

    def on_decoded_video_buffer(self, sink):
        print("decoded video buffer")
        sample = sink.emit("pull-sample")
        gst_buffer = sample.get_buffer()

        caps = sample.get_caps()
        structure = caps.get_structure(0)
        width = structure.get_int("width")[1]
        height = structure.get_int("height")[1]
        format = structure.get_string("format")
        print(width, height, format)

        if not gst_buffer:
            print("failed to get buffer")
        gst_buffer

        (result, mapinfo) = gst_buffer.map(Gst.MapFlags.READ)
        assert result
        numpy_frame = np.ndarray(
            shape=(height, width, 3),
            dtype=np.uint8,
            buffer=mapinfo.data)
        img = Image.fromarray(numpy_frame)
        img.save("test.jpeg")

        gst_buffer.unmap(mapinfo)

        return Gst.FlowReturn.OK

    def on_incoming_stream(self, _, pad):
        print('on_incoming_stream')
        if pad.direction != Gst.PadDirection.SRC:
            return
        decodebin = Gst.ElementFactory.make('decodebin')
        self.pipe.add(decodebin)
        decodebin.connect('pad-added', self.on_incoming_decodebin_stream)
        decodebin.sync_state_with_parent()
        self.webrtc.link(decodebin)

    def start_pipeline(self, mode):
        print('Creating WebRTC Pipeline')
        self.pipe = Gst.parse_launch(PIPELINE_DESC)
        self.webrtc = self.pipe.get_by_name('sendrecv')
        if (mode == "publish"):
            self.webrtc.connect('on-negotiation-needed',
                                self.on_negotiation_needed)
        self.webrtc.connect('on-ice-candidate',
                            self.send_ice_candidate_message)
        self.webrtc.connect('pad-added', self.on_incoming_stream)
        self.pipe.set_state(Gst.State.PLAYING)

    def notification(self, data):
        if (data['definition'] == 'publish_started'):
            print('Publish Started')
        else:
            print(data['definition'])

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
        print(reply)
        answer = reply.get_value('answer')
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

    async def loop(self):
        print('Inititialized')
        assert self.conn
        async for message in self.conn:

            data = json.loads(message)

            print('Message: ' + data['command'], data)

            if (data['command'] == 'start'):
                self.start_pipeline("publish")
            elif (data['command'] == 'takeCandidate'):
                self.take_candidate(data)
            elif (data['command'] == 'takeConfiguration'):
                self.take_configuration(data)
            elif (data['command'] == 'notification'):
                self.notification(data)
            elif (data['command'] == 'error'):
                print('Message: ' + data['definition'])

        self.close_pipeline()
        return 0

    async def stop(self):
        if self.conn:
            await self.conn.close()
        self.conn = None


def check_plugins():
    needed = ["opus", "vpx", "nice", "webrtc", "dtls", "srtp", "rtp",
              "rtpmanager", "videotestsrc", "audiotestsrc"]
    missing = list(
        filter(lambda p: Gst.Registry.get().find_plugin(p) is None, needed))
    if len(missing):
        print('Missing gstreamer plugins:', missing)
        return False
    return True


if __name__ == '__main__':
    Gst.init(None)
    if not check_plugins():
        sys.exit(1)
    client = WebRTCClient('abcde')
    loop = asyncio.get_event_loop()
    loop.run_until_complete(client.connect())
    res = loop.run_until_complete(client.loop())
    sys.exit(res)

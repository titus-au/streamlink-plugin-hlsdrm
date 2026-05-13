from __future__ import annotations

import re
import base64

from typing import Literal, Self, ClassVar
from requests import Response

from streamlink.exceptions import PluginError, FatalPluginError
from streamlink.logger import getLogger
from streamlink.plugin import Plugin, pluginmatcher, pluginargument
from streamlink.plugin.plugin import LOW_PRIORITY, parse_params
from streamlink.session import Streamlink
from streamlink.stream.ffmpegmux import FFMPEGMuxer
from streamlink.stream.hls import HLSStream, HLSStreamReader, HLSStreamWriter, HLSStreamWorker, MuxedHLSStream
from streamlink.stream.hls.segment import HLSSegment, HLSPlaylist
from streamlink.stream.hls.m3u8 import M3U8Parser, M3U8
from streamlink.utils.url import update_scheme


log = getLogger(__name__)

HLSDRM_OPTIONS = [
    "decryption-key",
]

@pluginmatcher(
    re.compile(r"hlsdrm(?:variant)?://(?P<url>\S+)(?:\s(?P<params>.+))?$"),
)
@pluginmatcher(
    priority=LOW_PRIORITY,
    pattern=re.compile(
        # URL with explicit scheme, or URL with implicit HTTPS scheme and a path
        r"(?P<url>[^/]+/\S+\.m3u8(?:\?\S*)?)(?:\s(?P<params>.+))?$",
        re.IGNORECASE,
    ),
)
@pluginargument(
    "decryption-key",
    type="comma_list",
    help="Decryption key(s) to be passed to ffmpeg."
)

class HLSPluginDRM(Plugin):
    def _get_streams(self):
        data = self.match.groupdict()
        url = update_scheme("https://", str(data.get("url", "")), force=False)
        params = parse_params(data.get("params"))
        log.debug(f"URL={url}; params={params}")

        # process and store plugin options before passing streams back
        for option in HLSDRM_OPTIONS:
            if option == 'decryption-key':
                if self.get_option('decryption-key'):
                    self.session.options[option] = self._process_keys()
            else:
                self.session.options[option] = self.get_option(option)

        self.session.set_option("stream-passthrough-encrypted", True)

        return HLSStreamDRM.parse_variant_playlist(self.session, url, **params)


    def _process_keys(self):
        keys = self.get_option('decryption-key')
        # if a colon separated key is given, assume its kid:key and take the
        # last component after the colon
        return_keys = []
        for k in keys:
            key = k.split(':')
            key_len = len(key[-1])
            log.debug('Decryption Key %s has %s digits', key[-1], key_len)
            if key_len in (21, 22, 23, 24):
                # key len of 21-24 may mean a base64 key was provided, so we 
                # try and decode it
                log.debug("Decryption key length is too short to be hex and looks like it might be base64, so we'll try and decode it..")
                b64_string = key[-1]
                padding = 4 - (len(b64_string) % 4)
                b64_string = b64_string + ("=" * padding)
                b64_key = base64.urlsafe_b64decode(b64_string).hex()
                if b64_key:
                    key = [b64_key]
                    key_len = len(b64_key)
                    log.debug('Decryption Key (post base64 decode) is %s and has %s digits', key[-1], key_len)
            if key_len == 32:
                # sanity check that it's a valid hex string
                try:
                    int(key[-1], 16)
                except ValueError as err:
                    raise FatalPluginError(f"Expecting 128bit key in 32 hex digits, but the key contains invalid hex.")
            elif key_len != 32:
                raise FatalPluginError(f"Expecting 128bit key in 32 hex digits.")
            return_keys.append(key[-1])
        return return_keys

class FFMPEGMuxerDRM(FFMPEGMuxer):
    '''
    Inherit and extend the FFMPEGMuxer class to pass decryption keys
    to ffmpeg

    We build a list of keys to use based on the value of command line option
    --dashdrm-decryption-keys. If only 1 key is given, it's used for
    all streams. If more than 1 key is given, the first key is used for
    video, and the remaining keys used for remaining streams. If the number
    of keys given is less than the number of streams, keys are looped
    starting from the first key after the video key. This will basically
    mean if you have a key for video, and a key for the rest of the streams
    you just need to specify 2 keys, but alternatively you can provide a
    different key for every single stream if needed
    '''

    @classmethod
    def _get_keys(cls, session):
        keys=[]
        if session.options.get("decryption-key"):
            keys = session.options.get("decryption-key")
            # If only 1 key is given, then we use that also for all remaining
            # streams
            if len(keys) == 1:
                keys.extend(keys)
        log.debug('Decryption Keys %s', keys)
        return keys

    def __init__(self, session, *streams, **options):
        super().__init__(session, *streams, **options)
        # if a decryption key is set, we rebuild the ffmpeg command list
        # to include the key before specifying the input stream
        keys = self._get_keys(session)
        key = 0
        # Build new ffmpeg command list
        old_cmd = self._cmd.copy()
        self._cmd = []
        while len(old_cmd) > 0:
            cmd = old_cmd.pop(0)
            if keys and cmd == "-i":
                _ = old_cmd.pop(0)
                self._cmd.extend(["-decryption_key", keys[key]])
                key += 1
                # If we had more streams than keys, start with the first
                # audio key again
                if key == len(keys):
                    key = 1
                self._cmd.extend([cmd, _])
                self._cmd.extend(['-thread_queue_size', '4096'])
            else:
                self._cmd.append(cmd)
        #self._cmd.extend(["-report"])
        log.debug("Updated ffmpeg command %s", self._cmd)

class HLSStreamWriterDRM(HLSStreamWriter):
    reader: HLSStreamReaderDRM
    stream: HLSStreamDRM

    def _write(self, segment: HLSSegment, result: Response, is_map: bool):
        key = segment.map.key if is_map and segment.map else segment.key
        if key and key.method == "AES-128":
            log.debug("Key Method is AES-128, we will let streamlink to try and decrypt.")
            self.passthrough_encrypted = False
        super()._write(segment, result, is_map,)

class HLSStreamWorkerDRM(HLSStreamWorker):
    reader: HLSStreamReaderDRM
    writer: HLSStreamWriterDRM
    stream: HLSStreamDRM

class HLSStreamReaderDRM(HLSStreamReader):
    __worker__ = HLSStreamWorkerDRM
    __writer__ = HLSStreamWriterDRM

    worker: HLSStreamWorkerDRM
    writer: HLSStreamWriterDRM
    stream: HLSStreamDRM

class HLSStreamDRM(HLSStream):
    __shortname__ = "hlsdrm"
    __reader__: ClassVar[type[HLSStreamReaderDRM]] = HLSStreamReaderDRM

    @classmethod
    def parse_variant_playlist(
        cls,
        session: Streamlink,
        url: str,
        name_key: str = "name",
        name_prefix: str = "",
        check_streams: bool | Literal["playlists", "segments"] = False,
        force_restart: bool = False,
        name_fmt: str | None = None,
        start_offset: float = 0,
        duration: float | None = None,
        **kwargs,
    ) -> dict[str, Self | MuxedHLSStream[Self]]:
        streams = super().parse_variant_playlist(session=session,
                                                url=url,
                                                name_key=name_key,
                                                name_prefix=name_prefix,
                                                check_streams=check_streams,
                                                force_restart=force_restart,
                                                name_fmt=name_fmt,
                                                start_offset=start_offset,
                                                duration=duration,
                                                **kwargs)
        if not streams:
            log.debug ('No streams')
            return {"live": MuxedHLSStream(session, 
                                            video=url,
                                            audio=None,
                                            **kwargs)}

        new_streams = {}
        for name, stream in streams.items():
            if isinstance(stream, MuxedHLSStream):
                new_streams[name] = stream
            else:
                muxed_stream = MuxedHLSStream(
                                stream.session,
                                video = stream.url,
                                audio = None,
                                hlsstream=cls,
                                multivariant=stream.multivariant,
                                start_offset=stream.start_offset,
                                duration=stream.duration,
                                **kwargs,
                                )
                new_streams[name] = muxed_stream
        return new_streams



__plugin__ = HLSPluginDRM
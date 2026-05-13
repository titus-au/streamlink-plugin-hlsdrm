# streamlink-plugin-hlsdrm

A [streamlink](https://github.com/streamlink/streamlink) plugin that extends the standard streamlink hls plugin to support DRM streams using SAMPLE-AES and clearkeys. 

This is a reimplementation of [hlsdrm](https://github.com/jordandalley/dispatchwrapparr/blob/main/drmplugins/hlsdrm.py) by Jordan Dalley which in turn was originally based on [streamlink-plugin-dashdrm](https://github.com/titus-au/streamlink-plugin-dashdrm).


# Install and Use

To use this plugin, you need to utilise streamlink's plugin [sideload](https://streamlink.github.io/latest/cli/plugin-sideloading.html) capability. Download the plugin source by cloning the repository, or just downloading the plugin file (hlsdrm.py) and either place it in your streamlink plugins sideload directory, or put in a new directory and specify the path when executing streamlink with --plugin-dir <path_of_hlsdrm.py>.

Install using git by typing:
```sh
git clone https://github.com/titus-au/streamlink-plugin-hlsdrm.git
```
To update the plugin using git, change into the directory where you had cloned the plugin, then type:
```sh
git pull
```

To make use of the plugin, add dashdrm:// in front of the url.
```sh
streamlink --plugin-dir /path/to/dashdrm/plugin --default-stream best --url hlsdrm://http://abc.def/xyz.m3u8
```

# Parameters

The plugin accepts a number of optional parameters:
<TABLE>
  <TR>
    <TH>Option</TH>
    <TH>Description</TH>
  </TR>
  <TR>
    <TD>--hlsdrm-decryption-key &ltkey in hex or base64&gt</TD>
    <TD>This is a comma seperated list of decryption keys to be passed to ffmpeg. If only one key is given, then all streams will use this key. If 2 keys are given, then the video stream will use the first key, and all remaining streams (eg audio streams) will use the second key. If more than 2 keys are given, then the video stream will use the first key, and the second stream will use the second key, the third stream will use the third key etc. If more streams than keys are given, keys will be looped starting with the second key. The keys need to be in hex or base64, either just the key by itself, or in the format of kid:key (although the kid is not used)</TD>
  </TR>

</TABLE>

# Disclaimer

<LI>Use of this code to decrypt DRM is purely for academic purposes. You should not use this code for any illegal purposes and I take no responsibility for your actions</LI>
<LI>This plugin is reliant on streamlink 8.4.0 which implemented the --stream-passthrough-encrypted command line option</LI>
<LI>This plugin turns on the --stream-passthrough-encrypted option, which in turn will disable AES-128 enrypted HLS streams with embedded keys</LI>
<LI>This code has basically not been tested, so consider it pre-alpha software</LI>


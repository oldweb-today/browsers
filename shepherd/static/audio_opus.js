var AudioOpus = function(browser_info, init_params) {

    var audioInit = false;
    var browser_info;
    var audioWS = null;
    var audioCount = 0;
    var minLatency = 0.2; // 200ms
    var maxLatency = 0.5  // 500ms

    init_params = init_params || {};


    function start() {
        if (audioInit) {
            return;
        }

        audioInit = true;

        restartAudio();
    }

    function stop() {
        if (audioWS) {
            console.log("Close Audio");
            audioWS.close();
        }
    }

    function restartAudio() {
        if (audioWS && audioWS.initing) {
            return;
        }

        stop();

        audioWS = new WSAudio(get_ws_url(browser_info));
    }

    function get_ws_url(browser_info) {
        var ws_url;
        ws_url = (window.location.protocol == "https:" ? "wss:" : "ws:");

        if (init_params.proxy_ws) {
            var audio_port = browser_info.cmd_host.split(":")[1];
            ws_url += window.location.host + "/" + init_params.proxy_ws + audio_port;
            ws_url += "&count=" + audioCount++;
        } else {
            ws_url += browser_info.cmd_host + "/audio_ws";
        }

        return ws_url;
    }

    function get_http_url(browser_info) {
        var audio_port = browser_info.cmd_host.split(":")[1];
        var http_url = window.location.origin + "/_audio.webm?port=" + audio_port;
        http_url += "&count=" + audioCount++;
        return http_url;
    }



    function WSAudio(ws_url) {
        var MIME_TYPE = 'audio/webm; codecs="opus"';

        var MAX_BUFFERS = 250;
        var MIN_START_BUFFERS = 10;

        var MAX_ERRORS = 1;

        this.buffQ = [];
        this.buffCount = 0;

        this.ws_url = ws_url;
        this.lastTs = undefined;
        this.ws = null;

        this.errCount = 0;

        this.initing = false;
        this.updating = false;

        this.audio = null;
        this.mediasource = null;
        this.buffer = null;

        this.buffSize = 0;

        this.latencyController = null;

        this.initAudio = function() {

            this.latencyController = setInterval(this.latencyController.bind(this), 250);

            if (this.initing) {
                console.log("already initing");
                return;
            }

            this.initing = true;
            console.log("Init Audio");

            this.mediasource = new MediaSource();
            this.mediasource.addEventListener("sourceopen", this.sourceOpen.bind(this));

            this.mediasource.addEventListener("error", (function(event) {
                this.audioError("MediaSource Error", event);
            }).bind(this));

            this.audio = new Audio();
            this.audio.src = URL.createObjectURL(this.mediasource);
            this.audio.autoplay = true;
            this.audio.load();
            this.audio.play().catch(function() { });
        }

        this.sourceOpen = function() {
            if (this.mediasource.sourceBuffers.length) {
                console.log("source already open");
                return;
            }

            var buffer = null;

            try {
                buffer = this.mediasource.addSourceBuffer(MIME_TYPE);
            } catch (e) {
                console.log("Opening Source Error: " + e);
                return;
            }

            buffer.mode = "sequence";
            //buffer.timestampOffset = 0;

            buffer.addEventListener("error", (function(event) {
                this.audioError("buffer error: " + (this.buffCount), event);
            }).bind(this));

            buffer.addEventListener("updateend", this.updateNext.bind(this));

            this.buffer = buffer;
            this.initing = false;

            this.initWs();
        };

        this.close = function() {
            console.log("Closing Audio");
            try {
                if (this.latencyController) {
                    clearInterval(this.latencyController);
                }

                if (this.mediasource) {
                    this.mediasource.removeSourceBuffer(this.buffer);
                    if (this.mediasource.readyState == "open") {
                        this.mediasource.endOfStream();
                    }
                }
                this.buffer = null;

            } catch(e) {
                console.log("Error Closing: " + e);
            }
            this.mediasource = null;

            try {
                if (this.audio) {
                    this.audio.pause();
                }
                this.audio = null;
            } catch (e) {
                console.log("Error Closing: " + e);
            }

            if (this.ws) {
                console.log("Closing websocket");
                try {
                    this.ws.close();
                } catch(e) {}

                this.ws = null;
            }
        }

        this.valid = function(lastTs) {
            if (this.errCount > 0) {
                return false;
            }

            if (!this.buffer) {
                return false;
            }

            // if ws update hasn't changed
            if (lastTs && this.lastTs && (this.lastTs <= lastTs)) {
                return false;
            }

            return true;
        }

        this.mergeBuffers = function() {
            var merged;

            if (this.buffQ.length == 1) {
                merged = this.buffQ[0];
            } else {
                merged = new Uint8Array(this.buffSize);

                var length = this.buffQ.length;
                var offset = 0;

                for (var i = 0; i < length; i++) {
                    var curr = this.buffQ[i];
                    if (curr.length <= 0) {
                        continue;
                    }
                    merged.set(curr, offset);
                    offset += curr.length;
                }
            }

            this.buffQ = [];
            this.buffCount++;
            return merged;
        }

        this.updateNext = function() {
            if (this.initing || this.updating || (this.errCount >= MAX_ERRORS) || !this.buffQ.length || !this.buffer || this.buffer.updating) {
                return;
            }

            if (this.buffCount == 0 && this.buffQ.length < MIN_START_BUFFERS) {
                return;
            }

            this.updating = true;

            try {
                var merged = this.mergeBuffers();
                this.buffer.appendBuffer(merged);
                this.buffSize -= merged.length;
                this.buffSize = 0;
                this.errCount = 0;
            } catch (e) {
                this.audioError("Error Adding Buffer: " + e);
            }
            this.updating = false;
        }

        this.latencyController = function() {
            // take care about latency
            try {
                var latency = this.audio.buffered.end(0) - this.audio.currentTime;
                if (latency > maxLatency) {
                    this.audio.currentTime = this.audio.buffered.end(0) - minLatency;
                    console.log("Audio has been seeked by ", Math.round((latency - minLatency) * 1000), " ms");
                }

            } catch(e) {

            }
        }

        this.audioError = function(msg, event) {
            if (this.audio.error) {
                console.log(msg);
                console.log(this.audio.error);
                //console.log("num processed: " + this.buffCount);
                this.errCount += 1;
                if (this.errCount == 1) {
                    setTimeout(restartAudio, 3000);
                }
            }
        }

        this.queue = function(buffer) {
            if (this.buffSize > 20000) {
                if (this.buffCount > 0) {
                    res = this.buffQ.shift();
                    this.buffSize -= res.length;
                    console.log("dropping old buffers");
                } else {
                    // don't drop the starting buffers
                    console.log("dropping new buffers");
                    this.updateNext();
                    return;
                }
            }

            buffer = new Uint8Array(buffer);
            this.buffQ.push(buffer);
            this.buffSize += buffer.length;

            this.updateNext();
        }

        this.initWs = function() {
            try {
                this.ws = new WebSocket(this.ws_url, "binary");
            } catch (e) {
                this.audioError("WS Open Failed");
            }

            this.ws.binaryType = 'arraybuffer';
            this.ws.addEventListener("open", ws_open);
            this.ws.addEventListener("close", ws_close);
            this.ws.addEventListener("message", ws_message);
            this.ws.addEventListener('error', ws_error);
        }

        var ws_open = function(event) {
            if (!audioWS || this != audioWS.ws) {
                return;
            }

            this.send("ready");
        }

        var ws_message = function(event) {
            if (!audioWS || this != audioWS.ws) {
                return;
            }

            if (audioWS.errCount < MAX_ERRORS) {
                audioWS.queue(event.data);
            }
        }

        var ws_error = function() {
            if (!audioWS || this != audioWS.ws) {
                return;
            }

            audioWS.audioError("WS Error");
        }

        var ws_close = function() {
            if (!audioWS || this != audioWS.ws) {
                return;
            }

            audioWS.audioError("WS Close");
        }

        this.initAudio();
    }

    return {"start": start,
            "stop": stop,
            "restart": restartAudio,
            "getAudio": function () {return  audioWS.audio;},
    }
};





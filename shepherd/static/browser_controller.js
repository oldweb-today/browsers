var CBrowser = function(target_div, init_params) {
    var cmd_host = undefined;
    var vnc_host = undefined;

    var connected = false;

    var fail_count = 0;

    var rfb;
    var resizeTimeout;

    var end_time = undefined;
    var cid = undefined;
    var waiting_for_container = false;

    var api_prefix = init_params.api_prefix || "";
    var on_connect = init_params.on_connect;
    var static_prefix = init_params.static_prefix;

    function start() {
        if (!window.INCLUDE_URI) {
            if (!static_prefix) {
                static_prefix = "/static/";
            }

            window.INCLUDE_URI = static_prefix + "novnc/";

            $.getScript(window.INCLUDE_URI + "util.js", function() {
                // Load supporting scripts
                Util.load_scripts(["webutil.js", "base64.js", "websock.js", "des.js",
                                   "keysymdef.js", "keyboard.js", "input.js", "display.js",
                                   "inflator.js", "rfb.js", "keysym.js"]);
            });
        }

        // Countdown updater
        //cid = setInterval(update_countdown, 1000);
        init_html(target_div);

        init_container();
    }

    function canvas() {
        return $("canvas", target_div);
    }

    function msgdiv() {
        return $("#browserMsg", target_div);
    }

    function screen() {
        return $("#noVNC_screen", target_div);
    }

    function init_html() {
        $(target_div).append($("<div>", {"id": "browserMsg", "class": "loading"}).text("Initializing Browser..."));
        $(target_div).append($("<div>", {"id": "noVNC_screen"}).append("<canvas>"));

        canvas().hide();

        screen().blur(lose_focus);
        screen().mouseleave(lose_focus);

        screen().mouseenter(grab_focus);
    }

    function init_container() {
        var params = {};

        // calculate dimensions
        var hh = $('header').height();
        var w = window.innerWidth * 0.96;
        var h = window.innerHeight - (25 + hh);

        params['width'] = Math.max(w, 800);
        params['height'] = Math.max(h, 600);
        params['width'] = parseInt(params['width'] / 16) * 16;
        params['height'] = parseInt(params['height'] / 16) * 16;

        params['reqid'] = window.reqid;

        function send_request() {
            if (waiting_for_container) {
                return;
            }

            waiting_for_container = true;

            var init_url = api_prefix + "/init_browser?" + $.param(params);

            $.getJSON(init_url, handle_browser_response)
            .fail(function() {
                fail_count++;

                if (fail_count <= 3) {
                    msgdiv().text("Retrying browser init...");
                    setTimeout(send_request, 5000);
                } else {
                    msgdiv().text("Failed to init browser... Please try again later");
                }
                msgdiv().show();
            }).complete(function() {
                waiting_for_container = false;
            });
        }

        send_request();
    }

    function handle_browser_response(data) {
        qid = data.id;

        if (data.cmd_host && data.vnc_host) {
            cmd_host = data.cmd_host;
            vnc_host = data.vnc_host;

            if (on_connect) {
                on_connect(data);
            }

            window.setTimeout(try_init_vnc, 1000);

        } else if (data.queue != undefined) {
            var msg = "Waiting for empty slot... ";
            if (data.queue == 0) {
                msg += "<b>You are next!</b>";
            } else {
                msg += "At most <b>" + data.queue + " user(s)</b> ahead of you";
            }
            msgdiv().html(msg);

            window.setTimeout(send_request, 3000);
        }
    }

    function try_init_vnc() {
        var res = do_vnc();
        if (!res) {
            window.setTimeout(try_init_vnc, 1000);
        }
    }

    function lose_focus() {
        if (!rfb) return;
        rfb.get_keyboard().set_focused(false);
        rfb.get_mouse().set_focused(false);
    }

    function grab_focus() {
        if (!rfb) return;
        rfb.get_keyboard().set_focused(true);
        rfb.get_mouse().set_focused(true);
    }

    function UIresize() {
        if (WebUtil.getQueryVar('resize', false)) {
            var innerW = window.innerWidth;
            var innerH = window.innerHeight;
            //var controlbarH = $D('noVNC_status_bar').offsetHeight;
            var controlH = 0;
            var padding = 5;
            if (innerW !== undefined && innerH !== undefined)
                rfb.setDesktopSize(innerW, innerH - controlbarH - padding);
        }
    }

    function clientPosition() {
        var hh = $('header').height();
        var c = canvas();
        var ch = c.height();
        var cw = c.width();
        c.css({
            marginLeft: (window.innerWidth - cw)/2,
            marginTop: (window.innerHeight - (hh + ch + 25))/2
        });
    }

    function clientResize() {
        var hh = $('header').height();
        var w = Math.round(window.innerWidth * 0.96);
        var h = Math.round(window.innerHeight - (25 + hh));

        if (rfb) {
            var s = rfb._display.autoscale(w, h);
            rfb.get_mouse().set_scale(s);
        }
    }

    function FBUComplete(rfb, fbu) {
        UIresize();
        clientPosition();
        rfb.set_onFBUComplete(function() { });
    }

    function onVNCCopyCut(rfb, text)
    {
        //$("#clipcontent").text(text);
    }

    function do_vnc() {
        try {
            rfb = new RFB({'target':       canvas()[0],
                           'encrypt':      WebUtil.getQueryVar('encrypt',
                                                               (window.location.protocol === "https:")),
                           'repeaterID':   WebUtil.getQueryVar('repeaterID', ''),
                           'true_color':   WebUtil.getQueryVar('true_color', true),
                           'local_cursor': WebUtil.getQueryVar('cursor', true),
                           'shared':       WebUtil.getQueryVar('shared', true),
                           'view_only':    WebUtil.getQueryVar('view_only', false),
                           'onUpdateState':  updateState,
                           'onClipboard':    onVNCCopyCut,
                           'onFBUComplete':  FBUComplete});
        } catch (exc) {
            //updateState(null, 'fatal', null, 'Unable to create RFB client -- ' + exc);
            console.warn(exc);
            return false; // don't continue trying to connect
        }

        var hostport = vnc_host.split(":");
        var host = hostport[0];
        var port = hostport[1];
        var password = "secret";
        var path = "websockify";

        try {
            rfb.connect(host, port, password, path);
        } catch (exc) {
            console.warn(exc);
            return false;
        }

        return true;
    }

    function updateState(rfb, state, oldstate, msg) {
        if (state == "failed" || state == "fatal") {
            // if not connected yet, attempt to connect until succeed
            if (!connected) {
                window.setTimeout(do_vnc, 1000);
            }
        } else if (state == "disconnected") {
            if (connected) {
                connected = false;
                canvas().hide();
                msgdiv().show();

                init_container();
            }
        } else if (state == "normal") {
            canvas().show();
            msgdiv().hide();

            connected = true;
            fail_count = 0;
        }
    }

    window.onresize = function () {
        // When the window has been resized, wait until the size remains
        // the same for 0.5 seconds before sending the request for changing
        // the resolution of the session
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(function(){
            UIresize();
            clientResize();
            clientPosition();
        }, 500);
    };

    function update_countdown() {
        if (!end_time) {
            return;
        }
        var curr = Math.floor(new Date().getTime() / 1000);
        var secdiff = end_time - curr;

        if (secdiff < 0) {
            window.location.href = window.location.origin + "/";
            return;
        }

        var min = Math.floor(secdiff / 60);
        var sec = secdiff % 60;
        if (sec <= 9) {
            sec = "0" + sec;
        }
        if (min <= 9) {
            min = "0" + min;
        }

        $("#expire").text(min + ":" + sec);
    }

    start();
};





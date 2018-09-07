define(["exports", "../lib/vendor/pako/lib/zlib/inflate.js", "../lib/vendor/pako/lib/zlib/zstream.js"], function (exports, _inflate2, _zstream) {
    "use strict";

    Object.defineProperty(exports, "__esModule", {
        value: true
    });

    var _zstream2 = _interopRequireDefault(_zstream);

    function _interopRequireDefault(obj) {
        return obj && obj.__esModule ? obj : {
            default: obj
        };
    }

    function _classCallCheck(instance, Constructor) {
        if (!(instance instanceof Constructor)) {
            throw new TypeError("Cannot call a class as a function");
        }
    }

    var _createClass = function () {
        function defineProperties(target, props) {
            for (var i = 0; i < props.length; i++) {
                var descriptor = props[i];
                descriptor.enumerable = descriptor.enumerable || false;
                descriptor.configurable = true;
                if ("value" in descriptor) descriptor.writable = true;
                Object.defineProperty(target, descriptor.key, descriptor);
            }
        }

        return function (Constructor, protoProps, staticProps) {
            if (protoProps) defineProperties(Constructor.prototype, protoProps);
            if (staticProps) defineProperties(Constructor, staticProps);
            return Constructor;
        };
    }();

    var Inflate = function () {
        function Inflate() {
            _classCallCheck(this, Inflate);

            this.strm = new _zstream2.default();
            this.chunkSize = 1024 * 10 * 10;
            this.strm.output = new Uint8Array(this.chunkSize);
            this.windowBits = 5;

            (0, _inflate2.inflateInit)(this.strm, this.windowBits);
        }

        _createClass(Inflate, [{
            key: "inflate",
            value: function inflate(data, flush, expected) {
                this.strm.input = data;
                this.strm.avail_in = this.strm.input.length;
                this.strm.next_in = 0;
                this.strm.next_out = 0;

                // resize our output buffer if it's too small
                // (we could just use multiple chunks, but that would cause an extra
                // allocation each time to flatten the chunks)
                if (expected > this.chunkSize) {
                    this.chunkSize = expected;
                    this.strm.output = new Uint8Array(this.chunkSize);
                }

                this.strm.avail_out = this.chunkSize;

                (0, _inflate2.inflate)(this.strm, flush);

                return new Uint8Array(this.strm.output.buffer, 0, this.strm.next_out);
            }
        }, {
            key: "reset",
            value: function reset() {
                (0, _inflate2.inflateReset)(this.strm);
            }
        }]);

        return Inflate;
    }();

    exports.default = Inflate;
});
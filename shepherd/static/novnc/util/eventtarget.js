define(["exports"], function (exports) {
   "use strict";

   Object.defineProperty(exports, "__esModule", {
      value: true
   });

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

   var EventTargetMixin = function () {
      function EventTargetMixin() {
         _classCallCheck(this, EventTargetMixin);

         this._listeners = null;
      }

      _createClass(EventTargetMixin, [{
         key: "addEventListener",
         value: function addEventListener(type, callback) {
            if (!this._listeners) {
               this._listeners = new Map();
            }
            if (!this._listeners.has(type)) {
               this._listeners.set(type, new Set());
            }
            this._listeners.get(type).add(callback);
         }
      }, {
         key: "removeEventListener",
         value: function removeEventListener(type, callback) {
            if (!this._listeners || !this._listeners.has(type)) {
               return;
            }
            this._listeners.get(type).delete(callback);
         }
      }, {
         key: "dispatchEvent",
         value: function dispatchEvent(event) {
            var _this = this;

            if (!this._listeners || !this._listeners.has(event.type)) {
               return true;
            }
            this._listeners.get(event.type).forEach(function (callback) {
               callback.call(_this, event);
            }, this);
            return !event.defaultPrevented;
         }
      }]);

      return EventTargetMixin;
   }();

   exports.default = EventTargetMixin;
});
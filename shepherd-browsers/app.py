from gevent.monkey import patch_all; patch_all()

from shepherd.wsgi import create_app
from shepherd.shepherd import Shepherd

from shepherd.schema import Schema, fields

from shepherd.pool import FixedSizePool, PersistentPool

from redis import StrictRedis

from flask import request, render_template, Response

import os
import base64
import json


NETWORK_NAME = 'shep-browsers:{0}'
FLOCKS = 'flocks.yaml'

DEFAULT_POOL = 'fixed-pool'

DEFAULT_FLOCK = 'browsers-vnc'


# ============================================================================
def main():
    redis_url = os.environ.get('REDIS_BROWSER_URL', 'redis://localhost/0')

    redis = StrictRedis.from_url(redis_url, decode_responses=True)

    shepherd = Shepherd(redis, NETWORK_NAME)
    shepherd.load_flocks(FLOCKS)

    fixed_pool = FixedSizePool('fixed-pool', shepherd, redis,
                               duration=180,
                               max_size=5,
                               expire_check=30,
                               number_ttl=120)

    persist_pool = PersistentPool('auto-pool', shepherd, redis,
                                  duration=180,
                                  max_size=2,
                                  expire_check=30,
                                  grace_time=1)

    pools = {'fixed-pool': fixed_pool,
             'auto-pool': persist_pool}

    wsgi_app = create_app(shepherd, pools, name=__name__)
    init_routes(wsgi_app)
    return wsgi_app


# ============================================================================
class InitBrowserSchema(Schema):
    id = fields.String()
    ip = fields.String()
    audio = fields.String()
    vnc_pass = fields.String()
    cmd_port = fields.Int()
    vnc_port = fields.Int()


# ============================================================================
def init_routes(app):
    @app.route('/init_browser', methods=['GET'],
               resp_schema=InitBrowserSchema)
    def init_browser():
        reqid = request.args.get('reqid')

        width = request.args.get('width')
        height = request.args.get('height')
        audio = request.args.get('audio')

        environ = {}
        if width:
            environ['SCREEN_WIDTH'] = width

        if height:
            environ['SCREEN_HEIGHT'] = height

        if audio:
            environ['AUDIO_TYPE'] = audio

        # vnc password
        vnc_pass = base64.b64encode(os.urandom(21)).decode('utf-8')
        environ['VNC_PASS'] = vnc_pass

        res = app.get_pool(DEFAULT_POOL).start(reqid, environ=environ)

        if 'error' in res or 'queued' in res:
            return res

        browser_res = {'id': reqid,
                       'cmd_port': res['containers']['xserver']['ports']['cmd_port'],
                       'vnc_port': res['containers']['xserver']['ports']['vnc_port'],
                       'ip': res['containers']['browser']['ip'],
                       'vnc_pass': vnc_pass,
                       'audio': audio,
                      }

        return browser_res

    @app.route('/view/<browser>/<path:url>')
    @app.route('/view/<flock>/<browser>/<path:url>')
    def view(browser, url, flock=DEFAULT_FLOCK):
        # TODO: parse ts
        # ensure full url
        if request.query_string:
            url += '?' + request.query_string.decode('utf-8')

        env = {'URL': url,
               'IDLE_TIMEOUT': os.environ.get('IDLE_TIMEOUT')
              }

        opts = {}
        opts['overrides'] = {'browser': 'oldwebtoday/' + browser}
        opts['environ'] = env

        res = app.get_pool(DEFAULT_POOL).request(flock, opts)

        reqid = res.get('reqid')

        if not reqid:
            return Response('Error Has Occured: ' + str(res), status=400)

        return render_template('browser_embed.html', reqid=reqid)

    @app.route('/info/<reqid>', resp_schema=InitBrowserSchema)
    def info(reqid):
        res = app.get_pool(DEFAULT_POOL).start(reqid)
        return {'ip': res['containers']['browser']['ip']}


# ============================================================================
application = main()


if __name__ == '__main__':
    from gevent.pywsgi import WSGIServer
    WSGIServer(('0.0.0.0', 9020), application).serve_forever()

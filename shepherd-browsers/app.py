from gevent.monkey import patch_all; patch_all()

from shepherd.wsgi import create_app
from shepherd.shepherd import Shepherd

from shepherd.schema import Schema, fields

from shepherd.pool import FixedSizePool

from redis import Redis

from flask import request, render_template

import os


NETWORK_NAME = 'shep-browsers:{0}'
FLOCKS = 'browsers.yaml'


# ============================================================================
def main():
    redis_url = os.environ.get('REDIS_BROWSER_URL', 'redis://localhost/0')

    redis = Redis.from_url(redis_url, decode_responses=True)

    shepherd = Shepherd(redis, NETWORK_NAME)
    shepherd.load_flocks(FLOCKS)

    pool = FixedSizePool('fixed-pool', shepherd, redis,
                         duration=180,
                         max_size=5,
                         expire_check=30,
                         number_ttl=120)

    wsgi_app = create_app(shepherd, pool, name=__name__)
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

        #todo: set width/height in start
        width = request.args.get('width')
        height = request.args.get('height')

        res = app.pool.start(reqid)

        if 'error' in res:
            return res

        if 'queued' in res:
            return res

        browser_res = {'id': reqid,
                       'cmd_port': res['containers']['xserver']['ports']['cmd_port'],
                       'vnc_port': res['containers']['xserver']['ports']['vnc_port'],
                       'ip': res['containers']['browser']['ip'],
                       'vnc_pass': 'secret',
                       'audio': 'mp3'
                       }

        return browser_res

    @app.route('/view/<browser>/<path:url>')
    def view(browser, url):
        if request.query_string:
            url += '?' + request.query_string.decode('utf-8')

        env = {'URL': url,
               'IDLE_TIMEOUT': os.environ.get('IDLE_TIMEOUT')
              }

        opts = {}
        opts['overrides'] = {'browser': 'owt/' + browser}
        opts['environment'] = env

        res = app.pool.request('browsers', opts)

        return render_template('browser_embed.html', reqid=res.get('reqid'))


# ============================================================================
application = main()


if __name__ == '__main__':
    from gevent.pywsgi import WSGIServer
    WSGIServer(('0.0.0.0', 9020), application).serve_forever()

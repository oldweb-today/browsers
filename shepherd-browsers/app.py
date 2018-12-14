from gevent.monkey import patch_all; patch_all()

from shepherd.wsgi import create_app
from shepherd.shepherd import Shepherd

from shepherd.schema import Schema, fields, GenericResponseSchema
import marshmallow.utils

from shepherd.pool import FixedSizePool, PersistentPool

from redis import StrictRedis

from flask import request, render_template, Response

import os
import base64
import json
import traceback


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
                               duration=1800,
                               max_size=50,
                               expire_check=30,
                               number_ttl=120)

    persist_pool = PersistentPool('auto-pool', shepherd, redis,
                                  duration=1800,
                                  max_size=4,
                                  expire_check=30,
                                  grace_time=1)

    pools = {'fixed-pool': fixed_pool,
             'auto-pool': persist_pool}

    wsgi_app = create_app(shepherd, pools, name=__name__)

    browser_utils = BrowserShepherdUtils(shepherd.docker)

    init_routes(wsgi_app, browser_utils)
    return wsgi_app


# ============================================================================
class InitBrowserSchema(Schema):
    id = fields.String()
    ip = fields.String()
    audio = fields.String()
    vnc_pass = fields.String()
    cmd_port = fields.Int()
    vnc_port = fields.Int()
    queued = fields.Int()

class RequestBrowserSchema(GenericResponseSchema):
    id = fields.String()


class AnySchema(Schema):
    def __init__(self, *args, **kwargs):
        super(AnySchema, self).__init__(unknown=marshmallow.utils.INCLUDE)

    class Meta:
        unknown = marshmallow.utils.INCLUDE


# ============================================================================
class BrowserShepherdUtils():
    browser_image_prefix = 'oldwebtoday/'
    label_name = 'wr.shepherd_name'
    label_browser = 'wr.name'
    label_prefix = 'wr.'

    def __init__(self, docker_client):
        self.docker = docker_client

    def _browser_info(self, labels, include_icon=False):
        props = {}
        caps = []
        for n, v in labels.items():
            wr_prop = n.split(self.label_prefix)
            if len(wr_prop) != 2:
                continue

            name = wr_prop[1]

            if not include_icon and name == 'icon':
                continue

            props[name] = v

            if name.startswith('caps.'):
                caps.append(name.split('.', 1)[1])

        props['caps'] = ', '.join(caps)

        return props

    def get_browser_info(self, name, include_icon=False):
        tag = self.browser_image_prefix + name

        try:
            image = self.docker.images.get(tag)
            props = self._browser_info(image.labels, include_icon=include_icon)
            props['id'] = self._get_primary_id(image.tags)
            props['tags'] = image.tags
            return props

        except:
            traceback.print_exc()
            return {}

    def _get_primary_id(self, tags):
        if not tags:
            return None

        primary_tag = None
        for tag in tags:
            if not tag:
                continue

            if tag.endswith(':latest'):
                tag = tag.replace(':latest', '')

            if not tag.startswith(self.browser_image_prefix):
                continue

            # pick the longest tag as primary tag
            if not primary_tag or len(tag) > len(primary_tag):
                primary_tag = tag

        if primary_tag:
            return primary_tag[len(self.browser_image_prefix):]
        else:
            return None

    def load_avail_browsers(self, params=None):
        filters = {"dangling": False}

        if params:
            all_filters = []
            for k, v in params.items():
                if k not in ('short'):
                    all_filters.append(self.label_prefix + k + '=' + v)
            filters["label"] = all_filters
        else:
            filters["label"] = self.label_browser

        browsers = {}
        try:
            images = self.docker.images.list(filters=filters)

            for image in images:
                id_ = self._get_primary_id(image.tags)
                if not id_:
                    continue

                props = self._browser_info(image.labels)
                props['id'] = id_

                browsers[id_] = props

        except:
            traceback.print_exc()

        return browsers


# ============================================================================
def init_routes(app, browser_utils):
    def do_request_browser(browser, url=None, user_params=None, flock=DEFAULT_FLOCK):
        user_params = user_params or {}
        user_params['browser'] = browser_utils.browser_image_prefix + browser

        url = url or user_params.get('url')

        env = {'URL': url,
               #'IDLE_TIMEOUT': os.environ.get('IDLE_TIMEOUT')
              }

        opts = {}
        opts['overrides'] = {'browser': user_params['browser']}
        opts['environ'] = env
        opts['user_params'] = user_params

        res = app.get_pool(DEFAULT_POOL).request(flock, opts)

        return res

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
        vnc_pass = 'secret'#base64.b64encode(os.urandom(21)).decode('utf-8')
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

    @app.route('/attach/<reqid>')
    def attach(reqid):
        return render_template('browser_embed.html', reqid=reqid)

    @app.route('/view/<browser>/<path:url>')
    @app.route('/view/<flock>/<browser>/<path:url>')
    def view(browser, url, flock=DEFAULT_FLOCK):
        # TODO: parse ts
        # ensure full url
        if request.query_string:
            url += '?' + request.query_string.decode('utf-8')

        res = do_request_browser(browser, url=url, flock=flock)

        reqid = res.get('reqid')

        if not reqid:
            return Response('Error Has Occured: ' + str(res), status=400)

        return render_template('browser_embed.html', reqid=reqid)


    @app.route('/request_browser/<browser>', methods=['POST'],
               resp_schema=RequestBrowserSchema)
    def request_browser(browser):
        try:
            browser_data = browser_utils.get_browser_info(browser)
            if not browser_data:
                return {'error': 'browser_not_found'}

            res = do_request_browser(browser, user_params=request.json, flock=DEFAULT_FLOCK)

            reqid = res.get('reqid')

            if not reqid:
                return {'error': str(res)}

            return {'reqid': reqid,
                    'id': browser_data['id']}

        except Exception as e:
            traceback.print_exc()

            return {'error': traceback.format_exc()}

    @app.route('/info/<reqid>', resp_schema=InitBrowserSchema)
    def info(reqid):
        res = app.get_pool(DEFAULT_POOL).start(reqid)
        return {'ip': res['containers']['browser']['ip']}


    @app.route('/browsers')
    def list_browsers():
        """
        List all available browsers
        Query params can be used to filter on metadata properties
        """
        res = browser_utils.load_avail_browsers(request.args)
        return Response(json.dumps(res), mimetype='application/json')

    @app.route('/browsers/<name>/icon')
    def get_browser_icon(name):
        """
        Load icon for browser using wr.icon metadata
        """
        res = browser_utils.get_browser_info(name, True)
        if not res or 'icon' not in res:
            return Response('Browser or Icon Not Found: ' + str(name), status=404)

        return Response(base64.b64decode(res['icon'].split(',', 1)[-1]),
                        mimetype='image/png')


# ============================================================================
application = main()


if __name__ == '__main__':
    from gevent.pywsgi import WSGIServer
    WSGIServer(('0.0.0.0', 9020), application).serve_forever()

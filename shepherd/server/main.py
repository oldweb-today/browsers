import gevent.monkey; gevent.monkey.patch_all()
import gevent

from bottle import route, request, default_app, jinja2_view
from bottle import static_file, response, debug, HTTPError

import os
import base64

from server.controller.docker import DockerController


# ============================================================================
class Main(object):
    def __init__(self):
        self.dc = DockerController()

        self.event_loop_gevent = gevent.spawn(self.dc.event_loop)
        self.cleanup_gevent = gevent.spawn(self.dc.remove_expired_loop)

        self.application = default_app()

        debug(True)

        self.init_routes()

    def load_browser(self, browser, url):
        """ Load a given url with a specified browser
            No proxy settings are applied, browser should run in normal live mode
        """
        container_data = {
            'url': url,
            'browser': browser,
            'request_ts': 'now',
        }

        reqid = request.query.getunicode('reqid')
        if not reqid:
            reqid = self.dc.register_request(container_data)

        container_data['reqid'] = reqid

        return {'STATIC_PREFIX': '/static',
                'container_data': container_data,
                'audio': os.environ.get('AUDIO_TYPE', ''),
               }

    def request_browser(self, browser):
        try:
            browser_data = self.dc.get_browser_info(browser)
            if not browser_data:
                return {'error': 'Browser Not Found'}

            container_data = dict(request.forms.decode())
            container_data['browser'] = browser

            reqid = self.dc.register_request(container_data)

            return {'reqid': reqid,
                    'id': browser_data['id']}

        except Exception as e:
            import traceback
            traceback.print_exc()

            return {'error_message': str(e)}

    def init_routes(self):
        @route('/embed/<browser>')
        @jinja2_view('browser_embed.html', template_lookup=['templates'])
        def route_view_url_with_options(browser):
            url = request.query.getunicode('url')

            result = self.load_browser(browser, url)
            result['css'] = request.query.getunicode('css', '')
            return result

        @route('/view/<browser>/<url:path>')
        @jinja2_view('browser_embed.html', template_lookup=['templates'])
        def route_view_url(browser, url):
            if request.query_string:
                url += '?' + request.query_string

            return self.load_browser(browser, url)

        @route('/request_browser/<browser>', method='POST')
        def request_browser(browser):
            """
        request a new browser with specified container data
        should include: url and ts, other params as needed
        """
            return self.request_browser(browser)

        @route(['/browsers'])
        def list_browsers():
            """
        List all available browsers
        Query params can be used to filter on metadata properties
        """
            params = dict(request.query)
            return self.dc.load_avail_browsers(params)

        @route(['/browsers/<name>'])
        def get_browser(name):
            """
        Get info for specific browser
        """
            return self.dc.get_browser_info(name)

        @route(['/browsers/<name>/icon'])
        def get_browser_icon(name):
            """
        Load icon for browser using wr.icon metadata
        """
            res = self.dc.get_browser_info(name, True)
            if not res:
                raise HTTPError(404, 'Browser Not Found')

            response.content_type = 'image/png'
            return base64.b64decode(res['icon'].split(',', 1)[-1])

        @route(['/init_browser'])
        def init_container():
            reqid = request.query.get('reqid', '')

            width = request.query.get('width')
            height = request.query.get('height')
            audio = request.query.get("audio")

            host = request.urlparts.netloc.split(':')[0]

            resp = self.dc.init_new_browser(reqid, host, width, height, audio)

            if not resp:
                response.status = 404
                resp = {'error_message': 'Invalid Browser Request'}

            response.headers['Cache-Control'] = 'no-cache, no-store, max-age=0, must-revalidate'
            return resp

        @route('/static/<filepath:path>')
        def server_static(filepath):
            return static_file(filepath, root='./static/')


        @route('/clone_browser')
        def clone_browser():
            reqid = request.query['reqid']
            id_ = request.query['id']
            name = request.query['name']

            return self.dc.clone_browser(reqid, id_, name)


# ============================================================================
#run(host='0.0.0.0', port='9020')
application = Main().application


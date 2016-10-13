import gevent.monkey; gevent.monkey.patch_all()
import gevent

from bottle import route, run, template, request, default_app, jinja2_view
from bottle import redirect, static_file, response, debug, HTTPError

import os
import datetime
import base64

from dockercontroller import DockerController


@route('/view/<browser>/<url:path>')
@jinja2_view('browser_embed.html', template_lookup=['templates'])
def load_template(browser, url):
    """ Load a given url with a specified browser
        No proxy settings are applied, browser should run in normal live mode
    """
    if request.query_string:
        url += '?' + request.query_string

    container_data = {
        'url': url,
        'browser': browser,
        'request_ts': 'now',
    }

    reqid = request.query.getunicode('reqid')
    if not reqid:
        reqid = dc.register_request(container_data)

    container_data['reqid'] = reqid

    return {'STATIC_PREFIX': '/static',
            'container_data': container_data
           }

@route('/request_browser/<browser>', method='POST')
def request_browser(browser):
    """
request a new browser with specified container data
should include: url and ts, other params as needed
"""
    try:
        browser_data = dc.load_browser(browser)
        if not browser_data:
            return {'error': 'Browser Not Found'}

        container_data = dict(request.forms.decode())
        container_data['browser'] = browser

        reqid = dc.register_request(container_data)

        return {'reqid': reqid,
                'id': browser_data['id']}

    except Exception as e:
        import traceback
        traceback.print_exc()

        return {'error_message': str(e)}


@route(['/browsers'])
def list_browsers():
    """
List all available browsers
Query params can be used to filter on metadata properties
"""
    params = dict(request.query)
    return dc.load_avail_browsers(params)

@route(['/browsers/<name>'])
def get_browser(name):
    """
Get info for specific browser
"""
    return dc.load_browser(name)

@route(['/browsers/<name>/icon'])
def get_browser_icon(name):
    """
Load icon for browser using wr.icon metadata
"""
    res = dc.load_browser(name, True)
    if not res:
        raise HTTPError(404, 'Browser Not Found')

    response.content_type = 'image/png'
    return base64.b64decode(res['icon'].split(',', 1)[-1])


@route(['/init_browser'])
def init_container():
    reqid = request.query.get('reqid', '')

    width = request.query.get('width')
    height = request.query.get('height')

    host = request.urlparts.netloc.split(':')[0]

    resp = dc.init_new_browser(reqid, host, width, height)

    if not resp:
        response.status = 404
        resp = {'error_message': 'Invalid Browser Request'}

    response.headers['Cache-Control'] = 'no-cache, no-store, max-age=0, must-revalidate'
    return resp

@route('/static/<filepath:path>')
def server_static(filepath):
    return static_file(filepath, root='./static/')


# ======================
dc = DockerController()

event_loop_gevent = gevent.spawn(dc.event_loop)
cleanup_gevent = gevent.spawn(dc.remove_expired_loop)

application = default_app()

debug(True)

#run(host='0.0.0.0', port='9020')


from docker.client import Client
from docker.utils import kwargs_from_env

import os
import base64
import time
import redis
import yaml
import random
import traceback

from redis.exceptions import BusyLoadingError


#=============================================================================
class DockerController(object):
    def _load_config(self):
        config = os.environ.get('BROWSER_CONFIG', './config.yaml')
        with open(config) as fh:
            config = yaml.load(fh)

        config = config['browser_config']
        for n, v in config.items():
            new_v = os.environ.get(n)
            if not new_v:
                new_v = os.environ.get(n.upper())

            if new_v:
                print('Setting Env Val: {0}={1}'.format(n, new_v))
                config[n] = new_v

        return config

    def __init__(self):
        config = self._load_config()

        self.name = config['cluster_name']
        self.label_name = config['label_name']

        self.init_req_expire_secs = config['init_req_expire_secs']
        self.queue_expire_secs = config['queue_expire_secs']

        self.remove_expired_secs = config['remove_expired_secs']

        self.api_version = config['api_version']

        self.vnc_port = config['vnc_port']
        self.cmd_port = config['cmd_port']

        self.max_containers = config['max_containers']

        self.throttle_expire_secs = config['throttle_expire_secs']

        self.browser_image_prefix = config['browser_image_prefix']

        self.label_browser = config['label_browser']
        self.label_prefix = config['label_prefix']

        self.network_name = config['network_name']
        self.volume_source = config['browser_volumes']

        self.default_browser = config['default_browser']

        self._init_cli()

        while True:
            try:
                self._init_redis(config)
                break
            except BusyLoadingError:
                print('Waiting for Redis to Load...')
                time.sleep(5)

    def _init_cli(self):
        if os.path.exists('/var/run/docker.sock'):
            self.cli = Client(base_url='unix://var/run/docker.sock',
                              version=self.api_version)
        else:
            kwargs = kwargs_from_env(assert_hostname=False)
            kwargs['version'] = self.api_version
            self.cli = Client(**kwargs)

    def _init_redis(self, config):
        redis_url = os.environ['REDIS_BROWSER_URL']

        self.redis = redis.StrictRedis.from_url(redis_url, decode_responses=True)

        self.redis.setnx('next_client', '1')
        self.redis.setnx('max_containers', self.max_containers)
        self.redis.setnx('num_containers', '0')

        # TODO: support this
        #self.redis.set('cpu_auto_adjust', config['cpu_auto_adjust'])

        # if num_containers is invalid, reset to 0
        try:
            assert(int(self.redis.get('num_containers') >= 0))
        except:
            self.redis.set('num_containers', 0)

        self.redis.set('throttle_samples', config['throttle_samples'])

        self.redis.set('throttle_max_avg', config['throttle_max_avg'])

        self.duration = int(config['container_expire_secs'])
        self.redis.set('container_expire_secs', self.duration)

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
            images = self.cli.images(filters=filters)

            for image in images:
                tags = image.get('RepoTags')
                id_ = self._get_primary_id(tags)
                if not id_:
                    continue

                props = self._browser_info(image['Labels'])
                props['id'] = id_

                browsers[id_] = props

        except:
            traceback.print_exc()

        return browsers

    def _get_primary_id(self, tags):
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

    def load_browser(self, name, include_icon=False):
        tag = self.browser_image_prefix + name

        try:
            image = self.cli.inspect_image(tag)
            tags = image.get('RepoTags')
            props = self._browser_info(image['Config']['Labels'], include_icon=include_icon)
            props['id'] = self._get_primary_id(tags)
            props['tags'] = tags
            return props

        except:
            traceback.print_exc()
            return {}

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

    def _get_host_port(self, info, port, default_host):
        info = info['NetworkSettings']['Ports'][str(port) + '/tcp']
        info = info[0]
        host = info['HostIp']
        if host == '0.0.0.0' and default_host:
            host = default_host

        return host + ':' + info['HostPort']

    def _get_port(self, info, port):
        info = info['NetworkSettings']['Ports'][str(port) + '/tcp']
        info = info[0]
        return info['HostPort']

    def sid(self, id):
        return id[:12]

    def timed_new_container(self, browser, env, host, reqid):
        start = time.time()
        info = self.new_container(browser, env, host)
        end = time.time()
        dur = end - start

        time_key = 't:' + reqid
        self.redis.setex(time_key, self.throttle_expire_secs, dur)

        throttle_samples = int(self.redis.get('throttle_samples'))
        print('INIT DUR: ' + str(dur))
        self.redis.lpush('init_timings', time_key)
        self.redis.ltrim('init_timings', 0, throttle_samples - 1)

        return info

    def new_container(self, browser_id, env=None, default_host=None):
        #browser = self.browsers.get(browser_id)
        browser = self.load_browser(browser_id)

        # get default browser
        if not browser:
            browser = self.load_browser(browser_id)
            #browser = self.browsers.get(self.default_browser)

        if browser.get('req_width'):
            env['SCREEN_WIDTH'] = browser.get('req_width')

        if browser.get('req_height'):
            env['SCREEN_HEIGHT'] = browser.get('req_height')

        image = browser['tags'][0]
        print('Launching ' + image)

        short_id = None

        try:
            host_config = self.create_host_config()

            container = self.cli.create_container(image=image,
                                                  ports=[self.vnc_port, self.cmd_port],
                                                  environment=env,
                                                  host_config=host_config,
                                                  labels={self.label_name: self.name},
                                                  )
            id_ = container.get('Id')
            short_id = self.sid(id_)

            res = self.cli.start(container=id_)

            info = self.cli.inspect_container(id_)
            ip = info['NetworkSettings']['IPAddress']
            if not ip:
                ip = info['NetworkSettings']['Networks'][self.network_name]['IPAddress']

            self.redis.hset('all_containers', short_id, ip)

            vnc_host = self._get_host_port(info, self.vnc_port, default_host)
            cmd_host = self._get_host_port(info, self.cmd_port, default_host)

            print(ip)
            print(vnc_host)
            print(cmd_host)

            return {'vnc_host': vnc_host,
                    'cmd_host': cmd_host,
                    'id': short_id,
                    'ip': ip,
                   }

        except Exception as e:
            traceback.print_exc()
            if short_id:
                print('EXCEPTION: ' + short_id)
                self.remove_container(short_id)

            return {}

    def create_host_config(self):
        if self.volume_source:
            volumes_from = [self.volume_source]
        else:
            volumes_from = None

        host_config = self.cli.create_host_config(
                                 port_bindings={self.vnc_port: None,
                                                self.cmd_port: None},
                                 volumes_from=volumes_from,
                                 network_mode=self.network_name,
                                 cap_add=['ALL'],
                                )
        return host_config

    def remove_container(self, short_id):
        print('REMOVING: ' + short_id)
        try:
            self.cli.remove_container(short_id, force=True)
        except Exception as e:
            print(e)

        reqid = None
        ip = self.redis.hget('all_containers', short_id)
        if ip:
            reqid = self.redis.hget('ip:' + ip, 'reqid')

        with redis.utils.pipeline(self.redis) as pi:
            pi.delete('ct:' + short_id)

            if not ip:
                return

            pi.hdel('all_containers', short_id)
            pi.delete('ip:' + ip)
            if reqid:
                pi.delete('req:' + reqid)

    def event_loop(self):
        for event in self.cli.events(decode=True):
            try:
                self.handle_docker_event(event)
            except Exception as e:
                print(e)

    def handle_docker_event(self, event):
        if event['Type'] != 'container':
            return

        if (event['status'] == 'die' and
            event['from'].startswith(self.browser_image_prefix) and
            event['Actor']['Attributes'].get(self.label_name) == self.name):

            short_id = self.sid(event['id'])
            print('EXITED: ' + short_id)

            self.remove_container(short_id)
            self.redis.decr('num_containers')
            return

        if (event['status'] == 'start' and
            event['from'].startswith(self.browser_image_prefix) and
            event['Actor']['Attributes'].get(self.label_name) == self.name):

            short_id = self.sid(event['id'])
            print('STARTED: ' + short_id)

            self.redis.incr('num_containers')
            self.redis.setex('ct:' + short_id, self.duration, 1)
            return

    def remove_expired_loop(self):
        while True:
            try:
                self.remove_expired()
            except Exception as e:
                print(e)

            time.sleep(self.remove_expired_secs)

    def remove_expired(self):
        all_known_ids = self.redis.hkeys('all_containers')

        all_containers = {self.sid(c['Id']) for c in self.cli.containers(quiet=True)}

        for short_id in all_known_ids:
            if not self.redis.get('ct:' + short_id):
                print('TIME EXPIRED: ' + short_id)
                self.remove_container(short_id)
            elif short_id not in all_containers:
                print('STALE ID: ' + short_id)
                self.remove_container(short_id)

    def auto_adjust_max(self):
        print('Auto-Adjust Max Loop')
        try:
            scale = self.redis.get('cpu_auto_adjust')
            if not scale:
                return

            info = self.cli.info()
            cpus = int(info.get('NCPU', 0))
            if cpus <= 1:
                return

            total = int(float(scale) * cpus)
            self.redis.set('max_containers', total)

        except Exception as e:
            traceback.print_exc()

    def add_new_client(self, reqid):
        client_id = self.redis.incr('clients')
        #enc_id = base64.b64encode(os.urandom(27)).decode('utf-8')
        self.redis.setex('cm:' + reqid, self.queue_expire_secs, client_id)
        self.redis.setex('q:' + str(client_id), self.queue_expire_secs, 1)
        return client_id

    def _make_reqid(self):
        return base64.b32encode(os.urandom(15)).decode('utf-8')

    def _make_vnc_pass(self):
        return base64.b64encode(os.urandom(21)).decode('utf-8')

    def register_request(self, container_data):
        reqid = self._make_reqid()

        container_data['reqid'] = reqid

        self.redis.hmset('req:' + reqid, container_data)
        self.redis.expire('req:' + reqid, self.init_req_expire_secs)
        return reqid

    def am_i_next(self, reqid):
        client_id = self.redis.get('cm:' + reqid)

        if not client_id:
            client_id = self.add_new_client(reqid)
        else:
            self.redis.expire('cm:' + reqid, self.queue_expire_secs)

        client_id = int(client_id)
        next_client = int(self.redis.get('next_client'))

        # not next client
        if client_id != next_client:
            # if this client expired, delete it from queue
            if not self.redis.get('q:' + str(next_client)):
                print('skipping expired', next_client)
                self.redis.incr('next_client')

            # missed your number somehow, get a new one!
            if client_id < next_client:
                client_id = self.add_new_client(reqid)

        diff = client_id - next_client

        if self.throttle():
            self.redis.expire('q:' + str(client_id), self.queue_expire_secs)
            return client_id - next_client

        #num_containers = self.redis.hlen('all_containers')
        num_containers = int(self.redis.get('num_containers'))

        max_containers = self.redis.get('max_containers')
        max_containers = int(max_containers) if max_containers else self.max_containers

        if diff <= (max_containers - num_containers):
            self.redis.incr('next_client')
            return -1

        else:
            self.redis.expire('q:' + str(client_id), self.queue_expire_secs)
            return client_id - next_client

    def throttle(self):
        timings = self.redis.lrange('init_timings', 0, -1)
        if not timings:
            return False

        timings = self.redis.mget(*timings)

        avg = 0
        count = 0
        for val in timings:
            if val is not None:
                avg += float(val)
                count += 1

        if count == 0:
            return False

        avg = avg / count

        print('AVG: ', avg)
        throttle_max_avg = float(self.redis.get('throttle_max_avg'))
        if avg >= throttle_max_avg:
            print('Throttling, too slow...')
            return True

        return False

    def _copy_env(self, env, name, override=None):
        env[name] = override or os.environ.get(name)

    def init_new_browser(self, reqid, host, width=None, height=None):
        req_key = 'req:' + reqid

        container_data = self.redis.hgetall(req_key)

        if not container_data:
            return None

        # already started, attempt to reconnect
        if 'queue' in container_data:
            container_data['ttl'] = self.redis.ttl('ct:' + container_data['id'])
            return container_data

        queue_pos = self.am_i_next(reqid)

        if queue_pos >= 0:
            return {'queue': queue_pos}

        browser = container_data['browser']
        url = container_data.get('url', 'about:blank')
        ts = container_data.get('request_ts')

        env = {}

        env['URL'] = url
        env['TS'] = ts
        env['BROWSER'] = browser

        vnc_pass = self._make_vnc_pass()
        env['VNC_PASS'] = vnc_pass

        self._copy_env(env, 'PROXY_HOST')
        self._copy_env(env, 'PROXY_PORT')
        self._copy_env(env, 'SCREEN_WIDTH', width)
        self._copy_env(env, 'SCREEN_HEIGHT', height)
        self._copy_env(env, 'IDLE_TIME')

        info = self.timed_new_container(browser, env, host, reqid)
        info['queue'] = 0
        info['vnc_pass'] = vnc_pass

        new_key = 'ip:' + info['ip']

        # TODO: support different durations?
        self.duration = int(self.redis.get('container_expire_secs'))

        with redis.utils.pipeline(self.redis) as pi:
            pi.rename(req_key, new_key)
            pi.persist(new_key)

            pi.hmset(req_key, info)
            pi.expire(req_key, self.duration)

        info['ttl'] = self.duration
        return info

    def get_random_browser(self):
        browsers = self.load_avail_browsers()
        while True:
            id_ = random.choice(browsers.keys())
            if browsers[id_].get('skip_random'):
                continue

            return id_

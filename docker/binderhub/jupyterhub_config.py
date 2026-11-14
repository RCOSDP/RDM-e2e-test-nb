"""OAuth Hub used by the existing RDM E2E Notebook suite (Linux Docker host)."""
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))
from rdm_spawner import LocalContainerSpawner  # noqa: E402

d = json.loads((root / '.state/config.json').read_text())
c = get_config()  # noqa
# CS forks use this host list for browser CORS responses (health checks and builds).
c.JupyterHub.allowed_hosts = [urlsplit(d['rdm_origin']).hostname]


# RDM already uses ports 8000 (API) and 8001 (admin).
c.JupyterHub.bind_url = 'http://0.0.0.0:18000'
c.ConfigurableHTTPProxy.api_url = 'http://127.0.0.1:18001'
c.JupyterHub.hub_port = 18081
c.JupyterHub.hub_ip = '0.0.0.0'
c.JupyterHub.hub_connect_ip = d['host_ip']
c.JupyterHub.db_url = 'sqlite:///' + str(root / '.state/jupyterhub.sqlite')
c.JupyterHub.pid_file = str(root / '.state/jupyterhub.pid')
c.JupyterHub.cookie_secret_file = str(root / '.state/jupyterhub_cookie_secret')
c.JupyterHub.authenticator_class = 'dummy'
c.Authenticator.allowed_users = {d['username']}
c.DummyAuthenticator.password = d['password']
c.JupyterHub.spawner_class = LocalContainerSpawner
LocalContainerSpawner.rdmfs_mount_root = d['mount_root']
LocalContainerSpawner.rdmfs_local_root = str(root / '.state/rdmfs')
c.JupyterHub.allow_named_servers = True
c.JupyterHub.named_server_limit_per_user = 10
c.LocalContainerSpawner.auth_enabled = True
c.LocalContainerSpawner.start_timeout = 180
c.LocalContainerSpawner.http_timeout = 120
c.DockerSpawner.allowed_images = '*'
c.DockerSpawner.remove = True
c.DockerSpawner.name_template = 'rdm-e2e-binder-{username}-{servername}'
c.JupyterHub.default_url = '/hub/home'
c.JupyterHub.load_roles = [
    {'name': 'user', 'scopes': ['self', 'access:services!service=binder', 'access:services!service=rdm']},
]
c.JupyterHub.services = [
    {'name': 'binder', 'admin': True, 'oauth_no_confirm': True,
     'url': 'http://127.0.0.1:18010',
     'oauth_redirect_uri': d['binder_origin']+'/oauth_callback',
     'command': [sys.executable, '-m', 'binderhub', '--config='+str(root / 'binderhub_config.py'), '--port=18010'],
     'environment': {'OAUTHLIB_INSECURE_TRANSPORT': '1',
                     'JUPYTERHUB_HOST': d['hub_origin'],
                     'JUPYTERHUB_OAUTH_CALLBACK_URL': d['binder_origin']+'/oauth_callback'}},
    {'name': 'rdm', 'api_token': d['hub_secret'], 'oauth_client_id': 'service-rdm',
     'oauth_redirect_uri': d['rdm_origin']+'/project/binderhub/callback', 'oauth_no_confirm': False},
    {'name': 'rdm-token-admin', 'admin': True, 'api_token': d['admin_token']},
]

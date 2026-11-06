import json
from urllib.parse import urlsplit
from pathlib import Path
from binderhub.build_local import LocalRepo2dockerBuild
from binderhub.quota import LaunchQuota

root = Path(__file__).resolve().parent
d = json.loads((root / '.state/config.json').read_text())
c = get_config()  # noqa
# CS forks use this host list for browser CORS responses (health checks and builds).
c.BinderHub.allowed_hosts = [urlsplit(d['rdm_origin']).hostname]
c.BinderHub.use_registry = False
c.BinderHub.builder_required = False
c.BinderHub.build_class = LocalRepo2dockerBuild
c.BinderHub.launch_quota_class = LaunchQuota
# RDM checks /health at the origin root; serve BinderHub on its own public origin.
c.BinderHub.base_url = '/'
c.HubOAuth.base_url = '/'
c.HubOAuth.hub_host = d['hub_origin']
c.HubOAuth.oauth_redirect_uri = d['binder_origin']+'/oauth_callback'
c.BinderHub.hub_url = d['hub_origin'] + '/'
c.BinderHub.auth_enabled = True
c.Launcher.allow_named_servers = True
c.Launcher.named_server_limit_per_user = 10
c.BinderHub.oauth2_provider_enabled = True
c.BinderHub.oauth_db_url = 'sqlite:///' + str(root / '.state/binderhub-oauth.sqlite')
c.BinderHub.oauth_clients = [dict(client_id='rdm-binder', client_secret=d['binder_secret'],
    redirect_uri=d['rdm_origin']+'/project/binderhub/callback', description='RDM E2E')]
c.BinderHub.oauth_no_confirm_list = ['rdm-binder']
# RDM's frontend handles the provider's `auth` event by creating a personal
# token and retrying with repo_token. The provider must still be able to build
# that event's authorization URL; these client metadata are not exchanged with
# fakecas (which does not implement repository OAuth).
c.RDMProvider.hosts = [{
    'hostname': [d['rdm_origin']], 'api': d['rdm_api'],
    'client_id': 'binderhub-e2e-repository',
    'scope': ['osf.full_read', 'osf.full_write'],
    'oauth_authorize_url': 'http://192.168.168.167:8080/oauth2.0/authorize',
}]

#!/usr/bin/env python3
"""Prepare OAuth settings for both the local Hub and the existing RDM deployment."""
import argparse
import json
import os
from pathlib import Path
import secrets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rdm_root', type=Path)
    parser.add_argument('--rdm-origin', default='http://192.168.168.167:5000')
    parser.add_argument('--rdm-api', default='http://192.168.168.167:8000/v2/')
    parser.add_argument('--hub-origin', default='http://192.168.168.167:18000')
    parser.add_argument('--binder-origin', default='http://192.168.168.167:18010')
    parser.add_argument('--host-ip', required=True)
    args = parser.parse_args()
    local = args.rdm_root / 'addons/binderhub/settings/local.py'
    if not local.is_file():
        parser.error('Run setup_rdm.sh setup_config_files first')
    root = Path(__file__).resolve().parents[2] / 'docker/binderhub'
    state = root / '.state'
    state.mkdir(mode=0o700, exist_ok=True)
    if (state / 'config.json').exists():
        parser.error('Existing Hub state found; stop and remove it before preparing another deployment')
    os.umask(0o077)
    d = dict(hub_origin=args.hub_origin.rstrip('/'), binder_origin=args.binder_origin.rstrip('/'), rdm_origin=args.rdm_origin.rstrip('/'),
             rdm_api=args.rdm_api, host_ip=args.host_ip, username='rdm-e2e',
             password=secrets.token_urlsafe(24), binder_secret=secrets.token_hex(32),
             hub_secret=secrets.token_hex(32), admin_token=secrets.token_hex(32),
             mount_root=str(state.resolve() / 'rdmfs'))
    (state / 'config.json').write_text(json.dumps(d, indent=2)+'\n')
    bh = d['binder_origin']
    jh = d['hub_origin']+'/'
    settings = dict(DEFAULT_BINDER_URL=bh,
        BINDERHUB_OAUTH_CLIENT=dict(client_id='rdm-binder', client_secret=d['binder_secret'],
            authorize_url=bh+'/api/oauth2/authorize', token_url=bh+'/api/oauth2/token',
            services_url=bh+'/api/services', scope=['identity']),
        JUPYTERHUB_OAUTH_CLIENTS={jh: dict(client_id='service-rdm', client_secret=d['hub_secret'],
            admin_api_token=d['admin_token'], authorize_url=jh+'hub/api/oauth2/authorize',
            token_url=jh+'hub/api/oauth2/token', api_url=jh+'hub/api/', scope=['identity'], max_servers=10)})
    # setup_rdm.sh has already written the deployment image choices. Preserve them.
    with local.open('a') as out:
        out.write('\n# Local OAuth E2E configuration\n')
        out.write('\n'.join(f'{key} = {value!r}' for key, value in settings.items())+'\n')
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        for key in ('password', 'binder_secret', 'hub_secret', 'admin_token'):
            print('::add-mask::'+d[key])
    print('Prepared BinderHub/JupyterHub and RDM OAuth settings')


if __name__ == '__main__':
    main()

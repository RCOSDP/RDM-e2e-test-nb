import os
import subprocess


def register_sword_client(compose_path, client_id, mode, mapping_id, workflow_id=None):
    if mode not in ('direct', 'workflow'):
        raise ValueError(f'Unsupported SWORD registration mode: {mode}')
    command = ['docker', 'compose', '-f', compose_path, 'exec', '-T', 'web']
    if os.environ.get('WEKO_TEST_SERVICE') == 'true':
        command.extend(['python', 'register.py', client_id, mode, str(mapping_id)])
    else:
        workflow = f'workflow_id={int(workflow_id)},' if mode == 'workflow' else ''
        code = f"""
from weko_swordserver.api import SwordClient
from weko_swordserver.models import SwordClientModel as M
SwordClient.register(client_id={client_id!r}, registration_type_id=M.RegistrationType.{mode.upper()},
                     mapping_id={int(mapping_id)}, {workflow} active=True, duplicate_check=False)
"""
        command.extend(['invenio', 'shell', '-c', code])
    subprocess.run(command, check=True)

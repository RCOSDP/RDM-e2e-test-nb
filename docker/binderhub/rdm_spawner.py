"""Docker-backed BinderHub with RDMFS, following CS-tljh-repo2docker's setup.

Each server has its own RDMFS container and shared /mnt bind. No Hub admin
credentials are passed to the file system or the single-user container.
"""
import asyncio
from pathlib import Path
import re

from binderhub.binderspawner_mixin import BinderSpawnerMixin
from docker.types import Mount
from dockerspawner import DockerSpawner


PROVISION_COMMAND = '''set -e
for provision in "$REPO_DIR/binder/provision.sh" "$REPO_DIR/.binder/provision.sh" "$HOME/binder/provision.sh" "$HOME/.binder/provision.sh"; do
    if [ -f "$provision" ]; then
        exec bash "$provision" jupyterhub-singleuser
    fi
done
exec jupyterhub-singleuser
'''


class LocalContainerSpawner(BinderSpawnerMixin, DockerSpawner):
    rdmfs_mount_root: str
    rdmfs_local_root: str
    rdmfs_image = 'gcr.io/nii-ap-ops/rdmfs:2026.02.1'

    @property
    def mount_binds(self):
        mounts = super().mount_binds
        if self.user_options:
            mounts.append(Mount(
                type='bind', source=str(Path(self.rdmfs_mount_root) / self.container_name),
                target='/mnt', propagation='rshared'))
        return mounts

    async def _remove_rdmfs(self):
        name = self.container_name + '_rdmfs'
        containers = await self.docker('containers', all=True, filters={'name': '^/' + re.escape(name) + '$'})
        if not containers:
            return
        container = await self.docker('inspect_container', name)
        if container['State']['Running']:
            terminate = await self.docker(
                'exec_create', name, ['sh', '-c', 'xattr -w command terminate /mnt/rdms'])
            await self.docker('exec_start', terminate['Id'], detach=True)
            await self.docker('stop', name, timeout=10)
        await self.docker('remove_container', name, force=True)

    async def start(self):
        options = self.user_options
        project = options['rdm_node_id']
        if not re.fullmatch(r'[a-zA-Z0-9]+', project) or not options['repo_token']:
            raise ValueError('BinderHub RDM project and repository token are required')
        local = Path(self.rdmfs_local_root) / self.container_name
        local.mkdir(parents=True, exist_ok=True)
        local.chmod(0o777)
        await self._remove_rdmfs()
        mount = self.mount_binds[-1]
        host_config = self.client.create_host_config(privileged=True, mounts=[mount])
        sidecar = await self.docker(
            'create_container', image=self.rdmfs_image, name=self.container_name + '_rdmfs',
            environment={'RDM_API_URL': options['rdm_api_url'],
                         'RDM_TOKEN': options['repo_token'], 'MOUNT_PATH': '/mnt/rdms'},
            host_config=host_config)
        try:
            await self.docker('start', sidecar['Id'])
            # Wait for the actual project mount, rather than a container status.
            for _ in range(60):
                check = await self.docker(
                    'exec_create', sidecar['Id'], ['test', '-d', '/mnt/rdms/' + project + '/osfstorage'])
                await self.docker('exec_start', check['Id'])
                status = await self.docker('exec_inspect', check['Id'])
                if status['ExitCode'] == 0:
                    break
                await asyncio.sleep(1)
            else:
                raise RuntimeError('RDMFS project mount did not become ready')
            self.cmd = ['bash', '-lc', PROVISION_COMMAND]
            return await super().start()
        except BaseException:
            await self._remove_rdmfs()
            raise

    async def stop(self, now=False):
        try:
            return await super().stop(now=now)
        finally:
            await self._remove_rdmfs()

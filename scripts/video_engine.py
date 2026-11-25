"""Execute a procedure with Papermill and save its captioned browser recording."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import papermill as pm
from papermill.clientwrap import PapermillNotebookClient
from papermill.engines import NBClientEngine, papermill_engines

from scripts.render_report_video import render


class VideoClient(PapermillNotebookClient):
    def control(self, source):
        reply = self.wait_for_reply(self.kc.execute(source, silent=True))['content']
        if reply['status'] != 'ok':
            raise RuntimeError('\n'.join(reply['traceback']))

    def papermill_execute_cells(self):
        self.scenario = ''
        self.step = 0
        self.control('from scripts.report_video import Recorder\n'
                     f'_video = Recorder({self.directory!r})\n_video.install()')
        try:
            super().papermill_execute_cells()
        finally:
            self.control('await _video.finish()')

    def execute_cell(self, cell, index, **kwargs):
        source = cell.source
        if cell.cell_type == 'markdown':
            if source.startswith('# '):
                self.scenario = source.splitlines()[0][2:]
                self.step = 0
            elif source.startswith('## '):
                self.title = source.splitlines()[0][3:]
                self.step += 1
        elif cell.cell_type == 'code' and self.step and source.strip():
            self.control(f'await _video.begin_cell({index}, {self.scenario!r}, '
                         f'{self.step}, {self.title!r})')
        return super().execute_cell(cell, index, **kwargs)


class VideoEngine(NBClientEngine):
    @classmethod
    def execute_managed_notebook(cls, nb_man, kernel_name, video_directory, **kwargs):
        if not any(cell.cell_type == 'code' and 'from scripts.playwright import' in cell.source
                   for cell in nb_man.nb.cells):
            return super().execute_managed_notebook(nb_man, kernel_name, **kwargs)
        client = VideoClient(nb_man, kernel_name=kernel_name, timeout=None)
        client.directory = video_directory
        return client.execute()


def execute_notebook(base_notebook, result_notebook, parameters):
    papermill_engines.register('procedure-video', VideoEngine)
    output = Path(parameters['default_result_path']) / 'report.webm'
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as scratch:
        directory = Path(scratch).resolve()
        try:
            return pm.execute_notebook(base_notebook, result_notebook, parameters=parameters,
                                       engine_name='procedure-video', video_directory=str(directory))
        finally:
            manifest = directory / 'recording.json'
            if manifest.exists() and json.loads(manifest.read_text())['segments']:
                render(directory, '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc').replace(output)

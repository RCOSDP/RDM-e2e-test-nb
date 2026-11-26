"""Execute a procedure with Papermill and save its captioned browser recording."""
import json
import logging
import subprocess
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
            try:
                self.control('await _video.finish()')
            except RuntimeError as error:
                (Path(self.directory) / 'capture-error.txt').write_text(str(error))

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


def execute_notebook(base_notebook, result_notebook, parameters, skip_failed_test=False):
    papermill_engines.register('procedure-video', VideoEngine)
    output = Path(parameters['default_result_path']) / 'report.webm'
    output.parent.mkdir(parents=True, exist_ok=True)
    warning = output.with_name('report-video-error.txt')
    warning.unlink(missing_ok=True)
    output.unlink(missing_ok=True)
    with TemporaryDirectory(dir=output.parent) as scratch:
        directory = Path(scratch).resolve()
        try:
            result = pm.execute_notebook(base_notebook, result_notebook, parameters=parameters,
                                       engine_name='procedure-video', video_directory=str(directory))
        finally:
            manifest = directory / 'recording.json'
            capture_error = directory / 'capture-error.txt'
            try:
                if capture_error.exists():
                    raise RuntimeError(capture_error.read_text())
                if manifest.exists() and json.loads(manifest.read_text())['segments']:
                    render(directory, '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc').replace(output)
            except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
                message = f'動画生成失敗: {error}'
                warning.write_text(message)
                logging.warning('%s: %s', result_notebook, message)
    if warning.exists() and not skip_failed_test:
        raise RuntimeError(warning.read_text())
    return result

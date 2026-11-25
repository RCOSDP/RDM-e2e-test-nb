# PapermillによるJupyter Notebookの実行およびその事前準備をサポートするためのユーティリティ関数群

import os
import traceback
from typing import Callable
import papermill as pm
from scripts.video_engine import execute_notebook
import shutil
import yaml

def run_notebook(
    result_dir: str,
    base_notebook: str,
    transition_timeout: int,
    shared_params: dict = None,
    extra_params: dict = None,
    skip_failed_test: bool = False,
    optional_result_id: str = None,
) -> str:
    """
    Jupyter Notebook を指定のパラメータで実行し、結果を保存する。

    :param result_dir: 実行後のNotebookや撮影されたスクリーンショットなどを保存するディレクトリ
    :param base_notebook: 実行するNotebookパス
    :param transition_timeout: 画面表示を伴うステップにおける、画面表示完了のタイムアウト時間
    :param shared_params: Coordinatorの中で共通のパラメータ
    :param extra_params: base_notebookに固有の追加パラメータ
    :param skip_failed_test: base_notebookの実行に失敗したとき、処理を続行する(True)か例外を投げて停止する(False、デフォルト)か
    :param optional_result_id: 実行後のNotebookのファイル名に前置する識別子
    :return: 実行後のNotebookのパス
    """
    _, filename = os.path.split(base_notebook)
    result_id, _ = os.path.splitext(filename)
    if optional_result_id:
        result_id += optional_result_id
    result_notebook = os.path.join(result_dir, result_id + '.ipynb')
    result_path = os.path.join(result_dir, result_id)
    os.makedirs(result_path, exist_ok=True)
    params = dict(
        default_result_path=result_path,
        close_on_fail=True,
        transition_timeout=transition_timeout,
    )

    if shared_params:
        params.update(shared_params)
    if extra_params:
        params.update(extra_params)

    try:
        execute_notebook(base_notebook, result_notebook, parameters=params)
    except pm.PapermillExecutionError:
        if not skip_failed_test:
            raise
        print('失敗しました。テストは続行します...')
        traceback.print_exc()
    return result_notebook

def gen_run_notebook(
    result_dir: str,
    transition_timeout: int,
    shared_params: dict | None = None,
    skip_failed_test: bool = False,
    exclude_notebooks: list | None = None
) -> Callable[[str, str, dict | None, str | None], str]:
    """
    一部の引数を固定した run_notebook 関数を生成する。

    :param result_dir: 実行後のNotebookや撮影されたスクリーンショットなどを保存するディレクトリ
    :param transition_timeout: 画面表示を伴うステップにおける、画面表示完了のタイムアウト時間
    :param shared_params: Coordinatorの中で共通のパラメータ
    :param skip_failed_test: base_notebookの実行に失敗したとき、処理を続行する(True)か例外を投げて停止する(False、デフォルト)か
    :param exclude_notebooks: スキップするNotebookのリスト
    :return: run_notebook(result_dir, base_notebook, extra_params, optional_result_id) を受け取る関数
    """

    def partial_run_notebook(
        base_notebook: str,
        extra_params: dict | None = None,
        optional_result_id: str | None = None,
    ) -> str:
        # Check if notebook should be excluded
        if exclude_notebooks and base_notebook in exclude_notebooks:
            print(f'Skipping excluded notebook: {base_notebook}')
            return None

        return run_notebook(
            result_dir,
            base_notebook,
            transition_timeout,
            shared_params,
            extra_params,
            skip_failed_test,
            optional_result_id,
        )

    return partial_run_notebook

def run_manual_notebook(notebook_filename, local_vars, work_dir, result_dir, optional_result_id=None, **optional_params):
    result_id, _ = os.path.splitext(notebook_filename)
    if optional_result_id:
        result_id += optional_result_id
    result_path = os.path.join(result_dir, result_id)

    user_config_path = os.path.join(work_dir, '.config.yaml')
    with open(user_config_path, 'w') as f:
        additional = [
            ('default_result_path', result_path),
        ]
        f.write(yaml.dump(dict([
            (k, local_vars[k])
            for k in local_vars.keys()
            if (isinstance(local_vars[k], str) or local_vars[k] is None) and k not in ['work_dir'] and not k.startswith('_')
        ] + additional + list(optional_params.items()))))

    print('以下の操作を実施してください。')

    print(f'1. Jupyter Notebook {notebook_filename} を開く')
    print('2. Run All Cellsを実施する')
    print(f'  設定ファイルを要求されたときには、 {user_config_path} を入力する')

    assert input(prompt="全てのセル実行の成功を確認し、Notebookの保存を完了したら、'finished'と入力してください") == 'finished'
    result_notebook = os.path.join(result_dir, result_id + '.ipynb')
    shutil.copyfile(notebook_filename, result_notebook)
    return result_notebook

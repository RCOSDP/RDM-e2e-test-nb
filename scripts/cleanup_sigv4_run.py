# -*- coding: utf-8 -*-
"""SigV4 回帰の証跡取りで作ったものを試験環境から片付ける。

ノートブック(テスト手順-管理者機能-S3-機関ストレージ-SigV4回帰.ipynb)の
「後始末チェックリスト」のうち、画面操作が要る 2 つを行う。

1. 本ノートブックが作ったプロジェクトを削除する
   (`<prefix>-institutional` / `-apne1` / `-addon` / `-versioned`)
2. ユーザー設定 →「アドオンアカウント構成」から Amazon S3 の連携を解除する

**機関ストレージには触らない。** 既に元の設定に戻してあるため、ここで触ると
戻した設定を壊す。

接続先と資格情報は .config.yaml から読む(ノートブックのセル [1] と同じ)。
リポジトリ直下で実行すること。

    # まず何を消すのか確認する(削除も解除もしない。画面だけ撮る)
    python3 scripts/cleanup_sigv4_run.py --prefix TEST-S3-SIGV4-<run_id> --dry-run

    # 実行する
    python3 scripts/cleanup_sigv4_run.py --prefix TEST-S3-SIGV4-<run_id> \
        --out <証跡ディレクトリ>
"""
import argparse
import asyncio
import os
import sys

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
# scripts/ 直下のスクリプトとして起動すると sys.path[0] が scripts/ になり、
# scripts/playwright.py が本物の playwright パッケージを隠す
# (ModuleNotFoundError: 'playwright' is not a package)。
# scripts/ を外し、代わりにリポジトリ直下を入れる。
sys.path[:] = [p for p in sys.path if os.path.abspath(p or '.') != _HERE]
sys.path.insert(0, os.path.dirname(_HERE))

from scripts.playwright import (  # noqa: E402
    expect, finish_pw_context, init_pw_context, run_pw, save_screenshot)
from scripts import grdm  # noqa: E402

SUFFIXES = ['institutional', 'apne1', 'addon', 'versioned']

# ユーザー設定 → アドオンアカウント構成 の S3 の枠(s3_user_settings.mako L2/L16/L18)。
DISCONNECT_LINK = ('//div[@id="s3AddonScope"]//div[@id="s3-header"]'
                   '//a[contains(@class, "default-authorized-by")'
                   ' and contains(@class, "text-danger")]')
# askDisconnect は bootbox.confirm を出す(addonSettings.js L115-137)。
# 確認文字列の入力は無く、btn-danger を押すだけ。
DISCONNECT_CONFIRM = ('//div[contains(@class, "bootbox")]'
                      '//button[contains(@class, "btn-danger")]')


def load_config():
    """.config.yaml から接続情報を読む。**値は印字しない。**"""
    if not os.path.exists('.config.yaml'):
        print('.config.yaml が無い。リポジトリ直下で実行すること。',
              file=sys.stderr)
        sys.exit(2)
    with open('.config.yaml') as f:
        cfg = yaml.safe_load(f) or {}
    conf = {
        'rdm_url': cfg.get('rdm_url'),
        'idp_name_1': cfg.get('idp_name_1') or 'GakuNin RDM IdP',
        'idp_username_1': cfg.get('idp_username_1'),
        'idp_password_1': cfg.get('idp_password_1'),
        'transition_timeout': cfg.get('transition_timeout') or 60000,
    }
    missing = [k for k in ('rdm_url', 'idp_username_1', 'idp_password_1')
               if not conf[k]]
    if missing:
        print(f'.config.yaml に足りないキーがある: {missing}', file=sys.stderr)
        sys.exit(2)
    return conf


async def wait_dashboard_loaded(page, conf, retries=3):
    """ダッシュボードのプロジェクト一覧が読み終わるのを待つ。

    一覧が出る前に「無い」と判定すると、消し残しを「消えた」と誤報告する。
    ノートブックのセル [26] と同じ理由で待つ。
    """
    timeout = conf['transition_timeout']
    loaded = page.locator(
        '//*[@data-test-dashboard-item-title]'
        ' | //*[contains(text(), "まだプロジェクトがありません")]').first
    create_btn = page.locator('//*[@data-test-create-project-modal-button]')
    no_api = page.locator('//*[@data-analytics-scope = "No api page"]')
    for attempt in range(1, retries + 1):
        reason = None
        try:
            await expect(create_btn.or_(no_api).first
                         ).to_be_visible(timeout=timeout)
            if await no_api.count() > 0:
                reason = 'Ember が「APIは利用できません」を出している'
            else:
                await expect(loaded).to_be_visible(timeout=timeout)
                return
        except AssertionError:
            reason = 'プロジェクト一覧がスピナーのまま'
        if attempt == retries:
            raise AssertionError(
                f'ダッシュボードが読み込まれない({reason})。現在地: {page.url}')
        print(f'[!] {reason}。再読込する ({attempt}/{retries - 1})')
        await asyncio.sleep(30)
        await page.goto(conf['rdm_url'])


async def list_projects(page, conf):
    await page.goto(conf['rdm_url'])
    await wait_dashboard_loaded(page, conf)
    return await page.locator(
        '//*[@data-test-dashboard-item-title]').all_text_contents()


def plan(args):
    return [f'{args.prefix}-{s}' for s in SUFFIXES]


async def delete_one(page, conf, name):
    """ダッシュボードから name を開いて削除する。無ければ False。"""
    await page.goto(conf['rdm_url'])
    await wait_dashboard_loaded(page, conf)
    item = page.locator(
        f'//*[@data-test-dashboard-item-title and text()="{name}"]')
    if await item.count() == 0:
        print(f'skip (既に無い): {name}')
        return False
    await item.first.click(timeout=conf['transition_timeout'])
    await expect(page.locator('#projectNavFiles')
                 ).to_be_visible(timeout=conf['transition_timeout'])
    await grdm.delete_project(page, transition_timeout=conf['transition_timeout'])
    await asyncio.sleep(5)
    print(f'削除した: {name}')
    return True


async def disconnect_s3(page, conf, out_dir, dry_run):
    """ユーザー設定 → アドオンアカウント構成 の Amazon S3 を解除する。

    アドオンのアカウントは**ユーザー単位**で残るので、プロジェクトを消しても
    消えない。ここで解除しないと次回の実行が前回の資格情報を掴む。
    """
    timeout = conf['transition_timeout']
    await page.goto(conf['rdm_url'].rstrip('/') + '/settings/addons/')
    await expect(page.locator('//div[@id="s3AddonScope"]')
                 ).to_be_visible(timeout=timeout)
    await asyncio.sleep(3)
    if out_dir:
        await save_screenshot(os.path.join(out_dir, 'S-9-addons-before.png'))
    link = page.locator(DISCONNECT_LINK)
    count = await link.count()
    if count == 0:
        print('skip (S3 の連携アカウントが無い)')
        return False
    if dry_run:
        print(f'[dry-run] S3 の連携を解除する (アカウント {count} 件)')
        return False
    await link.first.scroll_into_view_if_needed()
    await link.first.click()
    confirm = page.locator(DISCONNECT_CONFIRM)
    await expect(confirm.first).to_be_visible(timeout=timeout)
    await confirm.first.click()
    await asyncio.sleep(3)
    # 解除できていなければリンクが残る。残ったまま「解除した」と書かない。
    await page.goto(conf['rdm_url'].rstrip('/') + '/settings/addons/')
    await expect(page.locator('//div[@id="s3AddonScope"]')
                 ).to_be_visible(timeout=timeout)
    await asyncio.sleep(3)
    remain = await page.locator(DISCONNECT_LINK).count()
    assert remain == 0, f'S3 の連携が解除できていない(残り {remain} 件)'
    if out_dir:
        await save_screenshot(os.path.join(out_dir, 'S-9-addons-after.png'))
    print('S3 の連携を解除した')
    return True


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', required=True,
                        help='プロジェクト名の接頭辞 '
                             '(例 TEST-S3-SIGV4-20261001-130318)')
    parser.add_argument('--out', default=None,
                        help='証跡の保存先ディレクトリ')
    parser.add_argument('--dry-run', action='store_true',
                        help='削除も解除もせず、対象の有無と画面だけを採る')
    parser.add_argument('--skip-addon', action='store_true',
                        help='S3 アドオンの連携解除を行わない')
    args = parser.parse_args()

    conf = load_config()
    targets = plan(args)
    out_dir = os.path.abspath(args.out) if args.out else None
    session_dir = None
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        # playwright 側の session 証跡(video-N.webm / har.zip / console.log /
        # last-*.html|png)は**固定名**なので、証跡ディレクトリ直下を last_path に
        # すると本番の採取が残した同名ファイルを上書きする(実際に 1 回消した)。
        # 後始末ぶんは下位ディレクトリに分ける。
        session_dir = os.path.join(out_dir, 'cleanup')
        os.makedirs(session_dir, exist_ok=True)
    print('対象プロジェクト:')
    for t in targets:
        print(f'  - {t}')
    print(f'証跡: {out_dir or "(保存しない)"}')
    print(f'dry-run: {args.dry_run}')
    print('機関ストレージには触らない')

    await init_pw_context(close_on_fail=False, last_path=session_dir)
    try:
        async def _login(page):
            # about:blank のまま login を呼ぶと IdP 選択に届かず、
            # 「ユーザー名とパスワードによるログインを試みます...」の
            # フォールバックも空振りする。ノートブックのセル [24] と同じ順で開く。
            await page.goto(conf['rdm_url'])
            await page.wait_for_load_state('networkidle')
            consent = page.locator('//button[text() = "同意する"]')
            if await consent.count() > 0 and await consent.is_visible():
                await consent.click()
                await page.wait_for_load_state('networkidle')
            await grdm.expect_anonymous_toppage(
                page, conf['idp_name_1'],
                transition_timeout=conf['transition_timeout'])
            await grdm.login(page, conf['idp_name_1'], conf['idp_username_1'],
                             conf['idp_password_1'],
                             transition_timeout=conf['transition_timeout'])
            await expect(
                page.locator('//*[@data-test-create-project-modal-button]')
            ).to_be_visible(timeout=conf['transition_timeout'])
        await run_pw(_login)

        async def _before(page):
            names = await list_projects(page, conf)
            found = [t for t in targets if t in names]
            print(f'削除前に見えているもの: {found}')
            missing = [t for t in targets if t not in names]
            if missing:
                print(f'一覧に無いもの(既に削除済みか別ユーザー): {missing}')
            if out_dir:
                await save_screenshot(
                    os.path.join(out_dir, 'S-9-projects-before.png'))
        await run_pw(_before)

        if not args.dry_run:
            async def _delete(page):
                for name in targets:
                    await delete_one(page, conf, name)
            await run_pw(_delete)

        if not args.skip_addon:
            async def _addon(page):
                await disconnect_s3(page, conf, out_dir, args.dry_run)
            await run_pw(_addon)

        async def _after(page):
            names = await list_projects(page, conf)
            left = [t for t in targets if t in names]
            if out_dir:
                await save_screenshot(
                    os.path.join(out_dir, 'S-9-cleanup.png'))
            print(f'削除後に残っているもの: {left}')
            assert args.dry_run or not left, \
                f'削除できていないプロジェクトがある: {left}'
        await run_pw(_after)
    finally:
        await finish_pw_context(screenshot=True, last_path=session_dir)
    print('後始末を終えた')


if __name__ == '__main__':
    asyncio.run(main())

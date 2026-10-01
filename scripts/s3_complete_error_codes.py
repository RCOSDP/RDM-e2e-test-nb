#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S-6: AWS S3 が CompleteMultipartUpload に返す Error Code を実機採取する。

RDM-waterbutler の ``waterbutler/providers/s3/provider.py`` には
``DEFINITIVE_REJECTION_CODES``(9 コード)という表がある。これは
「CompleteMultipartUpload がこのコードで落ちたなら、オブジェクトは確実に
できていない(= NOT_COMMITTED)」と判断するための表で、**MinIO の実装と S3 の
仕様書から起こしたもので AWS S3 の実機では確認されていない**(provider.py の
同箇所のコメント)。受入項目 E-1 はこの突合を求めている。

本スクリプトは AWS に対して壊れた CompleteMultipartUpload を投げ、返ってきた
Error Code を採取して表と突き合わせる。**コード側(表)は変更しない。**
表に無いコードが出た場合は、WaterButler の既定どおり ``UNKNOWN``
(= オブジェクトができたかどうか分からない)として記録するだけ。
これが E-1 の合格基準である。

使い方(バケットも本スクリプトに作らせる場合)::

    AWS_PROFILE=<プロファイル名> \\
        python3 scripts/s3_complete_error_codes.py --create-bucket \\
        --out <証跡ディレクトリ>

``--create-bucket`` は ``e2e-sigv4-s6-<YYYYmmdd-HHMMSS>`` を ``E2E_S3_REGION``
(既定 ``us-east-1``)に作り、**正常終了でも例外でも空にして削除する**。

使い方(既にあるバケットを使う場合)::

    export E2E_S3_BUCKET=...
    export E2E_S3_REGION=us-east-1          # 省略時 us-east-1
    AWS_PROFILE=<プロファイル名> \\
        python3 scripts/s3_complete_error_codes.py --out <証跡ディレクトリ>

``E2E_S3_BUCKET`` / ``E2E_S3_REGION`` の 2 行は、SigV4 回帰ノートブックの
バケット生成セル(セル [6])が ``export …`` の形で印字するので、それをそのまま
貼ればよい。ノートブックは既定でバケットを生成し**後始末で削除する**ので、
その場合はノートブックの後始末セルより**前**に実行すること。
指定したバケットは本スクリプトが作った multipart を中止するだけで、
オブジェクトも残さない(バケット自体は消さない)。

資格情報は boto3 の既定の解決順(環境変数 / ``AWS_PROFILE`` /
インスタンスロール)で解決する。コマンドライン引数では受け取らない
(ps に出るため)。出力の直前にアクセスキーが混ざっていないことを検査する。

``--dry-run`` を付けると AWS には一切アクセスせず、呼び出し計画だけを印字する。
"""
import argparse
import json
import os
import re
import sys
import textwrap
from datetime import datetime

# ---------------------------------------------------------------------------
# RDM-waterbutler waterbutler/providers/s3/provider.py の DEFINITIVE_REJECTION_CODES
# の写し。**ここを書き換えて突合を通すのは禁止**(表の妥当性を測るのが目的)。
DEFINITIVE_REJECTION_CODES = frozenset({
    'AccessDenied',
    'InvalidPart',
    'InvalidPartOrder',
    'EntityTooSmall',
    'EntityTooLarge',
    'MalformedXML',
    'SignatureDoesNotMatch',
    'InvalidAccessKeyId',
    'NoSuchBucket',
})

# S3 の最小パートサイズ。非最終パートがこれ未満だと EntityTooSmall になる。
MIN_PART_SIZE = 5 * 1024 * 1024

# 架空のアクセスキー。実在しない形式(AKIA + 16 文字)にしてある。
# 出力には伏せ字ではなくこのまま出す(実在しないので伏せる必要がない)が、
# redact() の正規表現に引っかかるため、印字時は _BOGUS_DISPLAY を使う。
BOGUS_ACCESS_KEY = 'AKIA' + 'INVALIDINVALIDIN'
_BOGUS_DISPLAY = '<架空のアクセスキー (AKIA + INVALID...)>'

OUT_JSON = 'S-6-complete-error-codes.json'
OUT_MD = 'S-6-complete-error-codes.md'

# 本スクリプトの構成では実機採取できない 9 コードと、その理由。
UNCOLLECTABLE_REASONS = {
    'EntityTooLarge': (
        '1 オブジェクト 5TiB 超(または 1 パート 5GiB 超)でしか返らない。'
        '転送量・費用・所要時間の点で E2E では採取しない。'
        'ガードは単体テストで担保する。'),
}


def classify(code):
    """WaterButler が返す分類。表にあれば NOT_COMMITTED、無ければ既定の UNKNOWN。"""
    return 'NOT_COMMITTED' if code in DEFINITIVE_REJECTION_CODES else 'UNKNOWN'


# ---------------------------------------------------------------------------
# ケース定義。説明は --dry-run の呼び出し計画にもそのまま使う。
CASES = [
    ('no-such-upload', '存在しない UploadId で complete する', [
        'create_multipart_upload(Key=<key>)',
        'abort_multipart_upload(<本物の UploadId>)   # 先に捨てる',
        'complete_multipart_upload(UploadId=<捨てた UploadId>, Parts=[])',
    ]),
    ('invalid-part', '実在するパートに偽の ETag を付けて complete する', [
        'create_multipart_upload(Key=<key>)',
        'upload_part(PartNumber=1, Body=<5MiB>)',
        'complete_multipart_upload(Parts=[{PartNumber: 1, ETag: "<偽 ETag>"}])',
        'abort_multipart_upload()   # 後始末',
    ]),
    ('entity-too-small', '1MiB のパートを 2 つ上げて complete する', [
        'create_multipart_upload(Key=<key>)',
        'upload_part(PartNumber=1, Body=<1MiB>)   # 非最終パートが 5MiB 未満',
        'upload_part(PartNumber=2, Body=<1MiB>)',
        'complete_multipart_upload(Parts=[1, 2])',
        'abort_multipart_upload()   # 後始末',
    ]),
    ('invalid-part-order', '2 パートを逆順で complete する', [
        'create_multipart_upload(Key=<key>)',
        'upload_part(PartNumber=1, Body=<5MiB>)',
        'upload_part(PartNumber=2, Body=<5MiB>)   # 両方 5MiB(サイズで落とさない)',
        'complete_multipart_upload(Parts=[2, 1])   # 降順',
        'abort_multipart_upload()   # 後始末',
    ]),
    ('malformed-xml', 'Parts=[] で complete する', [
        'create_multipart_upload(Key=<key>)',
        'upload_part(PartNumber=1, Body=<5MiB>)',
        'complete_multipart_upload(MultipartUpload={"Parts": []})',
        'abort_multipart_upload()   # 後始末',
    ]),
    ('access-denied', '(--with-access-denied のとき) PutObject を拒否する'
     'ポリシーの付いたバケットに complete する', [
         'create_multipart_upload(Bucket=<E2E_S3_DENY_BUCKET>, Key=<key>)',
         'upload_part(PartNumber=1, Body=<5MiB>)',
         'complete_multipart_upload(Parts=[1])',
         'abort_multipart_upload()   # 後始末(これも拒否される場合がある)',
     ]),
    ('completed-twice', '正常に complete したあと、同じ UploadId でもう一度 complete する', [
        'create_multipart_upload(Key=<key>)',
        'upload_part(PartNumber=1, Body=<5MiB>)',
        'complete_multipart_upload(Parts=[1])   # 1 回目は成功する',
        'complete_multipart_upload(Parts=[1])   # 2 回目 ← これを記録する',
        'delete_object(Key=<key>)   # 後始末(1 回目で実体ができている)',
    ]),
    ('invalid-access-key-id', '架空のアクセスキーのクライアントで complete する', [
        'create_multipart_upload(Key=<key>)   # 正しい資格情報で',
        'upload_part(PartNumber=1, Body=<5MiB>)',
        f'complete_multipart_upload(...)   # aws_access_key_id={_BOGUS_DISPLAY}',
        'abort_multipart_upload()   # 後始末は正しい資格情報で',
    ]),
    ('signature-does-not-match', '正しいアクセスキー + 壊したシークレットで complete する', [
        'create_multipart_upload(Key=<key>)   # 正しい資格情報で',
        'upload_part(PartNumber=1, Body=<5MiB>)',
        'complete_multipart_upload(...)   # secret の末尾 1 文字を別の文字に置換',
        'abort_multipart_upload()   # 後始末は正しい資格情報で',
    ]),
    ('no-such-bucket', '存在しないバケットに対して complete する', [
        'complete_multipart_upload(Bucket=<E2E_S3_BUCKET>-does-not-exist-<random>, '
        'UploadId=<架空>, Parts=[1])',
        '# 後始末なし(何も作っていない)',
    ]),
]

CASE_NOTES = {
    'completed-twice': (
        'NoSuchUpload が返るなら、「NoSuchUpload = オブジェクトは無い」とは'
        '言えないことの実機根拠になる(完了済みの UploadId でも同じ答えが返るため)。'
        'provider.py が NoSuchUpload を DEFINITIVE_REJECTION_CODES に入れず'
        'UNKNOWN 既定にしているのは、まさにこの理由による。'),
    'access-denied': (
        '事前にユーザーが「s3:PutObject を拒否するバケットポリシー」を付けた'
        'バケットを用意し、環境変数 E2E_S3_DENY_BUCKET で渡すこと。'),
    'invalid-access-key-id': (
        'UploadId とパートは正しい資格情報で作る。壊すのは complete の呼び出し'
        'だけなので、「complete がこのコードで落ちたときオブジェクトは無い」と'
        'いう表の主張をそのまま検証できる。'),
    'signature-does-not-match': (
        'シークレットの末尾 1 文字を別の文字に置換する。シークレットそのものは'
        '出力にも例外文にも出さない(botocore は署名計算にしか使わない)。'),
    'no-such-bucket': (
        'NoSuchBucket と NoSuchUpload のどちらが先に返るかを記録する。'
        'バケットが無ければ UploadId の存在は問えないので NoSuchBucket が'
        '期待値だが、実機の順序は未確認。'),
}


def redact(text):
    """アクセスキーらしき文字列を伏せる。"""
    out = re.sub(r'AKIA[0-9A-Z]{12,}', 'AKIA***', text)
    out = re.sub(r'ASIA[0-9A-Z]{12,}', 'ASIA***', out)
    return out


def assert_no_credentials(text, access_key=None, secret_key=None):
    """出力に資格情報が混ざっていないことを確かめる。"""
    assert 'AKIA' not in text.replace('AKIA***', ''), '出力にアクセスキーが残っている'
    assert 'ASIA' not in text.replace('ASIA***', ''), '出力にアクセスキーが残っている'
    if access_key:
        assert access_key not in text, '出力にアクセスキーが残っている'
    if secret_key:
        assert secret_key not in text, '出力にシークレットキーが残っている'


# ---------------------------------------------------------------------------
def print_plan(args, bucket, region, deny_bucket):
    print('S-6 CompleteMultipartUpload Error Code 採取 — 呼び出し計画 (--dry-run)')
    print()
    if args.create_bucket:
        print('  bucket           : e2e-sigv4-s6-<YYYYmmdd-HHMMSS>'
              '(--create-bucket で生成し、終了時に空にして削除する)')
    else:
        print(f'  bucket           : {bucket or "<E2E_S3_BUCKET 未設定>"}')
    print(f'  region           : {region}')
    print('  credentials      : boto3 の既定の解決順'
          '(環境変数 / AWS_PROFILE / インスタンスロール)')
    print(f'  key prefix       : {args.prefix}')
    print(f'  out              : {args.out}')
    print(f'  deny bucket      : {deny_bucket or "(未設定 → access-denied はスキップ)"}')
    print()
    if args.create_bucket:
        print('  [create-bucket] 採取用バケットを作る')
        print('      - create_bucket(Bucket=e2e-sigv4-s6-<YYYYmmdd-HHMMSS>)')
        print('      # 終了時(例外が出た場合も)に multipart を中止し、'
              'オブジェクトを消して delete_bucket する')
        print()
    for name, desc, calls in CASES:
        if name == 'access-denied' and not args.with_access_denied:
            print(f'  [skip] {name}: --with-access-denied が無いためスキップ')
            continue
        if name == 'access-denied' and not deny_bucket:
            print(f'  [skip] {name}: E2E_S3_DENY_BUCKET 未設定のためスキップ')
            continue
        print(f'  [{name}] {desc}')
        for c in calls:
            print(f'      - {c}')
        if name in CASE_NOTES:
            for line in textwrap.wrap(CASE_NOTES[name], 76):
                print(f'      # {line}')
        print()
    print('出力:')
    print(f'  {os.path.join(args.out, OUT_JSON)}')
    print(f'  {os.path.join(args.out, OUT_MD)}')
    print()
    print('※ --dry-run では AWS に一切アクセスしていない。')
    return 0


# ---------------------------------------------------------------------------
def _client(region, access_key=None, secret_key=None, session_token=None):
    """S3 クライアント。資格情報を渡さなければ boto3 の既定の解決順
    (環境変数 / AWS_PROFILE / インスタンスロール)に任せる。

    access_key / secret_key を明示すると、その資格情報だけを使う
    (ケース 8・9 用。壊した資格情報で complete を投げるため)。
    """
    import boto3
    from botocore.config import Config
    kwargs = {
        'region_name': region,
        'config': Config(signature_version='s3v4', retries={'max_attempts': 1}),
    }
    if access_key is not None:
        kwargs['aws_access_key_id'] = access_key
        kwargs['aws_secret_access_key'] = secret_key
        kwargs['aws_session_token'] = session_token
    return boto3.client('s3', **kwargs)


def _resolve_credentials():
    """既定の解決順で資格情報を解決し、(access_key, secret_key, token) を返す。

    解決した値は「壊した署名を作る」(ケース 9)のと、出力に混ざっていない
    ことを検査するのにしか使わない。**印字も証跡への書き出しもしない。**
    解決できなければ 3 つとも None。
    """
    import boto3
    creds = boto3.Session().get_credentials()
    if creds is None:
        return None, None, None
    frozen = creds.get_frozen_credentials()
    return frozen.access_key, frozen.secret_key, frozen.token


def _make_bucket(client, bucket, region):
    """採取用のバケットを作る。"""
    kwargs = {'Bucket': bucket}
    if region != 'us-east-1':
        # us-east-1 以外は LocationConstraint が要る(us-east-1 は付けると弾かれる)
        kwargs['CreateBucketConfiguration'] = {'LocationConstraint': region}
    client.create_bucket(**kwargs)


def _drop_bucket(client, bucket):
    """生成したバケットを空にして削除する。**残骸を残さない。**

    採取の途中で例外が出ても呼ばれる(main の finally)。削除に失敗したら
    黙らずに、手で消すべきバケット名を標準エラーに出す。
    """
    counts = {'aborted_uploads': 0, 'deleted_versions': 0, 'deleted_objects': 0}
    try:
        for page in client.get_paginator(
                'list_multipart_uploads').paginate(Bucket=bucket):
            for u in page.get('Uploads', []):
                client.abort_multipart_upload(
                    Bucket=bucket, Key=u['Key'], UploadId=u['UploadId'])
                counts['aborted_uploads'] += 1
        for page in client.get_paginator(
                'list_object_versions').paginate(Bucket=bucket):
            for kind in ('Versions', 'DeleteMarkers'):
                for o in page.get(kind, []):
                    client.delete_object(Bucket=bucket, Key=o['Key'],
                                         VersionId=o['VersionId'])
                    counts['deleted_versions'] += 1
        for page in client.get_paginator('list_objects_v2').paginate(Bucket=bucket):
            for o in page.get('Contents', []):
                client.delete_object(Bucket=bucket, Key=o['Key'])
                counts['deleted_objects'] += 1
        client.delete_bucket(Bucket=bucket)
    except Exception as e:
        print(f'[!] 生成バケットを削除できなかった: {bucket} '
              f'({type(e).__name__}: {e})', file=sys.stderr)
        print('    **手で削除すること。**', file=sys.stderr)
        return False
    print(f'生成バケットを削除した: {bucket} {counts}')
    return True


def _break_secret(secret):
    """シークレットの末尾 1 文字を別の文字に置き換える。

    元のシークレットは返り値に残らない…わけではない(末尾以外は同じ)ので、
    この値は**絶対に出力しない**。署名計算にだけ渡す。
    """
    last = secret[-1]
    return secret[:-1] + ('B' if last != 'B' else 'C')


def _nonexistent_bucket(bucket):
    """存在しないバケット名を作る。S3 の命名規則(63 文字以内・小文字)に収める。"""
    import uuid
    suffix = '-does-not-exist-' + uuid.uuid4().hex[:8]
    base = bucket.lower()[:63 - len(suffix)]
    return base + suffix


def _observe(fn):
    """呼び出して ClientError から Code / Message / status を取り出す。

    例外が出なかった場合は ``code: None``(= 成功)を返す。

    ClientError 以外も拾うのは、moto のような代替実装が生の例外
    (``KeyError`` など)を投げることがあり、そこで落ちると残りのケースの
    採取まで失われるため。AWS 実機では botocore が必ず ClientError にする。
    """
    from botocore.exceptions import ClientError
    try:
        fn()
    except ClientError as e:
        err = e.response.get('Error', {})
        meta = e.response.get('ResponseMetadata', {})
        return {
            'raised': True,
            'http_status': meta.get('HTTPStatusCode'),
            'code': err.get('Code'),
            'message': err.get('Message'),
        }
    except Exception as e:
        return {
            'raised': True,
            'http_status': None,
            'code': None,
            'message': f'{type(e).__name__}: {e}',
            'unexpected_exception': True,
        }
    return {'raised': False, 'http_status': 200, 'code': None, 'message': None}


def _abort(client, bucket, key, upload_id):
    try:
        client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
    except Exception as e:  # 後始末の失敗は記録するだけ
        return f'{type(e).__name__}'
    return 'ok'


def _cleanup(client, bucket, key, upload_id, obs):
    """ケースの後始末。complete が通ってしまった場合は実体も消す。

    「落ちるはず」の complete が通ることもありうる(moto では
    invalid-part-order が 200 で通った)。その場合 abort は効かないので、
    オブジェクトが残らないよう delete_object も試す。
    """
    out = {'abort': _abort(client, bucket, key, upload_id)}
    if not obs.get('raised'):
        try:
            client.delete_object(Bucket=bucket, Key=key)
            out['delete_object'] = 'deleted'
        except Exception as e:
            out['delete_object'] = type(e).__name__
    return out


def run_cases(client, bucket, deny_bucket, prefix, with_access_denied,
              region='us-east-1', access_key=None, secret_key=None,
              session_token=None):
    body_5m = b'0' * MIN_PART_SIZE
    body_1m = b'0' * (1024 * 1024)
    results = []

    def key_for(name):
        return f'{prefix}{name}'

    # ---------------- 1. no-such-upload
    key = key_for('no-such-upload')
    up = client.create_multipart_upload(Bucket=bucket, Key=key)['UploadId']
    cleanup = _abort(client, bucket, key, up)
    obs = _observe(lambda: client.complete_multipart_upload(
        Bucket=bucket, Key=key, UploadId=up,
        MultipartUpload={'Parts': [
            {'PartNumber': 1, 'ETag': '"d41d8cd98f00b204e9800998ecf8427e"'}]}))
    results.append(('no-such-upload', obs, {'pre_abort': cleanup}))

    # ---------------- 2. invalid-part
    key = key_for('invalid-part')
    up = client.create_multipart_upload(Bucket=bucket, Key=key)['UploadId']
    client.upload_part(Bucket=bucket, Key=key, UploadId=up, PartNumber=1, Body=body_5m)
    obs = _observe(lambda: client.complete_multipart_upload(
        Bucket=bucket, Key=key, UploadId=up,
        MultipartUpload={'Parts': [
            {'PartNumber': 1, 'ETag': '"00000000000000000000000000000000"'}]}))
    results.append(('invalid-part', obs, _cleanup(client, bucket, key, up, obs)))

    # ---------------- 3. entity-too-small
    key = key_for('entity-too-small')
    up = client.create_multipart_upload(Bucket=bucket, Key=key)['UploadId']
    e1 = client.upload_part(Bucket=bucket, Key=key, UploadId=up,
                            PartNumber=1, Body=body_1m)['ETag']
    e2 = client.upload_part(Bucket=bucket, Key=key, UploadId=up,
                            PartNumber=2, Body=body_1m)['ETag']
    obs = _observe(lambda: client.complete_multipart_upload(
        Bucket=bucket, Key=key, UploadId=up,
        MultipartUpload={'Parts': [{'PartNumber': 1, 'ETag': e1},
                                   {'PartNumber': 2, 'ETag': e2}]}))
    results.append(('entity-too-small', obs, _cleanup(client, bucket, key, up, obs)))

    # ---------------- 4. invalid-part-order
    key = key_for('invalid-part-order')
    up = client.create_multipart_upload(Bucket=bucket, Key=key)['UploadId']
    e1 = client.upload_part(Bucket=bucket, Key=key, UploadId=up,
                            PartNumber=1, Body=body_5m)['ETag']
    # 両方 5MiB にしておく。片方を小さくすると「非最終パートが小さい」に
    # 引っかかって EntityTooSmall が先に返り、順序の判定にならない
    # (moto ではそうなった。AWS 実機の順序はこのスクリプトで確かめる)。
    e2 = client.upload_part(Bucket=bucket, Key=key, UploadId=up,
                            PartNumber=2, Body=body_5m)['ETag']
    obs = _observe(lambda: client.complete_multipart_upload(
        Bucket=bucket, Key=key, UploadId=up,
        MultipartUpload={'Parts': [{'PartNumber': 2, 'ETag': e2},
                                   {'PartNumber': 1, 'ETag': e1}]}))
    results.append(('invalid-part-order', obs, _cleanup(client, bucket, key, up, obs)))

    # ---------------- 5. malformed-xml
    key = key_for('malformed-xml')
    up = client.create_multipart_upload(Bucket=bucket, Key=key)['UploadId']
    client.upload_part(Bucket=bucket, Key=key, UploadId=up, PartNumber=1, Body=body_5m)
    obs = _observe(lambda: client.complete_multipart_upload(
        Bucket=bucket, Key=key, UploadId=up, MultipartUpload={'Parts': []}))
    results.append(('malformed-xml', obs, _cleanup(client, bucket, key, up, obs)))

    # ---------------- 6. access-denied (任意)
    if with_access_denied and deny_bucket:
        key = key_for('access-denied')
        try:
            up = client.create_multipart_upload(Bucket=deny_bucket, Key=key)['UploadId']
        except Exception as e:
            results.append(('access-denied',
                            {'raised': True, 'http_status': None,
                             'code': getattr(e, 'response', {}).get(
                                 'Error', {}).get('Code', type(e).__name__),
                             'message': str(e)},
                            {'note': 'create_multipart_upload の時点で拒否された'}))
        else:
            try:
                etag = client.upload_part(Bucket=deny_bucket, Key=key, UploadId=up,
                                          PartNumber=1, Body=body_5m)['ETag']
            except Exception as e:
                results.append(('access-denied',
                                {'raised': True, 'http_status': None,
                                 'code': getattr(e, 'response', {}).get(
                                     'Error', {}).get('Code', type(e).__name__),
                                 'message': str(e)},
                                {'note': 'upload_part の時点で拒否された',
                                 'abort': _abort(client, deny_bucket, key, up)}))
            else:
                obs = _observe(lambda: client.complete_multipart_upload(
                    Bucket=deny_bucket, Key=key, UploadId=up,
                    MultipartUpload={'Parts': [{'PartNumber': 1, 'ETag': etag}]}))
                results.append(('access-denied', obs,
                                _cleanup(client, deny_bucket, key, up, obs)))

    # ---------------- 7. completed-twice
    key = key_for('completed-twice')
    up = client.create_multipart_upload(Bucket=bucket, Key=key)['UploadId']
    etag = client.upload_part(Bucket=bucket, Key=key, UploadId=up,
                              PartNumber=1, Body=body_5m)['ETag']
    parts = {'Parts': [{'PartNumber': 1, 'ETag': etag}]}
    first = _observe(lambda: client.complete_multipart_upload(
        Bucket=bucket, Key=key, UploadId=up, MultipartUpload=parts))
    second = _observe(lambda: client.complete_multipart_upload(
        Bucket=bucket, Key=key, UploadId=up, MultipartUpload=parts))
    extra = {'first_complete': first}
    try:
        client.head_object(Bucket=bucket, Key=key)
        extra['object_exists_after_second'] = True
    except Exception:
        extra['object_exists_after_second'] = False
    try:
        client.delete_object(Bucket=bucket, Key=key)
        extra['cleanup'] = 'deleted'
    except Exception as e:
        extra['cleanup'] = type(e).__name__
    results.append(('completed-twice', second, extra))

    # ---------------- 8. invalid-access-key-id
    # UploadId とパートは正しい資格情報で作り、complete だけ架空のキーで投げる。
    key = key_for('invalid-access-key-id')
    up = client.create_multipart_upload(Bucket=bucket, Key=key)['UploadId']
    etag = client.upload_part(Bucket=bucket, Key=key, UploadId=up,
                              PartNumber=1, Body=body_5m)['ETag']
    bad_key_client = _client(region, BOGUS_ACCESS_KEY, 'bogus-secret-not-a-real-one')
    obs = _observe(lambda: bad_key_client.complete_multipart_upload(
        Bucket=bucket, Key=key, UploadId=up,
        MultipartUpload={'Parts': [{'PartNumber': 1, 'ETag': etag}]}))
    results.append(('invalid-access-key-id', obs,
                    _cleanup(client, bucket, key, up, obs)))

    # ---------------- 9. signature-does-not-match
    if secret_key:
        key = key_for('signature-does-not-match')
        up = client.create_multipart_upload(Bucket=bucket, Key=key)['UploadId']
        etag = client.upload_part(Bucket=bucket, Key=key, UploadId=up,
                                  PartNumber=1, Body=body_5m)['ETag']
        bad_sig_client = _client(region, access_key, _break_secret(secret_key),
                                 session_token)
        obs = _observe(lambda: bad_sig_client.complete_multipart_upload(
            Bucket=bucket, Key=key, UploadId=up,
            MultipartUpload={'Parts': [{'PartNumber': 1, 'ETag': etag}]}))
        results.append(('signature-does-not-match', obs,
                        _cleanup(client, bucket, key, up, obs)))

    # ---------------- 10. no-such-bucket
    # 何も作らない。存在しないバケットに架空の UploadId で complete を投げる。
    ghost = _nonexistent_bucket(bucket)
    obs = _observe(lambda: client.complete_multipart_upload(
        Bucket=ghost, Key=key_for('no-such-bucket'),
        UploadId='ZmFrZS11cGxvYWQtaWQtZm9yLXMtNg',
        MultipartUpload={'Parts': [
            {'PartNumber': 1, 'ETag': '"d41d8cd98f00b204e9800998ecf8427e"'}]}))
    results.append(('no-such-bucket', obs, {
        'bucket': ghost,
        'note': 'NoSuchBucket と NoSuchUpload のどちらが先に返るかを見る。'
                '後始末は不要(何も作っていない)。',
    }))

    return results


def build_report(results, bucket, region, started_at, skipped):
    cases = []
    for name, obs, extra in results:
        code = obs.get('code')
        cases.append({
            'case': name,
            'raised': obs.get('raised'),
            'http_status': obs.get('http_status'),
            'code': code,
            'message': obs.get('message'),
            'in_definitive_table': bool(code) and code in DEFINITIVE_REJECTION_CODES,
            'wb_classification': classify(code) if code else 'N/A (例外が出なかった)',
            'extra': extra,
        })

    observed = {c['code'] for c in cases if c['code']}
    uncollected = sorted(DEFINITIVE_REJECTION_CODES - observed)
    unlisted = sorted(observed - DEFINITIVE_REJECTION_CODES)

    report = {
        'generated_at': datetime.now().isoformat(),
        'started_at': started_at,
        'bucket': bucket,
        'region': region,
        'definitive_rejection_codes': sorted(DEFINITIVE_REJECTION_CODES),
        'cases': cases,
        'skipped_cases': skipped,
        'observed_codes': sorted(observed),
        'uncollected_table_codes': uncollected,
        'uncollectable_by_design': UNCOLLECTABLE_REASONS,
        'codes_not_in_table': unlisted,
        'note': ('コード側(DEFINITIVE_REJECTION_CODES)は変更していない。'
                 '表に無いコードは WaterButler の既定どおり UNKNOWN として扱う'
                 '(E-1 の合格基準)。'),
    }
    return report


def build_markdown(report):
    lines = [
        '# S-6: CompleteMultipartUpload の Error Code 採取 (E-1)',
        '',
        f'- 採取日時: {report["generated_at"]}',
        f'- bucket: `{report["bucket"]}` / region: `{report["region"]}`',
        '- 突合先: RDM-waterbutler `waterbutler/providers/s3/provider.py` '
        'の `DEFINITIVE_REJECTION_CODES`(9 コード)',
        '- **コード側は変更していない。** 表に無いコードは既定の `UNKNOWN` として記録する。',
        '',
        '## 採取結果',
        '',
        '| ケース | HTTP | Code | 表にある | WB の分類 | Message |',
        '|---|---|---|---|---|---|',
    ]
    for c in report['cases']:
        msg = (c['message'] or '').replace('|', r'\|')
        if len(msg) > 80:
            msg = msg[:77] + '...'
        lines.append(
            '| `{case}` | {http} | `{code}` | {tbl} | `{cls}` | {msg} |'.format(
                case=c['case'],
                http=c['http_status'],
                code=c['code'] or '(例外なし)',
                tbl='✓' if c['in_definitive_table'] else '—',
                cls=c['wb_classification'],
                msg=msg))

    lines += ['', '## 9 コード表との突合', '',
              '| Code | 今回採取 | WB の扱い |', '|---|---|---|']
    observed = set(report['observed_codes'])
    for code in report['definitive_rejection_codes']:
        lines.append('| `{}` | {} | NOT_COMMITTED |'.format(
            code, '採取' if code in observed else '**未採取**'))
    for code in report['codes_not_in_table']:
        lines.append('| `{}` | 採取(**表に無い**) | UNKNOWN(既定) |'.format(code))

    if report['uncollected_table_codes']:
        lines += ['', '未採取のコードと理由:', '']
        for code in report['uncollected_table_codes']:
            reason = UNCOLLECTABLE_REASONS.get(
                code, '本スクリプトのケースでは出せなかった('
                      '該当ケースがスキップされたか、実装差で別のコードが返った)。')
            lines.append(f'- `{code}` — {reason}')

    if report['skipped_cases']:
        lines += ['', '## スキップしたケース', '']
        for name, why in report['skipped_cases'].items():
            lines.append(f'- `{name}`: {why}')

    lines += ['', '## 注記', '', report['note'], '']

    twice = [c for c in report['cases'] if c['case'] == 'completed-twice']
    if twice:
        c = twice[0]
        lines += [
            '`completed-twice` は「1 回成功したあと同じ UploadId で complete を'
            'やり直す」ケース。返ってきたのは '
            f'`{c["code"] or "(例外なし)"}`、'
            'このとき対象オブジェクトは '
            f'{"存在する" if c["extra"].get("object_exists_after_second") else "存在しない"}。'
            'これが `NoSuchUpload` なら、**そのコードだけでは「オブジェクトは'
            'できていない」と断定できない**ことの実機根拠になる'
            '(provider.py が `NoSuchUpload` を表に入れず UNKNOWN 既定にしている理由)。',
            '',
        ]
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        description='AWS S3 の CompleteMultipartUpload 失敗コードを採取する (S-6 / E-1)')
    parser.add_argument('--out', default=os.environ.get('E2E_EVIDENCE_DIR', '.'),
                        help='証跡の出力先ディレクトリ (既定: $E2E_EVIDENCE_DIR か .)')
    parser.add_argument('--prefix', default='s6-complete-error/',
                        help='テスト用オブジェクトのキーの接頭辞')
    parser.add_argument('--dry-run', action='store_true',
                        help='AWS にアクセスせず、呼び出し計画だけを印字する')
    parser.add_argument('--with-access-denied', action='store_true',
                        help='access-denied ケースを実施する'
                             '(E2E_S3_DENY_BUCKET が必要)')
    parser.add_argument('--create-bucket', action='store_true',
                        help='採取用のバケットを作り、終了時に空にして削除する'
                             '(E2E_S3_BUCKET は不要)')
    args = parser.parse_args(argv)

    bucket = os.environ.get('E2E_S3_BUCKET')
    region = os.environ.get('E2E_S3_REGION', 'us-east-1')
    deny_bucket = os.environ.get('E2E_S3_DENY_BUCKET')

    if args.dry_run:
        return print_plan(args, bucket, region, deny_bucket)

    if not bucket and not args.create_bucket:
        print('バケットが決まらない。E2E_S3_BUCKET を設定するか '
              '--create-bucket を付けること。', file=sys.stderr)
        return 2

    # 資格情報は boto3 の既定の解決順に任せる(AWS_PROFILE でもよい)。
    access_key, secret_key, session_token = _resolve_credentials()
    if access_key is None:
        print('資格情報が解決できない。AWS_PROFILE か '
              'AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY を設定すること。',
              file=sys.stderr)
        print('(--dry-run なら資格情報なしで呼び出し計画だけ見られる)', file=sys.stderr)
        return 2

    skipped = {}
    if not args.with_access_denied:
        skipped['access-denied'] = '--with-access-denied が指定されていない'
    elif not deny_bucket:
        skipped['access-denied'] = 'E2E_S3_DENY_BUCKET が未設定'

    client = _client(region)
    created_bucket = None
    if args.create_bucket:
        bucket = 'e2e-sigv4-s6-' + datetime.now().strftime('%Y%m%d-%H%M%S')
        _make_bucket(client, bucket, region)
        created_bucket = bucket
        print(f'採取用バケットを生成した: {bucket} ({region})')

    started_at = datetime.now().isoformat()
    try:
        results = run_cases(client, bucket, deny_bucket, args.prefix,
                            args.with_access_denied,
                            region=region, access_key=access_key,
                            secret_key=secret_key, session_token=session_token)

        report = build_report(results, bucket, region, started_at, skipped)
        text_json = redact(json.dumps(report, indent=2, ensure_ascii=False))
        text_md = redact(build_markdown(report))
        assert_no_credentials(text_json, access_key, secret_key)
        assert_no_credentials(text_md, access_key, secret_key)

        os.makedirs(args.out, exist_ok=True)
        path_json = os.path.join(args.out, OUT_JSON)
        path_md = os.path.join(args.out, OUT_MD)
        with open(path_json, 'w', encoding='utf-8') as f:
            f.write(text_json + '\n')
        with open(path_md, 'w', encoding='utf-8') as f:
            f.write(text_md + '\n')
    finally:
        # 採取が途中で落ちても生成バケットは残さない。
        if created_bucket:
            _drop_bucket(client, created_bucket)

    print(text_md)
    print()
    print('wrote:', path_json)
    print('wrote:', path_md)
    if report['codes_not_in_table']:
        print()
        print('[!] 表に無いコードを採取した: '
              + ', '.join(report['codes_not_in_table']))
        print('    コードは変更せず、UNKNOWN 既定のまま記録した'
              '(E-1 の合格基準)。')
    return 0


if __name__ == '__main__':
    sys.exit(main())

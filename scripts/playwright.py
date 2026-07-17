# ユーティリティ関数群
import asyncio
from datetime import datetime
import os
import shutil
import sys
import tempfile
import time
import traceback

from IPython.display import Image
from playwright.async_api import async_playwright, expect

playwright = None
current_session_id = None
current_browser = None
current_browser_type = None
current_contexts = None
default_last_path = None
context_close_on_fail = True
current_ignore_https_errors = False
temp_dir = None
console_messages = []

async def run_pw(f, last_path=default_last_path, screenshot=True, permissions=None, new_context=False, new_page=False):
    global current_browser
    global current_browser_type
    if current_browser is None:
        browser_type = current_browser_type or 'chromium'
        if browser_type == 'firefox':
            current_browser = await playwright.firefox.launch(
                headless=True,
                args=[],
            )
        else:
            current_browser = await playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--lang=ja"],
            )
    
    global current_contexts
    if current_contexts is None or len(current_contexts) == 0 or new_context:
        videos_dir = os.path.join(temp_dir, 'videos/')
        os.makedirs(videos_dir, exist_ok=True)
        har_path = os.path.join(temp_dir, 'har.zip')

        context = await current_browser.new_context(
            locale="ja-JP",
            record_video_dir=videos_dir,
            record_har_path=har_path,
            ignore_https_errors=current_ignore_https_errors,
        )
        if current_contexts is None:
            current_contexts = [(context, [])]
        else:
            current_contexts.append((context, []))

    current_context, current_pages = current_contexts[-1]
    if len(current_pages) == 0 or new_page:
        page = await current_context.new_page()
        page.on("console", lambda msg: console_messages.append({
            "timestamp": time.time(),
            "url": page.url,
            "type": msg.type,
            "text": msg.text
        }))
        current_pages.append(page)

    current_time = time.time()
    print(f'Start epoch: {current_time} seconds')
    if permissions is not None:
        await current_context.grant_permissions(permissions)
    next_page = None
    if f is not None:
        try:
            next_page = await f(current_pages[-1])
        except:
            try:
                await _save_dom(last_path=last_path)
            except Exception:
                print('DOMダンプの取得に失敗しました。', file=sys.stderr)
                traceback.print_exc()
            if context_close_on_fail:
                await finish_pw_context(screenshot=screenshot, last_path=last_path)
                raise
            if screenshot:
                await _save_screenshot()
            raise
    if next_page is not None:
        current_pages.append(next_page)
    screenshot_path = os.path.join(temp_dir, 'screenshot.png')
    await current_pages[-1].screenshot(path=screenshot_path)
    return Image(screenshot_path)

async def close_latest_page(last_path=None):
    global current_contexts
    if current_contexts is None or len(current_contexts) == 0:
        raise Exception('No contexts')
    current_context, current_pages = current_contexts[-1]
    if len(current_contexts) <= 1 and len(current_pages) <= 1:
        raise Exception('It is only possible to close when two or more contexts or pages are stacked')
    os.makedirs(last_path or default_last_path, exist_ok=True)
    last_page = current_pages[-1]
    if last_page in current_pages[:-1] or any([last_page in p for _, p in current_contexts[:-1]]):
        # まだインスタンスがページ一覧に存在する場合は、スタックから削除するだけ
        assert len(current_pages) > 0, current_pages
        current_contexts[-1] = (current_context, current_pages[:-1])
        return
    video_path = await last_page.video.path()
    index = len(current_pages)
    dest_video_path = os.path.join(last_path or default_last_path, f'video-{index}.webm')
    shutil.copyfile(video_path, dest_video_path)
    current_pages = current_pages[:-1]
    current_contexts[-1] = (current_context, current_pages)
    await last_page.close()
    if len(current_pages) > 0:
        return
    current_contexts = current_contexts[:-1]
    await current_context.close()

async def init_pw_context(close_on_fail=True, last_path=None, browser_type='chromium', ignore_https_errors=False):
    global playwright, current_session_id, default_last_path, current_browser, current_browser_type, temp_dir, context_close_on_fail, current_ignore_https_errors, current_contexts, console_messages
    if current_browser is not None:
        await current_browser.close()
        current_browser = None
    if playwright is not None:
        await playwright.stop()
        playwright = None
    playwright = await async_playwright().start()
    current_session_id = datetime.now().strftime('%Y%m%d-%H%M%S')
    default_last_path = last_path or os.path.join(os.path.expanduser('~/last-screenshots'), current_session_id)
    temp_dir = tempfile.mkdtemp()
    context_close_on_fail = close_on_fail
    current_browser_type = browser_type
    current_ignore_https_errors = ignore_https_errors
    if current_contexts is not None:
        for current_context in current_contexts:
            await current_context.close()
    current_contexts = None
    console_messages = []
    return (current_session_id, temp_dir)

async def finish_pw_context(screenshot=False, last_path=None, timeout=30):
    global current_browser
    try:
        await asyncio.wait_for(
            _finish_pw_context(screenshot=screenshot, last_path=last_path),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        print(f'finish_pw_context timed out after {timeout} seconds', file=sys.stderr)
    if current_browser is not None:
        try:
            await asyncio.wait_for(current_browser.close(), timeout=10)
        except asyncio.TimeoutError:
            print('browser.close() timed out', file=sys.stderr)
        current_browser = None

async def save_screenshot(path):
    if current_contexts is None or len(current_contexts) == 0:
        raise Exception('No contexts')
    _, current_pages = current_contexts[-1]
    if current_pages is None or len(current_pages) == 0:
        raise Exception('Unexpected state')
    await current_pages[-1].screenshot(path=path)
    return path

async def _save_screenshot(last_path=None):
    if current_contexts is None or len(current_contexts) == 0:
        raise Exception('No contexts')
    _, current_pages = current_contexts[-1]
    os.makedirs(last_path or default_last_path, exist_ok=True)
    if current_pages is None or len(current_pages) == 0:
        return
    screenshot_path = os.path.join(temp_dir, 'last-screenshot.png')
    await current_pages[-1].screenshot(path=screenshot_path, full_page=True)
    dest_screenshot_path = os.path.join(last_path or default_last_path, 'last-screenshot.png')
    shutil.copyfile(screenshot_path, dest_screenshot_path)
    print(f'Screenshot: {dest_screenshot_path}')

async def _save_dom(last_path=None):
    if current_contexts is None or len(current_contexts) == 0:
        return
    _, current_pages = current_contexts[-1]
    if current_pages is None or len(current_pages) == 0:
        return
    os.makedirs(last_path or default_last_path, exist_ok=True)
    page = current_pages[-1]
    parts = []
    # Dump every frame; do not assume which frame holds the form.
    for frame in page.frames:
        try:
            content = await frame.content()
        except Exception as e:
            content = f'<!-- frame unavailable url={frame.url}: {e} -->'
        parts.append(f'<!-- ===== FRAME url={frame.url} name={frame.name} ===== -->\n{content}')
    dest_dom_path = os.path.join(last_path or default_last_path, 'last-dom.html')
    with open(dest_dom_path, 'w', encoding='utf-8') as fh:
        fh.write('\n\n'.join(parts))
    print(f'DOM: {dest_dom_path}')

async def _finish_pw_context(screenshot=False, last_path=None):
    global current_contexts
    if current_contexts is None or len(current_contexts) == 0:
        return
    current_context, current_pages = current_contexts[-1]
    os.makedirs(last_path or default_last_path, exist_ok=True)
    timeout_on_screenshot = False
    if screenshot and current_pages is not None and len(current_pages) > 0:
        try:
            await _save_screenshot(last_path=last_path)
        except:
            print('スクリーンショットの取得に失敗しました。', file=sys.stderr)
            traceback.print_exc()
            timeout_on_screenshot = True
    if timeout_on_screenshot:
        return
    current_contexts = current_contexts[::-1]
    await current_context.close()
    for i, current_page in enumerate(current_pages):
        index = i + 1
        try:
            video_path = await current_page.video.path()
            dest_video_path = os.path.join(last_path or default_last_path, f'video-{index}.webm')
            shutil.copyfile(video_path, dest_video_path)
            print(f'Video: {dest_video_path}')
        except:
            print('スクリーンキャプチャ動画の取得に失敗しました。', file=sys.stderr)
            traceback.print_exc()
            timeout_on_screenshot = True
    if timeout_on_screenshot:
        return   
    har_path = os.path.join(temp_dir, 'har.zip')
    dest_har_path = os.path.join(last_path or default_last_path, 'har.zip')
    if os.path.exists(har_path):
        shutil.copyfile(har_path, dest_har_path)
        print(f'HAR: {dest_har_path}')
    else:
        print('.harファイルの取得に失敗しました。', file=sys.stderr)
    console_log_path = os.path.join(last_path or default_last_path, 'console.log')
    with open(console_log_path, 'w') as f:
        for msg in console_messages:
            f.write(f"{msg['timestamp']:.3f} {msg['url']} [{msg['type']}] {msg['text']}\n")
    print(f'Console: {console_log_path}')
    shutil.rmtree(temp_dir)
    for page in current_pages:
        await page.close()
    if len(current_contexts) == 0:
        return
    await _finish_pw_context(screenshot=False, last_path=last_path)

async def mock_clipboard(page):
    """Mock navigator.clipboard for non-secure contexts."""
    await page.evaluate("""
        () => {
            const clipboard = {
                _mocked: true,
                _text: null,
                async writeText(text) {
                    this._text = text;
                },
                async readText() {
                    return this._text;
                }
            };
            Object.defineProperty(navigator, 'clipboard', {
                value: clipboard,
                writable: true,
                configurable: true
            });
        }
    """)

async def get_mocked_clipboard_text(page):
    """Get text from the mocked clipboard."""
    is_mocked = await page.evaluate("() => navigator.clipboard?._mocked")
    if not is_mocked:
        raise RuntimeError("Clipboard is not mocked. Call mock_clipboard(page) first.")
    return await page.evaluate("() => navigator.clipboard._text")
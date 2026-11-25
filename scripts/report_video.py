"""Record notebook cells' active pages with QR identifiers in the video."""
import base64
import contextvars
import functools
import inspect
import io
import json
import secrets
import weakref
from pathlib import Path

import zxingcpp
from PIL import Image
from playwright.async_api import (
    Browser, Frame, Locator, LocatorAssertions, Page, PageAssertions, expect,
)

VIEWPORT = {'width': 1280, 'height': 720}
INIT_SCRIPT = '''(() => {
  if (window !== window.top) return;
  const host = document.createElement('div');
  host.style.cssText = 'display:none;position:fixed;bottom:8px;right:8px;z-index:2147483647;pointer-events:none';
  const root = host.attachShadow({mode:'open'});
  const image = document.createElement('img');
  image.style.cssText = 'display:block;width:165px;height:12px';
  root.append(image);
  let explicitlySet = false;
  const setQR = async (src) => {
    host.style.display = src ? 'block' : 'none';
    if (src) { image.src = src; await image.decode(); }
    return true;
  };
  const mount = () => document.documentElement.append(host);
  if (document.documentElement) mount();
  else document.addEventListener('DOMContentLoaded', mount, {once:true});
  window.__setReportQR = (src) => { explicitlySet = true; return setQR(src); };
  window.__readReportQR().then(src => { if (!explicitlySet) return setQR(src); });
})();'''


class Recorder:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.run = secrets.token_hex(4)
        self.cell = None
        self.active = None
        self.pages = []
        self.contexts = []
        self.cells = []
        self.segments = []
        self.patches = []
        self.marker = ''
        self.saved = {}
        self.guard = contextvars.ContextVar('report_video_guard', default=False)
        self.assertion_pages = weakref.WeakKeyDictionary()

    def register_page(self, page):
        if page not in self.pages:
            self.pages.append(page)
        return self.pages.index(page) + 1

    async def attach(self, context):
        self.contexts.append(context)
        context._procedure_recorder = self
        def marker(source):
            self.register_page(source['page'])
            return self.marker if source['page'] == self.active else ''
        await context.expose_binding('__readReportQR', marker)
        await context.add_init_script(script=INIT_SCRIPT)
        context.on('page', self.register_page)

    async def set_marker(self, page, source):
        reset = self.guard.set(True)
        try:
            await page.wait_for_function('(src) => window.__setReportQR && window.__setReportQR(src)',
                                         arg=source)
        finally:
            self.guard.reset(reset)

    async def begin_cell(self, index, scenario, step, title):
        if self.active is not None and not self.active.is_closed():
            await self.set_marker(self.active, '')
        self.active = None
        self.cell = {'index': index, 'scenario': scenario, 'step': step, 'title': title}
        self.cells.append(self.cell)

    async def focus(self, page):
        if self.cell is None or page == self.active:
            return
        if self.active is not None and not self.active.is_closed():
            await self.set_marker(self.active, '')
        token = len(self.segments) + 1
        payload = f"{self.run}:{self.cell['index']:04x}:{token:04x}"
        digits = f"{int(payload.replace(':', ''), 16):020d}"
        barcode = zxingcpp.create_barcode(digits, zxingcpp.BarcodeFormat.Code128)
        bars = zxingcpp.write_barcode_to_image(barcode)
        image = Image.frombytes('L', (bars.shape[1], bars.shape[0]), bytes(bars))
        png = io.BytesIO()
        image.resize((165, 12), Image.Resampling.NEAREST).save(png, format='PNG')
        self.marker = 'data:image/png;base64,' + base64.b64encode(png.getvalue()).decode()
        self.active = page
        self.segments.append({'token': token, 'qr': payload,
                              'page': self.register_page(page), 'cell': self.cell['index']})
        await self.set_marker(page, self.marker)

    def patch(self, cls, name, replacement):
        self.patches.append((cls, name, getattr(cls, name)))
        setattr(cls, name, replacement)

    def install(self):
        recorder = self
        new_context = Browser.new_context
        async def recorded_context(browser, *args, **kwargs):
            kwargs.update(record_video_dir=str(recorder.directory / 'raw'),
                          record_video_size=VIEWPORT, viewport=VIEWPORT)
            context = await new_context(browser, *args, **kwargs)
            await recorder.attach(context)
            return context
        self.patch(Browser, 'new_context', recorded_context)
        close_browser = Browser.close
        async def recorded_close(browser, *args, **kwargs):
            await recorder.save_browser(browser)
            return await close_browser(browser, *args, **kwargs)
        self.patch(Browser, 'close', recorded_close)

        def wrap(method, target):
            @functools.wraps(method)
            async def focused(obj, *args, **kwargs):
                if not recorder.guard.get():
                    await recorder.focus(target(obj))
                return await method(obj, *args, **kwargs)
            return focused

        # The page comes from the action/assertion, not from tab creation or OS focus.
        for cls, target in [(Page, lambda obj: obj), (Frame, lambda obj: obj.page),
                            (Locator, lambda obj: obj.page)]:
            for name, method in vars(cls).items():
                if (inspect.iscoroutinefunction(method) and not name.startswith('_')
                    and name not in {'close', 'screenshot', 'add_init_script',
                                     'expose_binding', 'expose_function'}):
                    self.patch(cls, name, wrap(method, target))
        expect_type = type(expect)
        original_call = expect_type.__call__
        def tracked_expect(expect, actual, *args, **kwargs):
            assertion = original_call(expect, actual, *args, **kwargs)
            if isinstance(actual, (Page, Locator)):
                recorder.assertion_pages[assertion] = actual if isinstance(actual, Page) else actual.page
            return assertion
        self.patch(expect_type, '__call__', tracked_expect)
        for cls in (LocatorAssertions, PageAssertions):
            for name, method in vars(cls).items():
                if inspect.iscoroutinefunction(method) and not name.startswith('_'):
                    self.patch(cls, name, wrap(method, lambda obj: recorder.assertion_pages[obj]))

    async def save_browser(self, browser):
        for context in self.contexts:
            if context.browser == browser:
                await context.close()
        for index, page in enumerate(self.pages, 1):
            if page.context.browser == browser and page not in self.saved:
                filename = f'page-{index}.webm'
                await page.video.save_as(self.directory / filename)
                self.saved[page] = {'page': index, 'file': filename}

    async def finish(self):
        for cls, name, original in reversed(self.patches):
            setattr(cls, name, original)
        for browser in dict.fromkeys(context.browser for context in self.contexts):
            if browser.is_connected():
                await self.save_browser(browser)
                await browser.close()
        if len(self.saved) != len(self.pages):
            raise ValueError('A browser closed before its videos were saved')
        manifest = {'run': self.run, 'cells': self.cells,
                    'segments': self.segments, 'videos': list(self.saved.values())}
        (self.directory / 'recording.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

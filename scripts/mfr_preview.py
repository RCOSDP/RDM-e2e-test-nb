"""Shared assertions for the file-preview procedure notebook."""

from playwright.async_api import expect

from scripts import grdm


FRAME = 'iframe[src*="/render"]'


def viewer(page):
    return page.frame_locator(FRAME)


async def open_file(page, filename, timeout):
    await grdm.get_select_file_title_locator(page, filename).click()
    await expect(page.locator(FRAME)).to_be_visible(timeout=timeout)


async def file_list(page, storage_name, timeout):
    await page.locator('#projectNavFiles a').click()
    await expect(page.locator(FRAME)).to_have_count(0, timeout=timeout)
    await expect(grdm.get_select_expanded_storage_title_locator(
        page, storage_name
    )).to_be_visible(timeout=timeout)


async def expect_image(page, timeout):
    image = viewer(page).locator('#base-image')
    await expect(image).to_be_visible(timeout=timeout)
    await expect(image).to_have_js_property('complete', True, timeout=timeout)
    await expect(image).to_have_js_property('naturalWidth', 640, timeout=timeout)
    await expect(image).to_have_js_property('naturalHeight', 480, timeout=timeout)


# The PDF viewer's markup differs between the PDF.js generations MFR has shipped. 1.x gives
# each page an id and prints through canvases; 2.x and later mark pages with data-page-number,
# print through images and name some toolbar buttons differently. The structure that is actually
# on the page selects the entries used; anything else is reported instead of guessed.
PDF_VIEWER_MARKUP = {
    'legacy': {
        'page': '#pageContainer{number}',
        'printed_page': 'canvas',
        'find_button': '#viewFind',
        'print_button': '#print',
    },
    'modern': {
        'page': '#viewer .page[data-page-number="{number}"]',
        'printed_page': '.printedPage img',
        'find_button': '#viewFindButton',
        'print_button': '#printButton',
    },
}


async def pdf_markup(frame, timeout):
    """Return the PDF_VIEWER_MARKUP key for the page structure the viewer has rendered."""
    await expect(frame.locator('#viewer .page').first).to_be_attached(timeout=timeout)
    legacy = await frame.locator(PDF_VIEWER_MARKUP['legacy']['page'].format(number=1)).count()
    modern = await frame.locator(PDF_VIEWER_MARKUP['modern']['page'].format(number=1)).count()
    if legacy == 1 and modern == 0:
        return 'legacy'
    if modern == 1 and legacy == 0:
        return 'modern'
    raise AssertionError(
        f'unexpected PDF viewer page markup: {legacy} legacy and {modern} modern first pages'
    )


def pdf_page(frame, markup, number):
    return frame.locator(PDF_VIEWER_MARKUP[markup]['page'].format(number=number))


async def expect_pdf_page(page, number, text, timeout):
    frame = viewer(page)
    await expect(frame.locator('#viewer .page')).to_have_count(2, timeout=timeout)
    await expect(frame.locator('#pageNumber')).to_have_value(str(number), timeout=timeout)
    current = pdf_page(frame, await pdf_markup(frame, timeout), number)
    await expect(current.locator('.textLayer')).to_contain_text(text, timeout=timeout)
    await expect(current.locator('canvas')).to_be_visible(timeout=timeout)


async def expect_pdf_page_text(page, number, text, timeout):
    """The text layer of the given page contains the text (the document is already shown)."""
    frame = viewer(page)
    current = pdf_page(frame, await pdf_markup(frame, timeout), number)
    await expect(current.locator('.textLayer')).to_contain_text(text, timeout=timeout)


async def open_pdf_find(page, timeout):
    frame = viewer(page)
    await frame.locator(PDF_VIEWER_MARKUP[await pdf_markup(frame, timeout)]['find_button']).click()


async def expect_table(page, rows, timeout):
    frame = viewer(page)
    await expect(frame.locator('.slick-header-column')).to_have_text(
        ['名称', '数量', '日付'], timeout=timeout
    )
    grid_rows = frame.locator('#mfrGrid .slick-row')
    await expect(grid_rows).to_have_count(len(rows), timeout=timeout)
    for index, cells in enumerate(rows):
        await expect(grid_rows.nth(index).locator('.slick-cell')).to_have_text(
            cells, timeout=timeout
        )


async def wait_video(page, condition, timeout):
    video = await viewer(page).locator('video').element_handle(timeout=timeout)
    frame = await video.owner_frame()
    await frame.wait_for_function(condition, arg=video, timeout=timeout)


async def observe_pdf_print(page, timeout):
    sandbox = await page.locator(FRAME).get_attribute('sandbox')
    assert sandbox is None or 'allow-modals' in sandbox.split(), 'The preview iframe blocks printing'
    frame = viewer(page)
    printed_page = PDF_VIEWER_MARKUP[await pdf_markup(frame, timeout)]['printed_page']
    # Observe the viewer's real print path without replacing window.print. The pages the viewer
    # prepares for printing are counted as they are added to #printContainer: PDF.js 1.x adds
    # them synchronously while handling beforeprint, 2.x and later render them asynchronously
    # before calling print, and both empty the container again on afterprint.
    await frame.locator('body').evaluate('''(body, printedPage) => {
        body.dataset.printPages = '0';
        body.dataset.printComplete = 'false';
        const isPrintedPage = node => node.nodeType === Node.ELEMENT_NODE &&
            (node.matches(printedPage) || node.querySelector(printedPage) !== null);
        new MutationObserver(mutations => {
            let pages = Number(body.dataset.printPages);
            for (const mutation of mutations) {
                for (const node of mutation.addedNodes) {
                    if (isPrintedPage(node)) {
                        pages += 1;
                    }
                }
            }
            body.dataset.printPages = String(pages);
        }).observe(document.getElementById('printContainer'), {childList: true});
        window.addEventListener('afterprint', () => {
            body.dataset.printComplete = 'true';
        }, {once: true});
    }''', printed_page)


async def click_pdf_print(page, timeout):
    frame = viewer(page)
    markup = await pdf_markup(frame, timeout)
    print_button = frame.locator(PDF_VIEWER_MARKUP[markup]['print_button'])
    if markup == 'legacy' and not await print_button.is_visible():
        # the 1.x toolbar hides the print button in narrow views and offers it in the menu
        await frame.locator('#secondaryToolbarToggle').click()
        await frame.locator('#secondaryPrint').click()
        return
    await print_button.click()


async def expect_pdf_print(page, timeout):
    frame = viewer(page)
    await expect(frame.locator('body')).to_have_attribute('data-print-pages', '2', timeout=timeout)
    await expect(frame.locator('body')).to_have_attribute('data-print-complete', 'true', timeout=timeout)


async def wait_image_width(page, original, larger, timeout):
    image = await viewer(page).locator('.zoomImage').element_handle(timeout=timeout)
    frame = await image.owner_frame()
    comparison = 'image.width > original' if larger else 'Math.abs(image.width - original) <= 1'
    await frame.wait_for_function(
        f'([image, original]) => {comparison}',
        arg=[image, original], timeout=timeout,
    )

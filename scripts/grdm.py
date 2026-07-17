# GRDM Test on Playwright ユーティリティ関数群

import asyncio
import base64
import os
import re
import time
import traceback
from playwright.async_api import expect


async def login_cas(page, username, password):
    # find_element_by_xpath_with_retry(driver, '').send_keys(username)
    # find_element_by_xpath_with_retry(driver, '//input[@name = "password"]').send_keys(password)
    # find_element_by_xpath_with_retry(driver, '//input[@type = "submit"]').click()
    await page.locator('//input[@name = "username"]').fill(username);
    await page.locator('//input[@name = "password"]').fill(password);
    await page.locator('//input[@type = "submit"]').click();

async def login_fakecas(page, username):
    """FakeCAS用のログイン処理"""
    # ユーザー名を入力
    await page.locator('#username').fill(username)
    # Sign Inボタンをクリック
    await page.locator('#submit').click()

async def expect_idp_login(page, idp_name, timeout=30000):
    # Shibboleth Login Page
    login_page_locators = _get_login_page_locators(idp_name)
    await expect(page.locator(login_page_locators['username'])).to_be_editable(timeout=timeout)

async def login_as_admin(page, idp_name, idp_username, idp_password, transition_timeout=30000):
    if idp_name is None or idp_name == 'FakeCAS':
        # CAS/FakeCASでログイン
        await page.locator('#id_email').fill(idp_username)
        await page.locator('#id_password').fill(idp_password)
        await page.locator('//button[text() = "サインイン"]').click()
        await expect(page.locator('//*[@href="/account/logout/"]')).to_be_visible(timeout=transition_timeout)
        try:
            # 念のためツールバーを隠すボタンを押しておく - なければ無視
            await page.locator('#djHideToolBarButton').click()
        except:
            print('Skipped hiding toolbar')
            traceback.print_exc()
        return
    try:
        # IdPリストから所望のIdPを選択
        idplist = page.locator('//form[@id = "IdPList"]//input[@type = "text"]')
        await idplist.fill(idp_name);
        await idplist.press('Enter');
        # ドロップダウンリストから一致するIdPをクリック
        idp_option = page.locator(f'//div[@class = "wayf_list_idp" and text() = "{idp_name}"]').first
        await expect(idp_option).to_be_visible(timeout=transition_timeout)
        await idp_option.click()

        # 選択ボタンが有効になったことを確認
        locator_wayf_submit = page.locator('//input[@id = "wayf_submit_button"]')
        await expect(locator_wayf_submit).to_be_enabled(timeout=transition_timeout)
        await locator_wayf_submit.click()

        # アカウント入力欄が編集可能になったことを確認
        await expect_idp_login(page, idp_name, timeout=transition_timeout)

        await _login_idp_pw(page, idp_name, idp_username, idp_password, transition_timeout=transition_timeout)
    except:
        traceback.print_exc()

        print('ユーザー名とパスワードによるログインを試みます...')
        # すでにIdP選択済みとみなし、ユーザー名とパスワード入力を試みる
        await _login_idp_pw(page, idp_name, idp_username, idp_password, transition_timeout=transition_timeout)

async def login(page, idp_name, idp_username, idp_password, transition_timeout=30000):
    if idp_name is None:
        # CASでログイン
        if '/login' not in page.url:
            # 現在CAS以外→一旦ログインボタンを押す
            await page.locator('//button[text() = "ログイン"]').click()
        await login_cas(page, idp_username, idp_password)
        return
    
    # FakeCASの場合の処理
    if idp_name == 'FakeCAS':
        # FakeCAS(port 8080)でない場合のみサインインボタンをクリック
        if ':8080' not in page.url:
            await page.locator('//button[@data-test-sign-in-button]').click()
        await login_fakecas(page, idp_username)
        return
    
    # 通常のIdP選択フロー（GakuNin RDM IdP, Orthrosなど）
    try:
        await page.locator('//*[@id = "dropdown_img"]').click()

        # IdPが要素として作成されることを確認
        locator = page.locator(f'//*[@class = "list_idp" and text() = "{idp_name}"]')
        await expect(locator).to_be_visible(timeout=transition_timeout)
        time.sleep(5)
        await locator.click()

        # 選択ボタンが有効になったことを確認
        locator_wayf_submit = page.locator('//input[@id = "wayf_submit_button"]')
        await expect(locator_wayf_submit).to_be_enabled(timeout=transition_timeout)
        await locator_wayf_submit.click()

        await _login_idp_pw(page, idp_name, idp_username, idp_password, transition_timeout=transition_timeout)
    except:
        traceback.print_exc()

        print('ユーザー名とパスワードによるログインを試みます...')
        # すでにIdP選択済みとみなし、ユーザー名とパスワード入力を試みる
        await _login_idp_pw(page, idp_name, idp_username, idp_password, transition_timeout=transition_timeout)

async def logout(page, idp_name, transition_timeout=30000):
    """GRDMからログアウトする"""
    ember_profile_dropdown = page.locator('//a[@data-test-auth-dropdown-toggle]')
    if await ember_profile_dropdown.count() > 0:
        await ember_profile_dropdown.click()
        await page.locator('//*[@data-test-ad-logout]').click()
    else:
        await page.locator('//div[@class = "nav-profile-name"]').click()
        await page.locator('//*[contains(text(), "ログアウト")]').click()

    if idp_name == 'FakeCAS':
        await expect(page.locator('//button[@data-test-sign-in-button]')).to_be_visible(timeout=transition_timeout)
    elif idp_name is not None:
        await expect(page.locator('//*[@id = "dropdown_img"]')).to_be_visible(timeout=transition_timeout)
    else:
        await expect(page.locator('//button[text() = "ログイン"]')).to_be_visible(timeout=transition_timeout)

async def expect_anonymous_toppage(page, idp_name, transition_timeout=30000):
    """未ログイン状態のGRDMトップページが表示されていることを確認する"""
    if not idp_name or idp_name == 'FakeCAS':
        await expect(page.locator('//button[text() = "ログイン"]')).to_be_visible(timeout=transition_timeout)
    else:
        await expect(page.locator('#wayf_submit_button')).to_be_visible(timeout=transition_timeout)

async def _login_idp_pw(page, idp_name, idp_username, idp_password, transition_timeout=30000):
    login_proc = _login_handlers[idp_name]
    await login_proc(page, idp_username, idp_password, transition_timeout)

async def _login_grdm_idp_pw(page, idp_username, idp_password, transition_timeout):
    # Shibboleth Login Page
    login_page_locators = _get_login_page_locators('GakuNin RDM IdP')
    username_fields = await page.locator(login_page_locators['username']).count()
    if username_fields > 0:
        # アカウント入力欄が編集可能になったことを確認
        await expect_idp_login(page, 'GakuNin RDM IdP', timeout=transition_timeout)
        # ユーザー名入力を求められた
        password_fields = await page.locator('#password').count()
        submit_buttons = await page.locator('//button[@type = "submit"]').count()
        assert username_fields == 1 and password_fields == 1 and submit_buttons == 1, (username_fields, password_fields, submit_buttons)
        # メールアドレスとパスワードを入力
        await page.locator(login_page_locators['username']).fill(idp_username)
        await page.locator(login_page_locators['password']).fill(idp_password)

        # サインインボタンが押下可能であることを確認
        await expect(page.locator(login_page_locators['submit'])).to_be_enabled(timeout=transition_timeout)
        # サインインボタンをクリック
        await page.locator(login_page_locators['submit']).click()

    # チェック「Ask me again at next login」が表示されることを確認
    await expect(page.locator('#_shib_idp_doNotRememberConsent')).to_be_enabled(timeout=transition_timeout)
    await page.locator('#_shib_idp_doNotRememberConsent').click()
    await expect(page.locator('#_shib_idp_doNotRememberConsent')).to_be_checked()

    await expect(page.locator('//*[@name="_eventId_proceed"]')).to_be_enabled()
    await page.locator('//*[@name="_eventId_proceed"]').click()

def _get_login_page_locators(idp_name):
    if idp_name == 'GakuNin RDM IdP':
        return {
            'username': '#username',
            'password': '#password',
            'submit': '//button[@type = "submit"]'
        }
    return {
        'username': '#signInName',
        'password': '#password',
        'submit': '#next'
    }

async def _login_orthros_pw(page, idp_username, idp_password, transition_timeout):
    signin_tab = page.locator('#signin_signup_tab label[tabIndex = "2"]')
    await expect(signin_tab).to_be_visible(timeout=transition_timeout)
    await signin_tab.click()

    await expect(page.locator('#next')).to_be_enabled()
    await page.locator('#signInName').fill(idp_username)
    await page.locator('#password').fill(idp_password)
    await page.locator('#next').click()

_login_handlers = {
    'GakuNin RDM IdP': _login_grdm_idp_pw,
    'Orthros': _login_orthros_pw,
}

async def expect_dashboard(page, transition_timeout=30000, retries=3):
    # 429 Too many requestsで表示できない場合があるので、複数回リロードする
    remain = retries
    while remain > 0:
        try:
            # GRDMのボタンが表示されることを確認
            await expect(page.locator('//*[text() = "プロジェクト管理者" or contains(text(), "まだプロジェクトがありません。")]')).to_be_visible(timeout=transition_timeout)
            break
        except:
            if remain <= 0:
                raise
            remain -= 1
            traceback.print_exc()
            print('Retrying...')
            # 1分待って再チャレンジ
            await asyncio.sleep(60)            
    
async def ensure_project_exists(page, project_name, transition_timeout=30000):
    await expect(page.locator('//*[@data-test-create-project-modal-button]')).to_have_count(1, timeout=transition_timeout)
    try:
        await expect(page.locator(f'//*[@data-test-dashboard-item-title and text()="{project_name}"]')).to_be_visible()
        return False
    except:
        # プロジェクトが存在しない
        await page.locator('//*[@data-test-create-project-modal-button]').click()

        # プロジェクト名フィールドが表示される
        await expect(page.locator('//input[contains(@class, "project-name")]')).to_be_editable(timeout=transition_timeout)
        time.sleep(1)

        # プロジェクト名を入力
        await page.locator('//input[contains(@class, "project-name")]').fill(project_name)
    
        # 作成ボタンが有効化される
        create_button_locator = page.locator('//*[@data-test-create-project-submit]')
        await expect(create_button_locator).to_be_enabled()
    
        # 作成ボタンをクリック
        await create_button_locator.click()
    
        await expect(page.locator('//button[@data-test-stay-here]')).to_be_visible(timeout=transition_timeout)
        await page.locator('//button[@data-test-stay-here]').click()
        
        # プロジェクトダッシュボードが更新され、
        # GRDMのボタンが表示されることを確認
        await expect(page.locator('//*[text() = "プロジェクト管理者"]')).to_be_visible(timeout=transition_timeout)
        await expect(page.locator(f'//*[@data-test-dashboard-item-title and text()="{project_name}"]')).to_be_visible(timeout=transition_timeout)
        return True    

async def delete_project(page, transition_timeout=30000):
    await page.locator(f'//ul[contains(@class, "navbar-nav")]//a[text() = "設定"]').click()
    await asyncio.sleep(3)
    await page.locator('//button[text() = "プロジェクトを削除" and @data-target = "#nodesDelete"]').click()

    confirmation_label = page.locator('//strong[@data-bind = "text: confirmationString"]')
    await expect(confirmation_label).to_have_count(1, timeout=transition_timeout)
    confirmation = await confirmation_label.text_content()
    print(confirmation)

    time.sleep(1)
    confirmation_input = page.locator('//*[@data-bind = "editableHTML: {observable: confirmInput, onUpdate: handleEditableUpdate}"]')
    await confirmation_input.fill(confirmation)

    delete_button = page.locator('//a[contains(@class, "btn-danger") and text() = "削除"]')
    await expect(delete_button).to_be_visible()
    await delete_button.click()

def get_select_storage_title_locator(page, provider):
    return page.locator(get_select_storage_title_xpath(provider))

def get_select_storage_title_xpath(provider):
    return f'//*[contains(@class, "tb-td-first")]//*[contains(@style, "/static/addons/")]/../../following-sibling::*[contains(@class, "title-text")]//*[starts-with(text(), "{provider}")]'

def get_select_expanded_storage_title_locator(page, provider):
    return page.locator(get_select_expanded_storage_title_xpath(provider))

def get_select_expanded_storage_title_xpath(provider):
    return f'//*[contains(@class, "fa-minus")]/../..//*[contains(@style, "/static/addons/")]/../../following-sibling::*[contains(@class, "title-text")]//*[starts-with(text(), "{provider}")]'

def get_select_folder_title_locator(page, provider):
    return page.locator(get_select_folder_title_xpath(provider))

def get_select_folder_title_xpath(name):
    return f'//*[contains(@class, "tb-expand-icon-holder")]//i[contains(@class, "fa-folder")]/../../following-sibling::*[contains(@class, "title-text")]//*[text() = "{name}"]'

def get_select_folder_toggle_locator(page, provider, expanded=False, collapsed=False):
    return page.locator(get_select_folder_toggle_xpath(provider, expanded=expanded, collapsed=collapsed))

def get_select_folder_toggle_xpath(name, expanded=False, collapsed=False):
    base_xpath = f'//*[contains(@class, "title-text")]//*[text() = "{name}"]/../preceding-sibling::*[contains(@class, "tb-td-first")]//*[contains(@class, "tb-toggle-icon")]'
    if expanded:
        return f'{base_xpath}//i[contains(@class, "fa-minus")]'
    if collapsed:
        return f'{base_xpath}//i[contains(@class, "fa-plus")]'
    return base_xpath

def get_select_folder_droppable_locator(page, provider):
    return page.locator(get_select_folder_droppable_xpath(provider))

def get_select_folder_droppable_xpath(name):
    return f'//*[contains(@class, "tb-expand-icon-holder")]//i[contains(@class, "fa-folder")]/../../following-sibling::*[contains(@class, "title-text")]//*[text() = "{name}"]/../../..'

def get_select_folder_draggable_locator(page, provider):
    return page.locator(get_select_folder_draggable_xpath(provider))

def get_select_folder_draggable_xpath(name):
    return f'//*[contains(@class, "tb-expand-icon-holder")]//i[contains(@class, "fa-folder")]/../../following-sibling::*[contains(@class, "title-text")]//*[text() = "{name}"]/../..'

def get_select_file_title_locator(page, provider):
    return page.locator(get_select_file_title_xpath(provider))

def get_select_file_title_xpath(name):
    return f'//*[contains(@class, "tb-expand-icon-holder")]//*[contains(@class, "file-extension")]/../../following-sibling::*[contains(@class, "title-text")]//*[text() = "{name}"]'

def get_select_file_extension_locator(page, provider):
    return page.locator(get_select_file_extension_xpath(provider))

def get_select_file_extension_xpath(name):
    return f'//*[contains(@class, "title-text")]//*[text() = "{name}"]/../preceding-sibling::*[contains(@class, "tb-td-first")]//*[contains(@class, "file-extension")]'

def get_select_file_draggable_locator(page, provider):
    return page.locator(get_select_file_draggable_xpath(provider))

def get_select_file_draggable_xpath(name):
    return f'//*[contains(@class, "tb-expand-icon-holder")]//*[contains(@class, "file-extension")]/../../following-sibling::*[contains(@class, "title-text")]//*[text() = "{name}"]/../..'

async def wait_for_uploaded(page, filename, timeout=30000):
    await expect(page.locator(f'//*[text() = "{filename}"]/../following-sibling::*//*[@role = "progressbar"]')).to_have_count(0, timeout=timeout)
    await expect(get_select_file_title_locator(page, filename)).to_be_visible(timeout=timeout)

def _bytes_to_data_url(byte_data, mime_type="application/octet-stream"):
    """バイト配列をDataURLに変換"""
    base64_data = base64.b64encode(byte_data).decode('utf-8')
    return f"data:{mime_type};base64,{base64_data}"

async def upload_file(page, path):
    # Upload ボタンを使ってファイルをアップロード
    await page.locator('//i[contains(@class, "fa-upload")]/../*[text() = "アップロード"]').click()
    await page.set_input_files('//input[@type = "file"]', path, timeout=60000)

async def upload_folder(page, path):
    # フォルダのアップロード ボタンを使ってファイルをアップロード
    await page.locator('//i[contains(@class, "fa-plus")]/../*[text() = "フォルダのアップロード"]').click()
    await page.set_input_files('//input[@type = "file" and @webkitdirectory = "true"]', path, timeout=60000)

async def drop_file(page, element_locator, path):
    # based on: https://zenn.dev/st_little/articles/how-to-upload-files-in-playwright
    with open(path, 'rb') as f:
        buffer = f.read()

    # ページのコンテキスト内でDataTransferとFileを作成
    data_transfer = await page.evaluate_handle(
        """async ({ bufferData, localFileName, localFileType }) => {
            const dt = new DataTransfer();
    
            const blobData = await fetch(bufferData).then((res) => res.blob());
    
            const file = new File([blobData], localFileName, {
            type: localFileType,
            });
            dt.items.add(file);
            return dt;
        }""",
        {
            'bufferData': _bytes_to_data_url(buffer),
            'localFileName': os.path.split(path)[-1],
            'localFileType': '',
        }
    )

    await page.dispatch_event(element_locator, 'drop', {
        'dataTransfer': data_transfer
    })
    await data_transfer.dispose()

async def drag_and_drop(page, source, dest):
    await expect(source).to_have_class(re.compile('.*ui-draggable.*'))

    center_coordinates_source = await source.evaluate('''element => {
        const rect = element.getBoundingClientRect();
        return {
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2
        };
    }''')

    center_coordinates_dest = await dest.evaluate('''element => {
        const rect = element.getBoundingClientRect();
        return {
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2
        };
    }''')

    await page.mouse.move(center_coordinates_source['x'], center_coordinates_source['y'])
    await page.mouse.down()
    await page.wait_for_timeout(1000)
    await page.mouse.move(center_coordinates_dest['x'], center_coordinates_dest['y'], steps=30)
    await page.wait_for_timeout(1000)
    await page.mouse.up()

async def enable_addon(page, addon_name, transition_timeout=10000):
    await page.locator('//a[text() = "アドオン"]').click()
    await expect(page.locator('//h3[text() = "アドオンを選択"]')).to_be_visible(timeout=transition_timeout)
    enable_locator = page.locator(f'//div[@full_name = "{addon_name}"]//a[text() = "有効にする"]')
    if await enable_locator.count():
        await enable_locator.click()
        confirm_button = page.locator('//button[@data-bb-handler = "confirm"]')
        await expect(confirm_button).to_be_visible(timeout=transition_timeout)
        await confirm_button.click()
    else:
        print('Addon already enabled')

async def _expect_empty_or_not(locator, expected):
    if expected == 'nonempty':
        await expect(locator).not_to_be_empty()
    elif expected == 'empty':
        await expect(locator).to_be_empty()
    else:
        raise ValueError(f'expected must be "empty" or "nonempty", got {expected!r}')

async def verify_property_file_info(
    page, filesize, filepath, *,
    expected_createtime, expected_updatetime, expected_updateby,
):
    locator_size = page.locator('//*[@id = "tb-tbody"]//*[@class = "modal-content"]//*[text() = "サイズ: "]/following-sibling::span')
    locator_createtime = page.locator('//*[@id = "tb-tbody"]//*[@class = "modal-content"]//*[text() = "作成日時: "]/following-sibling::span')
    locator_updatetime = page.locator('//*[@id = "tb-tbody"]//*[@class = "modal-content"]//*[text() = "更新日時: "]/following-sibling::span')
    locator_updateby = page.locator('//*[@id = "tb-tbody"]//*[@class = "modal-content"]//*[text() = "最終更新者: "]/following-sibling::span')
    locator_path = page.locator('//*[@id = "tb-tbody"]//*[@class = "modal-content"]//*[text() = "パス: "]/following-sibling::span')

    await locator_size.scroll_into_view_if_needed()
    await expect(locator_size).to_have_text(filesize)
    time.sleep(1)

    await locator_createtime.scroll_into_view_if_needed()
    await _expect_empty_or_not(locator_createtime, expected_createtime)
    await locator_updatetime.scroll_into_view_if_needed()
    await _expect_empty_or_not(locator_updatetime, expected_updatetime)
    await locator_updateby.scroll_into_view_if_needed()
    await _expect_empty_or_not(locator_updateby, expected_updateby)

    await locator_path.scroll_into_view_if_needed()
    await expect(locator_path).to_have_text(filepath)

    time.sleep(1)

async def verify_property_folder_info(
    page, filenumber, foldersize, folderpath, *,
    expected_createtime, expected_updatetime, expected_updateby,
):
    await expect(page.locator('//*[@id = "tb-tbody"]//*[@class = "modal-content"]//*[text() = "読み込み中..."]')).not_to_be_visible(timeout=60000)
    time.sleep(2)

    locator_filenumber = page.locator('//*[@id = "tb-tbody"]//*[@class = "modal-content"]//*[text() = "合計ファイル数: "]/following-sibling::span')
    locator_size = page.locator('//*[@id = "tb-tbody"]//*[@class = "modal-content"]//*[text() = "合計サイズ: "]/following-sibling::span')
    locator_createtime = page.locator('//*[@id = "tb-tbody"]//*[@class = "modal-content"]//*[text() = "作成日時: "]/following-sibling::span')
    locator_updatetime = page.locator('//*[@id = "tb-tbody"]//*[@class = "modal-content"]//*[text() = "更新日時: "]/following-sibling::span')
    locator_updateby = page.locator('//*[@id = "tb-tbody"]//*[@class = "modal-content"]//*[text() = "最終更新者: "]/following-sibling::span')
    locator_path = page.locator('//*[@id = "tb-tbody"]//*[@class = "modal-content"]//*[text() = "パス: "]/following-sibling::span')

    await locator_filenumber.scroll_into_view_if_needed()
    await expect(locator_filenumber).to_have_text(filenumber)
    await locator_size.scroll_into_view_if_needed()
    await expect(locator_size).to_have_text(foldersize)
    time.sleep(1)

    await locator_createtime.scroll_into_view_if_needed()
    await _expect_empty_or_not(locator_createtime, expected_createtime)
    await locator_updatetime.scroll_into_view_if_needed()
    await _expect_empty_or_not(locator_updatetime, expected_updatetime)
    await locator_updateby.scroll_into_view_if_needed()
    await _expect_empty_or_not(locator_updateby, expected_updateby)

    await locator_path.scroll_into_view_if_needed()
    await expect(locator_path).to_have_text(folderpath)

    time.sleep(1)
    
async def open_wiki(page, wikiname, text, transition_timeout=60000):
    await page.locator(f'//*[contains(@class, "title-text")]//a[text()="{wikiname}"]').click()
    await expect(page.locator('//span[contains(@class, "title-text")]//b[contains(text(), "プロジェクトのWiki")]')).to_be_visible(timeout=transition_timeout)
    await expect(page.locator('#pageName')).to_be_visible(timeout=transition_timeout)
    await expect(page.locator('#pageName')).to_have_text(wikiname, timeout=transition_timeout)
    await expect(page.locator('#wikiViewRender')).to_contain_text(text, timeout=transition_timeout)

async def open_edit_wiki(page, transition_timeout=60000):
    await page.locator('//div[@id="editWysiwyg"]//span[normalize-space()="編集"]').click()
    await expect(page.locator('#mMenuBar')).to_be_visible(timeout=transition_timeout)
    await expect(page.locator('#mEditor .ProseMirror[contenteditable="true"]')).to_be_visible(timeout=transition_timeout)

async def select_text_range(page, text, transition_timeout=60000):
    editor_locator = page.locator('#mEditor .ProseMirror[contenteditable="true"]')
    await editor_locator.focus()
    await editor_locator.evaluate("""
    (el, targetText) => {
        const p = Array.from(el.querySelectorAll('p')).find(par => par.innerText === targetText);
        if (!p) return;
        let textNode = p.firstChild;
        if (textNode.nodeType !== Node.TEXT_NODE) {
            textNode = textNode.firstChild;
        }
        const range = document.createRange();
        range.setStart(textNode, 0);
        range.setEnd(textNode, textNode.length);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
    }
    """, text)

async def fill_text(page, text, transition_timeout=60000):
    editor_locator = page.locator('#mEditor .ProseMirror[contenteditable="true"]')
    await editor_locator.click()
    await editor_locator.press("Enter")
    await editor_locator.fill(text)
    await expect(editor_locator).to_have_text(text, timeout=transition_timeout)

async def click_wiki_menu_save(page, menu_list, transition_timeout=60000):
    for menu in menu_list:
        locator_by_id = page.locator(f'#{menu}')
        if await locator_by_id.count() > 0:
            await locator_by_id.click()
            continue

        locator_by_text = page.locator(f'#mMenuBar span:has-text("{menu}")')
        if await locator_by_text.count() > 0:
            await locator_by_text.click()
            if menu == 'format_color_text':
                await set_text_color(page.locator('.m-menu-color-input'), 255, 0, 0)  # R=255, G=0, B=0
            if menu == 'table':
                await fill_all_cells(page)
            continue

        raise ValueError(f"Menu item '{menu}' not found in wiki menu bar.")

    await page.locator('//input[@type="submit" and @value="保存"]').click()
    await expect(page.locator('//span[contains(@class, "title-text")]//b[contains(text(), "プロジェクトのWiki")]')).to_be_visible(timeout=transition_timeout)

async def set_text_color(color_input, r, g, b):
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    
    # Convert RGB to HEX
    hex_color = f"#{r:02x}{g:02x}{b:02x}"
    # Fill value to input color
    await color_input.fill(hex_color)

async def fill_all_cells(page):
    rows = await page.locator("table tbody tr").count()
    for row_idx in range(rows):
        row = page.locator("table tbody tr").nth(row_idx)
        cells_count = await row.locator("th, td").count()
        
        for col_idx in range(cells_count):
            text = f"row{row_idx}col{col_idx}"
            cell = row.locator("th, td").nth(col_idx)

            await cell.evaluate("""
                (cell, text) => {
                    let p = cell.querySelector('p');
                    if (!p) {
                        p = document.createElement('p');
                        cell.appendChild(p);
                    }
                    p.innerHTML = text;
                }
            """, text)

async def click_table_menu_save(page, row_index, col_index, table_menu, transition_timeout=60000):
    table = page.locator('#mEditor .ProseMirror .tableWrapper table').first
    first_cell = table.locator("tr").first.locator("th, td").first
    await first_cell.click(force=True)
    if table_menu == 'セルを削除':
        last_cell = table.locator("tr").first.locator("th, td").last
        await last_cell.click(modifiers=["Shift"])
    for _ in range(row_index):
        await page.keyboard.press("ArrowDown")
    for _ in range(col_index):
        if table_menu == 'セルを削除':
            await page.keyboard.press("Shift+ArrowRight")
        else:
            await page.keyboard.press("ArrowRight")

    await page.locator("#arrowDropDown").click()
    await page.locator(f'.table-dropdown-item:has-text("{table_menu}")').click()
    await page.locator('//input[@type="submit" and @value="保存"]').click()

    view_locator = page.locator('#mView .ProseMirror[contenteditable="false"]')
    await expect(page.locator('//span[contains(@class, "title-text")]//b[contains(text(), "プロジェクトのWiki")]')).to_be_visible(timeout=transition_timeout)

async def click_and_expect_alert(page, action, expected_message, transition_timeout=60000):
    async with page.expect_event("dialog", timeout=transition_timeout*5) as dialog_info:
        await action()
    dialog = await dialog_info.value
    print(dialog.message)
    print(expected_message)
    assert dialog.message == expected_message
    await dialog.accept()
    await expect(page.locator('//*[contains(@class, "title-text")]//*[text() = "プロジェクトのWiki"]')).to_be_visible(timeout=transition_timeout)


async def go_to_file_detail(page, filename_move, work_dir):
    transition_timeout = 60000
    await get_select_file_title_locator(page, filename_move).click(timeout=transition_timeout)
    await expect(page.get_by_text(re.compile(r"^タイムスタンプ検証中"))).not_to_be_visible(timeout=transition_timeout * 5)
    time.sleep(2)

    # タイムスタンプエラーが発生した場合は、画面の証跡を記録した上で、「タイムスタンプを打つ」を押して、タイムスタンプエラーが解消するか確認すること
    locator_timestamperror = page.get_by_text(re.compile(r"^タイムスタンプの検証"))
    if await locator_timestamperror.is_visible():
        print('timestamp error')
        await page.locator(f'//a[contains(text(), "タイムスタンプを打つ")]').click(timeout=transition_timeout * 5)
        await expect(page.get_by_text(re.compile(r"^タイムスタンプ検証中"))).not_to_be_visible(timeout=transition_timeout * 5)
        await expect(page.get_by_text(re.compile(r"^タイムスタンプの検証"))).not_to_be_visible(timeout=transition_timeout * 5)

    # 200 KiB より大きいファイルは詳細情報の表示はできない
    filepath = os.path.join(work_dir, filename_move)
    filesize = os.path.getsize(filepath)
    large_filesize = 204800 # (200 * 1024)
    if filesize > large_filesize:
        print('file size > 200kB')
        text = 'Text files larger than 200 KiB are not rendered. Please download the file to view.'
        frame = page.frame_locator("iframe[src*='/render']")
        alert_locator = frame.locator('//div[contains(@class, "alert-warning")]')
        await alert_locator.wait_for(state="visible", timeout=transition_timeout * 5)
        await expect(alert_locator).to_have_text(text, timeout=transition_timeout * 5)

async def back_to_file_list_screen(page, provider, target_file_view):
    transition_timeout = 60000
    if target_file_view != 'file-tab':
        await page.locator("a.project-title").click()
    else:
        await page.locator('#projectNavFiles a').click()
    time.sleep(1)
    await expect(page.locator('//a[text() = "アドオン"]')).to_be_visible(timeout=transition_timeout)
    await expect(get_select_expanded_storage_title_locator(page, provider)).to_be_visible(timeout=transition_timeout)

async def move_file_to_storage(page, provider, filename_move):
    transition_timeout = 60000
    await expect(get_select_file_title_locator(page, filename_move)).to_be_visible(timeout=transition_timeout * 2)
    await get_select_file_extension_locator(page, filename_move).click()
    source = get_select_file_draggable_locator(page, filename_move)
    dest = get_select_storage_title_locator(page, provider)

    await drag_and_drop(page, source, dest)
    await expect(page.get_by_text(re.compile(r"^移動中"))).not_to_be_visible(timeout=transition_timeout * 5)
    time.sleep(10)
    await page.reload()
    
    await expect(get_select_file_title_locator(page, filename_move)).to_be_visible(timeout=transition_timeout * 5)

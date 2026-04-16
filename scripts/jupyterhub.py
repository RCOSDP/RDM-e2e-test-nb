from playwright.async_api import expect

async def login(page, username, password, transition_timeout=30000):
    # Login to JupyterHub
    jupyterhub_signin_button = page.locator('//*[@id = "login_submit"]')
    await expect(jupyterhub_signin_button).to_be_visible(timeout=transition_timeout)
    await page.locator('//*[@id = "username_input"]').fill(username)
    await page.locator('//*[@id = "password_input"]').fill(password)
    await jupyterhub_signin_button.click()

async def authorize(page, transition_timeout=30000):
    # JupyterHub authorizes a service (e.g. BinderHub addon of RDM OSF Integration)
    authorize_button = page.locator('//*[@value = "Authorize"]')
    await expect(authorize_button).to_be_visible(timeout=transition_timeout)
    await authorize_button.click()

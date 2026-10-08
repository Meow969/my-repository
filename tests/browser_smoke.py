"""Optional UI integration smoke test; requires playwright + Chrome (not CI unit suite)."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
URL=os.environ.get('RADAR_TEST_URL','http://127.0.0.1:8788/')
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,executable_path=os.environ.get('CHROME_PATH','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'))
    for width,height,label in [(1440,1000,'desktop'),(390,844,'mobile')]:
        context=browser.new_context(viewport={'width':width,'height':height},device_scale_factor=1)
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(URL,wait_until='networkidle');page.locator('.article-card').first.wait_for()
        assert page.locator('#feedTab').is_visible()
        assert not page.locator('#sourcesTab').is_visible()
        assert page.locator('.source-card').count()==28
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),label
        page.screenshot(path=f'/tmp/radar-{label}-home.png',full_page=False)
        page.locator('.brief-item').first.click()
        assert page.locator('[data-month="all"]').get_attribute('aria-pressed')=='true'
        page.locator('#qualityFilter').select_option('精选')
        assert page.locator('.article-card').count()>0
        assert page.locator('.article-card .evidence-badge:not(.verified)').count()==0
        page.locator('#sortFilter').select_option('quality')
        page.locator('.bookmark-btn').first.click()
        page.locator('#savedFilter').click()
        assert page.locator('.article-card').count()==1
        page.reload(wait_until='networkidle')
        page.locator('#savedFilter').click()
        assert page.locator('.article-card').count()<=1 # bookmark may be older than default 30 days
        page.locator('#savedFilter').click()
        page.locator('#searchInput').fill('zxunmatched999')
        assert page.locator('#articleGroups .empty').is_visible()
        page.locator('#resetFilters').click()
        page.locator('#searchInput').fill('Stripe')
        assert page.locator('.article-card').count()>0
        page.locator('#searchInput').fill('')
        page.locator('[data-tab="inspiration"]').click()
        assert page.locator('#inspirationTab').is_visible()
        assert page.locator('.insight-evidence').count()>0
        page.locator('#legacyToggle').click()
        assert page.locator('.insight-card').count()>10
        page.locator('#legacyToggle').click()
        with page.expect_download() as download:
            page.locator('#exportNotes').click()
        assert download.value.suggested_filename.endswith('.json')
        page.locator('[data-tab="sources"]').click()
        assert page.locator('#sourcesTab').is_visible()
        assert not page.locator('.global-toolbar').is_visible()
        page.screenshot(path=f'/tmp/radar-{label}-sources.png',full_page=False)
        page.locator('#floatingNoteBtn').click()
        assert page.locator('#notePanel').get_attribute('aria-hidden')=='false'
        page.keyboard.press('Escape')
        assert page.locator('#notePanel').get_attribute('aria-hidden')=='true'
        page.locator('[data-tab="feed"]').click()
        page.locator('.article-card').first.scroll_into_view_if_needed()
        page.locator('.analysis-details summary').first.click()
        page.screenshot(path=f'/tmp/radar-{label}-card.png',full_page=False)
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),label
        assert not errors,errors
        print(label,'PASS: navigation, search, filters, bookmarks, legacy, notes, export, overflow, console')
        context.close()
    browser.close()

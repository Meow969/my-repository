"""UI integration smoke: monthly summary → recommendations → daily timeline."""
import os
from playwright.sync_api import sync_playwright
URL=os.environ.get('RADAR_TEST_URL','http://127.0.0.1:8788/')
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,executable_path=os.environ.get('CHROME_PATH','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'))
    for width,height,label in [(1440,1000,'desktop'),(390,844,'mobile')]:
        context=browser.new_context(viewport={'width':width,'height':height},device_scale_factor=1)
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(URL,wait_until='networkidle');page.locator('.article-card').first.wait_for()
        assert page.locator('.top-tab').count()==2
        assert page.locator('[data-tab="feed"]').inner_text().startswith('有事没事来看看')
        assert page.locator('#feedTab').is_visible()
        for absent in ['#sourcesTab','#dailyBrief','#researchMetrics','.research-intro','[data-month="recent"]','[data-month="all"]']:
            assert page.locator(absent).count()==0,absent
        months=page.locator('.month-tab').evaluate_all('(els)=>els.map(e=>e.dataset.month)')
        assert months==sorted(months,reverse=True)
        assert page.locator('.month-tab.active').get_attribute('data-month')==months[0]
        assert page.locator('.monthly-summary').is_visible()
        assert 1<=page.locator('.monthly-links a').count()<=5
        first_monthly_links=page.locator('.monthly-links a').evaluate_all('(els)=>els.map(e=>e.href)')
        assert all(url.startswith('https://') for url in first_monthly_links)
        def check_days(month):
            dates=page.locator('.day-group').evaluate_all('(els)=>els.map(e=>e.dataset.date)')
            assert dates==sorted(dates,reverse=True)
            assert all(date.startswith(month) for date in dates)
            assert page.locator('#monthTabs').bounding_box()['y']<page.locator('#activeMonthlyReport').bounding_box()['y']<page.locator('#articleGroups').bounding_box()['y']
        check_days(months[0])
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),label
        page.screenshot(path=f'/tmp/radar-timeline-{label}-home.png',full_page=False)
        page.locator('.month-tab').nth(1).click()
        check_days(months[1])
        assert page.locator('.monthly-links a').evaluate_all('(els)=>els.map(e=>e.href)')!=first_monthly_links
        assert page.locator('.monthly-summary').is_visible()
        page.locator('.month-tab').last.click()
        check_days(months[-1])
        assert page.locator('.monthly-summary').is_visible()
        page.locator('.month-tab').first.click()
        page.locator('.filter-menu summary').click()
        page.locator('#qualityFilter').select_option('精选')
        page.locator('.filter-menu summary').click()
        assert page.locator('.article-card').count()>0
        assert page.locator('.article-card .evidence-badge:not(.verified)').count()==0
        page.locator('.bookmark-btn').first.click()
        page.locator('#savedFilter').click()
        assert page.locator('.article-card').count()==1
        assert page.locator('.monthly-card').count()==0
        page.reload(wait_until='networkidle')
        page.locator('#savedFilter').click()
        assert page.locator('.article-card').count()==1
        page.locator('#savedFilter').click()
        page.locator('#searchInput').fill('zxunmatched999')
        assert page.locator('#articleGroups .empty').is_visible()
        assert page.locator('.monthly-card').count()==0
        page.locator('#resetFilters').click()
        assert page.locator('.monthly-summary').is_visible()
        page.locator('#searchInput').fill('Stripe')
        assert page.locator('.article-card').count()>0
        assert page.locator('#filterContext').inner_text().startswith('全站搜索')
        page.locator('#searchInput').fill('')
        page.locator('[data-tab="inspiration"]').click()
        assert page.locator('#inspirationTab').is_visible()
        assert page.locator('.insight-evidence').count()>0
        page.locator('#legacyToggle').click()
        assert page.locator('.insight-card').count()>10
        page.locator('#legacyToggle').click()
        with page.expect_download() as download:page.locator('#exportNotes').click()
        assert download.value.suggested_filename.endswith('.json')
        page.locator('#floatingNoteBtn').click()
        assert page.locator('#notePanel').get_attribute('aria-hidden')=='false'
        page.keyboard.press('Escape')
        assert page.locator('#notePanel').get_attribute('aria-hidden')=='true'
        page.locator('[data-tab="feed"]').click()
        page.locator('.article-card').first.scroll_into_view_if_needed()
        page.locator('.analysis-details summary').first.click()
        page.screenshot(path=f'/tmp/radar-timeline-{label}-card.png',full_page=False)
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),label
        assert not errors,errors
        print(label,'PASS: two tabs, monthly summaries & recommendations, daily timeline, search, quality, bookmarks, notes, export, no overflow or errors')
        context.close()
    browser.close()

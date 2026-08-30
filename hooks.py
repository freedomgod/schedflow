"""Fix the language-switcher links on the two homepage pages.

mkdocs-static-i18n computes page-relative switcher links for every page
except the homepage variants (the Chinese root page and the English root
page), where it keeps links derived from ``site_url`` (e.g.
``/zh-cn/latest/en/``). Those absolute paths only work on the deployed
Read the Docs site, not under ``mkdocs serve``.

This hook rewrites those two pages' rendered HTML so the switcher links are
relative (``./`` and ``en/``, or ``../`` and ``./`` for the English
homepage), which resolve correctly both locally and under any Read the Docs
language prefix.
"""

from urllib.parse import urlsplit


def on_post_page(output, page, config):
    url = page.url or ""
    is_zh_home = url in ("", ".", "index.html")
    is_en_home = url in ("en/", "en/index.html")
    if not (is_zh_home or is_en_home):
        return output

    base = urlsplit(config.site_url or "").path.rstrip("/")
    zh_href = f'href="{base}/"'
    en_href = f'href="{base}/en/"'
    if is_zh_home:
        output = output.replace(zh_href, 'href="./"').replace(en_href, 'href="en/"')
    else:
        output = output.replace(zh_href, 'href="../"').replace(en_href, 'href="./"')
    return output

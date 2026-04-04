"""
crawler.py — Tech0 Search v1.0
URLからWebページを取得し、タイトル・説明文・本文などを抽出する。
"""

import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup


def fetch_page(url: str, timeout: int = 10) -> Optional[str]:
    """
    指定URLのHTMLを取得する。
    """
    try:
        headers = {"User-Agent": "Tech0SearchBot/1.0 (Educational Purpose)"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        return resp.text

    except requests.RequestException as e:
        print(f"取得エラー: {e}")
        return None


def normalize_url(url: str) -> str:
    """
    URLの断片(#...)を除去し、末尾スラッシュなどを軽く正規化する。
    """
    url, _ = urldefrag(url)
    return url.strip()


def parse_html(html: str, url: str) -> dict:
    """
    HTMLを解析してページ情報を抽出する。
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    title = "No Title"
    if soup.find("title"):
        title = soup.find("title").get_text().strip()
    elif soup.find("h1"):
        title = soup.find("h1").get_text().strip()

    description = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        description = meta["content"][:200]

    keywords = []
    meta_kw = soup.find("meta", attrs={"name": "keywords"})
    if meta_kw and meta_kw.get("content"):
        keywords = [kw.strip() for kw in meta_kw["content"].split(",")][:10]

    elems = soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td"])
    full_text = " ".join(e.get_text().strip() for e in elems)
    full_text = re.sub(r"\s+", " ", full_text).strip()

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        absolute_url = urljoin(url, href)
        absolute_url = normalize_url(absolute_url)
        if absolute_url.startswith("http"):
            links.append(absolute_url)

    links = list(dict.fromkeys(links))[:50]

    return {
        "url": url,
        "title": title,
        "description": description,
        "keywords": keywords,
        "full_text": full_text,
        "links": links,
        "word_count": len(full_text.split()),
        "crawled_at": datetime.now().isoformat(),
        "crawl_status": "success",
    }


def crawl_url(url: str) -> dict:
    """
    URLをクロールしてページ情報を返す。
    """
    html = fetch_page(url)
    if not html:
        return {
            "url": url,
            "crawl_status": "failed",
            "crawled_at": datetime.now().isoformat(),
            "error": "Failed to fetch page",
        }

    try:
        return parse_html(html, url)
    except Exception as e:
        return {
            "url": url,
            "crawl_status": "error",
            "crawled_at": datetime.now().isoformat(),
            "error": str(e),
        }


def extract_links_from_index(index_url: str, keyword: str = "", limit: int = 200) -> dict:
    """
    一覧ページからリンク先URLを抽出する。
    MVPでは seminar / book の詳細ページを主対象にする。
    """
    html = fetch_page(index_url)
    if not html:
        return {
            "index_url": index_url,
            "extract_status": "failed",
            "extracted_urls": [],
            "error": "Failed to fetch index page",
        }

    try:
        soup = BeautifulSoup(html, "html.parser")
        base_domain = urlparse(index_url).netloc

        collected = []

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            absolute_url = urljoin(index_url, href)
            absolute_url = normalize_url(absolute_url)

            if not absolute_url.startswith("http"):
                continue

            parsed = urlparse(absolute_url)

            # 同一ドメインだけ対象
            if parsed.netloc != base_domain:
                continue

            # 一覧ページ自身は除外
            if absolute_url == normalize_url(index_url):
                continue

            lower_url = absolute_url.lower()

            # 不要ページ除外
            if any(x in lower_url for x in [
                "/user/",
                "/password/",
                "/home",
                "/pages/",
                "/items/",
                "/search/",
                "/faq",
                "/advertising",
                "/entry",
            ]):
                continue

            # 静的ファイル除外
            if re.search(r"\.(pdf|jpg|jpeg|png|gif|zip)$", absolute_url, re.IGNORECASE):
                continue

            # seminar詳細 または book詳細だけ通す
            if not ("/seminar/" in lower_url or "/book/" in lower_url):
                continue

            collected.append(absolute_url)

        unique_urls = list(dict.fromkeys(collected))
        truncated = len(unique_urls) > limit
        limited_urls = unique_urls[:limit]

        return {
            "index_url": index_url,
            "extract_status": "success",
            "extracted_urls": limited_urls,
            "count": len(limited_urls),
            "total_found": len(unique_urls),
            "truncated": truncated,
        }

    except Exception as e:
        return {
            "index_url": index_url,
            "extract_status": "error",
            "extracted_urls": [],
            "error": str(e),
        }
"""
app.py — Tech0 Search v1.0
Streamlit アプリ本体
・検索
・クローラー
・一覧
・生成AIによる要約
・生成AIによる新規事業提案
"""

import os
import re
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

from database import init_db, get_all_pages, insert_page, log_search
from ranking import get_engine, rebuild_index
from crawler import crawl_url, extract_links_from_index # 追加0404
from ai_client import generate_ai_summary


# ── 初期設定 ─────────────────────────────────────────────
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

init_db()

st.set_page_config(
    page_title="TechZeron Future Design",
    page_icon="🚀",
    layout="wide"
)


# ── キャッシュ付きインデックス構築 ─────────────────────
@st.cache_resource
def load_and_index():
    pages = get_all_pages()
    if pages:
        rebuild_index(pages)
    return pages


def parse_date_safe(date_str: str):
    """
    '2025-04-01T12:00:00' や '2025-04-01' を date に変換
    """
    if not date_str:
        return None

    text = str(date_str)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


pages = load_and_index()
engine = get_engine()


# ── session_state 初期化 ───────────────────────────────
if "search_executed" not in st.session_state:
    st.session_state.search_executed = False

if "search_results" not in st.session_state:
    st.session_state.search_results = []

if "last_query" not in st.session_state:
    st.session_state.last_query = ""

if "last_top_n" not in st.session_state:
    st.session_state.last_top_n = 10

if "summary_states" not in st.session_state:
    st.session_state.summary_states = {}

if "business_states" not in st.session_state:
    st.session_state.business_states = {}

if "global_summary" not in st.session_state:
    st.session_state.global_summary = ""

if "global_business" not in st.session_state:
    st.session_state.global_business = ""

# 追加0404
if "extracted_urls" not in st.session_state:
    st.session_state.extracted_urls = []

if "extracted_category" not in st.session_state:
    st.session_state.extracted_category = ""

if "crawl_success" not in st.session_state:
    st.session_state.crawl_success = False

if "bulk_crawl_success" not in st.session_state:
    st.session_state.bulk_crawl_success = False

if "bulk_crawl_success_count" not in st.session_state:
    st.session_state.bulk_crawl_success_count = 0

if "index_url_input" not in st.session_state:
    st.session_state["index_url_input"] = ""

if "category_name_input" not in st.session_state:
    st.session_state["category_name_input"] = ""
# 追加0404 ここまで

# ── サイドバー ─────────────────────────────────────────
with st.sidebar:
    st.header("DB の状態")
    st.metric("登録ページ数", f"{len(pages)} 件")

    if api_key:
        st.success("OpenAI APIキー読み込みOK")
    else:
        st.error("APIキー未設定")

    if st.button("🔄 インデックスを更新"):
        st.cache_resource.clear()
        st.rerun()


# ── ヘッダー ───────────────────────────────────────────
st.title("🚀 TechZeron Future Design")
st.caption("社内ナレッジと外部トレンドを融合し、意思決定を高速化する「社内知見活用アシスタント」")


# ── タブ ───────────────────────────────────────────────
tab_search, tab_crawl, tab_list = st.tabs(
    ["🔍 検索", "🤖 クローラー", "📋 一覧"]
)


# ── 検索タブ ───────────────────────────────────────────
with tab_search:
    st.subheader("キーワードで検索")

    col1, col2 = st.columns([3, 1])

    with col1:
        query = st.text_input(
            "検索キーワード",
            value=st.session_state.last_query,
            placeholder="例：DX、製造業、半導体、品質改善"
        )

    with col2:
        top_n = st.selectbox(
            "表示件数",
            [10, 20, 50],
            index=[10, 20, 50].index(st.session_state.last_top_n)
            if st.session_state.last_top_n in [10, 20, 50] else 0
        )

    # 追加条件：登録時期
    st.markdown("#### 登録時期で絞り込み")
    date_col1, date_col2 = st.columns(2)

    with date_col1:
        start_date = st.date_input("開始日", value=None)

    with date_col2:
        end_date = st.date_input("終了日", value=None)

    # 検索・リセットボタン
    btn_col1, btn_col2 = st.columns(2)

    with btn_col1:
        search_clicked = st.button("検索", use_container_width=True)

    with btn_col2:
        reset_clicked = st.button("リセット", use_container_width=True)

    # リセット処理
    if reset_clicked:
        st.session_state.search_executed = False
        st.session_state.search_results = []
        st.session_state.last_query = ""
        st.session_state.last_top_n = 10
        st.session_state.summary_states = {}
        st.session_state.business_states = {}
        st.session_state.global_summary = ""
        st.session_state.global_business = ""
        st.rerun()

    # 検索実行
    if search_clicked:
        st.session_state.last_query = query
        st.session_state.last_top_n = top_n
        st.session_state.search_executed = True
        st.session_state.summary_states = {}
        st.session_state.business_states = {}
        st.session_state.global_summary = ""
        st.session_state.global_business = ""

        raw_results = engine.search(query, top_n=top_n) if query.strip() else []

        # 登録時期で絞り込み
        filtered_results = []
        for page in raw_results:
            crawled_date = parse_date_safe(page.get("crawled_at", ""))

            if start_date and crawled_date and crawled_date < start_date:
                continue
            if end_date and crawled_date and crawled_date > end_date:
                continue

            # 日付がないデータは期間指定時は除外
            if (start_date or end_date) and crawled_date is None:
                continue

            filtered_results.append(page)

        st.session_state.search_results = filtered_results
        log_search(query, len(filtered_results))

    # 検索結果表示
    if st.session_state.search_executed:
        results = st.session_state.search_results

        st.markdown(f"**検索結果：{len(results)} 件（TF-IDF順）**")
        st.divider()

        if results:
            # 先に検索結果一覧を出す
            for i, page in enumerate(results, 1):
                page_id = page.get("id", i)
                summary_key = f"summary_{page_id}"
                business_key = f"business_{page_id}"

                with st.container():
                    col_rank, col_title, col_score = st.columns([1, 6, 2])

                    with col_rank:
                        medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else str(i)
                        st.markdown(f"### {medal}")

                    with col_title:
                        st.markdown(f"### {page['title']}")

                    with col_score:
                        st.metric("スコア", f"{page['relevance_score']}")

                    desc = page.get("description", "")
                    if desc:
                        st.caption(desc[:200] + ("..." if len(desc) > 200 else ""))

                    meta_col1, meta_col2, meta_col3 = st.columns(3)
                    with meta_col1:
                        st.caption(f"👤 {page.get('author', '不明') or '不明'}")
                    with meta_col2:
                        st.caption(f"📁 {page.get('category', '未分類') or '未分類'}")
                    with meta_col3:
                        crawled_at = (page.get("crawled_at", "") or "")[:10]
                        st.caption(f"📅 {crawled_at}")

                    st.markdown(f"[🔗 ページを見る]({page['url']})")

                    # 各検索結果ごとのAIボタン
                    ai_btn_col1, ai_btn_col2 = st.columns(2)

                    with ai_btn_col1:
                        if st.button("🤖 この結果を要約", key=f"btn_summary_{page_id}"):
                            with st.spinner("要約を生成しています..."):
                                one_summary = generate_ai_summary(
                                    page.get("title", ""),
                                    [page],
                                    mode="summary"
                                )
                            st.session_state.summary_states[summary_key] = one_summary

                    # 要約が出た後だけ、新規事業提案ボタンを表示
                    if summary_key in st.session_state.summary_states:
                        with ai_btn_col2:
                            if st.button("💡 この結果から新規事業提案", key=f"btn_business_{page_id}"):
                                with st.spinner("新規事業案を生成しています..."):
                                    one_business = generate_ai_summary(
                                        page.get("title", ""),
                                        [page],
                                        mode="business"
                                    )
                                st.session_state.business_states[business_key] = one_business

                    # 要約結果表示
                    if summary_key in st.session_state.summary_states:
                        st.markdown("#### 生成AIによる要約")
                        st.write(st.session_state.summary_states[summary_key])

                    # 事業提案表示
                    if business_key in st.session_state.business_states:
                        st.markdown("#### 生成AIによる新規事業提案")
                        st.write(st.session_state.business_states[business_key])

                    st.divider()

            # 全体AIボタンは検索結果の下に配置
            st.markdown("### 検索結果全体に対するAI活用")

            global_col1, global_col2 = st.columns(2)

            with global_col1:
                if st.button("🤖 検索結果全体を要約"):
                    with st.spinner("検索結果全体を要約しています..."):
                        st.session_state.global_summary = generate_ai_summary(
                            st.session_state.last_query,
                            results,
                            mode="summary"
                        )
                    st.session_state.global_business = ""

            if st.session_state.global_summary:
                with global_col2:
                    if st.button("💡 検索結果全体から新規事業提案"):
                        with st.spinner("検索結果全体から新規事業案を生成しています..."):
                            st.session_state.global_business = generate_ai_summary(
                                st.session_state.last_query,
                                results,
                                mode="business"
                            )

            if st.session_state.global_summary:
                st.subheader("生成AIによる要約")
                st.write(st.session_state.global_summary)

            if st.session_state.global_business:
                st.subheader("生成AIによる新規事業提案")
                st.write(st.session_state.global_business)

        else:
            st.info("該当データが見つかりませんでした。")


# ── クローラータブ ─────────────────────────────────────
with tab_crawl:
    st.subheader("クローラー")
    st.caption("単体クロール・一括クロール・一覧URL抽出に対応")

    if st.session_state.get("crawl_success"):
        st.success("登録完了しました。")
        st.session_state["crawl_success"] = False

    if st.session_state.get("bulk_crawl_success"):
        count = st.session_state.get("bulk_crawl_success_count", 0)
        st.success(f"{count}件の登録が完了しました。")
        st.session_state["bulk_crawl_success"] = False

    # -----------------------------
    # 単体クロール
    # -----------------------------
    st.subheader("🌀 単体クロール")

    with st.form("single_crawl_form", clear_on_submit=True):
        crawl_url_input = st.text_input(
            "クロール対象URL",
            placeholder="https://example.com"
        )
        single_submitted = st.form_submit_button("クロール実行")

    if single_submitted:
        target_url = crawl_url_input.strip()

        if not target_url:
            st.warning("URLを入力してください。")
        else:
            with st.spinner("クロール中です..."):
                result = crawl_url(target_url)

            if result.get("crawl_status") == "success":
                insert_page(result)
                st.cache_resource.clear()
                st.session_state["crawl_success"] = True
                st.rerun()
            else:
                st.error(f"クロールに失敗しました: {result.get('error', 'Unknown error')}")

    st.divider()

    # -----------------------------
    # 一括クロール
    # -----------------------------
    st.subheader("🕸️ 一括クロール")

    with st.form("bulk_crawl_form", clear_on_submit=True):
        bulk_urls = st.text_area(
            "URLリスト（1行に1URL）",
            placeholder="https://example1.com\nhttps://example2.com",
            height=180
        )
        bulk_submitted = st.form_submit_button("一括クロール実行")

    if bulk_submitted:
        url_list = [u.strip() for u in bulk_urls.splitlines() if u.strip()]

        if not url_list:
            st.warning("URLを1件以上入力してください。")
        else:
            success_count = 0
            fail_urls = []

            with st.spinner("一括クロール中です..."):
                for url in url_list:
                    result = crawl_url(url)

                    if result.get("crawl_status") == "success":
                        insert_page(result)
                        success_count += 1
                    else:
                        fail_urls.append(url)

            st.cache_resource.clear()

            if success_count > 0:
                st.session_state["bulk_crawl_success"] = True
                st.session_state["bulk_crawl_success_count"] = success_count

            if fail_urls:
                st.warning("一部失敗したURLがあります。")
                st.code("\n".join(fail_urls))

            st.rerun()

    st.divider()

    # -----------------------------
    # 一覧URL抽出
    # -----------------------------
    st.subheader("🧭 一覧URL抽出")

    with st.form("index_extract_form", clear_on_submit=False):
        index_url = st.text_input(
            "インデックスページURL",
            placeholder="https://www.rdsc.co.jp/search/index?sch_tag_id=73",
            key="index_url_input"
        )
        category_name = st.text_input(
            "カテゴリ名",
            placeholder="例：半導体",
            key="category_name_input"
        )
        extract_submitted = st.form_submit_button("一覧からURL抽出")

    if extract_submitted:
        if not index_url.strip():
            st.warning("インデックスページURLを入力してください。")
        else:
            with st.spinner("一覧ページからURLを抽出しています..."):
                extract_result = extract_links_from_index(
                    index_url=index_url.strip(),
                    keyword=category_name.strip(),
                    limit=200
                )

            if extract_result.get("extract_status") == "success":
                st.session_state["extracted_urls"] = extract_result.get("extracted_urls", [])
                st.session_state["extracted_category"] = category_name.strip()

                total_found = extract_result.get("total_found", 0)
                count = extract_result.get("count", 0)
                truncated = extract_result.get("truncated", False)

                if truncated:
                    st.success(f"{total_found}件見つかりました。上限により先頭{count}件を抽出しました。")
                else:
                    st.success(f"{count}件のURLを抽出しました。")
            else:
                st.error(f"URL抽出に失敗しました: {extract_result.get('error', 'Unknown error')}")
#修正0404 ここまで
    extracted_urls = st.session_state.get("extracted_urls", [])

    if extracted_urls:
        st.markdown(f"**抽出URL一覧：{len(extracted_urls)}件**")
        st.code("\n".join(extracted_urls[:100]))

        if len(extracted_urls) > 100:
            st.caption("表示は先頭100件までです。")

        if st.button("抽出したURLを一括クロール"):
            success_count = 0
            fail_urls = []
            category_value = st.session_state.get("extracted_category", "").strip()

            with st.spinner("抽出済みURLを一括クロール中です..."):
                for url in extracted_urls:
                    result = crawl_url(url)

                    if result.get("crawl_status") == "success":
                        if category_value:
                            result["category"] = category_value
                        insert_page(result)
                        success_count += 1
                    else:
                        fail_urls.append(url)

            st.cache_resource.clear()

            if success_count > 0:
                st.session_state["bulk_crawl_success"] = True
                st.session_state["bulk_crawl_success_count"] = success_count

                # 抽出結果だけクリア
                st.session_state["extracted_urls"] = []
                st.session_state["extracted_category"] = ""
                st.session_state["extracted_page"] = 1

            if fail_urls:
                st.warning("一部失敗したURLがあります。")
                st.code("\n".join(fail_urls[:20]))
            
            st.session_state["extracted_urls"] = []
            st.session_state["extracted_category"] = ""

            st.rerun()


# ── 一覧タブ ───────────────────────────────────────────
with tab_list:
    st.subheader("登録データ一覧")

    if not pages:
        st.info("登録データがありません。")
    else:
        for page in pages:
            st.markdown(f"### {page['title']}")
            st.caption(page["url"])

            desc = page.get("description", "")
            if desc:
                st.write(desc)

            st.divider()
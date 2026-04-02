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
from crawler import crawl_url
from ai_client import generate_ai_summary


# ── 初期設定 ─────────────────────────────────────────────
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

init_db()

st.set_page_config(
    page_title="Tech0 Search v1.0",
    page_icon="🔍",
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
st.title("🔍 Tech0 Search v1.0")
st.caption("PROJECT ZERO — 社内ナレッジ検索エンジン【TF-IDFランキング搭載】")


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

    urls_input = st.text_area(
        "URL入力",
        placeholder="URLを改行またはスペース区切りで入力してください"
    )

    if st.button("実行"):
        urls = re.split(r"\s+", urls_input.strip())

        success_count = 0
        fail_count = 0

        for url in urls:
            if url.startswith("http"):
                data = crawl_url(url)

                if data and data.get("crawl_status") == "success":
                    insert_page(data)
                    success_count += 1
                else:
                    fail_count += 1

        st.success(f"登録完了：成功 {success_count} 件 / 失敗 {fail_count} 件")
        st.cache_resource.clear()
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
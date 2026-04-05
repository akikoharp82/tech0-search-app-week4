"""
ai_client.py — Tech0 Search v1.0

生成AIを使って
・検索結果の要約
・新規事業提案
を行うモジュール
"""

import os
import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

api_key = None

try:
    api_key = st.secrets["OPENAI_API_KEY"]
except Exception:
    api_key = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=api_key) if api_key else None


# ── メイン関数 ─────────────────────────────
def generate_ai_summary(query: str, search_results: list, mode: str = "summary") -> str:
    """
    AIで要約 or 新規事業提案を生成する

    Parameters:
        query           : 検索キーワード
        search_results  : 検索結果（list）
        mode            : "summary" or "business"
    """

    # ── ガード処理 ─────────────────────────
    if not search_results:
        return "検索結果がないため、生成できませんでした。"

    # ── コンテキスト生成 ───────────────────
    context_lines = []

    for i, page in enumerate(search_results[:5], start=1):
        context_lines.append(
            f"""
{i}.
タイトル: {page.get('title', '')}
説明: {page.get('description', '')}
本文: {page.get('full_text', '')[:300]}
URL: {page.get('url', '')}
"""
        )

    context_text = "\n".join(context_lines)

    # ── プロンプト分岐 ─────────────────────
    if mode == "summary":

        prompt = f"""
あなたは優秀なコンサルタントです。
以下の検索結果をもとに、日本語で要点を整理してください。

【検索キーワード】
{query}

【検索結果】
{context_text}

【出力形式】
① 要点（3つ）
② 重要な示唆
③ 次に取るべきアクション
"""

    elif mode == "business":

        prompt = f"""
あなたは半導体メーカーの新規事業責任者です。
以下の検索結果をもとに、新規事業を提案してください。

【検索キーワード】
{query}

【検索結果】
{context_text}

【出力形式】
① 技術トレンド
② 市場機会
③ 顧客課題
④ 新規事業アイデア（具体）
⑤ ビジネスモデル（収益構造）
⑥ 差別化ポイント
"""

    else:
        return "エラー：不正なモードです"

    # ── OpenAI 実行 ───────────────────────
    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=prompt,
        )

        return response.output_text

    except Exception as e:
        return f"AI生成中にエラーが発生しました: {str(e)}"
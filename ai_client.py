from openai import OpenAI

def generate_ai_summary(query: str, search_results: list, api_key: str) -> str:

    if not api_key:
        return "APIキーが設定されていません"

    if not search_results:
        return "検索結果がありません"

    client = OpenAI(api_key=api_key)

    context_lines = []

    for i, page in enumerate(search_results[:5], start=1):
        context_lines.append(
            f"{i}. タイトル: {page.get('title', '')}\n"
            f"   説明: {page.get('description', '')}\n"
            f"   本文: {page.get('full_text', '')[:200]}"
        )

    context_text = "\n\n".join(context_lines)

    prompt = f"""
あなたは半導体メーカーの新規事業企画担当です。

キーワード:
{query}

情報:
{context_text}

以下を出してください：

① 技術トレンド
② 市場機会
③ 新規事業案
④ 次のアクション
"""

    response = client.responses.create(
        model="gpt-4o-mini",
        input=prompt
    )

    return response.output_text
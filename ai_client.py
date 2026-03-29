from openai import OpenAI

client = OpenAI()

def generate_ai_summary(query: str, search_results: list) -> str:
    """
    検索結果をもとに、AIが要点・示唆・次アクションを返す
    """
    if not search_results:
        return "検索結果がないため、要約できませんでした。"

    context_lines = []

    for i, page in enumerate(search_results[:5], start=1):
        context_lines.append(
            f"{i}. タイトル: {page.get('title', '')}\n"
            f"   説明: {page.get('description', '')}\n"
            f"   URL: {page.get('url', '')}\n"
            f"   本文抜粋: {page.get('full_text', '')[:300]}"
        )

    context_text = "\n\n".join(context_lines)

    prompt = f"""
あなたは社内知見活用アシスタントです。
以下は、社内ナレッジ検索アプリで見つかった検索結果です。

検索キーワード:
{query}

検索結果:
{context_text}

以下の形式で日本語で整理してください。
1. 社内知見の要点
2. 重要な示唆
3. 外部のサイトから最新のトレンドを検索して、掛け合わせて新しい事業を考えてください。
4. 次に取るべきアクション
"""

    response = client.responses.create(
        model="gpt-5.4",
        input=prompt
    )

    return response.output_text
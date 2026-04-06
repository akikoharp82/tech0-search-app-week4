"""
ranking.py — Tech0 Search v2.0
日本語の部分一致に強い検索 + ランキング版
"""

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from typing import List
from datetime import datetime


class SearchEngine:
    """日本語向けの検索エンジン"""

    def __init__(self):
        # 日本語の複合語・部分一致に強い設定
        self.vectorizer = TfidfVectorizer(
            max_features=8000,
            analyzer="char",
            ngram_range=(2, 4),
            min_df=1,
            max_df=0.98,
            sublinear_tf=True
        )
        self.tfidf_matrix = None
        self.pages = []
        self.is_fitted = False

    def build_index(self, pages: list):
        """
        全ページのインデックスを構築する。
        """
        if not pages:
            self.pages = []
            self.tfidf_matrix = None
            self.is_fitted = False
            return

        self.pages = pages
        corpus = []

        for p in pages:
            kw = p.get("keywords", "") or ""
            if isinstance(kw, str):
                kw_list = [k.strip() for k in kw.split(",") if k.strip()]
            else:
                kw_list = [str(k).strip() for k in kw if str(k).strip()]

            title = p.get("title", "") or ""
            description = p.get("description", "") or ""
            full_text = p.get("full_text", "") or ""
            keywords_text = " ".join(kw_list)

            # タイトル・説明・キーワードに重みを持たせる
            weighted_text = " ".join([
                (title + " ") * 4,
                (description + " ") * 2,
                (keywords_text + " ") * 3,
                full_text
            ])
            corpus.append(weighted_text)

        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)
        self.is_fitted = True

    def search(self, query: str, top_n: int = 20) -> list:
        """
        検索を実行する。
        """
        if not self.is_fitted or not query.strip():
            return []

        query = query.strip()
        query_lower = query.lower()

        query_vec = self.vectorizer.transform([query])
        similarities = cosine_similarity(query_vec, self.tfidf_matrix)[0]

        results = []

        for idx, base_score in enumerate(similarities):
            page = self.pages[idx].copy()

            match_info = self._analyze_match(page, query_lower)

            # 候補抽出:
            # 1) どこかに直接部分一致していれば採用
            # 2) 直接一致がなくても類似度が少しあれば採用
            if match_info["any_direct_match"] or base_score >= 0.004:
                final_score = self._calculate_final_score(
                    page=page,
                    base_score=float(base_score),
                    match_info=match_info
                )

                page["relevance_score"] = round(final_score, 1)
                page["base_score"] = round(float(base_score) * 100, 2)
                page["match_type"] = self._get_match_type_label(match_info)

                results.append(page)

        results.sort(
            key=lambda x: (
                self._match_type_priority(x.get("match_type", "")),
                x["relevance_score"],
                x["base_score"]
            ),
            reverse=True
        )

        return results[:top_n]

    def _analyze_match(self, page: dict, query_lower: str) -> dict:
        """
        どこに一致したかを解析する。
        """
        title = (page.get("title", "") or "").lower()
        description = (page.get("description", "") or "").lower()
        full_text = (page.get("full_text", "") or "").lower()

        keywords = page.get("keywords", [])
        if isinstance(keywords, str):
            keywords_list = [k.strip().lower() for k in keywords.split(",") if k.strip()]
        else:
            keywords_list = [str(k).strip().lower() for k in keywords if str(k).strip()]

        title_exact = query_lower == title
        title_partial = query_lower in title if title else False

        keyword_exact = query_lower in keywords_list
        keyword_partial = any(query_lower in k for k in keywords_list) if keywords_list else False

        description_partial = query_lower in description if description else False
        full_text_partial = query_lower in full_text if full_text else False

        any_direct_match = any([
            title_exact,
            title_partial,
            keyword_exact,
            keyword_partial,
            description_partial,
            full_text_partial
        ])

        return {
            "title_exact": title_exact,
            "title_partial": title_partial,
            "keyword_exact": keyword_exact,
            "keyword_partial": keyword_partial,
            "description_partial": description_partial,
            "full_text_partial": full_text_partial,
            "any_direct_match": any_direct_match
        }

    def _calculate_final_score(self, page: dict, base_score: float, match_info: dict) -> float:
        """
        最終スコアを加点式で計算する。
        """
        # 類似度を土台にする
        score = base_score * 100

        # タイトル一致は最優先
        if match_info["title_exact"]:
            score += 120
        elif match_info["title_partial"]:
            score += 75

        # キーワード一致
        if match_info["keyword_exact"]:
            score += 45
        elif match_info["keyword_partial"]:
            score += 25

        # 説明文・本文一致
        if match_info["description_partial"]:
            score += 18
        if match_info["full_text_partial"]:
            score += 6

        # 直接一致がある候補を少し優遇
        if match_info["any_direct_match"]:
            score += 12

        # 新鮮度ボーナス
        crawled_at = page.get("crawled_at", "")
        if crawled_at:
            try:
                crawled = datetime.fromisoformat(crawled_at.replace("Z", "+00:00"))
                days_old = (datetime.now() - crawled.replace(tzinfo=None)).days
                if days_old <= 90:
                    score += 10 * (90 - days_old) / 90
            except Exception:
                pass

        # 文字数調整
        word_count = page.get("word_count", 0)
        if word_count < 50:
            score -= 12
        elif word_count < 150:
            score -= 5
        elif word_count > 15000:
            score -= 8
        elif word_count > 8000:
            score -= 3

        return max(score, 0.0)

    def _get_match_type_label(self, match_info: dict) -> str:
        if match_info["title_exact"]:
            return "title_exact"
        if match_info["title_partial"]:
            return "title_partial"
        if match_info["keyword_exact"]:
            return "keyword_exact"
        if match_info["keyword_partial"]:
            return "keyword_partial"
        if match_info["description_partial"]:
            return "description_partial"
        if match_info["full_text_partial"]:
            return "full_text_partial"
        return "semantic_only"

    def _match_type_priority(self, match_type: str) -> int:
        priority_map = {
            "title_exact": 7,
            "title_partial": 6,
            "keyword_exact": 5,
            "keyword_partial": 4,
            "description_partial": 3,
            "full_text_partial": 2,
            "semantic_only": 1,
        }
        return priority_map.get(match_type, 0)


_engine = None


def get_engine() -> SearchEngine:
    """検索エンジンのシングルトンを取得する"""
    global _engine
    if _engine is None:
        _engine = SearchEngine()
    return _engine


def rebuild_index(pages: List[dict]):
    """インデックスを再構築する"""
    engine = get_engine()
    engine.build_index(pages)
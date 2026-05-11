import time
import json
import logging
import re
from typing import Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .models import RawReview

logger = logging.getLogger(__name__)

REVIEW_API_URL = "https://www.zappos.com/api/3/review/product/{product_id}"

# Full browser-like headers — Zappos checks these
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


class ZapposScraper:
    def __init__(self, delay: float = 2.0):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._warmed_up = False

    def _warm_up(self) -> None:
        """Visit the homepage once to collect cookies before any API calls."""
        if self._warmed_up:
            return
        try:
            self.session.get("https://www.zappos.com/", timeout=15)
            self._warmed_up = True
            time.sleep(self.delay)
        except Exception as exc:
            logger.debug("Warm-up request failed (non-fatal): %s", exc)

    def _get(self, url: str, params: Optional[dict] = None, json_mode: bool = False) -> requests.Response:
        time.sleep(self.delay)
        headers = {}
        if json_mode:
            headers["Accept"] = "application/json, */*"
            headers["Referer"] = "https://www.zappos.com/"
            headers["X-Requested-With"] = "XMLHttpRequest"
        resp = self.session.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp

    def search_products(self, query: str, max_products: int = 5) -> list[dict]:
        """Return a list of {product_id, name, brand} dicts matching the query."""
        self._warm_up()
        products = self._search_products_html(query, max_products)
        if not products:
            # Last-resort: try the internal catalog API
            products = self._search_products_api(query, max_products)
        return products

    def _search_products_html(self, query: str, max_products: int) -> list[dict]:
        url = f"https://www.zappos.com/search?term={quote(query)}"
        try:
            resp = self._get(url)
            # Try __NEXT_DATA__ JSON blob first (Next.js SSR)
            soup = BeautifulSoup(resp.text, "html.parser")
            script_tag = soup.find("script", id="__NEXT_DATA__")
            if script_tag and script_tag.string:
                next_data = json.loads(script_tag.string)
                products = self._extract_products_from_next_data(next_data, max_products)
                if products:
                    return products

            # Fallback: parse product cards directly from HTML
            return self._extract_products_from_html(soup, max_products)
        except Exception as exc:
            logger.warning("HTML search failed: %s", exc)
            return []

    def _extract_products_from_next_data(self, next_data: dict, max_products: int) -> list[dict]:
        """Walk common __NEXT_DATA__ paths where Zappos stores search results."""
        candidates = [
            next_data.get("props", {}).get("pageProps", {}).get("searchResult", {}).get("results", []),
            next_data.get("props", {}).get("pageProps", {}).get("products", []),
            next_data.get("props", {}).get("initialState", {}).get("products", {}).get("list", []),
        ]
        for results in candidates:
            if results:
                products = []
                for p in results[:max_products]:
                    pid = str(p.get("productId", p.get("id", "")))
                    name = p.get("productName", p.get("name", ""))
                    brand = p.get("brandName", p.get("brand", {}).get("name", ""))
                    if pid:
                        products.append({"product_id": pid, "name": name, "brand": brand})
                if products:
                    return products
        return []

    def _extract_products_from_html(self, soup: BeautifulSoup, max_products: int) -> list[dict]:
        """Parse product IDs from href links like /product/WB/8930495 in search results."""
        products = []
        seen = set()
        # Zappos product URLs contain /product/ followed by letters+digits
        for tag in soup.find_all("a", href=re.compile(r"/product/[A-Z]{2}/\d+")):
            href = tag.get("href", "")
            m = re.search(r"/product/[A-Z]{2}/(\d+)", href)
            if not m:
                continue
            product_id = m.group(1)
            if product_id in seen:
                continue
            seen.add(product_id)
            # Try to grab name from aria-label or nearby text
            name = tag.get("aria-label", "") or tag.get_text(strip=True)[:80]
            products.append({"product_id": product_id, "name": name, "brand": ""})
            if len(products) >= max_products:
                break
        return products

    def _search_products_api(self, query: str, max_products: int) -> list[dict]:
        url = "https://www.zappos.com/api/3/catalog/search"
        params = {"term": query, "limit": max_products, "includes[]": "products"}
        try:
            resp = self._get(url, params=params, json_mode=True)
            data = resp.json()
            return [
                {
                    "product_id": str(p.get("productId", "")),
                    "name": p.get("productName", ""),
                    "brand": p.get("brandName", ""),
                }
                for p in data.get("results", [])[:max_products]
                if p.get("productId")
            ]
        except Exception as exc:
            logger.error("Catalog API also failed: %s", exc)
            return []

    def get_reviews(
        self,
        product_id: str,
        product_name: str,
        brand: str,
        max_reviews: int = 50,
    ) -> list[RawReview]:
        reviews = self._get_reviews_api(product_id, product_name, brand, max_reviews)
        if not reviews:
            logger.info("Review API empty; trying HTML for %s", product_id)
            reviews = self._get_reviews_html(product_id, product_name, brand, max_reviews)
        return reviews

    def _get_reviews_api(
        self,
        product_id: str,
        product_name: str,
        brand: str,
        max_reviews: int,
    ) -> list[RawReview]:
        url = REVIEW_API_URL.format(product_id=product_id)
        params = {"pageNumber": 1, "resultCount": min(max_reviews, 100)}
        try:
            resp = self._get(url, params=params, json_mode=True)
            data = resp.json()
            return [
                self._parse_review(r, product_id, product_name, brand)
                for r in data.get("reviews", [])[:max_reviews]
                if r.get("reviewText")
            ]
        except Exception as exc:
            logger.warning("Review API error for %s: %s", product_id, exc)
            return []

    def _get_reviews_html(
        self,
        product_id: str,
        product_name: str,
        brand: str,
        max_reviews: int,
    ) -> list[RawReview]:
        url = f"https://www.zappos.com/product/{product_id}"
        try:
            resp = self._get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            script_tag = soup.find("script", id="__NEXT_DATA__")
            if not script_tag or not script_tag.string:
                return []
            next_data = json.loads(script_tag.string)
            page_props = next_data.get("props", {}).get("pageProps", {})
            reviews_data = (
                page_props.get("reviews", {}).get("reviews", [])
                or page_props.get("productReviews", {}).get("reviews", [])
            )
            return [
                self._parse_review(r, product_id, product_name, brand)
                for r in reviews_data[:max_reviews]
                if r.get("reviewText")
            ]
        except Exception as exc:
            logger.error("HTML review fallback failed for %s: %s", product_id, exc)
            return []

    @staticmethod
    def _parse_review(r: dict, product_id: str, product_name: str, brand: str) -> RawReview:
        return RawReview(
            product_id=product_id,
            product_name=product_name,
            brand=brand,
            reviewer=r.get("screenName", "Anonymous"),
            rating=float(r.get("rating", 3)),
            title=r.get("reviewTitle", ""),
            body=r.get("reviewText", ""),
            date=r.get("submittedDate", ""),
            verified_purchase=r.get("verifiedPurchaser", False),
        )

import os
import time
import json
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import altair as alt
from typing import List, Dict, Optional
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.parse

analyzer = SentimentIntensityAnalyzer()

# ========================================
# API KEY MANAGEMENT
# ========================================

def get_api_key(key_name: str, user_key: Optional[str] = None) -> Optional[str]:
    """
    Get API key with fallback priority:
    1. User-provided key
    2. Streamlit secrets (app's shared keys)
    3. Environment variables
    4. None
    """
    if user_key:
        return user_key
    
    try:
        if hasattr(st, 'secrets') and key_name in st.secrets:
            return st.secrets[key_name]
    except:
        pass
    
    env_key = os.getenv(key_name)
    if env_key:
        return env_key
    
    return None


# ========================================
# SENTIMENT GRADING SYSTEM
# ========================================

def get_sentiment_grade(score: float) -> Dict[str, str]:
    """Convert sentiment score to letter grade with emoji and description."""
    if score >= 0.5:
        return {
            "grade": "A+",
            "emoji": "🚀",
            "description": "Extremely Bullish",
            "color": "#10b981",
            "advice": "Strong positive sentiment! Community is very optimistic."
        }
    elif score >= 0.3:
        return {
            "grade": "A",
            "emoji": "📈",
            "description": "Very Bullish",
            "color": "#34d399",
            "advice": "High positive sentiment. Good vibes in the community."
        }
    elif score >= 0.1:
        return {
            "grade": "B",
            "emoji": "😊",
            "description": "Bullish",
            "color": "#6ee7b7",
            "advice": "Moderately positive sentiment. Cautiously optimistic."
        }
    elif score >= -0.1:
        return {
            "grade": "C",
            "emoji": "😐",
            "description": "Neutral",
            "color": "#fbbf24",
            "advice": "Mixed sentiment. Community is divided or uncertain."
        }
    elif score >= -0.3:
        return {
            "grade": "D",
            "emoji": "📉",
            "description": "Bearish",
            "color": "#fb923c",
            "advice": "Moderately negative sentiment. Proceed with caution."
        }
    else:
        return {
            "grade": "F",
            "emoji": "💀",
            "description": "Extremely Bearish",
            "color": "#ef4444",
            "advice": "Strong negative sentiment! High fear in the community."
        }


# ========================================
# PROXY SUPPORT
# ========================================

def get_free_proxies():
    """Fetch free proxies."""
    proxies = []
    try:
        r = requests.get(
            "https://api.proxyscrape.com/v2/?request=get&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all",
            timeout=10
        )
        if r.status_code == 200:
            proxies.extend([f"http://{p}" for p in r.text.strip().split('\n') if p])
    except:
        pass
    
    return proxies[:20]


def safe_request(url, params=None, headers=None, proxies_list=None, timeout=10):
    """Request with proxy fallback."""
    try:
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
        if r.status_code == 200:
            return r
    except:
        pass
    
    if proxies_list:
        for proxy in random.sample(proxies_list, min(3, len(proxies_list))):
            try:
                r = requests.get(
                    url, 
                    params=params, 
                    headers=headers,
                    proxies={"http": proxy, "https": proxy},
                    timeout=timeout
                )
                if r.status_code == 200:
                    return r
            except:
                continue
    
    return None


# ========================================
# HELPERS
# ========================================

def vader_label(score):
    if score > 0.05:
        return "positive"
    elif score < -0.05:
        return "negative"
    return "neutral"


def sentiment_emoji(score):
    """Get emoji for sentiment score."""
    if score > 0.3:
        return "🚀"
    elif score > 0.1:
        return "📈"
    elif score > -0.1:
        return "😐"
    elif score > -0.3:
        return "📉"
    else:
        return "💀"


# ========================================
# CRYPTO TWITTER SOURCES
# ========================================

def fetch_ct_nitter(query: str, limit: int, proxies_list=None) -> tuple[List[Dict], str]:
    """Nitter instances - free Twitter mirrors."""
    if limit == 0:
        return [], "Disabled"
    
    items = []
    nitter_instances = [
        "nitter.poast.org",
        "nitter.privacydev.net", 
        "nitter.woodland.cafe",
        "nitter.lucabased.xyz",
        "nitter.mint.lgbt",
        "xcancel.com",
    ]
    
    for instance in nitter_instances:
        try:
            url = f"https://{instance}/search/rss"
            params = {"q": f"{query} lang:en", "f": "tweets"}
            
            r = safe_request(url, params=params, proxies_list=proxies_list, timeout=15)
            
            if not r:
                continue
            
            content = r.text
            import re
            tweets = re.findall(r'<item>.*?</item>', content, re.DOTALL)
            
            for tweet_xml in tweets[:limit]:
                text_match = re.search(r'<description>(.*?)</description>', tweet_xml, re.DOTALL)
                link_match = re.search(r'<link>(.*?)</link>', tweet_xml)
                
                if text_match:
                    text = re.sub(r'<[^>]+>', '', text_match.group(1)).strip()
                    score = analyzer.polarity_scores(text)["compound"]
                    
                    items.append({
                        "source": "ct_nitter",
                        "title": text[:80],
                        "text": text,
                        "url": link_match.group(1) if link_match else "",
                        "dt": datetime.utcnow().isoformat(),
                        "compound": score,
                        "label": vader_label(score),
                    })
                
                if len(items) >= limit:
                    break
            
            if items:
                return items, f"✅ {len(items)} tweets"
                
        except Exception as e:
            continue
    
    return [], "❌ All instances down"


def fetch_ct_rapidapi(query: str, limit: int, api_key: Optional[str]) -> tuple[List[Dict], str]:
    """RapidAPI Twitter scraper."""
    if limit == 0:
        return [], "Disabled"
    
    key = get_api_key("RAPIDAPI_KEY", api_key)
    
    if not key:
        return [], "⚠️ No API key"
    
    items = []
    
    try:
        url = "https://twitter154.p.rapidapi.com/search/search"
        
        headers = {
            "X-RapidAPI-Key": key,
            "X-RapidAPI-Host": "twitter154.p.rapidapi.com"
        }
        
        params = {
            "query": query,
            "section": "top",
            "limit": str(limit),
            "language": "en"
        }
        
        r = requests.get(url, headers=headers, params=params, timeout=15)
        
        if r.status_code == 429:
            return [], "⚠️ Rate limit reached"
        
        if r.status_code != 200:
            return [], f"❌ API error: {r.status_code}"
        
        data = r.json()
        
        for tweet in data.get("results", [])[:limit]:
            text = tweet.get("text", "")
            score = analyzer.polarity_scores(text)["compound"]
            
            items.append({
                "source": "ct_rapidapi",
                "title": text[:80],
                "text": text,
                "url": f"https://twitter.com/i/status/{tweet.get('tweet_id', '')}",
                "dt": tweet.get("creation_date", datetime.utcnow().isoformat()),
                "compound": score,
                "label": vader_label(score),
            })
        
        return items, f"✅ {len(items)} tweets"
    
    except Exception as e:
        return [], f"❌ Error: {str(e)[:50]}"


# ========================================
# REDDIT
# ========================================

def fetch_reddit_json(subs: List[str], query: str, limit: int, proxies_list=None) -> tuple[List[Dict], str]:
    """Reddit without API - direct JSON endpoint."""
    if limit == 0:
        return [], "Disabled"
    
    items = []
    errors = []
    
    per_sub_limit = max(10, limit // len(subs)) if subs else limit
    
    for sub in subs:
        try:
            url = f"https://www.reddit.com/r/{sub}/search.json"
            params = {
                "q": query,
                "sort": "new",
                "limit": per_sub_limit,
                "restrict_sr": "true",
                "t": "month"
            }
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            r = safe_request(url, params=params, headers=headers, proxies_list=proxies_list)
            
            if not r:
                errors.append(sub)
                continue
            
            try:
                data = r.json()
            except:
                errors.append(sub)
                continue
            
            posts = data.get("data", {}).get("children", [])
            
            if not posts:
                url2 = f"https://www.reddit.com/r/{sub}/hot.json"
                params2 = {"limit": per_sub_limit}
                r2 = safe_request(url2, params=params2, headers=headers, proxies_list=proxies_list)
                
                if r2:
                    try:
                        data = r2.json()
                        posts = data.get("data", {}).get("children", [])
                    except:
                        pass
            
            for post in posts:
                p = post.get("data", {})
                text = f"{p.get('title', '')} {p.get('selftext', '')}"
                
                if query.lower() not in text.lower():
                    continue
                
                score = analyzer.polarity_scores(text)["compound"]
                
                items.append({
                    "source": "reddit",
                    "title": p.get("title", ""),
                    "text": text,
                    "url": f"https://reddit.com{p.get('permalink', '')}",
                    "dt": datetime.utcfromtimestamp(p.get("created_utc", 0)).isoformat(),
                    "compound": score,
                    "label": vader_label(score),
                })
                
                if len(items) >= limit:
                    break
            
            time.sleep(0.5)
            
        except Exception as e:
            errors.append(sub)
            continue
    
    status = f"✅ {len(items)} posts"
    if errors:
        status += f" (⚠️ {len(errors)} subs failed)"
    
    if len(items) == 0:
        status = "⚠️ No posts found (try broader terms)"
    
    return items, status


# ========================================
# NEWS
# ========================================

def fetch_news(query: str, days: int, limit: int, api_key: Optional[str]) -> tuple[List[Dict], str]:
    """NewsAPI."""
    if limit == 0:
        return [], "Disabled"
    
    key = get_api_key("NEWSAPI_KEY", api_key)
    
    if not key:
        return [], "⚠️ No API key"

    start = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    url = f"https://newsapi.org/v2/everything?q={query}&from={start}&sortBy=publishedAt&language=en&pageSize={limit}"

    try:
        r = requests.get(url, headers={"X-Api-Key": key}, timeout=15)
        
        if r.status_code == 429:
            return [], "⚠️ Rate limit reached"
        
        if r.status_code != 200:
            return [], f"❌ API error: {r.status_code}"

        items = []
        for a in r.json().get("articles", []):
            text = f"{a['title']} {a.get('description','')}"
            score = analyzer.polarity_scores(text)["compound"]
            items.append({
                "source": "news",
                "title": a["title"],
                "text": text,
                "url": a["url"],
                "dt": a["publishedAt"],
                "compound": score,
                "label": vader_label(score),
            })
        
        return items, f"✅ {len(items)} articles"
    except Exception as e:
        return [], f"❌ Error: {str(e)[:50]}"


# ========================================
# NEW RELIABLE SOURCES
# ========================================

def fetch_coingecko_trending() -> tuple[List[Dict], str]:
    """CoinGecko trending coins."""
    try:
        r = requests.get("https://api.coingecko.com/api/v3/search/trending", timeout=10)
        
        if r.status_code != 200:
            return [], "❌ API error"
        
        items = []
        coins = r.json().get("coins", [])
        
        for coin_data in coins[:7]:
            coin = coin_data.get("item", {})
            text = f"Trending: {coin.get('name')} ({coin.get('symbol')}) - Rank #{coin.get('market_cap_rank', 'N/A')}"
            
            score = 0.3
            
            items.append({
                "source": "coingecko_trending",
                "title": text,
                "text": text,
                "url": f"https://www.coingecko.com/en/coins/{coin.get('id')}",
                "dt": datetime.utcnow().isoformat(),
                "compound": score,
                "label": vader_label(score),
            })
        
        return items, f"✅ {len(items)} trending"
    except Exception as e:
        return [], f"❌ Error: {str(e)[:50]}"


def fetch_cryptocompare_news(query: str, limit: int) -> tuple[List[Dict], str]:
    """CryptoCompare News API."""
    if limit == 0:
        return [], "Disabled"
    
    try:
        url = "https://min-api.cryptocompare.com/data/v2/news/"
        params = {"lang": "EN"}
        
        r = requests.get(url, params=params, timeout=10)
        
        if r.status_code != 200:
            return [], f"❌ API error: {r.status_code}"
        
        items = []
        articles = r.json().get("Data", [])
        
        filtered = [a for a in articles if query.lower() in a.get("title", "").lower() or 
                    query.lower() in a.get("body", "").lower()]
        
        if not filtered:
            filtered = articles[:limit]
        
        for article in filtered[:limit]:
            text = f"{article.get('title', '')} {article.get('body', '')[:200]}"
            score = analyzer.polarity_scores(text)["compound"]
            
            items.append({
                "source": "cryptocompare",
                "title": article.get("title", ""),
                "text": text,
                "url": article.get("url", ""),
                "dt": datetime.utcfromtimestamp(article.get("published_on", 0)).isoformat(),
                "compound": score,
                "label": vader_label(score),
            })
        
        return items, f"✅ {len(items)} articles"
    except Exception as e:
        return [], f"❌ Error: {str(e)[:50]}"


def fetch_cryptopanic(query: str, limit: int) -> tuple[List[Dict], str]:
    """CryptoPanic API."""
    if limit == 0:
        return [], "Disabled"
    
    items = []
    
    try:
        url = "https://cryptopanic.com/api/free/v1/posts/"
        params = {
            "auth_token": "free",
            "public": "true",
            "kind": "news",
            "filter": "rising",
        }
        
        known_currencies = ["BTC", "ETH", "AVAX", "SOL", "ADA", "DOT", "MATIC", "LINK"]
        if query.upper() in known_currencies:
            params["currencies"] = query.upper()
        
        r = requests.get(url, params=params, timeout=10)
        
        if r.status_code != 200:
            url = "https://cryptopanic.com/api/free/v1/posts/"
            params = {
                "auth_token": "free",
                "public": "true",
                "kind": "news"
            }
            r = requests.get(url, params=params, timeout=10)
            
            if r.status_code != 200:
                return [], f"❌ API unavailable"
        
        results = r.json().get("results", [])
        
        if "currencies" not in params:
            results = [a for a in results if query.lower() in a.get("title", "").lower()]
        
        for article in results[:limit]:
            text = article["title"]
            score = analyzer.polarity_scores(text)["compound"]
            
            items.append({
                "source": "cryptopanic",
                "title": article["title"],
                "text": text,
                "url": article["url"],
                "dt": article["published_at"],
                "compound": score,
                "label": vader_label(score),
            })
        
        if not items:
            return [], "⚠️ No results"
        
        return items, f"✅ {len(items)} articles"
    except Exception as e:
        return [], f"❌ Error: {str(e)[:50]}"


def fetch_coinmarketcap_news(query: str, limit: int) -> tuple[List[Dict], str]:
    """CoinMarketCap news."""
    if limit == 0:
        return [], "Disabled"
    
    try:
        url = f"https://coinmarketcap.com/headlines/news/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        r = requests.get(url, headers=headers, timeout=10)
        
        if r.status_code != 200:
            return [], "❌ Scraping blocked"
        
        import re
        headlines = re.findall(r'<h3[^>]*>(.*?)</h3>', r.text)
        
        items = []
        for headline in headlines[:limit]:
            clean_headline = re.sub(r'<[^>]+>', '', headline).strip()
            
            if not clean_headline or len(clean_headline) < 10:
                continue
            
            if query.lower() not in clean_headline.lower():
                continue
            
            score = analyzer.polarity_scores(clean_headline)["compound"]
            
            items.append({
                "source": "coinmarketcap",
                "title": clean_headline,
                "text": clean_headline,
                "url": "https://coinmarketcap.com/headlines/news/",
                "dt": datetime.utcnow().isoformat(),
                "compound": score,
                "label": vader_label(score),
            })
        
        if not items:
            return [], "⚠️ No matching news"
        
        return items, f"✅ {len(items)} headlines"
    except Exception as e:
        return [], f"❌ Error: {str(e)[:50]}"


# ========================================
# MARKET DATA
# ========================================

def fetch_fear_greed() -> Optional[Dict]:
    """Alternative.me Fear & Greed Index."""
    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=10)
        if r.status_code == 200:
            data = r.json()["data"][0]
            return {
                "value": int(data["value"]),
                "classification": data["value_classification"],
                "timestamp": data["timestamp"]
            }
    except:
        pass
    return None


def get_coingecko_id(symbol: str) -> Optional[str]:
    """Map symbols to CoinGecko IDs."""
    symbol_map = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "AVAX": "avalanche-2",
        "APT": "aptos",
        "SOL": "solana",
        "ADA": "cardano",
        "DOT": "polkadot",
        "MATIC": "matic-network",
        "LINK": "chainlink",
        "UNI": "uniswap",
        "ATOM": "cosmos",
        "XRP": "ripple",
        "DOGE": "dogecoin",
        "SHIB": "shiba-inu",
        "LTC": "litecoin",
        "NEAR": "near",
        "ARB": "arbitrum",
        "OP": "optimism",
    }
    
    symbol_upper = symbol.upper()
    
    if symbol_upper in symbol_map:
        return symbol_map[symbol_upper]
    
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/search",
            params={"query": symbol},
            timeout=10
        )
        
        if r.status_code == 200:
            coins = r.json().get("coins", [])
            if coins:
                return coins[0]["id"]
    except:
        pass
    
    return symbol.lower()


def get_coingecko(token: str) -> tuple[Optional[Dict], str]:
    """CoinGecko API - price data."""
    try:
        coin_id = get_coingecko_id(token)
        
        if not coin_id:
            return None, "❌ Token not found"
        
        r = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}",
            params={"localization": False, "tickers": False, "market_data": True},
            timeout=10,
        )
        
        if r.status_code != 200:
            return None, f"❌ API error: {r.status_code}"
        
        d = r.json()
        data = {
            "name": d["name"],
            "symbol": d["symbol"].upper(),
            "coingecko_id": d["id"],
            "price_usd": d["market_data"]["current_price"]["usd"],
            "market_cap_usd": d["market_data"]["market_cap"]["usd"],
            "volume_24h_usd": d["market_data"]["total_volume"]["usd"],
            "price_change_24h": d["market_data"]["price_change_percentage_24h"],
        }
        
        return data, "✅ Success"
    except Exception as e:
        return None, f"❌ Error: {str(e)[:50]}"


# ========================================
# PARALLEL FETCHING
# ========================================

def fetch_all_parallel(config):
    """Fetch all data sources in parallel."""
    results = {}
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {}
        
        if config['ct_limit'] > 0:
            if config['ct_method'] in ["Nitter (Free)", "All"]:
                futures['ct_nitter'] = executor.submit(
                    fetch_ct_nitter, 
                    config['query'], 
                    config['ct_limit'],
                    config.get('proxies')
                )
            
            if config['ct_method'] in ["RapidAPI", "All"] and (config.get('rapidapi_key') or get_api_key("RAPIDAPI_KEY")):
                futures['ct_rapidapi'] = executor.submit(
                    fetch_ct_rapidapi,
                    config['query'],
                    config['ct_limit'],
                    config['rapidapi_key']
                )
        
        if config['reddit_limit'] > 0:
            futures['reddit'] = executor.submit(
                fetch_reddit_json,
                config['subs'],
                config['query'],
                config['reddit_limit'],
                config.get('proxies')
            )
        
        if config['news_limit'] > 0:
            futures['news'] = executor.submit(
                fetch_news,
                config['query'],
                config['lookback'],
                config['news_limit'],
                config['newsapi_key']
            )
        
        if config['cryptopanic_limit'] > 0:
            futures['cryptopanic'] = executor.submit(
                fetch_cryptopanic,
                config['query'],
                config['cryptopanic_limit']
            )
        
        if config.get('cryptocompare_limit', 0) > 0:
            futures['cryptocompare'] = executor.submit(
                fetch_cryptocompare_news,
                config['query'],
                config['cryptocompare_limit']
            )
        
        if config.get('cmc_limit', 0) > 0:
            futures['cmc'] = executor.submit(
                fetch_coinmarketcap_news,
                config['query'],
                config['cmc_limit']
            )
        
        if config.get('trending_enabled', False):
            futures['trending'] = executor.submit(fetch_coingecko_trending)
        
        futures['coingecko'] = executor.submit(
            get_coingecko,
            config['query']
        )
        
        futures['fear_greed'] = executor.submit(fetch_fear_greed)
        
        for name, future in futures.items():
            try:
                results[name] = future.result(timeout=30)
            except Exception as e:
                results[name] = ([], f"❌ Timeout/Error")
    
    return results


# ========================================
# STREAMLIT UI
# ========================================

st.set_page_config(
    page_title="CryptoVibes - Sentiment Analysis",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: 700;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    .status-badge {
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
        font-size: 0.875rem;
        font-weight: 600;
        display: inline-block;
        margin: 0.25rem;
    }
    .success {
        background-color: #10b981;
        color: white;
    }
    .error {
        background-color: #ef4444;
        color: white;
    }
    .grade-card {
        padding: 2rem;
        border-radius: 16px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin: 1rem 0;
    }
    .grade-emoji {
        font-size: 4rem;
        margin-bottom: 0.5rem;
    }
    .grade-letter {
        font-size: 3rem;
        font-weight: 700;
        margin: 0.5rem 0;
    }
    .grade-desc {
        font-size: 1.5rem;
        font-weight: 600;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<h1 class="main-header">🔮 CryptoVibes</h1>', unsafe_allow_html=True)
st.caption("Real-time sentiment analysis from Twitter, Reddit, News & more")

# Sidebar Configuration
with st.sidebar:
    st.markdown("### 🎯 Analysis Settings")
    
    query = st.text_input("Token/Symbol", "BTC", help="Enter crypto symbol (BTC, ETH, AVAX, etc.)")
    lookback = st.slider("Lookback Days", 1, 30, 7)
    
    st.markdown("---")
    st.markdown("### 📊 Data Sources")
    
    with st.expander("🐦 Crypto Twitter (CT)", expanded=True):
        ct_method = st.selectbox(
            "Method",
            ["Nitter (Free)", "RapidAPI", "All"],
            help="Nitter is free but less reliable"
        )
        ct_limit = st.slider("Posts", 0, 100, 30)
    
    with st.expander("📱 Reddit"):
        reddit_limit = st.slider("Posts", 0, 150, 60, key="reddit")
        subs_in = st.text_area(
            "Subreddits (one per line)",
            "bitcoin\ncryptocurrency\nbtc"
        )
        subs = [s.strip() for s in subs_in.splitlines() if s.strip()]
    
    with st.expander("📰 News & Feeds"):
        news_limit = st.slider("News Articles (NewsAPI)", 0, 50, 20, key="news")
        cryptocompare_limit = st.slider("CryptoCompare News", 0, 30, 15, key="cryptocompare")
        cryptopanic_limit = st.slider("CryptoPanic", 0, 30, 10, key="cryptopanic")
    
    with st.expander("🔥 Additional Sources"):
        trending_enabled = st.checkbox("CoinGecko Trending", value=True, help="Top trending coins")
        cmc_limit = st.slider("CoinMarketCap Headlines", 0, 20, 10, key="cmc")
    
    st.markdown("---")
    st.markdown("### 🔑 API Configuration")
    
    use_own_keys = st.checkbox(
        "🔓 Use my own API keys",
        value=False,
        help="By default, we use shared free-tier keys"
    )
    
    if use_own_keys:
        st.caption("⚡ Power user mode")
        newsapi_key = st.text_input("NewsAPI", type="password")
        rapidapi_key = st.text_input("RapidAPI", type="password")
    else:
        st.caption("✅ Using shared keys")
        newsapi_key = None
        rapidapi_key = None
    
    st.markdown("---")
    use_proxies = st.checkbox("🌐 Use Proxies (experimental)")
    
    st.markdown("---")
    analyze_btn = st.button("🔍 **Analyze Sentiment**", use_container_width=True, type="primary")
    
    # Buy Me a Coffee Button
    st.markdown("---")
    st.markdown("### 💝 Support CryptoVibes")
    st.markdown("""
    <a href="https://www.buymeacoffee.com/cryptovibes" target="_blank">
        <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" 
             alt="Buy Me A Coffee" 
             style="height: 50px !important;width: 180px !important;">
    </a>
    """, unsafe_allow_html=True)
    st.caption("Help keep CryptoVibes running! ☕")

# Main content
if not analyze_btn and 'results' not in st.session_state:
    has_shared_keys = (
        get_api_key("NEWSAPI_KEY") is not None or 
        get_api_key("RAPIDAPI_KEY") is not None
    )
    
    if has_shared_keys:
        st.success("🎉 **Ready to use!** Using shared free-tier API keys for instant analysis.")
    else:
        st.warning("⚠️ **Limited mode.** Some features require API keys.")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.info("📊 **Multi-Source Analysis**\n\nAggregate sentiment from Twitter, Reddit, news and more")
    
    with col2:
        st.success("⚡ **Real-Time Data**\n\nFresh data from multiple APIs in parallel")
    
    with col3:
        st.warning("🎯 **AI-Powered**\n\nVADER sentiment analysis with smart scoring")
    
    st.markdown("---")
    st.markdown("### 🚀 Getting Started")
    st.markdown("""
    1. **Enter a token symbol** (BTC, ETH, SOL, etc.)
    2. **Configure data sources** in the sidebar
    3. **Click Analyze** to start!
    
    💡 **Tip**: Popular tokens like BTC, ETH, and SOL have the most data.
    """)
    
    st.stop()

# Fetch data
if analyze_btn:
    st.session_state['analyzing'] = True
    
    config = {
        'query': query,
        'lookback': lookback,
        'ct_method': ct_method,
        'ct_limit': ct_limit,
        'reddit_limit': reddit_limit,
        'news_limit': news_limit,
        'cryptopanic_limit': cryptopanic_limit,
        'cryptocompare_limit': cryptocompare_limit,
        'cmc_limit': cmc_limit,
        'trending_enabled': trending_enabled,
        'subs': subs,
        'newsapi_key': newsapi_key if newsapi_key else None,
        'rapidapi_key': rapidapi_key if rapidapi_key else None,
        'proxies': get_free_proxies() if use_proxies else None
    }
    
    with st.spinner(f"🔮 Analyzing crypto vibes for ${query}..."):
        results = fetch_all_parallel(config)
        st.session_state['results'] = results
        st.session_state['config'] = config

# Display results
if 'results' in st.session_state:
    results = st.session_state['results']
    config = st.session_state['config']
    
    # Status badges
    st.markdown("### 📡 Data Sources Status")
    
    enabled_sources = []
    source_info = []
    
    if config.get('ct_limit', 0) > 0:
        if 'ct_nitter' in results:
            source_info.append(('CT Nitter', results['ct_nitter']))
        if 'ct_rapidapi' in results:
            source_info.append(('CT Rapid', results['ct_rapidapi']))
    
    if config.get('reddit_limit', 0) > 0 and 'reddit' in results:
        source_info.append(('Reddit', results['reddit']))
    
    if config.get('news_limit', 0) > 0 and 'news' in results:
        source_info.append(('NewsAPI', results['news']))
    
    if config.get('cryptocompare_limit', 0) > 0 and 'cryptocompare' in results:
        source_info.append(('CryptoCompare', results['cryptocompare']))
    
    if config.get('cryptopanic_limit', 0) > 0 and 'cryptopanic' in results:
        source_info.append(('CryptoPanic', results['cryptopanic']))
    
    if config.get('cmc_limit', 0) > 0 and 'cmc' in results:
        source_info.append(('CMC', results['cmc']))
    
    if config.get('trending_enabled', False) and 'trending' in results:
        source_info.append(('Trending', results['trending']))
    
    if 'coingecko' in results:
        source_info.append(('CoinGecko', results['coingecko']))
    
    num_cols = min(len(source_info), 6)
    if num_cols > 0:
        cols = st.columns(num_cols)
        
        for i, (label, result) in enumerate(source_info[:6]):
            data, status = result if isinstance(result, tuple) else (result, "✅")
            
            badge_class = "success" if "✅" in status else "error"
            col_idx = i % num_cols
            
            cols[col_idx].markdown(
                f'<div class="status-badge {badge_class}">{label}<br/><small>{status}</small></div>',
                unsafe_allow_html=True
            )
        
        if len(source_info) > 6:
            cols2 = st.columns(min(len(source_info) - 6, 6))
            for i, (label, result) in enumerate(source_info[6:12]):
                data, status = result if isinstance(result, tuple) else (result, "✅")
                badge_class = "success" if "✅" in status else "error"
                cols2[i].markdown(
                    f'<div class="status-badge {badge_class}">{label}<br/><small>{status}</small></div>',
                    unsafe_allow_html=True
                )
    
    st.markdown("---")
    
    # Aggregate all sentiment data
    all_data = []
    sentiment_sources = ['ct_nitter', 'ct_rapidapi', 'reddit', 'news', 'cryptopanic', 
                        'cryptocompare', 'cmc', 'trending']
    
    for name in sentiment_sources:
        if name in results:
            data, _ = results[name] if isinstance(results[name], tuple) else (results[name], "")
            if data:
                all_data.extend(data)
    
    df = pd.DataFrame(all_data)
    
    if df.empty:
        st.error("❌ No sentiment data collected. Try different settings or popular tokens like BTC, ETH, or SOL.")
        st.stop()
    
    # Calculate overall sentiment
    overall_sentiment = df["compound"].mean()
    grade_info = get_sentiment_grade(overall_sentiment)
    
    # SENTIMENT GRADE CARD
    st.markdown(f"""
    <div class="grade-card" style="background: linear-gradient(135deg, {grade_info['color']}22, {grade_info['color']}44); border: 3px solid {grade_info['color']};">
        <div class="grade-emoji">{grade_info['emoji']}</div>
        <div class="grade-letter" style="color: {grade_info['color']};">{grade_info['grade']}</div>
        <div class="grade-desc" style="color: {grade_info['color']};">{grade_info['description']}</div>
        <p style="font-size: 1.1rem; margin-top: 1rem; color: #666;">{grade_info['advice']}</p>
        <p style="font-size: 0.9rem; color: #888; margin-top: 0.5rem;">Sentiment Score: {overall_sentiment:.3f}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Share on Twitter Button
    tweet_text = f"Just analyzed ${config['query']} sentiment on CryptoVibes! Grade: {grade_info['grade']} {grade_info['emoji']} - {grade_info['description']}. Check it out!"
    tweet_url = "https://cryptovibes.streamlit.app"
    twitter_url = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(tweet_text)}&url={urllib.parse.quote(tweet_url)}"
    
    st.markdown(f"""
    <div style="text-align: center; margin: 1rem 0;">
        <a href="{twitter_url}" target="_blank" style="
            display: inline-block;
            background: #1DA1F2;
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 1.1rem;
        ">
            🐦 Share on Twitter
        </a>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Main metrics
    st.markdown("### 💬 Sentiment Breakdown")
    
    label_counts = df["label"].value_counts()
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("📊 Total Items", len(df))
    col2.metric("✅ Positive", label_counts.get("positive", 0))
    col3.metric("❌ Negative", label_counts.get("negative", 0))
    col4.metric("⚪ Neutral", label_counts.get("neutral", 0))
    
    # Source breakdown
    st.markdown("### 📈 Sentiment by Source")
    
    agg = (
        df.groupby("source", as_index=False)
        .agg(mean_compound=("compound", "mean"), items=("compound", "count"))
    )
    agg["mean_compound"] = agg["mean_compound"].round(4)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        chart = (
            alt.Chart(agg)
            .mark_bar()
            .encode(
                x=alt.X("source:N", title="Source", sort="-y"),
                y=alt.Y("mean_compound:Q", title="Mean Sentiment", scale=alt.Scale(domain=[-1, 1])),
                color=alt.condition(
                    alt.datum.mean_compound > 0,
                    alt.value("#10b981"),
                    alt.value("#ef4444")
                ),
                tooltip=["source", "mean_compound", "items"],
            )
            .properties(height=400)
        )
        st.altair_chart(chart, use_container_width=True)
    
    with col2:
        try:
            st.dataframe(
                agg.style.background_gradient(cmap='RdYlGn', subset=['mean_compound']),
                use_container_width=True,
                height=400
            )
        except ImportError:
            st.dataframe(agg, use_container_width=True, height=400)
    
    # Market context
    st.markdown("---")
    st.markdown("### 💰 Market Data")
    
    cg_data, cg_status = results.get('coingecko', (None, "❌ Error"))
    fear_greed = results.get('fear_greed')
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    if cg_data:
        with col1:
            st.metric("💵 Price", f"${cg_data['price_usd']:,.2f}")
        with col2:
            st.metric(
                "📈 24h Change",
                f"{cg_data['price_change_24h']:.2f}%",
                delta=f"{cg_data['price_change_24h']:.2f}%"
            )
        with col3:
            st.metric("🏦 Market Cap", f"${cg_data['market_cap_usd']/1e9:.2f}B")
        with col4:
            st.metric("📊 24h Volume", f"${cg_data['volume_24h_usd']/1e6:.0f}M")
    
    if fear_greed:
        with col5:
            fg_emoji = "😱" if fear_greed['value'] < 25 else "😰" if fear_greed['value'] < 50 else "😊" if fear_greed['value'] < 75 else "🤑"
            st.metric(
                f"{fg_emoji} Fear & Greed",
                fear_greed['value'],
                delta=fear_greed['classification']
            )
    
    # Timeline
    st.markdown("---")
    st.markdown("### 📈 Sentiment Timeline")
    
    if "dt" in df.columns:
        df["dt"] = pd.to_datetime(df["dt"], errors="coerce")
        df_timeline = df.dropna(subset=["dt"]).copy()
        
        if not df_timeline.empty:
            timeline_chart = (
                alt.Chart(df_timeline)
                .mark_circle(size=100, opacity=0.6)
                .encode(
                    x=alt.X("dt:T", title="Time"),
                    y=alt.Y("compound:Q", title="Sentiment", scale=alt.Scale(domain=[-1, 1])),
                    color=alt.Color(
                        "source:N",
                        title="Source",
                        scale=alt.Scale(scheme='category10')
                    ),
                    tooltip=["source", "dt", "compound", "title"]
                )
                .properties(height=400)
                .interactive()
            )
            
            st.altair_chart(timeline_chart, use_container_width=True)
    
    # Raw data
    st.markdown("---")
    st.markdown("### 📋 Detailed Items")
    
    show_cols = ["source", "dt", "label", "compound", "title", "url"]
    df_show = df.sort_values("compound", ascending=False)
    
    col1, col2 = st.columns(2)
    with col1:
        filter_source = st.multiselect("Filter by source", df["source"].unique())
    with col2:
        filter_label = st.multiselect("Filter by sentiment", ["positive", "negative", "neutral"])
    
    if filter_source:
        df_show = df_show[df_show["source"].isin(filter_source)]
    if filter_label:
        df_show = df_show[df_show["label"].isin(filter_label)]
    
    st.dataframe(
        df_show[show_cols].head(100),
        use_container_width=True,
        height=400
    )
    
    # Download
    csv = df.to_csv(index=False)
    st.download_button(
        "⬇️ Download Full Dataset (CSV)",
        csv,
        f"cryptovibes_{config['query']}_{datetime.now().strftime('%Y%m%d')}.csv",
        "text/csv",
        use_container_width=True
    )
    
    st.success("✅ Analysis complete!")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666; padding: 2rem 0;">
        <p>Made with ❤️ by CryptoVibes | Not financial advice</p>
        <p style="font-size: 0.9rem;">Data sources: Twitter, Reddit, NewsAPI, CryptoPanic, CoinGecko</p>
    </div>
    """, unsafe_allow_html=True)

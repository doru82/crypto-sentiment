import os
import sys
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import requests
import time

# Import TOATE funcțiile din aplicația ta CryptoVibes
from app import (
    fetch_all_parallel,
    get_sentiment_grade,
    get_coingecko
)

load_dotenv()

# ========================================
# CONFIGURATION
# ========================================

TYPEFULLY_API_KEY = os.getenv("TYPEFULLY_API_KEY", "")

TOP_5_COINS = ["BTC", "ETH", "SOL", "ADA", "XRP"]
SPECIAL_COIN = "AVAX"


# ========================================
# TYPEFULLY API V2
# ========================================

def get_social_set_id() -> str:
    """Get the first social set ID (Twitter account)."""
    if not TYPEFULLY_API_KEY:
        raise ValueError("TYPEFULLY_API_KEY not found!")
    
    headers = {
        "Authorization": f"Bearer {TYPEFULLY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(
            "https://api.typefully.com/v2/social-sets",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("results") and len(data["results"]) > 0:
                social_set_id = data["results"][0]["id"]
                print(f"✅ Found social set ID: {social_set_id}")
                return str(social_set_id)
            else:
                raise ValueError("No social sets found!")
        else:
            raise ValueError(f"Failed to get social sets: {response.status_code}")
    
    except Exception as e:
        raise ValueError(f"Error getting social set: {e}")


# ========================================
# ANALYZE USING CRYPTOVIBES APP
# ========================================

def analyze_coin_with_cryptovibes(coin: str) -> dict:
    """
    Analizează coin folosind EXACT aceleași funcții din app.py.
    Returnează sentiment identic cu cel din aplicația Streamlit!
    """
    print(f"  📊 Analyzing {coin} with CryptoVibes engine...")
    
    # Configurare IDENTICĂ cu Streamlit app
    config = {
        'query': coin,
        'lookback': 7,
        'ct_method': "Nitter (Free)",
        'ct_limit': 30,
        'reddit_limit': 60,
        'subs': ['CryptoCurrency', 'Bitcoin', 'ethereum', 'solana', 'cardano'],
        'news_limit': 20,
        'cryptopanic_limit': 10,
        'cryptocompare_limit': 15,
        'cmc_limit': 10,
        'trending_enabled': True,
        'newsapi_key': os.getenv("NEWSAPI_KEY"),
        'rapidapi_key': os.getenv("RAPIDAPI_KEY"),
        'proxies': None
    }
    
    # Pentru AVAX, adaugă subreddit-uri specifice
    if coin.upper() == "AVAX":
        config['subs'] = ['Avax', 'Avalanche', 'CryptoCurrency', 'altcoin']
    
    try:
        # Rulează EXACT ca în app.py - fetch paralel de la toate sursele
        results = fetch_all_parallel(config)
        
        # Agregă datele EXACT ca în app.py
        all_data = []
        sentiment_sources = ['ct_nitter', 'ct_rapidapi', 'reddit', 'news', 
                           'cryptopanic', 'cryptocompare', 'cmc', 'trending']
        
        for name in sentiment_sources:
            if name in results:
                data, status = results[name] if isinstance(results[name], tuple) else (results[name], "")
                if data and isinstance(data, list):
                    all_data.extend(data)
        
        if not all_data:
            print(f"  ⚠️ No data collected for {coin}")
            return {"error": True, "coin": coin}
        
        # Calculează sentiment EXACT ca în app.py
        df = pd.DataFrame(all_data)
        overall_sentiment = df["compound"].mean()
        grade_info = get_sentiment_grade(overall_sentiment)
        
        # Informații price (bonus)
        price_info = {}
        if 'coingecko' in results:
            cg_data, _ = results['coingecko']
            if cg_data:
                price_info = {
                    'price_change_24h': cg_data.get('price_change_24h', 0),
                    'price_usd': cg_data.get('price_usd', 0)
                }
        
        print(f"  ✅ {coin}: {grade_info['grade']} {grade_info['emoji']} ({overall_sentiment:.3f})")
        
        return {
            "coin": coin,
            "sentiment": overall_sentiment,
            "grade": grade_info["grade"],
            "emoji": grade_info["emoji"],
            "desc": grade_info["description"],
            "items_analyzed": len(all_data),
            **price_info
        }
        
    except Exception as e:
        print(f"  ❌ Error analyzing {coin}: {e}")
        return {"error": True, "coin": coin}


# ========================================
# TWEET FORMATTING
# ========================================

def format_top5_tweet(results: list) -> str:
    """Format tweet for top 5 coins."""
    tweet = "🔮 Daily Crypto Sentiment\n\n"
    
    for r in results:
        if not r.get("error"):
            # Adaugă price change dacă există
            price_str = ""
            if 'price_change_24h' in r and r['price_change_24h'] != 0:
                price_str = f" ({r['price_change_24h']:+.1f}%)"
            
            tweet += f"${r['coin']}: {r['grade']} {r['emoji']}{price_str}\n"
    
    total_analyzed = sum(r.get('items_analyzed', 0) for r in results if not r.get("error"))
    tweet += f"\n📊 {total_analyzed} sources analyzed"
    tweet += "\n🔗 cryptovibes.streamlit.app"
    tweet += "\n\n#Crypto #Bitcoin #Sentiment"
    
    return tweet


def format_avax_tweet(result: dict) -> str:
    """Format detailed tweet for AVAX."""
    if result.get("error"):
        return None
    
    tweet = f"🔺 $AVAX Daily Report\n\n"
    tweet += f"Grade: {result['grade']} {result['emoji']}\n"
    tweet += f"Sentiment: {result['desc']}\n"
    
    # Price info dacă există
    if 'price_change_24h' in result:
        tweet += f"24h: {result['price_change_24h']:+.1f}%\n"
    
    tweet += f"\n"
    
    # Context bazat pe sentiment
    if result['sentiment'] > 0.3:
        tweet += "🔥 Strong community momentum!\n"
    elif result['sentiment'] > 0.1:
        tweet += "📈 Positive sentiment detected\n"
    elif result['sentiment'] > -0.1:
        tweet += "😐 Mixed market signals\n"
    else:
        tweet += "⚠️ Bearish pressure noted\n"
    
    tweet += f"\n📊 Based on {result['items_analyzed']} sources"
    tweet += "\n🔗 cryptovibes.streamlit.app"
    tweet += "\n#AVAX #Avalanche"
    
    return tweet


# ========================================
# POST TO TYPEFULLY (API V2)
# ========================================

def post_to_typefully_v2(social_set_id: str, tweet_text: str, publish_now: bool = True) -> bool:
    """Post tweet via Typefully API v2."""
    
    if not TYPEFULLY_API_KEY:
        print("❌ TYPEFULLY_API_KEY not found!")
        return False
    
    headers = {
        "Authorization": f"Bearer {TYPEFULLY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "platforms": {
            "x": {
                "enabled": True,
                "posts": [{"text": tweet_text}]
            }
        }
    }
    
    if publish_now:
        payload["publish_at"] = "now"
    
    url = f"https://api.typefully.com/v2/social-sets/{social_set_id}/drafts"
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code in [200, 201]:
            print(f"✅ Tweet {'posted' if publish_now else 'saved as draft'} successfully!")
            return True
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False


# ========================================
# MAIN EXECUTION
# ========================================

def run_daily_analysis():
    """Main function - folosește CryptoVibes engine pentru sentiment."""
    
    print(f"🚀 Starting CryptoVibes daily analysis at {datetime.now()}\n")
    
    # Get social set ID
    try:
        social_set_id = get_social_set_id()
    except Exception as e:
        print(f"❌ Failed to get social set ID: {e}")
        return
    
    # 1. Analyze Top 5 cu CryptoVibes engine
    print("\n📊 Analyzing Top 5 coins with CryptoVibes...")
    top5_results = []
    
    for coin in TOP_5_COINS:
        result = analyze_coin_with_cryptovibes(coin)
        top5_results.append(result)
        time.sleep(3)  # Rate limiting
    
    # 2. Generate & Post Top 5 tweet
    top5_tweet = format_top5_tweet(top5_results)
    print("\n" + "="*60)
    print("TWEET 1 (Top 5):")
    print("="*60)
    print(top5_tweet)
    print("="*60)
    print(f"Length: {len(top5_tweet)} chars\n")
    
    success1 = post_to_typefully_v2(social_set_id, top5_tweet, publish_now=True)
    
    if not success1:
        print("❌ Failed to post Top 5 tweet")
        return
    
    # Wait before AVAX
    print("\n⏳ Waiting 5 minutes before AVAX tweet...")
    time.sleep(300)
    
    # 3. Analyze AVAX cu CryptoVibes engine
    print(f"\n📊 Analyzing {SPECIAL_COIN} with CryptoVibes...")
    avax_result = analyze_coin_with_cryptovibes(SPECIAL_COIN)
    
    # 4. Generate & Post AVAX tweet
    avax_tweet = format_avax_tweet(avax_result)
    
    if avax_tweet:
        print("\n" + "="*60)
        print(f"TWEET 2 ({SPECIAL_COIN}):")
        print("="*60)
        print(avax_tweet)
        print("="*60)
        print(f"Length: {len(avax_tweet)} chars\n")
        
        success2 = post_to_typefully_v2(social_set_id, avax_tweet, publish_now=True)
        
        if success2:
            print(f"✅ {SPECIAL_COIN} tweet posted!")
        else:
            print(f"❌ Failed to post {SPECIAL_COIN} tweet")
    else:
        print(f"❌ Could not generate {SPECIAL_COIN} tweet")
    
    print(f"\n🎉 Analysis completed at {datetime.now()}")


# ========================================
# RUN
# ========================================

if __name__ == "__main__":
    if not TYPEFULLY_API_KEY:
        print("❌ TYPEFULLY_API_KEY not found in .env!")
        exit(1)
    
    print("🤖 CryptoVibes X Bot (Integrated with app.py)")
    print("=" * 60)
    

    run_daily_analysis()

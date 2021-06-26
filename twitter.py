from twitter_scraper import get_tweets
t = get_tweets('twitter', pages=1)
print(next(t))

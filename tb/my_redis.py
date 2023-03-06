import redis as _redis
pool = _redis.ConnectionPool(host='127.0.0.1', port=6379, db=0, decode_responses=True)
cur_redis = _redis.Redis(connection_pool=pool)
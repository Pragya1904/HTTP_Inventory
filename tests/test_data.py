"""
Shared test URLs for metadata fetcher and publisher integration tests.

Real-world URLs with varying headers, cookies, redirects, and content types.
Use for: metadata fetcher integration tests (parametrized), publisher/worker
integration tests (pick randomly via random.choice(TEST_URLS)).
"""

# ---- Full list: use for random selection in publisher integration tests ----
TEST_URLS = [
    "https://www.wikipedia.org/",
    "https://www.python.org/",
    "https://httpbin.org/get",
    "https://httpbin.org/cookies/set?testcookie=1",
    "https://httpbin.org/redirect/2",
    "https://www.google.com",
    "https://www.github.com",
    "https://www.amazon.com/",
    "https://www.cloudflare.com/",
    "https://www.cloudflare.com/cdn-cgi/trace",
    "https://www.stackoverflow.com/",
    "https://httpbin.org/status/301",
    "https://httpbin.org/status/404",
    "https://httpbin.org/status/500",
    "https://httpbin.org/image/jpeg",
    "https://httpbin.org/xml",
    "https://httpbin.org/robots.txt",
    "https://httpbin.org/cookies/set?session=abc123",
]

# ---- Expected to return 2xx (for metadata fetcher success assertions) ----
TEST_URLS_SUCCESS = [
    "https://www.wikipedia.org/",
    "https://www.python.org/",
    "https://httpbin.org/get",
    "https://httpbin.org/redirect/2",
    "https://httpbin.org/image/jpeg",
    "https://httpbin.org/xml",
    "https://httpbin.org/robots.txt",
    "https://www.cloudflare.com/cdn-cgi/trace",
]

# ---- Expected to return non-2xx (for error-path assertions) ----
TEST_URLS_ERROR_STATUS = [
    ("https://httpbin.org/status/404", 404),
    ("https://httpbin.org/status/500", 500),
]

# ---- Redirect-only (301 to nowhere; may succeed or fail depending on follow) ----
TEST_URL_REDIRECT_301 = "https://httpbin.org/status/301"

# ---- Cookie-set endpoints (success, with Set-Cookie) ----
TEST_URLS_COOKIES = [
    "https://httpbin.org/cookies/set?testcookie=1",
    "https://httpbin.org/cookies/set?session=abc123",
]

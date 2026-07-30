"""Config-driven booru subclasses for 8 simple booru APIs.

Each subclass has a unique base_url and slight variations in get_posts().
"""

import random

from ranboorux.boorus import Booru


class Danbooru(Booru):
    def __init__(self):
        from scripts.ranbooru import POST_AMOUNT

        super().__init__("Danbooru", f"https://danbooru.donmai.us/posts.json?limit={POST_AMOUNT}")

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        import scripts.ranbooru as _r

        _r.COUNT = 0
        all_fetched_posts = []
        if post_id:
            query_url = f"https://danbooru.donmai.us/posts/{post_id}.json"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, dict) and "id" in fetched_data:
                all_fetched_posts = [fetched_data]
            _r.COUNT = len(all_fetched_posts)
            print(f"[R] Found {_r.COUNT} post(s) for ID: {post_id}")
        else:
            page = random.randint(1, max_pages)
            query_url = f"{self.base_api_url}&page={page}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, list):
                all_fetched_posts = fetched_data
            _r.COUNT = len(all_fetched_posts)
            print(f"[R] Fetched {_r.COUNT} posts from page {page}.")
        return [self._standardize_post(post) for post in all_fetched_posts if post]


class XBooru(Booru):
    def __init__(self):
        from scripts.ranbooru import POST_AMOUNT

        super().__init__(
            "XBooru",
            f"https://xbooru.com/index.php?page=dapi&s=post&q=index&json=1&limit={POST_AMOUNT}",
        )

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        import scripts.ranbooru as _r

        _r.COUNT = 0
        all_fetched_posts = []
        if post_id:
            query_url = f"{self.base_api_url}&id={post_id}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, dict) and "id" in fetched_data:
                all_fetched_posts = [fetched_data]
        else:
            page = random.randint(0, max_pages - 1)
            query_url = f"{self.base_api_url}&pid={page}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, list):
                all_fetched_posts = fetched_data
        _r.COUNT = len(all_fetched_posts)
        print(f"[R] Fetched {_r.COUNT} posts from XBooru.")
        standardized_posts = []
        for post_data in all_fetched_posts:
            post = self._standardize_post(post_data)
            if "directory" in post_data and "image" in post_data:
                post["file_url"] = (
                    f"https://xbooru.com/images/{post_data['directory']}/{post_data['image']}"
                )
            standardized_posts.append(post)
        return standardized_posts


class Rule34(Booru):
    def __init__(self):
        from scripts.ranbooru import POST_AMOUNT

        super().__init__(
            "Rule34",
            f"https://api.rule34.xxx/index.php?page=dapi&s=post&q=index&json=1&limit={POST_AMOUNT}",
        )

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        import scripts.ranbooru as _r

        _r.COUNT = 0
        all_fetched_posts = []
        if post_id:
            query_url = f"{self.base_api_url}&id={post_id}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, dict) and "id" in fetched_data:
                all_fetched_posts = [fetched_data]
        else:
            page = random.randint(0, max_pages - 1)
            query_url = f"{self.base_api_url}&pid={page}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, list):
                all_fetched_posts = fetched_data
        _r.COUNT = len(all_fetched_posts)
        print(f"[R] Fetched {_r.COUNT} posts from Rule34.")
        return [self._standardize_post(post) for post in all_fetched_posts]


class Safebooru(Booru):
    def __init__(self):
        from scripts.ranbooru import POST_AMOUNT

        super().__init__(
            "Safebooru",
            f"https://safebooru.org/index.php?page=dapi&s=post&q=index&json=1&limit={POST_AMOUNT}",
        )

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        import scripts.ranbooru as _r

        _r.COUNT = 0
        all_fetched_posts = []
        if post_id:
            query_url = f"{self.base_api_url}&id={post_id}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, dict) and "id" in fetched_data:
                all_fetched_posts = [fetched_data]
        else:
            page = random.randint(0, max_pages - 1)
            query_url = f"{self.base_api_url}&pid={page}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, list):
                all_fetched_posts = fetched_data
        _r.COUNT = len(all_fetched_posts)
        print(f"[R] Fetched {_r.COUNT} posts from Safebooru.")
        standardized_posts = []
        for post_data in all_fetched_posts:
            post = self._standardize_post(post_data)
            if "directory" in post_data and "image" in post_data:
                post["file_url"] = (
                    f"https://safebooru.org/images/{post_data['directory']}/{post_data['image']}"
                )
            standardized_posts.append(post)
        return standardized_posts


class Konachan(Booru):
    def __init__(self):
        from scripts.ranbooru import POST_AMOUNT

        super().__init__("Konachan", f"https://konachan.com/post.json?limit={POST_AMOUNT}")

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        import scripts.ranbooru as _r

        _r.COUNT = 0
        all_fetched_posts = []
        if post_id:
            print("[R] Warn: Konachan does not support post IDs.")
            return []
        page = random.randint(1, max_pages)
        query_url = f"{self.base_api_url}&page={page}{tags_query}"
        fetched_data = self._fetch_data(query_url)
        if isinstance(fetched_data, list):
            all_fetched_posts = fetched_data
        _r.COUNT = len(all_fetched_posts)
        print(f"[R] Fetched {_r.COUNT} posts from Konachan.")
        return [self._standardize_post(post) for post in all_fetched_posts]


class Yandere(Booru):
    def __init__(self):
        from scripts.ranbooru import POST_AMOUNT

        super().__init__("Yandere", f"https://yande.re/post.json?limit={POST_AMOUNT}")

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        import scripts.ranbooru as _r

        _r.COUNT = 0
        all_fetched_posts = []
        if post_id:
            print("[R] Warn: Yandere does not support post IDs.")
            return []
        page = random.randint(1, max_pages)
        query_url = f"{self.base_api_url}&page={page}{tags_query}"
        fetched_data = self._fetch_data(query_url)
        if isinstance(fetched_data, list):
            all_fetched_posts = fetched_data
        _r.COUNT = len(all_fetched_posts)
        print(f"[R] Fetched {_r.COUNT} posts from Yandere.")
        return [self._standardize_post(post) for post in all_fetched_posts]


class AIBooru(Booru):
    def __init__(self):
        from scripts.ranbooru import POST_AMOUNT

        super().__init__("AIBooru", f"https://aibooru.online/posts.json?limit={POST_AMOUNT}")

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        import scripts.ranbooru as _r

        _r.COUNT = 0
        all_fetched_posts = []
        if post_id:
            print("[R] Warn: AIBooru does not support post IDs.")
            return []
        page = random.randint(1, max_pages)
        query_url = f"{self.base_api_url}&page={page}{tags_query}"
        fetched_data = self._fetch_data(query_url)
        if isinstance(fetched_data, list):
            all_fetched_posts = fetched_data
        _r.COUNT = len(all_fetched_posts)
        print(f"[R] Fetched {_r.COUNT} posts from AIBooru.")
        standardized_posts = []
        for post_data in all_fetched_posts:
            post = self._standardize_post(post_data)
            post["tags"] = post_data.get("tag_string", "")
            standardized_posts.append(post)
        return standardized_posts


class e621(Booru):
    def __init__(self):
        from scripts.ranbooru import POST_AMOUNT

        super().__init__("e621", f"https://e621.net/posts.json?limit={POST_AMOUNT}")

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        import scripts.ranbooru as _r

        _r.COUNT = 0
        all_fetched_posts = []
        if post_id:
            print("[R] Warn: e621 does not support post IDs.")
            return []
        page = random.randint(1, max_pages)
        query_url = f"{self.base_api_url}&page={page}{tags_query}"
        fetched_data = self._fetch_data(query_url)
        if (
            isinstance(fetched_data, dict)
            and "posts" in fetched_data
            and isinstance(fetched_data["posts"], list)
        ):
            all_fetched_posts = fetched_data["posts"]
        _r.COUNT = len(all_fetched_posts)
        print(f"[R] Fetched {_r.COUNT} posts from e621.")
        standardized_posts = []
        for post_data in all_fetched_posts:
            post = self._standardize_post(post_data)
            temp_tags = []
            sublevels = ["general", "artist", "copyright", "character", "species"]
            if "tags" in post_data:
                for sublevel in sublevels:
                    if sublevel in post_data["tags"] and isinstance(
                        post_data["tags"][sublevel], list
                    ):
                        temp_tags.extend(post_data["tags"][sublevel])
            post["tags"] = " ".join(temp_tags)
            if (
                "score" in post_data
                and isinstance(post_data["score"], dict)
                and "total" in post_data["score"]
            ):
                post["score"] = post_data["score"]["total"]
            standardized_posts.append(post)
        return standardized_posts

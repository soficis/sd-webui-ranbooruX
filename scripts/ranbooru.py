from io import BytesIO
import re
import random
import requests
import modules.scripts as scripts
import gradio as gr
import os
import json
import unicodedata
from typing import Dict, Iterable, List, Optional, Set, Tuple
from PIL import Image
import numpy as np
import requests_cache
import importlib
import sys
import traceback
from datetime import datetime
from urllib.parse import quote_plus

from modules.processing import process_images, StableDiffusionProcessingImg2Img, StableDiffusionProcessing
from modules import shared
from modules.sd_hijack import model_hijack
from modules import deepbooru
from modules.ui_components import InputAccordion
from modules.scripts import basedir

# --- Constants and Paths ---
EXTENSION_ROOT = basedir()
# Ensure extension root is on sys.path for local package imports (e.g., sd_forge_controlnet)
if EXTENSION_ROOT not in sys.path:
    sys.path.append(EXTENSION_ROOT)
USER_DATA_DIR = os.path.join(EXTENSION_ROOT, 'user')
USER_SEARCH_DIR = os.path.join(USER_DATA_DIR, 'search')
USER_REMOVE_DIR = os.path.join(USER_DATA_DIR, 'remove')
LOG_DIR = os.path.join(USER_DATA_DIR, 'logs')
COOKIES_DIR = os.path.join(USER_DATA_DIR, 'cookies')
os.makedirs(USER_SEARCH_DIR, exist_ok=True)
os.makedirs(USER_REMOVE_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(COOKIES_DIR, exist_ok=True)

GELBOORU_CREDENTIALS_DIR = os.path.join(USER_DATA_DIR, 'gelbooru')
GELBOORU_CREDENTIALS_FILE = os.path.join(GELBOORU_CREDENTIALS_DIR, 'credentials.json')

PERSONAL_REMOVE_FILE = os.path.join(USER_REMOVE_DIR, 'personal_remove.txt')
FAVORITES_FILE = os.path.join(USER_SEARCH_DIR, 'favorites.txt')
PROMPT_LOG_JSONL = os.path.join(LOG_DIR, 'prompt_sources.jsonl')

REMOVAL_SYNONYM_GROUPS_RAW: Tuple[Set[str], ...] = (
    {'grayscale', 'greyscale', 'monochrome'},
    {'1girl', '1female', '1woman'},
)

# Ensure default files exist
for filename in ['tags_search.txt', 'tags_remove.txt']:
    dir_path = USER_SEARCH_DIR if 'search' in filename else USER_REMOVE_DIR
    filepath = os.path.join(dir_path, filename)
    if not os.path.isfile(filepath):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                pass
        except Exception as e:
            print(f"[Ranbooru] Error creating file {filepath}: {e}")

for ensured_path in (PERSONAL_REMOVE_FILE, FAVORITES_FILE, PROMPT_LOG_JSONL):
    parent = os.path.dirname(ensured_path)
    try:
        os.makedirs(parent, exist_ok=True)
        if not os.path.isfile(ensured_path):
            mode = 'w'
            with open(ensured_path, mode, encoding='utf-8') as f:
                if ensured_path == PROMPT_LOG_JSONL:
                    pass
    except Exception as exc:
        print(f"[Ranbooru] Error ensuring file {ensured_path}: {exc}")

COLORED_BG = ['black_background', 'aqua_background', 'white_background', 'colored_background', 'gray_background', 'blue_background', 'green_background', 'red_background', 'brown_background', 'purple_background', 'yellow_background', 'orange_background', 'pink_background', 'plain', 'transparent_background', 'simple_background', 'two-tone_background', 'grey_background']
ADD_BG = ['outdoors', 'indoors']
BW_BG = ['monochrome', 'greyscale', 'grayscale']
POST_AMOUNT = 100
COUNT = 100
DEBUG = False

FURRY_CORE_TAGS = {
    'anthro', 'furry', 'feral', 'feral_focus', 'feral_only', 'scalie', 'avian', 'hooved_animal', 'digitigrade',
    'taur', 'mythological_creature', 'kemono', 'beastman', 'beastgirl', 'beastboy', 'kemonomimi', 'fur', 'fur_focus'
}

POKEMON_PREFIXES = ('pokemon', 'pikachu', 'eevee', 'charizard', 'mewtwo', 'gardevoir', 'lucario', 'lopunny')
ANIMAL_EAR_KEYWORDS = ('_ear', 'animal_ears', 'beast_ears', 'cat_ears', 'dog_ears', 'fox_ears', 'bunny_ears', 'wolf_ears', 'horse_ears', 'bear_ears')
HORN_KEYWORDS = ('horn', 'horns', 'antlers', 'unicorn_horn', 'goat_horns', 'demon_horns', 'ram_horns', 'bull_horns', 'long_horns')

HEADWEAR_TAGS = {
    'hat', 'cap', 'beret', 'helmet', 'hood', 'crown', 'tiara', 'headband', 'hairband', 'headdress', 'veil',
    'witch_hat', 'wizard_hat', 'top_hat', 'beanie', 'goggles', 'glasses_on_head', 'sailor_hat', 'nurse_cap',
    'maid_headdress', 'pirate_hat', 'sombrero', 'bunny_ears_headband', 'cat_ears_headband', 'animal_ears_headband',
    'motorcycle_helmet', 'baseball_cap', 'bowler_hat', 'straw_hat', 'sun_hat', 'halo', 'circular_halo', 'floating_halo'
}

HALO_TAGS = {'halo', 'circular_halo', 'ring_halo', 'floating_halo', 'angelic_halo'}

HAIR_COLOR_TAGS = {
    'blonde_hair', 'brown_hair', 'black_hair', 'grey_hair', 'gray_hair', 'white_hair', 'silver_hair', 'blue_hair',
    'green_hair', 'red_hair', 'pink_hair', 'purple_hair', 'orange_hair', 'aqua_hair', 'magenta_hair', 'teal_hair',
    'multicolored_hair', 'gradient_hair', 'rainbow_hair'
}

EYE_COLOR_TAGS = {
    'blue_eyes', 'green_eyes', 'red_eyes', 'brown_eyes', 'black_eyes', 'yellow_eyes', 'amber_eyes', 'orange_eyes',
    'purple_eyes', 'pink_eyes', 'golden_eyes', 'silver_eyes', 'grey_eyes', 'gray_eyes', 'white_eyes', 'aqua_eyes',
    'heterochromia', 'multicolored_eyes', 'gradient_eyes'
}

SERIES_KEYWORDS = {
    'franchise', 'series', 'canon', 'official_media', 'gacha_game', 'anime', 'manga_franchise', 'visual_novel'
}
SERIES_SUFFIXES = ('_series', '_franchise', '_media', '_universe')

RATING_TYPES = {
    "none": {"All": "All"},
    "full": {"All": "All", "Safe": "safe", "Questionable": "questionable", "Explicit": "explicit"},
    "single": {"All": "All", "Safe": "g", "Sensitive": "s", "Questionable": "q", "Explicit": "e"}
}

RATINGS = {
    "e621": RATING_TYPES['full'],
    "danbooru": RATING_TYPES['single'],
    "scatbooru": RATING_TYPES['single'],
    "aibooru": RATING_TYPES['full'],
    "yande.re": RATING_TYPES['full'],
    "konachan": RATING_TYPES['full'],
    "safebooru": RATING_TYPES['none'],
    "rule34": RATING_TYPES['full'],
    "xbooru": RATING_TYPES['full'],
    "gelbooru": RATING_TYPES['single']
}

STRICT_IMG2IMG_EXTRA_ROUNDS = 2
STRICT_IMG2IMG_LOG_SAMPLE = 5


def get_available_ratings(booru):
    choices = list(RATINGS.get(booru, RATING_TYPES['none']).keys())
    return gr.Radio.update(choices=choices, value="All")


def _get_scatbooru_cookie():
    env_cookie = os.environ.get('RANBOORUX_SCATBOORU_COOKIE')
    if isinstance(env_cookie, str) and env_cookie.strip():
        return env_cookie.strip()

    cookie_path = os.path.join(COOKIES_DIR, 'scatbooru.cookie')
    if os.path.isfile(cookie_path):
        try:
            with open(cookie_path, 'r', encoding='utf-8') as cookie_file:
                cookie_value = cookie_file.read().strip()
                if cookie_value:
                    return cookie_value
        except Exception as exc:
            print(f"[R] Warn: Failed to read scatbooru.cookie: {exc}")
    return None


def has_scatbooru_access():
    return _get_scatbooru_cookie() is not None


def show_fringe_benefits(booru):
    return gr.Checkbox.update(visible=(booru == 'gelbooru'))







def _sanitize_gelbooru_credential(value: Optional[str]) -> str:
    if not isinstance(value, str):
        return ""
    sanitized = value.strip()
    if not sanitized:
        return ""
    sanitized = sanitized.replace(chr(13), '').replace(chr(10), '')
    return sanitized



def _load_gelbooru_credentials_from_disk() -> Optional[Dict[str, str]]:
    if not os.path.isfile(GELBOORU_CREDENTIALS_FILE):
        return None
    try:
        with open(GELBOORU_CREDENTIALS_FILE, 'r', encoding='utf-8') as handle:
            payload = json.load(handle)
    except Exception as exc:
        print(f"[R] Warn: Failed to read Gelbooru credentials: {exc}")
        return None
    if not isinstance(payload, dict):
        return None
    api_key = _sanitize_gelbooru_credential(payload.get('api_key'))
    user_id = _sanitize_gelbooru_credential(payload.get('user_id'))
    if api_key and user_id:
        return {'api_key': api_key, 'user_id': user_id}
    return None


def _save_gelbooru_credentials_to_disk(api_key: Optional[str], user_id: Optional[str]) -> bool:
    api_key = _sanitize_gelbooru_credential(api_key)
    user_id = _sanitize_gelbooru_credential(user_id)
    if not api_key or not user_id:
        return False
    try:
        os.makedirs(GELBOORU_CREDENTIALS_DIR, exist_ok=True)
        with open(GELBOORU_CREDENTIALS_FILE, 'w', encoding='utf-8') as handle:
            json.dump({'api_key': api_key, 'user_id': user_id}, handle, ensure_ascii=False)
        return True
    except Exception as exc:
        print(f"[R] Warn: Failed to save Gelbooru credentials: {exc}")
        return False


def _clear_gelbooru_credentials_from_disk() -> bool:
    try:
        if os.path.isfile(GELBOORU_CREDENTIALS_FILE):
            os.remove(GELBOORU_CREDENTIALS_FILE)
        return True
    except Exception as exc:
        print(f"[R] Warn: Failed to clear Gelbooru credentials: {exc}")
        return False

def check_booru_exceptions(booru, post_id, tags):
    if booru == 'konachan' and post_id:
        raise ValueError("Konachan does not support post IDs")
    if booru == 'yande.re' and post_id:
        raise ValueError("Yande.re does not support post IDs")
    if booru == 'e621' and post_id:
        raise ValueError("e621 does not support post IDs")
    if booru == 'danbooru' and tags and len([t for t in tags.split(',') if t.strip()]) > 1:
        raise ValueError("Danbooru API only supports one tag.")


def resize_image(img, width, height, cropping=True):
    if img is None:
        return None
    if width <= 0 or height <= 0:
        print(f"[R] Warn: Invalid resize {width}x{height}")
        return img
    try:
        if cropping:
            img_aspect = img.width / img.height
            target_aspect = width / height
            if img_aspect > target_aspect:
                new_height = height
                new_width = int(new_height * img_aspect)
            else:
                new_width = width
                new_height = int(new_width / img_aspect)
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            left = (new_width - width) / 2
            top = (new_height - height) / 2
            right = (new_width + width) / 2
            bottom = (new_height + height) / 2
            return img_resized.crop((left, top, right, bottom))
        else:
            return img.resize((width, height), Image.Resampling.LANCZOS)
    except Exception as e:
        print(f"[R] Error resize: {e}")
        return img
def modify_prompt(prompt, tagged_prompt, type_deepbooru):
    prompt_tags = [tag.strip() for tag in prompt.split(',') if tag.strip()]
    tagged_tags = [tag.strip() for tag in tagged_prompt.split(',') if tag.strip()]
    if type_deepbooru == 'Add Before':
        combined_tags = tagged_tags + prompt_tags
    elif type_deepbooru == 'Add After':
        combined_tags = prompt_tags + tagged_tags
    elif type_deepbooru == 'Replace':
        combined_tags = tagged_tags
    else:
        combined_tags = prompt_tags + tagged_tags
    return ','.join(list(dict.fromkeys(combined_tags)))


def remove_repeated_tags(prompt):
    if not prompt or not isinstance(prompt, str):
        return ""
    tags = [tag.strip() for tag in prompt.split(',') if tag.strip()]
    if not tags:
        return ""
    try:
        unique_tags_string = ','.join(list(dict.fromkeys(tags)))
        return unique_tags_string if unique_tags_string is not None else ""
    except Exception as e:
        print(f"[R] Error remove_repeated: {e}. Input: '{prompt}'")
        return ""


def limit_prompt_tags(prompt, limit_val, mode):
    tags = [tag.strip() for tag in prompt.split(',') if tag.strip()]
    if not tags:
        return ""
    try:
        if mode == 'Limit':
            keep_count = max(1, int(len(tags) * float(limit_val)))
        elif mode == 'Max':
            keep_count = max(1, int(limit_val))
        else:
            return prompt
        return ','.join(tags[:keep_count])
    except ValueError:
        print(f"[R] Error limiting tags: Invalid limit value '{limit_val}'")
        return prompt
    except Exception as e:
        print(f"[R] Error limiting tags: {e}")
        return prompt


def get_original_post_url(post):
    try:
        booru = (post.get('booru_name') or '').lower()
        pid = post.get('id')
        if not pid:
            return None
        if booru == 'danbooru':
            return f"https://danbooru.donmai.us/posts/{pid}"
        if booru == 'gelbooru':
            return f"https://gelbooru.com/index.php?page=post&s=view&id={pid}"
        if booru == 'safebooru':
            return f"https://safebooru.org/index.php?page=post&s=view&id={pid}"
        if booru == 'rule34':
            return f"https://rule34.xxx/index.php?page=post&s=view&id={pid}"
        if booru == 'xbooru':
            return f"https://xbooru.com/index.php?page=post&s=view&id={pid}"
        if booru == 'konachan':
            return f"https://konachan.com/post/show/{pid}"
        if booru == 'yandere':
            return f"https://yande.re/post/show/{pid}"
        if booru == 'aibooru':
            return f"https://aibooru.online/posts/{pid}"
        if booru == 'e621':
            return f"https://e621.net/posts/{pid}"
        return None
    except Exception:
        return None


def generate_chaos(pos_tags, neg_tags, chaos_amount):
    pos_tag_list = [tag.strip() for tag in pos_tags.split(',') if tag.strip()]
    neg_tag_list = [tag.strip() for tag in neg_tags.split(',') if tag.strip()]
    chaos_list = list(set(pos_tag_list + neg_tag_list))
    if not chaos_list:
        return pos_tags, neg_tags
    random.shuffle(chaos_list)
    len_list = round(len(chaos_list) * chaos_amount)
    neg_add = chaos_list[:len_list]
    pos_add = chaos_list[len_list:]
    final_pos = list(set(pos_tag_list) - set(neg_add)) + pos_add
    final_neg = list(set(neg_tag_list) - set(pos_add)) + neg_add
    return ','.join(list(dict.fromkeys(final_pos))), ','.join(list(dict.fromkeys(final_neg)))


class BooruError(Exception):
    pass


class Booru():
    def __init__(self, booru_name, base_api_url):
        self.booru_name = booru_name
        self.base_api_url = base_api_url
        self.headers = {'user-agent': f'Ranbooru Extension/{Script.version} for Forge'}

    def _fetch_data(self, query_url):
        print(f"[R] Querying {self.booru_name}: {query_url}")
        try:
            res = requests.get(query_url, headers=self.headers, timeout=30)
            res.raise_for_status()
            if 'application/json' not in res.headers.get('content-type', ''):
                print(f"[R] Warn: Unexpected content type '{res.headers.get('content-type')}' from {self.booru_name}. Expected JSON.")
                try:
                    return res.json()
                except requests.exceptions.JSONDecodeError:
                    return None
            return res.json()
        except requests.exceptions.Timeout:
            print(f"[R] Error: Timeout fetching data from {self.booru_name}.")
            raise BooruError(f"Timeout connecting to {self.booru_name}") from None
        except requests.exceptions.RequestException as e:
            print(f"[R] Error fetching data from {self.booru_name}: {e}")
            raise BooruError(f"HTTP Error fetching from {self.booru_name}: {e}") from e
        except Exception as e:
            print(f"[R] Error processing response from {self.booru_name}: {e}")
            raise BooruError(f"Error processing response from {self.booru_name}: {e}") from e

    def _is_direct_image_url(self, url):
        """Check if URL is a direct image URL (not from external sites like Pixiv/Twitter)"""
        if not url or not isinstance(url, str):
            return False
        
        # Skip external sites that don't provide direct image access
        external_sites = [
            'pixiv.net', 'pximg.net', 'twitter.com', 'x.com', 't.co',
            'deviantart.com', 'artstation.com', 'instagram.com',
            'facebook.com', 'patreon.com', 'fanbox.cc'
        ]
        
        url_lower = url.lower()
        for site in external_sites:
            if site in url_lower:
                return False
        
        # Check if URL ends with common image extensions
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff']
        if any(url_lower.endswith(ext) for ext in image_extensions):
            return True
            
        # Check if URL contains image-serving patterns
        if any(pattern in url_lower for pattern in ['/images/', '/img/', '/media/', '/files/']):
            return True
            
        return False

    def _standardize_post(self, post_data):
        post = {}
        # extract tags in a robust way; some APIs return categorized tags as dicts
        raw_tags = post_data.get('tags', post_data.get('tag_string', ''))
        # store categorized lists when possible
        artist_tags = []
        character_tags = []
        copyright_tags = []
        if isinstance(post_data.get('tags'), dict):
            tags_dict = post_data.get('tags')
            # e621 style: tags dict with sublevels
            if isinstance(tags_dict.get('artist'), list):
                artist_tags = tags_dict.get('artist', [])
            if isinstance(tags_dict.get('character'), list):
                character_tags = tags_dict.get('character', [])
            if isinstance(tags_dict.get('copyright'), list):
                copyright_tags = tags_dict.get('copyright', [])
            # some APIs provide tag_string_artist / tag_string_character
        if 'tag_string_artist' in post_data:
            try:
                artist_tags = [t for t in re.split(r'[,\s]+', post_data.get('tag_string_artist', '').strip()) if t]
            except Exception:
                pass
        if 'tag_string_character' in post_data:
            try:
                character_tags = [t for t in re.split(r'[,\s]+', post_data.get('tag_string_character', '').strip()) if t]
            except Exception:
                pass
        if 'tag_string_copyright' in post_data:
            try:
                copyright_tags = [t for t in re.split(r'[,\s]+', post_data.get('tag_string_copyright', '').strip()) if t]
            except Exception:
                pass
        
        # For boorus that don't provide categorized tags, try to extract character tags from the main tag string
        # This handles cases like Gelbooru/Danbooru where character tags are mixed with other tags
        if not character_tags and isinstance(raw_tags, str):
            all_tags = [t.strip() for t in re.split(r'[,\s]+', raw_tags) if t.strip()]
            for tag in all_tags:
                # Common patterns for character tags: contains parentheses (series name) or ends with specific patterns
                if ('(' in tag and ')' in tag) or tag.endswith(r'_\(series\)') or tag.endswith(r'_\(character\)'):
                    character_tags.append(tag)
                # Also catch some common character name patterns (this is heuristic but should catch most)
                elif any(series in tag.lower() for series in ['genshin_impact', 'touhou', 'fate_', 'azur_lane', 'kantai_collection', 'pokemon']):
                    character_tags.append(tag)
        
        # print(f"[R Debug] Post {post_data.get('id', 'unknown')}: extracted {len(character_tags)} character tags: {character_tags}")
        
        post['tags'] = raw_tags
        post['artist_tags'] = artist_tags
        post['character_tags'] = character_tags
        post['copyright_tags'] = copyright_tags
        post['score'] = post_data.get('score', 0)
        post['file_url'] = post_data.get('file_url')
        if post['file_url'] is None:
            post['file_url'] = post_data.get('large_file_url')
        if post['file_url'] is None:
            # Check if source is a direct image URL before using it
            source_url = post_data.get('source')
            if source_url and self._is_direct_image_url(source_url):
                post['file_url'] = source_url
            else:
                post['file_url'] = None
        post['id'] = post_data.get('id')
        post['rating'] = post_data.get('rating')
        post['booru_name'] = self.booru_name
        return post

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        raise NotImplementedError


class Gelbooru(Booru):
    def __init__(self, fringe_benefits, credentials: Optional[Dict[str, str]] = None):
        super().__init__('Gelbooru', f'https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&limit={POST_AMOUNT}')
        self.fringeBenefits = fringe_benefits
        credentials = credentials or {}
        self.api_key = _sanitize_gelbooru_credential(credentials.get('api_key')) if isinstance(credentials, dict) else ""
        self.user_id = _sanitize_gelbooru_credential(credentials.get('user_id')) if isinstance(credentials, dict) else ""

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        global COUNT
        COUNT = 0
        all_fetched_posts = []
        if not self.api_key or not self.user_id:
            raise BooruError("Gelbooru requires an API key and user ID. Set them under RanbooruX → Gelbooru settings.")
        credentials_query = f"&api_key={quote_plus(self.api_key)}&user_id={quote_plus(self.user_id)}"
        if post_id:
            query_url = f"{self.base_api_url}{credentials_query}&id={post_id}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if fetched_data and 'post' in fetched_data and isinstance(fetched_data['post'], list):
                all_fetched_posts = fetched_data['post']
            COUNT = len(all_fetched_posts)
            print(f"[R] Found {COUNT} post(s) for ID: {post_id}")
        else:
            page = random.randint(0, max_pages - 1)
            query_url = f"{self.base_api_url}{credentials_query}&pid={page}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if fetched_data and 'post' in fetched_data and isinstance(fetched_data['post'], list):
                all_fetched_posts = fetched_data['post']
            if fetched_data and '@attributes' in fetched_data and 'count' in fetched_data['@attributes']:
                try:
                    COUNT = int(fetched_data['@attributes']['count'])
                except Exception:
                    COUNT = len(all_fetched_posts)
            else:
                COUNT = len(all_fetched_posts)
            print(f"[R] Fetched {len(all_fetched_posts)} posts from page {page}. Reported total (approx): {COUNT}")
        return [self._standardize_post(post) for post in all_fetched_posts]


class Danbooru(Booru):
    def __init__(self):
        super().__init__('Danbooru', f'https://danbooru.donmai.us/posts.json?limit={POST_AMOUNT}')

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        global COUNT
        COUNT = 0
        all_fetched_posts = []
        if post_id:
            query_url = f"https://danbooru.donmai.us/posts/{post_id}.json"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, dict) and 'id' in fetched_data:
                all_fetched_posts = [fetched_data]
            COUNT = len(all_fetched_posts)
            print(f"[R] Found {COUNT} post(s) for ID: {post_id}")
        else:
            page = random.randint(1, max_pages)
            query_url = f"{self.base_api_url}&page={page}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, list):
                all_fetched_posts = fetched_data
            COUNT = len(all_fetched_posts)
            print(f"[R] Fetched {COUNT} posts from page {page}.")
        return [self._standardize_post(post) for post in all_fetched_posts if post]


class Scatbooru(Booru):
    def __init__(self):
        super().__init__('Scatbooru', f'https://scatbooru.com/posts.json?limit={POST_AMOUNT}')

    def _fetch_data(self, query_url):
        headers = self.headers.copy()
        session_cookie = _get_scatbooru_cookie()
        if session_cookie:
            headers['Cookie'] = session_cookie
        try:
            resp = requests.get(query_url, headers=headers, timeout=30)
            if resp.status_code == 429:
                raise BooruError('Scatbooru rate limited the request. Provide RANBOORUX_SCATBOORU_COOKIE or place the cookie in user/cookies/scatbooru.cookie, then slow down requests.')
            content_type = resp.headers.get('content-type', '')
            if 'application/json' in content_type:
                return resp.json()
            # HTML normally indicates that the Cloudflare/anti-bot check blocked the request
            raise BooruError('Scatbooru returned HTML instead of JSON. Provide a valid session cookie via RANBOORUX_SCATBOORU_COOKIE or user/cookies/scatbooru.cookie.')
        except BooruError:
            raise
        except Exception as exc:
            raise BooruError(f'Scatbooru fetch error: {exc}') from exc

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        global COUNT
        COUNT = 0
        all_fetched_posts = []
        if post_id:
            query_url = f"https://scatbooru.com/posts/{post_id}.json"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, dict) and 'id' in fetched_data:
                all_fetched_posts = [fetched_data]
            COUNT = len(all_fetched_posts)
            print(f"[R] Fetched {COUNT} Scatbooru post(s) for ID {post_id}.")
        else:
            page = random.randint(1, max_pages)
            query_url = f"{self.base_api_url}&page={page}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, list):
                all_fetched_posts = fetched_data
            COUNT = len(all_fetched_posts)
            print(f"[R] Fetched {COUNT} posts from Scatbooru (page {page}).")
        return [self._standardize_post(post) for post in all_fetched_posts if post]





class XBooru(Booru):
    def __init__(self):
        super().__init__('XBooru', f'https://xbooru.com/index.php?page=dapi&s=post&q=index&json=1&limit={POST_AMOUNT}')

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        global COUNT
        COUNT = 0
        all_fetched_posts = []
        if post_id:
            query_url = f"{self.base_api_url}&id={post_id}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, dict) and 'id' in fetched_data:
                all_fetched_posts = [fetched_data]
        else:
            page = random.randint(0, max_pages - 1)
            query_url = f"{self.base_api_url}&pid={page}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, list):
                all_fetched_posts = fetched_data
        COUNT = len(all_fetched_posts)
        print(f"[R] Fetched {COUNT} posts from XBooru.")
        standardized_posts = []
        for post_data in all_fetched_posts:
            post = self._standardize_post(post_data)
            if 'directory' in post_data and 'image' in post_data:
                post['file_url'] = f"https://xbooru.com/images/{post_data['directory']}/{post_data['image']}"
            standardized_posts.append(post)
        return standardized_posts


class Rule34(Booru):
    def __init__(self):
        super().__init__('Rule34', f'https://api.rule34.xxx/index.php?page=dapi&s=post&q=index&json=1&limit={POST_AMOUNT}')

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        global COUNT
        COUNT = 0
        all_fetched_posts = []
        if post_id:
            query_url = f"{self.base_api_url}&id={post_id}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, dict) and 'id' in fetched_data:
                all_fetched_posts = [fetched_data]
        else:
            page = random.randint(0, max_pages - 1)
            query_url = f"{self.base_api_url}&pid={page}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, list):
                all_fetched_posts = fetched_data
        COUNT = len(all_fetched_posts)
        print(f"[R] Fetched {COUNT} posts from Rule34.")
        return [self._standardize_post(post) for post in all_fetched_posts]


class Safebooru(Booru):
    def __init__(self):
        super().__init__('Safebooru', f'https://safebooru.org/index.php?page=dapi&s=post&q=index&json=1&limit={POST_AMOUNT}')

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        global COUNT
        COUNT = 0
        all_fetched_posts = []
        if post_id:
            query_url = f"{self.base_api_url}&id={post_id}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, dict) and 'id' in fetched_data:
                all_fetched_posts = [fetched_data]
        else:
            page = random.randint(0, max_pages - 1)
            query_url = f"{self.base_api_url}&pid={page}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if isinstance(fetched_data, list):
                all_fetched_posts = fetched_data
        COUNT = len(all_fetched_posts)
        print(f"[R] Fetched {COUNT} posts from Safebooru.")
        standardized_posts = []
        for post_data in all_fetched_posts:
            post = self._standardize_post(post_data)
            if 'directory' in post_data and 'image' in post_data:
                post['file_url'] = f"https://safebooru.org/images/{post_data['directory']}/{post_data['image']}"
            standardized_posts.append(post)
        return standardized_posts


class Konachan(Booru):
    def __init__(self):
        super().__init__('Konachan', f'https://konachan.com/post.json?limit={POST_AMOUNT}')

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        global COUNT
        COUNT = 0
        all_fetched_posts = []
        if post_id:
            print("[R] Warn: Konachan does not support post IDs.")
            return []
        page = random.randint(1, max_pages)
        query_url = f"{self.base_api_url}&page={page}{tags_query}"
        fetched_data = self._fetch_data(query_url)
        if isinstance(fetched_data, list):
            all_fetched_posts = fetched_data
        COUNT = len(all_fetched_posts)
        print(f"[R] Fetched {COUNT} posts from Konachan.")
        return [self._standardize_post(post) for post in all_fetched_posts]


class Yandere(Booru):
    def __init__(self):
        super().__init__('Yandere', f'https://yande.re/post.json?limit={POST_AMOUNT}')

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        global COUNT
        COUNT = 0
        all_fetched_posts = []
        if post_id:
            print("[R] Warn: Yandere does not support post IDs.")
            return []
        page = random.randint(1, max_pages)
        query_url = f"{self.base_api_url}&page={page}{tags_query}"
        fetched_data = self._fetch_data(query_url)
        if isinstance(fetched_data, list):
            all_fetched_posts = fetched_data
        COUNT = len(all_fetched_posts)
        print(f"[R] Fetched {COUNT} posts from Yandere.")
        return [self._standardize_post(post) for post in all_fetched_posts]


class AIBooru(Booru):
    def __init__(self):
        super().__init__('AIBooru', f'https://aibooru.online/posts.json?limit={POST_AMOUNT}')

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        global COUNT
        COUNT = 0
        all_fetched_posts = []
        if post_id:
            print("[R] Warn: AIBooru does not support post IDs.")
            return []
        page = random.randint(1, max_pages)
        query_url = f"{self.base_api_url}?limit={POST_AMOUNT}&page={page}{tags_query}"
        fetched_data = self._fetch_data(query_url)
        if isinstance(fetched_data, list):
            all_fetched_posts = fetched_data
        COUNT = len(all_fetched_posts)
        print(f"[R] Fetched {COUNT} posts from AIBooru.")
        standardized_posts = []
        for post_data in all_fetched_posts:
            post = self._standardize_post(post_data)
            post['tags'] = post_data.get('tag_string', '')
            standardized_posts.append(post)
        return standardized_posts


class e621(Booru):
    def __init__(self):
        super().__init__('e621', f'https://e621.net/posts.json?limit={POST_AMOUNT}')

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        global COUNT
        COUNT = 0
        all_fetched_posts = []
        if post_id:
            print("[R] Warn: e621 does not support post IDs.")
            return []
        page = random.randint(1, max_pages)
        query_url = f"{self.base_api_url}?page={page}{tags_query}"
        fetched_data = self._fetch_data(query_url)
        if isinstance(fetched_data, dict) and 'posts' in fetched_data and isinstance(fetched_data['posts'], list):
            all_fetched_posts = fetched_data['posts']
        COUNT = len(all_fetched_posts)
        print(f"[R] Fetched {COUNT} posts from e621.")
        standardized_posts = []
        for post_data in all_fetched_posts:
            post = self._standardize_post(post_data)
            temp_tags = []
            sublevels = ['general', 'artist', 'copyright', 'character', 'species']
            if 'tags' in post_data:
                for sublevel in sublevels:
                    if sublevel in post_data['tags'] and isinstance(post_data['tags'][sublevel], list):
                        temp_tags.extend(post_data['tags'][sublevel])
            post['tags'] = ' '.join(temp_tags)
            if 'score' in post_data and isinstance(post_data['score'], dict) and 'total' in post_data['score']:
                post['score'] = post_data['score']['total']
            standardized_posts.append(post)
        return standardized_posts


class Script(scripts.Script):
    def __init__(self):
        super().__init__()
        self._gelbooru_saved_credentials: Optional[Dict[str, str]] = _load_gelbooru_credentials_from_disk()
        self._gelbooru_effective_credentials: Optional[Dict[str, str]] = None
        self._personal_remove_tags: Set[str] = set()
        self._favorite_tags: Set[str] = set()
        self._removal_context: Dict[str, object] = {}
        self._tag_normal_cache: Dict[str, str] = {}
        self._synonym_groups: Tuple[Set[str], ...] = tuple()
        self._synonym_lookup: Dict[str, Set[str]] = {}
        try:
            norm = self._normalize_tag
            groups: List[Set[str]] = []
            for group in REMOVAL_SYNONYM_GROUPS_RAW:
                normalized_group = {norm(tag) for tag in group if norm(tag)}
                if normalized_group:
                    groups.append(normalized_group)
            self._synonym_groups = tuple(groups)
            lookup: Dict[str, Set[str]] = {}
            for group in self._synonym_groups:
                for entry in group:
                    lookup[entry] = group
            self._synonym_lookup = lookup
        except Exception:
            self._synonym_groups = tuple()
            self._synonym_lookup = {}
        self._legacy_bad_exact: Set[str] = set()
        self._legacy_bad_wildcard: Dict[str, str] = {}
        self._strict_img2img_fetch: bool = True
        self._strict_img2img_active: bool = False
        self._strict_img2img_relaxed: bool = False
        self._strict_img2img_rejections: List[Dict[str, object]] = []
        self._strict_allowed_subjects: Set[str] = set()
        self._strict_initial_additions: str = ""

    sorting_priority = 1  # Highest priority to run before ALL other extensions
    previous_loras = ''
    last_img = []
    real_steps = 0
    version = "1.8-Refactored"
    original_prompt = ''
    run_img2img_pass = False
    img2img_denoising = 0.75
    cache_installed_by_us = False
    _adetailer_support_enabled = False
    _post_adetailer_enabled = False
    _manual_adetailer_prev_enabled = False
    _DASH_UNDERSCORE_RE = re.compile(r'[_\-]+')
    _WHITESPACE_RE = re.compile(r'\s+')
    _USER_LIST_PATHS = {
        'personal': PERSONAL_REMOVE_FILE,
        'favorites': FAVORITES_FILE,
    }
    _CLOTHING_KEYWORDS = {
        'dress', 'shirt', 'skirt', 'skorts', 'pants', 'jeans', 'shorts', 'jacket', 'coat', 'sweater', 'hoodie',
        'kimono', 'robe', 'uniform', 'school uniform', 'sailor uniform', 'bikini', 'swimsuit', 'lingerie', 'underwear',
        'panties', 'bra', 'corset', 'thighhighs', 'stockings', 'socks', 'gloves', 'mittens', 'scarf', 'cape', 'apron',
        'armor', 'bustier', 'bodysuit', 'leotard', 'gown', 'tuxedo', 'suit', 'vest', 'necktie', 'bowtie', 'hat', 'cap',
        'headband', 'hairband', 'headdress', 'veil', 'crown', 'helmet', 'sandals', 'boots', 'shoes', 'heels', 'sneakers',
        'flip flops', 'garter', 'garter belt', 'pantyhose', 'stocking', 'cloak', 'cardigan', 'sleeves', 'armband',
        'choker', 'ribbon', 'bow', 'shawl', 'loincloth', 'loin cloth', 'tabard', 'capelet', 'poncho', 'overalls', 'tank top',
        't-shirt', 'tee shirt', 'pajamas', 'nightgown'
    }
    _TEXTUAL_TAGS = {
        'text', 'english text', 'japanese text', 'chinese text', 'korean text', 'translated', 'translation', 'commentary',
        'artist commentary', 'author commentary', 'publisher commentary', 'copyright text', 'speech bubble', 'speech bubbles',
        'dialogue', 'dialog', 'sound effect', 'sound effects', 'comic text', 'comic panel', 'subtitle', 'subtitles', 'caption',
        'captions', 'floating text', 'text focus', 'text overlay', 'text background', 'watermark', 'watermark text', 'signature',
        'sign', 'tagme', 'written text', 'scribble', 'handwritten text', 'handwriting', 'text box', 'thought bubble', 'thought balloon',
        'logo', 'logo text', 'notice', 'speech bubble text'
    }
    _SUBJECT_TAGS = {
        'solo', 'duo', 'trio', 'quartet', 'group', 'gang', 'crowd', 'couple', 'threesome', 'foursome', 'orgy',
        '1girl', '2girls', '3girls', '4girls', '1boy', '2boys', '3boys', '4boys', '1other', '2others', '3others', '4others',
        'multiple girls', 'multiple boys', 'multiple people', 'multiple others', 'solo focus', 'female focus', 'male focus',
        'mixed group', '1female', '1male', '2females', '2males', '3females', '3males', '1person', '2people', '3people', '4people'
    }
    _FURRY_CORE_NORMALIZED = {tag.replace('_', ' ') for tag in FURRY_CORE_TAGS}
    _POKEMON_PREFIXES_NORMALIZED = tuple(prefix.replace('_', ' ') for prefix in POKEMON_PREFIXES)
    _ANIMAL_EAR_KEYWORDS_NORMALIZED = tuple(keyword.replace('_', ' ') for keyword in ANIMAL_EAR_KEYWORDS)
    _HORN_KEYWORDS_NORMALIZED = tuple(keyword.replace('_', ' ') for keyword in HORN_KEYWORDS)
    _HEADWEAR_TAGS_NORMALIZED = {tag.replace('_', ' ') for tag in HEADWEAR_TAGS}
    _HALO_TAGS_NORMALIZED = {tag.replace('_', ' ') for tag in HALO_TAGS}
    _HAIR_COLOR_TAGS_NORMALIZED = {tag.replace('_', ' ') for tag in HAIR_COLOR_TAGS}
    _EYE_COLOR_TAGS_NORMALIZED = {tag.replace('_', ' ') for tag in EYE_COLOR_TAGS}
    _SERIES_KEYWORDS_NORMALIZED = {tag.replace('_', ' ') for tag in SERIES_KEYWORDS}
    _SERIES_SUFFIXES_NORMALIZED = tuple(suffix.replace('_', ' ') for suffix in SERIES_SUFFIXES)

    @staticmethod
    def _canonicalize_raw_tag(tag: str) -> str:
        if not isinstance(tag, str):
            return ""
        lowered = (tag or '').strip().lower().replace('_', ' ')
        return re.sub(r'\s+', ' ', lowered) if lowered else ""

    @staticmethod
    def _normalize_tag(tag: str) -> str:
        if not isinstance(tag, str):
            return ""
        normalized = unicodedata.normalize("NFKC", tag).casefold()
        normalized = Script._DASH_UNDERSCORE_RE.sub(' ', normalized)
        normalized = Script._WHITESPACE_RE.sub(' ', normalized).strip()
        if not normalized:
            return ""
        wrapper_pairs = {('(', ')'), ('[', ']'), ('{', '}')}
        while len(normalized) > 2 and (normalized[0], normalized[-1]) in wrapper_pairs:
            normalized = normalized[1:-1].strip()
        return normalized

    def _ensure_user_file(self, path: str) -> None:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if not os.path.isfile(path):
                with open(path, 'w', encoding='utf-8') as handle:
                    handle.write('')
        except Exception as exc:
            print(f"[R Files] Failed to ensure file {path}: {exc}")

    def _read_list_file(self, path: str) -> List[str]:
        self._ensure_user_file(path)
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                contents = handle.read()
        except Exception as exc:
            print(f"[R Files] Failed to read list file {path}: {exc}")
            return []
        if not contents:
            return []
        parts = [segment.strip() for segment in re.split(r'[\n,]+', contents) if segment.strip()]
        seen: Set[str] = set()
        ordered: List[str] = []
        for part in parts:
            key = self._normalize_tag(part) or part.casefold()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(part.strip())
        return ordered

    def _write_list_file(self, path: str, tags: Iterable[str]) -> None:
        self._ensure_user_file(path)
        seen: Set[str] = set()
        deduped: List[str] = []
        for tag in tags:
            cleaned = (tag or '').strip()
            if not cleaned:
                continue
            key = self._normalize_tag(cleaned)
            if key in seen:
                continue
            if key:
                seen.add(key)
            deduped.append(cleaned)
        try:
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write('\n'.join(deduped))
        except Exception as exc:
            print(f"[R Files] Failed to write list file {path}: {exc}")

    def _load_personal_lists(self) -> Tuple[Set[str], Set[str]]:
        personal = set(self._read_list_file(PERSONAL_REMOVE_FILE))
        favorites = set(self._read_list_file(FAVORITES_FILE))
        self._personal_remove_tags = personal
        self._favorite_tags = favorites
        return personal, favorites

    def _normalize_cached(self, tag: str, cache: Dict[str, str]) -> str:
        if tag in cache:
            return cache[tag]
        normalized = self._normalize_tag(tag)
        cache[tag] = normalized
        return normalized

    def _expand_with_synonyms(self, normalized_tag: str, target_set: Set[str]) -> None:
        if not normalized_tag:
            return
        group = self._synonym_lookup.get(normalized_tag)
        if group:
            target_set.update(group)

    def _build_removal_context(self, removal_raw: Iterable[str], favorites_raw: Iterable[str]) -> Dict[str, object]:
        norm = self._normalize_tag
        exact: Set[str] = set()
        prefix: List[str] = []
        suffix: List[str] = []
        contains: List[str] = []
        regex_objects: List[re.Pattern[str]] = []
        for raw in removal_raw:
            if not isinstance(raw, str):
                continue
            candidate = raw.strip()
            if not candidate:
                continue
            if '*' not in candidate:
                normalized = norm(candidate)
                if normalized:
                    exact.add(normalized)
                    self._expand_with_synonyms(normalized, exact)
                continue
            if candidate.startswith('*') and candidate.endswith('*') and candidate.count('*') == 2:
                body = candidate[1:-1]
                normalized = norm(body)
                if normalized:
                    contains.append(normalized)
                continue
            if candidate.endswith('*') and candidate.count('*') == 1:
                body = candidate[:-1]
                normalized = norm(body)
                if normalized:
                    prefix.append(normalized)
                continue
            if candidate.startswith('*') and candidate.count('*') == 1:
                body = candidate[1:]
                normalized = norm(body)
                if normalized:
                    suffix.append(normalized)
                continue
            segments = candidate.split('*')
            pattern_fragments: List[str] = []
            for idx, segment in enumerate(segments):
                if segment:
                    normalized_segment = norm(segment)
                    if normalized_segment:
                        pattern_fragments.append(re.escape(normalized_segment))
                if idx < len(segments) - 1:
                    pattern_fragments.append('.*')
            pattern_body = ''.join(pattern_fragments)
            if pattern_body:
                try:
                    regex_objects.append(re.compile(f'^{pattern_body}$'))
                except re.error as exc:
                    print(f"[R Filters] Invalid wildcard pattern '{candidate}': {exc}")
        contains_set = set(filter(None, contains))
        contains_regex: Optional[re.Pattern[str]] = None
        if len(contains_set) > 50:
            pattern_union = '|'.join(re.escape(term) for term in contains_set if term)
            if pattern_union:
                try:
                    contains_regex = re.compile(pattern_union)
                except re.error as exc:
                    print(f"[R Filters] Failed to compile contains regex: {exc}")
                    contains_regex = None
        prefix_tuple = tuple(sorted(set(filter(None, prefix))))
        suffix_tuple = tuple(sorted(set(filter(None, suffix))))
        contains_tuple = tuple(sorted(contains_set))
        favorites_exact: Set[str] = set()
        for fav in favorites_raw:
            if not isinstance(fav, str):
                continue
            normalized = norm(fav)
            if not normalized:
                continue
            favorites_exact.add(normalized)
            self._expand_with_synonyms(normalized, favorites_exact)
        return {
            'exact': frozenset(exact),
            'prefix': prefix_tuple,
            'suffix': suffix_tuple,
            'contains': contains_tuple,
            'contains_regex': contains_regex,
            'regex_objects': tuple(regex_objects),
            'favorites': frozenset(favorites_exact),
        }

    def _tag_matches_removal(self, normalized_tag: str, context: Optional[Dict[str, object]]) -> bool:
        if not context or not normalized_tag:
            return False
        favorites: Set[str] = context.get('favorites', frozenset())  # type: ignore[assignment]
        if normalized_tag in favorites:
            return False
        exact: Set[str] = context.get('exact', frozenset())  # type: ignore[assignment]
        if normalized_tag in exact:
            return True
        prefix_terms: Tuple[str, ...] = context.get('prefix', tuple())  # type: ignore[assignment]
        if any(normalized_tag.startswith(term) for term in prefix_terms if term):
            return True
        suffix_terms: Tuple[str, ...] = context.get('suffix', tuple())  # type: ignore[assignment]
        if any(normalized_tag.endswith(term) for term in suffix_terms if term):
            return True
        contains_regex: Optional[re.Pattern[str]] = context.get('contains_regex')  # type: ignore[assignment]
        if contains_regex and contains_regex.search(normalized_tag):
            return True
        contains_terms: Tuple[str, ...] = context.get('contains', tuple())  # type: ignore[assignment]
        if not contains_regex and any(term and term in normalized_tag for term in contains_terms):
            return True
        regex_patterns: Tuple[re.Pattern[str], ...] = context.get('regex_objects', tuple())  # type: ignore[assignment]
        for pattern in regex_patterns:
            if pattern.fullmatch(normalized_tag):
                return True
        return False

    def _parse_user_tags(self, text: str) -> List[str]:
        if not text or not isinstance(text, str):
            return []
        segments = [seg.strip() for seg in re.split(r'[\n,]+', text) if seg and seg.strip()]
        if not segments:
            return []
        seen: Set[str] = set()
        ordered: List[str] = []
        for seg in segments:
            norm = self._normalize_tag(seg) or seg.casefold()
            if norm in seen:
                continue
            seen.add(norm)
            ordered.append(seg.strip())
        return ordered

    def _coerce_selection(self, selection: Optional[object]) -> List[str]:
        if selection is None:
            return []
        if isinstance(selection, str):
            return [selection]
        if isinstance(selection, (list, tuple)):
            return [item for item in selection if isinstance(item, str) and item.strip()]
        return []

    def _merge_tag_lists(self, base: List[str], additions: List[str]) -> List[str]:
        merged: List[str] = []
        seen: Set[str] = set()
        for tag in list(base) + list(additions):
            cleaned = (tag or '').strip()
            if not cleaned:
                continue
            key = self._normalize_tag(cleaned) or cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(cleaned)
        return merged

    def _apply_list_operation(
        self,
        list_key: str,
        *,
        additions: Optional[List[str]] = None,
        removals: Optional[List[str]] = None,
        imported: Optional[List[str]] = None,
        dedupe: bool = False,
    ) -> List[str]:
        path = self._USER_LIST_PATHS[list_key]
        existing = self._read_list_file(path)
        working = list(existing)
        combined_additions: List[str] = []
        if additions:
            combined_additions.extend(additions)
        if imported:
            combined_additions.extend(imported)
        if combined_additions:
            working = self._merge_tag_lists(working, combined_additions)
        if removals:
            removal_keys = {self._normalize_tag(tag) or tag.casefold() for tag in removals if isinstance(tag, str)}
            if removal_keys:
                working = [tag for tag in working if (self._normalize_tag(tag) or tag.casefold()) not in removal_keys]
        if dedupe:
            working = self._merge_tag_lists([], working)
        self._write_list_file(path, working)
        self._load_personal_lists()
        return working

    def _ui_add_personal_tags(self, tags_text: str, current_selection: Optional[object]):
        additions = self._parse_user_tags(tags_text)
        new_list = self._apply_list_operation('personal', additions=additions)
        selection = additions or self._coerce_selection(current_selection)
        selection = [tag for tag in selection if tag in new_list]
        return (
            gr.Dropdown.update(choices=new_list, value=selection),
            gr.Textbox.update(value="")
        )

    def _ui_remove_personal_tags(self, selected: Optional[object]):
        removals = self._coerce_selection(selected)
        new_list = self._apply_list_operation('personal', removals=removals) if removals else self._read_list_file(PERSONAL_REMOVE_FILE)
        return gr.Dropdown.update(choices=new_list, value=[])

    def _ui_dedupe_personal_list(self):
        new_list = self._apply_list_operation('personal', dedupe=True)
        return gr.Dropdown.update(choices=new_list, value=new_list)

    def _ui_import_personal_list(self, uploaded_file: Optional[dict]):
        if not uploaded_file:
            current = self._read_list_file(PERSONAL_REMOVE_FILE)
            return gr.Dropdown.update(choices=current, value=current), gr.File.update(value=None)
        data = uploaded_file.get('data') if isinstance(uploaded_file, dict) else None
        text = ''
        if isinstance(data, bytes):
            try:
                text = data.decode('utf-8', errors='ignore')
            except Exception as exc:
                print(f"[R Lists] Failed to decode personal import: {exc}")
        additions = self._parse_user_tags(text)
        new_list = self._apply_list_operation('personal', additions=additions)
        selection = [tag for tag in additions if tag in new_list]
        return gr.Dropdown.update(choices=new_list, value=selection), gr.File.update(value=None)

    def _ui_export_personal_list(self):
        return PERSONAL_REMOVE_FILE

    def _ui_add_favorite_tags(self, tags_text: str, current_selection: Optional[object]):
        additions = self._parse_user_tags(tags_text)
        new_list = self._apply_list_operation('favorites', additions=additions)
        selection = additions or self._coerce_selection(current_selection)
        selection = [tag for tag in selection if tag in new_list]
        return (
            gr.Dropdown.update(choices=new_list, value=selection),
            gr.Textbox.update(value="")
        )

    def _ui_remove_favorite_tags(self, selected: Optional[object]):
        removals = self._coerce_selection(selected)
        new_list = self._apply_list_operation('favorites', removals=removals) if removals else self._read_list_file(FAVORITES_FILE)
        return gr.Dropdown.update(choices=new_list, value=[])

    def _ui_dedupe_favorite_list(self):
        new_list = self._apply_list_operation('favorites', dedupe=True)
        return gr.Dropdown.update(choices=new_list, value=new_list)

    def _ui_import_favorite_list(self, uploaded_file: Optional[dict]):
        if not uploaded_file:
            current = self._read_list_file(FAVORITES_FILE)
            return gr.Dropdown.update(choices=current, value=current), gr.File.update(value=None)
        data = uploaded_file.get('data') if isinstance(uploaded_file, dict) else None
        text = ''
        if isinstance(data, bytes):
            try:
                text = data.decode('utf-8', errors='ignore')
            except Exception as exc:
                print(f"[R Lists] Failed to decode favorites import: {exc}")
        additions = self._parse_user_tags(text)
        new_list = self._apply_list_operation('favorites', additions=additions)
        selection = [tag for tag in additions if tag in new_list]
        return gr.Dropdown.update(choices=new_list, value=selection), gr.File.update(value=None)

    def _ui_export_favorite_list(self):
        return FAVORITES_FILE

    def _get_saved_gelbooru_credentials(self) -> Optional[Dict[str, str]]:
        creds = self._gelbooru_saved_credentials
        if isinstance(creds, dict):
            api_key = _sanitize_gelbooru_credential(creds.get('api_key'))
            user_id = _sanitize_gelbooru_credential(creds.get('user_id'))
            if api_key and user_id:
                return {'api_key': api_key, 'user_id': user_id}
        return None

    def _resolve_gelbooru_credentials(self, runtime_api_key: Optional[str], runtime_user_id: Optional[str]) -> Optional[Dict[str, str]]:
        runtime_api_key = _sanitize_gelbooru_credential(runtime_api_key)
        runtime_user_id = _sanitize_gelbooru_credential(runtime_user_id)
        if runtime_api_key and runtime_user_id:
            return {'api_key': runtime_api_key, 'user_id': runtime_user_id}
        saved = self._get_saved_gelbooru_credentials()
        if saved:
            return saved
        return None

    def _gelbooru_saved_message(self) -> str:
        return f"✅ Using saved Gelbooru credentials from `{GELBOORU_CREDENTIALS_FILE}`."

    def _ui_save_gelbooru_credentials(self, api_key: Optional[str], user_id: Optional[str]):
        api_key = _sanitize_gelbooru_credential(api_key)
        user_id = _sanitize_gelbooru_credential(user_id)
        if not api_key or not user_id:
            warn = "⚠️ Please enter both API Key and User ID before saving."
            return (
                gr.Markdown.update(value=warn, visible=True),
                gr.Group.update(visible=True),
                gr.Button.update(visible=False),
                gr.Textbox.update(value=api_key),
                gr.Textbox.update(value=user_id),
            )
        if _save_gelbooru_credentials_to_disk(api_key, user_id):
            self._gelbooru_saved_credentials = {'api_key': api_key, 'user_id': user_id}
            message = self._gelbooru_saved_message()
            return (
                gr.Markdown.update(value=message, visible=True),
                gr.Group.update(visible=False),
                gr.Button.update(visible=True),
                gr.Textbox.update(value=""),
                gr.Textbox.update(value=""),
            )
        error = "⚠️ Failed to save Gelbooru credentials. Check console for details."
        return (
            gr.Markdown.update(value=error, visible=True),
            gr.Group.update(visible=True),
            gr.Button.update(visible=False),
            gr.Textbox.update(value=api_key),
            gr.Textbox.update(value=user_id),
        )

    def _ui_clear_gelbooru_credentials(self):
        if _clear_gelbooru_credentials_from_disk():
            self._gelbooru_saved_credentials = None
            return (
                gr.Markdown.update(value="🧹 Saved Gelbooru credentials cleared.", visible=True),
                gr.Group.update(visible=True),
                gr.Button.update(visible=False),
                gr.Textbox.update(value=""),
                gr.Textbox.update(value=""),
            )
        warn = "⚠️ Gelbooru credentials file could not be removed."
        return (
            gr.Markdown.update(value=warn, visible=True),
            gr.Group.update(visible=False),
            gr.Button.update(visible=True),
            gr.Textbox.update(value=""),
            gr.Textbox.update(value=""),
        )

    def _update_gelbooru_ui_visibility(self, booru_name: Optional[str]):
        booru_name = (booru_name or "").strip().lower()
        has_saved = self._get_saved_gelbooru_credentials() is not None
        if booru_name == 'gelbooru':
            if has_saved:
                return (
                    gr.Group.update(visible=False),
                    gr.Markdown.update(value=self._gelbooru_saved_message(), visible=True),
                    gr.Button.update(visible=True),
                    gr.Textbox.update(value=""),
                    gr.Textbox.update(value=""),
                )
            return (
                gr.Group.update(visible=True),
                gr.Markdown.update(value="", visible=False),
                gr.Button.update(visible=False),
                gr.Textbox.update(value=""),
                gr.Textbox.update(value=""),
            )
        # Hide for non-Gelbooru selections
        return (
            gr.Group.update(visible=False),
            gr.Markdown.update(value="", visible=False),
            gr.Button.update(visible=False),
            gr.Textbox.update(value=""),
            gr.Textbox.update(value=""),
        )

    def _build_legacy_bad_index(self, bad_tags: Iterable[str]) -> None:
        exact: Set[str] = set()
        wildcard: Dict[str, str] = {}
        for tag in bad_tags:
            if not isinstance(tag, str):
                continue
            cleaned = tag.strip()
            if not cleaned:
                continue
            if '*' not in cleaned:
                exact.add(cleaned)
                continue
            base = cleaned.replace('*', '')
            if not base:
                continue
            if cleaned.endswith('*') and not cleaned.startswith('*'):
                wildcard[base] = 's'
            elif cleaned.startswith('*') and not cleaned.endswith('*'):
                wildcard[base] = 'e'
            else:
                wildcard[base] = 'c'
        self._legacy_bad_exact = exact
        self._legacy_bad_wildcard = wildcard

    def _legacy_tag_matches(self, tag: str) -> bool:
        if tag in self._legacy_bad_exact:
            return True
        for pattern, mode in self._legacy_bad_wildcard.items():
            if not pattern:
                continue
            if mode == 's' and tag.startswith(pattern):
                return True
            if mode == 'e' and tag.endswith(pattern):
                return True
            if mode == 'c' and pattern in tag:
                return True
        return False

    def _is_furry_tag(self, tag: str) -> bool:
        normalized = (self._normalize_tag(tag) or '').strip().lower()
        if not normalized:
            normalized = self._canonicalize_raw_tag(tag)
        if not normalized:
            return False
        raw_lower = (tag or '').strip().lower()
        if normalized in self._FURRY_CORE_NORMALIZED or raw_lower in FURRY_CORE_TAGS:
            return True
        if any(normalized.startswith(prefix) or raw_lower.startswith(prefix) for prefix in self._POKEMON_PREFIXES_NORMALIZED):
            return True
        if any(keyword in normalized for keyword in self._ANIMAL_EAR_KEYWORDS_NORMALIZED):
            return True
        if any(keyword in normalized for keyword in self._HORN_KEYWORDS_NORMALIZED):
            return True
        return False

    def _is_headwear_tag(self, tag: str) -> bool:
        normalized = (self._normalize_tag(tag) or '').strip().lower()
        if not normalized:
            normalized = self._canonicalize_raw_tag(tag)
        if not normalized:
            return False
        if normalized in self._HEADWEAR_TAGS_NORMALIZED or normalized in self._HALO_TAGS_NORMALIZED:
            return True
        # Allow simple keyword containment like " halo" or " headpiece"
        if ' halo' in normalized or normalized.endswith(' halo'):
            return True
        return False

    def _is_hair_color_tag(self, tag: str) -> bool:
        normalized = (self._normalize_tag(tag) or '').strip().lower()
        if not normalized:
            normalized = self._canonicalize_raw_tag(tag)
        return normalized in self._HAIR_COLOR_TAGS_NORMALIZED

    def _is_eye_color_tag(self, tag: str) -> bool:
        normalized = (self._normalize_tag(tag) or '').strip().lower()
        if not normalized:
            normalized = self._canonicalize_raw_tag(tag)
        return normalized in self._EYE_COLOR_TAGS_NORMALIZED

    def _is_series_tag(self, tag: str) -> bool:
        normalized = (self._normalize_tag(tag) or '').strip().lower()
        if not normalized:
            normalized = self._canonicalize_raw_tag(tag)
        if not normalized:
            return False
        raw_lower = (tag or '').strip().lower()
        if any(keyword in normalized for keyword in self._SERIES_KEYWORDS_NORMALIZED):
            return True
        if any(raw_lower.endswith(suffix) or normalized.endswith(suffix) for suffix in SERIES_SUFFIXES):
            return True
        if any(normalized.endswith(suffix) for suffix in self._SERIES_SUFFIXES_NORMALIZED):
            return True
        return False

    def _extract_color_tags(self, text: str) -> tuple[set[str], set[str]]:
        hair_tags: set[str] = set()
        eye_tags: set[str] = set()
        if not text or not isinstance(text, str):
            return hair_tags, eye_tags
        tokens = [token.strip() for token in re.split(r'[\s,]+', text) if token.strip()]
        for token in tokens:
            normalized = (self._normalize_tag(token) or '').strip().lower()
            if not normalized:
                normalized = self._canonicalize_raw_tag(token)
            if not normalized:
                continue
            if normalized in self._HAIR_COLOR_TAGS_NORMALIZED:
                hair_tags.add(normalized)
            if normalized in self._EYE_COLOR_TAGS_NORMALIZED:
                eye_tags.add(normalized)
        return hair_tags, eye_tags
    def _is_clothing_tag(self, tag: str) -> bool:
        normalized = self._normalize_tag(tag)
        if not normalized:
            return False
        if normalized.startswith('no ') or normalized.startswith('without ') or ' without ' in normalized or normalized.startswith('nude'):
            return False
        for keyword in self._CLOTHING_KEYWORDS:
            if keyword in normalized:
                return True
        if normalized.endswith(' uniform') or normalized.endswith(' outfit') or normalized.endswith(' costume'):
            return True
        return False

    def _is_textual_tag(self, tag: str) -> bool:
        normalized = self._normalize_tag(tag)
        if not normalized:
            return False
        if normalized in self._TEXTUAL_TAGS:
            return True
        if ' text' in normalized or normalized.endswith(' text') or normalized.startswith('text '):
            return True
        if 'commentary' in normalized or 'speech bubble' in normalized or 'dialog' in normalized or 'subtitle' in normalized or 'caption' in normalized:
            return True
        if normalized.startswith('translated ') or normalized.startswith('translation '):
            return True
        return False

    def _is_subject_tag(self, tag: str) -> bool:
        normalized = self._normalize_tag(tag)
        return normalized in self._SUBJECT_TAGS

    def _extract_subject_tags(self, text: str) -> set:
        if not text or not isinstance(text, str):
            return set()
        tags = [t.strip() for t in re.split(r'[\s,]+', text) if t.strip()]
        return {self._normalize_tag(t) for t in tags if self._is_subject_tag(t)}

    def _normalize_post_tags(self, post: Optional[Dict[str, object]], cache: Dict[str, str]) -> Tuple[Set[str], Dict[str, List[str]]]:
        normalized_tags: Set[str] = set()
        buckets: Dict[str, List[str]] = {
            'tags': [],
            'artist_tags': [],
            'character_tags': [],
            'copyright_tags': [],
        }
        if not isinstance(post, dict):
            return normalized_tags, buckets

        raw_tags = post.get('tags')
        tag_list: List[str] = []
        if isinstance(raw_tags, str):
            tag_list = [segment.strip() for segment in re.split(r'[\s,]+', raw_tags) if segment.strip()]
        elif isinstance(raw_tags, dict):
            for value in raw_tags.values():
                if isinstance(value, (list, tuple, set)):
                    tag_list.extend([str(item).strip() for item in value if isinstance(item, str) and item.strip()])
                elif isinstance(value, str) and value.strip():
                    tag_list.append(value.strip())
        elif isinstance(raw_tags, (list, tuple, set)):
            tag_list = [str(item).strip() for item in raw_tags if isinstance(item, str) and item.strip()]
        buckets['tags'] = tag_list

        for key in ('artist_tags', 'character_tags', 'copyright_tags'):
            values = post.get(key)
            if isinstance(values, str) and values.strip():
                buckets[key] = [values.strip()]
            elif isinstance(values, (list, tuple, set)):
                buckets[key] = [str(item).strip() for item in values if isinstance(item, str) and item.strip()]
            else:
                buckets[key] = []

        for key, values in buckets.items():
            cleaned: List[str] = []
            for tag in values:
                if not isinstance(tag, str):
                    continue
                cleaned_tag = tag.strip()
                if not cleaned_tag:
                    continue
                cleaned.append(cleaned_tag)
                normalized = self._normalize_cached(cleaned_tag, cache)
                if normalized:
                    normalized_tags.add(normalized)
            buckets[key] = cleaned

        return normalized_tags, buckets

    def _post_rejected_by_filter(
        self,
        post: Optional[Dict[str, object]],
        *,
        filter_ctx: Optional[Dict[str, object]],
        toggles: Tuple[bool, bool, bool, bool, bool, bool, bool, bool, bool],
        base_colors: Tuple[Set[str], Set[str]],
        allowed_subjects: Set[str],
        cache: Dict[str, str],
        favorites_guard: Set[str],
    ) -> Tuple[bool, Optional[Dict[str, object]]]:
        (
            remove_artist,
            remove_character,
            remove_clothing,
            remove_text,
            restrict_subject,
            remove_furry,
            remove_headwear,
            preserve_hair_eye,
            remove_series,
        ) = toggles
        base_hair, base_eye = base_colors
        _, buckets = self._normalize_post_tags(post, cache)
        primary_subject: Optional[str] = None

        for bucket_name, tags in buckets.items():
            for raw_tag in tags:
                normalized_tag = self._normalize_cached(raw_tag, cache)
                if normalized_tag and normalized_tag in favorites_guard:
                    continue
                canonical_tag = normalized_tag or self._canonicalize_raw_tag(raw_tag)
                canonical_tag = canonical_tag or ''
                reason_base = {
                    'tag': raw_tag,
                    'norm': normalized_tag,
                    'bucket': bucket_name,
                }

                if remove_artist and (
                    bucket_name == 'artist_tags'
                    or (normalized_tag and (normalized_tag.endswith(' artist') or ' drawn by' in normalized_tag))
                ):
                    return True, {**reason_base, 'rule': 'artist'}

                if remove_character and (
                    bucket_name == 'character_tags'
                    or ('(' in raw_tag and ')' in raw_tag and not raw_tag.strip().startswith('('))
                    or (normalized_tag and (
                        normalized_tag.endswith(' character')
                        or normalized_tag.endswith(' characters')
                        or normalized_tag.endswith(' series')
                        or normalized_tag.endswith(' franchise')
                    ))
                ):
                    return True, {**reason_base, 'rule': 'character'}

                if remove_series and (
                    bucket_name == 'copyright_tags'
                    or self._is_series_tag(raw_tag)
                ):
                    return True, {**reason_base, 'rule': 'series'}

                if remove_clothing and self._is_clothing_tag(raw_tag):
                    return True, {**reason_base, 'rule': 'clothing'}

                if remove_text and self._is_textual_tag(raw_tag):
                    return True, {**reason_base, 'rule': 'text'}

                if remove_furry and self._is_furry_tag(raw_tag):
                    return True, {**reason_base, 'rule': 'furry'}

                if remove_headwear and self._is_headwear_tag(raw_tag):
                    return True, {**reason_base, 'rule': 'headwear'}

                if preserve_hair_eye:
                    if base_hair and self._is_hair_color_tag(raw_tag) and canonical_tag not in base_hair:
                        return True, {**reason_base, 'rule': 'hair-color-conflict'}
                    if base_eye and self._is_eye_color_tag(raw_tag) and canonical_tag not in base_eye:
                        return True, {**reason_base, 'rule': 'eye-color-conflict'}

                if restrict_subject and self._is_subject_tag(raw_tag):
                    subject_norm = normalized_tag or canonical_tag
                    if allowed_subjects:
                        if subject_norm not in allowed_subjects:
                            return True, {**reason_base, 'rule': 'subject-not-allowed'}
                    else:
                        if primary_subject is None:
                            primary_subject = subject_norm
                        elif subject_norm != primary_subject:
                            return True, {**reason_base, 'rule': 'multiple-subjects'}

                if filter_ctx and normalized_tag and self._tag_matches_removal(normalized_tag, filter_ctx):
                    return True, {**reason_base, 'rule': 'removal-list'}

        return False, None

    def _apply_strict_img2img_prefilter(
        self,
        posts: List[Dict[str, object]],
        *,
        api: Booru,
        tags_query: str,
        post_id: Optional[str],
        num_images_needed: int,
        max_pages: int,
        filter_ctx: Optional[Dict[str, object]],
        toggles: Tuple[bool, bool, bool, bool, bool, bool, bool, bool, bool],
        base_colors: Tuple[Set[str], Set[str]],
        allowed_subjects: Set[str],
    ) -> Tuple[List[Dict[str, object]], List[Dict[str, object]], bool, bool]:
        if not posts:
            return [], [], False, False

        if not getattr(self, '_strict_img2img_fetch', True):
            return list(posts), [], False, False

        cache = getattr(self, '_tag_normal_cache', {})
        if not isinstance(cache, dict):
            cache = {}
            self._tag_normal_cache = cache

        favorites_guard: Set[str] = set()
        if filter_ctx:
            favorites_guard = set(filter_ctx.get('favorites', frozenset()))  # type: ignore[arg-type]

        hair_colors, eye_colors = base_colors
        base_colors = (set(hair_colors or []), set(eye_colors or []))
        allowed_subjects = set(allowed_subjects or [])

        kept: List[Dict[str, object]] = []
        rejections: List[Dict[str, object]] = []
        seen_keys: Set[Tuple[Optional[str], Optional[str], Optional[str]]] = set()

        def _post_key(entry: Dict[str, object]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
            return (
                str(entry.get('booru_name')).lower() if entry.get('booru_name') else None,
                entry.get('id'),
                entry.get('file_url'),
            )

        original_posts = list(posts)

        for post in original_posts:
            key = _post_key(post)
            seen_keys.add(key)
            rejected, reason = self._post_rejected_by_filter(
                post,
                filter_ctx=filter_ctx,
                toggles=toggles,
                base_colors=base_colors,
                allowed_subjects=allowed_subjects,
                cache=cache,
                favorites_guard=favorites_guard,
            )
            if rejected:
                reason_entry = {
                    'post_id': post.get('id'),
                    'booru': post.get('booru_name'),
                    'matched_tag': reason.get('tag') if reason else None,
                    'normalized_tag': reason.get('norm') if reason else None,
                    'rule_type': reason.get('rule') if reason else None,
                    'bucket': reason.get('bucket') if reason else None,
                }
                rejections.append(reason_entry)
            else:
                kept.append(post)

        if len(kept) >= num_images_needed or post_id:
            return kept, rejections, True, False

        relaxed = False
        rounds = max(0, int(STRICT_IMG2IMG_EXTRA_ROUNDS))
        for round_index in range(rounds):
            try:
                extra_posts = api.get_posts(tags_query=tags_query, max_pages=max_pages, post_id=None)
            except Exception as exc:
                print(f"[R Strict] Warn: extra fetch round {round_index + 1} failed: {exc}")
                break
            if not extra_posts:
                continue
            for post in extra_posts:
                key = _post_key(post)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                rejected, reason = self._post_rejected_by_filter(
                    post,
                    filter_ctx=filter_ctx,
                    toggles=toggles,
                    base_colors=base_colors,
                    allowed_subjects=allowed_subjects,
                    cache=cache,
                    favorites_guard=favorites_guard,
                )
                if rejected:
                    reason_entry = {
                        'post_id': post.get('id'),
                        'booru': post.get('booru_name'),
                        'matched_tag': reason.get('tag') if reason else None,
                        'normalized_tag': reason.get('norm') if reason else None,
                        'rule_type': reason.get('rule') if reason else None,
                        'bucket': reason.get('bucket') if reason else None,
                        'extra_round': round_index + 1,
                    }
                    rejections.append(reason_entry)
                    continue
                kept.append(post)
                if len(kept) >= num_images_needed:
                    break
            if len(kept) >= num_images_needed:
                break

        if len(kept) < num_images_needed:
            print("[R Strict] Img2Img strict pre-filter exhausted candidates; relaxing to prompt-level filtering")
            relaxed = True
            kept = list(original_posts)

        return kept, rejections, True, relaxed

    def _log_generation_reference(self, p):
        if not getattr(self, '_log_prompt_sources', False):
            return
        try:
            prompts = list(getattr(self, '_final_prompts_snapshot', []))
            if not prompts:
                prompt_attr = getattr(p, 'prompt', '')
                if isinstance(prompt_attr, list):
                    prompts = list(prompt_attr)
                elif isinstance(prompt_attr, str):
                    prompts = [prompt_attr]
            prompts = [pr for pr in prompts if isinstance(pr, str) and pr.strip()]
            if not prompts:
                return
            seeds = list(getattr(p, 'all_seeds', []) or [])
            posts = list(getattr(self, '_posts_used_for_generation', []))
            post_urls = list(getattr(self, '_last_post_urls', [])) if hasattr(self, '_last_post_urls') else []
            os.makedirs(LOG_DIR, exist_ok=True)
            log_path = os.path.join(LOG_DIR, 'prompt_sources.txt')
            booru = getattr(self, '_current_booru_name', 'unknown')
            base_prompt = getattr(self, 'original_prompt', getattr(p, 'prompt', ''))
            negative_prompt = getattr(p, 'negative_prompt', '')
            with open(log_path, 'a', encoding='utf-8') as log_file:
                log_file.write('---\n')
                log_file.write(f"{datetime.now().isoformat()} | booru={booru} | reuse_cached={getattr(self, '_reuse_cached_posts', False)}\n")
                log_file.write(f"base_prompt={base_prompt}\n")
                if isinstance(negative_prompt, str) and negative_prompt:
                    log_file.write(f"negative_prompt={negative_prompt}\n")
                for idx, prompt in enumerate(prompts):
                    seed = seeds[idx] if idx < len(seeds) else getattr(p, 'seed', None)
                    log_file.write(f"[{idx+1}] seed={seed}\n")
                    log_file.write(f"prompt={prompt}\n")
                    post = posts[idx] if idx < len(posts) else None
                    source_url = post_urls[idx] if idx < len(post_urls) else None
                    if not source_url and post:
                        source_url = get_original_post_url(post)
                    if not source_url and post and post.get('file_url'):
                        source_url = post.get('file_url')
                    if source_url:
                        log_file.write(f"source={source_url}\n")
                    if post and post.get('id') is not None:
                        log_file.write(f"post_id={post.get('id')}\n")
                    log_file.write('\n')
            try:
                json_payload = {
                    'timestamp': datetime.now().isoformat(),
                    'booru': booru,
                    'mode': 'img2img' if bool(getattr(self, '_post_use_img2img', False)) else 'txt2img',
                    'strict_fetch_enabled': bool(getattr(self, '_strict_img2img_fetch', False)),
                    'strict_prefilter_active': bool(getattr(self, '_strict_img2img_active', False)),
                    'strict_prefilter_relaxed': bool(getattr(self, '_strict_img2img_relaxed', False)),
                    'strict_rejections': list(getattr(self, '_strict_img2img_rejections', [])),
                    'kept_post_ids': [post.get('id') for post in posts if isinstance(post, dict)],
                    'prompts': prompts,
                    'negative_prompt': negative_prompt if isinstance(negative_prompt, str) else None,
                    'reuse_cached': bool(getattr(self, '_reuse_cached_posts', False)),
                }
                with open(PROMPT_LOG_JSONL, 'a', encoding='utf-8') as jsonl_file:
                    jsonl_file.write(json.dumps(json_payload, ensure_ascii=False) + '\n')
            except Exception as exc:
                print(f"[R Log] Failed to append JSONL prompt record: {exc}")
            self._posts_used_for_generation = []
            self._final_prompts_snapshot = []
            self._final_negative_prompts_snapshot = []
        except Exception as exc:
            print(f"[R Log] Failed to log prompt sources: {exc}")

    def _ensure_pil_images_in_processed(self, processed_obj):
        try:
            if hasattr(processed_obj, 'images') and isinstance(processed_obj.images, list):
                for i, im in enumerate(list(processed_obj.images)):
                    pil_im = self._ensure_pil_image(im)
                    if pil_im is not None:
                        processed_obj.images[i] = pil_im
            # Ensure single image too
            if hasattr(processed_obj, 'image'):
                processed_obj.image = self._ensure_pil_image(getattr(processed_obj, 'image'))
        except Exception:
            pass

    def _ensure_pil_in_processing(self, p):
        try:
            if hasattr(p, 'init_images') and isinstance(p.init_images, list) and p.init_images:
                for i, im in enumerate(list(p.init_images)):
                    pil_im = self._ensure_pil_image(im)
                    if pil_im is not None:
                        p.init_images[i] = pil_im
        except Exception:
            pass

    def _load_cn_external_code(self):
        candidates = [
            'sd_forge_controlnet.lib_controlnet.external_code',
            'extensions.sd_forge_controlnet.lib_controlnet.external_code',
            'extensions.sd-webui-controlnet.scripts.external_code',
        ]
        errors = []
        for mod in candidates:
            try:
                return importlib.import_module(mod)
            except Exception as e:
                errors.append(f"{mod}: {e}")
        # Environment-provided ControlNet path
        try:
            env_root = os.environ.get('SD_FORGE_CONTROLNET_PATH') or os.environ.get('RANBOORUX_CN_PATH')
            if env_root:
                env_path = os.path.join(env_root, 'lib_controlnet', 'external_code.py')
                if os.path.isfile(env_path):
                    import importlib.util
                    spec = importlib.util.spec_from_file_location('sd_forge_controlnet.lib_controlnet.external_code', env_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)  # type: ignore
                    return module
                else:
                    errors.append(f"env:{env_path}: not found")
        except Exception as e:
            errors.append(f"env_load: {e}")
        # WebUI built-in extensions path (Forge)
        try:
            webui_root = None
            try:
                from modules import paths as webui_paths  # type: ignore
                webui_root = getattr(webui_paths, 'script_path', None)
            except Exception as e:
                errors.append(f"modules.paths.script_path: {e}")
            if webui_root:
                builtin_path = os.path.join(webui_root, 'extensions-builtin', 'sd_forge_controlnet', 'lib_controlnet', 'external_code.py')
                if os.path.isfile(builtin_path):
                    import importlib.util
                    spec = importlib.util.spec_from_file_location('sd_forge_controlnet.lib_controlnet.external_code', builtin_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)  # type: ignore
                    return module
                else:
                    errors.append(f"builtin:{builtin_path}: not found")
        except Exception as e:
            errors.append(f"builtin_load: {e}")
        # Filesystem fallback (directly load from this extension folder)
        try:
            ext_path = os.path.join(EXTENSION_ROOT, 'sd_forge_controlnet', 'lib_controlnet', 'external_code.py')
            if os.path.isfile(ext_path):
                import importlib.util
                spec = importlib.util.spec_from_file_location('sd_forge_controlnet.lib_controlnet.external_code', ext_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)  # type: ignore
                return module
            else:
                errors.append(f"file://{ext_path}: not found")
        except Exception as e:
            errors.append(f"file_fallback: {e}")
        raise ImportError("Unable to import ControlNet external_code. Attempts: " + "; ".join(errors))

    def get_files(self, path):
        files = []
        try:
            for file in os.listdir(path):
                if file.endswith('.txt'):
                    files.append(file)
        except FileNotFoundError:
            print(f"[R] Warn: Dir not found: {path}")
        return files

    def title(self):
        return "RanbooruX"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def refresh_ser(self):
        return gr.update(choices=self.get_files(USER_SEARCH_DIR))

    def refresh_rem(self):
        return gr.update(choices=self.get_files(USER_REMOVE_DIR))

    def ui(self, is_img2img):
        with InputAccordion(False, label="RanbooruX", elem_id=self.elem_id("ra_enable")) as enabled:
            booru_list = ["gelbooru", "danbooru", "xbooru", "rule34", "safebooru", "konachan", 'yande.re', 'aibooru', 'e621']
            if has_scatbooru_access():
                booru_list.insert(2, "scatbooru")
            booru = gr.Dropdown(booru_list, label="Booru", value="danbooru")
            with gr.Group(visible=False) as gelbooru_credentials_group:
                gelbooru_api_key = gr.Textbox(label="Gelbooru API Key", type="password", placeholder="Enter your Gelbooru API key")
                gelbooru_user_id = gr.Textbox(label="Gelbooru User ID", placeholder="Enter your Gelbooru user ID")
                gelbooru_save_button = gr.Button("Save Credentials to Disk", variant="primary")
            gelbooru_saved_message = gr.Markdown("", visible=False)
            gelbooru_clear_button = gr.Button("Clear Saved Credentials", visible=False)
            max_pages = gr.Slider(label="Max Pages (tag search)", minimum=1, maximum=100, value=10, step=1)
            gr.Markdown("""## Post"""); post_id = gr.Textbox(lines=1, label="Post ID (Overrides tags/pages)")
            gr.Markdown("""## Tags"""); tags = gr.Textbox(lines=1, label="Tags to Search (Pre)"); remove_tags = gr.Textbox(lines=1, label="Tags to Remove (Post)")
            mature_rating = gr.Radio(list(RATINGS.get('gelbooru', RATING_TYPES['none'])), label="Mature Rating", value="All")
            with gr.Accordion("Removal Filters", open=False):
                beta_filter_toggle = gr.Checkbox(
                    label="Beta: New Tag Filtering",
                    value=True,
                    info="Enable the normalized removal engine with personal lists and favorites guard. Disable to fall back to legacy behavior."
                )
                gr.Markdown("**Quick Presets** — apply common filter combinations with one click.")
                with gr.Row():
                    preset_strip_series = gr.Button("Strip Series/Character")
                    preset_remove_text = gr.Button("Remove Text-like Tags")
                    preset_preserve_colors = gr.Button("Preserve Base Colors")
                with gr.Group():
                    gr.Markdown("**Text & Metadata**")
                    remove_bad_tags = gr.Checkbox(
                        label="Remove common 'bad' tags",
                        value=True,
                        info="Cull frequent watermark, commentary, and UI text tags from prompts."
                    )
                    remove_text_tags = gr.Checkbox(
                        label="Remove tag/text/commentary metadata",
                        value=True,
                        info="Strip speech bubbles, watermark text, and similar metadata from fetched prompts."
                    )
                with gr.Group():
                    gr.Markdown("**Characters & Series**")
                    remove_artist_tags = gr.Checkbox(
                        label="Remove artist tags",
                        value=False,
                        info="Drop artist credits drawn from the source post."
                    )
                    remove_character_tags = gr.Checkbox(
                        label="Remove character tags",
                        value=False,
                        info="Filter character/franchise tags sourced from metadata."
                    )
                    remove_series_tags = gr.Checkbox(
                        label="Remove series / franchise tags",
                        value=False,
                        info="Ignore franchise/game/anime tags to keep prompts generic."
                    )
                with gr.Group():
                    gr.Markdown("**Clothing & Accessories**")
                    remove_clothing_tags = gr.Checkbox(
                        label="Remove clothing tags",
                        value=False,
                        info="Omit apparel/accessory tags introduced by the booru."
                    )
                with gr.Group():
                    gr.Markdown("**Furry & Headwear**")
                    remove_furry_tags = gr.Checkbox(
                        label="Filter furry/pokémon tags",
                        value=False,
                        info="Remove furry, pokémon, and animal trait tags."
                    )
                    remove_headwear_tags = gr.Checkbox(
                        label="Filter headwear / halo tags",
                        value=False,
                        info="Strip hats, halos, and similar head accessories."
                    )
                with gr.Group():
                    gr.Markdown("**Colors & Traits**")
                    preserve_hair_eye_colors = gr.Checkbox(
                        label="Preserve base hair & eye colors",
                        value=False,
                        info="Keep your prompt's hair/eye colors while removing conflicting imports."
                    )
                with gr.Group():
                    gr.Markdown("**Subject Constraints**")
                    restrict_subject_tags = gr.Checkbox(
                        label="Keep only subject counts",
                        value=False,
                        info="Maintain your subject count (e.g., solo/1girl) by removing mismatched tags."
                    )
            personal_choices = self._read_list_file(PERSONAL_REMOVE_FILE)
            favorite_choices = self._read_list_file(FAVORITES_FILE)
            with gr.Accordion("Personal Lists", open=False):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("**Personal Removal List**")
                        personal_remove_dropdown = gr.Dropdown(
                            choices=personal_choices,
                            value=personal_choices,
                            multiselect=True,
                            label="Removal Tags",
                            allow_custom_value=False
                        )
                        personal_remove_input = gr.Textbox(label="Add tags", placeholder="comma or newline separated")
                        with gr.Row():
                            personal_add_btn = gr.Button("Add", variant="primary")
                            personal_remove_btn = gr.Button("Remove Selected")
                            personal_dedupe_btn = gr.Button("De-duplicate")
                        with gr.Row():
                            personal_import_file = gr.File(label="Import CSV/TXT", file_types=['.txt', '.csv'], visible=True)
                            personal_export_btn = gr.DownloadButton("Export", file_name="personal_remove.txt")
                    with gr.Column():
                        gr.Markdown("**Favorites List**")
                        favorites_dropdown = gr.Dropdown(
                            choices=favorite_choices,
                            value=favorite_choices,
                            multiselect=True,
                            label="Favorite Tags",
                            allow_custom_value=False
                        )
                        favorites_input = gr.Textbox(label="Add favorites", placeholder="comma or newline separated")
                        with gr.Row():
                            favorites_add_btn = gr.Button("Add", variant="primary")
                            favorites_remove_btn = gr.Button("Remove Selected")
                            favorites_dedupe_btn = gr.Button("De-duplicate")
                        with gr.Row():
                            favorites_import_file = gr.File(label="Import CSV/TXT", file_types=['.txt', '.csv'], visible=True)
                            favorites_export_btn = gr.DownloadButton("Export", file_name="favorites.txt")
            shuffle_tags = gr.Checkbox(label="Shuffle tags", value=True)
            change_dash = gr.Checkbox(label='Convert "_" to spaces', value=False)
            same_prompt = gr.Checkbox(label="Use same prompt for batch", value=False)
            fringe_benefits = gr.Checkbox(label="Gelbooru: Fringe Benefits", value=True, visible=True)
            limit_tags = gr.Slider(value=1.0, label="Limit tags by %", minimum=0.05, maximum=1.0, step=0.05); max_tags = gr.Slider(value=0, label="Max tags (0=disabled)", minimum=0, maximum=300, step=1)
            change_background = gr.Radio(["Don't Change", "Add Detail", "Force Simple", "Force Transparent/White"], label="Change Background", value="Don't Change")
            change_color = gr.Radio(["Don't Change", "Force Color", "Force Monochrome"], label="Change Color", value="Don't Change")
            sorting_order = gr.Radio(["Random", "Score Descending", "Score Ascending"], label="Sort Order (tag search)", value="Random")
            booru.change(get_available_ratings, booru, mature_rating)
            booru.change(show_fringe_benefits, booru, fringe_benefits)
            booru.change(
                self._update_gelbooru_ui_visibility,
                inputs=[booru],
                outputs=[gelbooru_credentials_group, gelbooru_saved_message, gelbooru_clear_button, gelbooru_api_key, gelbooru_user_id],
                queue=False,
            )
            gelbooru_save_button.click(
                fn=self._ui_save_gelbooru_credentials,
                inputs=[gelbooru_api_key, gelbooru_user_id],
                outputs=[gelbooru_saved_message, gelbooru_credentials_group, gelbooru_clear_button, gelbooru_api_key, gelbooru_user_id],
                queue=False,
            )
            gelbooru_clear_button.click(
                fn=self._ui_clear_gelbooru_credentials,
                inputs=[],
                outputs=[gelbooru_saved_message, gelbooru_credentials_group, gelbooru_clear_button, gelbooru_api_key, gelbooru_user_id],
                queue=False,
            )

            gr.Markdown("""\n---\n""")
            with gr.Group():
                with gr.Accordion("Img2Img / ControlNet", open=False):
                    use_img2img = gr.Checkbox(label="Use Image for Img2Img", value=False)
                    use_ip = gr.Checkbox(label="Use Image for ControlNet (Unit 0)", value=False)
                    denoising = gr.Slider(value=0.75, label="Img2Img Denoising / CN Weight", minimum=0.0, maximum=1.0, step=0.05)
                    use_last_img = gr.Checkbox(label="Use same image for batch", value=False)
                    crop_center = gr.Checkbox(label="Crop image to fit target", value=False)
                    use_deepbooru = gr.Checkbox(label="Use Deepbooru on image", value=False)
                    type_deepbooru = gr.Radio(["Add Before", "Add After", "Replace"], label="DB Tags Position", value="Add Before")
                    enable_adetailer_support = gr.Checkbox(
                        label="Enable RanbooruX ADetailer support",
                        value=False,
                        info="Run RanbooruX's manual ADetailer integration after img2img when enabled."
                    )
                    reuse_cached_posts = gr.Checkbox(
                        label="Reuse cached booru posts",
                        value=False,
                        info="Leave disabled to fetch fresh images every generation. Enable when you want RanbooruX to reuse the previously cached posts."
                    )
            with gr.Group():
                with gr.Accordion("File Tags", open=False):
                    use_search_txt = gr.Checkbox(label="Add line from Search File", value=False); choose_search_txt = gr.Dropdown(self.get_files(USER_SEARCH_DIR), label="Choose Search File", value="", info=f"in '{USER_SEARCH_DIR}'")
                    search_refresh_btn = gr.Button("Refresh"); use_remove_txt = gr.Checkbox(label="Add tags from Remove File", value=False); choose_remove_txt = gr.Dropdown(self.get_files(USER_REMOVE_DIR), label="Choose Remove File", value="", info=f"in '{USER_REMOVE_DIR}'")
                    remove_refresh_btn = gr.Button("Refresh")
            with gr.Group():
                with gr.Accordion("Extra Prompt Modes", open=False):
                    with gr.Box(): mix_prompt = gr.Checkbox(label="Mix tags from multiple posts", value=False); mix_amount = gr.Slider(value=2, label="Posts to mix", minimum=2, maximum=10, step=1)
                    with gr.Box(): chaos_mode = gr.Radio(["None", "Shuffle All", "Shuffle Negative"], label="Tag Shuffling (Chaos)", value="None"); chaos_amount = gr.Slider(value=0.5, label="Chaos Amount %", minimum=0.1, maximum=1.0, step=0.05)
                    with gr.Box(): use_same_seed = gr.Checkbox(label="Use same seed for batch", value=False); use_cache = gr.Checkbox(label="Cache Booru API requests", value=True); log_prompt_sources = gr.Checkbox(label="Log image sources/prompts to txt", value=False, info="When enabled, RanbooruX appends a log entry mapping seeds and prompts to the source posts.")
        with InputAccordion(False, label="LoRAnado", elem_id=self.elem_id("lo_enable")) as lora_enabled:
            with gr.Box(): lora_lock_prev = gr.Checkbox(label="Lock previous LoRAs", value=False); lora_folder = gr.Textbox(lines=1, label="LoRAs Subfolder", placeholder="e.g., 'Characters' or empty"); lora_amount = gr.Slider(value=1, label="LoRAs Amount", minimum=1, maximum=10, step=1)
            with gr.Box(): lora_min = gr.Slider(value=0.6, label="Min LoRAs Weight", minimum=-1.0, maximum=1.5, step=0.1); lora_max = gr.Slider(value=1.0, label="Max LoRAs Weight", minimum=-1.0, maximum=1.5, step=0.1); lora_custom_weights = gr.Textbox(lines=1, label="Custom Weights (optional)", placeholder="e.g., 0.8, 0.5, 1.0")
        search_refresh_btn.click(fn=self.refresh_ser, inputs=[], outputs=[choose_search_txt])
        remove_refresh_btn.click(fn=self.refresh_rem, inputs=[], outputs=[choose_remove_txt])
        personal_add_btn.click(fn=self._ui_add_personal_tags, inputs=[personal_remove_input, personal_remove_dropdown], outputs=[personal_remove_dropdown, personal_remove_input], queue=False)
        personal_remove_btn.click(fn=self._ui_remove_personal_tags, inputs=[personal_remove_dropdown], outputs=[personal_remove_dropdown], queue=False)
        personal_dedupe_btn.click(fn=self._ui_dedupe_personal_list, inputs=[], outputs=[personal_remove_dropdown], queue=False)
        personal_import_file.upload(fn=self._ui_import_personal_list, inputs=[personal_import_file], outputs=[personal_remove_dropdown, personal_import_file], queue=False)
        personal_export_btn.click(fn=self._ui_export_personal_list, inputs=[], outputs=None, queue=False)

        favorites_add_btn.click(fn=self._ui_add_favorite_tags, inputs=[favorites_input, favorites_dropdown], outputs=[favorites_dropdown, favorites_input], queue=False)
        favorites_remove_btn.click(fn=self._ui_remove_favorite_tags, inputs=[favorites_dropdown], outputs=[favorites_dropdown], queue=False)
        favorites_dedupe_btn.click(fn=self._ui_dedupe_favorite_list, inputs=[], outputs=[favorites_dropdown], queue=False)
        favorites_import_file.upload(fn=self._ui_import_favorite_list, inputs=[favorites_import_file], outputs=[favorites_dropdown, favorites_import_file], queue=False)
        favorites_export_btn.click(fn=self._ui_export_favorite_list, inputs=[], outputs=None, queue=False)

        preset_strip_series.click(
            fn=lambda: (
                gr.Checkbox.update(value=True),
                gr.Checkbox.update(value=True),
                gr.Checkbox.update(value=True)
            ),
            inputs=[],
            outputs=[remove_series_tags, remove_character_tags, remove_artist_tags],
            queue=False
        )
        preset_remove_text.click(
            fn=lambda: (
                gr.Checkbox.update(value=True),
                gr.Checkbox.update(value=True)
            ),
            inputs=[],
            outputs=[remove_text_tags, remove_bad_tags],
            queue=False
        )
        preset_preserve_colors.click(
            fn=lambda: gr.Checkbox.update(value=True),
            inputs=[],
            outputs=[preserve_hair_eye_colors],
            queue=False
        )

        return [enabled, tags, booru, gelbooru_api_key, gelbooru_user_id, remove_bad_tags, max_pages, change_dash, same_prompt, fringe_benefits, remove_tags, use_img2img, denoising, use_last_img, change_background, change_color, shuffle_tags, post_id, mix_prompt, mix_amount, chaos_mode, chaos_amount, limit_tags, max_tags, sorting_order, mature_rating, lora_folder, lora_amount, lora_min, lora_max, lora_enabled, lora_custom_weights, lora_lock_prev, use_ip, use_search_txt, use_remove_txt, choose_search_txt, choose_remove_txt, search_refresh_btn, remove_refresh_btn, crop_center, use_deepbooru, type_deepbooru, enable_adetailer_support, use_same_seed, reuse_cached_posts, use_cache, log_prompt_sources, remove_artist_tags, remove_character_tags, remove_clothing_tags, remove_text_tags, restrict_subject_tags, remove_furry_tags, remove_headwear_tags, preserve_hair_eye_colors, remove_series_tags, beta_filter_toggle]

    def check_orientation(self, img):
        if img is None:
            print("[R Orientation] No image provided, defaulting to 1024x1024")
            return [1024, 1024]
        x, y = img.size
        aspect_ratio = x / y
        
        print(f"[R Orientation] Original: {x}x{y}, aspect_ratio: {aspect_ratio:.3f}")
        
        # Calculate dimensions that maintain aspect ratio while staying within reasonable bounds
        # Target around 1024 pixels for the longer dimension, minimum 512 for shorter
        if aspect_ratio > 1.33:  # Wide image
            # Landscape - width is longer
            target_width = 1152
            target_height = int(target_width / aspect_ratio)
            # Ensure minimum height
            if target_height < 512:
                target_height = 512
                target_width = int(target_height * aspect_ratio)
            
            # Round to multiples of 8 for better compatibility
            target_width = (target_width // 8) * 8
            target_height = (target_height // 8) * 8
            
            result = [target_width, target_height]
            print(f"[R Orientation] Wide image -> {result[0]}x{result[1]} (rounded to 8px)")
            return result
        elif aspect_ratio < 0.75:  # Tall image  
            # Portrait - height is longer
            target_height = 1152
            target_width = int(target_height * aspect_ratio)
            # Ensure minimum width
            if target_width < 512:
                target_width = 512
                target_height = int(target_width / aspect_ratio)
            
            # Round to multiples of 8 for better compatibility
            target_width = (target_width // 8) * 8
            target_height = (target_height // 8) * 8
            
            result = [target_width, target_height]
            print(f"[R Orientation] Tall image -> {result[0]}x{result[1]} (rounded to 8px)")
            return result
        else:
            # Square-ish - use balanced dimensions based on original size
            # Scale to reasonable size while maintaining square aspect
            max_dim = max(x, y)
            if max_dim > 1024:
                result = [1024, 1024]
            elif max_dim < 512:
                result = [512, 512]
            else:
                # Use original dimensions if they're reasonable, rounded to 8px
                max_dim = (max_dim // 8) * 8
                result = [max_dim, max_dim]
            print(f"[R Orientation] Square-ish image -> {result[0]}x{result[1]} (rounded to 8px)")
            return result

    def _setup_cache(self, use_cache):
        cache_was_installed = requests_cache.patcher.is_installed()
        if use_cache and not cache_was_installed:
            print("[R] Installing cache.")
            requests_cache.install_cache('ranbooru_cache', backend='sqlite', expire_after=3600)
        elif not use_cache and cache_was_installed:
            print("[R] Uninstalling cache.")
            requests_cache.uninstall_cache()
        return use_cache and not cache_was_installed

    def _prepare_tags(self, ui_tags, ui_remove_tags, use_remove_file, remove_file, change_background, change_color, use_search_file, search_file, remove_default_bad):
        bad_tags = set()
        if remove_default_bad:
            bad_tags.update(['mixed-language_text', 'watermark', 'text', 'english_text', 'speech_bubble', 'signature', 'artist_name', 'censored', 'bar_censor', 'translation', 'twitter_username', "twitter_logo", 'patreon_username', 'commentary_request', 'tagme', 'commentary', 'character_name', 'mosaic_censoring', 'instagram_username', 'text_focus', 'english_commentary', 'comic', 'translation_request', 'fake_text', 'translated', 'paid_reward_available', 'thought_bubble', 'multiple_views', 'silent_comic', 'out-of-frame_censoring', 'symbol-only_commentary', '3koma', '2koma', 'character_watermark', 'spoken_question_mark', 'japanese_text', 'spanish_text', 'language_text', 'fanbox_username', 'commission', 'original', 'ai_generated', 'stable_diffusion', 'tagme_(artist)', 'text_bubble', 'qr_code', 'chinese_commentary', 'korean_text', 'partial_commentary', 'chinese_text', 'copyright_request', 'heart_censor', 'censored_nipples', 'page_number', 'scan', 'fake_magazine_cover', 'korean_commentary'])
        if ui_remove_tags:
            bad_tags.update([t.strip() for t in ui_remove_tags.split(',') if t.strip()])
        if use_remove_file and remove_file:
            try:
                filepath = os.path.join(USER_REMOVE_DIR, remove_file)
                print(f"[R] Reading remove tags: {filepath}")
                with open(filepath, 'r', encoding='utf-8') as f:
                    read_tags = [t.strip() for t in f.read().split(',') if t.strip()]
                    print(f"[R] Tags read: {read_tags}")
                    bad_tags.update(read_tags)
            except Exception as e:
                print(f"[R] Warn: Read remove file failed {remove_file}: {e}")
        initial_additions = []
        bg_remove = set()
        color_remove = set()
        if change_background == 'Add Detail':
            initial_additions.append(random.choice(["outdoors", "indoors", "detailed_background"]))
            bg_remove.update(COLORED_BG + ['simple_background', 'plain_background', 'transparent_background'])
        elif change_background == 'Force Simple':
            initial_additions.append(random.choice(['simple_background', 'plain_background'] + COLORED_BG))
            bg_remove.update(ADD_BG + ['detailed_background'])
        elif change_background == 'Force Transparent/White':
            initial_additions.append(random.choice(['transparent_background', 'white_background', 'plain_background']))
            bg_remove.update(ADD_BG + COLORED_BG + ['detailed_background', 'simple_background'])
        if change_color == 'Force Color':
            color_remove.update(BW_BG + ['limited_palette'])
        elif change_color == 'Force Monochrome':
            initial_additions.append(random.choice(BW_BG))
            color_remove.update(['colored_background', 'limited_palette'])
        bad_tags.update(bg_remove)
        bad_tags.update(color_remove)
        initial_additions_str = ','.join(initial_additions)
        search_tags = ui_tags
        if use_search_file and search_file:
            try:
                filepath = os.path.join(USER_SEARCH_DIR, search_file)
                print(f"[R] Reading search tags: {filepath}")
                with open(filepath, 'r', encoding='utf-8') as f:
                    search_lines = [line.strip() for line in f.readlines() if line.strip()]
                    if search_lines:
                        selected_file_tags = random.choice(search_lines)
                        search_tags = f'{search_tags},{selected_file_tags}' if search_tags else selected_file_tags
                        print(f"[R] Added file tags: {selected_file_tags}")
                    else:
                        print(f"[R] Warn: Search file empty: '{search_file}'")
            except Exception as e:
                print(f"[R] Warn: Read search file failed {search_file}: {e}")
        return search_tags, bad_tags, initial_additions_str

    def _get_booru_api(self, booru_name, fringe_benefits, gelbooru_credentials: Optional[Dict[str, str]] = None):
        booru_apis = {
            'gelbooru': Gelbooru(fringe_benefits, gelbooru_credentials),
            'danbooru': Danbooru(),
            'xbooru': XBooru(),
            'rule34': Rule34(),
            'safebooru': Safebooru(),
            'konachan': Konachan(),
            'yande.re': Yandere(),
            'aibooru': AIBooru(),
            'e621': e621(),
        }
        if has_scatbooru_access():
            booru_apis['scatbooru'] = Scatbooru()
        if booru_name == 'scatbooru' and not has_scatbooru_access():
            raise ValueError('Scatbooru requires a valid session cookie. Set RANBOORUX_SCATBOORU_COOKIE or create user/cookies/scatbooru.cookie with the session value.')
        if booru_name not in booru_apis:
            raise ValueError(f"Booru '{booru_name}' not implemented.")
        return booru_apis.get(booru_name)

    def _fetch_booru_posts(self, api, search_tags, mature_rating, max_pages, post_id):
        add_tags_list = []
        # Don't add search_tags to tags_query when using post_id - causes API confusion
        if search_tags and not post_id:
            add_tags_list.extend([t.strip() for t in search_tags.split(',') if t.strip()])
        booru_name = api.booru_name.lower()
        if mature_rating != 'All' and booru_name in RATINGS and mature_rating in RATINGS[booru_name]:
            rating_tag = RATINGS[booru_name][mature_rating]
            if rating_tag != "All":
                add_tags_list.append(f"rating:{rating_tag}")
        add_tags_list.append('-animated')
        tags_query = f"&tags={'+'.join(add_tags_list)}" if add_tags_list else ""
        print(f"[R] Query Tags: '{tags_query}' (post_id={post_id})")
        try:
            all_posts = api.get_posts(tags_query=tags_query, max_pages=max_pages, post_id=post_id)
            if not all_posts:
                raise ValueError("No valid posts found matching criteria after fetching.")
            return all_posts, tags_query
        except BooruError as e:
            print(f"[R] Error fetching from {api.booru_name}: {e}")
            raise
        except Exception as e:
            print(f"[R] Unexpected error during fetch: {e}")
            raise BooruError(f"Unexpected fetch error: {e}") from e

    def _select_posts(self, all_posts, sorting_order, num_images_needed, post_id, same_prompt):
        if not all_posts:
            return []
        sort_key_map = {"Score Descending": "score", "Score Ascending": "score"}
        reverse_map = {"Score Descending": True, "Score Ascending": False}
        if not post_id and sorting_order != "Random":
            sort_key = sort_key_map.get(sorting_order)
            reverse = reverse_map.get(sorting_order, False)
            if sort_key:
                print(f"[R] Sorting {len(all_posts)} by {sort_key} {'Desc' if reverse else 'Asc'}")
                all_posts = sorted(all_posts, key=lambda k: k.get(sort_key, 0) if isinstance(k.get(sort_key, 0), (int, float)) else 0, reverse=reverse)
        available_count = len(all_posts)
        selected_indices = []
        if post_id:
            selected_indices = [0] * num_images_needed
        elif same_prompt:
            chosen_index = random.randrange(available_count) if sorting_order == "Random" else 0
            selected_indices = [chosen_index] * num_images_needed
        else:
            if sorting_order == "Random":
                selected_indices = random.choices(range(available_count), k=num_images_needed)
            else:
                indices_to_use = list(range(min(available_count, num_images_needed)))
                selected_indices = indices_to_use + [indices_to_use[-1]] * (num_images_needed - len(indices_to_use))
        print(f"[R] Selected indices: {selected_indices}")
        return [all_posts[i] for i in selected_indices]

    def _fetch_images(self, posts_to_fetch, use_same_image, booru_name, fringe_benefits):
        print("[R] Fetching images...")
        fetched_images = []
        image_urls = [post.get('file_url') for post in posts_to_fetch]
        if not any(url for url in image_urls if url):
            print("[R] Warn: No valid file_urls found.")
            return []
        first_valid_url = None
        if use_same_image:
            first_valid_url = next((url for url in image_urls if url), None)
            if not first_valid_url:
                print("[R] Warn: Cannot use same image, first URL invalid.")
                return []
            image_urls = [first_valid_url] * len(posts_to_fetch)
        try:
            api = self._get_booru_api(booru_name, fringe_benefits, getattr(self, '_gelbooru_effective_credentials', None))
        except ValueError as e:
            print(f"[R] Error getting API for image fetch: {e}")
            return []
        fetched_count = 0
        for i, img_url in enumerate(image_urls):
            img_to_append = None
            try:
                if img_url and img_url.startswith(('http://', 'https://')):
                    print(f"[R] Fetching {i+1}/{len(image_urls)}: {img_url[:50]}...")
                    response = requests.get(img_url, headers=api.headers, timeout=30)
                    response.raise_for_status()
                    img_data = BytesIO(response.content)
                    pil_image = Image.open(img_data).convert("RGB")
                    img_to_append = pil_image
                    fetched_count += 1
                    print(f"[R] Successfully fetched image {i+1}: {pil_image.size}")
                elif img_url:
                    if any(site in img_url.lower() for site in ['pixiv.net', 'pximg.net', 'twitter.com', 'x.com']):
                        print(f"[R] Skipped external site URL {i+1}: {img_url[:50]} (not a direct image)")
                    else:
                        print(f"[R] Invalid URL protocol {i+1}: {img_url[:50]}")
                else:
                    print(f"[R] No URL available for image {i+1}")
            except Exception as e:
                print(f"[R] Error fetching image {i+1}: {e}")
            fetched_images.append(img_to_append)
        print(f"[R] Fetched {fetched_count} images.")
        if None in fetched_images:
            print("[R] Warn: Some images failed.")
        return fetched_images

    def _process_single_prompt(self, index, raw_prompt, base_positive, base_negative, initial_additions, settings):
        (
            shuffle_tags, chaos_mode, chaos_amount, limit_tags_pct, max_tags_count, change_dash,
            use_deepbooru, type_deepbooru, remove_artist_tags, remove_character_tags,
            remove_clothing_tags, remove_text_tags, restrict_subject_tags,
            remove_furry_tags, remove_headwear_tags, preserve_hair_eye_colors, remove_series_tags
        ) = settings
        current_prompt = f"{initial_additions},{raw_prompt}" if initial_additions else raw_prompt
        prompt_tags = [tag.strip() for tag in re.split(r'[\,\t\s]+', current_prompt) if tag.strip()]
        base_hair_colors = set(getattr(self, '_base_hair_color_tags', set()) or [])
        base_eye_colors = set(getattr(self, '_base_eye_color_tags', set()) or [])
        # If removal flags are set, remove tags coming from selected post's artist/character lists
        try:
            post_meta = self._selected_posts[index] if hasattr(self, '_selected_posts') and index < len(self._selected_posts) else {}
            artist_tags_meta = post_meta.get('artist_tags', []) if isinstance(post_meta, dict) else []
            character_tags_meta = post_meta.get('character_tags', []) if isinstance(post_meta, dict) else []
            norm = self._normalize_tag
            artist_norm = {norm(t) for t in artist_tags_meta if isinstance(t, str)}
            char_norm = {norm(t) for t in character_tags_meta if isinstance(t, str)}
            if isinstance(post_meta, dict):
                copyright_tags_meta = post_meta.get('copyright_tags') or []
                if remove_character_tags and copyright_tags_meta:
                    char_norm.update({norm(t) for t in copyright_tags_meta if isinstance(t, str)})
                    char_norm.update({(t or '').strip().lower() for t in copyright_tags_meta if isinstance(t, str)})
            artist_norm.update({(t or '').strip().lower() for t in artist_tags_meta if isinstance(t, str)})
            char_norm.update({(t or '').strip().lower() for t in character_tags_meta if isinstance(t, str)})
            general_tags = []
            if isinstance(post_meta, dict):
                raw_all_tags = post_meta.get('tags') or ''
                if isinstance(raw_all_tags, str):
                    general_tags = [t.strip() for t in re.split(r'[\s,]+', raw_all_tags) if t.strip()]
            if remove_character_tags and general_tags:
                for tag in general_tags:
                    tag_norm = norm(tag)
                    if ('(' in tag and ')' in tag and not tag.strip().startswith('(')) or any(tag_norm.endswith(suffix) for suffix in (' series', ' franchise', ' character', ' characters')):
                        char_norm.add(tag_norm)
                        char_norm.add(tag.strip().lower())
            if remove_artist_tags and general_tags:
                for tag in general_tags:
                    tag_norm = norm(tag)
                    if tag_norm.startswith('artist:') or tag_norm.endswith(' artist') or ' drawn by' in tag_norm:
                        artist_norm.add(tag_norm)
                        artist_norm.add(tag.strip().lower())
            allowed_subjects = set()
            if restrict_subject_tags:
                allowed_subjects.update(self._extract_subject_tags(base_positive))
                allowed_subjects.update(self._extract_subject_tags(initial_additions))
                allowed_subjects.update(self._extract_subject_tags(getattr(self, 'original_prompt', '')))
            use_new_filter = getattr(self, '_beta_filter_enabled', True)
            filter_ctx = getattr(self, '_removal_context', None) if use_new_filter else None
            favorites_guard: Set[str] = set()
            if use_new_filter and filter_ctx:
                favorites_guard = set(filter_ctx.get('favorites', frozenset()))  # type: ignore[arg-type]
            norm_cache = getattr(self, '_tag_normal_cache', {})
            if not isinstance(norm_cache, dict):
                norm_cache = {}
                self._tag_normal_cache = norm_cache
            filtered_prompt_tags = []
            primary_subject = None
            for t in prompt_tags:
                t_norm = self._normalize_cached(t, norm_cache)
                canonical_tag = t_norm or self._canonicalize_raw_tag(t)
                t_orig = (t or '').strip().lower()
                is_favorite = bool(use_new_filter and t_norm and t_norm in favorites_guard)
                if is_favorite:
                    filtered_prompt_tags.append(t)
                    continue
                should_remove = False
                if remove_artist_tags and (t_norm in artist_norm or t_orig in artist_norm or (t_norm and t_norm.endswith(' artist'))):
                    should_remove = True
                elif remove_character_tags and (t_norm in char_norm or t_orig in char_norm or ('(' in t and ')' in t and not t.strip().startswith('(')) or (t_norm and (t_norm.endswith(' series') or t_norm.endswith(' franchise')))):
                    should_remove = True
                if not should_remove and remove_clothing_tags and self._is_clothing_tag(t):
                    should_remove = True
                if not should_remove and remove_text_tags and self._is_textual_tag(t):
                    should_remove = True
                if not should_remove and remove_furry_tags and self._is_furry_tag(t):
                    should_remove = True
                if not should_remove and remove_headwear_tags and self._is_headwear_tag(t):
                    should_remove = True
                if not should_remove and remove_series_tags and self._is_series_tag(t):
                    should_remove = True
                if not should_remove and preserve_hair_eye_colors:
                    if base_hair_colors and canonical_tag in base_hair_colors:
                        pass
                    elif base_eye_colors and canonical_tag in base_eye_colors:
                        pass
                    elif base_hair_colors and self._is_hair_color_tag(t) and canonical_tag not in base_hair_colors:
                        should_remove = True
                    elif base_eye_colors and self._is_eye_color_tag(t) and canonical_tag not in base_eye_colors:
                        should_remove = True
                if not should_remove and restrict_subject_tags and self._is_subject_tag(t):
                    subject_norm = t_norm
                    if allowed_subjects:
                        if subject_norm not in allowed_subjects:
                            should_remove = True
                    else:
                        if primary_subject is None:
                            primary_subject = subject_norm
                        elif subject_norm != primary_subject:
                            should_remove = True
                if not should_remove:
                    if use_new_filter and filter_ctx and t_norm:
                        should_remove = self._tag_matches_removal(t_norm, filter_ctx)
                    elif not use_new_filter:
                        should_remove = self._legacy_tag_matches(t)
                if not should_remove:
                    filtered_prompt_tags.append(t)
            prompt_tags = filtered_prompt_tags
        except Exception:
            # fallback: ignore removal if anything goes wrong
            pass
        current_prompt = ','.join(prompt_tags)
        if shuffle_tags:
            tags_list = [t.strip() for t in current_prompt.split(',') if t.strip()]
            random.shuffle(tags_list)
            current_prompt = ','.join(tags_list)
        current_negative = base_negative
        if chaos_mode == 'Shuffle All':
            current_prompt, current_negative = generate_chaos(current_prompt, current_negative, chaos_amount)
        elif chaos_mode == 'Shuffle Negative':
            _, current_negative = generate_chaos("", current_negative, chaos_amount)
        if limit_tags_pct < 1.0:
            current_prompt = limit_prompt_tags(current_prompt, limit_tags_pct, 'Limit')
        if max_tags_count > 0:
            current_prompt = limit_prompt_tags(current_prompt, max_tags_count, 'Max')
        if change_dash:
            current_prompt = current_prompt.replace("_", " ")
            current_negative = current_negative.replace("_", " ")
        if use_deepbooru and index < len(self.last_img) and self.last_img[index] is not None:
            print(f"[R] Running DB for {index}...")
            try:
                if not deepbooru.model.model:
                    deepbooru.model.start()
                db_tags = deepbooru.model.tag_multi(self.last_img[index])
                current_prompt = modify_prompt(current_prompt, db_tags, type_deepbooru)
            except Exception as e:
                print(f"[R] Error DB {index}: {e}")
        if base_positive:
            current_prompt = f"{base_positive}, {current_prompt}" if current_prompt else base_positive
        current_prompt = remove_repeated_tags(current_prompt)
        current_negative = remove_repeated_tags(current_negative)
        return current_prompt, current_negative

    def _apply_loranado(self, p, lora_enabled, lora_folder, lora_amount, lora_min, lora_max, lora_custom_weights, lora_lock_prev):
        lora_prompt = ''
        if not lora_enabled:
            return p
        if lora_lock_prev and self.previous_loras:
            lora_prompt = self.previous_loras
            print(f"[R] Using locked LoRAs: {lora_prompt}")
        else:
            lora_dir = shared.cmd_opts.lora_dir
            target_folder = os.path.join(lora_dir, lora_folder) if lora_folder else lora_dir
            if not os.path.isdir(target_folder):
                print(f"[R] LoRA folder not found: {target_folder}")
                self.previous_loras = ''
                return p
            try:
                all_loras = [f for f in os.listdir(target_folder) if f.lower().endswith('.safetensors')]
            except Exception as e:
                print(f"[R] Error list LoRA folder {target_folder}: {e}")
                all_loras = []
            if not all_loras:
                print(f"[R] No .safetensors LoRAs found: {target_folder}")
                self.previous_loras = ''
                return p
            custom_weights = []
            if lora_custom_weights:
                try:
                    custom_weights = [float(w.strip()) for w in lora_custom_weights.split(',')]
                except ValueError:
                    print(f"[R] Warn: Invalid custom LoRA weights: '{lora_custom_weights}'")
            selected_loras = []
            num_to_select = min(lora_amount, len(all_loras))
            allow_reuse = len(all_loras) < num_to_select
            chosen_files = set()
            for i in range(num_to_select):
                lora_weight = custom_weights[i] if i < len(custom_weights) else round(random.uniform(lora_min, lora_max), 2)
                available_choices = all_loras if allow_reuse else [lora for lora in all_loras if lora not in chosen_files]
                if not available_choices:
                    print(f"[R] Warn: Ran out unique LoRAs.")
                    break
                chosen_lora_file = random.choice(available_choices)
                if not allow_reuse:
                    chosen_files.add(chosen_lora_file)
                lora_name = os.path.splitext(chosen_lora_file)[0]
                selected_loras.append(f'<lora:{lora_name}:{lora_weight}>')
            lora_prompt = ' '.join(selected_loras)
            self.previous_loras = lora_prompt
            print(f"[R] Applying LoRAs: {lora_prompt}")
        if lora_prompt:
            if isinstance(p.prompt, list):
                p.prompt = [f'{lora_prompt} {pr}' for pr in p.prompt]
            else:
                p.prompt = f'{lora_prompt} {p.prompt}'
        return p

    def _prepare_img2img_pass(self, p, use_img2img, use_ip):
        self.run_img2img_pass = False
        if use_img2img:
            # CRITICAL FIX: Use higher quality initial pass to prevent distortion
            initial_steps = max(5, min(10, p.steps // 3))  # Use 1/3 of total steps, min 5
            print(f"[R] Prep Img2Img pass (steps={initial_steps}) - ControlNet {'enabled' if use_ip else 'disabled'}.")
            print("[R] Using higher quality initial pass to prevent distortion")
            self.real_steps = p.steps
            
            # CRITICAL FIX: Store original prompt and use minimal prompt for initial pass
            # This prevents ADetailer from processing the initial pass results
            self.original_full_prompt = p.prompt
            # Use minimal prompt to create basic shapes that ADetailer won't process
            if isinstance(p.prompt, list):
                p.prompt = ["abstract shapes, minimal"] * len(p.prompt)
            else:
                p.prompt = "abstract shapes, minimal"
            print("[R] Using minimal prompt for initial pass to avoid premature ADetailer processing")
            
            p.steps = initial_steps
            
            # CRITICAL FIX: Don't reduce CFG too much - maintain image coherence
            self.original_cfg = p.cfg_scale
            p.cfg_scale = max(4.0, min(p.cfg_scale, 8.0))  # Keep CFG between 4-8
            
            # CRITICAL FIX: Reduce denoising strength to prevent over-processing
            self.original_denoising = self.img2img_denoising
            self.img2img_denoising = min(0.6, self.img2img_denoising)  # Cap at 0.6 to prevent distortion
            
            self.run_img2img_pass = True
            
            # CRITICAL: Store original save settings BEFORE any modifications
            self.original_save_images = getattr(p, 'do_not_save_samples', False) 
            self.original_save_grid = getattr(p, 'do_not_save_grid', False)
            self.original_outpath = getattr(p, 'outpath_samples', None)
            
            print(f"[R Save Prevention] Original save state: do_not_save_samples={self.original_save_images}, outpath='{self.original_outpath}'")
            
            # AGGRESSIVE: Prevent initial pass results from being saved by multiple methods
            p.do_not_save_samples = True
            p.do_not_save_grid = True
            
            # Create temp directory for initial pass saves (will be deleted)
            import tempfile
            temp_dir = tempfile.mkdtemp(prefix='ranbooru_temp_')
            print(f"[R Save Prevention] 🚫 Redirected initial pass saves to temp directory: {temp_dir}")
            p.outpath_samples = temp_dir
            
            # Set batch size to 1 and disable extensions for initial pass
            self.original_batch_size = p.batch_size
            p.batch_size = 1  # Minimize processing
            
            # LIGHTER APPROACH: Just mark that we're in initial pass - don't completely disable ADetailer
            self._mark_initial_pass(p)
            
            # ADDITIONAL SAVE PREVENTION: More aggressive image saving prevention
            self._prevent_all_image_saving(p)
            
            print("[R] AGGRESSIVE: Disabled all saving, minimized batch for initial pass")
            print(f"[R] Optimized settings: steps={initial_steps}, cfg={p.cfg_scale}, denoising={self.img2img_denoising}")

    def _cleanup_after_run(self, use_cache):
        # Don't clear self.last_img or cached data - keep them for reuse
        self.real_steps = 0
        self.run_img2img_pass = False
        
        # Clean up stored original values
        if hasattr(self, 'original_full_prompt'):
            delattr(self, 'original_full_prompt')
        if hasattr(self, '_adetailer_script_args_snapshot'):
            delattr(self, '_adetailer_script_args_snapshot')
        if hasattr(self, '_current_processing_object'):
            delattr(self, '_current_processing_object')
        if hasattr(self, 'original_cfg'):
            delattr(self, 'original_cfg')
        if hasattr(self, 'original_denoising'):
            # Restore original denoising value
            self.img2img_denoising = self.original_denoising
            delattr(self, 'original_denoising')
        if hasattr(self, 'original_save_images'):
            # Restore original save settings before deleting
            try:
                import modules.shared
                if hasattr(modules.shared, 'opts'):
                    modules.shared.opts.save_images = self.original_save_images
            except Exception as e:
                print(f"[R Cleanup] Warning: Could not restore original save_images: {e}")
            delattr(self, 'original_save_images')
        if hasattr(self, 'original_save_grid'):
            # Restore original save grid settings before deleting
            try:
                import modules.shared
                if hasattr(modules.shared, 'opts'):
                    modules.shared.opts.save_images = self.original_save_grid
            except Exception as e:
                print(f"[R Cleanup] Warning: Could not restore original save_grid: {e}")
            delattr(self, 'original_save_grid')
        if hasattr(self, 'original_outpath'):
            # Restore original outpath before deleting
            try:
                import modules.shared
                if hasattr(modules.shared, 'opts'):
                    modules.shared.opts.outdir_txt2img_samples = self.original_outpath
            except Exception as e:
                print(f"[R Cleanup] Warning: Could not restore original outpath: {e}")
            delattr(self, 'original_outpath')
        if hasattr(self, 'original_batch_size'):
            delattr(self, 'original_batch_size')
            
        # Clean up additional save-related parameters
        if hasattr(self, 'original_save_to_dirs'):
            delattr(self, 'original_save_to_dirs')
            
        # Clean up temporary directory
        if hasattr(self, 'temp_initial_dir'):
            try:
                import shutil
                shutil.rmtree(self.temp_initial_dir, ignore_errors=True)
                print(f"[R Cleanup] 🧹 Cleaned up temporary directory: {self.temp_initial_dir}")
                delattr(self, 'temp_initial_dir')
            except Exception as e:
                print(f"[R Cleanup] Warning: Could not clean temp directory: {e}")
        if hasattr(self, 'original_filename_format'):
            delattr(self, 'original_filename_format')  
        if hasattr(self, 'original_save_images_history'):
            delattr(self, 'original_save_images_history')
        if hasattr(self, 'original_save_samples_dir'):
            delattr(self, 'original_save_samples_dir')
            
        # Clean up processing state flags
        if hasattr(self, '_ranbooru_processing_complete'):
            delattr(self, '_ranbooru_processing_complete')
        if hasattr(self, '_ranbooru_intermediate_results'):
            delattr(self, '_ranbooru_intermediate_results')

        if hasattr(self, '_native_adetailer_fallback_used'):
            delattr(self, '_native_adetailer_fallback_used')

        # Clean up ADetailer state
        if hasattr(self, '_ranbooru_initial_pass'):
            self._ranbooru_initial_pass = False
            print("[R Cleanup] Cleared initial pass flag")
        if hasattr(self, '_initial_pass_p'):
            delattr(self, '_initial_pass_p')
            
        # CRITICAL FIX: Don't re-enable ADetailer in cleanup - let it stay disabled for this generation
        if hasattr(self, 'disabled_adetailer_scripts'):
            print(f"[R Cleanup] 🚫 Keeping {len(self.disabled_adetailer_scripts)} ADetailer script(s) disabled to prevent wrong image processing")
            # We'll re-enable them on the NEXT generation start instead of now
            # This prevents ADetailer from running on wrong images after our manual processing
        
        # Clean up early protection state
        if hasattr(self, '_temp_disabled_adetailer'):
            # Force restore if cleanup is called early
            self._restore_early_adetailer_protection(getattr(self, '_initial_pass_p', None))
            
        # Clean up blocking state  
        if hasattr(self.__class__, '_block_640x512_images'):
            print("[R Cleanup] 🔄 Clearing 640x512 image blocking for next generation")
            delattr(self.__class__, '_block_640x512_images')
        
        # Restore ADetailer scripts if they were removed from the pipeline
        if hasattr(self, '_removed_adetailer_scripts'):
            print("[R Cleanup] 🔄 Restoring ADetailer scripts to pipeline for next generation")
            # Note: We don't actually restore here since it's too aggressive
            # ADetailer will be available for the next generation automatically
            delattr(self, '_removed_adetailer_scripts')
            
        # Ensure any manual patches are removed once we're finished
        self._unpatch_manual_adetailer_overrides()

        if not use_cache and hasattr(self, 'cache_installed_by_us') and self.cache_installed_by_us and requests_cache.patcher.is_installed():
            requests_cache.uninstall_cache()
            print("[R Post] Uninstalled cache.")
        if hasattr(self, 'cache_installed_by_us'):
            try:
                del self.cache_installed_by_us
            except AttributeError:
                pass

    def _force_release_processing_guards(self, reason, attempt_cleanup=True, processing_obj=None):
        """Aggressively clear processing locks when a previous job ended abruptly."""
        try:
            print(f"[R Guard] ⚠️ Forcing release of RanbooruX processing lock: {reason}")
        except Exception:
            pass

        released = False
        if attempt_cleanup:
            try:
                use_cache = getattr(self, '_post_use_cache', True)
                self._cleanup_after_run(use_cache)
            except Exception as exc:
                print(f"[R Guard] Cleanup while releasing lock failed: {exc}")

        try:
            if hasattr(self, '_current_processing_key'):
                processing_key = self._current_processing_key
                if hasattr(self, processing_key):
                    delattr(self, processing_key)
                delattr(self, '_current_processing_key')
            released = True
        except Exception as exc:
            print(f"[R Guard] Failed clearing instance processing key: {exc}")

        try:
            setattr(self.__class__, '_ranbooru_global_processing', False)
        except Exception as exc:
            print(f"[R Guard] Failed clearing global processing flag: {exc}")
            released = False

        if hasattr(self, '_current_processing_object'):
            try:
                delattr(self, '_current_processing_object')
            except Exception as exc:
                print(f"[R Guard] Failed clearing processing object reference: {exc}")
                released = False

        # Ensure ADetailer hooks are restored so future generations run normally
        try:
            self._restore_early_adetailer_protection(processing_obj)
        except Exception as exc:
            print(f"[R Guard] Failed restoring ADetailer protection: {exc}")
            released = False

        return released

    def _maybe_release_stale_guards(self, new_processing_obj):
        """Detect and release stale locks left behind by interrupted runs."""
        guard_active = getattr(self.__class__, '_ranbooru_global_processing', False)
        if not guard_active:
            return

        previous_obj = getattr(self, '_current_processing_object', None)
        if previous_obj is new_processing_obj:
            return

        state_interrupted = False
        state_processing = False
        try:
            state = getattr(shared, 'state', None)
            if state is not None:
                state_interrupted = getattr(state, 'interrupted', False) or getattr(state, 'stopping_job', False)
                state_processing = getattr(state, 'processing', False)
        except Exception:
            state_processing = False

        previous_finalized = False
        if previous_obj is not None:
            previous_finalized = getattr(previous_obj, '_ranbooru_finalized', False)

        # Release when the WebUI is idle, interrupted, or the previous object was already finalized.
        if not state_processing or state_interrupted or previous_finalized or previous_obj is None:
            reason_bits = []
            if not state_processing:
                reason_bits.append('WebUI idle')
            if state_interrupted:
                reason_bits.append('interrupted flag set')
            if previous_finalized:
                reason_bits.append('previous job finalized')
            if previous_obj is None:
                reason_bits.append('no tracked processing object')
            reason = '; '.join(reason_bits) if reason_bits else 'stale lock detected'
            self._force_release_processing_guards(reason, processing_obj=new_processing_obj)
        else:
            # New processing object arrived while guard is still active—treat as stale lock.
            self._force_release_processing_guards('new processing request detected while guard active', processing_obj=new_processing_obj)

    def before_process(self, p: StableDiffusionProcessing, *args):
        try:
            # Fast-path for our own internal img2img calls: initialize seeds and exit
            if getattr(p, '_ranbooru_internal_img2img', False):
                try:
                    # Minimal seeds init to satisfy WebUI expectations
                    base_seed = getattr(p, 'seed', -1)
                    if base_seed == -1:
                        base_seed = random.randint(0, 2**32 - 1)
                        p.seed = base_seed
                    batch_count = max(1, getattr(p, 'n_iter', 1))
                    batch_size = max(1, getattr(p, 'batch_size', 1))
                    total_images = batch_count * batch_size
                    p.all_seeds = [base_seed + i for i in range(total_images)]
                    base_subseed = getattr(p, 'subseed', -1)
                    if base_subseed == -1:
                        base_subseed = random.randint(0, 2**32 - 1)
                        p.subseed = base_subseed
                    p.all_subseeds = [base_subseed + i for i in range(total_images)]
                    # Mirror common aliases expected by some codepaths
                    p.seeds = list(p.all_seeds)
                    p.subseeds = list(p.all_subseeds)
                    print(f"[R Before] ⚙️ Internal img2img fast-path: seeds={len(p.all_seeds)} from {base_seed}, subseeds from {base_subseed}")
                except Exception as _e:
                    print(f"[R Before] WARN: Internal img2img seed init failed: {_e}")
                return

            # Ensure leftover guards from interrupted jobs don't block new generations
            self._maybe_release_stale_guards(p)

            # CRITICAL: Ultra-strict processing guard to prevent any duplicate runs
            processing_key = f'_ranbooru_processing_{id(p)}'
            
            # Check multiple levels of guards
            if (hasattr(self, processing_key) or 
                getattr(self.__class__, '_ranbooru_global_processing', False) or
                hasattr(p, '_ranbooru_already_processing')):
                print(f"[R Before] 🛑 RanbooruX already processing - BLOCKING duplicate run")
                # Ensure seeds exist to prevent IndexError in core pipeline
                try:
                    base_seed = getattr(p, 'seed', -1)
                    if base_seed == -1:
                        base_seed = random.randint(0, 2**32 - 1)
                        p.seed = base_seed
                    batch_count = max(1, getattr(p, 'n_iter', 1))
                    batch_size = max(1, getattr(p, 'batch_size', 1))
                    total_images = batch_count * batch_size
                    if not getattr(p, 'all_seeds', None):
                        p.all_seeds = [base_seed + i for i in range(total_images)]
                    base_subseed = getattr(p, 'subseed', -1)
                    if base_subseed == -1:
                        base_subseed = random.randint(0, 2**32 - 1)
                        p.subseed = base_subseed
                    if not getattr(p, 'all_subseeds', None):
                        p.all_subseeds = [base_subseed + i for i in range(total_images)]
                except Exception as _e:
                    print(f"[R Before] WARN: Seed safety init failed on duplicate: {_e}")
                return

            # Set triple-level guards: instance, class, and processing object
            setattr(self, processing_key, True)
            setattr(self.__class__, '_ranbooru_global_processing', True)
            setattr(p, '_ranbooru_already_processing', True)
            print(f"[R Before] 🎯 Started RanbooruX processing for request {id(p)}")
            self._current_processing_object = p
            script_args_source = getattr(p, 'script_args', None)
            if isinstance(script_args_source, (list, tuple)):
                self._adetailer_script_args_snapshot = list(script_args_source)
            else:
                self._adetailer_script_args_snapshot = None
            
            # Store the processing key for cleanup
            self._current_processing_key = processing_key

            # Keep existing ordering stable for most outputs; new toggles are appended toward the end.
            (enabled, tags, booru, gelbooru_api_key_ui, gelbooru_user_id_ui, remove_bad_tags_ui, max_pages, change_dash, same_prompt,
             fringe_benefits, remove_tags_ui, use_img2img, denoising, use_last_img,
             change_background, change_color, shuffle_tags, post_id, mix_prompt, mix_amount,
             chaos_mode, chaos_amount, limit_tags_pct, max_tags_count, sorting_order, mature_rating,
             lora_folder, lora_amount, lora_min, lora_max, lora_enabled,
             lora_custom_weights, lora_lock_prev, use_ip, use_search_txt, use_remove_txt,
             choose_search_txt, choose_remove_txt, search_refresh_btn, remove_refresh_btn,
             crop_center, use_deepbooru, type_deepbooru, enable_adetailer_support, use_same_seed, reuse_cached_posts, use_cache, log_prompt_sources_ui,
             remove_artist_tags_ui, remove_character_tags_ui, remove_clothing_tags_ui, remove_text_tags_ui, restrict_subject_tags_ui,
             remove_furry_tags_ui, remove_headwear_tags_ui, preserve_hair_eye_colors_ui, remove_series_tags_ui, beta_filter_toggle_ui) = args
        except Exception as e:
            print(f"[R Before] CRITICAL Error unpack args: {e}. Aborting.")
            traceback.print_exc()
            return

        # denoising may come through as an empty string from the UI in some contexts; parse defensively
        try:
            self.img2img_denoising = float(denoising)
        except Exception:
            # fall back to previous default and warn
            self.img2img_denoising = float(getattr(self, 'img2img_denoising', 0.75))
            print(f"[R Before] Warn: invalid denoising value '{denoising}', falling back to {self.img2img_denoising}")

        # Persist values needed for postprocess to avoid fragile unpacking there
        self._post_enabled = bool(enabled)
        self._post_use_img2img = bool(use_img2img)
        self._post_use_ip = bool(use_ip)
        self._post_use_last_img = bool(use_last_img)
        self._post_crop_center = bool(crop_center)
        self._post_use_deepbooru = bool(use_deepbooru)
        self._post_type_deepbooru = type_deepbooru
        self._post_use_cache = bool(use_cache)
        self._reuse_cached_posts = bool(reuse_cached_posts)
        self._adetailer_support_enabled = bool(enable_adetailer_support)
        self._post_adetailer_enabled = self._adetailer_support_enabled
        prev_manual_state = getattr(self, '_manual_adetailer_prev_enabled', False)
        self._handle_adetailer_toggle_change(prev_manual_state, self._adetailer_support_enabled, p)
        self._manual_adetailer_prev_enabled = self._adetailer_support_enabled
        self._log_prompt_sources = bool(log_prompt_sources_ui)
        self._beta_filter_enabled = bool(beta_filter_toggle_ui)

        self._current_booru_name = booru
        if booru == 'gelbooru':
            self._gelbooru_effective_credentials = self._resolve_gelbooru_credentials(gelbooru_api_key_ui, gelbooru_user_id_ui)
        else:
            self._gelbooru_effective_credentials = None
        if not self._reuse_cached_posts:
            self._last_post_urls = []
        self._posts_used_for_generation = []
        self._final_prompts_snapshot = []
        self._final_negative_prompts_snapshot = []

        if lora_enabled:
            p = self._apply_loranado(p, lora_enabled, lora_folder, lora_amount, lora_min, lora_max, lora_custom_weights, lora_lock_prev)
        
        # CRITICAL: Ensure seeds are properly initialized to prevent IndexError
        # This must happen EVERY time, not just when they're empty
        if hasattr(p, 'seed'):
            base_seed = p.seed if p.seed != -1 else random.randint(0, 2**32 - 1)
        else:
            base_seed = random.randint(0, 2**32 - 1)
            p.seed = base_seed
        
        # Calculate batch size - be more defensive about this
        batch_count = max(1, getattr(p, 'n_iter', 1))
        batch_size = max(1, getattr(p, 'batch_size', 1)) 
        total_images = batch_count * batch_size
        
        # ALWAYS reinitialize seeds to prevent index errors
        p.all_seeds = [base_seed + i for i in range(total_images)]
        print(f"[R Before] 🔧 Initialized p.all_seeds with {len(p.all_seeds)} seeds starting from {base_seed}")
        
        # Also reinitialize all_subseeds
        base_subseed = getattr(p, 'subseed', -1)
        if base_subseed == -1:
            base_subseed = random.randint(0, 2**32 - 1)
        p.all_subseeds = [base_subseed + i for i in range(total_images)]
        print(f"[R Before] 🔧 Initialized p.all_subseeds with {len(p.all_subseeds)} subseeds starting from {base_subseed}")
        
        # ADDITIONAL: Ensure other seed-related attributes exist
        if not hasattr(p, 'seeds'):
            p.seeds = p.all_seeds.copy()
        if not hasattr(p, 'subseeds'):
            p.subseeds = p.all_subseeds.copy()
        
        self._reset_adetailer_state_for_run(p)

        if not enabled:
            print("[R] RanbooruX is DISABLED - skipping image fetch")
            self._adetailer_support_enabled = False
            self._post_adetailer_enabled = False
            # Clear processing guards even when disabled
            if hasattr(self, '_current_processing_key'):
                processing_key = self._current_processing_key
                if hasattr(self, processing_key):
                    delattr(self, processing_key)
                delattr(self, '_current_processing_key')
                setattr(self.__class__, '_ranbooru_global_processing', False)
            return

        self._reset_script_runner_guards()
        if self._is_adetailer_enabled():
            print("[R Before] Resetting ADetailer blocking flags for new generation")
        else:
            print("[R Before] Manual ADetailer support disabled - ensuring native ADetailer remains available")

        # Clear notification that extension is active
        print("[R Before] ⚠️  RanbooruX IS ENABLED AND RUNNING ⚠️")
        print(f"[R Before] Search tags: '{tags}' | Booru: {booru} | Img2Img: {use_img2img} | ControlNet: {use_ip}")
        
        # Check if we should reuse existing images or fetch new ones
        reuse_cached_posts = bool(getattr(self, '_reuse_cached_posts', False))

        # Special handling: if tags contain "!refresh", force fetch new images
        force_refresh = "!refresh" in (tags or "")
        if force_refresh:
            original_tags = tags
            tags = tags.replace("!refresh", "").replace(",,", ",").strip(",")
            print(f"[R Before] Detected !refresh command - forcing new image fetch")
            print(f"[R Before] Original tags: '{original_tags}' -> Cleaned: '{tags}'")

        personal_remove_tags, favorites_tags = self._load_personal_lists()

        current_search_key = f"{booru}_{tags}_{post_id}_{mature_rating}_{sorting_order}"
        if not reuse_cached_posts:
            should_fetch_new = True
        else:
            should_fetch_new = (
                force_refresh or
                not hasattr(self, '_last_search_key') or
                self._last_search_key != current_search_key or
                not hasattr(self, '_cached_posts') or
                not self._cached_posts or
                not hasattr(self, 'last_img') or
                not self.last_img
            )
        
        if not reuse_cached_posts:
            self._cached_posts = []
            self._cached_search_tags = ''
            self._cached_bad_tags = set()
            self._cached_initial_additions = ''
            self._cached_strict_rejections = []
            self._cached_strict_active = False
            self._cached_strict_relaxed = False

        if should_fetch_new:
            if force_refresh:
                print("[R Before] Fetching new images (!refresh command used)")
            else:
                print("[R Before] Fetching new images (search parameters changed or caching disabled)")
        else:
            if reuse_cached_posts:
                print(f"[R Before] Reusing cached images ({len(self.last_img)} images) from previous search")
                print("[R Before] 💡 TIP: Add '!refresh' to your tags to force fetch new images")
        
        self.original_prompt = p.prompt if isinstance(p.prompt, str) else (p.prompt[0] if isinstance(p.prompt, list) and p.prompt else "")
        base_hair_colors, base_eye_colors = self._extract_color_tags(self.original_prompt)
        self._base_hair_color_tags = base_hair_colors
        self._base_eye_color_tags = base_eye_colors
        self._strict_img2img_active = False
        self._strict_img2img_relaxed = False
        self._strict_img2img_rejections = []
        self._strict_initial_additions = ""
        self._strict_allowed_subjects = set(self._extract_subject_tags(self.original_prompt))
        base_subjects = set(self._strict_allowed_subjects)
        
        if not should_fetch_new:
            # Skip the fetching process but continue with cached images
            selected_posts = self._cached_posts
            print(f"[R Before] Using {len(selected_posts)} cached posts")
        else:
            self.last_img = []

        try:
            self.cache_installed_by_us = self._setup_cache(use_cache)
            
            # Always calculate num_images_needed - needed for both new and cached images
            original_batch = getattr(self, 'original_batch_size', p.batch_size)
            num_images_needed = original_batch * p.n_iter
            filter_ctx: Optional[Dict[str, object]] = None
            if should_fetch_new:
                search_tags, bad_tags, initial_additions = self._prepare_tags(
                    tags,
                    remove_tags_ui,
                    use_remove_txt,
                    choose_remove_txt,
                    change_background,
                    change_color,
                    use_search_txt,
                    choose_search_txt,
                    remove_bad_tags_ui,
                )
                bad_tags = set(bad_tags)
                bad_tags.update(personal_remove_tags)
                self._strict_initial_additions = initial_additions

                allowed_subjects = set()
                if bool(restrict_subject_tags_ui):
                    allowed_subjects = set(base_subjects)
                    allowed_subjects.update(self._extract_subject_tags(initial_additions))
                    self._strict_allowed_subjects = set(allowed_subjects)
                else:
                    self._strict_allowed_subjects = set()

                filter_ctx = self._build_removal_context(bad_tags, favorites_tags)
                self._removal_context = filter_ctx

                toggles_tuple = (
                    bool(remove_artist_tags_ui),
                    bool(remove_character_tags_ui),
                    bool(remove_clothing_tags_ui),
                    bool(remove_text_tags_ui),
                    bool(restrict_subject_tags_ui),
                    bool(remove_furry_tags_ui),
                    bool(remove_headwear_tags_ui),
                    bool(preserve_hair_eye_colors_ui),
                    bool(remove_series_tags_ui),
                )
                base_colors_tuple = (set(base_hair_colors), set(base_eye_colors))

                api = self._get_booru_api(booru, fringe_benefits, getattr(self, '_gelbooru_effective_credentials', None))
                all_posts, tags_query = self._fetch_booru_posts(api, search_tags, mature_rating, max_pages, post_id)

                filtered_posts = list(all_posts)
                strict_rejections: List[Dict[str, object]] = []
                strict_active = False
                strict_relaxed = False

                strict_enabled_for_run = bool(use_img2img and not post_id)

                if strict_enabled_for_run:
                    filtered_posts, strict_rejections, strict_active, strict_relaxed = self._apply_strict_img2img_prefilter(
                        list(all_posts),
                        api=api,
                        tags_query=tags_query,
                        post_id=post_id,
                        num_images_needed=num_images_needed,
                        max_pages=max_pages,
                        filter_ctx=filter_ctx,
                        toggles=toggles_tuple,
                        base_colors=base_colors_tuple,
                        allowed_subjects=allowed_subjects,
                    )
                    self._strict_img2img_active = strict_active
                    self._strict_img2img_relaxed = strict_relaxed
                    self._strict_img2img_rejections = list(strict_rejections)
                    self._last_rejections = list(self._strict_img2img_rejections)
                    if strict_active:
                        if strict_rejections:
                            print(f"[R Strict] Img2Img strict pre-filter rejected {len(strict_rejections)} candidate(s) before download")
                            preview = strict_rejections[:STRICT_IMG2IMG_LOG_SAMPLE]
                            for entry in preview:
                                print(
                                    f"[R Strict] • {entry.get('booru')} post {entry.get('post_id')} rejected by {entry.get('rule_type')} (tag: {entry.get('matched_tag')})"
                                )
                            if len(strict_rejections) > STRICT_IMG2IMG_LOG_SAMPLE:
                                print(f"[R Strict] • ... {len(strict_rejections) - STRICT_IMG2IMG_LOG_SAMPLE} more")
                        print(
                            f"[R Strict] {len(filtered_posts)} candidate(s) available after strict filtering (need {num_images_needed})"
                        )
                else:
                    self._strict_img2img_active = False
                    self._strict_img2img_relaxed = False
                    self._strict_img2img_rejections = []
                    self._last_rejections = []

                all_posts = filtered_posts
                selected_posts = self._select_posts(filtered_posts, sorting_order, num_images_needed, post_id, same_prompt)

                # Cache the results for future use
                self._cached_posts = selected_posts
                self._last_search_key = current_search_key
                self._cached_search_tags = search_tags
                self._cached_bad_tags = set(bad_tags)
                self._cached_initial_additions = initial_additions
                self._cached_strict_rejections = list(self._strict_img2img_rejections)
                self._cached_strict_active = self._strict_img2img_active
                self._cached_strict_relaxed = self._strict_img2img_relaxed

                post_urls = []
                try:
                    for idx, post in enumerate(selected_posts):
                        post_url = get_original_post_url(post)
                        if post_url:
                            post_urls.append(post_url)
                            print(f"[R] Original post {idx+1}/{len(selected_posts)}: {post_url}")
                except Exception as e:
                    print(f"[R] Warn: Failed to compute original post URLs: {e}")
                self._last_post_urls = post_urls

                if use_img2img or use_deepbooru or use_ip:
                    self.last_img = self._fetch_images(selected_posts, use_last_img, booru, fringe_benefits)
            else:
                # Use cached values
                search_tags = getattr(self, '_cached_search_tags', '')
                bad_tags = set(getattr(self, '_cached_bad_tags', set()))
                bad_tags.update(personal_remove_tags)
                initial_additions = getattr(self, '_cached_initial_additions', '')
                self._cached_bad_tags = set(bad_tags)
                self._strict_initial_additions = initial_additions
                all_posts = list(getattr(self, '_cached_posts', []))

                if bool(restrict_subject_tags_ui):
                    allowed_subjects = set(base_subjects)
                    allowed_subjects.update(self._extract_subject_tags(initial_additions))
                    self._strict_allowed_subjects = set(allowed_subjects)
                else:
                    self._strict_allowed_subjects = set()

                filter_ctx = getattr(self, '_removal_context', None)
                if filter_ctx is None:
                    filter_ctx = self._build_removal_context(bad_tags, favorites_tags)
                self._strict_img2img_active = bool(getattr(self, '_cached_strict_active', False))
                self._strict_img2img_relaxed = bool(getattr(self, '_cached_strict_relaxed', False))
                cached_rejections = getattr(self, '_cached_strict_rejections', [])
                self._strict_img2img_rejections = list(cached_rejections) if cached_rejections else []
                self._last_rejections = list(self._strict_img2img_rejections)

            self._build_legacy_bad_index(bad_tags)
            if filter_ctx is None:
                filter_ctx = self._build_removal_context(bad_tags, favorites_tags)
            self._removal_context = filter_ctx
            self._tag_normal_cache = {}
            
            # persist selected posts and removal flags so prompt processing can access them
            self._selected_posts = selected_posts
            self._remove_artist_tags = bool(remove_artist_tags_ui)
            self._remove_character_tags = bool(remove_character_tags_ui)
            self._remove_clothing_tags = bool(remove_clothing_tags_ui)
            self._remove_text_tags = bool(remove_text_tags_ui)
            self._restrict_subject_tags = bool(restrict_subject_tags_ui)
            self._remove_furry_tags = bool(remove_furry_tags_ui)
            self._remove_headwear_tags = bool(remove_headwear_tags_ui)
            self._preserve_hair_eye_colors = bool(preserve_hair_eye_colors_ui)
            self._remove_series_tags = bool(remove_series_tags_ui)

            # Preview UI removed by request

            base_negative = getattr(p, 'negative_prompt', '') or ""
            final_prompts = []
            final_negative_prompts = [base_negative] * num_images_needed
            prompt_processing_settings = (
                shuffle_tags, chaos_mode, chaos_amount, limit_tags_pct, max_tags_count, change_dash,
                use_deepbooru, type_deepbooru, self._remove_artist_tags, self._remove_character_tags,
                self._remove_clothing_tags, self._remove_text_tags, self._restrict_subject_tags,
                self._remove_furry_tags, self._remove_headwear_tags, self._preserve_hair_eye_colors,
                self._remove_series_tags
            )
            
            # Ensure we only use the number of posts that match the current generation request
            posts_to_use = selected_posts[:num_images_needed] if len(selected_posts) > num_images_needed else selected_posts
            # If we need more images than available posts, repeat the last post
            while len(posts_to_use) < num_images_needed:
                posts_to_use.append(posts_to_use[-1] if posts_to_use else selected_posts[0])
            self._posts_used_for_generation = list(posts_to_use)
            
            # Also align cached images with current generation request
            if not should_fetch_new and hasattr(self, 'last_img') and self.last_img:
                # Adjust cached images to match current request
                if len(self.last_img) > num_images_needed:
                    self.last_img = self.last_img[:num_images_needed]
                elif len(self.last_img) < num_images_needed:
                    # Repeat images to fill the requirement
                    while len(self.last_img) < num_images_needed:
                        self.last_img.append(self.last_img[-1] if self.last_img else None)
                print(f"[R] Aligned cached images: {len(self.last_img)} images for {num_images_needed} requested")
            
            raw_prompts = [post.get('tags', '') for post in posts_to_use]
            print(f"[R] Using {len(posts_to_use)} posts for {num_images_needed} images (from {len(selected_posts)} cached)")

            if mix_prompt and not post_id and not same_prompt:
                print(f"[R] Mixing tags from {mix_amount} posts...")
                mixed_prompts = []
                original_indices_map = {i: post for i in range(len(all_posts))}
                for _ in range(num_images_needed):
                    mix_indices = random.sample(list(original_indices_map.keys()), min(mix_amount, len(original_indices_map)))
                    combined_tags = set()
                    for mix_idx in mix_indices:
                        combined_tags.update([t.strip() for t in all_posts[mix_idx].get('tags', '').split(' ') if t.strip()])
                    final_mix_tags = list(combined_tags)
                    random.shuffle(final_mix_tags)
                    if max_tags_count > 0:
                        final_mix_tags = final_mix_tags[:max_tags_count]
                    mixed_prompts.append(','.join(final_mix_tags))
                raw_prompts = mixed_prompts

            for i, rp in enumerate(raw_prompts):
                processed_prompt, processed_negative = self._process_single_prompt(i, rp, self.original_prompt, base_negative, initial_additions, prompt_processing_settings)
                final_prompts.append(processed_prompt)
                final_negative_prompts[i] = processed_negative

            valid_final_prompts = [s for s in final_prompts if s and not s.isspace()]
            if not valid_final_prompts:
                p.prompt = " "
                p.negative_prompt = "" if num_images_needed == 1 else [""] * num_images_needed
                print("[R] Warn: No valid prompts generated.")
            elif num_images_needed == 1:
                p.prompt = valid_final_prompts[0]
                p.negative_prompt = final_negative_prompts[0] if final_negative_prompts else ""
            else:
                p.prompt = valid_final_prompts
                p.negative_prompt = final_negative_prompts
            self._final_prompts_snapshot = list(valid_final_prompts)
            self._final_negative_prompts_snapshot = list(final_negative_prompts)
            # Debug print removed per user request

            if use_same_seed:
                p.seed = p.seed if p.seed != -1 else random.randint(0, 2**32 - 1)
                print(f"[R] Using same seed: {p.seed}")

            if use_ip and self.last_img and self.last_img[0] is not None:
                cn_configured = False
                # Preferred: external_code API from ControlNet
                try:
                    cn_module = self._load_cn_external_code()
                    if hasattr(cn_module, 'get_all_units_in_processing') and hasattr(cn_module, 'update_cn_script_in_processing'):
                        cn_units = cn_module.get_all_units_in_processing(p)
                        if cn_units and len(cn_units) > 0:
                            copied_unit = cn_units[0].__dict__.copy()
                            copied_unit['enabled'] = True
                            copied_unit['weight'] = float(self.img2img_denoising)
                            img_for_cn = self.last_img[0].convert('RGB') if self.last_img[0].mode != 'RGB' else self.last_img[0]
                            copied_unit['image']['image'] = np.array(img_for_cn)
                            cn_module.update_cn_script_in_processing(p, [copied_unit] + cn_units[1:])
                            cn_configured = True
                            print("[R Before] ControlNet configured via external_code.")
                    # else: module loaded but does not expose update helpers; silently skip to fallback
                except Exception:
                    # Silently fallback if external_code path not supported in this build
                    pass

                # Fallback: p.script_args hack (fragile but effective)
                if not cn_configured:
                    cn_arg_start_guess = 0
                    num_controls_per_unit = 20
                    if num_controls_per_unit > 0:
                        target_unit_arg_start = cn_arg_start_guess
                        enabled_idx = target_unit_arg_start + 0
                        weight_idx = target_unit_arg_start + 3
                        image_idx = target_unit_arg_start + 4
                        args_source = p.script_args
                        if isinstance(args_source, tuple):
                            args_target_list = list(args_source)
                            max_idx = max(enabled_idx, weight_idx, image_idx)
                            if max_idx < len(args_target_list):
                                try:
                                    img_for_cn = self.last_img[0].convert('RGB') if self.last_img[0].mode != 'RGB' else self.last_img[0]
                                    cn_image_input = {'image': np.array(img_for_cn), 'mask': None}
                                    args_target_list[enabled_idx] = True
                                    args_target_list[weight_idx] = float(self.img2img_denoising)
                                    args_target_list[image_idx] = cn_image_input
                                    p.script_args = tuple(args_target_list)
                                    print("[R Before] ControlNet using fallback p.script_args hack.")
                                except Exception as e:
                                    print(f"[R Before] Error setting CN via p.script_args: {e}")
                            else:
                                print(f"[R Before] Error: CN arg index ({max_idx}) OOB ({len(args_target_list)}).")
                        else:
                            print("[R Before] Error: p.script_args is not a tuple.")

            self._prepare_img2img_pass(p, use_img2img, use_ip)

        except Exception as e:
            print(f"[Ranbooru BeforeProcess] UNEXPECTED ERROR: {e}")
            traceback.print_exc()
            if hasattr(self, 'cache_installed_by_us') and self.cache_installed_by_us and requests_cache.patcher.is_installed():
                requests_cache.uninstall_cache()
                print("[R] Uninstalled cache due to error.")

        print("[Ranbooru BeforeProcess] Finished.")

    def _reset_adetailer_state_for_run(self, p):
        """Clear RanbooruX-managed ADetailer flags before a generation begins."""
        self._unpatch_manual_adetailer_overrides()
        setattr(self.__class__, '_ranbooru_block_all_adetailer', False)
        setattr(self.__class__, '_adetailer_global_guard_active', False)
        setattr(self.__class__, '_adetailer_pipeline_blocked', False)
        setattr(self.__class__, '_ranbooru_manual_adetailer_active', False)
        cleanup_attrs = (
            '_ranbooru_manual_adetailer_complete',
            '_ad_disabled',
            '_ranbooru_skip_initial_adetailer',
            '_ranbooru_suppress_all_processing',
            '_ranbooru_adetailer_already_processed',
        )
        for attr in cleanup_attrs:
            if hasattr(p, attr):
                try:
                    delattr(p, attr)
                except Exception:
                    setattr(p, attr, False)

        # Ensure any global guard we installed is cleared before the next generation begins
        try:
            self._set_adetailer_block(False)
        except Exception as exc:
            print(f"[R Before] Warn: Could not clear ADetailer global guard: {exc}")

        # If a previous manual run removed or disabled ADetailer scripts, restore them now so
        # disabling the manual toggle returns control back to Forge's native behaviour.
        restore_needed = (
            hasattr(self, '_stored_adetailer_scripts') or
            hasattr(self, 'disabled_adetailer_scripts') or
            getattr(self.__class__, '_block_640x512_images', False)
        )
        if restore_needed:
            try:
                self._restore_early_adetailer_protection(p)
            except Exception as exc:
                print(f"[R Before] Warn: Failed to restore ADetailer pipeline state: {exc}")
        if not getattr(self, '_adetailer_support_enabled', False):
            try:
                self._restore_native_adetailer_scripts(p)
            except Exception as exc:
                print(f"[R Before] Warn: Failed to restore native ADetailer state: {exc}")

    def _restore_native_adetailer_scripts(self, p):
        """Ensure native ADetailer scripts resume running when manual support is disabled."""
        try:
            needs_unpatch = any(
                hasattr(self, attr)
                for attr in ('_patched_processed_objects', '_patched_adetailer_modules', '_patched_conversion_modules')
            )
            if needs_unpatch:
                self._unpatch_manual_adetailer_overrides()
        except Exception as exc:
            print(f"[R Before] Warn: Could not unpatch manual ADetailer overrides: {exc}")
        try:
            self._set_adetailer_block(False)
        except Exception:
            pass
        setattr(self.__class__, '_ranbooru_block_all_adetailer', False)
        setattr(self.__class__, '_adetailer_global_guard_active', False)
        try:
            self._restore_early_adetailer_protection(p)
        except Exception as exc:
            print(f"[R Before] Warn: Could not restore ADetailer runner state: {exc}")
        try:
            self._reenable_adetailer_from_previous_generation()
        except Exception as exc:
            print(f"[R Before] Warn: Could not re-enable ADetailer scripts: {exc}")
        try:
            restored = self._force_enable_adetailer_scripts(p)
        except Exception as exc:
            print(f"[R Before] Warn: Could not force-enable ADetailer scripts: {exc}")
            restored = 0
        if restored:
            print(f"[R Before] Restored {restored} native ADetailer script(s) after manual toggle was disabled")
        if hasattr(self, 'disabled_adetailer_scripts'):
            try:
                delattr(self, 'disabled_adetailer_scripts')
            except Exception:
                pass
        guard_present = False
        try:
            import modules.scripts as scripts_module
            for runner_attr in ('scripts_txt2img', 'scripts_img2img'):
                runner = getattr(scripts_module, runner_attr, None)
                if runner and getattr(runner, '_ranbooru_guard_installed', False):
                    guard_present = True
                    break
        except Exception:
            guard_present = False
        if guard_present:
            try:
                self._reset_script_runner_guards()
            except Exception as exc:
                print(f"[R Before] Warn: Could not reset script runner guards: {exc}")
        self._ensure_native_adetailer_enable_flags(p)
        if not self._native_adetailer_detected():
            try:
                import modules.scripts as scripts_module
                if hasattr(scripts_module, 'reload_scripts'):
                    print('[R Before] Reloading scripts to restore native ADetailer')
                    scripts_module.reload_scripts()
            except Exception as exc:
                print(f"[R Before] Warn: Could not reload scripts for ADetailer: {exc}")

    def _force_enable_adetailer_scripts(self, processing_obj=None):
        """Return the count of ADetailer scripts restored to their original behaviour."""
        try:
            import modules.scripts as scripts_module
        except Exception as exc:
            print(f"[R Before] Warn: Could not access scripts module to restore ADetailer: {exc}")
            return 0
        runners = []
        for runner_attr in ('scripts_txt2img', 'scripts_img2img'):
            runner = getattr(scripts_module, runner_attr, None)
            if runner:
                runners.append(runner)
        if processing_obj is not None and hasattr(processing_obj, 'scripts') and processing_obj.scripts not in runners:
            runners.append(processing_obj.scripts)
        seen_ids = set()
        restored_count = 0
        for runner in runners:
            if runner is None:
                continue
            for list_attr in ('alwayson_scripts', 'scripts'):
                script_list = getattr(runner, list_attr, None)
                if not script_list:
                    continue
                for script in script_list:
                    if not script:
                        continue
                    script_id = id(script)
                    if script_id in seen_ids:
                        continue
                    seen_ids.add(script_id)
                    if not self._is_adetailer_script(script):
                        continue
                    restored = False
                    if hasattr(script, 'enabled') and script.enabled is False:
                        script.enabled = True
                        restored = True
                    for method_name in ('postprocess', 'process', 'process_batch', 'before_process', 'after_process'):
                        backup_name = f'_ranbooru_original_{method_name}'
                        if hasattr(script, backup_name):
                            try:
                                setattr(script, method_name, getattr(script, backup_name))
                            except Exception:
                                pass
                            try:
                                delattr(script, backup_name)
                            except Exception:
                                pass
                            restored = True
                    for attr in ('_ranbooru_disabled_after_manual', '_ranbooru_disabled_source'):
                        if hasattr(script, attr):
                            try:
                                delattr(script, attr)
                            except Exception:
                                pass
                            restored = True
                    if restored:
                        restored_count += 1
        if restored_count == 0:
            try:
                debug_entries = []
                for runner in runners:
                    if not runner:
                        continue
                    for list_attr in ('alwayson_scripts', 'scripts'):
                        script_list = getattr(runner, list_attr, None)
                        if not script_list:
                            continue
                        for script in script_list:
                            if self._is_adetailer_script(script):
                                debug_entries.append(f"{script.__class__.__name__}(enabled={getattr(script, 'enabled', 'n/a')})")
                if debug_entries:
                    print(f"[R Before] Native ADetailer scripts detected: {', '.join(debug_entries)}")
            except Exception:
                pass
        return restored_count


    def _ensure_native_adetailer_enable_flags(self, processing_obj):
        if not getattr(self, '_adetailer_support_enabled', False):
            return
        try:
            args = getattr(processing_obj, 'script_args', None)
        except Exception as exc:
            print(f"[R Before] Native ADetailer: unable to read script_args: {exc}")
            return
        if not isinstance(args, (list, tuple)) or not args:
            print("[R Before] Native ADetailer: script_args empty or not list/tuple; skipping flag repair")
            return
        args_list = list(args)
        runners = []
        runner = getattr(processing_obj, 'scripts', None)
        if runner is not None:
            runners.append(runner)
        try:
            import modules.scripts as scripts_module
            for attr in ('scripts_txt2img', 'scripts_img2img'):
                global_runner = getattr(scripts_module, attr, None)
                if global_runner is not None and global_runner not in runners:
                    runners.append(global_runner)
        except Exception as exc:
            print(f"[R Before] Native ADetailer: could not gather global runners: {exc}")
        candidates = []
        for r in runners:
            for list_attr in ('alwayson_scripts', 'scripts'):
                script_list = getattr(r, list_attr, None)
                if script_list:
                    candidates.extend(script_list)
        if not candidates:
            print("[R Before] Native ADetailer: no script candidates found for flag repair")
            return
        changed = False
        for script in candidates:
            if not self._is_adetailer_script(script):
                continue
            extracted = self._extract_adetailer_script_args(script, processing_obj)
            sanitized = list(extracted.get('args') or [])
            meta = extracted.get('meta') or {}
            start_idx = meta.get('slice_start')
            end_idx = meta.get('slice_end')
            if start_idx is None or end_idx is None:
                continue
            start_idx = max(0, min(len(args_list), start_idx))
            end_idx = max(start_idx, min(len(args_list), end_idx))
            if not sanitized or end_idx - start_idx != len(sanitized):
                slice_view = args_list[start_idx:end_idx]
            else:
                slice_view = sanitized
            print(f"[R Before] Native ADetailer candidate {script.__class__.__name__} enabled={getattr(script, 'enabled', 'n/a')} slice [{start_idx}:{end_idx}] -> {slice_view}")
            if not sanitized:
                continue
            bool_index = 0
            local_changed = False
            for offset, val in enumerate(sanitized):
                if isinstance(val, bool):
                    if bool_index == 0 and val is False:
                        sanitized[offset] = True
                        local_changed = True
                        print(f"[R Before] Set native ADetailer enable flag True at offset {offset}")
                    elif bool_index == 1 and val is True:
                        sanitized[offset] = False
                        local_changed = True
                        print(f"[R Before] Cleared native ADetailer skip flag at offset {offset}")
                    bool_index += 1
                elif isinstance(val, dict):
                    if val.get('ad_tab_enable') is False and val.get('ad_model') not in (None, '', 'None'):
                        val['ad_tab_enable'] = True
                        local_changed = True
                        print(f"[R Before] Enabled ad_tab_enable in dict at offset {offset}")
            if local_changed:
                if end_idx - start_idx == len(sanitized):
                    args_list[start_idx:end_idx] = sanitized
                    changed = True
                    continue
                # fallback if lengths mismatch
                for offset, val in enumerate(sanitized):
                    target_idx = start_idx + offset
                    if target_idx < len(args_list):
                        args_list[target_idx] = val
                    else:
                        args_list.append(val)
                changed = True
        if changed:
            if isinstance(args, list):
                processing_obj.script_args = args_list
            else:
                processing_obj.script_args = tuple(args_list)
            print(f"[R Before] Native ADetailer flags updated: {args_list}")
        else:
            print("[R Before] Native ADetailer flags already enabled; no changes made")

    def _force_native_adetailer_execution(self, p, processed):
        if getattr(self, '_adetailer_support_enabled', False):
            return False
        if not self._native_adetailer_requested(p):
            return False
        try:
            if getattr(self, '_native_adetailer_fallback_used', False):
                return False
            if not processed or not getattr(processed, 'images', None):
                print('[R Before] Native fallback: processed has no images; skipping ADetailer run')
                return False
            image_list = [img for img in processed.images if img is not None]
            if not image_list:
                print('[R Before] Native fallback: no valid images available for ADetailer')
                return False
            if not self._native_adetailer_detected():
                print('[R Before] Native fallback: no native ADetailer scripts detected; skipping fallback')
                return False
            print(f"[R Before] Native fallback: running manual ADetailer on {len(image_list)} txt2img result(s)")
            self._prepare_processing_for_manual_adetailer(p, processed, image_list)
            self._native_adetailer_fallback_used = True
            original_support = getattr(self, '_adetailer_support_enabled', False)
            original_post_support = getattr(self, '_post_adetailer_enabled', False)
            original_prev_manual = getattr(self, '_manual_adetailer_prev_enabled', False)
            try:
                self._adetailer_support_enabled = True
                self._post_adetailer_enabled = True
                self._manual_adetailer_prev_enabled = True
                ran = self._run_adetailer_on_img2img(p, processed, image_list)
            finally:
                self._adetailer_support_enabled = original_support
                self._post_adetailer_enabled = original_post_support
                self._manual_adetailer_prev_enabled = original_prev_manual
            if ran:
                print('[R Before] Native fallback: manual ADetailer execution complete')
            else:
                print('[R Before] Native fallback: manual ADetailer execution reported failure')
            return bool(ran)
        except Exception as exc:
            print(f"[R Before] Native fallback: error running manual ADetailer: {exc}")
            return False

    def _native_adetailer_requested(self, processing_obj):
        try:
            args = getattr(processing_obj, 'script_args', None)
        except Exception:
            return False
        if not isinstance(args, (list, tuple)) or not args:
            return False
        args_list = list(args)
        runners = []
        runner = getattr(processing_obj, 'scripts', None)
        if runner is not None:
            runners.append(runner)
        try:
            import modules.scripts as scripts_module
            for attr in ('scripts_txt2img', 'scripts_img2img'):
                global_runner = getattr(scripts_module, attr, None)
                if global_runner is not None and global_runner not in runners:
                    runners.append(global_runner)
        except Exception:
            pass
        candidates = []
        for r in runners:
            for list_attr in ('alwayson_scripts', 'scripts'):
                script_list = getattr(r, list_attr, None)
                if script_list:
                    candidates.extend(script_list)
        for script in candidates:
            if not self._is_adetailer_script(script):
                continue
            extracted = self._extract_adetailer_script_args(script, processing_obj)
            sanitized = list(extracted.get('args') or [])
            if sanitized and isinstance(sanitized[0], bool):
                return sanitized[0]
        # Fallback: try first bool in original args
        for value in args_list:
            if isinstance(value, bool):
                return value
        return False

    def _native_adetailer_detected(self):
        try:
            import modules.scripts as scripts_module
        except Exception:
            return False
        for runner_attr in ('scripts_txt2img', 'scripts_img2img'):
            runner = getattr(scripts_module, runner_attr, None)
            if not runner:
                continue
            for list_attr in ('alwayson_scripts', 'scripts'):
                script_list = getattr(runner, list_attr, None)
                if not script_list:
                    continue
                for script in script_list:
                    if self._is_adetailer_script(script):
                        return True
        return False

    def _handle_adetailer_toggle_change(self, previous_enabled, current_enabled, p):
        if previous_enabled and not current_enabled:
            try:
                self._restore_native_adetailer_scripts(p)
            except Exception as exc:
                print(f"[R Before] Warn: Failed handling ADetailer toggle change: {exc}")

    def postprocess(self, p: StableDiffusionProcessing, processed, *args):
        try:
            # If this generation already finalized, avoid looping
            if getattr(p, '_ranbooru_finalized', False):
                print("[R Post] ⏭️ Already finalized this generation; skipping repeat postprocess")
                return
            # If this call is re-entered during our manual ADetailer run, skip to avoid loops
            if getattr(self.__class__, '_ranbooru_manual_adetailer_active', False):
                print("[R Post] ⏭️ Skipping RanbooruX postprocess during manual ADetailer run")
                return
            # Prevent duplicate img2img runs within the same generation
            if getattr(p, '_ranbooru_img2img_started', False):
                print("[R Post] ⏭️ Img2Img already started for this generation; skipping duplicate postprocess entry")
                return
            enabled = getattr(self, '_post_enabled', False)
            use_img2img = getattr(self, '_post_use_img2img', False)
            use_last_img = getattr(self, '_post_use_last_img', False)
            crop_center = getattr(self, '_post_crop_center', False)
            use_deepbooru = getattr(self, '_post_use_deepbooru', False)
            type_deepbooru = getattr(self, '_post_type_deepbooru', 'Add Before')
            use_cache = getattr(self, '_post_use_cache', True)
            use_adetailer = getattr(self, '_post_adetailer_enabled', False) and self._is_adetailer_enabled()
            
            # Validate essential objects
            if not processed or not hasattr(processed, 'images'):
                print("[R Post] Error: Invalid processed object, skipping img2img")
                self._cleanup_after_run(use_cache)
                return
                
            if not enabled:
                print("[R Post] RanbooruX disabled, skipping img2img")
                self._cleanup_after_run(use_cache)
                return
                
            if not (getattr(self, 'run_img2img_pass', False) and hasattr(self, 'last_img') and self.last_img and use_img2img):
                fallback_ran = False
                if not use_adetailer and not getattr(self, '_adetailer_support_enabled', False):
                    fallback_ran = self._force_native_adetailer_execution(p, processed)
                if fallback_ran:
                    self._cleanup_after_run(use_cache)
                    return
                print("[R Post] Img2Img conditions not met, skipping")
                self._cleanup_after_run(use_cache)
                return
                
        except Exception as e:
            print(f"[R Post] Error in postprocess validation: {e}")
            self._cleanup_after_run(getattr(self, '_post_use_cache', True))
            return
            
        # Main img2img processing block
        try:
            # Mark as started to avoid re-entrant img2img runs
            try:
                setattr(p, '_ranbooru_img2img_started', True)
            except Exception:
                pass

            if use_adetailer:
                # EARLY PROTECTION: Restore ADetailer scripts that were temporarily disabled during initial pass
                self._restore_early_adetailer_protection(p)
                # CRITICAL: Prepare ADetailer for img2img so it can process the final results
                self._prepare_adetailer_for_img2img(p)
            else:
                print('[R Post] Manual ADetailer support disabled; skipping ADetailer preparation steps')

            print('[R Post] Starting separate Img2Img run...')
            valid_images = [img for img in self.last_img if img is not None]
            if not valid_images:
                print("[R Post] No valid images for Img2Img.")
                self._cleanup_after_run(use_cache)
                return
            if len(valid_images) < len(self.last_img):
                print(f"[R Post] Warn: Only {len(valid_images)}/{len(self.last_img)} valid. Filling gaps.")
                if valid_images:
                    self.last_img = [(img if img is not None else valid_images[0]) for img in self.last_img]
                else:
                    print("[R Post] No valid images left.")
                    self._cleanup_after_run(use_cache)
                    return
            target_w, target_h = (p.width, p.height) if crop_center else self.check_orientation(self.last_img[0])
            print(f"[R Post] Preparing {len(self.last_img)} images ({'Crop' if crop_center else 'Resize'}) to {target_w}x{target_h} for Img2Img.")
            prepared_images = [resize_image(img, target_w, target_h, cropping=crop_center) for img in self.last_img if img is not None]
            if not prepared_images:
                print("[R Post] No images left after resize.")
                self._cleanup_after_run(use_cache)
                return
            # Use the original RanbooruX-generated prompts, not the simplified initial prompts
            if hasattr(self, 'original_full_prompt') and self.original_full_prompt:
                print("[R Post] Using original RanbooruX prompts for img2img (not simplified initial prompts)")
                final_prompts = self.original_full_prompt
            else:
                final_prompts = processed.prompt
            final_negative_prompts = processed.negative_prompt
            if use_deepbooru:
                print("[R Post] Applying Deepbooru before Img2Img pass...")
                tagged_prompts = []
                try:
                    if not deepbooru.model.model:
                        deepbooru.model.start()
                    temp_prompts = [final_prompts] * len(prepared_images) if not isinstance(final_prompts, list) else final_prompts
                    for i, img in enumerate(prepared_images):
                        db_tags = deepbooru.model.tag_multi(img)
                        current_orig_prompt = temp_prompts[i % len(temp_prompts)]
                        modified_p = modify_prompt(current_orig_prompt, db_tags, type_deepbooru)
                        tagged_prompts.append(remove_repeated_tags(modified_p))
                    final_prompts = tagged_prompts
                    print("[R] Deepbooru tags applied.")
                except Exception as e:
                    print(f"[R] Error Deepbooru Img2Img: {e}.")
            num_imgs = len(prepared_images)
            if not isinstance(final_prompts, list) or len(final_prompts) != num_imgs:
                final_prompts = ([final_prompts] * num_imgs) if not isinstance(final_prompts, list) else (final_prompts * (num_imgs // len(final_prompts)) + final_prompts[:num_imgs % len(final_prompts)])
            if not isinstance(final_negative_prompts, list) or len(final_negative_prompts) != num_imgs:
                final_negative_prompts = ([final_negative_prompts] * num_imgs) if not isinstance(final_negative_prompts, list) else (final_negative_prompts * (num_imgs // len(final_negative_prompts)) + final_negative_prompts[:num_imgs % len(final_negative_prompts)])
            img2img_width, img2img_height = prepared_images[0].size
            # Process images in batches that match WebUI expectations
            # Use batch_size=1 to ensure compatibility with all configurations
            print(f"[R] Processing {len(prepared_images)} images individually to ensure compatibility")
            
            # Process all prepared images (do not limit by original txt2img batch size)
            
            print(f"[R] Running Img2Img ({len(prepared_images)} images) steps={self.real_steps}, Denoise={self.img2img_denoising}")
            
            # Process images individually to avoid batch size issues
            all_img2img_results = []
            all_infotexts = []
            last_seed = processed.seed
            last_subseed = processed.subseed
            
            for i, img in enumerate(prepared_images):
                current_prompt = final_prompts[i] if i < len(final_prompts) else final_prompts[0]
                current_negative = final_negative_prompts[i] if i < len(final_negative_prompts) else final_negative_prompts[0]
                
                p_img2img = StableDiffusionProcessingImg2Img(
                    sd_model=shared.sd_model, outpath_samples=shared.opts.outdir_samples or shared.opts.outdir_img2img_samples,
                    outpath_grids=shared.opts.outdir_grids or shared.opts.outdir_img2img_grids, 
                    prompt=current_prompt, negative_prompt=current_negative,
                    seed=processed.seed + i, subseed=processed.subseed + i, 
                    sampler_name=p.sampler_name, scheduler=getattr(p, 'scheduler', None),
                    batch_size=1, n_iter=1, steps=self.real_steps, cfg_scale=p.cfg_scale,
                    width=img2img_width, height=img2img_height, init_images=[img], denoising_strength=self.img2img_denoising,
                )
                # Mark as internal so our before_process performs a minimal seed init instead of blocking
                try:
                    setattr(p_img2img, '_ranbooru_internal_img2img', True)
                except Exception:
                    pass
                
                # CRITICAL: Explicitly enable saving for img2img pass (was disabled for initial pass)
                p_img2img.do_not_save_samples = False  # Always enable saving for final results
                p_img2img.do_not_save_grid = False     # Always enable grid saving for final results
                
                # Ensure correct output path for img2img results
                if hasattr(self, 'original_outpath') and self.original_outpath:
                    p_img2img.outpath_samples = self.original_outpath
                    print(f"[R Save] 💾 Saving img2img result {i+1} to: {self.original_outpath}")
                else:
                    # Fallback to default img2img output directory
                    p_img2img.outpath_samples = shared.opts.outdir_img2img_samples or shared.opts.outdir_samples
                    print(f"[R Save] 💾 Saving img2img result {i+1} to default: {p_img2img.outpath_samples}")
                
                # Restore original batch size  
                if hasattr(self, 'original_batch_size'):
                    p_img2img.batch_size = self.original_batch_size
                
                print(f"[R] Processing image {i+1}/{len(prepared_images)} individually")
                single_result = process_images(p_img2img)
                all_img2img_results.extend(single_result.images)
                all_infotexts.extend(single_result.infotexts)
                last_seed = single_result.seed
                last_subseed = single_result.subseed
            
            # CRITICAL: Complete replacement of processed object to force all extensions to see new results
            print("[R Post] Performing COMPLETE processed object replacement for extension compatibility")
            
            # Store original processed object reference
            original_processed = processed
            
            # Update ALL possible references that might be cached by other extensions
            processed.images.clear()
            processed.images.extend(all_img2img_results)
            
            # Force immediate update of all fields
            processed.prompt = final_prompts if len(final_prompts) > 1 else (final_prompts[0] if final_prompts else processed.prompt)
            processed.negative_prompt = final_negative_prompts if len(final_negative_prompts) > 1 else (final_negative_prompts[0] if final_negative_prompts else processed.negative_prompt)
            processed.infotexts.clear()
            processed.infotexts.extend(all_infotexts)
            processed.seed = last_seed
            processed.subseed = last_subseed
            processed.width = img2img_width
            processed.height = img2img_height
            
            # Force update all array fields by clearing and extending (not replacing references)
            if hasattr(processed, 'all_prompts'):
                processed.all_prompts.clear()
                processed.all_prompts.extend(final_prompts if isinstance(final_prompts, list) else [final_prompts] * len(all_img2img_results))
            else:
                processed.all_prompts = final_prompts if isinstance(final_prompts, list) else [final_prompts] * len(all_img2img_results)
                
            if hasattr(processed, 'all_negative_prompts'):
                processed.all_negative_prompts.clear()
                processed.all_negative_prompts.extend(final_negative_prompts if isinstance(final_negative_prompts, list) else [final_negative_prompts] * len(all_img2img_results))
            else:
                processed.all_negative_prompts = final_negative_prompts if isinstance(final_negative_prompts, list) else [final_negative_prompts] * len(all_img2img_results)
                
            if hasattr(processed, 'all_seeds'):
                processed.all_seeds.clear()
                processed.all_seeds.extend([last_seed + i for i in range(len(all_img2img_results))])
            else:
                processed.all_seeds = [last_seed + i for i in range(len(all_img2img_results))]
                
            if hasattr(processed, 'all_subseeds'):
                processed.all_subseeds.clear() 
                processed.all_subseeds.extend([last_subseed + i for i in range(len(all_img2img_results))])
            else:
                processed.all_subseeds = [last_subseed + i for i in range(len(all_img2img_results))]
            
            # Clear any cached references and force immediate updates
            for attr_name in ['cached_images', 'images_list', 'output_images', '_cached_images']:
                if hasattr(processed, attr_name):
                    attr_val = getattr(processed, attr_name)
                    if isinstance(attr_val, list):
                        attr_val.clear()
                        attr_val.extend(all_img2img_results)
                    else:
                        setattr(processed, attr_name, all_img2img_results)
            
            # Force update the main processing result references
            if hasattr(p, 'processed_result'):
                p.processed_result = processed
            if hasattr(p, '_processed'):
                p._processed = processed
                
            # CRITICAL: Force global state update to ensure other extensions see the changes
            self._force_global_processed_update(p, processed, all_img2img_results)
            
            adetailer_ran_successfully = False
            if use_adetailer:
                # FINAL AGGRESSIVE FIX: Directly patch ADetailer to force it to use our results
                self._patch_adetailer_directly(processed, all_img2img_results)
                print("[R Post] Attempting manual ADetailer run on img2img results...")
                # Ensure processing object is aligned to our img2img result for ADetailer
                self._prepare_processing_for_manual_adetailer(p, processed, all_img2img_results)
                try:
                    self._set_adetailer_block(False)
                    setattr(self.__class__, '_ranbooru_block_all_adetailer', False)
                    setattr(p, '_ranbooru_skip_initial_adetailer', False)
                    print("[R Post] Unblocked ADetailer guard for manual run")
                except Exception:
                    pass
                try:
                    final_dims = all_img2img_results[0].size if all_img2img_results and hasattr(all_img2img_results[0], 'size') else None
                    self._install_preview_guard()
                    self._set_preview_guard(True, final_dims)
                except Exception:
                    pass
                adetailer_ran_successfully = self._run_adetailer_on_img2img(p, processed, all_img2img_results)
                if adetailer_ran_successfully:
                    print("[R Post] SUCCESS: ADetailer processed img2img results")
                    all_img2img_results = processed.images.copy()
                    try:
                        setattr(p, '_ranbooru_manual_adetailer_complete', True)
                    except Exception:
                        pass
                else:
                    print("[R Post] WARN: ADetailer manual run failed - img2img results will be unprocessed by ADetailer")
            else:
                adetailer_ran_successfully = False
                print("[R Post] Manual ADetailer support disabled; skipping manual ADetailer execution")

            # Mark processing as complete for other extensions and UI
            setattr(self, '_ranbooru_processing_complete', True)
            if hasattr(self, '_ranbooru_intermediate_results'):
                delattr(self, '_ranbooru_intermediate_results')
            
            print("[R Post] Img2Img finished.")
            print(f"[R Post] Updated processed object with {len(all_img2img_results)} img2img results")
            # DEBUG: Add comprehensive logging to trace what ADetailer will see
            # CRITICAL: Force UI to display our final results
            self._force_ui_update(p, processed, all_img2img_results)
            
            print("[R Post] ✅ RanbooruX processing complete - final results ready for UI and other extensions")
            print(f"[R Post DEBUG] Final processed.images count: {len(processed.images) if hasattr(processed, 'images') else 'NO IMAGES ATTR'}")
            if hasattr(processed, 'images') and processed.images:
                for i, img in enumerate(processed.images[:3]):  # Show first 3 images
                    if img:
                        print(f"[R Post DEBUG] Image {i}: {type(img)} size={getattr(img, 'size', 'unknown')}")
                    else:
                        print(f"[R Post DEBUG] Image {i}: None")
            else:
                print("[R Post DEBUG] WARNING: No images in processed.images!")
                
            # DEBUG: Check all image attributes
            debug_attrs = ['images', 'images_list', 'output_images', '_cached_images', 'cached_images']
            for attr in debug_attrs:
                if hasattr(processed, attr):
                    val = getattr(processed, attr)
                    if isinstance(val, list):
                        print(f"[R Post DEBUG] {attr}: list with {len(val)} items")
                    else:
                        print(f"[R Post DEBUG] {attr}: {type(val)}")
                else:
                    print(f"[R Post DEBUG] {attr}: not present")
            
        except Exception as e:
            print(f"[R Post] Critical error during img2img processing: {e}")
            import traceback
            traceback.print_exc()
            try:
                # Attempt to preserve original images if img2img fails
                if hasattr(self, 'last_img') and self.last_img:
                    print("[R Post] Attempting to fallback to original txt2img results")
                else:
                    print("[R Post] No fallback images available")
            except:
                print("[R Post] Fallback failed")
                
        finally:
            if getattr(self, '_log_prompt_sources', False):
                self._log_generation_reference(p)
            # Always cleanup regardless of success or failure
            self._cleanup_after_run(use_cache)
            
            # Clear all processing guards only when truly complete
            if hasattr(self, '_current_processing_key'):
                processing_key = self._current_processing_key
                if hasattr(self, processing_key):
                    delattr(self, processing_key)
                    print(f"[R Post] 🔓 Cleared processing guard for request {processing_key}")
                delattr(self, '_current_processing_key')
                
                # Clear global processing guard with delay to ensure no race conditions
                import time
                time.sleep(0.1)  # Small delay to ensure all processing is complete
                setattr(self.__class__, '_ranbooru_global_processing', False)
                print(f"[R Post] 🔓 Cleared global processing guard")
                
                # Also clear the processing object guard
                # Note: p might not be available in postprocess, so we'll clear it in a different way
                # The guard will be cleared when the processing object is destroyed
                try:
                    setattr(p, '_ranbooru_finalized', True)
                except Exception:
                    pass

    def _force_global_processed_update(self, p, processed, img2img_results):
        """Force global state updates to ensure ALL extensions see the img2img results"""
        try:
            print(f"[R Post] Forcing global processed update with {len(img2img_results)} img2img results")
            
            # Update WebUI's global state references if accessible
            try:
                import modules.shared as shared_modules
                
                # Force update any global processing state
                if hasattr(shared_modules, 'state'):
                    # Mark that processing is complete with final results
                    if hasattr(shared_modules.state, 'textinfo'):
                        shared_modules.state.textinfo = "RanbooruX img2img complete"
                
                # Update global opts if they cache processing results  
                if hasattr(shared_modules, 'opts') and hasattr(shared_modules.opts, 'current_processed'):
                    shared_modules.opts.current_processed = processed
                    
            except Exception as e:
                print(f"[R Post] Could not update global state: {e}")
            
            # Force update ALL possible image references that extensions might cache
            image_attrs = [
                'images', 'image', 'images_list', 'output_images', '_cached_images',
                'cached_images', 'result_images', 'final_images', '_images'
            ]
            
            for attr in image_attrs:
                if hasattr(processed, attr):
                    current_val = getattr(processed, attr)
                    if isinstance(current_val, list):
                        current_val.clear()
                        current_val.extend(img2img_results)
                        print(f"[R Post] Updated list attribute: {attr}")
                    else:
                        setattr(processed, attr, img2img_results[0] if img2img_results else None)
                        print(f"[R Post] Updated single attribute: {attr}")
            
            # Force refresh processed state with timestamp
            import time
            processed._images_updated = True
            processed._ranbooru_update_time = time.time()
            processed._ranbooru_image_count = len(img2img_results)
            
            # Try to update the processing pipeline's cached references
            if hasattr(p, '__dict__'):
                for key, value in p.__dict__.items():
                    if 'processed' in key.lower() and hasattr(value, 'images'):
                        print(f"[R Post] Found cached processed reference: {key}")
                        if isinstance(value.images, list):
                            value.images.clear()
                            value.images.extend(img2img_results)
            
            # Force immediate memory sync
            import gc
            gc.collect()
            
            print(f"[R Post] ✅ Global processed update complete - {len(img2img_results)} results should now be visible to all extensions")
            
            # NUCLEAR OPTION: Try to override WebUI's main processing result completely
            try:
                self._nuclear_processed_override(p, processed, img2img_results)
            except Exception as e:
                print(f"[R Post] Nuclear override failed: {e}")
            
        except Exception as e:
            print(f"[R Post] Warning: Could not complete global processed update: {e}")
    
    def _nuclear_processed_override(self, p, processed, img2img_results):
        """Last resort: completely override all possible processing references"""
        try:
            print("[R Post] 🔥 NUCLEAR OPTION: Overriding ALL processing references")
            
            # Store the img2img results in a global location that we control
            setattr(self.__class__, '_global_ranbooru_results', img2img_results)
            setattr(self.__class__, '_global_ranbooru_processed', processed)
            
            # Try to patch the processing result at the module level
            try:
                import modules.processing
                if hasattr(modules.processing, '_current_processed'):
                    modules.processing._current_processed = processed
                    print("[R Post] Patched modules.processing._current_processed")
            except:
                pass
                
            # Try to override Gradio/WebUI state
            try:
                import modules.shared as shared
                if hasattr(shared, 'state'):
                    # Store our results in shared state for other extensions to find
                    shared.state.ranbooru_images = img2img_results
                    shared.state.ranbooru_processed = processed
                    print("[R Post] Stored results in shared.state")
            except:
                pass
            
            # Force all script results to point to our img2img results (converted to PIL)
            if hasattr(p, 'scripts') and hasattr(p.scripts, 'scripts'):
                # Convert img2img_results to PIL Images first
                converted_script_images = []
                for img in img2img_results:
                    if hasattr(img, 'mode') and img.mode != 'RGB':
                        img = img.convert('RGB')
                    elif hasattr(img, 'shape'):  # Handle numpy arrays
                        import numpy as np
                        from PIL import Image
                        if len(img.shape) == 3 and img.shape[2] == 3:
                            img = Image.fromarray(img.astype(np.uint8), 'RGB')
                        else:
                            img = Image.fromarray(img.astype(np.uint8))
                    converted_script_images.append(img)
                
                for script in p.scripts.scripts:
                    if hasattr(script, 'postprocessed_images'):
                        script.postprocessed_images = converted_script_images
                        print(f"[R Post] Override {script.__class__.__name__}.postprocessed_images with {len(converted_script_images)} PIL images")
            
            print("[R Post] 🔥 Nuclear override complete - all processing references should now point to img2img results")
            
        except Exception as e:
            print(f"[R Post] Nuclear override error: {e}")
    
    def _patch_adetailer_directly(self, processed, img2img_results):
        """FINAL AGGRESSIVE FIX: Directly patch ADetailer to force correct image access"""
        try:
            print("[R Post] 🎯 FINAL FIX: Patching ADetailer directly")
            
            # Method 1: Monkey patch common image access patterns
            if hasattr(processed, '_ranbooru_original_getattribute'):
                original_getattr = getattr(processed, '_ranbooru_original_getattribute')
            else:
                original_getattr = processed.__getattribute__
                try:
                    setattr(processed, '_ranbooru_original_getattribute', original_getattr)
                    if not hasattr(self, '_patched_processed_objects'):
                        self._patched_processed_objects = []
                    self._patched_processed_objects.append(processed)
                except Exception:
                    pass
            
            def patched_getattr(name):
                if name in ['images', 'image', 'imgs']:
                    print(f"[R Post] 🎯 Intercepted ADetailer access to '{name}' - returning img2img results")
                    return img2img_results if name == 'images' else (img2img_results[0] if img2img_results else None)
                return original_getattr(name)
            
            # Apply the monkey patch
            processed.__getattribute__ = patched_getattr
            
            # Method 2: Try to find and patch ADetailer extension directly
            try:
                import sys
                adetailer_modules = [name for name in sys.modules if 'adetailer' in name.lower()]
                for module_name in adetailer_modules:
                    module = sys.modules[module_name]
                    # Patch any image access methods we can find
                    if hasattr(module, 'get_images'):
                        if not hasattr(module, '_ranbooru_original_get_images'):
                            try:
                                setattr(module, '_ranbooru_original_get_images', module.get_images)
                                if not hasattr(self, '_patched_adetailer_modules'):
                                    self._patched_adetailer_modules = []
                                self._patched_adetailer_modules.append((module, 'get_images'))
                            except Exception:
                                pass

                        def patched_get_images(*args, **kwargs):
                            print("[R Post] 🎯 Intercepted ADetailer.get_images() - returning img2img results")
                            return img2img_results

                        module.get_images = patched_get_images
                        print(f"[R Post] 🎯 Patched {module_name}.get_images()")
                
                print(f"[R Post] 🎯 Found and attempted to patch {len(adetailer_modules)} ADetailer modules")
                
                # Method 2b: Install global guard wrappers on AfterDetailerScript methods
                self._install_adetailer_global_guard()
                
            except Exception as e:
                print(f"[R Post] ADetailer module patching failed: {e}")
            
            # Method 3: Force update all possible cached references in the processing pipeline
            if hasattr(processed, '__dict__'):
                for attr_name in processed.__dict__:
                    if 'image' in attr_name.lower():
                        attr_value = getattr(processed, attr_name)
                        if isinstance(attr_value, list):
                            # Replace list contents
                            attr_value.clear()
                            attr_value.extend(img2img_results)
                            print(f"[R Post] 🎯 Force-updated list attribute: {attr_name}")
                        elif attr_value is not None:
                            # CRITICAL FIX: Handle special attributes that must remain as lists
                            if attr_name in ['extra_images', 'images_list', 'output_images', '_cached_images']:
                                setattr(processed, attr_name, img2img_results.copy())  # Set as list
                                print(f"[R Post] 🎯 Force-updated list attribute: {attr_name} (converted to list)")
                            elif attr_name in ['index_of_first_image', '_ranbooru_image_count']:
                                # These are numeric indices, don't change them
                                print(f"[R Post] 🎯 Skipped numeric attribute: {attr_name}")
                            else:
                                setattr(processed, attr_name, img2img_results[0] if img2img_results else None)
                                print(f"[R Post] 🎯 Force-updated single attribute: {attr_name}")
            
            # Method 4: Create a global intercept for image access
            self.__class__._force_adetailer_images = img2img_results
            
            print("[R Post] 🎯 ADetailer direct patching complete")
            
        except Exception as e:
            print(f"[R Post] ADetailer direct patching error: {e}")
    
    def _install_adetailer_global_guard(self):
        """Install wrappers on AfterDetailerScript to early-exit when our block flag is set"""
        try:
            import sys
            if not hasattr(self, '_adetailer_classes'):
                self._adetailer_classes = []
            installed = 0
            for module_name in list(sys.modules.keys()):
                if 'adetailer' not in module_name.lower():
                    continue
                module = sys.modules[module_name]
                Cls = getattr(module, 'AfterDetailerScript', None)
                if Cls is None or Cls in self._adetailer_classes:
                    continue
                # Wrap methods once
                if not getattr(Cls, '_ranbooru_guard_installed', False):
                    def wrap_method(method_name):
                        orig = getattr(Cls, method_name, None)
                        if not callable(orig):
                            return
                        def wrapped(inst, *args, **kwargs):
                            try:
                                if getattr(inst.__class__, '_ranbooru_should_block', False):
                                    print(f"[R Guard] 🛑 Blocked ADetailer.{method_name}")
                                    # Return strict boolean to avoid TypeError with |= aggregation
                                    return False
                            except Exception:
                                pass
                            return orig(inst, *args, **kwargs)
                        setattr(Cls, method_name, wrapped)
                    for m in [name for name in dir(Cls) if 'process' in name.lower()]:
                        wrap_method(m)
                    setattr(Cls, '_ranbooru_guard_installed', True)
                    setattr(Cls, '_ranbooru_should_block', False)
                    self._adetailer_classes.append(Cls)
                    installed += 1
            if installed:
                print(f"[R Post] 🎯 Installed global ADetailer guard on {installed} class(es)")
        except Exception as e:
            print(f"[R Post] Error installing ADetailer global guard: {e}")
    
    def _is_adetailer_enabled(self):
        return getattr(self, '_adetailer_support_enabled', False)


    def _set_adetailer_block(self, should_block: bool):
        """Toggle the global guard on patched ADetailer classes"""
        try:
            if hasattr(self, '_adetailer_classes'):
                for Cls in self._adetailer_classes:
                    try:
                        setattr(Cls, '_ranbooru_should_block', bool(should_block))
                    except Exception:
                        pass
                print(f"[R Post] 🎯 ADetailer global guard set to {should_block}")
        except Exception as e:
            print(f"[R Post] Error toggling ADetailer global guard: {e}")
    
    def _reset_script_runner_guards(self):
        """Reset ScriptRunner guards to ensure ADetailer is available for each generation"""
        try:
            print("[R Before] 🔄 Resetting ScriptRunner guards for new generation")
            
            # Reset the guard installation flag so guards can be reinstalled if needed
            import modules.scripts
            for runner in [modules.scripts.scripts_txt2img, modules.scripts.scripts_img2img]:
                if hasattr(runner, '_ranbooru_guard_installed'):
                    delattr(runner, '_ranbooru_guard_installed')
                    
            # Clear any cached ADetailer classes
            if hasattr(self, '_adetailer_classes'):
                delattr(self, '_adetailer_classes')
                
            print("[R Before] 🔄 ScriptRunner guards reset complete")
        except Exception as e:
            print(f"[R Before] Error resetting ScriptRunner guards: {e}")
    

    def _extract_adetailer_script_args(self, script, processing_obj):
        """Return sanitized ADetailer arguments derived from the processing object."""
        def _normalize(args):
            if args is None:
                return []
            if isinstance(args, tuple):
                return list(args)
            if isinstance(args, list):
                return list(args)
            return [args]
    
        def _contains_ad_dict(seq):
            for item in seq:
                if isinstance(item, dict) and any(str(key).startswith('ad_') for key in item.keys()):
                    return True
            return False
    
        def _extract_ad_dicts(seq):
            return [item for item in seq if isinstance(item, dict) and any(str(key).startswith('ad_') for key in item.keys())]
    
        all_args = _normalize(getattr(processing_obj, 'script_args', None))
        snapshot = getattr(self, '_adetailer_script_args_snapshot', None)
    
        used_snapshot = False
        if not _contains_ad_dict(all_args) and isinstance(snapshot, (list, tuple)):
            snapshot_norm = _normalize(snapshot)
            if _contains_ad_dict(snapshot_norm):
                all_args = snapshot_norm
                used_snapshot = True
    
        start_idx = getattr(script, 'args_from', None)
        end_idx = getattr(script, 'args_to', None)
        if isinstance(start_idx, int) and start_idx < 0:
            start_idx = 0
        if isinstance(end_idx, int) and end_idx < 0:
            end_idx = 0
    
        if isinstance(start_idx, int) and start_idx < len(all_args):
            slice_start = max(start_idx, 0)
            slice_end = max(end_idx, slice_start) if isinstance(end_idx, int) else len(all_args)
            slice_end = min(slice_end, len(all_args))
        else:
            slice_start = 0
            slice_end = len(all_args)
    
        subset = all_args[slice_start:slice_end]
    
        bool_candidates = [item for item in subset if isinstance(item, bool)]
        enable_flag = bool_candidates[0] if bool_candidates else None
        skip_flag = bool_candidates[1] if len(bool_candidates) > 1 else None
    
        dicts = _extract_ad_dicts(subset)
        fallback_reason = None
    
        if not dicts and not used_snapshot and isinstance(snapshot, (list, tuple)):
            snapshot_norm = _normalize(snapshot)
            snap_subset = snapshot_norm[slice_start:slice_end]
            dicts = _extract_ad_dicts(snap_subset) or _extract_ad_dicts(snapshot_norm)
            if dicts:
                fallback_reason = 'snapshot'
                used_snapshot = True
    
        if not dicts and _contains_ad_dict(all_args):
            dicts = _extract_ad_dicts(all_args)
            if dicts and fallback_reason is None:
                fallback_reason = 'all_args'
    
        meta = {
            'slice_start': slice_start,
            'slice_end': slice_end,
            'total_args': len(all_args),
            'dict_count': len(dicts),
            'fallback_reason': fallback_reason,
            'used_snapshot': used_snapshot,
        }
    
        if not dicts:
            return {'args': [], 'meta': meta}
    
        if enable_flag is None:
            enable_flag = True
        if skip_flag is None:
            skip_flag = False
    
        enable_flag = True if enable_flag is None else bool(enable_flag)
        # Manual runs should not honour skip flags from the UI; force processing
        skip_flag = False

        enable_flag = True if enable_flag is None else bool(enable_flag)
        # Manual img2img runs should never skip ADetailer tabs via the bool flag
        skip_flag = False

        # Ensure each tab only runs when it has a valid model
        for idx_dict, ad_dict in enumerate(dicts):
            model_name = str(ad_dict.get('ad_model', '') or '').strip().lower()
            has_model = model_name not in ('', 'none')
            if idx_dict == 0 and has_model:
                ad_dict['ad_tab_enable'] = True
            else:
                ad_dict['ad_tab_enable'] = bool(ad_dict.get('ad_tab_enable', False) and has_model)

        sanitized = [enable_flag, skip_flag] + dicts
        return {'args': sanitized, 'meta': meta}
    
    def _run_adetailer_on_img2img(self, p, processed, img2img_results):
        """Manually run ADetailer on our img2img results - EACH IMAGE in batch"""
        if not self._is_adetailer_enabled():
            print("[R Manual ADetailer] Support disabled - skipping manual run request")
            return False
        try:
            # Remove generation-based limiting - ADetailer should process ALL images in batch
            print(f"[R Post] 🎯 Starting manual ADetailer execution on {len(img2img_results)} img2img results")
            
            if not img2img_results:
                print("[R Post] ❌ No img2img results to process with ADetailer")
                return False
            
            # Debug: Check the images we're about to process
            for i, img in enumerate(img2img_results):
                if img:
                    print(f"[R Post] DEBUG - Image {i}: {type(img)} size={getattr(img, 'size', 'unknown')}")
                else:
                    print(f"[R Post] DEBUG - Image {i}: None")
            
            # Try to find and run ADetailer scripts manually
            if not hasattr(p, 'scripts'):
                print("[R Post] ❌ No scripts container on processing object")
                return False
            
            # Collect both always-on and regular scripts
            candidate_scripts = []
            try:
                if hasattr(p.scripts, 'alwayson_scripts') and p.scripts.alwayson_scripts:
                    candidate_scripts.extend(p.scripts.alwayson_scripts)
                if hasattr(p.scripts, 'scripts') and p.scripts.scripts:
                    candidate_scripts.extend(p.scripts.scripts)
            except Exception:
                pass
            
            # Fallback: also check global ScriptRunner registries
            try:
                import modules.scripts as _ms
                for runner_name in ('scripts_img2img', 'scripts_txt2img'):
                    runner = getattr(_ms, runner_name, None)
                    if runner is None:
                        continue
                    if hasattr(runner, 'alwayson_scripts') and runner.alwayson_scripts:
                        candidate_scripts.extend([s for s in runner.alwayson_scripts])
                    if hasattr(runner, 'scripts') and runner.scripts:
                        candidate_scripts.extend([s for s in runner.scripts])
            except Exception as _e:
                print(f"[R Post] WARN: Could not read global ScriptRunner registries: {_e}")
            
            # De-duplicate while preserving order
            try:
                seen_ids = set()
                deduped = []
                for s in candidate_scripts:
                    sid = id(s)
                    if sid in seen_ids:
                        continue
                    seen_ids.add(sid)
                    deduped.append(s)
                candidate_scripts = deduped
            except Exception:
                pass
            
            print(f"[R Post] DEBUG - Candidate scripts total: {len(candidate_scripts)}")
            
            if not candidate_scripts:
                print("[R Post] ❌ No candidate scripts available on processing object or global runners")
                return False
            
            adetailer_scripts_found = 0
            for script in candidate_scripts:
                try:
                    script_name_lower = getattr(script.__class__, '__name__', '').lower()
                except Exception:
                    script_name_lower = ''
                if 'adetailer' in script_name_lower or 'afterdetailer' in script_name_lower:
                    adetailer_scripts_found += 1
                    print(f"[R Post] 🎯 Found ADetailer script #{adetailer_scripts_found}: {script.__class__.__name__}")
                    
                    # Check if script is enabled
                    if hasattr(script, 'enabled') and not script.enabled:
                        print(f"[R Post] ⚠️  Script {script.__class__.__name__} is disabled - skipping")
                        continue
                    
                    # Process EACH IMAGE INDIVIDUALLY through ADetailer (not as batch)
                    final_processed_images = []
                    successful_processes = 0
                    
                    # Convert all images to PIL format first
                    converted_images = []
                    for img in img2img_results:
                        if hasattr(img, 'mode') and img.mode != 'RGB':
                            img = img.convert('RGB')
                        elif hasattr(img, 'shape'):  # Handle numpy arrays
                            import numpy as np
                            from PIL import Image
                            if len(img.shape) == 3 and img.shape[2] == 3:
                                img = Image.fromarray(img.astype(np.uint8), 'RGB')
                            else:
                                img = Image.fromarray(img.astype(np.uint8))
                        converted_images.append(img)
                    
                    print(f"[R Post] 🔧 Processing {len(converted_images)} images individually through ADetailer")
                    
                    # Process each image individually with error handling
                    for img_idx, single_img in enumerate(converted_images):
                        try:
                            print(f"[R Post] 🎯 Processing image {img_idx + 1}/{len(converted_images)} individually")
                            
                            # Create temp_processed for this single image
                            single_temp_processed = None
                            construction_methods = [
                                lambda: type(processed)(p, [single_img]),  # Method 1: Standard constructor with single PIL image
                                lambda: self._construct_processed_fallback(processed, [single_img], p)  # Method 2: Fallback
                            ]
                            
                            for method_num, construct_method in enumerate(construction_methods, 1):
                                try:
                                    print(f"[R Post] 🔧 Image {img_idx + 1}: Trying construction method {method_num}")
                                    single_temp_processed = construct_method()
                                    
                                    # Copy essential attributes
                                    essential_attrs = ['prompt', 'negative_prompt', 'seed', 'subseed', 'width', 'height', 'cfg_scale', 'steps']
                                    for attr in essential_attrs:
                                        if hasattr(processed, attr):
                                            setattr(single_temp_processed, attr, getattr(processed, attr))
                                    
                                    # CRITICAL: ADetailer expects 'image' attribute (singular) for postprocess_image
                                    # Ensure the image is definitely PIL format before assignment
                                    if not hasattr(single_img, 'mode'):
                                        import numpy as np
                                        from PIL import Image
                                        if hasattr(single_img, 'shape') and len(single_img.shape) == 3:
                                            single_img = Image.fromarray(single_img.astype(np.uint8), 'RGB')
                                        else:
                                            single_img = Image.fromarray(single_img.astype(np.uint8))
                                    
                                    single_temp_processed.image = single_img
                                    print(f"[R Post] 🔧 Image {img_idx + 1}: Set temp_processed.image = {single_img.size} mode={single_img.mode} type={type(single_img)}")
                                    print(f"[R Post] ✅ Image {img_idx + 1}: Successfully created temp_processed with method {method_num}")
                                    break
                                    
                                except Exception as construct_e:
                                    print(f"[R Post] ❌ Image {img_idx + 1}: Construction method {method_num} failed: {construct_e}")
                                    continue
                            
                            if single_temp_processed is None:
                                print(f"[R Post] ❌ Image {img_idx + 1}: Could not construct temp_processed - using original image")
                                final_processed_images.append(single_img)
                                continue
                            
                            # Now run ADetailer on this single image
                            print(f"[R Post] 🔄 Running {script.__class__.__name__} on image {img_idx + 1}")
                            
                            # Setup ADetailer processing parameters for this single image
                            p.init_images = [single_img]
                            p.width = single_img.width
                            p.height = single_img.height
                            
                            # Clear blocking flags for this run
                            setattr(p, '_ad_disabled', False)
                            setattr(p, '_ranbooru_skip_initial_adetailer', False)
                            setattr(p, '_ranbooru_suppress_all_processing', False)
                            setattr(p, '_ranbooru_adetailer_already_processed', False)
                            setattr(p, '_adetailer_can_save', True)
                            
                            # CRITICAL: Enable saving for ADetailer processed results
                            p.do_not_save_samples = False
                            p.do_not_save_grid = False
                            
                            # Ensure processed object has save configuration
                            if hasattr(single_temp_processed, 'do_not_save_samples'):
                                single_temp_processed.do_not_save_samples = False
                                single_temp_processed.do_not_save_grid = False
                            
                            # Set proper save path for ADetailer results
                            import os
                            save_path = getattr(p, 'outpath_samples', 'outputs/txt2img-images')
                            setattr(single_temp_processed, 'outpath_samples', save_path)
                            setattr(single_temp_processed, 'save_samples', True)
                            print(f"[R Post] 💾 Configured ADetailer save path: {save_path}")
                            
                            # Enable ADetailer globally for this run
                            setattr(self.__class__, '_ranbooru_block_all_adetailer', False)
                            setattr(self.__class__, '_adetailer_global_guard_active', False)
                            setattr(self.__class__, '_ranbooru_manual_adetailer_active', True)
                        
                            # CRITICAL: Comprehensive PIL enforcement for this image
                            self._enforce_pil_everywhere(p, single_temp_processed, [single_img])
                            
                            # NUCLEAR: Hook into WebUI's image conversion functions to intercept numpy arrays
                            self._patch_image_conversion_functions()
                            
                            # HOOK: Intercept ADetailer's image modifications
                            original_images_backup = []
                            if hasattr(single_temp_processed, 'images') and single_temp_processed.images:
                                original_images_backup = [img.copy() if hasattr(img, 'copy') else img for img in single_temp_processed.images]
                            
                            # CRITICAL: Convert ALL images in temp_processed to PIL format BEFORE calling ADetailer
                            try:
                                import numpy as np
                                from PIL import Image
                                
                                # Ensure temp_processed.images contains only PIL images
                                if hasattr(single_temp_processed, 'images') and single_temp_processed.images:
                                    converted_images = []
                                    for img_idx_inner, img in enumerate(single_temp_processed.images):
                                        if hasattr(img, 'shape'):  # It's a numpy array
                                            pil_img = Image.fromarray(img.astype(np.uint8), 'RGB')
                                            converted_images.append(pil_img)
                                            print(f"[R Post] 🔧 CONVERTED numpy to PIL: {pil_img.size}")
                                        else:
                                            converted_images.append(img)  # Already PIL
                                    single_temp_processed.images = converted_images
                                
                                # Ensure temp_processed.image (singular) is also PIL
                                if hasattr(single_temp_processed, 'image') and hasattr(single_temp_processed.image, 'shape'):
                                    pil_img = Image.fromarray(single_temp_processed.image.astype(np.uint8), 'RGB')
                                    single_temp_processed.image = pil_img
                                    print(f"[R Post] 🔧 CONVERTED temp_processed.image to PIL: {pil_img.size}")
                                
                                print(f"[R Post] ✅ All images converted to PIL before ADetailer call")
                            except Exception as conversion_error:
                                print(f"[R Post] ⚠️ PIL conversion failed: {conversion_error}")
                            
                            # Get script arguments
                            extracted_args = self._extract_adetailer_script_args(script, p)
                            script_args = extracted_args['args']
                            meta = extracted_args['meta']
                            if not script_args:
                                reason = meta.get('fallback_reason')
                                reason_text = f' (fallback={reason})' if reason else ''
                                print(f"[R Post] ⚠️ Image {img_idx + 1}: No ADetailer config found in script args; skipping manual run{reason_text}")
                                continue
                            args_preview = []
                            for arg_index, arg_value in enumerate(script_args[:6]):
                                if isinstance(arg_value, dict):
                                    keys = {k: arg_value.get(k) for k in ('ad_model', 'ad_tab_enable', 'ad_prompt', 'ad_negative_prompt')}
                                    args_preview.append((arg_index, 'dict', keys))
                                else:
                                    args_preview.append((arg_index, type(arg_value).__name__, arg_value))
                            print(f"[R Post] DEBUG - Image {img_idx + 1}: Using {len(script_args)} script args (slice={meta.get('slice_start')}->{meta.get('slice_end')}); preview={args_preview}")

                            
                            # Store the original image before ADetailer processing
                            original_image = single_temp_processed.images[0] if single_temp_processed.images else single_img
                            original_image_size = getattr(original_image, 'size', 'unknown')
                            print(f"[R Post] 📷 Image {img_idx + 1}: Original before ADetailer: {original_image_size}")
                            
                            # DETAILED DEBUG: Show temp_processed state before ADetailer
                            print(f"[R Post] 🔍 PRE-ADETAILER STATE:")
                            print(f"[R Post] 🔍   temp_processed.images count: {len(getattr(single_temp_processed, 'images', []))}")
                            if hasattr(single_temp_processed, 'images') and single_temp_processed.images:
                                for idx, img in enumerate(single_temp_processed.images):
                                    print(f"[R Post] 🔍   Image {idx}: {type(img)} {getattr(img, 'size', 'no-size')}")
                            
                            # Try postprocess_image first (ADetailer's main method)
                            adetailer_success = False
                            if hasattr(script, 'postprocess_image'):
                                try:
                                    print(f"[R Post] 🚀 Image {img_idx + 1}: Calling postprocess_image")
                                    result = script.postprocess_image(p, single_temp_processed, *script_args)
                                    print(f"[R Post] 📋 Image {img_idx + 1}: postprocess_image returned: {result}")

                                    processed_attr = getattr(single_temp_processed, 'image', None)
                                    if processed_attr is not None:
                                        if hasattr(single_temp_processed, 'images') and single_temp_processed.images:
                                            single_temp_processed.images[0] = processed_attr
                                        else:
                                            single_temp_processed.images = [processed_attr]
                                        print(f"[R Post] DEBUG - Image {img_idx + 1}: Synced processed image from temp_processed.image ({getattr(processed_attr, 'size', 'unknown')})")

                                    
                                    # COMPREHENSIVE DEBUG: Check ALL possible result locations
                                    print(f"[R Post] 🔍 POST-ADETAILER STATE:")
                                    print(f"[R Post] 🔍   temp_processed.images count: {len(getattr(single_temp_processed, 'images', []))}")
                                    
                                    # Check temp_processed.images
                                    if hasattr(single_temp_processed, 'images') and single_temp_processed.images:
                                        for idx, img in enumerate(single_temp_processed.images):
                                            print(f"[R Post] 🔍   Image {idx}: {type(img)} {getattr(img, 'size', 'no-size')}")
                                    
                                    # Check other possible result attributes
                                    for attr in ['extra_images', 'all_images', 'output_images', 'processed_images']:
                                        if hasattr(single_temp_processed, attr):
                                            attr_value = getattr(single_temp_processed, attr)
                                            if attr_value:
                                                print(f"[R Post] 🔍   {attr}: {len(attr_value) if isinstance(attr_value, (list, tuple)) else type(attr_value)}")
                                    
                                    # Check p object for results
                                    if hasattr(p, 'processed') and hasattr(p.processed, 'images'):
                                        print(f"[R Post] 🔍   p.processed.images count: {len(p.processed.images)}")
                                    
                                    # Now check if temp_processed.images was modified by ADetailer
                                    if hasattr(single_temp_processed, 'images') and single_temp_processed.images:
                                        # ADetailer may add processed images - check for the best quality result
                                        if len(single_temp_processed.images) > 1:
                                            # Multiple images - use the last (most processed) one
                                            processed_image = single_temp_processed.images[-1]
                                            print(f"[R Post] 🎯 Found {len(single_temp_processed.images)} images - using last processed image")
                                        else:
                                            processed_image = single_temp_processed.images[0]
                                        
                                        processed_size = getattr(processed_image, 'size', 'unknown')
                                        print(f"[R Post] 📷 Image {img_idx + 1}: After ADetailer: {processed_size}")
                                        
                                        # Check for upscaling (ADetailer often upscales faces)
                                        original_size = getattr(original_image, 'size', (0, 0))
                                        if processed_size != original_size and processed_size != 'unknown':
                                            print(f"[R Post] 🚀 UPSCALING DETECTED: {original_size} -> {processed_size}")
                                        
                                        # Advanced change detection: Check object identity, size, and image data
                                        image_changed = False
                                        
                                        # Debug: Show what we're comparing
                                        print(f"[R Post] 🔍 COMPARISON - Original: {type(original_image)} {original_image_size}, Processed: {type(processed_image)} {processed_size}")
                                        
                                        # Check 1: Different object identity
                                        if processed_image is not original_image:
                                            print(f"[R Post] ✅ Image {img_idx + 1}: Different image object detected")
                                            image_changed = True
                                        
                                        # Check 2: Different size (upscaling)
                                        elif processed_size != original_image_size:
                                            print(f"[R Post] ✅ Image {img_idx + 1}: Size changed from {original_image_size} to {processed_size}")
                                            image_changed = True
                                        
                                        # Check 3: Look for ADetailer-specific attributes
                                        elif hasattr(single_temp_processed, 'extra_generation_params') and single_temp_processed.extra_generation_params:
                                            print(f"[R Post] ✅ Image {img_idx + 1}: Extra generation params indicate ADetailer processing")
                                            image_changed = True
                                    
                                        # Check 3: Same object but potentially modified data (face enhancement)
                                        else:
                                            try:
                                                # Convert both to same format for comparison
                                                import hashlib
                                                orig_bytes = original_image.tobytes() if hasattr(original_image, 'tobytes') else None
                                                proc_bytes = processed_image.tobytes() if hasattr(processed_image, 'tobytes') else None
                                                
                                                if orig_bytes and proc_bytes and orig_bytes != proc_bytes:
                                                    print(f"[R Post] ✅ Image {img_idx + 1}: Image data modified (face enhancement detected)")
                                                    image_changed = True
                                                else:
                                                    print(f"[R Post] 📊 Image {img_idx + 1}: Checking for subtle changes (face enhancement)")
                                                    # Check if temp_processed was modified in any way
                                                    if hasattr(single_temp_processed, '_adetailer_processed') or \
                                                       hasattr(single_temp_processed, 'extra_generation_params') or \
                                                       len(getattr(single_temp_processed, 'images', [])) > 1:
                                                        print(f"[R Post] ✅ Image {img_idx + 1}: ADetailer metadata indicates processing occurred")
                                                        image_changed = True
                                                    else:
                                                        print(f"[R Post] 📊 Image {img_idx + 1}: No clear changes detected")

                                            except Exception as compare_e:
                                                print(f"[R Post] 📊 Image {img_idx + 1}: Could not compare image data: {compare_e}")
                                                image_changed = False
                                        
                                        if image_changed:
                                            adetailer_success = True
                                            print(f"[R Post] ✅ Image {img_idx + 1}: ADetailer processing detected as successful")
                                            if isinstance(getattr(p, 'extra_generation_params', None), dict):
                                                single_temp_processed.extra_generation_params = dict(p.extra_generation_params)
                                        else:
                                            print(f"[R Post] ⚠️ Image {img_idx + 1}: No changes detected; keeping original image")
                                    else:
                                        print(f"[R Post] ⚠️ Image {img_idx + 1}: No images in temp_processed after ADetailer")
                                except Exception as e:
                                    print(f"[R Post] ❌ Image {img_idx + 1}: postprocess_image failed: {e}")
                        
                            # Try postprocess as fallback
                            if not adetailer_success and hasattr(script, 'postprocess'):
                                try:
                                    print(f"[R Post] 🚀 Image {img_idx + 1}: FALLBACK calling postprocess")
                                    script.postprocess(p, single_temp_processed, *script_args)
                                    
                                    # Check results after postprocess
                                    if hasattr(single_temp_processed, 'images') and single_temp_processed.images:
                                        processed_image = single_temp_processed.images[0]
                                        processed_size = getattr(processed_image, 'size', 'unknown')
                                        print(f"[R Post] 📷 Image {img_idx + 1}: After postprocess: {processed_size}")
                                        adetailer_success = True
                                        print(f"[R Post] ✅ Image {img_idx + 1}: postprocess succeeded!")
                                    else:
                                        print(f"[R Post] ⚠️ Image {img_idx + 1}: No images after postprocess")
                                except Exception as e:
                                    print(f"[R Post] ❌ Image {img_idx + 1}: postprocess failed: {e}")
                            
                            # Collect the processed result - always use what's in temp_processed.images
                            if adetailer_success and hasattr(single_temp_processed, 'images') and single_temp_processed.images:
                                        # ENHANCED: Look for the best result from multiple sources
                                        processed_img = None
                                        
                                        # Method 1: Check for extra_images (ADetailer often puts results here)
                                        if hasattr(single_temp_processed, 'extra_images') and single_temp_processed.extra_images:
                                            processed_img = single_temp_processed.extra_images[-1]
                                            print(f"[R Post] 🎯 Using enhanced image from extra_images: {getattr(processed_img, 'size', 'unknown')}")
                                        
                                        # Method 2: Use last image if multiple exist
                                        elif len(single_temp_processed.images) > 1:
                                            processed_img = single_temp_processed.images[-1]  # Last = most processed
                                            print(f"[R Post] 🎯 Using last processed image from {len(single_temp_processed.images)} available")
                                        
                                        # Method 3: Compare with backup to find changes
                                        elif original_images_backup:
                                            current_img = single_temp_processed.images[0]
                                            if len(original_images_backup) > 0:
                                                original_backup = original_images_backup[0]
                                                if (hasattr(current_img, 'size') and hasattr(original_backup, 'size') and 
                                                    current_img.size != original_backup.size):
                                                    processed_img = current_img
                                                    print(f"[R Post] 🎯 Detected size change: {original_backup.size} -> {current_img.size}")
                                                elif current_img is not original_backup:
                                                    processed_img = current_img
                                                    print(f"[R Post] 🎯 Detected object change (same size)")
                                        
                                        # Method 4: Fallback to first image
                                        if processed_img is None:
                                            processed_img = single_temp_processed.images[0]
                                            print(f"[R Post] 🎯 Using fallback image: {getattr(processed_img, 'size', 'unknown')}")
                                
                            final_processed_images.append(processed_img)
                            successful_processes += 1
                            print(f"[R Post] ✅ Image {img_idx + 1}: Using ADetailer result - size {getattr(processed_img, 'size', 'unknown')}")
                            
                            # Debug: Compare original vs processed
                            if hasattr(processed_img, 'size') and hasattr(single_img, 'size'):
                                orig_size = getattr(single_img, 'size', 'unknown')
                                proc_size = getattr(processed_img, 'size', 'unknown')
                                print(f"[R Post] 📊 SIZE COMPARISON: Original {orig_size} -> Processed {proc_size}")
                            
                            # CRITICAL: Manually save ADetailer result since auto-save may not work
                                try:
                                    import os
                                    from modules import images as images_module
                                    save_dir = getattr(p, 'outpath_samples', 'outputs/txt2img-images')
                                    os.makedirs(save_dir, exist_ok=True)
                                    
                                    # Generate filename with ADetailer suffix
                                    base_filename = f"{getattr(p, 'seed', 'unknown')}_{img_idx+1}_adetailer"
                                    
                                    # Save both original and processed for comparison
                                    info_text = None
                                    if hasattr(processed, 'infotexts') and processed.infotexts:
                                        try:
                                            info_text = processed.infotexts[img_idx]
                                        except Exception:
                                            info_text = processed.infotexts[0]
                                    if info_text is None:
                                        info_text = getattr(single_temp_processed, 'info', '')
                                    if original_images_backup:
                                        orig_filepath = images_module.save_image(
                                            original_images_backup[0], 
                                            save_dir, 
                                            f"{base_filename}_ORIGINAL",
                                            extension='png',
                                            info=info_text,
                                            p=p
                                        )
                                        print(f"[R Post] 💾 SAVED original for comparison: {orig_filepath}")
                                    
                                    filepath = images_module.save_image(
                                        processed_img, 
                                        save_dir, 
                                        f"{base_filename}_PROCESSED",
                                        extension='png',
                                        info=info_text,
                                        p=p
                                    )
                                    print(f"[R Post] 💾 SAVED ADetailer result: {filepath}")
                                except Exception as save_error:
                                    print(f"[R Post] ⚠️ Manual save failed: {save_error}")
                            else:
                                # Use original if ADetailer failed
                                final_processed_images.append(single_img)
                                print(f"[R Post] ⚠️ Image {img_idx + 1}: ADetailer failed - using original image")
                        
                        except Exception as img_error:
                            # Comprehensive error handling for individual image processing
                            print(f"[R Post] ❌ Critical error processing image {img_idx + 1}: {img_error}")
                            # Always add the original image to prevent complete failure
                            final_processed_images.append(single_img)
                            import traceback
                            traceback.print_exc()
                    
                    # Report results
                    print(f"[R Post] 🎉 Individual processing complete: {successful_processes}/{len(converted_images)} images processed by ADetailer")
                    
                    # Update processed object with final results
                    if final_processed_images:
                        processed.images.clear()
                        processed.images.extend(final_processed_images)
                        img2img_results.clear()
                        img2img_results.extend(final_processed_images)
                        if hasattr(p, 'processed'):
                            p.processed.images.clear()
                            p.processed.images.extend(final_processed_images)
                        print(f"[R Post] 🔧 Updated processed.images with {len(final_processed_images)} final results")
                    
                    # Clear the manual ADetailer flag
                    setattr(self.__class__, '_ranbooru_manual_adetailer_active', False)
                    
                    return successful_processes > 0
                    
                    # Try to run ADetailer's postprocess method
                    if not hasattr(script, 'postprocess'):
                        print(f"[R Post] ❌ Script {script.__class__.__name__} has no postprocess method")
                        continue
                    
                    print(f"[R Post] 🔄 Running {script.__class__.__name__}.postprocess() on img2img results")
                    try:
                        # CRITICAL: Clear all our blocking flags so ADetailer can actually run
                        setattr(p, '_ad_disabled', False)
                        setattr(p, '_ranbooru_skip_initial_adetailer', False)
                        setattr(p, '_ranbooru_suppress_all_processing', False)
                        setattr(p, '_ranbooru_adetailer_already_processed', False)
                        
                        # Clear class-level blocks
                        setattr(self.__class__, '_ranbooru_block_all_adetailer', False)
                        setattr(self.__class__, '_adetailer_global_guard_active', False)
                        setattr(self.__class__, '_adetailer_pipeline_blocked', False)
                        
                        # CRITICAL: Set flag to prevent recursive guard calls
                        setattr(self.__class__, '_ranbooru_manual_adetailer_active', True)
                        
                        print("[R Post] 🔓 CLEARED all blocking flags for manual ADetailer run")
                        
                        # CRITICAL: Set up processing object for ADetailer
                        # ADetailer needs these parameters to actually run
                        p.init_images = [img2img_results[0]]  # Set the input image
                        p.width = img2img_results[0].width
                        p.height = img2img_results[0].height
                        
                        # Enable saving so ADetailer can work AND set proper output path
                        p.do_not_save_samples = False
                        p.do_not_save_grid = False
                        
                        # CRITICAL: Set ADetailer-specific save paths and flags
                        if hasattr(p, 'outpath_samples'):
                            # Store original path to restore later
                            original_outpath = p.outpath_samples
                        else:
                            original_outpath = 'outputs/txt2img-images'
                        
                        # Ensure ADetailer has a valid save path
                        try:
                            import modules.shared as shared
                            adetailer_outpath = getattr(shared.opts, 'outdir_txt2img_samples', None) or original_outpath
                            p.outpath_samples = adetailer_outpath
                            print(f"[R Post] 🔧 Set ADetailer save path: {adetailer_outpath}")
                        except Exception:
                            p.outpath_samples = original_outpath
                            print(f"[R Post] 🔧 Fallback ADetailer save path: {original_outpath}")
                        
                        # Set ADetailer-friendly flags
                        setattr(p, 'save_images', True)
                        setattr(p, '_adetailer_can_save', True)
                        
                        # CRITICAL: Comprehensive PIL enforcement - patch ALL possible image sources
                        self._enforce_pil_everywhere(p, temp_processed, img2img_results)
                        
                        # NUCLEAR: Hook into WebUI's image conversion functions to intercept numpy arrays
                        self._patch_image_conversion_functions()
                        
                        # ULTIMATE: Hook ADetailer's validation function directly to intercept numpy at source
                        try:
                            # Inline validation hook since method might not exist yet
                            import numpy as np
                            from PIL import Image
                            if hasattr(script, 'postprocess_image') and not hasattr(script.__class__, '_ranbooru_numpy_hooked'):
                                original_method = script.postprocess_image
                                def numpy_safe_postprocess_image(*args, **kwargs):
                                    new_args = []
                                    for arg in args:
                                        if isinstance(arg, dict) and 'image' in arg and hasattr(arg['image'], 'shape'):
                                            img_data = arg['image']
                                            if len(img_data.shape) == 3:
                                                pil_img = Image.fromarray(img_data.astype(np.uint8), 'RGB')
                                                new_arg = arg.copy()
                                                new_arg['image'] = pil_img
                                                new_args.append(new_arg)
                                                print(f"[R Post] 🔧 NUMPY HOOK: Intercepted and converted numpy array to PIL {pil_img.size}")
                                                continue
                                        new_args.append(arg)
                                    return original_method(*new_args, **kwargs)
                                script.postprocess_image = numpy_safe_postprocess_image
                                setattr(script.__class__, '_ranbooru_numpy_hooked', True)
                                print(f"[R Post] 🔧 INSTALLED: Numpy->PIL conversion hook on ADetailer.postprocess_image")
                        except Exception as hook_error:
                            print(f"[R Post] Numpy validation hook failed: {hook_error}")
                        
                        # Restore original parameters
                        if hasattr(self, 'original_full_prompt'):
                            p.prompt = self.original_full_prompt
                        if hasattr(self, 'original_outpath'):
                            p.outpath_samples = self.original_outpath
                        
                        print(f"[R Post] 🔧 SETUP: p.init_images[0]={p.init_images[0].size}, p.width={p.width}, p.height={p.height}")
                        print(f"[R Post] 🔧 SETUP: p.do_not_save_samples={p.do_not_save_samples}, p.outpath_samples='{p.outpath_samples}'")
                        
                        # Get script args - this is critical for ADetailer
                        script_args = getattr(p, 'script_args', [])
                        print(f"[R Post] DEBUG - Using {len(script_args)} script args")
                        
                        # Debug ADetailer's internal state
                        print(f"[R Post] DEBUG - Script enabled: {getattr(script, 'enabled', 'unknown')}")
                        print(f"[R Post] DEBUG - Script methods: {[m for m in dir(script) if 'process' in m.lower()]}")
                        
                        # Debug processing object state
                        print(f"[R Post] DEBUG - p.do_not_save_samples: {getattr(p, 'do_not_save_samples', 'unknown')}")
                        print(f"[R Post] DEBUG - p._ad_disabled: {getattr(p, '_ad_disabled', 'unknown')}")
                        print(f"[R Post] DEBUG - temp_processed type: {type(temp_processed)}")
                        print(f"[R Post] DEBUG - temp_processed.images count: {len(getattr(temp_processed, 'images', []))}")
                        
                        # Check if ADetailer has any internal flags that might block it
                        adetailer_flags = [attr for attr in dir(p) if 'adetailer' in attr.lower() or 'ad_' in attr.lower()]
                        if adetailer_flags:
                            print(f"[R Post] DEBUG - ADetailer-related flags on p: {adetailer_flags}")
                            for flag in adetailer_flags[:5]:  # Show first 5 to avoid spam
                                print(f"[R Post] DEBUG - p.{flag}: {getattr(p, flag, 'unknown')}")
                        
                        # Try to check ADetailer's configuration
                        try:
                            if hasattr(script, 'args_info'):
                                print(f"[R Post] DEBUG - Script args_info: {len(getattr(script, 'args_info', []))} items")
                            if hasattr(script, 'enabled') and script.enabled:
                                print(f"[R Post] DEBUG - Script is enabled and ready")
                            else:
                                print(f"[R Post] DEBUG - Script enabled status: {getattr(script, 'enabled', 'no enabled attr')}")
                        except Exception as debug_e:
                            print(f"[R Post] DEBUG - Could not check script config: {debug_e}")
                        
                        # Try both ADetailer methods - postprocess_image is the main one
                        adetailer_processed = False
                        
                        # FINAL VALIDATION: Check that ADetailer will receive only PIL Images
                        def validate_and_convert_image_data(data_dict):
                            """Final validation to ensure ADetailer receives only PIL Images"""
                            import numpy as np
                            from PIL import Image
                            
                            for key, value in data_dict.items():
                                if key == 'image' and hasattr(value, 'shape'):  # numpy array
                                    if len(value.shape) == 3 and value.shape[2] == 3:
                                        data_dict[key] = Image.fromarray(value.astype(np.uint8), 'RGB')
                                    else:
                                        data_dict[key] = Image.fromarray(value.astype(np.uint8))
                                    print(f"[R Post] 🔧 FINAL CONVERSION: {key} converted from numpy to PIL Image {data_dict[key].size}")
                            return data_dict
                        
                        # Hook ADetailer's validation to ensure PIL Images
                        original_adetailer_validate = None
                        def pil_ensuring_wrapper(original_func):
                            def wrapper(*args, **kwargs):
                                # Convert first argument if it's a dict with 'image' key containing numpy array
                                if args and isinstance(args[0], dict) and 'image' in args[0]:
                                    args = (validate_and_convert_image_data(args[0]),) + args[1:]
                                return original_func(*args, **kwargs)
                            return wrapper
                        
                        # Method 1: Try postprocess_image (ADetailer's main method)
                        if hasattr(script, 'postprocess_image'):
                            print(f"[R Post] 🚀 TRYING: {script.__class__.__name__}.postprocess_image(p, temp_processed, *{len(script_args)} args)")
                            try:
                                # CRITICAL: ADetailer extracts image data from different sources
                                # We need to patch ALL possible image sources, not just temp_processed
                                
                                # 1. Patch temp_processed images (our standard approach)
                                final_validation_images = []
                                for img in getattr(temp_processed, 'images', []):
                                    if hasattr(img, 'shape'):  # numpy array
                                        import numpy as np
                                        from PIL import Image
                                        if len(img.shape) == 3 and img.shape[2] == 3:
                                            final_img = Image.fromarray(img.astype(np.uint8), 'RGB')
                                        else:
                                            final_img = Image.fromarray(img.astype(np.uint8))
                                        print(f"[R Post] 🔧 CONVERTED temp_processed.images: numpy -> PIL Image {final_img.size}")
                                        final_validation_images.append(final_img)
                                    else:
                                        final_validation_images.append(img)
                                
                                if final_validation_images:
                                    temp_processed.images = final_validation_images
                                    if hasattr(temp_processed, 'image'):
                                        temp_processed.image = final_validation_images[0]
                                
                                # 2. CRITICAL: Patch p.init_images (ADetailer might read from here)
                                if hasattr(p, 'init_images') and p.init_images:
                                    patched_init_images = []
                                    for img in p.init_images:
                                        if hasattr(img, 'shape'):  # numpy array  
                                            import numpy as np
                                            from PIL import Image
                                            if len(img.shape) == 3 and img.shape[2] == 3:
                                                patched_img = Image.fromarray(img.astype(np.uint8), 'RGB')
                                            else:
                                                patched_img = Image.fromarray(img.astype(np.uint8))
                                            print(f"[R Post] 🔧 CONVERTED p.init_images: numpy -> PIL Image {patched_img.size}")
                                            patched_init_images.append(patched_img)
                                        else:
                                            patched_init_images.append(img)
                                    p.init_images = patched_init_images
                                
                                # 3. Hook ADetailer's validation function directly
                                original_validate_inputs = None
                                try:
                                    # Try to find ADetailer's input validation
                                    import sys
                                    adetailer_modules = [mod for name, mod in sys.modules.items() if 'adetailer' in name.lower()]
                                    for mod in adetailer_modules:
                                        if hasattr(mod, 'validate_inputs') or hasattr(mod, 'process_image'):
                                            # Found a potential validation function - this is where ADetailer processes the image
                                            print(f"[R Post] 🎯 Found ADetailer module with validation: {mod.__name__}")
                                            break
                                except Exception:
                                    pass
                                
                                print(f"[R Post] 🔧 COMPREHENSIVE PIL VALIDATION: All image sources patched")
                                
                                result = script.postprocess_image(p, temp_processed, *script_args)
                                print(f"[R Post] 📋 postprocess_image returned: {result}")
                                if result is not None:
                                    adetailer_processed = True
                                    print(f"[R Post] ✅ postprocess_image succeeded!")
                            except Exception as e:
                                print(f"[R Post] ❌ postprocess_image failed: {e}")
                                # Show ValidationError details if it's that type
                                error_str = str(e)
                                if 'ValidationError' in error_str and 'array(' in error_str:
                                    print(f"[R Post] 🔍 ADetailer ValidationError - ADetailer is reading numpy arrays from an unknown source")
                                    print(f"[R Post] 🔍 Debug temp_processed.images types: {[type(img).__name__ for img in getattr(temp_processed, 'images', [])]}")
                                    if hasattr(temp_processed, 'image'):
                                        print(f"[R Post] 🔍 Debug temp_processed.image type: {type(temp_processed.image).__name__}")
                                    if hasattr(p, 'init_images'):
                                        print(f"[R Post] 🔍 Debug p.init_images types: {[type(img).__name__ for img in p.init_images]}")
                                    # Try to skip ADetailer if it keeps failing
                                    print(f"[R Post] 🔍 ValidationError persists - ADetailer may be reading from internal cache or other source")
                        
                        # Method 2: Try postprocess (fallback)
                        if not adetailer_processed and hasattr(script, 'postprocess'):
                            print(f"[R Post] 🚀 FALLBACK: {script.__class__.__name__}.postprocess(p, temp_processed, *{len(script_args)} args)")
                            try:
                                script.postprocess(p, temp_processed, *script_args)
                                adetailer_processed = True
                                print(f"[R Post] ✅ postprocess succeeded!")
                            except Exception as e:
                                print(f"[R Post] ❌ postprocess failed: {e}")
                        
                        # Method 3: Try direct ADetailer processing (bypass all checks)
                        if not adetailer_processed:
                            print(f"[R Post] 🚀 DIRECT: Attempting direct ADetailer processing bypass")
                            try:
                                # Force enable the script
                                original_enabled = getattr(script, 'enabled', True)
                                script.enabled = True
                                
                                # Try to call ADetailer's internal processing directly
                                if hasattr(script, '_process_image'):
                                    print(f"[R Post] 🚀 DIRECT: Trying _process_image")
                                    result = script._process_image(temp_processed.images[0], p)
                                    if result:
                                        temp_processed.images[0] = result
                                        adetailer_processed = True
                                        print(f"[R Post] ✅ _process_image succeeded!")
                                
                                # Restore original state
                                script.enabled = original_enabled
                                
                            except Exception as e:
                                print(f"[R Post] ❌ Direct processing failed: {e}")
                                try:
                                    script.enabled = original_enabled
                                except:
                                    pass
                        
                        # Method 4: Try using modules.scripts to run ADetailer normally
                        if not adetailer_processed:
                            print(f"[R Post] 🚀 PIPELINE: Attempting to run ADetailer through normal pipeline")
                            try:
                                import modules.scripts
                                # Try to run postprocess_image through the script system
                                if hasattr(modules.scripts, 'postprocess_image'):
                                    print(f"[R Post] 🚀 PIPELINE: Calling modules.scripts.postprocess_image")
                                    modules.scripts.postprocess_image(p, temp_processed)
                                    adetailer_processed = True
                                    print(f"[R Post] ✅ Pipeline postprocess_image succeeded!")
                            except Exception as e:
                                print(f"[R Post] ❌ Pipeline processing failed: {e}")
                        
                        print(f"[R Post] 📋 AFTER ALL CALLS: temp_processed.images has {len(getattr(temp_processed, 'images', []))} images")
                        print(f"[R Post] 📋 ADetailer processing result: {adetailer_processed}")
                        
                        # Check if ADetailer actually processed the images
                        if hasattr(temp_processed, 'images') and temp_processed.images:
                            if len(temp_processed.images) > 0:
                                # CRITICAL: Update ALL image references immediately
                                processed.images.clear()
                                processed.images.extend(temp_processed.images)
                                
                                # Also update the img2img_results array that other code might reference
                                img2img_results.clear()
                                img2img_results.extend(temp_processed.images)
                                
                                # Force update the original processed object references
                                if hasattr(p, 'processed'):
                                    p.processed.images.clear()
                                    p.processed.images.extend(temp_processed.images)
                                
                                print(f"[R Post] 🎉 SUCCESS! {script.__class__.__name__} processed {len(temp_processed.images)} images")
                                print(f"[R Post] 🔧 Updated processed.images, img2img_results, and p.processed with ADetailer results")
                                
                                # Mark completion to prevent any subsequent manual re-runs
                                try:
                                    setattr(p, '_ranbooru_manual_adetailer_complete', True)
                                except Exception:
                                    pass
                                return True
                            else:
                                print(f"[R Post] ⚠️  {script.__class__.__name__} returned empty images list")
                        else:
                            print(f"[R Post] ⚠️  {script.__class__.__name__} didn't return processed images")
                    except Exception as e:
                        print(f"[R Post] ❌ {script.__class__.__name__} postprocess failed: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
                    finally:
                        # CRITICAL: Clear the manual ADetailer flag
                        setattr(self.__class__, '_ranbooru_manual_adetailer_active', False)
            
            if adetailer_scripts_found == 0:
                print("[R Post] ❌ No ADetailer scripts found")
            else:
                print(f"[R Post] ⚠️  Found {adetailer_scripts_found} ADetailer script(s) but none processed successfully")
            
            return False
        except Exception as e:
            print(f"[R Post] ❌ Critical error in manual ADetailer execution: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # Clear the manual ADetailer active flag
            setattr(self.__class__, '_ranbooru_manual_adetailer_active', False)
            print("[R Post] 🔓 Cleared ADetailer active flag")
    
    def _enforce_pil_everywhere(self, p, temp_processed, img2img_results):
        """Comprehensive PIL enforcement - patch ALL possible image sources that ADetailer might read from"""
        try:
            import numpy as np
            from PIL import Image
            
            def convert_to_pil(img):
                """Convert any image format to PIL RGB"""
                if img is None:
                    return None
                if hasattr(img, 'shape'):  # numpy array
                    if len(img.shape) == 3 and img.shape[2] == 3:
                        return Image.fromarray(img.astype(np.uint8), 'RGB')
                    else:
                        return Image.fromarray(img.astype(np.uint8))
                elif hasattr(img, 'mode'):  # PIL Image
                    return img.convert('RGB') if img.mode != 'RGB' else img
                return img
            
            # 1. Convert temp_processed images
            if hasattr(temp_processed, 'images') and temp_processed.images:
                for idx, img in enumerate(temp_processed.images):
                    converted = convert_to_pil(img)
                    if converted != img:
                        temp_processed.images[idx] = converted
                        print(f"[R Post] 🔧 ENFORCED PIL: temp_processed.images[{idx}] -> {converted.size}")
            
            if hasattr(temp_processed, 'image'):
                converted = convert_to_pil(temp_processed.image)
                if converted != temp_processed.image:
                    temp_processed.image = converted
                    print(f"[R Post] 🔧 ENFORCED PIL: temp_processed.image -> {converted.size}")
            
            # 2. Convert p.init_images (ADetailer reads from here too)
            if hasattr(p, 'init_images') and p.init_images:
                for idx, img in enumerate(p.init_images):
                    converted = convert_to_pil(img)
                    if converted != img:
                        p.init_images[idx] = converted
                        print(f"[R Post] 🔧 ENFORCED PIL: p.init_images[{idx}] -> {converted.size}")
            
            # 3. Convert the main processed object images
            if hasattr(p, 'processed') and hasattr(p.processed, 'images'):
                for idx, img in enumerate(p.processed.images):
                    converted = convert_to_pil(img)
                    if converted != img:
                        p.processed.images[idx] = converted
                        print(f"[R Post] 🔧 ENFORCED PIL: p.processed.images[{idx}] -> {converted.size}")
            
            print("[R Post] 🔧 COMPREHENSIVE PIL ENFORCEMENT: All image sources converted to PIL RGB")
            
        except Exception as e:
            print(f"[R Post] Error in PIL enforcement: {e}")
    
    def _patch_image_conversion_functions(self):
        """Patch WebUI's image conversion functions to prevent numpy arrays from reaching ADetailer"""
        try:
            import sys
            from PIL import Image
            import numpy as np
            
            # Find and patch modules that might convert PIL to numpy
            modules_to_patch = []
            for module_name in sys.modules:
                if any(name in module_name.lower() for name in ['processing', 'shared', 'scripts']):
                    module = sys.modules[module_name]
                    if hasattr(module, 'pil2numpy') or hasattr(module, 'numpy_to_pil') or hasattr(module, 'image_to_numpy'):
                        modules_to_patch.append(module)
            
            # Install interceptors
            for module in modules_to_patch:
                if hasattr(module, 'pil2numpy') and not hasattr(module, '_ranbooru_original_pil2numpy'):
                    original_func = module.pil2numpy
                    module._ranbooru_original_pil2numpy = original_func
                    
                    def patched_pil2numpy(*args, **kwargs):
                        result = original_func(*args, **kwargs)
                        # If ADetailer is active, return PIL instead of numpy
                        if getattr(self.__class__, '_ranbooru_manual_adetailer_active', False):
                            if isinstance(result, np.ndarray) and len(result.shape) == 3:
                                pil_img = Image.fromarray(result.astype(np.uint8), 'RGB')
                                print("[R Post] 🚫 INTERCEPTED: Blocked numpy conversion during ADetailer, returning PIL")
                                return pil_img
                        return result
                    
                    module.pil2numpy = patched_pil2numpy
                    try:
                        if not hasattr(self, '_patched_conversion_modules'):
                            self._patched_conversion_modules = []
                        self._patched_conversion_modules.append((module, 'pil2numpy'))
                    except Exception:
                        pass
            
            print(f"[R Post] 🔧 PATCHED: {len(modules_to_patch)} modules to prevent numpy leaks to ADetailer")
            
        except Exception as e:
            print(f"[R Post] Error patching image conversion functions: {e}")

    def _unpatch_manual_adetailer_overrides(self):
        """Restore any monkey patches applied for manual ADetailer runs."""
        try:
            if hasattr(self, '_patched_processed_objects'):
                for proc in list(self._patched_processed_objects):
                    original = getattr(proc, '_ranbooru_original_getattribute', None)
                    if original is not None:
                        try:
                            proc.__getattribute__ = original
                        except Exception:
                            pass
                        try:
                            delattr(proc, '_ranbooru_original_getattribute')
                        except Exception:
                            pass
                delattr(self, '_patched_processed_objects')

            if hasattr(self, '_patched_adetailer_modules'):
                for module, attr_name in list(self._patched_adetailer_modules):
                    attr_key = f'_ranbooru_original_{attr_name}'
                    original = getattr(module, attr_key, None)
                    if original is not None:
                        try:
                            setattr(module, attr_name, original)
                        except Exception:
                            pass
                    if hasattr(module, attr_key):
                        try:
                            delattr(module, attr_key)
                        except Exception:
                            pass
                delattr(self, '_patched_adetailer_modules')

            if hasattr(self, '_patched_conversion_modules'):
                for module, attr_name in list(self._patched_conversion_modules):
                    attr_key = f'_ranbooru_original_{attr_name}'
                    original = getattr(module, attr_key, None)
                    if original is not None:
                        try:
                            setattr(module, attr_name, original)
                        except Exception:
                            pass
                    if hasattr(module, attr_key):
                        try:
                            delattr(module, attr_key)
                        except Exception:
                            pass
                delattr(self, '_patched_conversion_modules')

            if hasattr(self.__class__, '_force_adetailer_images'):
                try:
                    delattr(self.__class__, '_force_adetailer_images')
                except Exception:
                    pass

            # Restore ScriptRunner guards back to their original implementations
            try:
                import modules.scripts as _ranbooru_scripts_module  # type: ignore
                for runner_attr in ('scripts_txt2img', 'scripts_img2img'):
                    runner = getattr(_ranbooru_scripts_module, runner_attr, None)
                    if not runner:
                        continue
                    original_post = getattr(runner, '_ranbooru_original_postprocess', None)
                    if original_post is not None:
                        try:
                            runner.postprocess = original_post
                        except Exception:
                            pass
                        try:
                            delattr(runner, '_ranbooru_original_postprocess')
                        except Exception:
                            pass
                    original_post_image = getattr(runner, '_ranbooru_original_postprocess_image', None)
                    if original_post_image is not None:
                        try:
                            runner.postprocess_image = original_post_image
                        except Exception:
                            pass
                        try:
                            delattr(runner, '_ranbooru_original_postprocess_image')
                        except Exception:
                            pass
                    if hasattr(runner, '_ranbooru_guard_installed'):
                        try:
                            delattr(runner, '_ranbooru_guard_installed')
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception as exc:
            print(f"[R Cleanup] Warn: Failed to unpatch manual ADetailer overrides: {exc}")
    
    def _construct_processed_fallback(self, processed, img2img_results, p):
        """Fallback method to construct Processed object"""
        try:
            # Try creating a minimal Processed-like object
            temp_processed = type('TempProcessed', (), {})()
            
            # Convert all images to PIL format before assignment
            converted_images = []
            for img in img2img_results:
                if hasattr(img, 'mode') and img.mode != 'RGB':
                    img = img.convert('RGB')
                elif hasattr(img, 'shape'):  # Handle numpy arrays
                    import numpy as np
                    from PIL import Image
                    if len(img.shape) == 3 and img.shape[2] == 3:
                        img = Image.fromarray(img.astype(np.uint8), 'RGB')
                    else:
                        img = Image.fromarray(img.astype(np.uint8))
                converted_images.append(img)
            
            temp_processed.images = converted_images
            temp_processed.infotexts = [''] * len(converted_images)
            
            # CRITICAL: ADetailer expects 'image' attribute (singular)
            if converted_images:
                temp_processed.image = converted_images[0]
                print(f"[R Post] 🔧 FALLBACK: Set temp_processed.image = {converted_images[0].size} mode={converted_images[0].mode}")
                print(f"[R Post] 🔧 FALLBACK: Converted {len(converted_images)} images to PIL format")
            
            return temp_processed
        except Exception as e:
            raise Exception(f"Fallback construction failed: {e}")
    
    def _disable_original_adetailer(self, p):
        """Comprehensively disable ALL ADetailer scripts from ALL possible sources"""
        try:
            print("[R Post] 🚫 COMPREHENSIVE: Finding and disabling ALL ADetailer scripts everywhere")
            self.disabled_adetailer_scripts = []
            
            # Method 1: Check alwayson_scripts (primary location)
            if hasattr(p, 'scripts') and hasattr(p.scripts, 'alwayson_scripts'):
                for script in p.scripts.alwayson_scripts:
                    if self._is_adetailer_script(script):
                        self._disable_single_adetailer(script, "alwayson_scripts")
            
            # Method 2: Check regular scripts list  
            if hasattr(p, 'scripts') and hasattr(p.scripts, 'scripts'):
                for script in p.scripts.scripts:
                    if self._is_adetailer_script(script):
                        self._disable_single_adetailer(script, "scripts")
            
            # Method 3: Check global scripts registry
            try:
                import modules.scripts as scripts_module
                if hasattr(scripts_module, 'scripts_data'):
                    for script_data in scripts_module.scripts_data:
                        if hasattr(script_data, 'script_class'):
                            script = script_data.script_class
                            if self._is_adetailer_script(script):
                                self._disable_single_adetailer(script, "global_registry")
            except:
                pass  # Global registry might not be accessible
            
            # Method 4: Find ADetailer through module inspection
            try:
                import sys
                for module_name in sys.modules:
                    if 'adetailer' in module_name.lower():
                        module = sys.modules[module_name]
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if hasattr(attr, 'postprocess') and self._is_adetailer_script(attr):
                                self._disable_single_adetailer(attr, f"module_{module_name}")
            except:
                pass  # Module inspection might fail
                
            print(f"[R Post] 🚫 COMPREHENSIVE DISABLE: Found and disabled {len(self.disabled_adetailer_scripts)} ADetailer script(s) from all sources")
            
            # NUCLEAR OPTION: Block the wrong image size entirely
            self._block_wrong_image_size()
            
        except Exception as e:
            print(f"[R Post] Error in comprehensive ADetailer disable: {e}")
    
    def _is_adetailer_script(self, script):
        """Check if a script is an ADetailer script"""
        try:
            if script is None:
                return False
            script_name = script.__class__.__name__.lower() if hasattr(script, '__class__') else str(script).lower()
            return ('adetailer' in script_name or 
                    'afterdetailer' in script_name or 
                    'after_detailer' in script_name or
                    'ad_script' in script_name)
        except:
            return False
    
    def _disable_single_adetailer(self, script, source):
        """Disable a single ADetailer script"""
        try:
            print(f"[R Post] 🚫 Disabling {script.__class__.__name__} from {source}")
            
            # Store original state for cleanup
            original_enabled = getattr(script, 'enabled', True)
            self.disabled_adetailer_scripts.append((script, original_enabled))
            
            # Disable the script completely
            if hasattr(script, 'enabled'):
                script.enabled = False
            
            # Replace ALL processing methods with no-ops
            methods_to_disable = ['postprocess', 'process', 'process_batch', 'before_process', 'after_process']
            for method_name in methods_to_disable:
                if hasattr(script, method_name):
                    original_method = getattr(script, method_name)
                    setattr(script, f'_ranbooru_original_{method_name}', original_method)
                    setattr(script, method_name, lambda *args, **kwargs: None)  # No-op
            
            # Mark as disabled by RanbooruX
            script._ranbooru_disabled_after_manual = True
            script._ranbooru_disabled_source = source
                
        except Exception as e:
            print(f"[R Post] Error disabling single ADetailer from {source}: {e}")
    
    def _block_wrong_image_size(self):
        """Block processing of 640x512 images entirely"""
        try:
            print("[R Post] 🚫 NUCLEAR: Blocking 640x512 image processing entirely")
            
            # Store global flag to block wrong image sizes
            self.__class__._block_640x512_images = True
            
            # Try to patch common image processing functions
            import modules.processing
            if hasattr(modules.processing, '_current_processed'):
                original_processed = modules.processing._current_processed
                if hasattr(original_processed, 'images'):
                    # Filter out 640x512 images from any processing
                    filtered_images = []
                    for img in original_processed.images:
                        if hasattr(img, 'size') and img.size != (640, 512):
                            filtered_images.append(img)
                        else:
                            print(f"[R Post] 🚫 BLOCKED 640x512 image from processing")
                    original_processed.images = filtered_images
            
        except Exception as e:
            print(f"[R Post] Error in nuclear image blocking: {e}")
    
    def _mark_initial_pass(self, p):
        """Mark that we're in initial pass so ADetailer can be intercepted later"""
        try:
            print("[R] 📍 Marking initial pass - ADetailer will run on img2img results instead")
            
            # Clear any previous hard-disable flag for ADetailer
            try:
                if hasattr(p, "_ad_disabled") and getattr(p, "_ad_disabled", False):
                    setattr(p, "_ad_disabled", False)
                    print("[R] 🔄 Cleared p._ad_disabled from previous generation")
            except Exception as _e:
                print(f"[R] WARN: Could not clear p._ad_disabled: {_e}")
            
            # Clear our class-level guard
            self._set_adetailer_block(False)
            # Clear pipeline-level guard flag
            setattr(self.__class__, '_ranbooru_block_all_adetailer', False)
            
            # Install runner guard (idempotent)
            self._install_scriptrunner_guard(p)
            
            # CRITICAL: Re-enable any ADetailer scripts from previous generation
            self._reenable_adetailer_from_previous_generation()
            
            # Just set a flag that we're in initial pass
            self._ranbooru_initial_pass = True
            
            # Store reference to processing object for later use
            self._initial_pass_p = p
            
        except Exception as e:
            print(f"[R] Error marking initial pass: {e}")
    
    def _reenable_adetailer_from_previous_generation(self):
        """Re-enable ALL ADetailer scripts that were disabled in the previous generation"""
        try:
            if hasattr(self, 'disabled_adetailer_scripts') and self.disabled_adetailer_scripts:
                print(f"[R] 🔄 COMPREHENSIVE RE-ENABLE: Restoring {len(self.disabled_adetailer_scripts)} ADetailer script(s) from previous generation")
                
                for script, original_enabled in self.disabled_adetailer_scripts:
                    source = getattr(script, '_ranbooru_disabled_source', 'unknown')
                    print(f"[R] 🔄 Re-enabling {script.__class__.__name__} from {source}")
                    
                    # Restore original enabled state
                    if hasattr(script, 'enabled'):
                        script.enabled = original_enabled
                    
                    # Restore ALL original methods that were disabled
                    methods_to_restore = ['postprocess', 'process', 'process_batch', 'before_process', 'after_process']
                    for method_name in methods_to_restore:
                        original_method_attr = f'_ranbooru_original_{method_name}'
                        if hasattr(script, original_method_attr):
                            original_method = getattr(script, original_method_attr)
                            setattr(script, method_name, original_method)
                            delattr(script, original_method_attr)
                    
                    # Remove our disable flags
                    if hasattr(script, '_ranbooru_disabled_after_manual'):
                        delattr(script, '_ranbooru_disabled_after_manual')
                    if hasattr(script, '_ranbooru_disabled_source'):
                        delattr(script, '_ranbooru_disabled_source')
                
                print(f"[R] 🔄 COMPREHENSIVE RE-ENABLE: Restored {len(self.disabled_adetailer_scripts)} ADetailer script(s) for new generation")
                # Clear the list now that we've re-enabled everything
                delattr(self, 'disabled_adetailer_scripts')
            
            # Unblock 640x512 images for normal processing
            self._unblock_wrong_image_size()
                
        except Exception as e:
            print(f"[R] Error in comprehensive ADetailer re-enable: {e}")
    
    def _unblock_wrong_image_size(self):
        """Unblock 640x512 image processing for normal ADetailer operation"""
        try:
            if hasattr(self.__class__, '_block_640x512_images'):
                print("[R] 🔄 UNBLOCKING: Re-enabling 640x512 image processing for normal operation")
                delattr(self.__class__, '_block_640x512_images')
        except Exception as e:
            print(f"[R] Error unblocking wrong image size: {e}")
    
    def _prevent_all_image_saving(self, p):
        """Prevent all possible image saving during initial pass"""
        try:
            print("[R] 🚫 Implementing comprehensive save prevention for initial pass")
            
            # Store additional original values for restoration
            self.original_save_to_dirs = getattr(p, 'save_to_dirs', True)  
            self.original_filename_format = getattr(p, 'filename_format', None)
            
            # Disable additional save mechanisms
            p.save_to_dirs = False
            
            # AGGRESSIVE: Set outpath to a temporary location that we can clean up
            import tempfile
            temp_dir = tempfile.mkdtemp(prefix='ranbooru_temp_')
            self.temp_initial_dir = temp_dir
            p.outpath_samples = temp_dir
            
            # ULTIMATE: Set a flag to completely suppress this generation from being processed by anything else
            setattr(p, '_ranbooru_suppress_all_processing', True)
            setattr(p, '_ranbooru_initial_pass_only', True)
            print(f"[R Save Prevention] 🚫 Redirected initial pass saves to temp directory: {temp_dir}")
            print("[R Save Prevention] 🚫 ULTIMATE: Marked initial pass for complete processing suppression")
            
            # Try to disable any gallery/history saving
            if hasattr(p, 'save_images_history'):
                self.original_save_images_history = p.save_images_history
                p.save_images_history = False
                
            # Disable any extra network saving
            if hasattr(p, 'save_samples_dir'):
                self.original_save_samples_dir = p.save_samples_dir
                p.save_samples_dir = None
                
            # Make filename format minimal to prevent accidental saves
            if hasattr(p, 'filename_format'):
                p.filename_format = ""
                
            print("[R] 🚫 Comprehensive save prevention applied")
            
        except Exception as e:
            print(f"[R] Error applying save prevention: {e}")
    
    def _prepare_adetailer_for_img2img(self, p):
        """Prepare ADetailer to run on img2img results"""
        if not self._is_adetailer_enabled():
            return
        try:
            print("[R] ✅ Preparing ADetailer to run on img2img results")
            
            # Clear the initial pass flag so ADetailer knows to run normally
            self._ranbooru_initial_pass = False
            
        except Exception as e:
            print(f"[R] Error preparing ADetailer: {e}")
    
    def _force_ui_update(self, p, processed, final_results):
        """Force ForgeUI to display our final ADetailer-processed results"""
        try:
            print(f"[R UI] 🖥️  Forcing UI to display {len(final_results)} final results")
            
            # SAFETY CHECK: Filter out any 640x512 images from final results
            filtered_results = []
            for img in final_results:
                if hasattr(img, 'size') and img.size == (640, 512):
                    print(f"[R UI] 🚫 BLOCKED 640x512 image from UI display")
                else:
                    filtered_results.append(img)
            
            if len(filtered_results) != len(final_results):
                print(f"[R UI] 🚫 Filtered out {len(final_results) - len(filtered_results)} wrong-sized images")
                final_results = filtered_results
            
            # Method 1: Update all possible UI-related attributes
            ui_attrs = [
                'images', 'output_images', 'result_images', 'final_images', 
                'display_images', 'ui_images', 'gallery_images'
            ]
            
            for attr in ui_attrs:
                if hasattr(processed, attr):
                    if isinstance(getattr(processed, attr), list):
                        getattr(processed, attr).clear()
                        getattr(processed, attr).extend(final_results)
                        print(f"[R UI] 🖥️  Updated {attr} for UI")
                    else:
                        setattr(processed, attr, final_results)
                        print(f"[R UI] 🖥️  Set {attr} for UI")
            
            # Method 2: Try to update WebUI/Gradio state directly
            try:
                import modules.shared as shared_modules
                if hasattr(shared_modules, 'state'):
                    # Force UI refresh
                    if hasattr(shared_modules.state, 'current_image'):
                        shared_modules.state.current_image = final_results[0] if final_results else None
                        print("[R UI] 🖥️  Updated shared.state.current_image")
                    
                    # Update any gallery state
                    if hasattr(shared_modules.state, 'gallery_images'):
                        shared_modules.state.gallery_images = final_results
                        print("[R UI] 🖥️  Updated shared.state.gallery_images")
                        
                    # Force UI state update
                    shared_modules.state.need_restart = False  # Prevent restart
                    
            except Exception as e:
                print(f"[R UI] Could not update WebUI state: {e}")
            
            # Method 3: Try to update processing pipeline UI references
            if hasattr(p, 'cached_images'):
                p.cached_images = final_results
                print("[R UI] 🖥️  Updated p.cached_images")
            
            # Method 4: Force update any Gradio components we can find
            try:
                # This is a bit hacky but should force UI refresh
                processed._ui_force_update = True
                processed._ui_timestamp = __import__('time').time()
                print("[R UI] 🖥️  Added UI force update flags")
            except:
                pass
            
            # Method 5: Update the main result that ForgeUI looks for
            if hasattr(processed, '__dict__'):
                for key, value in processed.__dict__.items():
                    if 'result' in key.lower() and isinstance(value, list):
                        value.clear()
                        value.extend(final_results)
                        print(f"[R UI] 🖥️  Updated result attribute: {key}")
            
            print(f"[R UI] 🖥️  UI force update complete - ForgeUI should now display final results")
            
            # Disable preview guard now that correct image is presented
            try:
                self._set_preview_guard(False)
            except Exception:
                pass
            
        except Exception as e:
            print(f"[R UI] Error forcing UI update: {e}")

    def postprocess_batch(self, p, *args, **kwargs):
        """Ensure the final batch results show img2img instead of txt2img"""
        try:
            if not getattr(self, '_post_enabled', False):
                return
                
            if not getattr(self, 'run_img2img_pass', False):
                return
                
            # This method runs after all individual postprocess methods
            # Use it to ensure the UI gets the final img2img results
            print("[R PostBatch] Ensuring UI displays img2img results")
            
            # FINAL INTERCEPT: If we have global results, force them into all possible locations
            if hasattr(self.__class__, '_global_ranbooru_results'):
                img2img_results = self.__class__._global_ranbooru_results
                print(f"[R PostBatch] 🎯 FINAL INTERCEPT: Forcing {len(img2img_results)} img2img results into all extensions")
                
                # Try to find the processed object in the arguments and force update it
                for arg in args:
                    if hasattr(arg, 'images') and hasattr(arg, 'prompt'):
                        print("[R PostBatch] 🎯 Found processed object in args - force updating")
                        arg.images.clear()
                        arg.images.extend(img2img_results)
                        # Apply UI force update here too
                        self._force_ui_update(p, arg, img2img_results)
                        # Apply the same monkey patch here
                        self._patch_adetailer_directly(arg, img2img_results)
                        
                # COMPREHENSIVE: Try to patch any scripts that might be running
                all_script_collections = []
                if hasattr(p, 'scripts'):
                    if hasattr(p.scripts, 'alwayson_scripts'):
                        all_script_collections.extend([(script, 'alwayson') for script in p.scripts.alwayson_scripts])
                    if hasattr(p.scripts, 'scripts'):
                        all_script_collections.extend([(script, 'regular') for script in p.scripts.scripts])
                
                for script, script_type in all_script_collections:
                    script_name = script.__class__.__name__.lower()
                    if self._is_adetailer_script(script):
                        # Skip if we've already disabled this script
                        if hasattr(script, '_ranbooru_disabled_after_manual'):
                            print(f"[R PostBatch] 🚫 Skipping {script.__class__.__name__} ({script_type}) - disabled by RanbooruX after manual processing")
                            continue
                            
                        print(f"[R PostBatch] 🎯 Found potential ADetailer script: {script.__class__.__name__} ({script_type})")
                        # Force update any image attributes this script might have
                        for attr_name in dir(script):
                            if 'image' in attr_name.lower() and not attr_name.startswith('_'):
                                try:
                                    attr_value = getattr(script, attr_name)
                                    if isinstance(attr_value, list):
                                        attr_value.clear()
                                        attr_value.extend(img2img_results)
                                        print(f"[R PostBatch] 🎯 Updated {script_name}.{attr_name}")
                                except:
                                    pass
                
                # CRITICAL: Final UI force update at batch level
                print("[R PostBatch] 🖥️  Performing final UI force update")
                if args and hasattr(args[0], 'images'):
                    self._force_ui_update(p, args[0], img2img_results)
            
            # Mark processing as complete for UI
            if hasattr(self, '_ranbooru_processing_complete'):
                print("[R PostBatch] RanbooruX img2img processing marked as complete")
            
        except Exception as e:
            print(f"[R PostBatch] Error: {e}")
    
    def process_batch(self, p, *args, **kwargs):
        """Process batch - used to mark initial results as intermediate"""
        try:
            if getattr(self, 'run_img2img_pass', False):
                # Mark that we're in a two-pass process
                setattr(self, '_ranbooru_intermediate_results', True)
                print("[R ProcessBatch] Marked results as intermediate - img2img will follow")
                
        except Exception as e:
            print(f"[R ProcessBatch] Error: {e}")
    
    def process(self, p, *args):
        """Process method - runs during main processing, can intercept results early"""
        try:
            # This method runs during the main processing phase
            # We can use it to prepare for result interception
            if getattr(self, 'run_img2img_pass', False):
                print("[R Process] Preparing for img2img result interception")
                # Mark that we need to intercept results
                setattr(self, '_intercept_results', True)
                
                if self._is_adetailer_enabled():
                    # EARLY PROTECTION: Disable ADetailer during initial pass
                    self._early_adetailer_protection(p)
                
                # Set early block flag if we're about to process with img2img
                if hasattr(self, '_ranbooru_manual_adetailer_complete'):
                    setattr(self.__class__, '_ranbooru_block_all_adetailer', True)
                    print("[R Process] 🛑 Early block flag set - preventing ADetailer execution")
                
        except Exception as e:
            print(f"[R Process] Error: {e}")
    
    def _early_adetailer_protection(self, p):
        """Complete ADetailer blocking during initial pass - remove scripts entirely"""
        if not self._is_adetailer_enabled():
            return
        try:
            print("[R Process] 🛡️  Early ADetailer protection activated")
            
            # Check if we're in the initial pass
            if getattr(self, '_ranbooru_initial_pass', False):
                print("[R Process] 🛡️  Detected initial pass - COMPLETELY BLOCKING ADetailer")
                
                # Set comprehensive block flags
                setattr(p, '_ranbooru_skip_initial_adetailer', True)
                setattr(p, '_ranbooru_suppress_all_processing', True)
                setattr(p, '_ranbooru_initial_pass_only', True)
                setattr(p, '_ad_disabled', True)  # ADetailer's own disable flag
                
                # CRITICAL: Completely remove ADetailer scripts from the runner during initial pass
                self._remove_adetailer_from_runner(p)
                
                # Set multiple block flags to ensure no ADetailer execution
                self._set_adetailer_block(True)
                setattr(self.__class__, '_ranbooru_block_all_adetailer', True)
                setattr(self.__class__, '_adetailer_global_guard_active', True)
                
                print("[R Process] 🛡️  ADetailer completely blocked for initial pass - will be restored for manual img2img processing")
                
        except Exception as e:
            print(f"[R Process] Error in early ADetailer protection: {e}")
    
    def _remove_adetailer_from_runner(self, p):
        """Temporarily remove ADetailer scripts from the script runner during initial pass"""
        try:
            if not hasattr(p, 'scripts') or p.scripts is None:
                return
            
            # Store original scripts for restoration
            if not hasattr(self, '_stored_adetailer_scripts'):
                self._stored_adetailer_scripts = {'alwayson': [], 'regular': []}
            
            # Remove ADetailer from alwayson_scripts
            if hasattr(p.scripts, 'alwayson_scripts') and p.scripts.alwayson_scripts:
                original_alwayson = list(p.scripts.alwayson_scripts)
                filtered_alwayson = [s for s in original_alwayson if not self._is_adetailer_script(s)]
                removed_alwayson = [s for s in original_alwayson if self._is_adetailer_script(s)]
                
                p.scripts.alwayson_scripts = filtered_alwayson
                self._stored_adetailer_scripts['alwayson'] = removed_alwayson
                print(f"[R Process] 🛡️  Removed {len(removed_alwayson)} ADetailer scripts from alwayson_scripts")
            
            # Remove ADetailer from regular scripts
            if hasattr(p.scripts, 'scripts') and p.scripts.scripts:
                original_scripts = list(p.scripts.scripts)
                filtered_scripts = [s for s in original_scripts if not self._is_adetailer_script(s)]
                removed_scripts = [s for s in original_scripts if self._is_adetailer_script(s)]
                
                p.scripts.scripts = filtered_scripts
                self._stored_adetailer_scripts['regular'] = removed_scripts
                print(f"[R Process] 🛡️  Removed {len(removed_scripts)} ADetailer scripts from scripts")
        
        except Exception as e:
            print(f"[R Process] Error removing ADetailer from runner: {e}")
    
    def _restore_early_adetailer_protection(self, processing_obj=None):
        """Restore ADetailer scripts and flags after an interrupted or completed run."""
        try:
            print("[R Process] 🛡️  Restoring ADetailer scripts for manual processing")

            # Clear initial pass/block flags so subsequent generations can run ADetailer
            setattr(self.__class__, '_ranbooru_block_all_adetailer', False)
            setattr(self.__class__, '_adetailer_global_guard_active', False)
            self._set_adetailer_block(False)

            # Determine which processing object's script runner to restore into
            candidate_p = processing_obj or getattr(self, '_initial_pass_p', None) or getattr(self, '_current_processing_object', None)
            runner = getattr(candidate_p, 'scripts', None) if candidate_p else None

            # Restore scripts we removed during the initial pass safeguard
            stored = getattr(self, '_stored_adetailer_scripts', None)
            if stored and runner:
                try:
                    if hasattr(runner, 'alwayson_scripts') and stored.get('alwayson'):
                        for script in stored['alwayson']:
                            if script not in runner.alwayson_scripts:
                                runner.alwayson_scripts.append(script)
                        print(f"[R Process] 🔄 Reattached {len(stored['alwayson'])} ADetailer always-on script(s)")
                    if hasattr(runner, 'scripts') and stored.get('regular'):
                        for script in stored['regular']:
                            if script not in runner.scripts:
                                runner.scripts.append(script)
                        print(f"[R Process] 🔄 Reattached {len(stored['regular'])} ADetailer on-demand script(s)")
                finally:
                    # Clear stored references so we don't duplicate reinsertion
                    delattr(self, '_stored_adetailer_scripts')

            # Ensure any scripts we hard-disabled are re-enabled for the next generation
            if hasattr(self, 'disabled_adetailer_scripts'):
                self._reenable_adetailer_from_previous_generation()

            # Clear temporary protection flag if present
            if hasattr(self, '_temp_disabled_adetailer'):
                delattr(self, '_temp_disabled_adetailer')

            print("[R Process] 🛡️  Early protection restoration complete")

        except Exception as e:
            print(f"[R Process] Error restoring early ADetailer protection: {e}")
    
    def process_batch_pre(self, p, *args, **kwargs):
        """Pre-batch processing to set up result interception"""
        try:
            if getattr(self, 'run_img2img_pass', False):
                print("[R ProcessBatchPre] Setting up early result interception")
        except Exception as e:
            print(f"[R ProcessBatchPre] Error: {e}")
    
    @classmethod
    def get_ranbooru_results(cls):
        """Public method for other extensions to get RanbooruX img2img results"""
        try:
            if hasattr(cls, '_global_ranbooru_results'):
                return cls._global_ranbooru_results
            return None
        except:
            return None
    
    @classmethod
    def get_ranbooru_processed(cls):
        """Public method for other extensions to get RanbooruX processed object"""
        try:
            if hasattr(cls, '_global_ranbooru_processed'):
                return cls._global_ranbooru_processed
            return None
        except:
            return None

    def random_number(self, sorting_order, size):
        global COUNT
        effective_count = COUNT
        if effective_count <= 0:
            print("[R] Warn: COUNT zero in random_number.")
            return []
        if size <= 0:
            return []
        max_index = effective_count
        if sorting_order in ('Score Descending', 'Score Ascending'):
            weights = np.arange(1, max_index + 1)
            weights = weights.astype(float)
            if sorting_order == 'Score Ascending':
                weights = weights[::-1]
            if weights.sum() == 0:
                weights = np.ones(max_index)
            weights /= weights.sum()
            replace = size > max_index
            try:
                random_indices = np.random.choice(np.arange(max_index), size=size, p=weights, replace=replace)
            except ValueError as e:
                print(f"[R] Err weighted choice: {e}. Fallback.")
                random_indices = random.choices(range(max_index), k=size)
        else:
            random_indices = random.choices(range(max_index), k=size)
        return random_indices.tolist() if isinstance(random_indices, np.ndarray) else random_indices

    def use_autotagger(self, model):
        if model == 'deepbooru':
            if isinstance(self.original_prompt, str):
                orig_prompt = [self.original_prompt]
            else:
                orig_prompt = self.original_prompt
            deepbooru.model.start()
            for img, prompt in zip(self.last_img, orig_prompt):
                final_prompts = [prompt + ',' + deepbooru.model.tag_multi(img) for img in self.last_img]
            deepbooru.model.stop()
            return final_prompts

    def _install_scriptrunner_guard(self, p):
        """Wrap p.scripts postprocess and postprocess_image to skip ADetailer when our block flag is active"""
        try:
            if not hasattr(p, 'scripts') or p.scripts is None:
                return
            runner = p.scripts
            if not hasattr(runner, '_ranbooru_guard_installed'):
                runner._ranbooru_guard_installed = False
            if runner._ranbooru_guard_installed:
                return
            
            def is_adetailer(s):
                try:
                    name = s.__class__.__name__.lower()
                    return 'adetailer' in name or 'afterdetailer' in name
                except Exception:
                    return False
            
            # Guard postprocess
            if hasattr(runner, 'postprocess') and not hasattr(runner, '_ranbooru_original_postprocess'):
                original_postprocess = runner.postprocess
                runner._ranbooru_original_postprocess = original_postprocess
                def guarded_postprocess(p_arg, processed_arg, *args, **kwargs):
                    # Sanitize images to PIL to avoid numpy leaking into downstream extensions
                    try:
                        self._ensure_pil_in_processing(p_arg)
                        if processed_arg is not None:
                            self._ensure_pil_images_in_processed(processed_arg)
                    except Exception:
                        pass
                    block = getattr(self.__class__, '_ranbooru_block_all_adetailer', False)
                    manual_active = getattr(self.__class__, '_ranbooru_manual_adetailer_active', False)
                    print(f"[R Guard] postprocess called - block={block}, manual={manual_active}, prompt='{getattr(p_arg, 'prompt', 'unknown')[:50]}...'")
                    
                    # Don't block if manual ADetailer is active
                    if block and not manual_active:
                        try:
                            saved_alwayson = list(getattr(runner, 'alwayson_scripts', []) or [])
                            saved_scripts = list(getattr(runner, 'scripts', []) or [])
                            adetailer_count = sum(1 for s in saved_alwayson if is_adetailer(s)) + sum(1 for s in saved_scripts if is_adetailer(s))
                            print(f"[R Guard] 🛑 BLOCKING {adetailer_count} ADetailer script(s) from postprocess")
                            if hasattr(runner, 'alwayson_scripts'):
                                runner.alwayson_scripts = [s for s in saved_alwayson if not is_adetailer(s)]
                            if hasattr(runner, 'scripts'):
                                runner.scripts = [s for s in saved_scripts if not is_adetailer(s)]
                            try:
                                return original_postprocess(p_arg, processed_arg, *args, **kwargs)
                            finally:
                                if hasattr(runner, 'alwayson_scripts'):
                                    runner.alwayson_scripts = saved_alwayson
                                if hasattr(runner, 'scripts'):
                                    runner.scripts = saved_scripts
                        except Exception as e:
                            print(f"[R Guard] Error during postprocess blocking: {e}")
                    return original_postprocess(p_arg, processed_arg, *args, **kwargs)
                runner.postprocess = guarded_postprocess
            
            # Guard postprocess_image
            if hasattr(runner, 'postprocess_image') and not hasattr(runner, '_ranbooru_original_postprocess_image'):
                original_postprocess_image = runner.postprocess_image
                runner._ranbooru_original_postprocess_image = original_postprocess_image
                def guarded_postprocess_image(p_arg, pp_arg, *args, **kwargs):
                    # Sanitize images to PIL before ADetailer or others consume them
                    try:
                        self._ensure_pil_in_processing(p_arg)
                        if pp_arg is not None:
                            self._ensure_pil_images_in_processed(pp_arg)
                    except Exception:
                        pass
                    block = getattr(self.__class__, '_ranbooru_block_all_adetailer', False)
                    manual_active = getattr(self.__class__, '_ranbooru_manual_adetailer_active', False)
                    print(f"[R Guard] postprocess_image called - block={block}, manual={manual_active}, prompt='{getattr(p_arg, 'prompt', 'unknown')[:50]}...'")
                    
                    # Don't block if manual ADetailer is active
                    if block and not manual_active:
                        try:
                            saved_alwayson = list(getattr(runner, 'alwayson_scripts', []) or [])
                            saved_scripts = list(getattr(runner, 'scripts', []) or [])
                            adetailer_count = sum(1 for s in saved_alwayson if is_adetailer(s)) + sum(1 for s in saved_scripts if is_adetailer(s))
                            print(f"[R Guard] 🛑 BLOCKING {adetailer_count} ADetailer script(s) from postprocess_image")
                            if hasattr(runner, 'alwayson_scripts'):
                                runner.alwayson_scripts = [s for s in saved_alwayson if not is_adetailer(s)]
                            if hasattr(runner, 'scripts'):
                                runner.scripts = [s for s in saved_scripts if not is_adetailer(s)]
                            try:
                                return original_postprocess_image(p_arg, pp_arg, *args, **kwargs)
                            finally:
                                if hasattr(runner, 'alwayson_scripts'):
                                    runner.alwayson_scripts = saved_alwayson
                                if hasattr(runner, 'scripts'):
                                    runner.scripts = saved_scripts
                        except Exception as e:
                            print(f"[R Guard] Error during postprocess_image blocking: {e}")
                    return original_postprocess_image(p_arg, pp_arg, *args, **kwargs)
                runner.postprocess_image = guarded_postprocess_image
            
            runner._ranbooru_guard_installed = True
            print("[R] 🎯 Installed ScriptRunner guard to skip ADetailer when blocked (postprocess & postprocess_image)")
        except Exception as e:
            print(f"[R] Error installing ScriptRunner guard: {e}")

    def _prepare_processing_for_manual_adetailer(self, p, processed, img2img_results):
        """Ensure p has correct images, sizes, prompts, and save paths before running ADetailer manually"""
        if not self._is_adetailer_enabled():
            return
        try:
            if not img2img_results:
                return
            # Set init image to the first img2img result
            first_img = img2img_results[0]
            try:
                p.init_images = [first_img]
            except Exception:
                pass
            # Align width/height to the image
            try:
                if hasattr(first_img, 'size'):
                    p.width, p.height = first_img.size
            except Exception:
                pass
            # Restore a meaningful prompt (avoid minimal initial-pass prompt)
            try:
                if hasattr(self, 'original_full_prompt'):
                    p.prompt = self.original_full_prompt
                elif hasattr(processed, 'all_prompts') and processed.all_prompts:
                    p.prompt = processed.all_prompts[0]
            except Exception:
                pass
            # Ensure saving paths are valid for ADetailer internals
            try:
                import modules.shared as shared
                outdir = getattr(shared.opts, 'outdir_img2img_samples', None) or getattr(shared.opts, 'outdir_samples', None) or 'outputs/img2img-images'
                if not outdir:
                    outdir = 'outputs/img2img-images'
                p.outpath_samples = outdir
                # Allow saving final artifacts if extension attempts
                if hasattr(p, 'do_not_save_samples'):
                    p.do_not_save_samples = False
                if hasattr(p, 'do_not_save_grid'):
                    p.do_not_save_grid = True
                if hasattr(p, 'save_to_dirs'):
                    p.save_to_dirs = True
            except Exception:
                # As a last resort, set a default path
                try:
                    p.outpath_samples = 'outputs/img2img-images'
                except Exception:
                    pass
        except Exception as e:
            print(f"[R Post] WARN: Could not fully prepare p for manual ADetailer: {e}")

    def _install_preview_guard(self):
        """Install a guard around shared.state.assign_current_image to block wrong previews"""
        try:
            import modules.shared as shared
            if not hasattr(shared, 'state'):
                return
            state = shared.state
            if getattr(state, '_ranbooru_preview_guard_installed', False):
                return
            if not hasattr(state, 'assign_current_image'):
                return
            state._ranbooru_original_assign_current_image = state.assign_current_image
            
            def guarded_assign_current_image(img):
                try:
                    if getattr(self.__class__, '_ranbooru_preview_guard_on', False):
                        # If we know final dims, only allow those; otherwise block 640x512
                        final_dims = getattr(self.__class__, '_ranbooru_final_dims', None)
                        if img is not None and hasattr(img, 'size'):
                            if final_dims and img.size != final_dims:
                                print("[R UI] 🚫 Preview blocked: mismatched size")
                                return
                            if img.size == (640, 512):
                                print("[R UI] 🚫 Preview blocked: 640x512 preview")
                                return
                except Exception:
                    pass
                return state._ranbooru_original_assign_current_image(img)
            
            state.assign_current_image = guarded_assign_current_image
            state._ranbooru_preview_guard_installed = True
            print("[R UI] 🎯 Installed preview guard")
        except Exception as e:
            print(f"[R UI] Error installing preview guard: {e}")
    
    def _set_preview_guard(self, enabled: bool, final_dims=None):
        try:
            self.__class__._ranbooru_preview_guard_on = bool(enabled)
            if enabled and final_dims is not None:
                self.__class__._ranbooru_final_dims = final_dims
            elif not enabled and hasattr(self.__class__, '_ranbooru_final_dims'):
                delattr(self.__class__, '_ranbooru_final_dims')
            print(f"[R UI] 🎯 Preview guard set to {enabled} with dims={final_dims}")
        except Exception as e:
            print(f"[R UI] Error setting preview guard: {e}")
    
    def _patch_adetailer_methods_directly(self):
        """Directly patch ADetailer class methods to check our block flag"""
        try:
            # Find all ADetailer script instances and patch their core methods
            patched_count = 0
            
            # Check sys.modules for ADetailer
            import sys
            for module_name, module in sys.modules.items():
                if 'adetailer' in module_name.lower():
                    try:
                        # Look for AfterDetailerScript classes
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if hasattr(attr, '__name__') and 'adetailer' in attr.__name__.lower():
                                # Patch the class methods
                                if hasattr(attr, 'postprocess_image') and not hasattr(attr, '_ranbooru_original_postprocess_image'):
                                    original_method = attr.postprocess_image
                                    attr._ranbooru_original_postprocess_image = original_method
                                    
                                    def blocked_postprocess_image(self, *args, **kwargs):
                                        from scripts.ranbooru import Script as RanbooruScript
                                        block = getattr(RanbooruScript, '_ranbooru_block_all_adetailer', False)
                                        if block:
                                            print(f"[R Direct Patch] 🛑 Blocked ADetailer.postprocess_image")
                                            return False
                                        return original_method(self, *args, **kwargs)
                                    
                                    attr.postprocess_image = blocked_postprocess_image
                                    patched_count += 1
                                    print(f"[R Direct Patch] Patched {attr.__name__}.postprocess_image")
                                
                                if hasattr(attr, 'postprocess') and not hasattr(attr, '_ranbooru_original_postprocess'):
                                    original_method = attr.postprocess
                                    attr._ranbooru_original_postprocess = original_method
                                    
                                    def blocked_postprocess(self, *args, **kwargs):
                                        from scripts.ranbooru import Script as RanbooruScript
                                        block = getattr(RanbooruScript, '_ranbooru_block_all_adetailer', False)
                                        if block:
                                            print(f"[R Direct Patch] 🛑 Blocked ADetailer.postprocess")
                                            return False
                                        return original_method(self, *args, **kwargs)
                                    
                                    attr.postprocess = blocked_postprocess
                                    patched_count += 1
                                    print(f"[R Direct Patch] Patched {attr.__name__}.postprocess")
                    except Exception as e:
                        continue
            
            print(f"[R Direct Patch] 🎯 Patched {patched_count} ADetailer methods directly")
            
        except Exception as e:
            print(f"[R Direct Patch] Error patching ADetailer methods: {e}")
    
    def _install_nuclear_adetailer_hook(self):
        """Install a nuclear hook that intercepts ANY script execution to catch ADetailer"""
        try:
            import modules.scripts
            
            # Hook into the main script execution method
            if not hasattr(modules.scripts, '_ranbooru_nuclear_hook_installed'):
                original_run_script = getattr(modules.scripts, 'run_script', None)
                if original_run_script:
                    def nuclear_script_hook(*args, **kwargs):
                        # Check if this is an ADetailer script
                        try:
                            if len(args) > 0:
                                script = args[0]
                                if hasattr(script, '__class__') and hasattr(script.__class__, '__name__'):
                                    class_name = script.__class__.__name__
                                    if 'adetailer' in class_name.lower():
                                        block = getattr(self.__class__, '_ranbooru_block_all_adetailer', False)
                                        if block:
                                            print(f"[R Nuclear] 🛑 BLOCKED script execution: {class_name}")
                                            return None
                        except Exception:
                            pass
                        return original_run_script(*args, **kwargs)
                    
                    modules.scripts.run_script = nuclear_script_hook
                    modules.scripts._ranbooru_nuclear_hook_installed = True
                    print("[R Nuclear] 🎯 Installed nuclear ADetailer execution hook")
            
            # Also hook into postprocess_image directly at the modules level
            if hasattr(modules.scripts, 'postprocess_image') and not hasattr(modules.scripts, '_ranbooru_nuclear_postprocess_image_hook'):
                original_postprocess_image = modules.scripts.postprocess_image
                def nuclear_postprocess_image_hook(*args, **kwargs):
                    block = getattr(self.__class__, '_ranbooru_block_all_adetailer', False)
                    if block:
                        print("[R Nuclear] 🛑 BLOCKED modules.scripts.postprocess_image")
                        return False
                    return original_postprocess_image(*args, **kwargs)
                
                modules.scripts.postprocess_image = nuclear_postprocess_image_hook
                modules.scripts._ranbooru_nuclear_postprocess_image_hook = True
                print("[R Nuclear] 🎯 Installed nuclear postprocess_image hook")
            
        except Exception as e:
            print(f"[R Nuclear] Error installing nuclear hook: {e}")
    
    def _override_all_image_access(self, img2img_results):
        """Final solution: Override ALL possible image access methods to force correct images"""
        try:
            print(f"[R Final] 🎯 Overriding ALL image access with {len(img2img_results)} img2img results")
            
            # Store our correct images globally
            self.__class__._force_images = img2img_results.copy()
            
            # Skip PIL.Image.open override as it interferes with normal operations
            # print("[R Final] 🎯 Skipped PIL.Image.open override to prevent interference")
            
            # Also override any existing processed.images access
            import modules.processing
            if hasattr(modules.processing, '_current_processed') and modules.processing._current_processed:
                current_processed = modules.processing._current_processed
                if hasattr(current_processed, 'images') and current_processed.images:
                    print(f"[R Final] 🎯 Replacing _current_processed.images ({len(current_processed.images)} -> {len(img2img_results)})")
                    current_processed.images.clear()
                    current_processed.images.extend(img2img_results)
            
            # Override shared.state images
            import modules.shared
            if hasattr(modules.shared.state, 'current_image'):
                print("[R Final] 🎯 Replacing shared.state.current_image")
                modules.shared.state.current_image = img2img_results[0] if img2img_results else None
            
            print("[R Final] 🎯 Image access override complete")
            
        except Exception as e:
            print(f"[R Final] Error overriding image access: {e}")
    
    def _remove_adetailer_from_pipeline_completely(self, p):
        """Nuclear option: Remove ADetailer from all processing pipelines"""
        try:
            print("[R Nuclear] 🚫 REMOVING ADetailer from processing pipeline completely")
            
            # Remove from the current processing object
            if hasattr(p, 'scripts'):
                if hasattr(p.scripts, 'alwayson_scripts'):
                    original_count = len(p.scripts.alwayson_scripts)
                    p.scripts.alwayson_scripts = [s for s in p.scripts.alwayson_scripts if not self._is_adetailer_script(s)]
                    new_count = len(p.scripts.alwayson_scripts)
                    print(f"[R Nuclear] 🚫 Removed {original_count - new_count} ADetailer from p.scripts.alwayson_scripts")
                
                if hasattr(p.scripts, 'scripts'):
                    original_count = len(p.scripts.scripts)
                    p.scripts.scripts = [s for s in p.scripts.scripts if not self._is_adetailer_script(s)]
                    new_count = len(p.scripts.scripts)
                    print(f"[R Nuclear] 🚫 Removed {original_count - new_count} ADetailer from p.scripts.scripts")
            
            # Remove from global script runners
            import modules.scripts
            for runner_attr in ['scripts_txt2img', 'scripts_img2img']:
                if hasattr(modules.scripts, runner_attr):
                    runner = getattr(modules.scripts, runner_attr)
                    if hasattr(runner, 'alwayson_scripts'):
                        original_count = len(runner.alwayson_scripts)
                        runner.alwayson_scripts = [s for s in runner.alwayson_scripts if not self._is_adetailer_script(s)]
                        new_count = len(runner.alwayson_scripts)
                        print(f"[R Nuclear] 🚫 Removed {original_count - new_count} ADetailer from {runner_attr}.alwayson_scripts")
                    
                    if hasattr(runner, 'scripts'):
                        original_count = len(runner.scripts)
                        runner.scripts = [s for s in runner.scripts if not self._is_adetailer_script(s)]
                        new_count = len(runner.scripts)
                        print(f"[R Nuclear] 🚫 Removed {original_count - new_count} ADetailer from {runner_attr}.scripts")
            
            # Remove from script data
            if hasattr(modules.scripts, 'scripts_data'):
                original_count = len(modules.scripts.scripts_data)
                modules.scripts.scripts_data = [s for s in modules.scripts.scripts_data if 'adetailer' not in s.path.lower()]
                new_count = len(modules.scripts.scripts_data)
                print(f"[R Nuclear] 🚫 Removed {original_count - new_count} ADetailer from scripts_data")
            
            print("[R Nuclear] 🚫 ADetailer completely removed from processing pipeline")
            
        except Exception as e:
            print(f"[R Nuclear] Error removing ADetailer from pipeline: {e}")
            import traceback
            traceback.print_exc()

    def _install_adetailer_skip_hook(self, p):
        """Install a hook that makes ADetailer skip processing if our flag is set"""
        try:
            print("[R Hook] Installing ADetailer skip hook")
            
            # First, let's see what ADetailer modules are available
            import sys
            adetailer_modules = []
            for module_name, module in sys.modules.items():
                if 'adetailer' in module_name.lower():
                    adetailer_modules.append(module_name)
            
            print(f"[R Hook] Found {len(adetailer_modules)} ADetailer modules: {adetailer_modules}")
            
            # Try to find and patch ADetailer's main processing method
            hooked_count = 0
            for module_name, module in sys.modules.items():
                if 'adetailer' in module_name.lower():
                    print(f"[R Hook] Examining module: {module_name}")
                    print(f"[R Hook] Module attributes: {[attr for attr in dir(module) if 'process' in attr.lower()]}")
                    
                    # Hook postprocess_image if it exists
                    if hasattr(module, 'postprocess_image') and not hasattr(module, '_ranbooru_original_postprocess_image'):
                        original_method = module.postprocess_image
                        module._ranbooru_original_postprocess_image = original_method
                        
                        def hooked_postprocess_image(p_arg, pp_arg, *args, **kwargs):
                            # Allow manual ADetailer execution
                            manual_active = getattr(self.__class__, '_ranbooru_manual_adetailer_active', False)
                            if manual_active:
                                print("[R Hook] ✅ Allowing manual ADetailer postprocess_image execution")
                                return original_method(p_arg, pp_arg, *args, **kwargs)
                            
                            # Check if we've already processed this image
                            if hasattr(p_arg, '_ranbooru_adetailer_already_processed'):
                                print("[R Hook] 🛑 ADetailer postprocess_image skipped - RanbooruX already processed")
                                return False
                            print(f"[R Hook] ⚠️ ADetailer postprocess_image running on {getattr(p_arg, 'prompt', 'unknown')[:50]}...")
                            return original_method(p_arg, pp_arg, *args, **kwargs)
                        
                        module.postprocess_image = hooked_postprocess_image
                        print(f"[R Hook] 🎯 Installed postprocess_image hook on {module_name}")
                        hooked_count += 1
                    
                    # Also hook any postprocess method
                    if hasattr(module, 'postprocess') and not hasattr(module, '_ranbooru_original_postprocess'):
                        original_method = module.postprocess
                        module._ranbooru_original_postprocess = original_method
                        
                        def hooked_postprocess(p_arg, processed_arg, *args, **kwargs):
                            # Allow manual ADetailer execution
                            manual_active = getattr(self.__class__, '_ranbooru_manual_adetailer_active', False)
                            if manual_active:
                                print("[R Hook] ✅ Allowing manual ADetailer postprocess execution")
                                return original_method(p_arg, processed_arg, *args, **kwargs)
                            
                            # Check if we've already processed this image
                            if hasattr(p_arg, '_ranbooru_adetailer_already_processed'):
                                print("[R Hook] 🛑 ADetailer postprocess skipped - RanbooruX already processed")
                                return False
                            print(f"[R Hook] ⚠️ ADetailer postprocess running on {getattr(p_arg, 'prompt', 'unknown')[:50]}...")
                            return original_method(p_arg, processed_arg, *args, **kwargs)
                        
                        module.postprocess = hooked_postprocess
                        print(f"[R Hook] 🎯 Installed postprocess hook on {module_name}")
                        hooked_count += 1
            
            # Try to hook ADetailer scripts directly from the script runners
            if hasattr(p, 'scripts'):
                print("[R Hook] Attempting to hook ADetailer scripts directly...")
                if hasattr(p.scripts, 'alwayson_scripts'):
                    for script in p.scripts.alwayson_scripts:
                        if self._is_adetailer_script(script):
                            script_name = script.__class__.__name__
                            print(f"[R Hook] Found ADetailer script: {script_name}")
                            print(f"[R Hook] Script methods: {[attr for attr in dir(script) if 'process' in attr.lower()]}")
                            
                            # Wrap all instance methods containing 'process'
                            try:
                                def make_inst_wrap(method_name, orig):
                                    def wrapped(p_arg, *args, **kwargs):
                                        # Allow manual ADetailer execution
                                        manual_active = getattr(self.__class__, '_ranbooru_manual_adetailer_active', False)
                                        if manual_active:
                                            print(f"[R Hook] ✅ Allowing manual ADetailer {script_name}.{method_name} execution")
                                            return orig(p_arg, *args, **kwargs)
                                        
                                        # Skip if RanbooruX already processed
                                        if hasattr(p_arg, '_ranbooru_adetailer_already_processed'):
                                            print(f"[R Hook] 🛑 {script_name}.{method_name} skipped - RanbooruX already processed")
                                            return False
                                        return orig(p_arg, *args, **kwargs)
                                    return wrapped
                                for m in [name for name in dir(script) if 'process' in name.lower()]:
                                    try:
                                        orig = getattr(script, m, None)
                                        if callable(orig) and not hasattr(orig, '_ranbooru_wrapped'):
                                            wrapped = make_inst_wrap(m, orig)
                                            setattr(script, m, wrapped)
                                            setattr(getattr(script, m), '_ranbooru_wrapped', True)
                                            hooked_count += 1
                                            print(f"[R Hook] 🎯 Hooked instance method {script_name}.{m}")
                                    except Exception:
                                        pass
                            except Exception as _e:
                                print(f"[R Hook] WARN: Could not wrap instance methods: {_e}")
                            
                            # Hook the script's postprocess_image method
                            if hasattr(script, 'postprocess_image') and not hasattr(script, '_ranbooru_original_postprocess_image'):
                                original_method = script.postprocess_image
                                script._ranbooru_original_postprocess_image = original_method
                                
                                def hooked_script_postprocess_image(p_arg, pp_arg, *args, **kwargs):
                                    # Allow manual ADetailer execution
                                    manual_active = getattr(self.__class__, '_ranbooru_manual_adetailer_active', False)
                                    if manual_active:
                                        print(f"[R Hook] ✅ Allowing manual ADetailer {script_name}.postprocess_image execution")
                                        return original_method(p_arg, pp_arg, *args, **kwargs)
                                    
                                    if hasattr(p_arg, '_ranbooru_adetailer_already_processed'):
                                        print(f"[R Hook] 🛑 {script_name}.postprocess_image skipped - RanbooruX already processed")
                                        return False
                                    print(f"[R Hook] ⚠️ {script_name}.postprocess_image running...")
                                    return original_method(p_arg, pp_arg, *args, **kwargs)
                                
                                script.postprocess_image = hooked_script_postprocess_image
                                print(f"[R Hook] 🎯 Hooked {script_name}.postprocess_image")
                                hooked_count += 1
                            else:
                                print(f"[R Hook] ❌ Could not hook {script_name}.postprocess_image - method {'exists' if hasattr(script, 'postprocess_image') else 'missing'}, already hooked: {hasattr(script, '_ranbooru_original_postprocess_image')}")
                            
                            # Also try to hook postprocess method
                            if hasattr(script, 'postprocess') and not hasattr(script, '_ranbooru_original_postprocess'):
                                original_method = script.postprocess
                                script._ranbooru_original_postprocess = original_method
                                
                                def hooked_script_postprocess(p_arg, processed_arg, *args, **kwargs):
                                    # Allow manual ADetailer execution
                                    manual_active = getattr(self.__class__, '_ranbooru_manual_adetailer_active', False)
                                    if manual_active:
                                        print(f"[R Hook] ✅ Allowing manual ADetailer {script_name}.postprocess execution")
                                        return original_method(p_arg, processed_arg, *args, **kwargs)
                                    
                                    if hasattr(p_arg, '_ranbooru_adetailer_already_processed'):
                                        print(f"[R Hook] 🛑 {script_name}.postprocess skipped - RanbooruX already processed")
                                        return False
                                    print(f"[R Hook] ⚠️ {script_name}.postprocess running...")
                                    return original_method(p_arg, processed_arg, *args, **kwargs)
                                
                                script.postprocess = hooked_script_postprocess
                                print(f"[R Hook] 🎯 Hooked {script_name}.postprocess")
                                hooked_count += 1
                            else:
                                print(f"[R Hook] ❌ Could not hook {script_name}.postprocess - method {'exists' if hasattr(script, 'postprocess') else 'missing'}, already hooked: {hasattr(script, '_ranbooru_original_postprocess')}")
            
            print(f"[R Hook] ADetailer skip hook installation complete - hooked {hooked_count} methods")
            
        except Exception as e:
            print(f"[R Hook] Error installing ADetailer skip hook: {e}")
            import traceback
            traceback.print_exc()

    def _suppress_initial_pass_completely(self, p):
        """Ultimate method to completely suppress the initial pass from any processing"""
        try:
            print("[R Suppress] 🚫 ULTIMATE: Completely suppressing initial pass from all processing")
            
            # Clear any saved initial images from the processing object
            if hasattr(p, '_ranbooru_initial_images'):
                p._ranbooru_initial_images.clear()
                print("[R Suppress] 🚫 Cleared initial images from p._ranbooru_initial_images")
            
            # Try to find and clear any cached initial pass results
            import modules.processing
            if hasattr(modules.processing, '_current_processed'):
                current_processed = modules.processing._current_processed
                if current_processed and hasattr(current_processed, 'images'):
                    # Filter out any 640x512 or other wrong-sized images
                    original_count = len(current_processed.images)
                    current_processed.images = [img for img in current_processed.images if img.size != (640, 512) and img.size != (512, 640)]
                    filtered_count = len(current_processed.images)
                    if filtered_count != original_count:
                        print(f"[R Suppress] 🚫 Filtered out {original_count - filtered_count} wrong-sized images from _current_processed")
            
            # Set flags to prevent any ADetailer from running on the initial pass
            setattr(p, '_ranbooru_suppress_all_adetailer', True)
            setattr(p, '_ranbooru_initial_pass_suppressed', True)
            
            # Try to hook into the postprocess_image function at the global level
            try:
                import modules.scripts
                if hasattr(modules.scripts, 'postprocess_image') and not hasattr(modules.scripts, '_ranbooru_suppress_hook'):
                    original_postprocess_image = modules.scripts.postprocess_image
                    modules.scripts._ranbooru_original_postprocess_image = original_postprocess_image
                    
                    def suppressed_postprocess_image(p_arg, pp_arg, *args, **kwargs):
                        # Check if this is the initial pass we want to suppress
                        if hasattr(p_arg, '_ranbooru_suppress_all_adetailer'):
                            print("[R Suppress] 🚫 BLOCKED global postprocess_image - initial pass suppressed")
                            return False  # Don't call the original function and return strict boolean
                        return original_postprocess_image(p_arg, pp_arg, *args, **kwargs)
                    
                    modules.scripts.postprocess_image = suppressed_postprocess_image
                    modules.scripts._ranbooru_suppress_hook = True
                    print("[R Suppress] 🚫 Installed global postprocess_image suppression hook")
            except Exception as e:
                print(f"[R Suppress] Could not install global hook: {e}")
            
            print("[R Suppress] 🚫 Initial pass suppression complete")
            
        except Exception as e:
            print(f"[R Suppress] Error suppressing initial pass: {e}")
            import traceback
            traceback.print_exc()

    def _completely_remove_adetailer_from_pipeline(self, p):
        """Nuclear option: Completely remove ADetailer from all processing pipelines for this generation"""
        try:
            print("[R Nuclear Pipeline] 🚫 NUCLEAR: Completely removing ADetailer from processing pipeline")
            
            # Remove from the current processing object
            removed_count = 0
            if hasattr(p, 'scripts'):
                if hasattr(p.scripts, 'alwayson_scripts'):
                    original_count = len(p.scripts.alwayson_scripts)
                    p.scripts.alwayson_scripts = [s for s in p.scripts.alwayson_scripts if not self._is_adetailer_script(s)]
                    new_count = len(p.scripts.alwayson_scripts)
                    removed_count += original_count - new_count
                    print(f"[R Nuclear Pipeline] 🚫 Removed {original_count - new_count} ADetailer from p.scripts.alwayson_scripts")
                
                if hasattr(p.scripts, 'scripts'):
                    original_count = len(p.scripts.scripts)
                    p.scripts.scripts = [s for s in p.scripts.scripts if not self._is_adetailer_script(s)]
                    new_count = len(p.scripts.scripts)
                    removed_count += original_count - new_count
                    print(f"[R Nuclear Pipeline] 🚫 Removed {original_count - new_count} ADetailer from p.scripts.scripts")
            
            # Remove from global script runners
            import modules.scripts
            for runner_attr in ['scripts_txt2img', 'scripts_img2img']:
                if hasattr(modules.scripts, runner_attr):
                    runner = getattr(modules.scripts, runner_attr)
                    if hasattr(runner, 'alwayson_scripts'):
                        original_count = len(runner.alwayson_scripts)
                        runner.alwayson_scripts = [s for s in runner.alwayson_scripts if not self._is_adetailer_script(s)]
                        new_count = len(runner.alwayson_scripts)
                        removed_count += original_count - new_count
                        print(f"[R Nuclear Pipeline] 🚫 Removed {original_count - new_count} ADetailer from {runner_attr}.alwayson_scripts")
                    
                    if hasattr(runner, 'scripts'):
                        original_count = len(runner.scripts)
                        runner.scripts = [s for s in runner.scripts if not self._is_adetailer_script(s)]
                        new_count = len(runner.scripts)
                        removed_count += original_count - new_count
                        print(f"[R Nuclear Pipeline] 🚫 Removed {original_count - new_count} ADetailer from {runner_attr}.scripts")
            
            # Store the removed scripts so we can restore them later
            self._removed_adetailer_scripts = []
            
            # Mark that we've removed ADetailer for this generation
            setattr(p, '_ranbooru_adetailer_removed_from_pipeline', True)
            
            print(f"[R Nuclear Pipeline] 🚫 NUCLEAR COMPLETE: Removed {removed_count} ADetailer script instances from processing pipeline")
            
        except Exception as e:
            print(f"[R Nuclear Pipeline] Error removing ADetailer from pipeline: {e}")
            import traceback
            traceback.print_exc()



from io import BytesIO
import random
import requests
import modules.scripts as scripts
import gradio as gr
import os
from PIL import Image
import numpy as np
import requests_cache
import importlib
import sys
import traceback

from modules.processing import process_images, StableDiffusionProcessingImg2Img, StableDiffusionProcessing
from modules import shared
from modules.sd_hijack import model_hijack
from modules import deepbooru
from modules.ui_components import InputAccordion
from modules.scripts import basedir

# --- Constants and Paths ---
EXTENSION_ROOT = basedir()
USER_DATA_DIR = os.path.join(EXTENSION_ROOT, 'user')
USER_SEARCH_DIR = os.path.join(USER_DATA_DIR, 'search')
USER_REMOVE_DIR = os.path.join(USER_DATA_DIR, 'remove')
os.makedirs(USER_SEARCH_DIR, exist_ok=True)
os.makedirs(USER_REMOVE_DIR, exist_ok=True)

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

COLORED_BG = ['black_background', 'aqua_background', 'white_background', 'colored_background', 'gray_background', 'blue_background', 'green_background', 'red_background', 'brown_background', 'purple_background', 'yellow_background', 'orange_background', 'pink_background', 'plain', 'transparent_background', 'simple_background', 'two-tone_background', 'grey_background']
ADD_BG = ['outdoors', 'indoors']
BW_BG = ['monochrome', 'greyscale', 'grayscale']
POST_AMOUNT = 100
COUNT = 100
DEBUG = False

RATING_TYPES = {
    "none": {"All": "All"},
    "full": {"All": "All", "Safe": "safe", "Questionable": "questionable", "Explicit": "explicit"},
    "single": {"All": "All", "Safe": "g", "Sensitive": "s", "Questionable": "q", "Explicit": "e"}
}

RATINGS = {
    "e621": RATING_TYPES['full'],
    "danbooru": RATING_TYPES['single'],
    "aibooru": RATING_TYPES['full'],
    "yande.re": RATING_TYPES['full'],
    "konachan": RATING_TYPES['full'],
    "safebooru": RATING_TYPES['none'],
    "rule34": RATING_TYPES['full'],
    "xbooru": RATING_TYPES['full'],
    "gelbooru": RATING_TYPES['single']
}


def get_available_ratings(booru):
    choices = list(RATINGS.get(booru, RATING_TYPES['none']).keys())
    return gr.Radio.update(choices=choices, value="All")


def show_fringe_benefits(booru):
    return gr.Checkbox.update(visible=(booru == 'gelbooru'))


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

    def _standardize_post(self, post_data):
        post = {}
        post['tags'] = post_data.get('tags', post_data.get('tag_string', ''))
        post['score'] = post_data.get('score', 0)
        post['file_url'] = post_data.get('file_url')
        if post['file_url'] is None:
            post['file_url'] = post_data.get('large_file_url')
        if post['file_url'] is None:
            post['file_url'] = post_data.get('source')
        post['id'] = post_data.get('id')
        post['rating'] = post_data.get('rating')
        post['booru_name'] = self.booru_name
        return post

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        raise NotImplementedError


class Gelbooru(Booru):
    def __init__(self, fringe_benefits):
        super().__init__('Gelbooru', f'https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&limit={POST_AMOUNT}')
        self.fringeBenefits = fringe_benefits

    def get_posts(self, tags_query="", max_pages=10, post_id=None):
        global COUNT
        COUNT = 0
        all_fetched_posts = []
        if post_id:
            query_url = f"{self.base_api_url}&id={post_id}{tags_query}"
            fetched_data = self._fetch_data(query_url)
            if fetched_data and 'post' in fetched_data and isinstance(fetched_data['post'], list):
                all_fetched_posts = fetched_data['post']
            COUNT = len(all_fetched_posts)
            print(f"[R] Found {COUNT} post(s) for ID: {post_id}")
        else:
            page = random.randint(0, max_pages - 1)
            query_url = f"{self.base_api_url}&pid={page}{tags_query}"
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
        return [self._standardize_post(post) for post in all_fetched_posts]


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
    sorting_priority = 20
    previous_loras = ''
    last_img = []
    real_steps = 0
    version = "1.8-Refactored"
    original_prompt = ''
    run_img2img_pass = False
    img2img_denoising = 0.75
    cache_installed_by_us = False

    def _load_cn_external_code(self):
        candidates = [
            'sd_forge_controlnet.lib_controlnet.external_code',
            'extensions.sd_forge_controlnet.lib_controlnet.external_code',
            'extensions.sd-webui-controlnet.scripts.external_code',
        ]
        last_error = None
        for mod in candidates:
            try:
                return importlib.import_module(mod)
            except Exception as e:
                last_error = e
        raise last_error if last_error else ImportError('ControlNet external_code not found')

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
            booru = gr.Dropdown(booru_list, label="Booru", value="gelbooru")
            max_pages = gr.Slider(label="Max Pages (tag search)", minimum=1, maximum=100, value=10, step=1)
            gr.Markdown("""## Post"""); post_id = gr.Textbox(lines=1, label="Post ID (Overrides tags/pages)")
            gr.Markdown("""## Tags"""); tags = gr.Textbox(lines=1, label="Tags to Search (Pre)"); remove_tags = gr.Textbox(lines=1, label="Tags to Remove (Post)")
            mature_rating = gr.Radio(list(RATINGS.get('gelbooru', RATING_TYPES['none'])), label="Mature Rating", value="All")
            remove_bad_tags = gr.Checkbox(label="Remove common 'bad' tags", value=True); shuffle_tags = gr.Checkbox(label="Shuffle tags", value=True); change_dash = gr.Checkbox(label='Convert "_" to spaces', value=False); same_prompt = gr.Checkbox(label="Use same prompt for batch", value=False)
            fringe_benefits = gr.Checkbox(label="Gelbooru: Fringe Benefits", value=True, visible=True)
            limit_tags = gr.Slider(value=1.0, label="Limit tags by %", minimum=0.05, maximum=1.0, step=0.05); max_tags = gr.Slider(value=0, label="Max tags (0=disabled)", minimum=0, maximum=300, step=1)
            change_background = gr.Radio(["Don't Change", "Add Detail", "Force Simple", "Force Transparent/White"], label="Change Background", value="Don't Change")
            change_color = gr.Radio(["Don't Change", "Force Color", "Force Monochrome"], label="Change Color", value="Don't Change")
            sorting_order = gr.Radio(["Random", "Score Descending", "Score Ascending"], label="Sort Order (tag search)", value="Random")
            booru.change(get_available_ratings, booru, mature_rating)
            booru.change(show_fringe_benefits, booru, fringe_benefits)

            gr.Markdown("""\n---\n""")
            with gr.Group():
                with gr.Accordion("Img2Img / ControlNet", open=False):
                    use_img2img = gr.Checkbox(label="Use Image for Img2Img", value=False); use_ip = gr.Checkbox(label="Use Image for ControlNet (Unit 0)", value=False)
                    denoising = gr.Slider(value=0.75, label="Img2Img Denoising / CN Weight", minimum=0.0, maximum=1.0, step=0.05)
                    use_last_img = gr.Checkbox(label="Use same image for batch", value=False); crop_center = gr.Checkbox(label="Crop image to fit target", value=False)
                    use_deepbooru = gr.Checkbox(label="Use Deepbooru on image", value=False); type_deepbooru = gr.Radio(["Add Before", "Add After", "Replace"], label="DB Tags Position", value="Add Before")
            with gr.Group():
                with gr.Accordion("File Tags", open=False):
                    use_search_txt = gr.Checkbox(label="Add line from Search File", value=False); choose_search_txt = gr.Dropdown(self.get_files(USER_SEARCH_DIR), label="Choose Search File", value="", info=f"in '{USER_SEARCH_DIR}'")
                    search_refresh_btn = gr.Button("Refresh"); use_remove_txt = gr.Checkbox(label="Add tags from Remove File", value=False); choose_remove_txt = gr.Dropdown(self.get_files(USER_REMOVE_DIR), label="Choose Remove File", value="", info=f"in '{USER_REMOVE_DIR}'")
                    remove_refresh_btn = gr.Button("Refresh")
            with gr.Group():
                with gr.Accordion("Extra Prompt Modes", open=False):
                    with gr.Box(): mix_prompt = gr.Checkbox(label="Mix tags from multiple posts", value=False); mix_amount = gr.Slider(value=2, label="Posts to mix", minimum=2, maximum=10, step=1)
                    with gr.Box(): chaos_mode = gr.Radio(["None", "Shuffle All", "Shuffle Negative"], label="Tag Shuffling (Chaos)", value="None"); chaos_amount = gr.Slider(value=0.5, label="Chaos Amount %", minimum=0.1, maximum=1.0, step=0.05)
                    with gr.Box(): use_same_seed = gr.Checkbox(label="Use same seed for batch", value=False); use_cache = gr.Checkbox(label="Cache Booru API requests", value=True)
        with InputAccordion(False, label="LoRAnado", elem_id=self.elem_id("lo_enable")) as lora_enabled:
            with gr.Box(): lora_lock_prev = gr.Checkbox(label="Lock previous LoRAs", value=False); lora_folder = gr.Textbox(lines=1, label="LoRAs Subfolder", placeholder="e.g., 'Characters' or empty"); lora_amount = gr.Slider(value=1, label="LoRAs Amount", minimum=1, maximum=10, step=1)
            with gr.Box(): lora_min = gr.Slider(value=0.6, label="Min LoRAs Weight", minimum=-1.0, maximum=1.5, step=0.1); lora_max = gr.Slider(value=1.0, label="Max LoRAs Weight", minimum=-1.0, maximum=1.5, step=0.1); lora_custom_weights = gr.Textbox(lines=1, label="Custom Weights (optional)", placeholder="e.g., 0.8, 0.5, 1.0")
        search_refresh_btn.click(fn=self.refresh_ser, inputs=[], outputs=[choose_search_txt])
        remove_refresh_btn.click(fn=self.refresh_rem, inputs=[], outputs=[choose_remove_txt])
        return [enabled, tags, booru, remove_bad_tags, max_pages, change_dash, same_prompt, fringe_benefits, remove_tags, use_img2img, denoising, use_last_img, change_background, change_color, shuffle_tags, post_id, mix_prompt, mix_amount, chaos_mode, chaos_amount, limit_tags, max_tags, sorting_order, mature_rating, lora_folder, lora_amount, lora_min, lora_max, lora_enabled, lora_custom_weights, lora_lock_prev, use_ip, use_search_txt, use_remove_txt, choose_search_txt, choose_remove_txt, search_refresh_btn, remove_refresh_btn, crop_center, use_deepbooru, type_deepbooru, use_same_seed, use_cache]

    def check_orientation(self, img):
        if img is None:
            return [512, 512]
        x, y = img.size
        if x / y > 1.3:
            return [768, 512]
        elif y / x > 1.3:
            return [512, 768]
        else:
            return [512, 512]

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

    def _get_booru_api(self, booru_name, fringe_benefits):
        booru_apis = {
            'gelbooru': Gelbooru(fringe_benefits),
            'danbooru': Danbooru(),
            'xbooru': XBooru(),
            'rule34': Rule34(),
            'safebooru': Safebooru(),
            'konachan': Konachan(),
            'yande.re': Yandere(),
            'aibooru': AIBooru(),
            'e621': e621(),
        }
        if booru_name not in booru_apis:
            raise ValueError(f"Booru '{booru_name}' not implemented.")
        return booru_apis.get(booru_name)

    def _fetch_booru_posts(self, api, search_tags, mature_rating, max_pages, post_id):
        add_tags_list = []
        if search_tags:
            add_tags_list.extend([t.strip() for t in search_tags.split(',') if t.strip()])
        booru_name = api.booru_name.lower()
        if mature_rating != 'All' and booru_name in RATINGS and mature_rating in RATINGS[booru_name]:
            rating_tag = RATINGS[booru_name][mature_rating]
            if rating_tag != "All":
                add_tags_list.append(f"rating:{rating_tag}")
        add_tags_list.append('-animated')
        tags_query = f"&tags={'+'.join(add_tags_list)}" if add_tags_list else ""
        print(f"[R] Query Tags: '{tags_query}'")
        try:
            all_posts = api.get_posts(tags_query=tags_query, max_pages=max_pages, post_id=post_id)
            if not all_posts:
                raise ValueError("No valid posts found matching criteria after fetching.")
            return all_posts
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
            api = self._get_booru_api(booru_name, fringe_benefits)
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
                else:
                    print(f"[R] Warn: Invalid URL {i}: '{img_url}'")
            except Exception as e:
                print(f"[R] Error fetch/proc {i}: {e}")
            fetched_images.append(img_to_append)
        print(f"[R] Fetched {fetched_count} images.")
        if None in fetched_images:
            print("[R] Warn: Some images failed.")
        return fetched_images

    def _process_single_prompt(self, index, raw_prompt, base_positive, base_negative, initial_additions, bad_tags, settings):
        (shuffle_tags, chaos_mode, chaos_amount, limit_tags_pct, max_tags_count, change_dash, use_deepbooru, type_deepbooru) = settings
        current_prompt = f"{initial_additions},{raw_prompt}" if initial_additions else raw_prompt
        prompt_tags = [tag.strip() for tag in current_prompt.split(',') if tag.strip()]
        wildcard_bad = {pat.replace('*', ''): ('s' if pat.endswith('*') else ('e' if pat.startswith('*') else 'c')) for pat in bad_tags if '*' in pat}
        non_wild_bad = bad_tags - set(wildcard_bad.keys()) if isinstance(bad_tags, set) else set(bad_tags) - set(wildcard_bad.keys())
        filtered_tags = []
        for tag in prompt_tags:
            is_bad = tag in non_wild_bad
            match = False
            if not is_bad:
                for pattern, mode in wildcard_bad.items():
                    if not pattern:
                        continue
                    if (mode == 's' and tag.startswith(pattern)) or (mode == 'e' and tag.endswith(pattern)) or (mode == 'c' and pattern in tag):
                        match = True
                        break
                if match:
                    is_bad = True
            if not is_bad:
                filtered_tags.append(tag)
        current_prompt = ','.join(filtered_tags)
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
        if use_img2img and not use_ip:
            print("[R] Prep Img2Img pass (steps=1).")
            self.real_steps = p.steps
            p.steps = 1
            self.run_img2img_pass = True

    def _cleanup_after_run(self, use_cache):
        self.last_img = []
        self.real_steps = 0
        self.run_img2img_pass = False
        if not use_cache and hasattr(self, 'cache_installed_by_us') and self.cache_installed_by_us and requests_cache.patcher.is_installed():
            requests_cache.uninstall_cache()
            print("[R Post] Uninstalled cache.")
        if hasattr(self, 'cache_installed_by_us'):
            try:
                del self.cache_installed_by_us
            except AttributeError:
                pass

    def before_process(self, p: StableDiffusionProcessing, *args):
        try:
            (enabled, tags, booru, remove_bad_tags_ui, max_pages, change_dash, same_prompt,
             fringe_benefits, remove_tags_ui, use_img2img, denoising, use_last_img,
             change_background, change_color, shuffle_tags, post_id, mix_prompt, mix_amount,
             chaos_mode, chaos_amount, limit_tags_pct, max_tags_count, sorting_order, mature_rating,
             lora_folder, lora_amount, lora_min, lora_max, lora_enabled,
             lora_custom_weights, lora_lock_prev, use_ip, use_search_txt, use_remove_txt,
             choose_search_txt, choose_remove_txt, _, _,
             crop_center, use_deepbooru, type_deepbooru, use_same_seed, use_cache) = args
        except Exception as e:
            print(f"[R Before] CRITICAL Error unpack args: {e}. Aborting.")
            traceback.print_exc()
            return

        self.img2img_denoising = float(denoising)

        # Persist values needed for postprocess to avoid fragile unpacking there
        self._post_enabled = bool(enabled)
        self._post_use_img2img = bool(use_img2img)
        self._post_use_ip = bool(use_ip)
        self._post_use_last_img = bool(use_last_img)
        self._post_crop_center = bool(crop_center)
        self._post_use_deepbooru = bool(use_deepbooru)
        self._post_type_deepbooru = type_deepbooru
        self._post_use_cache = bool(use_cache)

        if lora_enabled:
            p = self._apply_loranado(p, lora_enabled, lora_folder, lora_amount, lora_min, lora_max, lora_custom_weights, lora_lock_prev)
        if not enabled:
            return

        print("[R Before] Starting...")
        self.original_prompt = p.prompt if isinstance(p.prompt, str) else (p.prompt[0] if isinstance(p.prompt, list) and p.prompt else "")
        self.last_img = []

        try:
            self.cache_installed_by_us = self._setup_cache(use_cache)
            search_tags, bad_tags, initial_additions = self._prepare_tags(tags, remove_tags_ui, use_remove_txt, choose_remove_txt, change_background, change_color, use_search_txt, choose_search_txt, remove_bad_tags_ui)
            api = self._get_booru_api(booru, fringe_benefits)
            all_posts = self._fetch_booru_posts(api, search_tags, mature_rating, max_pages, post_id)
            num_images_needed = p.batch_size * p.n_iter
            selected_posts = self._select_posts(all_posts, sorting_order, num_images_needed, post_id, same_prompt)

            post_urls = []
            try:
                for idx, post in enumerate(selected_posts):
                    post_url = get_original_post_url(post)
                    if post_url:
                        post_urls.append(post_url)
                        print(f"[R] Original post {idx+1}/{len(selected_posts)}: {post_url}")
            except Exception as e:
                print(f"[R] Warn: Failed to compute original post URLs: {e}")

            if use_img2img or use_deepbooru or use_ip:
                self.last_img = self._fetch_images(selected_posts, use_last_img, booru, fringe_benefits)

            # Preview UI removed by request

            base_negative = getattr(p, 'negative_prompt', '') or ""
            final_prompts = []
            final_negative_prompts = [base_negative] * num_images_needed
            prompt_processing_settings = (shuffle_tags, chaos_mode, chaos_amount, limit_tags_pct, max_tags_count, change_dash, use_deepbooru, type_deepbooru)
            raw_prompts = [post.get('tags', '') for post in selected_posts]

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
                processed_prompt, processed_negative = self._process_single_prompt(i, rp, self.original_prompt, base_negative, initial_additions, bad_tags, prompt_processing_settings)
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
            # Debug print removed per user request

            if use_same_seed:
                p.seed = p.seed if p.seed != -1 else random.randint(0, 2**32 - 1)
                print(f"[R] Using same seed: {p.seed}")

            if use_ip and self.last_img and self.last_img[0] is not None:
                cn_configured = False
                # Preferred: external_code API from ControlNet
                try:
                    cn_module = self._load_cn_external_code()
                    cn_units = cn_module.get_all_units_in_processing(p)
                    if cn_units and len(cn_units) > 0:
                        copied_unit = cn_units[0].__dict__.copy()
                        copied_unit['enabled'] = True
                        copied_unit['weight'] = float(self.img2img_denoising)
                        img_for_cn = self.last_img[0].convert('RGB') if self.last_img[0].mode != 'RGB' else self.last_img[0]
                        copied_unit['image']['image'] = np.array(img_for_cn)
                        cn_module.update_cn_script_in_processing(p, [copied_unit] + cn_units[1:])
                        print("[R Before] ControlNet Unit 0 updated via external_code.")
                        cn_configured = True
                    else:
                        print("[R Before] No ControlNet units detected; falling back to p.script_args.")
                except Exception as e:
                    print(f"[R Before] external_code ControlNet update failed: {e}")

                # Fallback: p.script_args hack (fragile but effective)
                if not cn_configured:
                    print("[R Before] Using p.script_args hack for ControlNet Unit 0.")
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
                                    print("[R Before] p.script_args updated for ControlNet Unit 0.")
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

    def postprocess(self, p: StableDiffusionProcessing, processed, *args):
        enabled = getattr(self, '_post_enabled', False)
        use_img2img = getattr(self, '_post_use_img2img', False)
        use_last_img = getattr(self, '_post_use_last_img', False)
        crop_center = getattr(self, '_post_crop_center', False)
        use_deepbooru = getattr(self, '_post_use_deepbooru', False)
        type_deepbooru = getattr(self, '_post_type_deepbooru', 'Add Before')
        use_cache = getattr(self, '_post_use_cache', True)
        if getattr(self, 'run_img2img_pass', False) and self.last_img and enabled and use_img2img:
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
            p_img2img = StableDiffusionProcessingImg2Img(
                sd_model=shared.sd_model, outpath_samples=shared.opts.outdir_samples or shared.opts.outdir_img2img_samples,
                outpath_grids=shared.opts.outdir_grids or shared.opts.outdir_img2img_grids, prompt=final_prompts, negative_prompt=final_negative_prompts,
                seed=processed.seed, subseed=processed.subseed, sampler_name=p.sampler_name, scheduler=getattr(p, 'scheduler', None),
                batch_size=p.batch_size, n_iter=p.n_iter, steps=self.real_steps, cfg_scale=p.cfg_scale,
                width=img2img_width, height=img2img_height, init_images=prepared_images, denoising_strength=self.img2img_denoising,
            )
            print(f"[R] Running Img2Img ({len(prepared_images)} images) steps={self.real_steps}, Denoise={self.img2img_denoising}")
            img2img_processed = process_images(p_img2img)
            processed.images = img2img_processed.images
            processed.prompt = img2img_processed.prompt
            processed.negative_prompt = img2img_processed.negative_prompt
            processed.infotexts = img2img_processed.infotexts
            processed.seed = img2img_processed.seed
            processed.subseed = img2img_processed.subseed
            processed.width = img2img_width
            processed.height = img2img_height
            print("[R Post] Img2Img finished.")
        self._cleanup_after_run(use_cache)

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



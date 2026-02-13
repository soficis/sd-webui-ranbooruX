import re
import modules.scripts as scripts


def _strip_comments_from_single_text(text_content: str) -> str:
    if not isinstance(text_content, str):
        return text_content
    text_content = re.sub(r'(^|\n)#[^\n]*(\n|$)', '\n', text_content)
    text_content = re.sub(r'(^|\n)//[^\n]*(\n|$)', '\n', text_content)
    text_content = re.sub(r'/\*(.*?)\*/', '', text_content, flags=re.S)
    return text_content


def strip_comments(input_data):
    if isinstance(input_data, list):
        processed_list = []
        for item in input_data:
            if isinstance(item, str):
                processed_list.append(_strip_comments_from_single_text(item))
            else:
                processed_list.append(item)
        return processed_list
    elif isinstance(input_data, str):
        return _strip_comments_from_single_text(input_data)
    else:
        return input_data


class Script(scripts.Script):
    def title(self):
        return "Comments"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def process(self, p, *args):
        if hasattr(p, 'prompt'):
            p.prompt = strip_comments(p.prompt)
        if hasattr(p, 'negative_prompt'):
            p.negative_prompt = strip_comments(p.negative_prompt)
        if hasattr(p, 'hr_prompt'):
            p.hr_prompt = strip_comments(p.hr_prompt)
        if hasattr(p, 'hr_negative_prompt'):
            p.hr_negative_prompt = strip_comments(p.hr_negative_prompt)
        if hasattr(p, 'all_prompts') and isinstance(p.all_prompts, list):
            p.all_prompts = strip_comments(p.all_prompts)
        if hasattr(p, 'all_negative_prompts') and isinstance(p.all_negative_prompts, list):
            p.all_negative_prompts = strip_comments(p.all_negative_prompts)



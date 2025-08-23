# RanbooruX Examples

## Basic Search
To do a basic search you'll need to set the following parameters:

### Required
- **Booru**: The booru you want to search on.
- **Tags to search (pre)**: The tags to search for on the booru. These should be the same used on a booru, but separated by a comma (e.g. `'1girl, solo'`).

### Optional
- **Max Pages**: How many pages to sample when picking random posts.
- **Tags to remove (post)**: Tags to remove after the search.
- **Use the same prompt for all images**: By default you'll get a different prompt for each image you create. If you want to use the same prompt for all images, set this to true.

## Post ID
You can search for a specific post ID by setting the following parameters:

### Required
- **Booru**: The booru you want to search on. Konachan and yande.re don't support this.
- **Post ID**: The ID of the post you want to search for. This is the number at the end of the URL of the post. (e.g. `https://danbooru.donmai.us/posts/123456` --> `123456`)

### Optional
- **Tags to remove (post)**: These are the tags to remove from the prompt after the search. (e.g. If you search for `'1girl, solo'` and remove `'solo'`, the final prompt won't have `'solo'` in it.)

## Img2Img
Use the prompt plus the original image of the selected booru posts to create an Img2Img image:

### Required
- **Booru**: The booru you want to search on.
- **Tags to search (pre)**: The tags to search for on the booru. These should be the same used on a booru, but separated by a comma (e.g. `'1girl, solo'`).
- **Use img2img**: Set this to true to use the img2img mode.

### Optional
- **Max Pages**: How many pages to sample when picking random posts.
- **Tags to remove (post)**: Tags to remove after the search.
- **Use the same prompt for all images**: Reuse same prompt across batch.
- **Denoising Strength**: Strength for Img2Img; default 0.75.
- **Use last image as img2img**: Reuse the same source image across the batch.
- **ControlNet**: If enabled, RanbooruX configures Unit 0 via ControlNet external API, falling back to p.script_args automatically.

## Additional Modes
These can be used with the Basic Search and img2img examples.
### Mixing prompts
Enable `Mix prompts` to create prompts from a mixture of N posts (`Mix Amount`).
### Chaos Mode
By enabling `Chaos Mode` each image will have an amount of tags moved to the negative prompt. The amount is defined by the `Chaos Amount` parameter, for example 0.5 means 50% of the tags will be moved to the negative prompt. Using the `Less Chaos` option won't move the tags you manually insert in the negative prompt.
### Negative Mode
By enabling `Negative Mode` each image will have all tags moved to the negative prompt.
### LoRAnado
By enabling `Use LoRAnado` you can add random LoRAs to the prompt. Configure the folder (root or subfolder), the min/max weight range, and the amount to sample. Optionally pin previous selections with `Lock Previous LoRAs`.

## Notes
- RanbooruX logs canonical post URLs for selected items (e.g., `https://danbooru.donmai.us/posts/<id>`).
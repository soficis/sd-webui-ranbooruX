# Paths, files, and logs

RanbooruX uses a per‑extension **`user/`** folder inside the extension directory.

```
extensions/sd-webui-ranbooruX/
  user/
    search/   # Put .txt or .csv lists of tags (one line = one entry)
    remove/   # Put .txt or .csv lists of tags to strip out
    logs/     # Prompt + source post logging (optional)
    cookies/  # Drop cookies if you need authenticated access for a booru
```

### Environment variables

- `SD_FORGE_CONTROLNET_PATH` or `RANBOORUX_CN_PATH` — override the detected Forge ControlNet path.

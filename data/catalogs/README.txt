Danbooru Catalog Format
=======================

The bundled catalog file `danbooru_tags.csv` uses UTF-8 encoding and supports
either of these formats:

1) Header-based (preferred):
   tag,category,count,alias
   1girl,0,4974288,"sole_female,1girls"

2) Headerless (auto-detected):
   1girl,0,4974288,"sole_female,1girls"

Required columns:
- column 1: tag/name (string)
- column 2: category (integer)
- column 3: count (integer)

Optional column:
- column 4: alias/aliases (comma or whitespace-separated)

Custom files imported from the UI are copied into `user/catalogs/`.

Licensing Notes (researched 2026-02-13)
=======================================

The bundled `danbooru_tags.csv` is a tag metadata table. For provenance and license
context, see:

- Hugging Face dataset `newtextdoc1111/danbooru-tag-csv` (declared license: MIT):
  https://huggingface.co/datasets/newtextdoc1111/danbooru-tag-csv
- Hugging Face dataset `trojblue/danbooru2025-metadata` (declared license: MIT):
  https://huggingface.co/datasets/trojblue/danbooru2025-metadata
- Danbooru Terms of Service mirror including API and metadata notes:
  https://booru.touhoudiscord.net/static/terms_of_service

Important:
- Danbooru terms still govern API usage and acceptable use.
- The terms include a note that factual metadata (for example tags/timestamps) is
  generally not copyrightable.
- This note is for engineering provenance tracking, not legal advice.

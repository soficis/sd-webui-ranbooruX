def test_prompting_import():
    import ranboorux.prompting as prompting

    assert prompting.remove_repeated_tags("a, b, a") == "a,b"


def test_image_ops_import():
    import ranboorux.image_ops as image_ops

    assert hasattr(image_ops, "resize_image")


def test_io_lists_import():
    import ranboorux.io_lists as io_lists

    assert hasattr(io_lists, "read_list_file")


def test_catalog_import():
    import ranboorux.catalog as catalog

    assert hasattr(catalog, "validate_catalog_csv")

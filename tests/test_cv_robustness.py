import numpy as np
import pytest
from PIL import Image
from cv.eval_robustness import purged_photo_splits
from cv.model_views import prepare_view


def test_purged_blocks_hold_each_photo_once_without_adjacent_leakage():
    labels = np.array(["egg"] * 20 + ["stress_ball"] * 22 + ["can"] * 8)
    splits = list(purged_photo_splits(labels))
    assert len(splits) == 5
    assert sorted(i for _, test in splits for i in test) == list(range(50))
    for train, test in splits:
        assert not set(train) & set(test)
        assert set(labels[train]) == set(labels)
        for label in set(labels):
            ids = np.flatnonzero(labels == label)
            positions = [i for i, photo in enumerate(ids) if photo in test]
            forbidden = ids[max(0, min(positions)-2):max(positions)+3]
            assert not set(forbidden) & set(train)


def test_reject_bad_purge_configuration():
    with pytest.raises(ValueError):
        list(purged_photo_splits(["egg"] * 4 + ["can"] * 4))
    with pytest.raises(ValueError):
        list(purged_photo_splits(["egg"] * 8, folds=1))


def test_views_are_explicit_and_do_not_modify_input():
    source = Image.new("RGB", (100, 100), "blue")
    source.paste("red", (0, 0, 100, 40))
    hand = prepare_view(source, "hand")
    assert hand.size == (224, 224)
    assert hand.getpixel((112, 112)) == (0, 0, 255)
    assert source.getpixel((0, 0)) == (255, 0, 0)
    assert prepare_view(source, "center").size == source.size
    assert prepare_view(source, "full").size == (224, 224)
    with pytest.raises(ValueError):
        prepare_view(source, "automatic")

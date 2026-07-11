#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path

from utils.user_paths import _seed_directory_children


def test_seed_directory_children_skips_existing_when_not_overwriting(tmp_path):
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    (src / "Researcher").mkdir(parents=True)
    (src / "Researcher" / "general_prompts.yaml").write_text("new", encoding="utf-8")
    (dest / "Researcher").mkdir(parents=True)
    (dest / "Researcher" / "general_prompts.yaml").write_text("old", encoding="utf-8")

    _seed_directory_children(src, dest, overwrite_existing=False)

    assert (dest / "Researcher" / "general_prompts.yaml").read_text(encoding="utf-8") == "old"


def test_seed_directory_children_overwrites_existing_directory(tmp_path):
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    (src / "Researcher").mkdir(parents=True)
    (src / "Researcher" / "general_prompts.yaml").write_text("new", encoding="utf-8")
    (dest / "Researcher").mkdir(parents=True)
    (dest / "Researcher" / "general_prompts.yaml").write_text("old", encoding="utf-8")

    _seed_directory_children(src, dest, overwrite_existing=True)

    assert (dest / "Researcher" / "general_prompts.yaml").read_text(encoding="utf-8") == "new"

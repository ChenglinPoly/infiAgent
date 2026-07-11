#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
import pytest

from tool_server_lite.tools.reference_tools import (
    ReferenceAddTool,
    ReferenceDeleteTool,
    ReferenceListTool,
)


@pytest.fixture
def workspace(tmp_path):
    return str(tmp_path)


def _write_bib(path: Path, text: str):
    path.write_text(text, encoding="utf-8")


def test_reference_add_appends_new_key(workspace):
    bib = Path(workspace) / "reference.bib"
    _write_bib(
        bib,
        """@article{key1,
  title={One},
  year={2024}
}
""",
    )

    tool = ReferenceAddTool()
    result = tool.execute(workspace, {
        "bib_path": "reference.bib",
        "entries": ["""@article{key2,
  title={Two},
  year={2025}
}"""],
    })

    assert result["status"] == "success"
    text = bib.read_text(encoding="utf-8")
    assert "@article{key1" in text
    assert "@article{key2" in text


def test_reference_add_updates_existing_key_without_duplicate(workspace):
    bib = Path(workspace) / "reference.bib"
    _write_bib(
        bib,
        """@article{key1,
  title={Old Title},
  year={2024}
}
""",
    )

    tool = ReferenceAddTool()
    result = tool.execute(workspace, {
        "bib_path": "reference.bib",
        "entries": ["""@article{key1,
  title={New Title},
  year={2025}
}"""],
    })

    assert result["status"] == "success"
    text = bib.read_text(encoding="utf-8")
    assert text.count("@article{key1") == 1
    assert "New Title" in text
    assert "Old Title" not in text


def test_reference_delete_removes_exact_key_and_preserves_other_entries(workspace):
    bib = Path(workspace) / "reference.bib"
    _write_bib(
        bib,
        """% comment before
@article{key1,
  title={One},
  year={2024}
}

@article{key2,
  title={Two},
  year={2025}
}
""",
    )

    tool = ReferenceDeleteTool()
    result = tool.execute(workspace, {"bib_path": "reference.bib", "keys": ["key1"]})

    assert result["status"] == "success"
    text = bib.read_text(encoding="utf-8")
    assert "@article{key1" not in text
    assert "@article{key2" in text
    assert "% comment before" in text


def test_reference_delete_handles_nested_braces(workspace):
    bib = Path(workspace) / "reference.bib"
    _write_bib(
        bib,
        """@article{key1,
  title={A {Brace-Aware} Title},
  abstract={Nested {braces {inside}} abstract},
  year={2024}
}

@article{key2,
  title={Stable},
  year={2025}
}
""",
    )

    tool = ReferenceDeleteTool()
    result = tool.execute(workspace, {"bib_path": "reference.bib", "keys": ["key1"]})

    assert result["status"] == "success"
    text = bib.read_text(encoding="utf-8")
    assert "@article{key1" not in text
    assert "@article{key2" in text
    assert "Stable" in text


def test_reference_list_summary_mode(workspace):
    bib = Path(workspace) / "reference.bib"
    _write_bib(
        bib,
        """@article{key1,
  title={One},
  year={2024}
}
""",
    )

    tool = ReferenceListTool()
    result = tool.execute(workspace, {"bib_path": "reference.bib", "output_mode": "summary"})

    assert result["status"] == "success"
    assert '"count": 1' in result["output"]
    assert '"key": "key1"' in result["output"]

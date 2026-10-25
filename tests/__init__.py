import base64
import json

from lattice import codec, dpapi
from lattice.models import Column, Grid, Row


def dummy_grid():
    return Grid([Column("label"), Column("field-a")], [Row(["row-1", "value-1 ✓"])])


def foreign_blob(grid):
    """A DP1: store sealed with other entropy: Windows refuses it like another user's file."""
    inner = codec.pack(json.dumps(grid.to_dict())).encode("ascii")
    return "DP1:" + base64.b85encode(dpapi.protect(inner, entropy=b"other-user")).decode("ascii")

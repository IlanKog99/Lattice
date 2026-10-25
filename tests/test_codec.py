import unittest

from lattice import codec

# Made once by today's codec.pack("dummy-text-1"). Guards _MASK/_TAG: if this
# stops opening, every legacy store in the field stops opening too.
GOLDEN_LEGACY = "7yS*H)4!{r*Jh-%c7IH1ZlgT@T=4$"


class CodecTests(unittest.TestCase):
    def test_golden_legacy_blob_still_opens(self):
        self.assertEqual(codec.unpack(GOLDEN_LEGACY), "dummy-text-1")
        self.assertEqual(codec.open_blob(GOLDEN_LEGACY), "dummy-text-1")

    def test_seal_round_trip(self):
        blob = codec.seal("value-1 ✓")
        self.assertTrue(blob.startswith("DP1:"))
        self.assertNotIn("value-1", blob)
        self.assertEqual(codec.open_blob(blob), "value-1 ✓")

    def test_is_legacy(self):
        self.assertTrue(codec.is_legacy(codec.pack("value-1")))
        self.assertFalse(codec.is_legacy(codec.seal("value-1")))

    def test_garbage_raises_value_error(self):
        for junk in ("hello world", "DP1:###", ""):
            with self.assertRaises(ValueError):
                codec.open_blob(junk)


if __name__ == "__main__":
    unittest.main()

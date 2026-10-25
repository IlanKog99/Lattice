import unittest

from lattice import dpapi


class DpapiTests(unittest.TestCase):
    def test_round_trip(self):
        blob = dpapi.protect(b"value-1")
        self.assertNotIn(b"value-1", blob)
        self.assertEqual(dpapi.unprotect(blob), b"value-1")

    def test_empty_round_trip(self):
        self.assertEqual(dpapi.unprotect(dpapi.protect(b"")), b"")

    def test_wrong_entropy_fails(self):
        blob = dpapi.protect(b"value-1", entropy=b"other-user")
        with self.assertRaises(dpapi.DpapiError):
            dpapi.unprotect(blob)

    def test_garbage_fails(self):
        with self.assertRaises(dpapi.DpapiError):
            dpapi.unprotect(b"not a dpapi blob")


if __name__ == "__main__":
    unittest.main()

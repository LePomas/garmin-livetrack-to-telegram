import email
import email.policy
import unittest
from pathlib import Path

from livetrack_watcher import StateStore, extract_livetrack_link_from_message, is_garmin_livetrack


def load_sample() -> object:
    sample = Path(__file__).resolve().parents[1] / "sample" / "livetrack-email-sample.eml"
    raw = sample.read_bytes()
    return email.message_from_bytes(raw, policy=email.policy.default)


class LiveTrackWatcherTests(unittest.TestCase):
    def test_detects_garmin_livetrack_email(self) -> None:
        msg = load_sample()
        self.assertTrue(is_garmin_livetrack(msg))

    def test_extracts_livetrack_url(self) -> None:
        msg = load_sample()
        url = extract_livetrack_link_from_message(msg)
        self.assertIsNotNone(url)
        assert url is not None
        self.assertIn("livetrack.garmin.com/session/", url.lower())

    def test_state_store_dedup(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            state = StateStore(Path(tmp_dir) / "state.json")
            self.assertFalse(state.seen("id-1"))
            state.add("id-1")
            self.assertTrue(state.seen("id-1"))


if __name__ == "__main__":
    unittest.main()

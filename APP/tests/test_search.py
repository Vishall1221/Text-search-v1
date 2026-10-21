import unittest
from unittest.mock import patch

from APP.backend.query import plan_query
from APP.backend.ranking import rank_candidates, score_scene


CATALOG = [{
    "asset_id": "asset-1", "primary_language": "BENGALI", "title": "Dhumketu",
    "cast_names": ["Dev"], "genres": ["Romance", "Thriller"],
}]


def scene(scene_id, description, order):
    return {
        "asset_id": "asset-1", "primary_language": "BENGALI", "title": "Dhumketu",
        "movie_gcs_path": "gs://bucket/DHUMKETU_bn.mp4", "movie_description": "Story",
        "genres": ["Romance", "Thriller"], "movie_cast": ["Dev"],
        "thumbnail_image_url": None, "total_scenes": 2,
        "scene_id": scene_id, "scene_order": order, "chunk_id": "chunk_001",
        "start_time": "00:02:30" if order == 2 else "00:00:00",
        "end_time": "00:05:45" if order == 2 else "00:02:30",
        "start_seconds": 150.0 if order == 2 else 0.0,
        "end_seconds": 345.0 if order == 2 else 150.0,
        "description": description, "master_scene_summary": description,
        "visual_summary": description, "dialogue_transcript": "", "important_dialogue": "",
        "mood": "Gritty", "action_intensity": "MEDIUM",
        "barc_retention_score": "LOW", "engaging_score": "HIGH", "energy_level": "MEDIUM",
        "scene_cast": ["Dev"], "entities_characters": [], "entities_objects": [],
        "tags": [], "search_text": description,
    }


class SearchTests(unittest.TestCase):
    def test_exact_title_skips_llm(self):
        with patch("APP.backend.query._llm_extract") as llm:
            plan = plan_query("Play Dhumketu movie", CATALOG)
        self.assertEqual(plan.route, "exact_title_fast_path")
        llm.assert_not_called()

    def test_query_language_is_not_movie_language(self):
        with patch("APP.backend.query._llm_extract", return_value={"content_language": "Hindi", "genres": ["Thriller"]}):
            plan = plan_query("Dhumketu mein chai stall scene dikhao", CATALOG)
        self.assertIsNone(plan.language)
        self.assertEqual(plan.genres, [])

    def test_scene_phrase_and_timestamp(self):
        with patch("APP.backend.query._llm_extract", return_value={"scene_phrases": ["tea stall"]}):
            plan = plan_query("Dhumketu tea stall scene", CATALOG)
        rows = [scene("scene_001", "Bhanu works in the village field", 1),
                scene("scene_002", "Bhanu talks at a tea stall", 2)]
        cards = rank_candidates(rows, plan, 8)
        self.assertEqual(cards[0]["match_score"], 0.99)
        self.assertEqual(cards[0]["matched_scenes"][0]["scene_id"], "scene_002")
        self.assertEqual(cards[0]["matched_scenes"][0]["start_seconds"], 150.0)
        self.assertEqual(cards[0]["matched_scenes"][0]["barc_retention_score"], "LOW")

    def test_phrase_beats_no_match_without_vectors(self):
        hit, matched = score_scene(scene("scene_002", "tea stall conversation", 2), ["tea", "stall"], [])
        miss, not_matched = score_scene(scene("scene_001", "village field", 1), ["tea", "stall"], [])
        self.assertTrue(matched)
        self.assertFalse(not_matched)
        self.assertGreater(hit, miss)


if __name__ == "__main__":
    unittest.main()

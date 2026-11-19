import json, tempfile, unittest
from pathlib import Path

from dante import config, models_hub, models_ui as U


class HubInSettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.d = Path(self.tmp.name)
        self.m = self.d / "models.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_own_models_join_settings_before_backups(self):
        models_hub.upsert(self.m, {"name": "cerebras-x", "base_url": "https://api.cerebras.ai/v1", "model": "x",
                                   "key_env": "CEREBRAS_API_KEY", "needs_key": True})
        models_hub.upsert(self.m, {"name": "ollama-y", "base_url": "http://127.0.0.1:11434/v1", "model": "y",
                                   "needs_key": False})
        s = config.load_settings(self.d / "none.toml", self.m)
        order = list(s.order)
        self.assertLess(order.index("cerebras-x"), order.index("local"))
        by = {p.name: p for p in s.providers}
        self.assertFalse(by["cerebras-x"].backup)
        self.assertTrue(by["ollama-y"].backup)
        self.assertEqual(by["ollama-y"].api_key, "local")

    def test_paid_own_model_keeps_prices_and_is_off_by_default(self):
        models_hub.upsert(self.m, {"name": "pay-z", "base_url": "https://a.b/v1", "model": "z", "key_env": "PAY_KEY",
                                   "needs_key": True, "paid": True, "price_in": 0.5, "price_out": 1.5})
        s = config.load_settings(self.d / "none.toml", self.m)
        p = next(p for p in s.providers if p.name == "pay-z")
        self.assertEqual((p.paid, p.price_in_usd_per_m, p.price_out_usd_per_m), (True, 0.5, 1.5))
        self.assertFalse(s.allow_paid)

    def test_no_file_changes_nothing(self):
        self.assertEqual(config.load_settings(self.d / "none.toml", self.m), config.Settings())

    def test_models_json_is_protected_from_the_llm(self):
        self.assertIn("models.json", config.Settings().protected_paths)


class PresetsTest(unittest.TestCase):
    def test_presets_valid_and_no_russian_services(self):
        for p in U.PRESETS[1:]:
            self.assertEqual([f for f in models_hub.validate(
                {"name": "ok-name", "base_url": p.base_url, "model": "m", "key_env": p.key_env,
                 "needs_key": p.needs_key, "paid": False, "price_in": 0.0, "price_out": 0.0, "note": ""}, set())], [], p.id)
            for bad in ("yandex", "gigachat", "sber"):
                self.assertNotIn(bad, p.base_url)

    def test_unknown_service_is_paid_by_default(self):
        self.assertTrue(U.preset("custom").paid)

    def test_suggest_name(self):
        p = U.preset("cerebras")
        self.assertEqual(U.suggest_name(p, "llama-3.3-70b", set()), "cerebras-llama-3-3-70b")
        self.assertEqual(U.suggest_name(p, "llama-3.3-70b", {"cerebras-llama-3-3-70b"}), "cerebras-llama-3-3-70b-2")
        n = U.suggest_name(U.preset("openrouter"), "meta-llama/Llama-3.3-70B-Instruct:free" * 3, set())
        self.assertEqual(models_hub.validate({"name": n, "base_url": "https://a.b", "model": "m", "key_env": "",
                                              "needs_key": False, "paid": False, "price_in": 0, "price_out": 0}, set()), [])

    def test_ping_refuses_paid(self):
        with self.assertRaises(PermissionError):
            U.ping("https://a.b/v1", "m", "k", paid=True)


if __name__ == "__main__":
    unittest.main()
